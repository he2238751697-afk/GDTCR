#!/usr/bin/env python3
"""Freeze the complete v2 descriptive/paired analysis graph without looking at outcomes."""

import argparse
import datetime
import json
import sys
from pathlib import Path

from freeze_code import freeze


BASE = "artifacts/completion_v2"
RUN_FILES = ("summary.json", "query_metrics.json.gz", "provenance.json", "checksums.json")


def artifact_files(folder, names=RUN_FILES):
    return [folder + "/" + name for name in names]


def build_tasks():
    evaluations = json.loads(Path("configs/completion_v2/evaluation_jobs.json").read_text())["tasks"]
    tasks, runs, models = [], {}, {}
    for task in evaluations:
        protocol, name, seed = task["protocol_name"], task["evaluation_name"], task["model_seed_index"]
        root = task["evaluation_root"]
        command = next(command for command in task["commands"] if command["script"].endswith("apply_calibration_v2.py"))
        arguments = command["args"]
        train = arguments[arguments.index("--train") + 1]
        modes = ("free",) if name.endswith("/shuffled") else ("free", "pools")
        models[name, seed] = task
        for mode in modes:
            output = f"{BASE}/analysis/runs/{name}/seed-{seed}/{mode}"
            arguments = ["--mode", mode, "--input", f"{root}/analyzed/{mode}",
                         "--raw", f"{root}/{mode}/test", "--settings", f"{root}/calibration/{mode}/settings.json",
                         "--protocol", protocol, "--pairs", f"data/splits/completion_v2/{protocol}/test.tsv",
                         "--train", train, "--output", output]
            required = [value for value in task["outputs"] if "/analyzed/" in value or f"/calibration/{mode}/" in value]
            required.extend(artifact_files(f"{root}/{mode}/test", ("summary.json", "rows.json.gz", "checksums.json", "provenance.json")))
            if mode == "free":
                dataset = "data_fraction" + Path(train).stem.removeprefix("train_fraction") \
                    if Path(train).stem.startswith("train_fraction") else protocol
                for chain in ("gamma", "delta"):
                    for folder in (f"{BASE}/distances/supervised/{dataset}/{chain}",
                                   f"{BASE}/distances/" + ("pretrain_source_excluded_" if protocol.startswith("source_") else "pretrain_") + chain):
                        required.extend(artifact_files(folder, ("summary.json", "rows.json.gz")))
            tasks.append({"id": f"analysis-{name.replace('/', '-')}-seed-{seed}-{mode}",
                          "protocol_name": protocol, "evaluation_name": name, "model_seed_index": seed,
                          "mode": mode, "analysis_root": output, "requirements": ["S2"] + (["D4"] if mode == "free" else []),
                          "requires": sorted(set(required)),
                          "commands": [{"script": "scripts/analyze_run_v2.py", "args": arguments}],
                          "outputs": artifact_files(output)})
            runs[name, seed, mode] = output

    protocols = json.loads(Path("data/splits/completion_v2/manifest.json").read_text())["protocols"]
    baseline_runs = {}
    for protocol in sorted(protocols):
        for kind, seeds in (("exact_neighbor", (None,)), ("shallow", (0, 1))):
            for seed in seeds:
                source = f"{BASE}/baselines/{kind}/{protocol}" + (f"/seed-{seed}" if seed is not None else "")
                name = kind + (f"/seed-{seed}" if seed is not None else "")
                output = f"{BASE}/analysis/baselines/{protocol}/{name}"
                tasks.append({"id": f"analysis-baseline-{protocol}-{name.replace('/', '-')}",
                              "protocol_name": protocol, "baseline": kind, "model_seed_index": seed,
                              "mode": "pools", "analysis_root": output, "requirements": ["E1", "S2"],
                              "requires": artifact_files(source, ("summary.json", "test.json.gz", "checksums.json", "provenance.json")),
                              "commands": [{"script": "scripts/analyze_baseline_v2.py", "args": [
                                  "--kind", kind, "--input", source, "--protocol", protocol,
                                  "--pairs", f"data/splits/completion_v2/{protocol}/test.tsv", "--output", output]}],
                              "outputs": artifact_files(output)})
                baseline_runs[protocol, kind, seed] = output

    def comparison(label, protocol, seed, mode, left, right, lm=None, rm=None, direction=None):
        output = f"{BASE}/analysis/comparisons/{label}/seed-{seed}/{mode}"
        arguments = ["--left", left, "--right", right, "--output", output]
        if lm is not None:
            arguments.extend(("--left-method", lm, "--right-method", rm))
        if direction is not None:
            arguments.extend(("--direction", direction))
        tasks.append({"id": f"comparison-{label.replace('/', '-')}-seed-{seed}-{mode}",
                      "protocol_name": protocol, "comparison_name": label, "model_seed_index": seed,
                      "mode": mode, "analysis_root": output, "requirements": ["S2"],
                      "requires": sorted(set(artifact_files(left) + artifact_files(right))),
                      "commands": [{"script": "scripts/compare_runs_v2.py", "args": arguments}],
                      "outputs": artifact_files(output, ("summary.json", "provenance.json", "checksums.json"))})

    for (name, seed), task in sorted(models.items()):
        protocol, direction = task["protocol_name"], task["directions"]
        if name.endswith("/paired"):
            reference = None
        elif name.startswith("data_fraction"):
            reference = name.rsplit("/", 1)[0] + "/pretrained" if name.endswith("/random") else "split_seed17/paired"
        else:
            reference = protocol + "/paired"
        for mode in ("free", "pools"):
            if (name, seed, mode) not in runs:
                continue
            run = runs[name, seed, mode]
            if reference is not None:
                comparison(name + "/versus_primary", protocol, seed, mode, run, runs[reference, seed, mode],
                           direction=direction if direction != "both" else None)
            # Ranker/fusion improvements use the exact same saved candidates.
            has_ranker = any("--ranker" in cmd["args"] for cmd in task["commands"])
            if has_ranker:
                for method in ("ranker", "fused"):
                    comparison(name + "/" + method + "_minus_likelihood", protocol, seed, mode,
                               run, run, method, "likelihood")
            if mode == "pools" and name.endswith("/paired"):
                for baseline, method, baseline_seed in (("exact_neighbor", "edit_neighbor", None),
                                                        ("exact_neighbor", "frequency", None),
                                                        ("shallow", "shallow", seed)):
                    for model_method in ("likelihood", "ranker", "fused"):
                        comparison(name + "/" + model_method + "_minus_" + method, protocol, seed, mode,
                                   run, baseline_runs[protocol, baseline, baseline_seed], model_method, method)
                for method in ("prior", "shuffled", "difference", "random"):
                    comparison(name + "/likelihood_minus_" + method, protocol, seed, mode,
                               run, run, "likelihood", method)

    ids = [task["id"] for task in tasks]
    outputs = [path for task in tasks for path in task["outputs"]]
    if len(ids) != len(set(ids)) or len(outputs) != len(set(outputs)):
        raise ValueError("Analysis tasks or output paths collide")
    # Bundle analyses with identical dependency timing to avoid hundreds of tiny
    # scheduler submissions; each command still writes its own immutable report.
    bundled = {}
    for task in tasks:
        if "comparison_name" in task:
            # All contrasts for a fitted model share the same source outcomes.
            label = task["comparison_name"].rsplit("/", 1)[0]
            key = ("comparison", label, task["model_seed_index"])
        elif "evaluation_name" in task:
            key = ("model", task["evaluation_name"], task["model_seed_index"])
        else:
            key = ("baseline", task["id"], task["model_seed_index"])
        if key not in bundled:
            bundled[key] = {"id": "bundle-" + task["id"].removesuffix("-" + task["mode"]),
                            "requirements": [], "requires": [], "commands": [], "outputs": [], "reports": []}
        entry = bundled[key]
        for field in ("requirements", "requires", "commands", "outputs"):
            entry[field].extend(task[field])
        entry["reports"].append({key: value for key, value in task.items()
                                 if key not in ("requirements", "requires", "commands", "outputs")})
    for entry in bundled.values():
        entry["requires"] = sorted(set(entry["requires"]))
        entry["requirements"] = sorted(set(entry["requirements"]))
    return list(bundled.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    root = Path.cwd()
    tasks = build_tasks()
    snapshot = freeze(root, root / "artifacts/completion_v2/code")
    manifest = {"schema_version": 2, "root": str(root), "python": sys.executable,
                "code_snapshot": snapshot["snapshot"], "code_digest": snapshot["digest"],
                "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "phase": "analysis", "job_records": f"{BASE}/jobs/analysis", "tasks": tasks,
                "statistics": "2000 paired component/source-query percentile replicates; descriptive intervals"}
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"manifest": str(args.output), "tasks": len(tasks), "snapshot": snapshot["snapshot"]}))


if __name__ == "__main__":
    main()
