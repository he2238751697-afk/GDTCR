#!/usr/bin/env python3
"""Score one frozen retrieval pool using likelihood, prior, shuffle and ranker."""

from __future__ import annotations

import argparse
import gzip
import json
import random
import sys
import time
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gdtcr.data import build_source_map
from gdtcr.fileio import file_sha256
from gdtcr.metrics import rank_summary
from gdtcr.provenance import begin_run, finish_run
from gdtcr.training import load_checkpoint, load_ranker, sequence_mean_nll, set_seed
from calibrate_scores_v2 import verify_settings


DIRECTIONS = ("gamma_to_delta", "delta_to_gamma")
METHODS = ("likelihood", "ranker", "prior", "shuffled", "difference", "random")
METRICS = ("hit_at_1", "hit_at_5", "hit_at_10", "recall_at_1", "recall_at_5",
           "recall_at_10", "mrr", "mean_positive_rank")


def model_scores(model, source_chain, source, target_chain, candidates, device, batch_size):
    if model is None:
        return None
    scores = sequence_mean_nll(model, [(source_chain, source)] * len(candidates),
                               [(target_chain, candidate) for candidate in candidates],
                               device, batch_size)
    return [-value for value in scores]


def encode_target_universe(ranker, target_chain, targets, batch_size):
    if ranker is None:
        return None
    with torch.inference_mode():
        vectors = [ranker.encode_sequences(target_chain, targets[start:start + batch_size])
                   for start in range(0, len(targets), batch_size)]
    return torch.cat(vectors)


def ranker_scores(ranker, source_chain, source, target_vectors):
    if ranker is None:
        return None
    with torch.inference_mode():
        vector = ranker.encode_sequences(source_chain, [source])
        return ranker.score_queries(source_chain, vector, target_vectors)[0].float().cpu().tolist()


def summary_for_pool(positives, targets, indices, method_scores):
    candidates = [targets[index] for index in indices]
    output = {}
    for method, scores in method_scores.items():
        if scores is None:
            continue
        values = [scores[index] for index in indices]
        result = rank_summary(candidates, positives, values, descending=True)
        output[method] = {key: result[key] for key in METRICS}
    return output


def summarize(rows):
    if not rows:
        return {"n_queries": 0, "pools": {}}
    result = {"n_queries": len(rows), "n_edges": sum(len(row["positives"]) for row in rows),
              "pools": {}}
    for pool in rows[0]["pool_metrics"]:
        methods = {}
        for method in rows[0]["pool_metrics"][pool]:
            methods[method] = {
                metric: sum(row["pool_metrics"][pool][method][metric] for row in rows) / len(rows)
                for metric in METRICS}
        result["pools"][pool] = {"n_candidates_mean": sum(
            len(row["pool_indices"][pool]) for row in rows) / len(rows),
                                  "methods": methods}
    return result


