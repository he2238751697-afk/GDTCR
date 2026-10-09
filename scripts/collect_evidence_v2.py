#!/usr/bin/env python3
"""Validate the completion-v2 task graph and export manuscript-ready evidence tables."""

import argparse
import csv
import datetime
import gzip
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gdtcr.fileio import file_sha256
from gdtcr.provenance import begin_run, finish_run


BASE = Path("artifacts/completion_v2")
CONFIG = Path("configs/completion_v2")
MANIFESTS = ("pretrain_jobs.json", "generator_jobs.json", "generator_source_correction_jobs.json",
             "ranker_corrected_jobs.json", "distance_jobs.json", "neighbor_jobs.json", "shallow_jobs.json",
             "evaluation_jobs.json", "distance_audit_corrected_jobs.json", "analysis_jobs.json",
             "supplemental_audit_jobs.json", "evaluation_audit_jobs.json",
             "evaluation_audit_corrected_jobs.json", "training_audit_jobs.json")


def read(path):
    return json.loads(Path(path).read_text())


def verify_tasks(manifests, verify_large):
    replacements = {(entry["old_manifest_sha256"], entry["old_index"])
                    for name in ("task_supersessions.json", "evaluation_audit_supersessions.json")
                    for entry in read(CONFIG / name)["replacements"]}
    rows, missing, checked, records = [], [], {}, {}
    for path, manifest in manifests:
        digest = file_sha256(path)
        for index, task in enumerate(manifest["tasks"]):
            if (digest, index) in replacements:
                continue
            record_path = Path(manifest["job_records"]) / (task["id"] + ".json")
            row = {"manifest": str(path), "task_id": task["id"], "phase": manifest["phase"], "status": "not_started",
                   "requirements": task.get("requirements", [])}
            if record_path.exists():
                record = read(record_path)
                row.update(status=record["status"], slurm_job_id=record.get("slurm_job_id"),
                           elapsed_seconds=record.get("elapsed_seconds"), record=str(record_path))
                if record["manifest_sha256"] != digest or record["task"] != task:
                    raise ValueError(f"Task provenance differs from manifest: {record_path}")
                if record["status"] == "complete":
                    if set(record["output_sha256"]) != set(task["outputs"]):
                        raise ValueError(f"Incomplete output inventory: {record_path}")
                    for output, expected in record["output_sha256"].items():
                        file = Path(output)
                        if not file.is_file():
                            raise FileNotFoundError(file)
                        if verify_large or file.suffix != ".pt":
                            if output not in checked:
                                checked[output] = file_sha256(file)
                            actual = checked[output]
                            if actual != expected:
                                raise ValueError(f"Changed completed output: {file}")
                    records[task["id"]] = record
            if row["status"] != "complete":
                missing.append(row)
            rows.append(row)
    return rows, missing, checked, records


def metric_rows(report, summary):
    common = {key: report.get(key) for key in
              ("evaluation_name", "baseline", "comparison_name", "model_seed_index", "mode", "protocol_name")}
    for direction, entry in summary["directions"].items():
        for weighting in ("query_macro", "edge_weighted_query_metrics", "token_weighted_nll"):
            if weighting not in entry:
                continue
            group = entry[weighting]
            for metric, values in group["metrics"].items():
                yield {**common, "direction": direction, "weighting": weighting,
                       "stratum": "all", "metric": metric,
                       "n_queries": group["n_queries"], "n_clusters": group["n_clusters"],
                       **{key: values.get(key) for key in ("estimate", "lower", "upper", "events", "denominator")}}
        if "strata" in entry:
            for stratum, stratified in entry["strata"]["groups"].items():
                for weighting in ("query_macro", "edge_weighted_query_metrics", "token_weighted_nll"):
                    if weighting not in stratified:
                        continue
                    group = stratified[weighting]
                    if not group["metrics"]:
                        yield {**common, "direction": direction, "weighting": weighting, "stratum": stratum,
                               "metric": "EMPTY", "n_queries": 0, "n_clusters": 0}
                    for metric, values in group["metrics"].items():
                        yield {**common, "direction": direction, "weighting": weighting, "stratum": stratum,
                               "metric": metric, "n_queries": group["n_queries"], "n_clusters": group["n_clusters"],
                               **{key: values.get(key) for key in ("estimate", "lower", "upper", "events", "denominator")}}
    for metric, values in summary["equal_direction_macro"]["metrics"].items():
        yield {**common, "direction": "equal_direction_macro", "weighting": "query_macro",
               "stratum": "all", "metric": metric, "n_queries": sum(summary["equal_direction_macro"]["n_queries"].values()),
               "n_clusters": summary["equal_direction_macro"]["n_clusters"], **values}


