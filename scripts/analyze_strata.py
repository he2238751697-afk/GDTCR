#!/usr/bin/env python3
"""Summarize saved free-generation metrics by query difficulty strata.

The strata are descriptive only.  A positive is a target recorded for the
query in the supplied test split; an unobserved target is never treated as a
biological negative by this analysis.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gdtcr.metrics import row_metrics, summarize_metric_rows


def source_length_bin(length: int) -> str:
    if length <= 12:
        return "short_<=12"
    if length <= 16:
        return "medium_13-16"
    return "long_>=17"


def positive_count_bin(count: int) -> str:
    if count <= 1:
        return "one"
    if count <= 3:
        return "two_to_three"
    return "four_or_more"


def summarize(rows: list[dict]) -> dict:
    return {"n_queries": len(rows),
            **summarize_metric_rows([row_metrics(row) for row in rows])}


def grouped(rows: list[dict], key_fn) -> OrderedDict[str, dict]:
    groups: OrderedDict[str, list[dict]] = OrderedDict()
    for row in rows:
        key = key_fn(row)
        groups.setdefault(key, []).append(row)
    return OrderedDict((key, summarize(group)) for key, group in groups.items())


def analyze(path: Path) -> dict:
    payload = json.loads(path.read_text())
    directions = OrderedDict()
    for direction, rows in payload["rows"].items():
        directions[direction] = {
            "overall": summarize(rows),
            "source_length": grouped(
                rows, lambda row: source_length_bin(len(row["source"]))
            ),
            "recorded_positive_count": grouped(
                rows, lambda row: positive_count_bin(len(row["positives"]))
            ),
        }
    return {"evaluation": str(path), "directions": directions}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reports = [analyze(path) for path in args.evaluation]
    result = {
        "arguments": {
            "evaluation": [str(path) for path in args.evaluation],
            "output": str(args.output),
        },
        "reports": reports,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    for report in reports:
        print(report["evaluation"])
        for direction, values in report["directions"].items():
            print(direction, json.dumps(values["overall"], sort_keys=True))


if __name__ == "__main__":
    main()
