#!/usr/bin/env python3
"""Freeze labelled retrieval pools shared by every completion-v2 scorer."""

from __future__ import annotations

import argparse
import gzip
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

from rapidfuzz.distance import Levenshtein

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gdtcr.data import read_pairs
from gdtcr.fileio import file_sha256


def candidate_pools(positives, eligible, n_negatives, seed):
    positives = sorted(positives)
    eligible = sorted(eligible)
    rng = random.Random(seed)
    n = min(n_negatives, len(eligible))
    random_negatives = rng.sample(eligible, n)
    lengths = [len(value) for value in positives]
    end_motifs = {(value[:3], value[-3:]) for value in positives}
    scored = []
    for value in eligible:
        length_gap = min(abs(len(value) - length) for length in lengths)
        motif_gap = min(Levenshtein.distance(value[:3], first) +
                        Levenshtein.distance(value[-3:], last)
                        for first, last in end_motifs)
        edit_gap = min(Levenshtein.distance(value, positive) / max(len(value), len(positive))
                       for positive in positives)
        scored.append((value, length_gap, motif_gap, edit_gap))
    choices = {
        "random": random_negatives,
        "length": [item[0] for item in sorted(scored, key=lambda item: (item[1], item[3], item[0]))[:n]],
        "motif": [item[0] for item in sorted(scored, key=lambda item: (item[2], item[3], item[0]))[:n]],
        "edit": [item[0] for item in sorted(scored, key=lambda item: (item[3], item[0]))[:n]],
    }
    return {name: sorted(set(positives) | set(negatives)) for name, negatives in choices.items()}


def build_role(pairs, all_known, n_negatives, seed):
    result = {}
    for direction, source_index in (("gamma_to_delta", 0), ("delta_to_gamma", 1)):
        query_targets = defaultdict(set)
        for pair in pairs:
            query_targets[pair[source_index]].add(pair[1 - source_index])
        target_universe = sorted({pair[1 - source_index] for pair in pairs})
        known = defaultdict(set)
        for pair in all_known:
            known[pair[source_index]].add(pair[1 - source_index])
        rows = []
        for index, source in enumerate(sorted(query_targets)):
            positives = sorted(query_targets[source])
            eligible = set(target_universe) - known[source]
            pools = candidate_pools(positives, eligible, n_negatives,
                                    seed + index * 1009 + source_index)
            rows.append({"source": source, "positives": positives, "pools": pools,
                         "full_candidates": sorted(set(target_universe) - (known[source] - set(positives)))})
        result[direction] = {"source_chain": "gamma" if source_index == 0 else "delta",
                             "target_chain": "delta" if source_index == 0 else "gamma",
                             "target_universe": target_universe, "rows": rows}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split-manifest", type=Path, default=Path("data/splits/completion_v2/manifest.json"))
    parser.add_argument("--known-pairs", type=Path, default=Path("data/processed/paired_chain.txt"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/completion_v2/pools"))
    parser.add_argument("--negatives", type=int, default=100)
    parser.add_argument("--seed", type=int, default=3407)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"Frozen evaluation pools already exist: {args.output}")
    if args.negatives < 1:
        raise ValueError("negatives must be positive")
    split_manifest = json.loads(args.split_manifest.read_text())
    all_known = read_pairs(args.known_pairs)
    args.output.mkdir(parents=True)
    manifest = {"schema_version": 2, "seed": args.seed, "negatives": args.negatives,
                "split_manifest_sha256": file_sha256(args.split_manifest),
                "known_pairs_sha256": file_sha256(args.known_pairs), "files": {}}
    for protocol in sorted(split_manifest["protocols"]):
        for role in ("validation_selection", "validation_tuning", "validation_calibration", "test"):
            path = args.split_manifest.parent / protocol / (role + ".tsv")
            pairs = read_pairs(path)
            result = {"schema_version": 2, "protocol": protocol, "role": role,
                      "pair_sha256": file_sha256(path), "known_pairs_sha256": manifest["known_pairs_sha256"],
                      "negative_definition": "unrecorded target from this role's target universe",
                      "directions": build_role(pairs, all_known, args.negatives, args.seed)}
            output = args.output / protocol / (role + ".json.gz")
            output.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(output, "wt", encoding="utf-8", compresslevel=6) as handle:
                json.dump(result, handle, sort_keys=True, separators=(",", ":"))
            manifest["files"][str(output.relative_to(args.output))] = {
                "sha256": file_sha256(output),
                "n_queries": {d: len(entry["rows"]) for d, entry in result["directions"].items()},
                "n_targets": {d: len(entry["target_universe"]) for d, entry in result["directions"].items()},
            }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(args.output), "files": len(manifest["files"])}, sort_keys=True))


if __name__ == "__main__":
    main()
