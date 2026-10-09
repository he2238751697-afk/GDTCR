#!/usr/bin/env python3
"""Audit one completed model evaluation, including every saved draw and pool.

This is a content/lineage audit, not a second GPU forward pass. It recomputes
metrics, fusion, thresholds and their application from the immutable scores.
"""

import argparse
import datetime
import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rapidfuzz.distance import Levenshtein

from gdtcr.calibration import fit_calibration
from gdtcr.data import build_source_map, read_pairs
from gdtcr.evaluation import decode_sample_v2
from gdtcr.fileio import file_sha256
from gdtcr.model import PAD
from gdtcr.provenance import begin_run, finish_run
from apply_calibration_v2 import free_result, pool_result
from calibrate_scores_v2 import load_gzip, load_views, model_lineage
from evaluate_free_v2 import query_targets, summarize_prefix, summarize_rows
from evaluate_pools_v2 import summary_for_pool, summarize


def read(path):
    return json.loads(Path(path).read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def same(actual, expected, label):
    """Compare entire JSON trees, rejecting missing fields and nonfinite floats."""
    if isinstance(expected, dict):
        require(isinstance(actual, dict) and actual.keys() == expected.keys(), label + ": keys differ")
        for key, value in expected.items():
            same(actual[key], value, label + "/" + str(key))
    elif isinstance(expected, list):
        require(isinstance(actual, list) and len(actual) == len(expected), label + ": lengths differ")
        for index, (left, right) in enumerate(zip(actual, expected)):
            same(left, right, label + "/" + str(index))
    elif isinstance(expected, float):
        require(isinstance(actual, (float, int)) and math.isfinite(actual) and
                math.isfinite(expected) and math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-11),
                label + ": numeric values differ")
    else:
        require(actual == expected, label + ": values differ")


def finite_vector(values, size, label, nonnegative=False):
    require(isinstance(values, list) and len(values) == size, label + ": score count differs")
    require(all(math.isfinite(x) and (not nonnegative or x >= 0) for x in values),
            label + ": invalid score")


def decode_saved_sample(tokens, target_chain, model_max_length):
    """Restore deterministic tensor padding removed by the stored-token format.

    sample() returns model_max_length columns even when the 36-new-token budget
    expires. decode_sample_v2 records its rejection reason before trimming that
    padding. Re-decoding only the trimmed list changes a no-EOS reason from
    pad_before_eos to missing_eos; both are invalid, but the audit must reconstruct
    the actual padded decoder input to verify the saved reason exactly.
    """
    require(len(tokens) <= 38 <= model_max_length, "Sample exceeds frozen decoding budget")
    return decode_sample_v2(list(tokens) + [PAD] * (model_max_length - len(tokens)), target_chain)


