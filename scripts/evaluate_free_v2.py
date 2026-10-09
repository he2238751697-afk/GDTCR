#!/usr/bin/env python3
"""Strict fixed-draw evaluation with saved tokens and nested sampling budgets."""

from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gdtcr.data import build_source_map, read_pairs
from gdtcr.evaluation import decode_sample_v2, ranked_generation_metrics
from gdtcr.model import CHAIN_TO_ID, make_batch
from gdtcr.provenance import begin_run, finish_run
from gdtcr.training import load_checkpoint, load_ranker, sequence_mean_nll, set_seed
from nearest_sequences_v2 import nearest
from calibrate_scores_v2 import verify_settings


DIRECTIONS = ("gamma_to_delta", "delta_to_gamma")


def mean(values):
    return sum(values) / len(values) if values else 0.0


def entropy(values):
    if not values:
        return 0.0
    counts = Counter(values)
    return -sum((count / len(values)) * math.log(count / len(values))
                for count in counts.values())


def query_targets(pairs, direction):
    index = 0 if direction == "gamma_to_delta" else 1
    result = defaultdict(set)
    for pair in pairs:
        result[pair[index]].add(pair[1 - index])
    return {source: sorted(targets) for source, targets in sorted(result.items())}


def unique_in_order(values):
    return list(dict.fromkeys(values))


def candidate_neighbors(candidates, train_targets):
    if not candidates:
        return []
    reference = sorted(train_targets)
    distances = nearest(candidates, reference, workers=1)
    for row in distances:
        row["nearest_raw"] = reference[row.pop("nearest_raw_index")]
        row["nearest_normalized"] = reference[row.pop("nearest_normalized_index")]
        row["normalized_similarity"] = 1. - row["min_normalized"]
    return distances


def score_ranker(ranker, source_chain, source, target_chain, candidates, batch_size):
    if ranker is None:
        return None
    if not candidates:
        return []
    with torch.inference_mode():
        source_vector = ranker.encode_sequences(source_chain, [source])
        result = []
        for start in range(0, len(candidates), batch_size):
            chunk = candidates[start:start + batch_size]
            target_vectors = ranker.encode_sequences(target_chain, chunk)
            result.extend(ranker.score_queries(source_chain, source_vector,
                                                target_vectors)[0].float().cpu().tolist())
    return result


def summarize_prefix(samples, positives, train_targets, candidate_scores, budgets):
    summaries = {}
    scores = {source: values for source, values in candidate_scores.items() if values is not None}
    for budget in budgets:
        if budget > len(samples):
            continue
        prefix = samples[:budget]
        valid = [sample["sequence"] for sample in prefix if sample["valid"]]
        for policy in ("allow_training_targets", "exclude_training_targets"):
            kept = valid if policy == "allow_training_targets" else [x for x in valid if x not in train_targets]
            candidates = unique_in_order(kept)
            method_metrics = {"raw": ranked_generation_metrics(positives, candidates)}
            for name, method_scores in scores.items():
                ordered = sorted(candidates,
                                 key=lambda value: (-method_scores[value], value))
                method_metrics[name] = ranked_generation_metrics(positives, ordered)
            summaries[f"{budget}/{policy}"] = {
                "draws": budget, "valid_draws": len(valid), "kept_draws": len(kept),
                "invalid_reasons": dict(Counter(sample["reason"] for sample in prefix if not sample["valid"])),
                "unique_candidates": len(candidates),
                "recovered_partners": len(set(positives) & set(candidates)),
                "positive_count": len(positives),
                "reachable_positive_count": len(positives) if policy == "allow_training_targets" else
                                            sum(value not in train_targets for value in positives),
                "exact_training_target_draws": sum(value in train_targets for value in valid),
                "novel_draw_fraction": mean([float(value not in train_targets) for value in valid]),
                "unique_fraction_of_kept": len(candidates) / max(len(kept), 1),
                "length_entropy": entropy([len(value) for value in kept]),
                "terminal_motif_entropy": entropy([(value[:3], value[-3:]) for value in kept]),
                "methods": method_metrics,
            }
    return summaries


