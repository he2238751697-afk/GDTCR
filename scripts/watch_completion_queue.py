#!/usr/bin/env python3
"""Bounded local queue driver for already-frozen, authorized experiment tasks."""

import argparse
import datetime
import json
import subprocess
import sys
import time
from pathlib import Path

from submit_ready_v2 import sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifests", type=Path, nargs="+", required=True)
    parser.add_argument("--resource", choices=("cpu", "gpu", "gpu4090", "gpu_aux"), required=True)
    parser.add_argument("--poll-seconds", type=float, default=20.)
    parser.add_argument("--max-hours", type=float, default=48.)
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--supersessions", type=Path,
                        default=Path("configs/completion_v2/task_supersessions.json"))
    args = parser.parse_args()
    frozen = {str(path): sha256(path) for path in args.manifests}
    supersessions = args.supersessions
    supersession_hash = sha256(supersessions) if supersessions.exists() else None
    replaced = {(row["old_manifest_sha256"], row["old_index"])
                for row in json.loads(supersessions.read_text())["replacements"]} \
        if supersessions.exists() else set()
    started = time.time()
    previous = None
    while time.time() - started < 3600 * args.max_hours:
        if frozen != {str(path): sha256(path) for path in args.manifests}:
            raise ValueError("Watched task manifest changed; inspect before restarting driver")
        if (sha256(supersessions) if supersessions.exists() else None) != supersession_hash:
            raise ValueError("Task supersessions changed; inspect before restarting driver")
        counts, failed = {"complete": 0, "running": 0, "not_started": 0, "failed": 0}, []
        for path in args.manifests:
            manifest = json.loads(path.read_text())
            for index, task in enumerate(manifest["tasks"]):
                if (frozen[str(path)], index) in replaced:
                    continue
                record = Path(manifest["root"]) / manifest["job_records"] / (task["id"] + ".json")
                status = json.loads(record.read_text())["status"] if record.exists() else "not_started"
                counts[status] += 1
                if status == "failed":
                    failed.append(str(record))
        state = {"updated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 "resource": args.resource, "manifest_sha256": frozen,
                 "counts": counts, "failed_records": failed,
                 "elapsed_seconds": time.time() - started}
        args.status.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.status.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
        temporary.replace(args.status)
        if counts != previous:
            print(json.dumps(state, sort_keys=True), flush=True)
            previous = counts
        if failed:
            raise RuntimeError("Failed task requires inspection; driver stopped")
        if counts["complete"] == sum(counts.values()):
            return
        result = subprocess.run(
            [sys.executable, "-B", "scripts/submit_ready_v2.py", "--resource", args.resource,
             "--manifests", *map(str, args.manifests), "--supersessions", str(args.supersessions),
             "--submit"], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stderr or result.stdout)
        lines = result.stdout.splitlines()
        if len(lines) > 1:
            print(result.stdout.rstrip(), flush=True)
        time.sleep(args.poll_seconds)
    raise TimeoutError("Queue driver reached its explicit duration limit")


if __name__ == "__main__":
    main()
