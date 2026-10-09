#!/usr/bin/env python3
"""Build reviewable completion task manifests; submission is always separate."""

import argparse
import datetime
import json
import sys
from pathlib import Path

from freeze_code import freeze


def pretraining_tasks():
    tasks = []
    validation = ["data/splits/pretrain/gamma_validation.tsv", "data/splits/pretrain/delta_validation.tsv"]
    for sampling in ("raw", "balanced", "gamma", "delta", "sqrt"):
        for index, seed in enumerate((3407, 3508)):
            folder = f"artifacts/completion_v2/pretrain/{sampling}/seed-{index}"
            commands = []
            if sampling != "sqrt":
                checkpoint = folder + "/last.pt"
                args = ["--train", "data/splits/pretrain/train.tsv", "--validation", *validation,
                        "--output", folder, "--device", "cuda", "--seed", str(seed),
                        "--sampling", sampling, "--steps", "20000", "--batch-size", "1024",
                        "--learning-rate", "3e-4", "--warmup-steps", "500", "--validation-interval", "500",
                        "--validation-sequences", "2048", "--num-workers", "4", "--compact-checkpoints"]
                commands.append({"script": "scripts/train_denoiser.py", "args": args})
                outputs = [folder + "/last.pt", folder + "/summary.json", folder + "/provenance.json"]
            else:
                checkpoint = f"artifacts/runs/pretrain/a800/seed-{index}/last.pt"
                outputs = []
            commands.append({"script": "scripts/evaluate_denoising.py", "args": [
                "--checkpoint", checkpoint, "--validation", *validation,
                "--output", folder + "/denoising_audit.json", "--device", "cuda", "--seed", str(seed)]})
            outputs.append(folder + "/denoising_audit.json")
            tasks.append({"id": f"pretrain-{sampling}-seed-{index}", "requirements": ["P1", "P2"],
                          "commands": commands, "outputs": outputs})
    return tasks


def generator_tasks():
    tasks = []
    seeds = (3407, 3508)
    base = "data/splits/completion_v2"
    output_root = "artifacts/completion_v2/generator"

    def add(name, protocol, index, init, requirements, *, source_mode="paired",
            sampling="input", direction="both", fraction=None, steps=1500):
        folder = f"{output_root}/{name}/seed-{index}"
        train = f"{base}/{protocol}/" + (f"train_fraction{fraction}.tsv" if fraction else "train.tsv")
        validation = f"{base}/{protocol}/validation_selection.tsv"
        seed = seeds[index]
        args = ["--train", train, "--validation", validation,
                "--output", folder, "--device", "cuda", "--seed", str(seed),
                "--direction", direction, "--source-mode", source_mode,
                "--sampling", sampling, "--validation-objective", "direction_query_nll",
                "--steps", str(steps), "--batch-size", "256", "--learning-rate", "2e-5",
                "--warmup-steps", "100" if steps == 750 else "200",
                "--validation-interval", "100", "--early-stopping-patience", "5",
                "--num-workers", "4", "--compact-checkpoints"]
        required_files = [train, validation]
        if init:
            args.extend(("--init", init))
            required_files.append(init)
            if init.startswith("artifacts/completion_v2/pretrain/"):
                required_files.extend((str(Path(init).parent / "summary.json"),
                                       str(Path(init).parent / "checksums.json")))
            else:
                required_files.append(str(Path(init).parent / "summary.json"))
        tasks.append({"id": f"generator-{name.replace('/', '-')}-seed-{index}",
                      "requirements": requirements, "requires": required_files,
                      "commands": [{"script": "scripts/train_generator.py", "args": args}],
                      "outputs": [folder + "/best.pt", folder + "/summary.json",
                                  folder + "/provenance.json", folder + "/checksums.json"]})

    for index in range(2):
        standard = f"artifacts/runs/pretrain/a800/seed-{index}/last.pt"
        source_clean = f"artifacts/runs/pretrain/source_holdout/seed-{index}/last.pt"
        for split in (17, 3407, 2026):
            protocol = f"split_seed{split}"
            add(f"{protocol}/paired", protocol, index, standard, ["D2", "G1"])
            add(f"{protocol}/constant", protocol, index, standard, ["D2", "G1"] ,
                source_mode="constant")
            add(f"{protocol}/random", protocol, index, None, ["D2", "G1"])
        for sampling in ("raw", "balanced", "gamma", "delta"):
            init = f"artifacts/completion_v2/pretrain/{sampling}/seed-{index}/last.pt"
            add(f"pretrain_{sampling}", "split_seed17", index, init, ["P2"])
        add("edge_uniform", "split_seed17", index, standard, ["G2"], sampling="edge")
        for direction in ("gamma_to_delta", "delta_to_gamma"):
            add("unidirectional/" + direction, "split_seed17", index, standard,
                ["G2"], direction=direction, steps=750)
        for fraction in (10, 25, 50):
            add(f"data_fraction{fraction}/pretrained", "split_seed17", index,
                standard, ["G3"], fraction=fraction)
            add(f"data_fraction{fraction}/random", "split_seed17", index,
                None, ["G3"], fraction=fraction)
        for protocol, init in (("source_holdout", source_clean),
                               ("source_shared", source_clean)):
            add(f"{protocol}/paired", protocol, index, init, ["S1"])
            add(f"{protocol}/constant", protocol, index, init, ["S1"], source_mode="constant")
        for protocol in ("unseen_input_gamma_to_delta", "unseen_input_delta_to_gamma",
                         "seen_input_gamma_to_delta", "seen_input_delta_to_gamma"):
            direction = protocol.split("input_")[1]
            add(f"{protocol}/paired", protocol, index, standard, ["D3"], direction=direction)
            add(f"{protocol}/constant", protocol, index, standard, ["D3"],
                source_mode="constant", direction=direction)
    assert len(tasks) == 68 and len({task["id"] for task in tasks}) == 68
    return tasks


