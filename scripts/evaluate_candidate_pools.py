#!/usr/bin/env python3
"""Evaluate conditional likelihood and pair-ranker scores on fixed pools.

Each query contributes all of its recorded test partners plus a deterministic
set of unrecorded candidates drawn from the same test target pool.  The latter
are constructed negatives for ranking diagnostics; they are not treated as
biological negatives.  Candidate lists are generated once per invocation and
stored with the result so generator and ranker comparisons use the same pools.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gdtcr.data import read_pairs
from gdtcr.metrics import normalized_distance, rank_summary
from gdtcr.training import load_checkpoint, load_ranker, sequence_mean_nll


def motif_key(sequence):
    return (sequence[:1], sequence[-1:], len(sequence))


def candidate_lists(query_targets, all_targets, n_negatives, seed):
    """Build deterministic candidate lists for four constructed pools."""
    result = {kind: {} for kind in ("random", "length", "motif", "edit")}
    for query_index, query in enumerate(sorted(query_targets)):
        positives = set(query_targets[query])
        eligible = sorted(set(all_targets) - positives)
        rng = random.Random(seed + query_index * 1009)
        random_pool = rng.sample(eligible, min(n_negatives, len(eligible)))
        positive_lengths = [len(value) for value in positives]
        positive_keys = {motif_key(value) for value in positives}

        length_pool = sorted(
            eligible,
            key=lambda value: (min(abs(len(value) - length) for length in positive_lengths),
                               value),
        )[:n_negatives]
        motif_pool = sorted(
            eligible,
            key=lambda value: (
                0 if motif_key(value) in positive_keys else 1,
                min(normalized_distance(value, positive) for positive in positives),
                value,
            ),
        )[:n_negatives]
        edit_pool = sorted(
            eligible,
            key=lambda value: (min(normalized_distance(value, positive)
                                   for positive in positives), value),
        )[:n_negatives]
        for kind, negatives in (("random", random_pool), ("length", length_pool),
                                ("motif", motif_pool), ("edit", edit_pool)):
            # Lexical order makes the candidate tensor independent of the
            # construction ranking; model scores determine the final order.
            result[kind][query] = sorted(set(positives) | set(negatives))
    return result


def conditional_scores(model, source_chain, query, target_chain, candidates, device,
                       batch_size):
    return sequence_mean_nll(model, [(source_chain, query)] * len(candidates),
                             [(target_chain, value) for value in candidates], device, batch_size)


def ranker_scores(ranker, source_chain, query, target_chain, candidates):
    if ranker is None:
        return None
    with torch.inference_mode():
        source_vector = ranker.encode_sequences(source_chain, [query])
        target_vectors = ranker.encode_sequences(target_chain, candidates)
        return ranker.score_queries(source_chain, source_vector,
                                    target_vectors)[0].float().cpu().tolist()


def summarize(rows, score_name):
    keys = ("hit_at_1", "hit_at_5", "hit_at_10", "mrr")
    return {key: sum(row[score_name][key] for row in rows) / max(len(rows), 1)
            for key in keys}


def evaluate_direction(model, ranker, pairs, direction, args, device):
    query_targets = defaultdict(set)
    for gamma, delta in pairs:
        if direction == "gamma_to_delta":
            query_targets[gamma].add(delta)
        else:
            query_targets[delta].add(gamma)
    source_chain = "gamma" if direction == "gamma_to_delta" else "delta"
    target_chain = "delta" if source_chain == "gamma" else "gamma"
    all_targets = sorted({target for values in query_targets.values() for target in values})
    pools = candidate_lists(query_targets, all_targets, args.negatives, args.seed + len(direction))
    output = {}
    for pool_name, queries in pools.items():
        rows = []
        for query in sorted(queries):
            candidates = queries[query]
            positives = sorted(query_targets[query])
            generator = conditional_scores(model, source_chain, query, target_chain,
                                            candidates, device, args.batch_size)
            ranker_values = ranker_scores(ranker, source_chain, query, target_chain,
                                          candidates)
            row = {
                "source_chain": source_chain, "source": query,
                "positives": positives, "candidates": candidates,
                "generator": rank_summary(candidates, positives, generator, descending=False),
                "generator_scores": generator,
            }
            if ranker_values is not None:
                row["ranker"] = rank_summary(candidates, positives, ranker_values,
                                              descending=True)
                row["ranker_scores"] = ranker_values
            rows.append(row)
        entry = {
            "n_queries": len(rows),
            "n_candidates_mean": sum(len(row["candidates"]) for row in rows) / max(len(rows), 1),
            "n_negatives_requested": args.negatives,
            "generator": summarize(rows, "generator"),
            "rows": rows,
        }
        if ranker is not None:
            entry["ranker"] = summarize(rows, "ranker")
        output[pool_name] = entry
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generator", type=Path, required=True)
    parser.add_argument("--ranker", type=Path)
    parser.add_argument("--pairs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--seed", type=int, default=3407)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--negatives", type=int, default=100)
    args = parser.parse_args()
    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but no GPU is visible; submit through Slurm")
    if args.batch_size < 1 or args.negatives < 1:
        raise ValueError("batch-size and negatives must be positive")
    device = torch.device(args.device)
    model, checkpoint = load_checkpoint(args.generator, device)
    ranker = load_ranker(args.ranker, device) if args.ranker else None
    pairs = read_pairs(args.pairs)
    result = {
        "arguments": {key: str(value) if isinstance(value, Path) else value
                      for key, value in vars(args).items()},
        "generator": str(args.generator),
        "ranker": str(args.ranker) if args.ranker else None,
        "pairs": str(args.pairs), "model_config": checkpoint["model_config"],
        "device": str(device),
        "negative_definition": "unrecorded target from the same test target pool; constructed evaluation negative",
        "directions": {},
    }
    for direction in ("gamma_to_delta", "delta_to_gamma"):
        result["directions"][direction] = evaluate_direction(
            model, ranker, pairs, direction, args, device)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    for direction, pools in result["directions"].items():
        print(direction)
        for pool, values in pools.items():
            print(pool, json.dumps({key: values[key] for key in ("generator", "ranker")
                                    if key in values}, sort_keys=True))


if __name__ == "__main__":
    main()
