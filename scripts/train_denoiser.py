#!/usr/bin/env python3
"""Pretrain the shared gamma/delta encoder-decoder with sequence denoising."""

from __future__ import annotations

import argparse
import csv
import math
import random
import sys
import time
from pathlib import Path

import torch
from torch.utils.data import DataLoader, Dataset

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gdtcr.model import make_batch
from gdtcr.provenance import begin_run, finish_run
from gdtcr.training import (add_model_arguments, autocast_context, denoising_metrics,
                            log_metrics, make_model, model_config, restore_training_state,
                            save_checkpoint, set_seed, token_loss, warmup_cosine_lr, write_json)


class RandomSequenceDataset(Dataset):
    def __init__(self, rows, length, sampling):
        self.length = length
        groups = {chain: [row for row in rows if row[0] == chain]
                  for chain in ("gamma", "delta")}
        if sampling in ("gamma", "delta"):
            if not groups[sampling]:
                raise ValueError(f"No {sampling} training sequences")
            weights = {"gamma": float(sampling == "gamma"), "delta": float(sampling == "delta")}
        elif any(not group for group in groups.values()):
            raise ValueError("Mixed pretraining requires both chain types")
        elif sampling == "balanced":
            weights = {"gamma": 0.5, "delta": 0.5}
        elif sampling == "raw":
            total = sum(map(len, groups.values()))
            weights = {chain: len(group) / total for chain, group in groups.items()}
        elif sampling == "sqrt":
            roots = {chain: math.sqrt(len(group)) for chain, group in groups.items()}
            total = sum(roots.values())
            weights = {chain: value / total for chain, value in roots.items()}
        else:
            raise ValueError(f"Unknown chain sampling: {sampling}")
        self.groups = groups
        self.gamma_probability = weights["gamma"]

    def __len__(self):
        return self.length

    def __getitem__(self, _):
        chain = "gamma" if random.random() < self.gamma_probability else "delta"
        return random.choice(self.groups[chain])


