#!/usr/bin/env python3
"""Evaluate a trained generator and optional independent pair ranker."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gdtcr.data import build_source_map, read_pairs
from gdtcr.model import BOS, CHAIN_TO_ID, EOS, ID_TO_AA, make_batch
from gdtcr.training import corpus_token_nll, load_checkpoint, load_ranker, set_seed


def decode_sample(ids):
    """Decode one model sample, returning None for malformed output."""
    if len(ids) < 2 or ids[0] != BOS:
        return None
    residues = []
    for token in ids[2:]:
        token = int(token)
        if token == EOS:
            break
        if token == 0:
            break
        if token not in ID_TO_AA:
            return None
        residues.append(ID_TO_AA[token])
    return "".join(residues) if residues else None


def conditional_nll(model, pairs, direction, device, batch_size, source_mode="paired",
                     source_map=None):
    rows = []
    for gamma, delta in pairs:
        if direction == "gamma_to_delta":
            source_chain, source_sequence = "gamma", gamma
            target = ("delta", delta)
        else:
            source_chain, source_sequence = "delta", delta
            target = ("gamma", gamma)
        if source_mode == "constant":
            source_sequence = ""
        elif source_mode == "shuffled":
            source_sequence = source_map[source_sequence]
        rows.append(((source_chain, source_sequence), target))
    return corpus_token_nll(model, [item[0] for item in rows],
                            [item[1] for item in rows], device, batch_size)


def rank_candidates(ranker, source_chain, source_sequence, candidates):
    if ranker is None or not candidates:
        return list(candidates)
    with torch.inference_mode():
        source_vectors = ranker.encode_sequences(source_chain, [source_sequence])
        target_chain = "delta" if source_chain == "gamma" else "gamma"
        target_vectors = ranker.encode_sequences(target_chain, candidates)
        scores = ranker.score_queries(source_chain, source_vectors, target_vectors)[0]
    order = sorted(range(len(candidates)), key=lambda i: (-float(scores[i]), i))
    return [candidates[i] for i in order]


def evaluate_direction(model, ranker, pairs, direction, args, device, source_map=None):
    query_targets = defaultdict(set)
    for gamma, delta in pairs:
        if direction == "gamma_to_delta":
            query_targets[gamma].add(delta)
        else:
            query_targets[delta].add(gamma)
    source_chain = "gamma" if direction == "gamma_to_delta" else "delta"
    target_chain = "delta" if source_chain == "gamma" else "gamma"
    queries = sorted(query_targets)
    if args.source_mode == "shuffled" and source_map is None:
        source_map = build_source_map(queries, args.seed + (0 if source_chain == "gamma" else 1))
    rows = []
    raw_hits = {1: 0, 5: 0, 10: 0}
    reranked_hits = {1: 0, 5: 0, 10: 0}
    covered = 0
    valid = 0
    sampled = 0
    unique_total = 0
    model.eval()
    generator = torch.Generator(device=device).manual_seed(args.seed + (0 if source_chain == "gamma" else 1))
    with torch.inference_mode():
        for start in range(0, len(queries), args.batch_size):
            query_chunk = queries[start:start + args.batch_size]
            conditioned = []
            for query in query_chunk:
                if args.source_mode == "constant":
                    conditioned.append("")
                elif args.source_mode == "shuffled":
                    conditioned.append(source_map[query])
                else:
                    conditioned.append(query)
            batch = make_batch([(source_chain, query) for query in conditioned], device)
            samples = model.sample(batch["source"], CHAIN_TO_ID[target_chain],
                                   max_new_tokens=args.max_new_tokens,
                                   temperature=args.temperature, top_p=args.top_p,
                                   num_samples=args.samples, generator=generator)
            samples = samples.view(len(query_chunk), args.samples, -1).cpu().tolist()
            for query, query_samples in zip(query_chunk, samples):
                decoded = [decode_sample(item) for item in query_samples]
                valid_candidates = [item for item in decoded if item is not None]
                candidates = list(dict.fromkeys(valid_candidates))
                sampled += len(decoded)
                valid += len(valid_candidates)
                unique_total += len(candidates)
                positives = query_targets[query]
                if any(item in positives for item in valid_candidates):
                    covered += 1
                raw_order = candidates
                conditioned_source = conditioned[query_chunk.index(query)]
                reranked = rank_candidates(ranker, source_chain, conditioned_source,
                                            candidates)
                for k in raw_hits:
                    raw_hits[k] += int(any(item in positives for item in raw_order[:k]))
                    reranked_hits[k] += int(any(item in positives for item in reranked[:k]))
                rows.append({"source_chain": source_chain, "source": query,
                             "conditioned_source": conditioned_source,
                             "positives": sorted(positives),
                             "samples": decoded, "unique_candidates": candidates,
                             "reranked_candidates": reranked})
    count = max(len(queries), 1)
    metrics = {
        "direction": direction, "n_queries": len(queries),
        "samples_per_query": args.samples,
        "valid_sample_rate": valid / max(sampled, 1),
        "unique_candidates_per_query": unique_total / count,
        "candidate_coverage": covered / count,
        **{f"raw_hit_at_{k}": value / count for k, value in raw_hits.items()},
        **{f"reranked_hit_at_{k}": value / count for k, value in reranked_hits.items()},
    }
    return metrics, rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generator", type=Path,
                        help="Shared checkpoint used for both directions")
    parser.add_argument("--generator-gamma-to-delta", type=Path,
                        help="Direction-specific gamma-to-delta checkpoint")
    parser.add_argument("--generator-delta-to-gamma", type=Path,
                        help="Direction-specific delta-to-gamma checkpoint")
    parser.add_argument("--ranker", type=Path)
    parser.add_argument("--pairs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--seed", type=int, default=3407)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--samples", type=int, default=64)
    parser.add_argument("--max-new-tokens", type=int, default=35)
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--top-p", type=float, default=0.95)
    parser.add_argument("--source-mode", choices=("paired", "shuffled", "constant"),
                        default="paired",
                        help="Condition on the paired query, a deterministic shuffled query, "
                             "or only the chain token")
    args = parser.parse_args()
    if not any((args.generator, args.generator_gamma_to_delta,
                args.generator_delta_to_gamma)):
        parser.error("provide --generator or both direction-specific generators")
    if args.generator is None and not (args.generator_gamma_to_delta and
                                       args.generator_delta_to_gamma):
        parser.error("direction-specific mode requires both generator checkpoints")
    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but no GPU is visible; submit through Slurm")
    if args.samples < 1 or args.batch_size < 1:
        raise ValueError("samples and batch-size must be positive")
    set_seed(args.seed)
    device = torch.device(args.device)
    generator_paths = {
        "gamma_to_delta": args.generator_gamma_to_delta or args.generator,
        "delta_to_gamma": args.generator_delta_to_gamma or args.generator,
    }
    models = {}
    checkpoints = {}
    loaded = {}
    for direction, path in generator_paths.items():
        path_key = str(path)
        if path_key not in loaded:
            loaded[path_key] = load_checkpoint(path, device)
        models[direction], checkpoints[direction] = loaded[path_key]
    ranker = load_ranker(args.ranker, device) if args.ranker else None
    pairs = read_pairs(args.pairs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "generator": str(args.generator) if args.generator else None,
        "generators": {direction: str(path) for direction, path in generator_paths.items()},
        "ranker": str(args.ranker) if args.ranker else None,
        "pairs": str(args.pairs),
        "arguments": {key: str(value) if isinstance(value, Path) else value
                      for key, value in vars(args).items()},
        "model_config": {direction: checkpoints[direction]["model_config"]
                         for direction in checkpoints},
        "parameter_count": {direction: sum(parameter.numel()
                                             for parameter in models[direction].parameters())
                             for direction in models},
        "device": str(device),
        "device_name": torch.cuda.get_device_name(device) if device.type == "cuda" else "cpu",
        "directions": {}, "rows": {},
    }
    for direction in ("gamma_to_delta", "delta_to_gamma"):
        model = models[direction]
        source_map = None
        if args.source_mode == "shuffled":
            source_map = build_source_map(
                sorted({gamma if direction == "gamma_to_delta" else delta
                        for gamma, delta in pairs}),
                args.seed + (0 if direction == "gamma_to_delta" else 1))
        metrics, rows = evaluate_direction(
            model, ranker, pairs, direction, args, device, source_map)
        metrics["conditional_token_nll"] = conditional_nll(
            model, pairs, direction, device, args.batch_size, args.source_mode, source_map)
        result["directions"][direction] = metrics
        result["rows"][direction] = rows
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result["directions"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
