#!/usr/bin/env python3
"""Execute one immutable experiment task; never submit jobs from this entry."""

import argparse
import datetime
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--task", type=int, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    task = manifest["tasks"][args.task]
    root, snapshot = Path(manifest["root"]), Path(manifest["code_snapshot"])
    frozen = json.loads((snapshot / "snapshot.json").read_text())
    for path, expected in frozen["files_sha256"].items():
        if digest(snapshot / path) != expected:
            raise ValueError(f"Frozen source changed: {path}")
    output = root / manifest["job_records"] / (task["id"] + ".json")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        old = json.loads(output.read_text())
        if old["status"] == "complete":
            if old["manifest_sha256"] != digest(args.manifest) or old["task"] != task:
                raise ValueError("Completed task belongs to another manifest or command")
            if all((root / p).exists() and digest(root / p) == h for p, h in old["output_sha256"].items()):
                print(f"Already complete and verified: {task['id']}", flush=True)
                return
            raise ValueError("Completed task outputs changed")
        raise FileExistsError(f"Existing task record requires inspection before rerun: {output}")
    missing = [path for path in task.get("requires", []) if not (root / path).exists()]
    if missing:
        raise FileNotFoundError(f"Task dependencies are incomplete: {missing}")
    state = {"task": task, "manifest": str(args.manifest.resolve()),
             "manifest_sha256": digest(args.manifest), "code_snapshot": str(snapshot),
             "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
             "slurm_array_job_id": os.environ.get("SLURM_ARRAY_JOB_ID"),
             "slurm_array_task_id": os.environ.get("SLURM_ARRAY_TASK_ID"),
             "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
             "status": "running", "commands": []}
    def save():
        temporary = output.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
        temporary.replace(output)
    save()
    started = time.time()
    try:
        for command in task["commands"]:
            argv = [manifest["python"], str(snapshot / command["script"]), *command["args"]]
            entry = {"argv": argv, "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
            state["commands"].append(entry)
            save()
            print(json.dumps({"task": task["id"], "command": argv}), flush=True)
            result = subprocess.run(argv, cwd=root, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
            entry["returncode"] = result.returncode
            save()
            if result.returncode:
                raise RuntimeError(f"Command failed with {result.returncode}")
        state["output_sha256"] = {p: digest(root / p) for p in task["outputs"]}
        state["status"] = "complete"
    except BaseException as error:
        state["status"] = "failed"
        state["error"] = repr(error)
        raise
    finally:
        state["elapsed_seconds"] = time.time() - started
        state["finished_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save()


if __name__ == "__main__":
    main()
