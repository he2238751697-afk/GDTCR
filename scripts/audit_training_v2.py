#!/usr/bin/env python3
"""Verify completed training lineage, selected checkpoints and exposure counts."""

import argparse
import json
from pathlib import Path

import torch

from audit_evaluations_v2 import Auditor, read, require, same
from gdtcr.fileio import file_sha256
from gdtcr.provenance import begin_run, finish_run


CONFIG = Path("configs/completion_v2")
MANIFESTS = ("pretrain_jobs.json", "generator_jobs.json",
             "generator_source_correction_jobs.json", "ranker_corrected_jobs.json")


def checkpoint(path, arguments, state_key):
    # Only locally generated, hash-verified checkpoints are deserialized.
    value = torch.load(path, map_location="cpu", weights_only=False, mmap=True)
    same(json.loads(json.dumps(value["arguments"], default=str)), arguments, "Checkpoint arguments")
    require(all(torch.isfinite(tensor).all().item() for tensor in value[state_key].values()),
            "Nonfinite model weights: " + str(path))
    return value


def selected_generator(validations, delta):
    best, selected = float("inf"), None
    for row in validations:
        if row["validation"]["selection_nll"] < best - delta:
            selected, best = row, row["validation"]["selection_nll"]
    require(selected is not None, "No generator checkpoint satisfies selection")
    return selected


