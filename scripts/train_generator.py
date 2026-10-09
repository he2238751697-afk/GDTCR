#!/usr/bin/env python3
"""Bidirectional conditional CDR3 fine-tuning after single-chain pretraining."""

from __future__ import annotations

import argparse
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

import torch
from torch.utils.data import DataLoader, Dataset

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gdtcr.data import read_pairs
from gdtcr.model import make_batch
from gdtcr.provenance import begin_run, finish_run
from gdtcr.training import (add_model_arguments, autocast_context, corpus_token_nll,
                            load_checkpoint, log_metrics, make_model, model_config,
                            restore_training_state, save_checkpoint, set_seed, token_loss,
                            warmup_cosine_lr, write_json, sequence_mean_nll)


class PairDataset(Dataset):
    def __init__(self, pairs, steps, batch_size, direction="both", source_mode="paired", sampling="input"):
        if source_mode not in ("paired", "constant"):
            raise ValueError("source_mode must be paired or constant")
        self.source_mode = source_mode
        if sampling not in ("input", "edge"):
            raise ValueError("sampling must be input or edge")
        self.sampling, self.pairs = sampling, tuple(pairs)
        groups = {"gamma": {}, "delta": {}}
        for gamma, delta in pairs:
            if direction in ("both", "gamma_to_delta"):
                groups["gamma"].setdefault(gamma, []).append(delta)
            if direction in ("both", "delta_to_gamma"):
                groups["delta"].setdefault(delta, []).append(gamma)
        chains = [chain for chain in ("gamma", "delta") if groups[chain]]
        if not chains:
            raise ValueError("No pair directions available")
        self.groups = {chain: {sequence: tuple(targets)
                               for sequence, targets in values.items()}
                       for chain, values in groups.items()}
        self.inputs = {chain: tuple(values) for chain, values in groups.items()}
        self.chains = chains
        self.steps = steps
        self.batch_size = batch_size

    def __len__(self):
        return self.steps * self.batch_size

    def __getitem__(self, _):
        source_chain = random.choice(self.chains)
        if self.sampling == "edge":
            gamma, delta = random.choice(self.pairs)
            source_sequence, target_sequence = (gamma, delta) if source_chain == "gamma" else (delta, gamma)
        else:
            source_sequence = random.choice(self.inputs[source_chain])
            target_sequence = random.choice(self.groups[source_chain][source_sequence])
        target_chain = "delta" if source_chain == "gamma" else "gamma"
        if self.source_mode == "constant":
            source_sequence = ""
        return source_chain, source_sequence, target_chain, target_sequence


def collate(rows):
    source_rows = [(row[0], row[1]) for row in rows]
    target_rows = [(row[2], row[3]) for row in rows]
    return make_batch(source_rows, "cpu", conditional_rows=target_rows)


def conditional_loss(model, rows, device, batch_size):
    sources = [(row[0], row[1]) for row in rows]
    targets = [(row[2], row[3]) for row in rows]
    return corpus_token_nll(model, sources, targets, device, batch_size)


def query_validation_metrics(model, rows, device, batch_size, source_mode="paired"):
    """Average partners within input, then inputs within direction, then directions."""
    sources = [(row[0], "" if source_mode == "constant" else row[1]) for row in rows]
    targets = [(row[2], row[3]) for row in rows]
    values = sequence_mean_nll(model, sources, targets, device, batch_size)
    groups = defaultdict(lambda: defaultdict(list))
    weighted, tokens = 0.0, 0
    for row, value in zip(rows, values):
        groups[row[0]][row[1]].append(value)
        count = len(row[3]) + 1
        weighted += value * count
        tokens += count
    directional = {chain: sum(sum(v) / len(v) for v in queries.values()) / len(queries)
                   for chain, queries in groups.items()}
    return {"selection_nll": sum(directional.values()) / len(directional),
            "token_nll": weighted / tokens, "direction_query_nll": directional,
            "queries": {chain: len(queries) for chain, queries in groups.items()}}