def ranker_tasks():
    tasks = []
    seeds = (3407, 3508)
    root = "artifacts/completion_v2"
    split_root = "data/splits/completion_v2"

    def add(name, protocol, index, generator_name, requirements, *,
            negative_mode="mixed", ratio=3, direction="both"):
        init_folder = f"{root}/generator/{generator_name}/seed-{index}"
        folder = f"{root}/ranker/{name}/seed-{index}"
        train = f"{split_root}/{protocol}/train.tsv"
        validation = f"{split_root}/{protocol}/validation_selection.tsv"
        if generator_name.startswith("data_fraction"):
            raise ValueError("Data-curve rankers require a matching reduced train set")
        args = ["--train", train, "--validation", validation,
                "--validation-known-pairs", "data/processed/paired_chain.txt",
                "--init", init_folder + "/best.pt", "--output", folder,
                "--device", "cuda", "--seed", str(seeds[index]),
                "--steps", "3000", "--batch-size", "256", "--embedding-batch-size", "256",
                "--learning-rate", "3e-4", "--validation-interval", "250",
                "--early-stopping-patience", "8", "--ranker-version", "2",
                "--validation-direction", direction, "--negative-mode", negative_mode,
                "--negative-ratio", str(ratio), "--contrastive-steps", "1500",
                "--compact-checkpoints"]
        tasks.append({"id": f"ranker-{name.replace('/', '-')}-seed-{index}",
                      "requirements": requirements,
                      "requires": [train, validation, "data/processed/paired_chain.txt", init_folder + "/best.pt",
                                   init_folder + "/summary.json", init_folder + "/checksums.json"],
                      "commands": [{"script": "scripts/train_ranker.py", "args": args}],
                      "outputs": [folder + "/best.pt", folder + "/summary.json",
                                  folder + "/provenance.json", folder + "/checksums.json"]})

    for index in range(2):
        for split in (17, 3407, 2026):
            protocol = f"split_seed{split}"
            add(f"main/{protocol}", protocol, index, f"{protocol}/paired", ["R1", "D2"])
            add(f"random_init/{protocol}", protocol, index, f"{protocol}/random", ["G1"])
        for mode, ratios in (("random", (1, 3, 5)), ("mixed", (1, 5))):
            for ratio in ratios:
                add(f"negatives/{mode}{ratio}", "split_seed17", index,
                    "split_seed17/paired", ["R1"], negative_mode=mode, ratio=ratio)
        for sampling in ("raw", "balanced", "gamma", "delta"):
            add(f"pretrain_{sampling}", "split_seed17", index,
                f"pretrain_{sampling}", ["P2"])
        for protocol in ("source_holdout", "source_shared"):
            add(f"{protocol}", protocol, index, f"{protocol}/paired", ["S1"])
        for protocol in ("unseen_input_gamma_to_delta", "unseen_input_delta_to_gamma",
                         "seen_input_gamma_to_delta", "seen_input_delta_to_gamma"):
            direction = protocol.split("input_")[1]
            add(protocol, protocol, index, f"{protocol}/paired", ["D3"], direction=direction)
    assert len(tasks) == 42 and len({task["id"] for task in tasks}) == 42
    return tasks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["pretrain", "generator", "ranker"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    root = Path.cwd()
    snapshot = freeze(root, root / "artifacts/completion_v2/code")
    manifest = {"schema_version": 2, "root": str(root), "python": sys.executable,
                "code_snapshot": snapshot["snapshot"], "code_digest": snapshot["digest"],
                "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "protocol": "paper/protocol_v2.md", "phase": args.phase,
                "job_records": f"artifacts/completion_v2/jobs/{args.phase}",
                "tasks": {"pretrain": pretraining_tasks,
                          "generator": generator_tasks,
                          "ranker": ranker_tasks}[args.phase]()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"manifest": str(args.output), "tasks": len(manifest["tasks"]),
                      "code_snapshot": snapshot["snapshot"], "submission_performed": False}))


if __name__ == "__main__":
    main()
