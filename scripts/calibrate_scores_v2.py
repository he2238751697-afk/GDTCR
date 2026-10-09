#!/usr/bin/env python3
"""Fit score fusion on tuning rows, then thresholds on separate calibration rows."""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gdtcr.calibration import fit_calibration
from gdtcr.data import read_pairs
from gdtcr.fileio import file_sha256
from gdtcr.provenance import begin_run, finish_run


def load_gzip(path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def free_views(rows, budget=64, excluded_targets=None):
    views = []
    for row in rows:
        if len(row["samples"]) < budget:
            raise ValueError("Saved draws do not reach the frozen calibration budget")
        candidates = list(dict.fromkeys(sample["sequence"] for sample in row["samples"][:budget]
                                       if sample["valid"] and
                                       (excluded_targets is None or sample["sequence"] not in excluded_targets)))
        lookup = {value: index for index, value in enumerate(row["candidate_sequences"])}
        selected = [lookup[value] for value in candidates]
        ranker = row["candidate_ranker_score"]
        views.append({"source": row["source"], "positives": row["positives"], "candidates": candidates,
                      "scores": {"likelihood": [-row["candidate_nll"][index] for index in selected],
                                 "ranker": [ranker[index] for index in selected] if ranker is not None else None},
                      "groups": {"free": list(range(len(candidates)))},
                      "reference_group": "free", "selection_groups": ["free"]})
    return views


def pool_views(rows, universe):
    return [{"source": row["source"], "positives": row["positives"], "candidates": universe,
             "scores": {key: row["scores"][key] for key in ("likelihood", "ranker")},
             "groups": row["pool_indices"], "reference_group": "full",
             "selection_groups": ["random", "length", "motif", "edit"]} for row in rows]


def load_views(folder, mode, pool_path=None, budget=64):
    rows = load_gzip(folder / "rows.json.gz")
    if mode == "free":
        return {direction: free_views(values, budget) for direction, values in rows.items()}
    if pool_path is None:
        raise ValueError("Pool views require the frozen target-universe file")
    pool = load_gzip(pool_path)
    summary = json.loads((folder / "summary.json").read_text())
    if summary["pool_sha256"] != file_sha256(pool_path):
        raise ValueError("Scored pool and target universe differ")
    return {direction: pool_views(values, pool["directions"][direction]["target_universe"])
            for direction, values in rows.items()}


def model_lineage(folder):
    provenance = json.loads((folder / "provenance.json").read_text())
    arguments = provenance["arguments"]
    keys = ("generator", "generator_gamma_to_delta", "generator_delta_to_gamma", "ranker",
            "prior", "prior_gamma_to_delta", "prior_delta_to_gamma")
    return {key: {"path": value, "sha256": provenance["input_sha256"][str(Path(value).resolve())]}
            for key in keys if (value := arguments.get(key))}


def verify_settings(path, mode, arguments):
    if path is None:
        return None
    settings = json.loads(path.read_text())
    if settings["mode"] != mode:
        raise ValueError("Calibration settings belong to another evaluation mode")
    for key, item in settings["model_inputs"].items():
        value = getattr(arguments, key, None)
        if value is None or file_sha256(value) != item["sha256"]:
            raise ValueError(f"Frozen calibration checkpoint changed: {key}")
    if mode == "free":
        tuning = settings["sampling"]
        for key in ("temperature", "top_p", "source_mode", "ranker_source_mode"):
            if getattr(arguments, key) != tuning[key]:
                raise ValueError(f"Calibration and test sampling settings differ: {key}")
    return {"path": str(path), "sha256": file_sha256(path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("free", "pools"), required=True)
    parser.add_argument("--tuning", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--tuning-pool", type=Path)
    parser.add_argument("--calibration-pool", type=Path)
    parser.add_argument("--known-pairs", type=Path, default=Path("data/processed/paired_chain.txt"))
    parser.add_argument("--budget", type=int, default=64)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inputs = [args.known_pairs, args.tuning_pool, args.calibration_pool,
              *[folder / name for folder in (args.tuning, args.calibration)
                for name in ("rows.json.gz", "summary.json", "provenance.json", "checksums.json")]]
    begin_run(args.output, args, inputs)
    tuning_lineage, calibration_lineage = model_lineage(args.tuning), model_lineage(args.calibration)
    if tuning_lineage != calibration_lineage:
        raise ValueError("Tuning and calibration use different frozen checkpoints")
    tuning = load_views(args.tuning, args.mode, args.tuning_pool, args.budget)
    calibration = load_views(args.calibration, args.mode, args.calibration_pool, args.budget)
    result = fit_calibration(tuning, calibration, set(read_pairs(args.known_pairs)))
    result.update(mode=args.mode, primary_budget=args.budget,
                  model_inputs=tuning_lineage,
                  primary_policy="allow_training_targets", input_sha256={str(p): file_sha256(p) for p in inputs if p})
    if args.mode == "free":
        arguments = [json.loads((folder / "provenance.json").read_text())["arguments"]
                     for folder in (args.tuning, args.calibration)]
        keys = ("temperature", "top_p", "source_mode", "ranker_source_mode")
        if any(arguments[0][key] != arguments[1][key] for key in keys):
            raise ValueError("Tuning and calibration sampling differs")
        result["sampling"] = {key: arguments[0][key] for key in keys}
    (args.output / "settings.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    (args.output / "summary.json").write_text(json.dumps({
        "mode": args.mode, "alpha": result["fusion"]["alpha"],
        "directions": {direction: {"thresholds": item["methods"],
                                    "excluded_other_known_partners": item["excluded_other_known_partners"]}
                       for direction, item in result["calibration"].items()}}, indent=2, sort_keys=True) + "\n")
    finish_run(args.output)
    print(json.dumps({"output": str(args.output), "alpha": result["fusion"]["alpha"],
                      "calibrated_directions": sorted(calibration)}), flush=True)


if __name__ == "__main__":
    main()