def split_descriptives(reports):
    output = {}
    for model in ("paired", "constant", "random", "shuffled"):
        entries = [r for r in reports if r.get("evaluation_name") in
                   {f"split_seed{s}/{model}" for s in (17, 3407, 2026)}]
        by_mode = {}
        for mode in ("free", "pools"):
            selected = [r for r in entries if r["mode"] == mode]
            if len(selected) != 6:
                continue
            # Average seeds within each split, then compute descriptive SD over
            # the three split means. Never pool them as independent subjects.
            by_direction = {}
            for direction in ("gamma_to_delta", "delta_to_gamma", "equal_direction_macro"):
                groups = {}
                for r in selected:
                    summary = r["summary"]
                    stats = summary["equal_direction_macro"] if direction == "equal_direction_macro" else summary["directions"][direction]["query_macro"]
                    groups.setdefault(r["protocol_name"], []).append(stats["metrics"])
                keys = sorted(set.intersection(*(set(stats) for values in groups.values() for stats in values)))
                by_direction[direction] = {}
                for key in keys:
                    split_values = {split: statistics.mean(stats[key]["estimate"] for stats in values)
                                    for split, values in groups.items()}
                    by_direction[direction][key] = {
                        "mean": statistics.mean(split_values.values()),
                        "sd_between_split_means": statistics.stdev(split_values.values()),
                        "split_seed_averages": split_values,
                        "n_splits": 3, "model_seeds_per_split": 2,
                        "interpretation": "descriptive; splits overlap and seeds are not independent subjects"}
            by_mode[mode] = by_direction
        output[model] = by_mode
    return output


def training_records(records):
    output = []
    for name, record in sorted(records.items()):
        if not name.startswith(("generator-", "ranker-", "pretrain-")):
            continue
        task = record["task"]
        summary_paths = [Path(path) for path in task["outputs"] if path.endswith("/summary.json")]
        for path in summary_paths:
            summary = read(path)
            provenance = read(path.with_name("provenance.json"))
            row = {"task_id": name, "path": str(path.parent), "summary": summary,
                   "arguments": provenance["arguments"], "device_name": provenance["device_name"],
                   "slurm_job_id": record.get("slurm_job_id"),
                   "summary_sha256": file_sha256(path)}
            run_path = path.with_name("run.json")
            if run_path.exists():
                run = read(run_path)
                row["model_metadata"] = {key: run[key] for key in
                    ("parameter_count", "trainable_parameter_count", "generator_checkpoint", "ranker_config")
                    if key in run}
                row["run_sha256"] = file_sha256(run_path)
            initialization = provenance["arguments"].get("init")
            if initialization:
                row["initialization_checkpoint"] = initialization
                row["initialization_sha256"] = provenance["input_sha256"][str(Path(initialization).resolve())]
            metrics_path = path.with_name("metrics.jsonl")
            if metrics_path.exists() and name.startswith("generator-"):
                metrics = [json.loads(line) for line in metrics_path.read_text().splitlines()]
                vals = [entry for entry in metrics if "validation" in entry]
                if vals:
                    chosen = min(vals, key=lambda entry: (entry["validation"]["selection_nll"], entry["step"]))
                    row["selected_step_from_logged_criterion"] = chosen["step"]
            output.append(row)
    # Sqrt/source-excluded initializations were fit before v2; expose that lineage
    # instead of counting their reused checkpoints as new training runs.
    return output


def export_tsv(path, rows):
    rows = list(rows)
    keys = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def validation_candidate_information(pool_audit):
    """Expose whether frozen validation roles can actually discriminate ranks."""
    root = BASE / "pools"
    path = root / "manifest.json"
    if file_sha256(path) != pool_audit["pool_manifest_sha256"]:
        raise ValueError("Validation pool manifest differs from the inspected audit")
    manifest = read(path)
    output = []
    for relative, record in manifest["files"].items():
        path = root / relative
        if not path.name.startswith("validation_"):
            continue
        if file_sha256(path) != record["sha256"]:
            raise ValueError("Frozen validation pool changed: " + str(path))
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            data = json.load(handle)
        for direction, group in data["directions"].items():
            rows = group["rows"]
            counts = [len(row["full_candidates"]) - len(row["positives"]) for row in rows]
            output.append({"protocol": data["protocol"], "role": data["role"], "direction": direction,
                           "n_queries": len(rows), "n_target_universe": len(group["target_universe"]),
                           "n_recorded_edges": sum(len(row["positives"]) for row in rows),
                           "queries_with_no_full_pool_distractor": sum(n == 0 for n in counts),
                           "minimum_full_pool_distractors": min(counts),
                           "median_full_pool_distractors": statistics.median(counts),
                           "maximum_full_pool_distractors": max(counts),
                           "pool_sha256": record["sha256"]})
    return output


