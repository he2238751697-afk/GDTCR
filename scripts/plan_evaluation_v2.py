#!/usr/bin/env python3
"""Freeze all v2 model evaluations, tuning/calibration gates and saved-sample rescoring."""

import argparse
import datetime
import json
import sys
from pathlib import Path

from freeze_code import freeze


ROOT_OUT = "artifacts/completion_v2"
ROLES = ("validation_tuning", "validation_calibration", "test")


def dependencies(folder):
    return [folder + "/" + filename for filename in ("best.pt", "summary.json", "checksums.json")]


def build_tasks():
    original = json.loads(Path("configs/completion_v2/generator_jobs.json").read_text())
    correction = json.loads(Path("configs/completion_v2/generator_source_correction_jobs.json").read_text())
    corrected = {task["id"]: task for task in correction["tasks"]}
    generators = [corrected.get(task["id"], task) for task in original["tasks"]]
    tasks = []

    def make_task(name, protocol, seed, generator, ranker, prior, direction, train,
                  source_mode, *, base=None, shuffled=False, grid=False, budget=64, requirements=None):
        prefix = f"{ROOT_OUT}/evaluation/{name}/seed-{seed}"
        required = dependencies(generator)
        if ranker:
            required.extend(dependencies(ranker))
        if prior:
            required.extend(dependencies(prior))
        commands, outputs = [], []
        modes = ("free",) if shuffled else ("free", "pools")
        common = ["--generator", generator + "/best.pt", "--directions", direction,
                  "--source-mode", source_mode, "--device", "cuda", "--seed", str((3407, 3508)[seed])]
        if ranker:
            common.extend(("--ranker", ranker + "/best.pt"))

        def evaluate(mode, role, *, temperature=1., top_p=.95, suffix=None, settings=None):
            folder = f"{prefix}/{mode}/" + (suffix or role)
            pool = f"{ROOT_OUT}/pools/{protocol}/{role}.json.gz"
            if base:
                base_folder = f"{ROOT_OUT}/evaluation/{base}/seed-{seed}/{mode}/{role}"
                required.extend(base_folder + "/" + item for item in
                                ("summary.json", "rows.json.gz", "provenance.json", "checksums.json"))
                args = ["--mode", mode, "--base", base_folder, "--ranker", ranker + "/best.pt",
                        "--output", folder, "--device", "cuda", "--train", train]
                if mode == "pools":
                    args.extend(("--pool", pool))
                script = "scripts/rescore_v2.py"
            elif mode == "free":
                samples = budget if role == "test" else 64
                args = [*common, "--pairs", f"data/splits/completion_v2/{protocol}/{role}.tsv",
                        "--train", train, "--output", folder, "--samples", str(samples),
                        "--temperature", str(temperature), "--top-p", str(top_p),
                        "--ranker-source-mode", "same" if shuffled else "paired"]
                script = "scripts/evaluate_free_v2.py"
            else:
                args = [*common, "--pool", pool, "--output", folder]
                if prior:
                    args.extend(("--prior", prior + "/best.pt"))
                script = "scripts/evaluate_pools_v2.py"
            if settings:
                args.extend(("--settings", settings))
            commands.append({"script": script, "args": args})
            outputs.extend(folder + "/" + item for item in ("summary.json", "rows.json.gz", "provenance.json", "checksums.json"))
            return folder

        for mode in modes:
            for role in ROLES[:2]:
                evaluate(mode, role)
            if grid and mode == "free":
                grid_folders = [f"{prefix}/free/validation_tuning"]
                for temperature in (.7, 1., 1.2):
                    for top_p in (.9, .95):
                        if (temperature, top_p) == (1., .95):
                            continue
                        grid_folders.append(evaluate("free", "validation_tuning", temperature=temperature,
                                                     top_p=top_p, suffix=f"grid_t{temperature}_p{top_p}"))
                grid_out = prefix + "/sampling_grid"
                commands.append({"script": "scripts/select_sampling_grid_v2.py",
                                 "args": ["--evaluations", *grid_folders, "--output", grid_out]})
                outputs.extend(grid_out + "/" + item for item in ("summary.json", "checksums.json", "provenance.json"))
            calibration_folder = f"{prefix}/calibration/{mode}"
            args = ["--mode", mode, "--tuning", f"{prefix}/{mode}/validation_tuning",
                    "--calibration", f"{prefix}/{mode}/validation_calibration",
                    "--budget", "64", "--output", calibration_folder]
            if mode == "pools":
                args.extend(("--tuning-pool", f"{ROOT_OUT}/pools/{protocol}/validation_tuning.json.gz",
                             "--calibration-pool", f"{ROOT_OUT}/pools/{protocol}/validation_calibration.json.gz"))
            commands.append({"script": "scripts/calibrate_scores_v2.py", "args": args})
            outputs.extend(calibration_folder + "/" + item for item in
                           ("settings.json", "summary.json", "provenance.json", "checksums.json"))
        for mode in modes:
            evaluate(mode, "test", settings=f"{prefix}/calibration/{mode}/settings.json")
            analyzed = f"{prefix}/analyzed/{mode}"
            args = ["--mode", mode, "--input", f"{prefix}/{mode}/test",
                    "--settings", f"{prefix}/calibration/{mode}/settings.json",
                    "--train", train, "--output", analyzed]
            if mode == "pools":
                args.extend(("--pool", f"{ROOT_OUT}/pools/{protocol}/test.json.gz"))
            commands.append({"script": "scripts/apply_calibration_v2.py", "args": args})
            outputs.extend(analyzed + "/" + item for item in
                           ("summary.json", "rows.json.gz", "provenance.json", "checksums.json"))
        required.extend([train, "data/processed/paired_chain.txt"])
        for role in ROLES:
            required.extend((f"data/splits/completion_v2/{protocol}/{role}.tsv",
                             f"{ROOT_OUT}/pools/{protocol}/{role}.json.gz"))
        tasks.append({"id": "evaluation-" + name.replace("/", "-") + f"-seed-{seed}",
                      "protocol_name": protocol, "directions": direction, "model_seed_index": seed,
                      "evaluation_name": name, "evaluation_root": prefix,
                      "requirements": requirements or ["E1", "E2", "E3", "S2"],
                      "requires": sorted(set(required)), "commands": commands, "outputs": outputs})

    for task in generators:
        arguments = task["commands"][0]["args"]
        get = lambda key: arguments[arguments.index(key) + 1]
        folder = get("--output")
        seed = int(folder.rsplit("-", 1)[1])
        name = folder.split("/generator/", 1)[1].rsplit("/seed-", 1)[0]
        protocol = get("--validation").split("/")[-2]
        ranker = prior = None
        if name.startswith("split_seed") and name.endswith("/paired"):
            ranker = f"{ROOT_OUT}/ranker/main/{protocol}/seed-{seed}"
            prior = f"{ROOT_OUT}/generator/{protocol}/constant/seed-{seed}"
        elif name.startswith("split_seed") and name.endswith("/random"):
            ranker = f"{ROOT_OUT}/ranker/random_init/{protocol}/seed-{seed}"
        elif name.startswith("pretrain_"):
            ranker = f"{ROOT_OUT}/ranker/{name}/seed-{seed}"
        elif name.endswith("/paired") and protocol.startswith(("source_", "seen_input_", "unseen_input_")):
            ranker = f"{ROOT_OUT}/ranker/{protocol}/seed-{seed}"
            prior = f"{ROOT_OUT}/generator/{protocol}/constant/seed-{seed}"
        budget = 256 if name in ("split_seed17/paired", "split_seed17/constant") else 64
        make_task(name, protocol, seed, folder, ranker, prior, get("--direction"), get("--train"),
                  get("--source-mode"), grid=name == "split_seed17/paired", budget=budget,
                  requirements=sorted(set(task["requirements"]) | {"E1", "E2", "E3", "S2"}))
        if name.endswith("/paired") and protocol in ("split_seed17", "split_seed3407", "split_seed2026",
                                                     "source_holdout", "source_shared"):
            make_task(protocol + "/shuffled", protocol, seed, folder, ranker, None,
                      get("--direction"), get("--train"), "shuffled", shuffled=True)
    for seed in range(2):
        for mode, ratios in (("random", (1, 3, 5)), ("mixed", (1, 5))):
            for ratio in ratios:
                make_task(f"negative_ranker/{mode}{ratio}", "split_seed17", seed,
                          f"{ROOT_OUT}/generator/split_seed17/paired/seed-{seed}",
                          f"{ROOT_OUT}/ranker/negatives/{mode}{ratio}/seed-{seed}",
                          f"{ROOT_OUT}/generator/split_seed17/constant/seed-{seed}", "both",
                          "data/splits/completion_v2/split_seed17/train.tsv", "paired",
                          base="split_seed17/paired", budget=256, requirements=["R1", "E3", "S2"])
    return tasks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    root = Path.cwd()
    snapshot = freeze(root, root / "artifacts/completion_v2/code")
    tasks = build_tasks()
    if len(tasks) != 88 or len({task["id"] for task in tasks}) != 88:
        raise ValueError("Evaluation task coverage is incomplete or duplicated")
    manifest = {"schema_version": 2, "root": str(root), "python": sys.executable,
                "code_snapshot": snapshot["snapshot"], "code_digest": snapshot["digest"],
                "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "phase": "evaluation", "job_records": f"{ROOT_OUT}/jobs/evaluation", "tasks": tasks,
                "test_gate": "separate tuning and calibration commands finish before any test command"}
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"manifest": str(args.output), "tasks": len(tasks), "snapshot": snapshot["snapshot"]}))


if __name__ == "__main__":
    main()
