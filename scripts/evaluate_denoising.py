#!/usr/bin/env python3
"""Evaluate chain-specific denoising and an aligned pure-copy control."""

import argparse
import json
import random
import sys
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gdtcr.fileio import file_sha256
from gdtcr.provenance import source_hashes
from gdtcr.training import denoising_metrics, load_checkpoint, set_seed, write_json
from train_denoiser import read_sequences


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--validation", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--seed", type=int, default=3407)
    parser.add_argument("--per-chain", type=int, default=1024)
    parser.add_argument("--batch-size", type=int, default=256)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    set_seed(args.seed)
    device = torch.device(args.device)
    model, _ = load_checkpoint(args.checkpoint, device)
    rows = [r for path in args.validation for r in read_sequences(path)]
    result = {"checkpoint": str(args.checkpoint), "checkpoint_sha256": file_sha256(args.checkpoint),
              "validation_sha256": {str(p): file_sha256(p) for p in args.validation},
              "source_sha256": source_hashes(ROOT), "seed": args.seed, "chains": {}}
    for offset, chain in enumerate(("gamma", "delta")):
        chosen = [r for r in rows if r[0] == chain]
        random.Random(args.seed + offset).shuffle(chosen)
        chosen = chosen[:args.per_chain]
        result["chains"][chain] = denoising_metrics(model, chosen, device, args.batch_size,
                                                   seed=9107 + offset * 10000)
    write_json(args.output, result)
    print(json.dumps({"output": str(args.output), "chains": result["chains"]}), flush=True)


if __name__ == "__main__":
    main()