def summarize_rows(rows):
    if not rows:
        return {"n_queries": 0, "n_edges": 0, "prefixes": {}}
    keys = rows[0]["prefixes"]
    result = {"n_queries": len(rows), "n_edges": sum(len(row["positives"]) for row in rows),
              "conditional_query_macro_nll": mean([row["positive_query_mean_nll"] for row in rows]),
              "conditional_token_weighted_nll": sum(row["positive_nll_token_sum"] for row in rows) /
                                                max(sum(row["positive_token_count"] for row in rows), 1),
              "prefixes": {}}
    for key in keys:
        entries = [row["prefixes"][key] for row in rows]
        methods = {}
        for method in entries[0]["methods"]:
            metrics = entries[0]["methods"][method]
            methods[method] = {name: mean([entry["methods"][method][name] for entry in entries])
                               for name in metrics}
        result["prefixes"][key] = {
            "valid_draw_fraction": sum(entry["valid_draws"] for entry in entries) /
                                   max(sum(entry["draws"] for entry in entries), 1),
            "kept_draw_fraction": sum(entry["kept_draws"] for entry in entries) /
                                  max(sum(entry["draws"] for entry in entries), 1),
            "mean_unique_candidates": mean([entry["unique_candidates"] for entry in entries]),
            "mean_novel_draw_fraction": mean([entry["novel_draw_fraction"] for entry in entries]),
            "edge_weighted_recovery": sum(entry["recovered_partners"] for entry in entries) /
                                      max(sum(entry["positive_count"] for entry in entries), 1),
            "methods": methods,
        }
    return result


