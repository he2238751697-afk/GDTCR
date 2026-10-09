#!/usr/bin/env python3
"""Apply frozen fusion/rejection to test scores; preserve raw samples separately."""

import argparse
import copy
import gzip
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gdtcr.calibration import (acceptance_curves, calibrated_scores, rejection_metrics,
                              sorted_indices)
from gdtcr.data import read_pairs
from gdtcr.evaluation import ranked_generation_metrics
from gdtcr.fileio import file_sha256
from gdtcr.provenance import begin_run, finish_run
from calibrate_scores_v2 import free_views, load_gzip, load_views
from evaluate_free_v2 import summarize_rows
from evaluate_pools_v2 import summary_for_pool, summarize


def classification_diagnostics(views, direction, profile, alpha, known_pairs):
    result = {}
    for group in views[0]["groups"] if views else ():
        labels, by_method = [], {}
        for row in views:
            scores = calibrated_scores(row, profile, alpha)
            positives = set(row["positives"])
            for index in row["groups"][group]:
                target = row["candidates"][index]
                pair = (row["source"], target) if direction == "gamma_to_delta" else (target, row["source"])
                if target not in positives and pair in known_pairs:
                    continue
                labels.append(int(target in positives))
                for method, values in scores.items():
                    by_method.setdefault(method, []).append(float(values[index]))
        positives, total = sum(labels), len(labels)
        result[group] = {"candidate_pairs": total, "recorded_positives": positives,
                         "recorded_positive_prevalence": positives / total if total else None,
                         "methods": {method: {
                             "pooled_auroc": float(roc_auc_score(labels, values)) if 0 < positives < total else None,
                             "pooled_auprc": float(average_precision_score(labels, values)) if positives else None}
                                     for method, values in by_method.items()},
                         "label_scope": "recorded positives versus constructed unrecorded combinations"}
    return result


def free_result(raw, settings, train, known):
    output, summaries = {}, {}
    fusion = settings["fusion"]
    for direction, original in raw.items():
        profile = fusion["score_profiles"][direction]
        thresholds = settings["calibration"][direction]["methods"]
        rows = [{key: copy.deepcopy(value) for key, value in row.items()
                 if key not in ("samples", "candidate_sequences", "candidate_nll", "candidate_ranker_score",
                                "candidate_nearest_supervised")} for row in original]
        train_targets = {pair[1 if direction == "gamma_to_delta" else 0] for pair in train}
        for key in original[0]["prefixes"] if original else ():
            budget, policy = key.split("/")
            views = free_views(original, int(budget), train_targets if policy == "exclude_training_targets" else None)
            for result, view in zip(rows, views):
                scores = calibrated_scores(view, profile, fusion["alpha"])
                if "fused" in scores:
                    ordered = [view["candidates"][index] for index in sorted_indices(view, scores["fused"], view["groups"]["free"])]
                    result["prefixes"][key]["methods"]["fused"] = ranked_generation_metrics(view["positives"], ordered)
                result["prefixes"][key]["calibrated"] = {
                    method: rejection_metrics(view, values, view["groups"]["free"], thresholds[method])
                    for method, values in scores.items()}
        primary_views = free_views(original, 64)
        summary = summarize_rows(rows)
        summary["acceptance_curves"] = acceptance_curves(primary_views, direction, settings, known)
        summary["classification"] = classification_diagnostics(primary_views, direction, profile, fusion["alpha"], known)
        summary["calibrated"] = {key: {method: {
            "accepted_query_fraction": float(np.mean([row["prefixes"][key]["calibrated"][method]["accepted_query"] for row in rows])),
            "hit_at_5": float(np.mean([row["prefixes"][key]["calibrated"][method]["hit_at_5"] for row in rows])),
            "recall_at_5": float(np.mean([row["prefixes"][key]["calibrated"][method]["recall_at_5"] for row in rows]))}
            for method in thresholds} for key in original[0]["prefixes"]} if original else {}
        output[direction], summaries[direction] = rows, summary
    return output, summaries


def pool_result(raw, views_by_direction, settings, known):
    output, summaries = {}, {}
    fusion = settings["fusion"]
    for direction, original in raw.items():
        views = views_by_direction[direction]
        profile = fusion["score_profiles"][direction]
        thresholds = settings["calibration"][direction]["methods"]
        rows = []
        for old, view in zip(original, views):
            row = {key: copy.deepcopy(value) for key, value in old.items() if key != "scores"}
            scores = calibrated_scores(view, profile, fusion["alpha"])
            if "fused" in scores:
                for group, indices in view["groups"].items():
                    row["pool_metrics"][group].update(summary_for_pool(
                        row["positives"], view["candidates"], indices, {"fused": scores["fused"]}))
            row["calibrated"] = {group: {
                method: rejection_metrics(view, values, indices, thresholds[method]) for method, values in scores.items()}
                for group, indices in view["groups"].items()}
            rows.append(row)
        summary = summarize(rows)
        summary["acceptance_curves"] = acceptance_curves(views, direction, settings, known)
        summary["classification"] = classification_diagnostics(views, direction, profile, fusion["alpha"], known)
        output[direction], summaries[direction] = rows, summary
    return output, summaries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("free", "pools"), required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--settings", type=Path, required=True)
    parser.add_argument("--pool", type=Path)
    parser.add_argument("--train", type=Path)
    parser.add_argument("--known-pairs", type=Path, default=Path("data/processed/paired_chain.txt"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw_summary = json.loads((args.input / "summary.json").read_text())
    if not raw_summary.get("calibration_settings") or raw_summary["calibration_settings"]["sha256"] != file_sha256(args.settings):
        raise ValueError("Test was not scored after these exact calibration settings were frozen")
    inputs = [args.settings, args.pool, args.train, args.known_pairs,
              *[args.input / name for name in ("rows.json.gz", "summary.json", "checksums.json", "provenance.json")]]
    begin_run(args.output, args, inputs)
    settings = json.loads(args.settings.read_text())
    raw, known = load_gzip(args.input / "rows.json.gz"), set(read_pairs(args.known_pairs))
    if settings["mode"] != args.mode:
        raise ValueError("Frozen settings have the wrong evaluation mode")
    if args.mode == "free":
        rows, directions = free_result(raw, settings, read_pairs(args.train), known)
    else:
        rows, directions = pool_result(raw, load_views(args.input, args.mode, args.pool), settings, known)
    with gzip.open(args.output / "rows.json.gz", "wt", encoding="utf-8", compresslevel=6) as handle:
        json.dump(rows, handle, sort_keys=True, separators=(",", ":"))
    summary = {"schema_version": 2, "mode": args.mode, "directions": directions,
               "raw_evaluation": str(args.input), "settings_sha256": file_sha256(args.settings),
               "ranker_weight": settings["fusion"]["alpha"], "test_used_for_selection": False}
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    finish_run(args.output)
    print(json.dumps({"output": str(args.output), "mode": args.mode}), flush=True)


if __name__ == "__main__":
    main()
