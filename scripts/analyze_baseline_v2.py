#!/usr/bin/env python3
"""Cluster intervals for the exact-neighbor/frequency and shallow frozen-pool controls."""

import argparse
import gzip
import json
from pathlib import Path

from analyze_run_v2 import clusters_for, statistics
from calibrate_scores_v2 import load_gzip
from gdtcr.data import read_pairs
from gdtcr.fileio import file_sha256
from gdtcr.provenance import begin_run, finish_run
from gdtcr.statistics import bidirectional_intervals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("exact_neighbor", "shallow"), required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--pairs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bootstrap-replicates", type=int, default=2000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260930)
    args = parser.parse_args()
    inputs = [args.pairs, *[args.input / name for name in
                           ("test.json.gz", "summary.json", "checksums.json", "provenance.json")]]
    source_summary = json.loads((args.input / "summary.json").read_text())
    checksums = json.loads((args.input / "checksums.json").read_text())
    for name in ("test.json.gz", "summary.json", "provenance.json"):
        if file_sha256(args.input / name) != checksums[name]:
            raise ValueError(f"Changed baseline artifact: {args.input / name}")
    begin_run(args.output, args, inputs)
    pairs = read_pairs(args.pairs)
    data = load_gzip(args.input / "test.json.gz")
    directions, compact, joint_rows, joint_clusters = {}, {}, {}, {}
    for direction, entry in data.items():
        rows = entry["rows"] if args.kind == "shallow" else entry
        if args.kind == "shallow":
            rows = [{**row, "pool_metrics": {pool: {"shallow": metrics}
                                             for pool, metrics in row["pool_metrics"].items()}}
                    for row in rows]
        directional = args.protocol.startswith(("seen_input_", "unseen_input_"))
        lookup = clusters_for(pairs, direction, directional)
        if set(lookup) != {row["source"] for row in rows} or len(rows) != len(lookup):
            raise ValueError("Baseline queries differ from the frozen test split")
        result, metrics = statistics(rows, lookup, args, "pools")
        result["bootstrap_unit"] = "source_query" if directional else "connected_component_of_frozen_test_graph"
        directions[direction] = result
        joint_rows[direction] = metrics
        joint_clusters[direction] = [lookup[row["source"]] for row in rows]
        compact[direction] = [{"source": row["source"], "positives": row["positives"],
                               "cluster": lookup[row["source"]], "metrics": values}
                              for row, values in zip(rows, metrics)]
    with gzip.open(args.output / "query_metrics.json.gz", "wt", encoding="utf-8", compresslevel=6) as handle:
        json.dump(compact, handle, sort_keys=True, separators=(",", ":"))
    result = {"schema_version": 2, "mode": "pools", "baseline": args.kind,
              "protocol": args.protocol, "directions": directions,
              "pool_sha256": source_summary["pool_sha256"],
              "test_pool_sha256": source_summary["pool_sha256"]["test"],
              "equal_direction_macro": bidirectional_intervals(joint_rows, joint_clusters,
                                                                replicates=args.bootstrap_replicates,
                                                                seed=args.bootstrap_seed),
              "query_metrics_sha256": file_sha256(args.output / "query_metrics.json.gz"),
              "input_sha256": {str(path): file_sha256(path) for path in inputs},
              "zero_event_note": "Percentile [0,0] is not a population upper bound; iid Wilson reference is separate"}
    (args.output / "summary.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    finish_run(args.output)
    print(json.dumps({"output": str(args.output), "baseline": args.kind}), flush=True)


if __name__ == "__main__":
    main()