def evaluate_direction(model, ranker, pairs, train_pairs, direction, args, device):
    source_chain, target_chain = (("gamma", "delta") if direction == "gamma_to_delta"
                                  else ("delta", "gamma"))
    positive_map = query_targets(pairs, direction)
    train_targets = {pair[1 if direction == "gamma_to_delta" else 0] for pair in train_pairs}
    shuffled = build_source_map(list(positive_map), args.seed + (direction == "delta_to_gamma")) \
        if args.source_mode == "shuffled" else {}
    generator = torch.Generator(device=device).manual_seed(
        args.seed + (direction == "delta_to_gamma"))
    model.eval()
    if ranker is not None:
        ranker.eval()
    rows = []
    budgets = sorted({budget for budget in (16, 64, 256) if budget <= args.samples} | {args.samples})
    for query_index, (source, positives) in enumerate(positive_map.items()):
        conditioned_source = ("" if args.source_mode == "constant" else
                              shuffled[source] if args.source_mode == "shuffled" else source)
        batch = make_batch([(source_chain, conditioned_source)], device)
        with torch.inference_mode():
            tokens = model.sample(batch["source"], CHAIN_TO_ID[target_chain],
                                  max_new_tokens=36, temperature=args.temperature,
                                  top_p=args.top_p, num_samples=args.samples,
                                  generator=generator).cpu().tolist()
        samples = [decode_sample_v2(value, target_chain) for value in tokens]
        candidates = unique_in_order(sample["sequence"] for sample in samples if sample["valid"])
        positive_nll = sequence_mean_nll(
            model, [(source_chain, conditioned_source)] * len(positives),
            [(target_chain, value) for value in positives], device, args.batch_size)
        candidate_nll = sequence_mean_nll(
            model, [(source_chain, conditioned_source)] * len(candidates),
            [(target_chain, value) for value in candidates], device, args.batch_size)
        ranker_source = source if args.ranker_source_mode == "paired" else conditioned_source
        ranker_values = score_ranker(ranker, source_chain, ranker_source, target_chain,
                                     candidates, args.batch_size)
        candidate_scores = {
            "likelihood": dict(zip(candidates, (-value for value in candidate_nll))),
            "ranker": dict(zip(candidates, ranker_values)) if ranker_values is not None else None,
        }
        row = {"source": source, "conditioned_source": conditioned_source,
               "ranker_source": ranker_source if ranker is not None else None,
               "source_chain": source_chain, "target_chain": target_chain,
               "positives": positives, "samples": samples,
               "candidate_sequences": candidates, "candidate_nll": candidate_nll,
               "candidate_ranker_score": ranker_values,
               "candidate_nearest_supervised": candidate_neighbors(candidates, train_targets),
               "positive_nll": positive_nll,
               "positive_query_mean_nll": mean(positive_nll),
               "positive_nll_token_sum": sum(nll * (len(value) + 1)
                                             for nll, value in zip(positive_nll, positives)),
               "positive_token_count": sum(len(value) + 1 for value in positives),
               "prefixes": summarize_prefix(samples, positives, train_targets,
                                             candidate_scores, budgets)}
        rows.append(row)
        if (query_index + 1) % 50 == 0:
            print(json.dumps({"direction": direction, "queries_done": query_index + 1,
                              "queries_total": len(positive_map)}), flush=True)
    return rows, summarize_rows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generator", type=Path)
    parser.add_argument("--generator-gamma-to-delta", type=Path)
    parser.add_argument("--generator-delta-to-gamma", type=Path)
    parser.add_argument("--ranker", type=Path)
    parser.add_argument("--pairs", type=Path, required=True)
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--settings", type=Path,
                        help="Frozen calibration settings required before the final test stage")
    parser.add_argument("--directions", choices=("both", *DIRECTIONS), default="both")
    parser.add_argument("--source-mode", choices=("paired", "constant", "shuffled"), default="paired")
    parser.add_argument("--ranker-source-mode", choices=("paired", "same"), default="paired")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--seed", type=int, default=3407)
    parser.add_argument("--samples", type=int, default=64)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--temperature", type=float, default=1.)
    parser.add_argument("--top-p", type=float, default=.95)
    args = parser.parse_args()
    if args.samples < 1 or args.batch_size < 1:
        raise ValueError("Samples and batch size must be positive")
    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested without a GPU")
    directions = DIRECTIONS if args.directions == "both" else (args.directions,)
    generator_paths = {direction: (getattr(args, "generator_" + direction) or args.generator)
                       for direction in directions}
    if any(path is None for path in generator_paths.values()):
        parser.error("Provide a shared generator or one generator per evaluated direction")
    settings_record = verify_settings(args.settings, "free", args)
    inputs = [args.pairs, args.train, *generator_paths.values(), args.ranker, args.settings]
    set_seed(args.seed)
    begin_run(args.output, args, inputs)
    device = torch.device(args.device)
    started = time.monotonic()
    pairs, train_pairs = read_pairs(args.pairs), read_pairs(args.train)
    loaded = {}
    result = {"schema_version": 2, "rows_file": "rows.json.gz", "directions": {},
              "calibration_settings": settings_record,
              "method_order": "raw encounter order; descending negative mean NLL; descending ranker score",
              "validity": "standard amino acids, length 6-35, observed EOS within 36 new tokens",
              "mean_positive_rank": "mean over all recorded partners; unrecovered partners have rank number_of_unique_candidates+1"}
    rows_by_direction = {}
    for direction, path in generator_paths.items():
        if str(path) not in loaded:
            loaded[str(path)] = load_checkpoint(path, device)[0]
        ranker = load_ranker(args.ranker, device) if args.ranker else None
        rows, summary = evaluate_direction(loaded[str(path)], ranker, pairs,
                                           train_pairs, direction, args, device)
        rows_by_direction[direction] = rows
        result["directions"][direction] = summary
    result["evaluation_seconds"] = time.monotonic() - started
    result["peak_allocated_gib"] = torch.cuda.max_memory_allocated(device) / 2**30 if device.type == "cuda" else None
    with gzip.open(args.output / "rows.json.gz", "wt", encoding="utf-8", compresslevel=6) as handle:
        json.dump(rows_by_direction, handle, sort_keys=True, separators=(",", ":"))
    (args.output / "summary.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    finish_run(args.output)
    print(json.dumps({"output": str(args.output), "directions": result["directions"]}, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
