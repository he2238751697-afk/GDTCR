"""Immutable run inputs and runtime provenance for completion experiments."""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import platform
import socket
import subprocess
import sys
from pathlib import Path

import torch

from .fileio import file_sha256


def source_hashes(root):
    root = Path(root)
    return {str(p.relative_to(root)): file_sha256(p)
            for folder in ("src", "scripts")
            for p in sorted((root / folder).rglob("*.py"))}


def begin_run(output, args, inputs):
    """Refuse destructive reruns and record actual (including dirty) sources."""
    output = Path(output)
    if (output / "summary.json").exists():
        raise FileExistsError(f"Completed run is immutable: {output}")
    if (output / "run.json").exists() and not getattr(args, "resume", False):
        raise FileExistsError(f"Existing run requires explicit compatible resume: {output}")
    output.mkdir(parents=True, exist_ok=True)
    input_hashes = {str(Path(p).resolve()): file_sha256(p) for p in inputs if p}
    root = Path(__file__).resolve().parents[2]
    sources = source_hashes(root)
    arguments = json.loads(json.dumps(vars(args), default=str))
    metadata_path = output / "provenance.json"
    if metadata_path.exists():
        old = json.loads(metadata_path.read_text())
        comparable = {k: v for k, v in arguments.items() if k != "resume"}
        previous = {k: v for k, v in old["arguments"].items() if k != "resume"}
        if old["input_sha256"] != input_hashes or comparable != previous:
            raise ValueError("Resume would change inputs or configuration")
        if old["source_sha256"] != sources:
            raise ValueError("Resume would change the frozen source code")
        return old
    try:
        git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        git_status = subprocess.check_output(["git", "status", "--short"], text=True)
    except (OSError, subprocess.CalledProcessError):
        git_sha, git_status = None, None
    record = {
        "schema_version": 2,
        "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "arguments": arguments, "command_argv": [sys.executable, *sys.argv],
        "input_sha256": input_hashes, "source_root": str(root),
        "source_sha256": sources,
        "source_digest": hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest(),
        "git_head": git_sha, "git_status_at_start": git_status,
        "python": sys.version, "torch": torch.__version__, "cuda": torch.version.cuda,
        "float32_matmul_precision": torch.get_float32_matmul_precision(),
        "cuda_matmul_allow_tf32": torch.backends.cuda.matmul.allow_tf32,
        "cudnn_allow_tf32": torch.backends.cudnn.allow_tf32,
        "torch_num_threads": torch.get_num_threads(),
        "host": socket.gethostname(), "platform": platform.platform(),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "slurm_array_job_id": os.environ.get("SLURM_ARRAY_JOB_ID"),
        "slurm_array_task_id": os.environ.get("SLURM_ARRAY_TASK_ID"),
        "device_name": torch.cuda.get_device_name() if torch.cuda.is_available() else "cpu",
    }
    metadata_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return record


def finish_run(output):
    output = Path(output)
    files = [p for p in output.iterdir() if p.is_file() and p.name != "checksums.json"]
    values = {p.name: file_sha256(p) for p in sorted(files) if p.suffix != ".tmp"}
    (output / "checksums.json").write_text(json.dumps(values, indent=2, sort_keys=True) + "\n")
