#!/usr/bin/env python3
"""Freeze the remaining sequence-distance and shallow-control CPU tasks."""

import argparse
import datetime
import json
import sys
from pathlib import Path

from freeze_code import freeze


def distance_tasks():
    tasks = []
    queries = "data/processed/paired_chain.txt"

    def add(name, reference, file_format, chain):
        folder = f"artifacts/completion_v2/distances/{name}"
        tasks.append({"id": "distance-" + name.replace("/", "-"), "requirements": ["D4"],
                      "requires": [reference, queries],
                      "commands": [{"script": "scripts/nearest_sequences_v2.py", "args": [
                          "--reference", reference, "--reference-format", file_format,
                          "--queries", queries, "--chain", chain, "--output", folder,
                          "--chunk-size", "32", "--workers", "4"]}],
                      "outputs": [folder + "/summary.json", folder + "/rows.json.gz",
                                  folder + "/run.json"]})

    # Main-pool delta distances already have an immutable, separately recorded run.
    add("pretrain_gamma", "data/splits/pretrain/train.tsv", "sequences", "gamma")
    for chain in ("gamma", "delta"):
        add("pretrain_source_excluded_" + chain,
            "data/splits/source_holdout/pretrain/train.tsv", "sequences", chain)
    manifest = json.loads(Path("data/splits/completion_v2/manifest.json").read_text())
    for protocol in sorted(manifest["protocols"]):
        for chain in ("gamma", "delta"):
            add(f"supervised/{protocol}/{chain}",
                f"data/splits/completion_v2/{protocol}/train.tsv", "pairs", chain)
    for fraction in (10, 25, 50):
        for chain in ("gamma", "delta"):
            add(f"supervised/data_fraction{fraction}/{chain}",
                f"data/splits/completion_v2/split_seed17/train_fraction{fraction}.tsv",
                "pairs", chain)
    return tasks


def shallow_tasks():
    tasks = []
    manifest = json.loads(Path("data/splits/completion_v2/manifest.json").read_text())
    for protocol, entry in sorted(manifest["protocols"].items()):
        for index, seed in enumerate((3407, 3508)):
            folder = f"artifacts/completion_v2/baselines/shallow/{protocol}/seed-{index}"
            pool_root = f"artifacts/completion_v2/pools/{protocol}"
            train = f"data/splits/completion_v2/{protocol}/train.tsv"
            roles = ("validation_selection", "validation_tuning", "validation_calibration", "test")
            tasks.append({"id": f"shallow-{protocol}-seed-{index}", "requirements": ["E1"],
                          "requires": [train, *[pool_root + "/" + role + ".json.gz" for role in roles]],
                          "commands": [{"script": "scripts/evaluate_shallow_v2.py", "args": [
                              "--train", train, "--pool-root", pool_root, "--output", folder,
                              "--directions", entry["direction"], "--seed", str(seed)]}],
                          "outputs": [folder + "/summary.json", folder + "/model.joblib",
                                      folder + "/provenance.json", folder + "/checksums.json",
                                      *[folder + "/" + role + ".json.gz" for role in roles]]})
    return tasks


def neighbor_tasks():
    tasks = []
    manifest = json.loads(Path("data/splits/completion_v2/manifest.json").read_text())
    roles = ("validation_selection", "validation_tuning", "validation_calibration", "test")
    for protocol, entry in sorted(manifest["protocols"].items()):
        folder = f"artifacts/completion_v2/baselines/exact_neighbor/{protocol}"
        pool_root = f"artifacts/completion_v2/pools/{protocol}"
        train = f"data/splits/completion_v2/{protocol}/train.tsv"
        tasks.append({"id": f"exact-neighbor-{protocol}", "requirements": ["E1"],
                      "requires": [train, *[pool_root + "/" + role + ".json.gz" for role in roles]],
                      "commands": [{"script": "scripts/evaluate_neighbors_v2.py", "args": [
                          "--train", train, "--pool-root", pool_root, "--output", folder,
                          "--directions", entry["direction"], "--workers", "4"]}],
                      "outputs": [folder + "/summary.json", folder + "/provenance.json",
                                  folder + "/checksums.json",
                                  *[folder + "/" + role + ".json.gz" for role in roles]]})
    return tasks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("distance", "shallow", "neighbor"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    root = Path.cwd()
    snapshot = freeze(root, root / "artifacts/completion_v2/code")
    record = {"schema_version": 2, "root": str(root), "python": sys.executable,
              "code_snapshot": snapshot["snapshot"], "code_digest": snapshot["digest"],
              "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "protocol": "paper/protocol_v2.md", "phase": args.phase,
              "job_records": f"artifacts/completion_v2/jobs/{args.phase}",
              "tasks": {"distance": distance_tasks, "shallow": shallow_tasks,
                        "neighbor": neighbor_tasks}[args.phase]()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"manifest": str(args.output), "tasks": len(record["tasks"]),
                      "snapshot": snapshot["snapshot"]}))


if __name__ == "__main__":
    main()
