#!/usr/bin/env python3
"""Freeze a real-checkpoint GPU integration check, excluded from science results."""

import datetime
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gdtcr.data import read_pairs, write_pairs
from gdtcr.fileio import file_sha256
from freeze_code import freeze
from prepare_candidate_pools_v2 import build_role


def main():
    root = Path.cwd()
    output = root / "configs/completion_v2/smoke_gpu_jobs.json"
    folder = Path("artifacts/completion_v2/smoke_gpu")
    if output.exists() or (folder.exists() and any(folder.iterdir())):
        raise FileExistsError("GPU integration check already prepared")
    folder.mkdir(parents=True, exist_ok=True)
    pairs_file = folder / "validation_input.tsv"
    pairs = read_pairs(Path("data/splits/completion_v2/split_seed17/validation_selection.tsv"))[:6]
    write_pairs(pairs_file, pairs)
    known_path = Path("data/processed/paired_chain.txt")
    pool_path = folder / "pool_input.json.gz"
    pool = {"schema_version": 2, "purpose": "integration check only; excluded from scientific analyses",
            "directions": build_role(pairs, read_pairs(known_path), 100, 7319),
            "known_pairs_sha256": file_sha256(known_path), "pair_sha256": file_sha256(pairs_file),
            "negative_definition": "unrecorded combinations, excluding other known partners"}
    with gzip.open(pool_path, "wt", encoding="utf-8") as handle:
        json.dump(pool, handle, sort_keys=True)
    generator = "artifacts/runs/generator/a800_early/seed-0/best.pt"
    train = "data/splits/completion_v2/split_seed17/train.tsv"
    ranker_folder, free_folder, pool_folder = [str(folder / name) for name in ("ranker", "free", "pools")]
    commands = [
        {"script": "scripts/train_ranker.py", "args": [
            "--train", train, "--validation", str(pairs_file),
            "--validation-known-pairs", str(known_path), "--init", generator,
            "--output", ranker_folder, "--device", "cuda", "--seed", "7319",
            "--steps", "4", "--contrastive-steps", "2", "--batch-size", "32",
            "--embedding-batch-size", "64", "--validation-interval", "2",
            "--ranker-version", "2", "--negative-mode", "mixed", "--negative-ratio", "3",
            "--validation-direction", "both", "--compact-checkpoints"]},
        {"script": "scripts/evaluate_free_v2.py", "args": [
            "--generator", generator, "--ranker", ranker_folder + "/best.pt",
            "--pairs", str(pairs_file), "--train", train, "--output", free_folder,
            "--samples", "256", "--seed", "7319", "--device", "cuda"]},
        {"script": "scripts/evaluate_pools_v2.py", "args": [
            "--pool", str(pool_path), "--generator", generator, "--prior", generator,
            "--ranker", ranker_folder + "/best.pt", "--output", pool_folder,
            "--device", "cuda", "--seed", "7319"]}]
    snapshot = freeze(root, root / "artifacts/completion_v2/code")
    task = {"id": "gpu-v2-integration-check", "requirements": [],
            "requires": [train, str(known_path), generator, str(pairs_file), str(pool_path)],
            "commands": commands,
            "outputs": [directory + "/" + name for directory in (ranker_folder, free_folder, pool_folder)
                        for name in ("summary.json", "checksums.json", "provenance.json")] +
                       [ranker_folder + "/best.pt", free_folder + "/rows.json.gz", pool_folder + "/rows.json.gz"]}
    record = {"schema_version": 2, "root": str(root), "python": sys.executable,
              "code_snapshot": snapshot["snapshot"], "code_digest": snapshot["digest"],
              "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "phase": "smoke", "job_records": "artifacts/completion_v2/jobs/smoke",
              "scientific_result": False, "tasks": [task]}
    output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"manifest": str(output), "tasks": 1, "scientific_result": False}))


if __name__ == "__main__":
    main()
