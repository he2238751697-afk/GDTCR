#!/usr/bin/env python3
"""Bootstrap and stratify saved query-level GDTCR evaluation results."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gdtcr.data import read_pairs
from gdtcr.metrics import (bootstrap_metric_rows as bootstrap, levenshtein,
                           row_metrics, summarize_metric_rows)


def distance_to_training(sequence, training_sequences):
    return min(levenshtein(sequence, candidate) for candidate in training_sequences)


def summarize(rows):
    return summarize_metric_rows([row_metrics(row) for row in rows])


def add_distance_strata(rows, training_sources):
    enriched = []
    for row in rows:
        distance = distance_to_training(row["source"], training_sources)
        if distance == 0:
            stratum = "0"
        elif distance == 1:
            stratum = "1"
        elif distance == 2:
            stratum = "2"
        else:
            stratum = ">=3"
        enriched.append({"row": row,
                         "nearest_training_edit_distance": distance,
                         "stratum": stratum})
    return enriched


def stratified_summary(enriched):
    grouped = defaultdict(list)
    for item in enriched:
        grouped[item["stratum"]].append(item["row"])
    result = {}
    order = {"0": 0, "1": 1, "2": 2, ">=3": 3}
    for stratum in sorted(grouped, key=order.get):
        rows = grouped[stratum]
        result[stratum] = {"n_queries": len(rows), "metrics": summarize(rows)}
    return result


def analyze(path, train_path, replicates, seed):
    payload = json.loads(path.read_text())
    train_pairs = read_pairs(train_path)
    directions = {}
    for direction, rows in payload["rows"].items():
        source_chain = "gamma" if direction == "gamma_to_delta" else "delta"
        training_sources = sorted({
            gamma if source_chain == "gamma" else delta for gamma, delta in train_pairs
        })
        enriched = add_distance_strata(rows, training_sources)
        metric_rows = [row_metrics(row) for row in rows]
        directions[direction] = {
            "n_queries": len(rows),
            "summary": summarize_metric_rows(metric_rows),
            "bootstrap_95": bootstrap(metric_rows, replicates, seed + len(direction)),
            "nearest_training_distance": {
                "min": min(item["nearest_training_edit_distance"] for item in enriched),
                "max": max(item["nearest_training_edit_distance"] for item in enriched),
                "mean": sum(item["nearest_training_edit_distance"] for item in enriched) / max(len(enriched), 1),
            },
            "distance_strata": stratified_summary(enriched),
        }
    return {
        "evaluation": str(path),
        "train": str(train_path),
        "bootstrap_replicates": replicates,
        "directions": directions,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation", type=Path, nargs="+", required=True)
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bootstrap-replicates", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=3407)
    args = parser.parse_args()
    if args.bootstrap_replicates < 100:
        raise ValueError("Use at least 100 bootstrap replicates")
    result = {
        "arguments": {key: [str(v) for v in value] if isinstance(value, list)
                      else str(value) if isinstance(value, Path) else value
                      for key, value in vars(args).items()},
        "reports": [analyze(path, args.train, args.bootstrap_replicates,
                             args.seed + index * 1009)
                    for index, path in enumerate(args.evaluation)],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    for report in result["reports"]:
        print(report["evaluation"])
        for direction, values in report["directions"].items():
            print(direction, json.dumps(values["summary"], sort_keys=True))


if __name__ == "__main__":
    main()