def frequency_tie_information(records, checked):
    """Describe score degeneracy without changing the frozen ranking tie rule."""
    output = []
    for task in read(CONFIG / "neighbor_jobs.json")["tasks"]:
        if task["id"] not in records:
            continue
        path = next(Path(p) for p in task["outputs"] if p.endswith("/test.json.gz"))
        digest = file_sha256(path)
        if checked.get(str(path)) != digest:
            raise ValueError("Baseline tie audit input differs: " + str(path))
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            groups = json.load(handle)
        for direction, rows in groups.items():
            zeros, ties = 0, 0
            for row in rows:
                values = [row["scores"]["frequency"][i] for i in row["pool_indices"]["full"]]
                zeros += all(value == 0 for value in values)
                ties += len(set(values)) == 1
            protocol = path.parent.name
            if protocol.startswith("split_seed") and zeros != len(rows):
                raise ValueError("Primary chain-disjoint frequency scores must all be zero")
            output.append({"protocol": protocol, "direction": direction, "n_queries": len(rows),
                           "queries_with_all_zero_frequency_scores": zeros,
                           "queries_with_all_tied_frequency_scores": ties,
                           "tie_rule": "lexicographic target sequence order",
                           "test_scores_sha256": digest})
    return output


def qualitative_examples(records, checked):
    """Deterministic, explicitly descriptive examples; no metric/model selection."""
    output, hashes = [], {}
    prefix = "64/allow_training_targets"
    for protocol in ("split_seed17", "source_holdout", "source_shared"):
        task_id = "evaluation-" + protocol + "-paired-seed-0"
        if task_id not in records:
            continue
        task = records[task_id]["task"]
        path = Path(task["evaluation_root"]) / "free/test/rows.json.gz"
        digest = file_sha256(path)
        if checked.get(str(path)) != digest:
            raise ValueError("Example input was not verified: " + str(path))
        hashes[str(path)] = digest
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            data = json.load(handle)
        for direction, rows in data.items():
            groups = {"not_recovered": [], "recovered_outside_likelihood_top5": [], "likelihood_top5_hit": []}
            for row in sorted(rows, key=lambda r: r["source"]):
                metrics = row["prefixes"][prefix]["methods"]["likelihood"]
                category = ("not_recovered" if not metrics["coverage"] else
                            "likelihood_top5_hit" if metrics["hit_at_5"] else "recovered_outside_likelihood_top5")
                groups[category].append(row)
            for category, matches in groups.items():
                common = {"protocol": protocol, "seed_index": 0, "direction": direction, "category": category,
                          "n_queries_in_category": len(matches), "n_direction_queries": len(rows), "prefix": prefix}
                if not matches:
                    output.append({**common, "selection": "No matching query in this category"})
                    continue
                row = matches[0]
                candidates = {sample["sequence"] for sample in row["samples"][:64] if sample["valid"]}
                nll = dict(zip(row["candidate_sequences"], row["candidate_nll"]))
                neighbors = dict(zip(row["candidate_sequences"], row["candidate_nearest_supervised"]))
                ordered = sorted(candidates, key=lambda s: (nll[s], s))
                positives = set(row["positives"])
                metrics = row["prefixes"][prefix]["methods"]["likelihood"]
                if bool(positives & candidates) != bool(metrics["coverage"]) or bool(positives & set(ordered[:5])) != bool(metrics["hit_at_5"]):
                    raise ValueError("Example does not match the saved 64-draw metric")
                output.append({**common, "selection": "Lexicographically first input within the category",
                               "source_cdr3": row["source"], "recorded_partners": sorted(positives),
                               "unique_candidates": len(candidates), "recovered_partners": sorted(positives & candidates),
                               "likelihood_top5": ordered[:5], "top5_mean_token_nll": [nll[s] for s in ordered[:5]],
                               "top5_exact_training_target": [neighbors[s]["min_raw"] == 0 for s in ordered[:5]],
                               "likelihood_hit_at_5": metrics["hit_at_5"],
                               "ranker_hit_at_5": row["prefixes"][prefix]["methods"].get("ranker", {}).get("hit_at_5"),
                               "positive_query_mean_nll": row["positive_query_mean_nll"]})
    return {"rows": output, "input_sha256": hashes,
            "interpretation": "Post-hoc descriptive examples selected by a deterministic rule; not additional hypothesis tests or biological labels"}