class Auditor:
    def __init__(self, manifest):
        self.manifest = manifest
        self.verified = {}
        snapshot = read(Path(manifest["code_snapshot"]) / "snapshot.json")
        self.sources = {name: digest for name, digest in snapshot["files_sha256"].items()
                        if name.endswith(".py") and name.split("/")[0] in ("scripts", "src")}
        self.counts = {"raw_queries": 0, "saved_draws": 0, "candidate_witnesses": 0,
                       "pool_query_lists": 0, "derived_ranker_rows": 0, "analyzed_queries": 0,
                       "samples_without_observed_eos": 0}

    def verify_file(self, path, digest):
        key = str(Path(path).resolve())
        if key not in self.verified:
            self.verified[key] = file_sha256(path)
        require(self.verified[key] == digest, "Changed file: " + str(path))

    def verify_run(self, folder):
        checksums = read(folder / "checksums.json")
        for name, digest in checksums.items():
            self.verify_file(folder / name, digest)
        metadata = read(folder / "provenance.json")
        same(metadata["source_sha256"], self.sources, str(folder) + "/frozen_sources")
        for path, digest in metadata["input_sha256"].items():
            self.verify_file(path, digest)
        return metadata, read(folder / "summary.json")

    def free(self, folder, arguments, summary):
        pairs = read_pairs(Path(arguments["pairs"]))
        train = read_pairs(Path(arguments["train"]))
        raw = load_gzip(folder / "rows.json.gz")
        expected_directions = ("gamma_to_delta", "delta_to_gamma") if arguments["directions"] == "both" else (arguments["directions"],)
        require(set(raw) == set(expected_directions), "Free directions differ")
        for direction, rows in raw.items():
            source_chain, target_chain = direction.split("_to_")
            generator = Path(arguments.get("generator_" + direction) or arguments["generator"])
            run_path = generator.with_name("run.json")
            self.verify_file(run_path, read(generator.with_name("checksums.json"))["run.json"])
            model_max_length = read(run_path)["model_config"]["max_length"]
            expected = query_targets(pairs, direction)
            require([row["source"] for row in rows] == list(expected), "Free query order/set differs")
            train_targets = {pair[1 if source_chain == "gamma" else 0] for pair in train}
            shuffled = build_source_map(list(expected), arguments["seed"] + (source_chain == "delta"))
            budgets = sorted({v for v in (16, 64, 256) if v <= arguments["samples"]} | {arguments["samples"]})
            for row in rows:
                source = row["source"]
                same(row["positives"], expected[source], "Free positives")
                conditioned = "" if arguments["source_mode"] == "constant" else shuffled[source] if arguments["source_mode"] == "shuffled" else source
                require(row["conditioned_source"] == conditioned, "Free conditioned source differs")
                require(row["source_chain"] == source_chain and row["target_chain"] == target_chain, "Free chain types differ")
                ranker_source = source if arguments["ranker_source_mode"] == "paired" else conditioned
                require(row["ranker_source"] == (ranker_source if arguments.get("ranker") else None), "Ranker source differs")
                require(len(row["samples"]) == arguments["samples"], "Fixed sample budget differs")
                for sample in row["samples"]:
                    same(sample, decode_saved_sample(sample["tokens"], target_chain, model_max_length), "Strict padded-tensor token decoding")
                    self.counts["samples_without_observed_eos"] += int(not sample.get("observed_eos", False))
                candidates = list(dict.fromkeys(s["sequence"] for s in row["samples"] if s["valid"]))
                same(row["candidate_sequences"], candidates, "Candidate encounter order")
                finite_vector(row["candidate_nll"], len(candidates), "Candidate NLL", nonnegative=True)
                finite_vector(row["positive_nll"], len(row["positives"]), "Positive NLL", nonnegative=True)
                same(row["positive_query_mean_nll"], sum(row["positive_nll"]) / len(row["positives"]), "Query NLL")
                same(row["positive_token_count"], sum(len(t) + 1 for t in row["positives"]), "Positive tokens including EOS")
                same(row["positive_nll_token_sum"], sum(nll * (len(t) + 1) for nll, t in zip(row["positive_nll"], row["positives"])), "Token NLL sum")
                ranker = row["candidate_ranker_score"]
                if arguments.get("ranker"):
                    finite_vector(ranker, len(candidates), "Ranker scores")
                else:
                    require(ranker is None, "Unexpected ranker scores")
                require(len(row["candidate_nearest_supervised"]) == len(candidates), "Nearest witnesses missing")
                for candidate, witness in zip(candidates, row["candidate_nearest_supervised"]):
                    require(witness["nearest_raw"] in train_targets and witness["nearest_normalized"] in train_targets, "Nearest witness outside training")
                    require(Levenshtein.distance(candidate, witness["nearest_raw"]) == witness["min_raw"], "Raw nearest witness differs")
                    normal = Levenshtein.normalized_distance(candidate, witness["nearest_normalized"])
                    require(math.isclose(normal, witness["min_normalized"], abs_tol=1e-7), "Normalized nearest witness differs")
                    same(witness["normalized_similarity"], 1 - witness["min_normalized"], "Nearest similarity")
                scores = {"likelihood": dict(zip(candidates, (-n for n in row["candidate_nll"]))),
                          "ranker": dict(zip(candidates, ranker)) if ranker is not None else None}
                same(row["prefixes"], summarize_prefix(row["samples"], row["positives"], train_targets, scores, budgets), "All nested budgets/policies")
                self.counts["saved_draws"] += len(row["samples"])
                self.counts["candidate_witnesses"] += len(candidates)
            same(summary["directions"][direction], summarize_rows(rows), "Raw free summary")
            self.counts["raw_queries"] += len(rows)
        self.derived(folder, arguments, raw, "free")

    def pools(self, folder, arguments, summary):
        pool_path = Path(arguments["pool"])
        self.verify_file(pool_path, summary["pool_sha256"])
        pool, raw = load_gzip(pool_path), load_gzip(folder / "rows.json.gz")
        expected_directions = ("gamma_to_delta", "delta_to_gamma") if arguments["directions"] == "both" else (arguments["directions"],)
        require(set(raw) == set(expected_directions), "Pool directions differ")
        for direction, rows in raw.items():
            entry = pool["directions"][direction]
            targets = entry["target_universe"]
            lookup = {target: i for i, target in enumerate(targets)}
            require(len(rows) == len(entry["rows"]), "Pool query count differs")
            shuffled = build_source_map([r["source"] for r in entry["rows"]], arguments["seed"] + (direction == "delta_to_gamma"))
            for index, (row, item) in enumerate(zip(rows, entry["rows"])):
                require(row["source"] == item["source"] and row["positives"] == item["positives"], "Pool queries/positives differ")
                conditioned = "" if arguments["source_mode"] == "constant" else item["source"]
                require(row["conditioned_source"] == conditioned and row["shuffled_source"] == shuffled[item["source"]], "Pool conditioning differs")
                indices = {name: [lookup[t] for t in values] for name, values in item["pools"].items()}
                indices["full"] = [lookup[t] for t in item["full_candidates"]]
                same(row["pool_indices"], indices, "Frozen pool membership and order")
                scores = row["scores"]
                require(set(scores) == {"likelihood", "ranker", "prior", "shuffled", "difference", "random"}, "Pool method inventory differs")
                present = {"likelihood", "random"}
                if arguments.get("ranker"):
                    present.add("ranker")
                if arguments.get("prior") or arguments.get("prior_" + direction):
                    present.update(("prior", "difference"))
                if arguments["source_mode"] == "paired":
                    present.add("shuffled")
                for method, values in scores.items():
                    if method in present:
                        finite_vector(values, len(targets), "Pool " + method)
                    else:
                        require(values is None, "Unexpected pool method: " + method)
                if scores["prior"] is not None:
                    same(scores["difference"], [a - b for a, b in zip(scores["likelihood"], scores["prior"])], "Likelihood difference")
                rng = random.Random(arguments["seed"] + index * 1009 + (direction == "delta_to_gamma"))
                same(scores["random"], [rng.random() for _ in targets], "Random pool scorer")
                expected = {name: summary_for_pool(item["positives"], targets, values, scores) for name, values in indices.items()}
                same(row["pool_metrics"], expected, "All raw retrieval metrics")
                self.counts["pool_query_lists"] += len(indices)
            same(summary["directions"][direction], summarize(rows), "Raw pool summary")
            self.counts["raw_queries"] += len(rows)
        self.derived(folder, arguments, raw, "pools")

    def derived(self, folder, arguments, raw, mode):
        if not arguments.get("base"):
            return
        original = load_gzip(Path(arguments["base"]) / "rows.json.gz")
        same(list(raw), list(original), "Rescored directions")
        for direction, rows in raw.items():
            require(len(rows) == len(original[direction]), "Rescored row count differs")
            for row, base in zip(rows, original[direction]):
                for key in base:
                    if mode == "free" and key not in ("ranker_source", "candidate_ranker_score", "prefixes"):
                        same(row[key], base[key], "Rescored immutable free field: " + key)
                    elif mode == "pools" and key not in ("scores", "pool_metrics"):
                        same(row[key], base[key], "Rescored immutable pool field: " + key)
                if mode == "pools":
                    same({k: v for k, v in row["scores"].items() if k != "ranker"},
                         {k: v for k, v in base["scores"].items() if k != "ranker"}, "Rescored immutable model scores")
                self.counts["derived_ranker_rows"] += 1

    def calibration(self, folder, arguments):
        mode = arguments["mode"]
        tuning, calibration = Path(arguments["tuning"]), Path(arguments["calibration"])
        settings = read(folder / "settings.json")
        known = set(read_pairs(Path(arguments["known_pairs"])))
        tuning_pool = Path(arguments["tuning_pool"]) if arguments.get("tuning_pool") else None
        calibration_pool = Path(arguments["calibration_pool"]) if arguments.get("calibration_pool") else None
        expected = fit_calibration(load_views(tuning, mode, tuning_pool, arguments["budget"]),
                                   load_views(calibration, mode, calibration_pool, arguments["budget"]), known)
        for key, value in expected.items():
            same(settings[key], value, "Frozen tuning/calibration " + key)
        same(settings["model_inputs"], model_lineage(tuning), "Tuning model lineage")
        same(settings["model_inputs"], model_lineage(calibration), "Calibration model lineage")
        require(settings["primary_budget"] == 64 and settings["primary_policy"] == "allow_training_targets", "Primary calibration budget/policy differs")
        for path, digest in settings["input_sha256"].items():
            self.verify_file(path, digest)

    def applied(self, folder, arguments, summary):
        mode, raw_folder = arguments["mode"], Path(arguments["input"])
        settings_path = Path(arguments["settings"])
        settings, raw = read(settings_path), load_gzip(raw_folder / "rows.json.gz")
        digest = file_sha256(settings_path)
        raw_summary = read(raw_folder / "summary.json")
        require(raw_summary["calibration_settings"]["sha256"] == digest == summary["settings_sha256"], "Test settings hash differs")
        require(summary["test_used_for_selection"] is False, "Test-selected settings")
        known = set(read_pairs(Path(arguments["known_pairs"])))
        if mode == "free":
            expected, directions = free_result(raw, settings, read_pairs(Path(arguments["train"])), known)
        else:
            expected, directions = pool_result(raw, load_views(raw_folder, mode, Path(arguments["pool"])), settings, known)
        same(load_gzip(folder / "rows.json.gz"), expected, "All fused/calibrated test rows")
        same(summary["directions"], directions, "Fused metrics, classification and complete acceptance curves")
        self.counts["analyzed_queries"] += sum(map(len, expected.values()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("configs/completion_v2/evaluation_jobs.json"))
    parser.add_argument("--task", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = read(args.manifest)
    task = manifest["tasks"][args.task]
    record_path = Path(manifest["job_records"]) / (task["id"] + ".json")
    record = read(record_path)
    require(record["status"] == "complete", "Evaluation is incomplete")
    same(record["task"], task, "Task manifest")
    require(record["manifest_sha256"] == file_sha256(args.manifest), "Manifest changed")
    begin_run(args.output, args, [args.manifest, record_path])
    auditor = Auditor(manifest)
    require(set(record["output_sha256"]) == set(task["outputs"]), "Task output inventory differs")
    for path, digest in record["output_sha256"].items():
        auditor.verify_file(path, digest)
    require(len(record["commands"]) == len(task["commands"]), "Task commands incomplete")
    command_reports, calibration_times = [], {}
    previous_time = None
    for command, actual in zip(task["commands"], record["commands"]):
        argv = [manifest["python"], str(Path(manifest["code_snapshot"]) / command["script"]), *command["args"]]
        same(actual["argv"], argv, "Executed command")
        require(actual["returncode"] == 0, "Command failed")
        started = datetime.datetime.fromisoformat(actual["started_utc"])
        require(previous_time is None or started > previous_time, "Command ordering differs")
        previous_time = started
        values = command["args"]
        folder = Path(values[values.index("--output") + 1])
        provenance, summary = auditor.verify_run(folder)
        same(provenance["command_argv"], actual["argv"], "Run command provenance")
        arguments = provenance["arguments"]
        script = Path(command["script"]).name
        if script == "calibrate_scores_v2.py":
            auditor.calibration(folder, arguments)
            calibration_times[arguments["mode"]] = datetime.datetime.fromisoformat(provenance["created_utc"])
        elif script == "apply_calibration_v2.py":
            auditor.applied(folder, arguments, summary)
        elif script in ("evaluate_free_v2.py", "evaluate_pools_v2.py", "rescore_v2.py"):
            mode = arguments.get("mode", "free" if script == "evaluate_free_v2.py" else "pools")
            if folder.name == "test":
                require(mode in calibration_times and started > calibration_times[mode], "Test started before calibration")
                settings_path = Path(arguments["settings"])
                settings = read(settings_path)
                require(summary["calibration_settings"]["sha256"] == file_sha256(settings_path), "Unfrozen test settings")
                same(model_lineage(folder), settings["model_inputs"], "Test model lineage")
                if mode == "free":
                    same({key: arguments[key] for key in settings["sampling"]}, settings["sampling"], "Test sampling settings")
            (auditor.free if mode == "free" else auditor.pools)(folder, arguments, summary)
        elif script == "select_sampling_grid_v2.py":
            require(summary["primary_replaced"] is False and len(summary["grid"]) == 6, "Sampling grid changed primary setting")
            require({(r["temperature"], r["top_p"]) for r in summary["grid"]} == {(t, p) for t in (.7, 1., 1.2) for p in (.9, .95)}, "Sampling grid incomplete")
            require(all(Path(r["evaluation"]).name != "test" for r in summary["grid"]), "Test in sampling grid")
        else:
            raise ValueError("Unaudited command type: " + script)
        command_reports.append({"folder": str(folder), "script": script, "passed": True})
        print(json.dumps(command_reports[-1]), flush=True)
    result = {"schema_version": 2, "passed": True, "evaluation_task_id": task["id"],
              "evaluation_name": task["evaluation_name"], "model_seed_index": task["model_seed_index"],
              "counts": auditor.counts, "commands": command_reports, "verified_sha256": auditor.verified,
              "scope": "all output/input hashes and frozen source lineage; all raw token validity, budgets, prefix metrics, candidate witnesses, frozen pools and scores; deterministic fusion/threshold refit; all calibrated test rows and curves; no repeated GPU forward passes or exhaustive new nearest-distance matrices"}
    (args.output / "summary.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    finish_run(args.output)
    print(json.dumps({"passed": True, "task": task["id"], "counts": auditor.counts}), flush=True)


if __name__ == "__main__":
    main()