def evaluate_direction(pool, model, prior, ranker, direction, args, device):
    entry = pool["directions"][direction]
    source_chain, target_chain = entry["source_chain"], entry["target_chain"]
    targets = entry["target_universe"]
    target_indices = {target: index for index, target in enumerate(targets)}
    queries = entry["rows"]
    shuffled = build_source_map([row["source"] for row in queries], args.seed +
                                (direction == "delta_to_gamma"))
    prior_full = model_scores(prior, source_chain, "", target_chain, targets,
                              device, args.batch_size)
    target_vectors = encode_target_universe(ranker, target_chain, targets, args.batch_size)
    output = []
    for row_index, row in enumerate(queries):
        source = row["source"]
        conditioned = "" if args.source_mode == "constant" else source
        likelihood = model_scores(model, source_chain, conditioned, target_chain,
                                  targets, device, args.batch_size)
        shuffled_scores = model_scores(model, source_chain, shuffled[source],
                                       target_chain, targets, device, args.batch_size) \
            if args.source_mode == "paired" else None
        ranker_full = ranker_scores(ranker, source_chain, source, target_vectors)
        differences = [current - baseline for current, baseline in zip(likelihood, prior_full)] \
            if prior_full is not None else None
        rng = random.Random(args.seed + row_index * 1009 + (direction == "delta_to_gamma"))
        random_scores = [rng.random() for _ in targets]
        scores = {"likelihood": likelihood, "ranker": ranker_full, "prior": prior_full,
                  "shuffled": shuffled_scores, "difference": differences,
                  "random": random_scores}
        indices = {name: [target_indices[value] for value in candidates]
                   for name, candidates in row["pools"].items()}
        indices["full"] = [target_indices[value] for value in row["full_candidates"]]
        result = {"source": source, "positives": row["positives"],
                  "conditioned_source": conditioned, "shuffled_source": shuffled[source],
                  "pool_indices": indices, "scores": scores,
                  "pool_metrics": {name: summary_for_pool(row["positives"], targets,
                                                          candidates, scores)
                                   for name, candidates in indices.items()}}
        output.append(result)
        if (row_index + 1) % 50 == 0:
            print(json.dumps({"direction": direction, "queries_done": row_index + 1,
                              "queries_total": len(queries)}), flush=True)
    return output, summarize(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pool", type=Path, required=True)
    parser.add_argument("--generator", type=Path, required=True)
    parser.add_argument("--prior", type=Path)
    parser.add_argument("--prior-gamma-to-delta", type=Path)
    parser.add_argument("--prior-delta-to-gamma", type=Path)
    parser.add_argument("--ranker", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--settings", type=Path,
                        help="Frozen calibration settings required before the final test stage")
    parser.add_argument("--directions", choices=("both", *DIRECTIONS), default="both")
    parser.add_argument("--source-mode", choices=("paired", "constant"), default="paired")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--seed", type=int, default=3407)
    args = parser.parse_args()
    if args.batch_size < 1:
        raise ValueError("batch size must be positive")
    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested without a GPU")
    directions = DIRECTIONS if args.directions == "both" else (args.directions,)
    priors = {direction: getattr(args, "prior_" + direction) or args.prior
              for direction in directions}
    settings_record = verify_settings(args.settings, "pools", args)
    set_seed(args.seed)
    begin_run(args.output, args, [args.pool, args.generator, args.ranker, *priors.values(), args.settings])
    device = torch.device(args.device)
    started = time.monotonic()
    with gzip.open(args.pool, "rt", encoding="utf-8") as handle:
        pool = json.load(handle)
    model = load_checkpoint(args.generator, device)[0]
    model.eval()
    ranker = load_ranker(args.ranker, device) if args.ranker else None
    loaded_priors = {}
    rows, summaries = {}, {}
    for direction in directions:
        prior_path = priors[direction]
        if prior_path is not None and str(prior_path) not in loaded_priors:
            loaded_priors[str(prior_path)] = load_checkpoint(prior_path, device)[0]
            loaded_priors[str(prior_path)].eval()
        prior = loaded_priors.get(str(prior_path)) if prior_path else None
        rows[direction], summaries[direction] = evaluate_direction(
            pool, model, prior, ranker, direction, args, device)
    with gzip.open(args.output / "rows.json.gz", "wt", encoding="utf-8", compresslevel=6) as handle:
        json.dump(rows, handle, sort_keys=True, separators=(",", ":"))
    result = {"schema_version": 2, "pool_sha256": file_sha256(args.pool),
              "calibration_settings": settings_record,
              "rows_file": "rows.json.gz", "directions": summaries,
              "scores": "higher is better; likelihood is negative per-target-token NLL including EOS",
              "evaluation_seconds": time.monotonic() - started,
              "peak_allocated_gib": torch.cuda.max_memory_allocated(device) / 2**30 if device.type == "cuda" else None,
              "negative_definition": pool["negative_definition"]}
    (args.output / "summary.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    finish_run(args.output)
    print(json.dumps({"output": str(args.output), "directions": summaries}, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
