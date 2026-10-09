#!/usr/bin/env python3
"""Paired cluster-bootstrap differences between immutable saved query outcomes."""

import argparse
import json
from pathlib import Path

from calibrate_scores_v2 import load_gzip
from gdtcr.fileio import file_sha256
from gdtcr.provenance import begin_run, finish_run
from gdtcr.statistics import bidirectional_intervals, cluster_intervals


def load_analysis(folder):
    summary = json.loads((folder / "summary.json").read_text())
    if file_sha256(folder / "query_metrics.json.gz") != summary["query_metrics_sha256"]:
        raise ValueError(f"Changed query outcomes: {folder}")
    return summary, load_gzip(folder / "query_metrics.json.gz")


def metric_mapping(left_keys, right_keys, left_method=None, right_method=None):
    if (left_method is None) != (right_method is None):
        raise ValueError("Specify both methods, or neither")
    if left_method is None:
        return {key: (key, key) for key in sorted(left_keys & right_keys)}
    mapping = {}
    for key in sorted(left_keys):
        fields = key.split("|")
        if len(fields) != 3 or fields[1] != left_method:
            continue
        other = "|".join((fields[0], right_method, fields[2]))
        if other in right_keys:
            mapping[fields[0] + "|" + fields[2]] = (key, other)
    return mapping


def paired_difference(left, right, *, left_method=None, right_method=None,
                      directions=None, replicates=2000, seed=20260930):
    selected = sorted(set(left) & set(right)) if directions is None else directions
    if not selected:
        raise ValueError("No shared directions")
    results, joint_rows, joint_clusters = {}, {}, {}
    for direction in selected:
        a = {row["source"]: row for row in left[direction]}
        b = {row["source"]: row for row in right[direction]}
        if set(a) != set(b) or len(a) != len(left[direction]) or len(b) != len(right[direction]):
            raise ValueError("Paired differences require identical unique test queries")
        sources = sorted(a)
        if any(set(a[s]["positives"]) != set(b[s]["positives"]) or
               a[s]["cluster"] != b[s]["cluster"] for s in sources):
            raise ValueError("Paired differences require identical positives and clusters")
        mapping = metric_mapping(set(a[sources[0]]["metrics"]), set(b[sources[0]]["metrics"]),
                                 left_method, right_method)
        if not mapping:
            raise ValueError("No comparable metrics")
        rows = [{key: a[source]["metrics"][lk] - b[source]["metrics"][rk]
                 for key, (lk, rk) in mapping.items()} for source in sources]
        clusters = [a[source]["cluster"] for source in sources]
        kwargs = {"replicates": replicates, "seed": seed}
        results[direction] = {
            "metric_mapping": {key: {"left": lk, "right": rk} for key, (lk, rk) in mapping.items()},
            "query_macro": cluster_intervals(rows, clusters, **kwargs),
            "edge_weighted_query_metrics": cluster_intervals(
                rows, clusters, weights=[len(a[s]["positives"]) for s in sources], **kwargs)}
        joint_rows[direction], joint_clusters[direction] = rows, clusters
    return {"definition": "left minus right on identical test queries and shared cluster resamples",
            "directions": results,
            "equal_direction_macro": bidirectional_intervals(joint_rows, joint_clusters,
                                                              replicates=replicates, seed=seed),
            "interpretation": "negative NLL/rank differences favor left; positive recovery differences favor left",
            "multiplicity": "descriptive intervals, not family-wise adjusted hypothesis tests"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left", type=Path, required=True)
    parser.add_argument("--right", type=Path, required=True)
    parser.add_argument("--left-method")
    parser.add_argument("--right-method")
    parser.add_argument("--direction", choices=("gamma_to_delta", "delta_to_gamma"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bootstrap-replicates", type=int, default=2000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260930)
    args = parser.parse_args()
    left_summary, left = load_analysis(args.left)
    right_summary, right = load_analysis(args.right)
    if left_summary["protocol"] != right_summary["protocol"] or left_summary["mode"] != right_summary["mode"]:
        raise ValueError("Pairing requires the same protocol and outcome mode")
    if left_summary["mode"] == "pools" and left_summary["test_pool_sha256"] != right_summary["test_pool_sha256"]:
        raise ValueError("Paired retrieval requires identical frozen candidate pools")
    inputs = [folder / name for folder in (args.left, args.right)
              for name in ("summary.json", "query_metrics.json.gz", "checksums.json", "provenance.json")]
    begin_run(args.output, args, inputs)
    result = paired_difference(left, right, left_method=args.left_method, right_method=args.right_method,
                               directions=[args.direction] if args.direction else None,
                               replicates=args.bootstrap_replicates, seed=args.bootstrap_seed)
    result.update(schema_version=2, mode=left_summary["mode"], protocol=left_summary["protocol"],
                  left=str(args.left), right=str(args.right),
                  input_sha256={str(path): file_sha256(path) for path in inputs})
    (args.output / "summary.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    finish_run(args.output)
    print(json.dumps({"output": str(args.output)}), flush=True)


if __name__ == "__main__":
    main()