def inspect_training(folder, phase, summary, arguments):
    run = read(folder / "run.json")
    same(run["arguments"], arguments, "Training run arguments")
    require(arguments["seed"] in (3407, 3508), "Unexpected training seed")
    require(arguments["device"] == "cuda" and "A800" in run["device_name"], "Training device differs")
    require(not arguments.get("resume"), "Exposure audit expects uninterrupted training")
    steps = summary["steps_completed"]
    require(0 < steps <= arguments["steps"], "Training step budget differs")
    logs = [json.loads(line) for line in (folder / "metrics.jsonl").read_text().splitlines()]
    validations = [row for row in logs if "validation" in row]
    require(validations and validations[-1]["step"] == steps, "Final validation missing")
    row = {"phase": phase, "path": str(folder), "seed": arguments["seed"], "steps": steps,
           "nominal_steps": arguments["steps"], "batch_size": arguments["batch_size"],
           "elapsed_seconds": summary["elapsed_seconds"], "device_name": run["device_name"],
           "train_pairs": run.get("train_pairs"), "arguments": arguments}
    if phase == "generator":
        require(arguments["validation_objective"] == "direction_query_nll", "Generator selection objective differs")
        require(Path(arguments["validation"]).name == "validation_selection.tsv", "Generator selection role differs")
        require(run["parameter_count"] == 7396890, "Generator architecture size differs")
        chosen = selected_generator(validations, arguments["min_delta"])
        best = checkpoint(folder / "best.pt", arguments, "model_state")
        state = best["training_state"]
        require(state["step"] == chosen["step"], "Generator selected step differs")
        same(state["validation"], chosen["validation"], "Selected generator validation")
        same(summary["best_validation_nll"], chosen["validation"]["selection_nll"], "Best generator NLL")
        sequences = summary["direction_sequences_this_invocation"]
        tokens = summary["direction_target_tokens_this_invocation"]
        require(sum(sequences.values()) == steps * arguments["batch_size"], "Generator draw exposure differs")
        if arguments["direction"] != "both":
            require(sequences[arguments["direction"]] == sum(sequences.values()), "Unidirectional exposure differs")
        row.update(selected_step=state["step"], selected_metric=summary["best_validation_nll"],
                   sequence_exposure=sequences, target_token_exposure=tokens,
                   parameter_count=run["parameter_count"],
                   peak_allocated_gib=summary.get("peak_memory_allocated_gib"))
    elif phase == "ranker":
        require(arguments["ranker_version"] == 2 and arguments["contrastive_steps"] == 1500, "Ranker version/stages differ")
        require(Path(arguments["validation"]).name == "validation_selection.tsv", "Ranker selection role differs")
        require(arguments["negative_mode"] in ("random", "mixed") and arguments["negative_ratio"] in (1, 3, 5), "Ranker negative setting differs")
        eligible = [r for r in validations if r["step"] > arguments["contrastive_steps"]]
        require(bool(eligible), "Explicit-negative stage not completed")
        chosen = max(eligible, key=lambda r: (r["validation"]["mrr"], -r["step"]))
        best = checkpoint(folder / "best.pt", arguments, "ranker_state")
        require(best["step"] == chosen["step"] == summary["best_step"], "Ranker selected step differs")
        require(best["training_stage"] == "bce" and best["ranker_config"]["version"] == 2, "Ranker checkpoint stage/version differs")
        same(best["validation"], chosen["validation"], "Selected ranker validation")
        same(summary["best_validation_mrr"], chosen["validation"]["mrr"], "Best ranker MRR")
        for record in eligible:
            metrics = record["validation"]
            directions = metrics["directions"]
            expected = sum(d["mrr"] for d in directions.values()) / len(directions) if arguments["validation_direction"] == "both" else directions[arguments["validation_direction"]]["mrr"]
            same(metrics["mrr"], expected, "Ranker direction-balanced checkpoint criterion")
        audit = summary["negative_audit"]
        draws = audit.get("random_draws", 0) + audit.get("hard_draws", 0)
        expected = (steps - arguments["contrastive_steps"]) * arguments["batch_size"] * arguments["negative_ratio"]
        require(draws + audit.get("no_unrecorded_target", 0) == expected, "Negative exposure differs from ratio and steps")
        require(sum(v for k, v in audit.items() if k.startswith("length_difference_")) == draws, "Negative length audit differs")
        require(audit.get("source_gamma", 0) + audit.get("source_delta", 0) == draws, "Negative source audit differs")
        if arguments["negative_mode"] == "random":
            require(audit.get("hard_draws", 0) == audit.get("hard_fallbacks", 0) == 0, "Random-only negative run contains hard draws")
        row.update(selected_step=best["step"], selected_metric=summary["best_validation_mrr"],
                   constructed_negative_draws=draws, negative_audit=audit,
                   positive_pair_draws=steps * arguments["batch_size"])
    else:
        require(steps == arguments["steps"] == 20000 and arguments["batch_size"] == 1024, "Pretraining budget differs")
        last = checkpoint(folder / "last.pt", arguments, "model_state")
        require(last["training_state"]["step"] == steps, "Pretraining checkpoint step differs")
        sequences = summary["chain_sequences_this_invocation"]
        tokens = summary["chain_target_tokens_this_invocation"]
        require(sum(sequences.values()) == 20480000, "Pretraining draws differ")
        if arguments["sampling"] in ("gamma", "delta"):
            require(sequences[arguments["sampling"]] == sum(sequences.values()), "Single-chain pretraining exposure differs")
        row.update(selected_step=steps, sequence_exposure=sequences,
                   target_token_exposure=tokens, parameter_count=run["parameter_count"],
                   peak_allocated_gib=summary.get("peak_memory_allocated_gib"))
    if "sequence_exposure" in row:
        for key, count in row["sequence_exposure"].items():
            require(7 * count <= row["target_token_exposure"][key] <= 36 * count,
                    "Token exposure outside allowed residue lengths plus EOS")
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifests = [(CONFIG / name, read(CONFIG / name)) for name in MANIFESTS]
    replaced = {(r["old_manifest_sha256"], r["old_index"])
                for r in read(CONFIG / "task_supersessions.json")["replacements"]}
    begin_run(args.output, args, [p for p, _ in manifests] + [CONFIG / "task_supersessions.json"])
    reports, hashes = [], {}
    for path, manifest in manifests:
        digest = file_sha256(path)
        auditor = Auditor(manifest)
        for index, task in enumerate(manifest["tasks"]):
            if (digest, index) in replaced:
                continue
            record_path = Path(manifest["job_records"]) / (task["id"] + ".json")
            record = read(record_path)
            require(record["status"] == "complete", "Training task incomplete: " + task["id"])
            require(record["manifest_sha256"] == digest, "Training manifest changed")
            same(record["task"], task, "Training task")
            require(set(record["output_sha256"]) == set(task["outputs"]), "Training output inventory differs")
            for output, expected in record["output_sha256"].items():
                auditor.verify_file(output, expected)
            require(len(record["commands"]) == len(task["commands"]) and
                    all(c["returncode"] == 0 for c in record["commands"]), "Training command failed/missing")
            for command, actual in zip(task["commands"], record["commands"]):
                same(actual["argv"], [manifest["python"], str(Path(manifest["code_snapshot"]) / command["script"]), *command["args"]], "Training command line")
                if not Path(command["script"]).name.startswith("train_"):
                    continue
                values = command["args"]
                folder = Path(values[values.index("--output") + 1])
                provenance, summary = auditor.verify_run(folder)
                same(provenance["command_argv"], actual["argv"], "Training provenance command")
                row = inspect_training(folder, manifest["phase"], summary, provenance["arguments"])
                row.update(task_id=task["id"], slurm_job_id=record["slurm_job_id"], passed=True)
                reports.append(row)
                print(json.dumps({k: row[k] for k in ("task_id", "selected_step", "passed")}), flush=True)
        hashes.update(auditor.verified)
    counts = {phase: sum(row["phase"] == phase for row in reports) for phase in ("pretrain", "generator", "ranker")}
    require(counts == {"pretrain": 8, "generator": 68, "ranker": 42}, "Training coverage differs")
    result = {"schema_version": 2, "passed": True, "counts": counts, "runs": reports,
              "verified_sha256": hashes,
              "scope": "all v2 training input/output/code hashes, finite selected weights, logged checkpoint criteria, stages and exposure accounting; reused sqrt/source pretraining is separately reconstructed and identified by checkpoint SHA256"}
    (args.output / "summary.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    finish_run(args.output)


if __name__ == "__main__":
    main()
