#!/usr/bin/env python3
"""Train a target-chain-only autoregressive baseline.

The encoder receives only a constant source chain token and learns the target sequence
distribution.  It is first trained on the corresponding held-out single-chain
pretraining pool, then continued on target sequences from paired training
edges.  The constant one-token source keeps the decoder architecture identical
to the conditional generator while removing query information.
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
import time
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gdtcr.data import read_pairs
from gdtcr.model import make_batch
from gdtcr.training import (add_model_arguments, autocast_context, corpus_token_nll,
                            load_checkpoint, make_model, model_config, save_checkpoint,
                            set_seed, token_loss, warmup_cosine_lr, write_json)


def read_chain_sequences(path: Path, chain: str) -> list[str]:
    with path.open(encoding="ascii", newline="") as handle:
        rows = csv.DictReader(handle, delimiter="\t")
        result = [row["sequence"] for row in rows if row["chain"] == chain]
    if not result:
        raise ValueError(f"No {chain} sequences found in {path}")
    return result


def pair_targets(path: Path, target_chain: str) -> list[str]:
    """Select the requested target column from gamma<TAB>delta pairs."""
    pairs = read_pairs(path)
    if target_chain == "delta":
        return [delta for _, delta in pairs]
    if target_chain == "gamma":
        return [gamma for gamma, _ in pairs]
    raise ValueError(f"Unknown target chain: {target_chain}")


def load_pretrained_model(path: Path, target_chain: str, device):
    model, checkpoint = load_checkpoint(path, device)
    if checkpoint["arguments"].get("target_chain") != target_chain:
        raise ValueError("Pretraining checkpoint target chain does not match --target-chain")
    if checkpoint["training_state"].get("stage") != "pretrain":
        raise ValueError("--pretrain-checkpoint must contain a pretraining state")
    return model, checkpoint


def make_rows(source_chain: str, target_chain: str, sequences: list[str]):
    source = [(source_chain, "") for _ in sequences]
    target = [(target_chain, sequence) for sequence in sequences]
    return source, target


def validation_nll(model, source_chain: str, target_chain: str, sequences: list[str],
                   device, batch_size: int) -> float:
    source, target = make_rows(source_chain, target_chain, sequences)
    return corpus_token_nll(model, source, target, device, batch_size)


def train_stage(model, source_chain: str, target_chain: str,
                training_sequences: list[str], validation_sequences: list[str],
                stage: str, steps: int, batch_size: int, learning_rate: float,
                warmup_steps: int, validation_interval: int, patience: int,
                output: Path, config: dict, args, device, seed: int):
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=0.01,
                                  fused=device.type == "cuda")
    rng = random.Random(seed)
    best_nll = float("inf")
    stale = 0
    started = time.time()
    model.train()
    for step in range(1, steps + 1):
        lr = warmup_cosine_lr(step, steps, learning_rate, warmup_steps)
        for group in optimizer.param_groups:
            group["lr"] = lr
        chunk = [rng.choice(training_sequences) for _ in range(batch_size)]
        source, target = make_rows(source_chain, target_chain, chunk)
        batch = make_batch(source, device, conditional_rows=target)
        optimizer.zero_grad(set_to_none=True)
        with autocast_context(device):
            loss = token_loss(model(batch["source"], batch["decoder"]), batch["labels"])
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        if step % validation_interval == 0 or step == steps:
            score = validation_nll(model, source_chain, target_chain, validation_sequences,
                                   device, batch_size)
            record = {"stage": stage, "step": step, "validation_token_nll": score,
                      "train_token_nll": loss.item(), "learning_rate": lr,
                      "elapsed_seconds": time.time() - started}
            print(record, flush=True)
            state = {"stage": stage, "step": step, "validation_token_nll": score,
                     "best_validation_nll": min(best_nll, score),
                     "validations_without_improvement": stale}
            save_checkpoint(output / f"{stage}_last.pt", model, optimizer, config, state, args)
            if score < best_nll:
                best_nll = score
                stale = 0
                state["best_validation_nll"] = best_nll
                save_checkpoint(output / f"{stage}_best.pt", model, optimizer, config, state, args)
            else:
                stale += 1
            model.train()
            if patience > 0 and stale >= patience:
                print({"stage": stage, "early_stopping": True, "step": step,
                       "best_validation_nll": best_nll}, flush=True)
                break
    return {"stage": stage, "steps_completed": step, "best_validation_nll": best_nll,
            "final_validation_nll": validation_nll(model, source_chain, target_chain,
                                                    validation_sequences, device, batch_size),
            "elapsed_seconds": time.time() - started}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pretrain", type=Path, required=True)
    parser.add_argument("--pretrain-validation", type=Path, required=True)
    parser.add_argument("--pretrain-checkpoint", type=Path,
                        help="Reuse a target-only pretraining checkpoint and run only fine-tuning")
    parser.add_argument("--train-pairs", type=Path, required=True)
    parser.add_argument("--validation-pairs", type=Path, required=True)
    parser.add_argument("--target-chain", choices=("gamma", "delta"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--seed", type=int, default=3407)
    parser.add_argument("--pretrain-steps", type=int, default=20000)
    parser.add_argument("--finetune-steps", type=int, default=1500)
    parser.add_argument("--batch-size", type=int,
                        help="Fallback batch size for both stages")
    parser.add_argument("--pretrain-batch-size", type=int)
    parser.add_argument("--finetune-batch-size", type=int)
    parser.add_argument("--pretrain-learning-rate", type=float, default=3e-4)
    parser.add_argument("--finetune-learning-rate", type=float, default=2e-5)
    parser.add_argument("--warmup-steps", type=int, default=200)
    parser.add_argument("--validation-interval", type=int, default=500)
    parser.add_argument("--pretrain-patience", type=int, default=0,
                        help="Early-stopping patience for target-only pretraining; 0 disables it")
    parser.add_argument("--finetune-patience", type=int, default=5)
    add_model_arguments(parser)
    args = parser.parse_args()
    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but no GPU is visible; submit through Slurm")
    if args.pretrain_steps < 1 or args.finetune_steps < 1:
        raise ValueError("training steps must be positive")
    default_batch = args.batch_size or 256
    pretrain_batch_size = args.pretrain_batch_size or default_batch
    finetune_batch_size = args.finetune_batch_size or default_batch
    if pretrain_batch_size < 1 or finetune_batch_size < 1:
        raise ValueError("batch sizes must be positive")
    set_seed(args.seed)
    device = torch.device(args.device)
    args.output.mkdir(parents=True, exist_ok=True)
    pretrain_sequences = read_chain_sequences(args.pretrain, args.target_chain)
    pretrain_validation = read_chain_sequences(args.pretrain_validation, args.target_chain)
    train_targets = pair_targets(args.train_pairs, args.target_chain)
    validation_targets = pair_targets(args.validation_pairs, args.target_chain)
    source_chain = "delta" if args.target_chain == "gamma" else "gamma"
    if args.pretrain_checkpoint:
        model, checkpoint = load_pretrained_model(args.pretrain_checkpoint, args.target_chain, device)
        config = checkpoint["model_config"]
    else:
        config = model_config(args)
        model = make_model(config, device)
    write_json(args.output / "run.json", {
        "arguments": vars(args), "model_config": config, "target_chain": args.target_chain,
        "pretrain_sequences": len(pretrain_sequences),
        "pretrain_validation_sequences": len(pretrain_validation),
        "train_pair_targets": len(train_targets), "validation_pair_targets": len(validation_targets),
        "source_chain": source_chain, "paired_target_column": args.target_chain,
        "finetune_sampling": "uniform paired training edges, target column only",
        "pretrain_batch_size": pretrain_batch_size,
        "finetune_batch_size": finetune_batch_size,
        "parameter_count": sum(parameter.numel() for parameter in model.parameters()),
        "torch_version": torch.__version__, "device": str(device),
        "device_name": torch.cuda.get_device_name(device) if device.type == "cuda" else "cpu",
    })
    if args.pretrain_checkpoint:
        pretrain_summary = {
            "stage": "pretrain", "steps_completed": 0,
            "reused_checkpoint": str(args.pretrain_checkpoint),
            "checkpoint_step": checkpoint["training_state"]["step"],
            "best_validation_nll": checkpoint["training_state"]["validation_token_nll"],
        }
    else:
        pretrain_summary = train_stage(
            model, source_chain, args.target_chain, pretrain_sequences, pretrain_validation, "pretrain",
            args.pretrain_steps, pretrain_batch_size, args.pretrain_learning_rate,
            args.warmup_steps, args.validation_interval, args.pretrain_patience,
            args.output, config, args, device, args.seed)
        # Fine-tuning always starts from the validation-best pretraining state.
        model, _ = load_pretrained_model(args.output / "pretrain_best.pt", args.target_chain, device)
    finetune_summary = train_stage(
        model, source_chain, args.target_chain, train_targets, validation_targets, "finetune",
        args.finetune_steps, finetune_batch_size, args.finetune_learning_rate,
        min(args.warmup_steps, args.finetune_steps),
        max(1, min(args.validation_interval, args.finetune_steps)), args.finetune_patience,
        args.output, config, args, device, args.seed + 17)
    # The final checkpoint is the best finetuning state, which is the artifact
    # used by the shared evaluator with --source-mode constant.
    best_path = args.output / "finetune_best.pt"
    best_payload = torch.load(best_path, map_location=device, weights_only=False)
    torch.save(best_payload, args.output / "best.pt")
    write_json(args.output / "summary.json", {"pretrain": pretrain_summary,
                                               "finetune": finetune_summary,
                                               "best_checkpoint": str(args.output / "best.pt")})
    print({"pretrain": pretrain_summary, "finetune": finetune_summary}, flush=True)


if __name__ == "__main__":
    main()