def sampling_grid_information(records, checked):
    """Include the already executed tuning grid and its unchanged primary rule."""
    rows = []
    for task in read(CONFIG / "evaluation_jobs.json")["tasks"]:
        path = Path(task["evaluation_root"]) / "sampling_grid/summary.json"
        if task["id"] not in records or str(path) not in task["outputs"]:
            continue
        if checked.get(str(path)) != file_sha256(path):
            raise ValueError(f"Sampling-grid summary is not verified: {path}")
        summary = read(path)
        cells = []
        for cell in summary["grid"]:
            cell_path = Path(cell["evaluation"]) / "summary.json"
            if checked.get(str(cell_path)) != summary["input_sha256"][str(cell_path)]:
                raise ValueError(f"Sampling-grid cell differs from selected inputs: {cell_path}")
            cells.append({**cell, "summary": read(cell_path), "summary_sha256": checked[str(cell_path)]})
        rows.append({"evaluation": task["evaluation_name"], "seed_index": task["model_seed_index"],
                     "summary": summary, "summary_sha256": checked[str(path)], "cells": cells})
    return rows


def source_event_clusters(reports, checked):
    """Describe concentration of recorded source-test hits; no new inference."""
    rows = []
    metric = "64/allow_training_targets|likelihood|hit_at_5"
    for report in reports:
        if report.get("protocol_name") not in ("source_holdout", "source_shared") or report["mode"] != "free":
            continue
        path = Path(report["analysis_root"]) / "query_metrics.json.gz"
        if str(path) not in checked or file_sha256(path) != checked[str(path)]:
            raise ValueError(f"Source event description requires verified query metrics: {path}")
        with gzip.open(path, "rt") as handle:
            queries = json.load(handle)
        for direction, values in sorted(queries.items()):
            counts = Counter(row["cluster"] for row in values)
            hits = Counter(row["cluster"] for row in values if row["metrics"][metric])
            largest = sorted(counts, key=lambda key: (-counts[key], key))[0]
            rows.append({"evaluation": report["evaluation_name"], "seed_index": report["model_seed_index"],
                         "protocol": report["protocol_name"], "direction": direction,
                         "n_queries": len(values), "n_clusters": len(counts),
                         "largest_query_cluster": largest, "largest_cluster_queries": counts[largest],
                         "likelihood_hit_at_5_events": sum(hits.values()),
                         "hit_clusters": len(hits), "events_in_largest_cluster": hits[largest],
                         "post_hoc_descriptive": True})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-partial", action="store_true", help="Explicit progress-only snapshot; never a final release")
    args = parser.parse_args()
    manifests = [(CONFIG / name, read(CONFIG / name)) for name in MANIFESTS]
    status, pending, checked, records = verify_tasks(manifests, verify_large=not args.allow_partial)
    if pending and not args.allow_partial:
        raise ValueError(f"Final evidence requires every task complete: {len(pending)} remain")
    input_paths = [path for path, _ in manifests] + [CONFIG / "task_supersessions.json",
                  CONFIG / "evaluation_audit_supersessions.json",
                  BASE / "data_audit_final.json", BASE / "distance_audit_corrected/summary.json",
                  BASE / "environment.json", BASE / "pool_audit.json"]
    begin_run(args.output, args, input_paths)
    analysis = dict(manifests)[CONFIG / "analysis_jobs.json"]
    reports, comparisons, table, strata_table = [], [], [], []
    for task in analysis["tasks"]:
        if task["id"] not in records:
            continue
        for report in task["reports"]:
            summary = read(Path(report["analysis_root"]) / "summary.json")
            entry = {**report, "summary": summary}
            if "comparison_name" in report:
                comparisons.append(entry)
            else:
                reports.append(entry)
            for row in metric_rows(report, summary):
                (table if row["stratum"] == "all" else strata_table).append(row)
    evaluations = {}
    for task in dict(manifests)[CONFIG / "evaluation_jobs.json"]["tasks"]:
        if task["id"] not in records:
            continue
        root = Path(task["evaluation_root"])
        modes = ("free",) if task["evaluation_name"].endswith("/shuffled") else ("free", "pools")
        evaluations[task["id"]] = {"evaluation_name": task["evaluation_name"], "seed": task["model_seed_index"],
                                   "protocol": task["protocol_name"], "modes": {}}
        for mode in modes:
            setting_path = root / "calibration" / mode / "settings.json"
            evaluations[task["id"]]["modes"][mode] = {
                "analyzed": read(root / "analyzed" / mode / "summary.json"),
                "test": read(root / mode / "test" / "summary.json"),
                "calibration": read(setting_path), "settings_sha256": file_sha256(setting_path)}
    denoising = {str(path.relative_to(BASE / "pretrain")): read(path)
                 for path in sorted((BASE / "pretrain").glob("*/seed-*/denoising_audit.json"))}
    result = {"schema_version": 2, "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "complete": not pending and not args.allow_partial,
              "usage": "PROGRESS SNAPSHOT ONLY" if args.allow_partial else "verified completion-v2 evidence",
              "task_counts": dict(Counter(row["status"] for row in status)), "task_status": status,
              "data_audit": read(BASE / "data_audit_final.json"),
              "distance_audit": read(BASE / "distance_audit_corrected/summary.json"),
              "pool_audit": read(BASE / "pool_audit.json"),
              "reports": reports, "paired_comparisons": comparisons,
              "three_split_descriptives": split_descriptives(reports),
              "evaluations": evaluations, "training": training_records(records), "denoising": denoising,
              "verified_output_sha256": checked,
              "scope": "recorded-pair recovery; no biological negative truth or information-theoretic impossibility claim"}
    result["validation_candidate_information"] = validation_candidate_information(result["pool_audit"])
    result["frequency_tie_information"] = frequency_tie_information(records, checked)
    result["qualitative_examples"] = qualitative_examples(records, checked)
    result["source_event_clusters"] = source_event_clusters(reports, checked)
    result["sampling_grids"] = sampling_grid_information(records, checked)
    for name in ("pretrain_exposure", "baseline_audit", "training_audit"):
        path = BASE / name / "summary.json"
        result[name] = read(path) if path.exists() else None
    result["evaluation_audits"] = []
    for name in ("evaluation_audit_jobs.json", "evaluation_audit_corrected_jobs.json"):
        for task in dict(manifests)[CONFIG / name]["tasks"]:
            if task["id"] in records:
                audit_path = Path(task["audit_root"]) / "summary.json"
                audit = read(audit_path)
                if not audit["passed"]:
                    raise ValueError(f"Evaluation audit failed: {audit_path}")
                result["evaluation_audits"].append({key: audit[key] for key in
                    ("evaluation_task_id", "evaluation_name", "model_seed_index", "passed", "counts", "scope")})
    result["task_costs"] = {phase: {
        "completed_tasks": sum(row["status"] == "complete" and row["phase"] == phase for row in status),
        "summed_task_wall_seconds": sum(row.get("elapsed_seconds", 0) for row in status
                                        if row["status"] == "complete" and row["phase"] == phase),
        "interpretation": "sum of recorded task durations, including validation and loading; not elapsed project time"}
        for phase in sorted({row["phase"] for row in status})}
    if result["complete"]:
        if len({r["evaluation_task_id"] for r in result["evaluation_audits"]}) != 88 or not result["training_audit"]["passed"]:
            raise ValueError("Final release requires all content and training audits")
    (args.output / "evidence.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    export_tsv(args.output / "metrics.tsv", table)
    export_tsv(args.output / "strata.tsv", strata_table)
    export_tsv(args.output / "task_status.tsv", [{**row, "requirements": ",".join(row["requirements"])} for row in status])
    (args.output / "summary.json").write_text(json.dumps({
        "complete": result["complete"], "task_counts": result["task_counts"],
        "run_reports": len(reports), "comparisons": len(comparisons),
        "metrics_rows": len(table), "strata_rows": len(strata_table),
        "evidence_sha256": file_sha256(args.output / "evidence.json")}, indent=2, sort_keys=True) + "\n")
    finish_run(args.output)
    print(json.dumps(read(args.output / "summary.json")), flush=True)


if __name__ == "__main__":
    main()
