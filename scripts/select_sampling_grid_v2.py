#!/usr/bin/env python3
"""Summarize the prespecified tuning-only sampling grid without replacing primary settings."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gdtcr.fileio import file_sha256
from gdtcr.provenance import begin_run, finish_run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluations", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inputs = [folder / name for folder in args.evaluations for name in
              ("summary.json", "provenance.json", "checksums.json")]
    begin_run(args.output, args, inputs)
    grid = []
    required = {(temperature, top_p) for temperature in (.7, 1., 1.2) for top_p in (.9, .95)}
    for folder in args.evaluations:
        summary = json.loads((folder / "summary.json").read_text())
        arguments = json.loads((folder / "provenance.json").read_text())["arguments"]
        metrics = {direction: values["prefixes"]["64/allow_training_targets"]["methods"]["likelihood"]["hit_at_5"]
                   for direction, values in summary["directions"].items()}
        grid.append({"temperature": arguments["temperature"], "top_p": arguments["top_p"],
                     "evaluation": str(folder), "query_macro_hit_at_5": metrics,
                     "mean_hit_at_5": sum(metrics.values()) / len(metrics)})
    if {(item["temperature"], item["top_p"]) for item in grid} != required or len(grid) != 6:
        raise ValueError("Sampling grid is incomplete or contains duplicate cells")
    chosen = max(grid, key=lambda item: (item["mean_hit_at_5"],
                                        item["temperature"] == 1. and item["top_p"] == .95,
                                        -item["temperature"], -item["top_p"]))
    result = {"grid": grid, "tuning_best": chosen,
              "primary_test_setting": {"temperature": 1., "top_p": .95},
              "primary_replaced": False, "selection_data": "validation_tuning only",
              "tie_rule": "primary setting first; then smaller temperature, then smaller top-p",
              "input_sha256": {str(path): file_sha256(path) for path in inputs}}
    (args.output / "summary.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    finish_run(args.output)


if __name__ == "__main__":
    main()
