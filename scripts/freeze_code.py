#!/usr/bin/env python3
"""Snapshot actual source files for queued jobs without changing the worktree."""

import argparse
import datetime
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


def freeze(root, output):
    root, output = root.resolve(), output.resolve()
    files = sorted({p for folder in ("src", "scripts", "slurm", "tests", "paper", "configs")
                    for p in (root / folder).rglob("*")
                    if p.is_file() and p.suffix in (".py", ".sh", ".sbatch", ".md", ".json",
                                                    ".txt", ".toml", ".yaml", ".yml", ".tex", ".bib")
                    and "__pycache__" not in p.parts}
                   | {root / name for name in ("RESEARCH_PLAN.md", "PROGRESS.md", "requirements.txt",
                                               "README.md", ".gitignore") if (root / name).is_file()})
    hashes = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    digest = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = output / (stamp + "_" + digest[:12])
    destination.mkdir(parents=True, exist_ok=False)
    for path in files:
        target = destination / path.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    manifest = {"root": str(root), "snapshot": str(destination), "created_utc": stamp,
                "files_sha256": hashes, "digest": digest,
                "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()}
    (destination / "snapshot.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("artifacts/completion_v2/code"))
    args = parser.parse_args()
    print(json.dumps(freeze(args.root, args.output), sort_keys=True))