def read_sequences(path):
    with path.open(encoding="ascii", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        rows = [(row["chain"], row["sequence"]) for row in reader]
    if not rows:
        raise ValueError(f"No sequences in {path}")
    return rows


def collate(rows):
    return make_batch(rows, "cpu", corrupt=True)


def evaluate(model, rows, device, args):
    groups = {chain: [row for row in rows if row[0] == chain]
              for chain in ("gamma", "delta")}
    per_chain = max(1, args.validation_sequences // 2)
    chosen = []
    for chain in ("gamma", "delta"):
        candidates = groups[chain]
        random.Random(args.seed + (0 if chain == "gamma" else 1)).shuffle(candidates)
        chosen.extend(candidates[:per_chain])
    return denoising_metrics(model, chosen, device, args.batch_size)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", type=Path, default=ROOT / "data/splits/pretrain/train.tsv")
    parser.add_argument("--validation", type=Path, nargs="+", default=[
        ROOT / "data/splits/pretrain/gamma_validation.tsv",
        ROOT / "data/splits/pretrain/delta_validation.tsv"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--seed", type=int, default=3407)
    parser.add_argument("--sampling", choices=("sqrt", "raw", "balanced", "gamma", "delta"), default="sqrt")
    parser.add_argument("--steps", type=int, default=20000)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--warmup-steps", type=int, default=500)
    parser.add_argument("--validation-interval", type=int, default=500)
    parser.add_argument("--checkpoint-interval", type=int, default=1000)
    parser.add_argument("--compact-checkpoints", action="store_true",
                        help="Keep resumable last.pt without duplicate step/final checkpoints")
    parser.add_argument("--validation-sequences", type=int, default=2048)
    parser.add_argument("--num-workers", type=int, default=4)
    add_model_arguments(parser)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but no GPU is visible; submit through Slurm")
    set_seed(args.seed)
    device = torch.device(args.device)
    begin_run(args.output, args, [args.train, *args.validation])
    train_rows = read_sequences(args.train)
    validation_rows = [row for path in args.validation for row in read_sequences(path)]
    dataset = RandomSequenceDataset(train_rows, args.steps * args.batch_size, args.sampling)
    loader_generator = torch.Generator().manual_seed(args.seed)
    loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=False,
                        num_workers=args.num_workers, collate_fn=collate,
                        pin_memory=device.type == "cuda", persistent_workers=args.num_workers > 0,
                        generator=loader_generator)

    config = model_config(args)
    model = make_model(config, device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate,
                                  weight_decay=args.weight_decay,
                                  fused=device.type == "cuda")
    start_step = 0
    checkpoint_path = args.output / "last.pt"
    if args.resume and checkpoint_path.exists():
        state = restore_training_state(checkpoint_path, model, optimizer, device)
        start_step = int(state["step"])

    write_json(args.output / "run.json", {
        "arguments": vars(args), "model_config": config,
        "train_rows": len(train_rows), "validation_rows": len(validation_rows),
        "chain_sampling": args.sampling,
        "chain_sampling_probability_gamma": dataset.gamma_probability,
        "torch_version": torch.__version__, "device": str(device),
        "device_name": torch.cuda.get_device_name(device) if device.type == "cuda" else "cpu",
        "parameter_count": sum(parameter.numel() for parameter in model.parameters()),
    })
    log_path = args.output / "metrics.jsonl"
    mode = "a" if start_step else "w"
    model.train()
    started = time.time()
    last_report = started
    tokens_since_report = 0
    chain_sequences = {"gamma": 0, "delta": 0}
    chain_target_tokens = {"gamma": 0, "delta": 0}
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
    step = start_step
    for batch in loader:
        if step >= args.steps:
            break
        step += 1
        lr = warmup_cosine_lr(step, args.steps, args.learning_rate, args.warmup_steps)
        for group in optimizer.param_groups:
            group["lr"] = lr
        tokens_this_batch = int(batch["labels"].ne(-100).sum().item())
        for chain, token in (("gamma", 4), ("delta", 5)):
            selected = batch["source"][:, 0].eq(token)
            chain_sequences[chain] += int(selected.sum().item())
            chain_target_tokens[chain] += int(batch["labels"][selected].ne(-100).sum().item())
        batch = {key: value.to(device, non_blocking=True)
                 for key, value in batch.items() if isinstance(value, torch.Tensor)}
        optimizer.zero_grad(set_to_none=True)
        with autocast_context(device):
            logits = model(batch["source"], batch["decoder"])
            loss = token_loss(logits, batch["labels"])
        tokens_since_report += tokens_this_batch
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        if step == 1 or step % 50 == 0:
            if device.type == "cuda":
                torch.cuda.synchronize(device)
            now = time.time()
            record = {
                "step": step,
                "train_token_nll": loss.item(),
                "learning_rate": lr,
                "elapsed_seconds": now - started,
                "interval_tokens_per_second": tokens_since_report / max(now - last_report, 1e-8),
            }
            if device.type == "cuda":
                record["peak_memory_allocated_gib"] = torch.cuda.max_memory_allocated(device) / 2**30
                record["peak_memory_reserved_gib"] = torch.cuda.max_memory_reserved(device) / 2**30
            log_metrics(log_path, record, mode)
            mode = "a"
            last_report = now
            tokens_since_report = 0
        if step % args.validation_interval == 0 or step == args.steps:
            metrics = evaluate(model, validation_rows, device, args)
            record = {"step": step, "validation": metrics,
                      "elapsed_seconds": time.time() - started}
            log_metrics(log_path, record)
            model.train()
            state = {"step": step, "best_validation_nll": metrics["token_nll"]}
            save_checkpoint(checkpoint_path, model, optimizer, config, state, args)
            if not args.compact_checkpoints and (step % args.checkpoint_interval == 0 or step == args.steps):
                save_checkpoint(args.output / f"step_{step}.pt", model, optimizer,
                                config, state, args)
    final = {"steps_completed": step, "elapsed_seconds": time.time() - started,
             "last_validation": evaluate(model, validation_rows, device, args),
             "chain_sequences_this_invocation": chain_sequences,
             "chain_target_tokens_this_invocation": chain_target_tokens}
    if device.type == "cuda":
        final["peak_memory_allocated_gib"] = torch.cuda.max_memory_allocated(device) / 2**30
        final["peak_memory_reserved_gib"] = torch.cuda.max_memory_reserved(device) / 2**30
    write_json(args.output / "summary.json", final)
    if not args.compact_checkpoints:
        save_checkpoint(args.output / "final.pt", model, optimizer, config,
                        {"step": step, "summary": final}, args)
    finish_run(args.output)
    print(final, flush=True)


if __name__ == "__main__":
    main()
