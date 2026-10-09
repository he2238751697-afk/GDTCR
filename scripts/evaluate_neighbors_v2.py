#!/usr/bin/env python3
"""Exact normalized two-chain nearest-training-pair retrieval on frozen pools."""

from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from rapidfuzz import process
from rapidfuzz.distance import Levenshtein

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gdtcr.data import read_pairs
from gdtcr.fileio import file_sha256
from gdtcr.provenance import begin_run, finish_run
from evaluate_pools_v2 import summary_for_pool, summarize


DIRECTIONS = ("gamma_to_delta", "delta_to_gamma")
ROLES = ("validation_selection", "validation_tuning", "validation_calibration", "test")


def exact_pair_scores(pairs, sources, targets, direction, workers=4, target_chunk=128):
    """Return min over every edge; both normalized chain distances have weight 1/2."""
    source_index = 0 if direction == "gamma_to_delta" else 1
    reference_sources = sorted({pair[source_index] for pair in pairs})
    reference_targets = sorted({pair[1 - source_index] for pair in pairs})
    source_lookup = {value: i for i, value in enumerate(reference_sources)}
    target_lookup = {value: i for i, value in enumerate(reference_targets)}
    edge_sources = [source_lookup[pair[source_index]] for pair in pairs]
    edge_targets = [target_lookup[pair[1 - source_index]] for pair in pairs]
    source_distance = process.cdist(sources, reference_sources,
                                   scorer=Levenshtein.normalized_distance,
                                   dtype=np.float64, workers=workers)
    target_distance = process.cdist(targets, reference_targets,
                                   scorer=Levenshtein.normalized_distance,
                                   dtype=np.float64, workers=workers)
    scores = np.empty((len(sources), len(targets)), dtype=np.float64)
    witnesses = np.empty((len(sources), len(targets)), dtype=np.int32)
    for start in range(0, len(targets), target_chunk):
        target_to_edge = target_distance[start:start + target_chunk, edge_targets]
        for index in range(len(sources)):
            distance = target_to_edge + source_distance[index, edge_sources][None, :]
            best = distance.argmin(axis=1)
            witnesses[index, start:start + target_chunk] = best
            scores[index, start:start + target_chunk] = -0.5 * distance[np.arange(len(best)), best]
    return scores, witnesses


def evaluate_role(pool, pairs, directions, workers):
    output, summaries = {}, {}
    for direction in directions:
        entry = pool["directions"][direction]
        targets = entry["target_universe"]
        lookup = {value: index for index, value in enumerate(targets)}
        sources = [row["source"] for row in entry["rows"]]
        scores, witnesses = exact_pair_scores(pairs, sources, targets, direction, workers)
        counts = Counter(pair[1 if direction == "gamma_to_delta" else 0] for pair in pairs)
        frequency = [math.log1p(counts[target]) for target in targets]
        rows = []
        for index, row in enumerate(entry["rows"]):
            method_scores = {"edit_neighbor": scores[index].tolist(), "frequency": frequency}
            indices = {name: [lookup[target] for target in candidates]
                       for name, candidates in row["pools"].items()}
            indices["full"] = [lookup[target] for target in row["full_candidates"]]
            rows.append({"source": row["source"], "positives": row["positives"],
                         "scores": method_scores, "nearest_training_edge": witnesses[index].tolist(),
                         "pool_indices": indices,
                         "pool_metrics": {name: summary_for_pool(row["positives"], targets,
                                                                  chosen, method_scores)
                                          for name, chosen in indices.items()}})
        output[direction] = rows
        summaries[direction] = summarize(rows)
    return output, summaries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--pool-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--directions", choices=("both", *DIRECTIONS), default="both")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("workers must be positive")
    paths = {role: args.pool_root / (role + ".json.gz") for role in ROLES}
    begin_run(args.output, args, [args.train, *paths.values()])
    pairs = sorted(read_pairs(args.train))
    directions = DIRECTIONS if args.directions == "both" else (args.directions,)
    summary = {"schema_version": 2, "train_sha256": file_sha256(args.train),
               "pool_sha256": {role: file_sha256(path) for role, path in paths.items()},
               "score_definition": "-min_training_edges (normalized_edit_gamma + normalized_edit_delta)/2",
               "normalization": "each chain edit distance divided by longer chain length",
               "training_edge_order": "lexicographically sorted unique gamma/delta pairs",
               "training_edges": len(pairs), "roles": {}}
    for role, path in paths.items():
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            pool = json.load(handle)
        rows, result = evaluate_role(pool, pairs, directions, args.workers)
        with gzip.open(args.output / (role + ".json.gz"), "wt", encoding="utf-8",
                       compresslevel=6) as handle:
            json.dump(rows, handle, sort_keys=True, separators=(",", ":"))
        summary["roles"][role] = result
        print(json.dumps({"role": role, "output": str(args.output)}), flush=True)
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    finish_run(args.output)


if __name__ == "__main__":
    main()
