#!/usr/bin/env python3
"""Recover missing original pretraining metadata from surviving logs/checkpoints."""

import ast
import hashlib
import json
import re
import sys
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gdtcr.fileio import file_sha256
from gdtcr.training import write_json


def recover(root):
    recovered = []
    for index in (0, 1):
        folder = root / f"artifacts/runs/pretrain/a800/seed-{index}"
        log = root / f"artifacts/slurm/gdtcr-pretrain-2995691_{index}.out"
        checkpoint_path = folder / "last.pt"
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        records = []
        for line in log.read_text().splitlines():
            if line.startswith("{"):
                try:
                    records.append(ast.literal_eval(line))
                except (ValueError, SyntaxError):
                    pass
        summaries = [r for r in records if "steps_completed" in r and "last_validation" in r]
        if len(summaries) != 1 or summaries[0]["steps_completed"] != checkpoint["training_state"]["step"]:
            raise ValueError(f"Cannot unambiguously reconstruct {folder}")
        note = {"reconstructed": True, "original_job_id": f"2995691_{index}",
                "source_log": str(log.relative_to(root)), "source_log_sha256": file_sha256(log),
                "checkpoint": str(checkpoint_path.relative_to(root)),
                "checkpoint_sha256": file_sha256(checkpoint_path),
                "method": "Original completed-job stdout summary and saved checkpoint arguments; no inferred timing/device metadata"}
        summary = {**summaries[0], "recovery": note}
        git_match = re.search(r"^git=(\S+)", log.read_text(), re.MULTILINE)
        run = {"arguments": checkpoint["arguments"], "model_config": checkpoint["model_config"],
               "torch_version": checkpoint.get("torch_version"), "recovery": note,
               "git_head_from_original_log": git_match.group(1) if git_match else None}
        for name, content in (("run.json", run), ("summary.json", summary)):
            target = folder / name
            if target.exists():
                raise FileExistsError(f"Refuse metadata overwrite: {target}")
            write_json(target, content)
        recovered.append(note)
        del checkpoint
    write_json(root / "artifacts/completion_v2/recovery/pretrain_metadata.json", recovered)
    print(json.dumps(recovered, indent=2))


if __name__ == "__main__":
    recover(Path.cwd())
