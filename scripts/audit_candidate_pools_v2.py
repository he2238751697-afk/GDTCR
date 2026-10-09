#!/usr/bin/env python3
"""Verify frozen retrieval labels, known-pair exclusions and content hashes."""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gdtcr.data import read_pairs
from gdtcr.fileio import file_sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pools", type=Path, default=Path("artifacts/completion_v2/pools"))
    parser.add_argument("--splits", type=Path, default=Path("data/splits/completion_v2"))
    parser.add_argument("--known-pairs", type=Path, default=Path("data/processed/paired_chain.txt"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/completion_v2/pool_audit.json"))
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    manifest = json.loads((args.pools / "manifest.json").read_text())
    assert manifest["known_pairs_sha256"] == file_sha256(args.known_pairs)
    assert manifest["split_manifest_sha256"] == file_sha256(args.splits / "manifest.json")
    known_pairs = read_pairs(args.known_pairs)
    known = {}
    for direction, index in (("gamma_to_delta", 0), ("delta_to_gamma", 1)):
        groups = defaultdict(set)
        for pair in known_pairs:
            groups[pair[index]].add(pair[1 - index])
        known[direction] = groups
    checked, queries, pools, candidates = 0, 0, 0, 0
    for relative, record in manifest["files"].items():
        path = args.pools / relative
        assert file_sha256(path) == record["sha256"]
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            data = json.load(handle)
        pair_path = args.splits / data["protocol"] / (data["role"] + ".tsv")
        assert data["pair_sha256"] == file_sha256(pair_path)
        pairs = read_pairs(pair_path)
        for direction, index in (("gamma_to_delta", 0), ("delta_to_gamma", 1)):
            groups = defaultdict(set)
            for pair in pairs:
                groups[pair[index]].add(pair[1 - index])
            entry = data["directions"][direction]
            targets = set(entry["target_universe"])
            assert targets == {pair[1 - index] for pair in pairs}
            assert [row["source"] for row in entry["rows"]] == sorted(groups)
            assert record["n_queries"][direction] == len(groups)
            assert record["n_targets"][direction] == len(targets)
            for row in entry["rows"]:
                positives = groups[row["source"]]
                assert set(row["positives"]) == positives
                assert set(row["pools"]) == {"random", "length", "motif", "edit"}
                full = row["full_candidates"]
                assert full == sorted(targets - (known[direction][row["source"]] - positives))
                for pool_name, values in (("full", full), *row["pools"].items()):
                    assert values == sorted(set(values))
                    assert positives <= set(values)
                    assert set(values) <= set(full)
                    if pool_name != "full":
                        assert len(values) <= len(positives) + manifest["negatives"]
                    candidates += len(values)
                    pools += 1
                queries += 1
        checked += 1
    result = {"schema_version": 2, "files_checked": checked,
              "directional_queries_checked": queries, "query_pools_checked": pools,
              "candidate_memberships_checked": candidates,
              "pool_manifest_sha256": file_sha256(args.pools / "manifest.json"),
              "known_pairs_sha256": manifest["known_pairs_sha256"],
              "assertions": ["all frozen file hashes", "role-specific recorded positives",
                             "all positives in every pool", "other known partners excluded",
                             "at most 100 constructed distractors per small pool"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
