#!/usr/bin/env python3
"""Bootstrap query-level metrics from fixed candidate-pool evaluations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gdtcr.metrics import bootstrap_metric_rows


def bootstrap(rows, metric, replicates, seed):
    result = bootstrap_metric_rows([{metric: float(row[metric])} for row in rows],
                                   replicates, seed)
    return result.get(metric, {"mean": 0.0, "lower": 0.0, "upper": 0.0})


def summarize(rows, replicates, seed):
    return {
        metric: bootstrap(rows, metric, replicates, seed + index * 101)
        for index, metric in enumerate(("hit_at_1", "hit_at_5", "hit_at_10", "mrr"))
    }


def analyze(path, replicates, seed):
    payload = json.loads(path.read_text())
    directions = {}
    for direction, pools in payload["directions"].items():
        directions[direction] = {}
        for pool, values in pools.items():
            rows = values["rows"]
            entry = {"n_queries": len(rows), "generator": summarize(
                [row["generator"] for row in rows], replicates, seed)}
            if "ranker" in rows[0]:
                entry["ranker"] = summarize(
                    [row["ranker"] for row in rows], replicates, seed + 17)
            directions[direction][pool] = entry
    return {"evaluation": str(path), "bootstrap_replicates": replicates,
            "directions": directions}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bootstrap-replicates", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=3407)
    args = parser.parse_args()
    if args.bootstrap_replicates < 100:
        raise ValueError("Use at least 100 bootstrap replicates")
    result = {"arguments": {key: [str(value) for value in value] if isinstance(value, list)
                             else str(value) if isinstance(value, Path) else value
                             for key, value in vars(args).items()},
              "reports": [analyze(path, args.bootstrap_replicates,
                                    args.seed + index * 1009)
                          for index, path in enumerate(args.evaluation)]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(str(args.output))


if __name__ == "__main__":
    main()
