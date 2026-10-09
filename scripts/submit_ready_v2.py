#!/usr/bin/env python3
"""Submit dependency-ready frozen tasks within the observed per-user QoS limits.

One invocation is bounded. All submissions are appended to a ledger; completed,
active, failed, or already-submitted tasks are never submitted again implicitly.
"""

import argparse
import datetime
import fcntl
import hashlib
import json
import os
import subprocess
from pathlib import Path


def sha256(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifests", type=Path, nargs="+", required=True)
    parser.add_argument("--resource", choices=("gpu", "gpu4090", "gpu3090", "gpu_aux", "cpu"), required=True)
    parser.add_argument("--ledger", type=Path,
                        default=Path("artifacts/completion_v2/submissions.jsonl"))
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--supersessions", type=Path,
                        default=Path("configs/completion_v2/task_supersessions.json"))
    parser.add_argument("--submit", action="store_true")
    args = parser.parse_args()
    args.ledger.parent.mkdir(parents=True, exist_ok=True)
    qos, cap = {"gpu": ("2a800", 8), "gpu4090": ("4gpus", 8), "gpu3090": ("4gpus", 8), "gpu_aux": ("4gpus", 8),
                "cpu": ("cpudebug", 1)}[args.resource]
    with args.ledger.with_suffix(".lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        ledger = [json.loads(line) for line in args.ledger.read_text().splitlines()] \
            if args.ledger.exists() else []
        submitted = {(row["manifest_sha256"], int(index)) for row in ledger
                     for index in row["indices"]}
        superseded = {(row["old_manifest_sha256"], row["old_index"])
                      for row in json.loads(args.supersessions.read_text())["replacements"]} \
            if args.supersessions.exists() else set()
        queue = subprocess.check_output(
            ["squeue", "--noheader", "--array", "--user", os.environ.get("USER", "zihanhe25"),
             "--format=%i|%q|%T"], text=True)
        occupied = sum(line.split("|")[1] == qos for line in queue.splitlines())
        room = max(0, min(cap - occupied, args.limit))
        ready, deferred, complete, recorded = [], [], 0, 0
        for manifest_path in args.manifests:
            manifest = json.loads(manifest_path.read_text())
            manifest_hash = sha256(manifest_path)
            root = Path(manifest["root"])
            tasks = list(enumerate(manifest["tasks"]))
            # Interleave model seeds without changing the frozen task indices.
            if manifest.get("phase") in ("generator", "ranker"):
                half = len(tasks) // 2
                tasks.sort(key=lambda pair: (pair[0] % half, pair[0] // half))
            elif manifest.get("phase") == "evaluation":
                # Complete both prespecified seeds together. Scientific commands,
                # task indices, candidates and selection rules are unchanged.
                order = {}
                for _, task in tasks:
                    order.setdefault(task["evaluation_name"], len(order))
                tasks.sort(key=lambda pair: (order[pair[1]["evaluation_name"]],
                                             pair[1]["model_seed_index"]))
            for index, task in tasks:
                if (manifest_hash, index) in superseded:
                    continue
                record_path = root / manifest["job_records"] / (task["id"] + ".json")
                if record_path.exists():
                    record = json.loads(record_path.read_text())
                    if record["status"] == "complete":
                        complete += 1
                    else:
                        recorded += 1
                    continue
                if (manifest_hash, index) in submitted:
                    recorded += 1
                    continue
                missing = [p for p in task.get("requires", []) if not (root / p).is_file()]
                if missing:
                    deferred.append(task["id"])
                    continue
                ready.append((manifest_path, manifest, manifest_hash, index, task))
        chosen = ready[:room]
        print(json.dumps({"resource": args.resource, "occupied": occupied, "capacity": cap,
                          "available": room, "complete": complete, "recorded": recorded,
                          "deferred": len(deferred), "ready": len(ready),
                          "selected": [item[4]["id"] for item in chosen],
                          "submission_requested": args.submit}), flush=True)
        if not args.submit:
            return
        for path, manifest, manifest_hash, index, task in chosen:
            command = ["sbatch", "--parsable", "--array=" + str(index),
                       "--job-name=gdtcr-v2-" + manifest["phase"],
                       "--export=ALL,GDTCR_MANIFEST=" + str(path.resolve()) +
                       ",GDTCR_PYTHON=" + manifest["python"]]
            if args.resource == "gpu":
                command.extend(["--partition=gpua800", "--qos=2a800",
                                "--account=jiameng_mres", "--gres=gpu:a800:1",
                                "slurm/completion_task.sbatch"])
            elif args.resource == "gpu4090":
                command.extend(["--partition=gpu4090", "--qos=4gpus",
                                "--account=jiameng_mres", "--gres=gpu:rtx4090:1",
                                "--cpus-per-task=4", "slurm/completion_task.sbatch"])
            elif args.resource == "gpu3090":
                command.extend(["--partition=gpu3090", "--qos=4gpus",
                                "--account=jiameng_mres", "--gres=gpu:gtx3090:1",
                                "--cpus-per-task=2", "--mem=8G", "--time=01:00:00",
                                "slurm/completion_task.sbatch"])
            elif args.resource == "gpu_aux":
                command.extend(["--partition=gpu3090,gpu4090", "--qos=4gpus",
                                "--account=jiameng_mres", "--gres=gpu:1",
                                "--cpus-per-task=2", "slurm/completion_task.sbatch"])
            else:
                if manifest["phase"] in ("analysis", "evaluation_audit", "training_audit"):
                    command.append("--cpus-per-task=2")
                command.append("slurm/completion_cpu.sbatch")
            if manifest["phase"] == "evaluation" and args.resource != "cpu":
                # Full observed evaluations peak below 1.5 GiB host RSS and
                # 16 minutes. Keep ample headroom while allowing backfill.
                command[-1:-1] = ["--mem=8G", "--time=01:00:00"]
            result = subprocess.run(command, cwd=manifest["root"], capture_output=True, text=True)
            if result.returncode:
                raise RuntimeError(f"Submission rejected; no ledger entry written: {result.stderr.strip()}")
            job_id = result.stdout.strip().split(";")[0]
            if not job_id.isdigit():
                raise RuntimeError(f"Unexpected sbatch response requires manual reconciliation: {result.stdout!r}")
            entry = {"created_utc": now(), "manifest": str(path.resolve()),
                     "manifest_sha256": manifest_hash, "indices": [index],
                     "task_ids": [task["id"]], "job_id": job_id,
                     "resource": args.resource, "command": command,
                     "code_snapshot": manifest["code_snapshot"]}
            with args.ledger.open("a") as handle:
                handle.write(json.dumps(entry, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            print(json.dumps(entry, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
