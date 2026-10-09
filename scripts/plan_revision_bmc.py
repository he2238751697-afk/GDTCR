#!/usr/bin/env python3
"""Freeze revision fits and fixed-setting diagnostic evaluations."""
import copy
import datetime
import json
from pathlib import Path
from freeze_code import freeze


def main():
    root = Path.cwd()
    destination = root / "configs/revision_bmc"
    if destination.exists():
        raise FileExistsError("Task manifests are immutable")
    snapshot = freeze(root, root / "artifacts/revision_bmc/code")
    destination.mkdir(parents=True)
    original = json.loads((root / "configs/completion_v2/generator_jobs.json").read_text())
    rankers = json.loads((root / "configs/completion_v2/ranker_corrected_jobs.json").read_text())
    generators = {t["id"]: t for t in original["tasks"]}
    ranker_map = {t["id"]: t for t in rankers["tasks"]}
    phases = {"revision_training": [], "revision_evaluation": []}
    def task(name, commands, requires, outputs):
        return {"id": name, "commands": commands, "requires": requires,
                "outputs": outputs, "requirements": ["BMC-P0-2", "BMC-P0-3"]}
    def output_files(folder, names):
        return [str(folder / n) for n in names]
    for protocol, source_name, direction in (
            ("unseen_gamma_repaired", "unseen_input_gamma_to_delta", "gamma_to_delta"),
            ("giant_edge_holdout", "split_seed17", "both")):
        split = Path("data/splits/revision_bmc") / protocol
        for index in (0, 1):
            seed = 3407 + 101 * index
            generator_folders = {}
            for condition in ("paired", "constant", "random"):
                source_condition = condition if condition != "random" or source_name == "split_seed17" else "paired"
                original_task = generators[f"generator-{source_name}-{source_condition}-seed-{index}"]
                command = copy.deepcopy(original_task["commands"][0])
                args = command["args"]
                output = Path("artifacts/revision_bmc/generator") / protocol / condition / f"seed-{index}"
                generator_folders[condition] = output
                for flag, value in (("--train", split/"train.tsv"),
                                    ("--validation", split/"validation_selection.tsv"),
                                    ("--output", output)):
                    args[args.index(flag)+1] = str(value)
                if condition == "random" and "--init" in args:
                    pos = args.index("--init"); del args[pos:pos+2]
                requires = [str(split/"train.tsv"), str(split/"validation_selection.tsv")]
                if "--init" in args:
                    requires.append(args[args.index("--init")+1])
                phases["revision_training"].append(task(
                    f"generator-{protocol}-{condition}-seed-{index}", [command], requires,
                    output_files(output, ("best.pt", "summary.json", "run.json", "provenance.json", "checksums.json"))))
            ranker_name = (f"ranker-{source_name}-seed-{index}" if source_name != "split_seed17"
                           else f"ranker-main-{source_name}-seed-{index}")
            command = copy.deepcopy(ranker_map[ranker_name]["commands"][0])
            args = command["args"]
            ranker = Path("artifacts/revision_bmc/ranker") / protocol / f"seed-{index}"
            for flag, value in (("--train", split/"train.tsv"), ("--validation", split/"validation_selection.tsv"),
                                ("--init", generator_folders["paired"]/"best.pt"), ("--output", ranker)):
                args[args.index(flag)+1] = str(value)
            phases["revision_training"].append(task(
                f"ranker-{protocol}-seed-{index}", [command],
                [str(split/"train.tsv"), str(split/"validation_selection.tsv"),
                 str(generator_folders["paired"]/"best.pt"), str(generator_folders["paired"]/"checksums.json")],
                output_files(ranker, ("best.pt", "summary.json", "run.json", "provenance.json", "checksums.json"))))
            for condition in ("paired", "constant", "random", "shuffled"):
                generator = generator_folders["paired" if condition == "shuffled" else condition]
                output = Path("artifacts/revision_bmc/evaluation") / protocol / condition / f"seed-{index}"
                args = ["--generator", str(generator/"best.pt"), "--train", str(split/"train.tsv"),
                        "--pairs", str(split/"test.tsv"), "--output", str(output), "--directions", direction,
                        "--source-mode", condition if condition in ("constant", "shuffled") else "paired",
                        "--device", "cuda", "--seed", str(seed), "--samples", "64", "--batch-size", "128",
                        "--temperature", "1", "--top-p", "0.95", "--ranker-source-mode", "same"]
                requires = [str(generator/"best.pt"), str(generator/"checksums.json")]
                if condition in ("paired", "shuffled"):
                    args += ["--ranker", str(ranker/"best.pt")]
                    requires += [str(ranker/"best.pt"), str(ranker/"checksums.json")]
                phases["revision_evaluation"].append(task(
                    f"evaluate-{protocol}-{condition}-seed-{index}",
                    [{"script": "scripts/evaluate_free_v2.py", "args": args}], requires,
                    output_files(output, ("rows.json.gz", "summary.json", "provenance.json", "checksums.json"))))
    for phase, tasks in phases.items():
        manifest = {"schema_version": 2, "root": str(root), "python": original["python"],
                    "phase": phase, "protocol": "paper/revision_bmc_protocol.md",
                    "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "code_snapshot": snapshot["snapshot"], "code_digest": snapshot["digest"],
                    "job_records": "artifacts/revision_bmc/jobs/" + phase, "tasks": tasks}
        path = destination / (phase + ".json")
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True)+"\n")
        print(path, len(tasks))


if __name__ == "__main__":
    main()