def read_directional_rows(path, direction, source_mode="paired"):
    pairs = read_pairs(path)
    if source_mode == "constant":
        rows = []
        if direction in ("both", "gamma_to_delta"):
            rows.extend(("gamma", "", "delta", delta) for _, delta in pairs)
        if direction in ("both", "delta_to_gamma"):
            rows.extend(("delta", "", "gamma", gamma) for gamma, _ in pairs)
        return rows
    if direction == "gamma_to_delta":
        return [("gamma", gamma, "delta", delta) for gamma, delta in pairs]
    if direction == "delta_to_gamma":
        return [("delta", delta, "gamma", gamma) for gamma, delta in pairs]
    return [("gamma", gamma, "delta", delta) for gamma, delta in pairs] + [
        ("delta", delta, "gamma", gamma) for gamma, delta in pairs]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--init", type=Path, help="Pretrained checkpoint; omit for random initialization")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--seed", type=int, default=3407)
    parser.add_argument("--direction", choices=("both", "gamma_to_delta", "delta_to_gamma"), default="both")
    parser.add_argument("--source-mode", choices=("paired", "constant"), default="paired",
                        help="Constant mode removes source residues while retaining identical target sampling")
    parser.add_argument("--sampling", choices=("input", "edge"), default="input")
    parser.add_argument("--validation-objective", choices=("token_nll", "direction_query_nll"), default="token_nll")
    parser.add_argument("--steps", type=int, default=6000)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--warmup-steps", type=int, default=200)
    parser.add_argument("--validation-interval", type=int, default=250)
    parser.add_argument("--checkpoint-interval", type=int, default=1000)
    parser.add_argument("--compact-checkpoints", action="store_true")
    parser.add_argument("--early-stopping-patience", type=int, default=5,
                        help="Number of validation checks without improvement; 0 disables early stopping")
    parser.add_argument("--min-delta", type=float, default=0.0,
                        help="Minimum validation NLL decrease counted as an improvement")
    parser.add_argument("--num-workers", type=int, default=2)
    add_model_arguments(parser)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but no GPU is visible; submit through Slurm")
    set_seed(args.seed)
    device = torch.device(args.device)
    begin_run(args.output, args, [args.train, args.validation, args.init])
    train_pairs = read_pairs(args.train)
    validation_rows = read_directional_rows(args.validation, args.direction, args.source_mode)
    validation_queries = read_directional_rows(args.validation, args.direction, "paired")
    def validate():
        if args.validation_objective == "direction_query_nll":
            return query_validation_metrics(model, validation_queries, device, args.batch_size, args.source_mode)
        score = conditional_loss(model, validation_rows, device, args.batch_size)
        return {"selection_nll": score, "token_nll": score}
    if args.init:
        model, checkpoint = load_checkpoint(args.init, device)
        config = checkpoint["model_config"]
    else:
        config = model_config(args)
        model = make_model(config, device)
    dataset = PairDataset(train_pairs, args.steps, args.batch_size, args.direction, args.source_mode, args.sampling)
    loader_generator = torch.Generator().manual_seed(args.seed)
    loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=False,
                        num_workers=args.num_workers, collate_fn=collate,
                        pin_memory=device.type == "cuda", persistent_workers=args.num_workers > 0,
                        generator=loader_generator)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate,
                                  weight_decay=args.weight_decay,
                                  fused=device.type == "cuda")
    start_step = 0
    checkpoint_path = args.output / "last.pt"
    best_path = args.output / "best.pt"
    training_state = {}
    if args.resume and checkpoint_path.exists():
        training_state = restore_training_state(checkpoint_path, model, optimizer, device)
        start_step = int(training_state["step"])
    best_validation_nll = float(training_state.get("best_validation_nll", float("inf")))
    validations_without_improvement = int(training_state.get("validations_without_improvement", 0))
    write_json(args.output / "run.json", {
        "arguments": vars(args), "model_config": config,
        "train_pairs": len(train_pairs), "validation_rows": len(validation_rows),
        "parameter_count": sum(p.numel() for p in model.parameters()),
        "torch_version": torch.__version__, "device": str(device),
        "device_name": torch.cuda.get_device_name(device) if device.type == "cuda" else "cpu",
    })
    log_path = args.output / "metrics.jsonl"
    log_mode = "a" if start_step else "w"
    model.train()
    step, started = start_step, time.time()
    last_report = started
    tokens_since_report = 0
    direction_sequences = {"gamma_to_delta": 0, "delta_to_gamma": 0}
    direction_tokens = dict.fromkeys(direction_sequences, 0)
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
    for batch in loader:
        if step >= args.steps:
            break
        step += 1
        lr = warmup_cosine_lr(step, args.steps, args.learning_rate, args.warmup_steps)
        for group in optimizer.param_groups:
            group["lr"] = lr
        tokens_this_batch = int(batch["labels"].ne(-100).sum().item())
        for direction, token in (("gamma_to_delta", 4), ("delta_to_gamma", 5)):
            selected = batch["source"][:, 0].eq(token)
            direction_sequences[direction] += int(selected.sum().item())
            direction_tokens[direction] += int(batch["labels"][selected].ne(-100).sum().item())
        batch = {key: value.to(device, non_blocking=True)
                 for key, value in batch.items() if isinstance(value, torch.Tensor)}
        tokens_since_report += tokens_this_batch
        optimizer.zero_grad(set_to_none=True)
        with autocast_context(device):
            logits = model(batch["source"], batch["decoder"])
            loss = token_loss(logits, batch["labels"])
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        if step == 1 or step % 50 == 0:
            if device.type == "cuda":
                torch.cuda.synchronize(device)
            now = time.time()
            record = {"step": step, "train_token_nll": loss.item(), "learning_rate": lr,
                      "elapsed_seconds": now - started,
                      "interval_tokens_per_second": tokens_since_report / max(now - last_report, 1e-8)}
            if device.type == "cuda":
                record["peak_memory_allocated_gib"] = torch.cuda.max_memory_allocated(device) / 2**30
                record["peak_memory_reserved_gib"] = torch.cuda.max_memory_reserved(device) / 2**30
            log_metrics(log_path, record, log_mode)
            log_mode = "a"
            last_report = now
            tokens_since_report = 0
        if step % args.validation_interval == 0 or step == args.steps:
            metrics = validate()
            score = metrics["selection_nll"]
            record = {"step": step, "validation_token_nll": metrics["token_nll"], "validation": metrics,
                      "elapsed_seconds": time.time() - started}
            log_metrics(log_path, record)
            model.train()
            improved = score < best_validation_nll - args.min_delta
            if improved:
                best_validation_nll = score
                validations_without_improvement = 0
            else:
                validations_without_improvement += 1
            state = {"step": step, "validation_token_nll": metrics["token_nll"],
                     "selection_metric": args.validation_objective, "validation": metrics,
                     "best_validation_nll": best_validation_nll,
                     "validations_without_improvement": validations_without_improvement}
            save_checkpoint(checkpoint_path, model, optimizer, config, state, args)
            if improved:
                save_checkpoint(best_path, model, None if args.compact_checkpoints else optimizer, config, state, args)
            if not args.compact_checkpoints and (step % args.checkpoint_interval == 0 or step == args.steps):
                save_checkpoint(args.output / f"step_{step}.pt", model, optimizer,
                                config, state, args)
            if args.early_stopping_patience > 0 and validations_without_improvement >= args.early_stopping_patience:
                print({"early_stopping": True, "step": step,
                       "best_validation_nll": best_validation_nll}, flush=True)
                break
    final_metrics = validate()
    final = {"steps_completed": step, "selection_metric": args.validation_objective,
             "validation_token_nll": final_metrics["token_nll"], "validation": final_metrics,
             "best_validation_nll": best_validation_nll,
             "direction_sequences_this_invocation": direction_sequences,
             "direction_target_tokens_this_invocation": direction_tokens,
             "elapsed_seconds": time.time() - started}
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
