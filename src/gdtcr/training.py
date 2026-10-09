"""Shared runtime and checkpoint helpers for Slurm training jobs."""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

import numpy as np
import torch
from torch.nn import functional as F

from .model import ConditionalSeq2Seq, PairRanker, make_batch


DEFAULT_MODEL_CONFIG = {
    "d_model": 256,
    "nhead": 8,
    "encoder_layers": 4,
    "decoder_layers": 4,
    "dim_feedforward": 1024,
    "dropout": 0.1,
    "max_length": 64,
}


def add_model_arguments(parser):
    for name, default in DEFAULT_MODEL_CONFIG.items():
        parser.add_argument("--" + name.replace("_", "-"), type=type(default), default=default)


def warmup_cosine_lr(step, steps, learning_rate, warmup_steps):
    progress = min(1.0, step / max(steps, 1))
    warmup = min(1.0, step / max(warmup_steps, 1))
    return learning_rate * warmup * 0.5 * (1.0 + math.cos(math.pi * progress))


def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True


def model_config(args):
    return {
        "d_model": args.d_model,
        "nhead": args.nhead,
        "encoder_layers": args.encoder_layers,
        "decoder_layers": args.decoder_layers,
        "dim_feedforward": args.dim_feedforward,
        "dropout": args.dropout,
        "max_length": args.max_length,
    }


def make_model(config=None, device="cpu"):
    return ConditionalSeq2Seq(**(config or DEFAULT_MODEL_CONFIG)).to(device)


def load_checkpoint(path, device="cpu"):
    checkpoint = torch.load(path, map_location=device, weights_only=False)
    model = make_model(checkpoint["model_config"], device)
    model.load_state_dict(checkpoint["model_state"])
    return model, checkpoint


def load_ranker(path, device):
    checkpoint = torch.load(path, map_location=device, weights_only=False)
    encoder = make_model(checkpoint["generator_config"], device)
    ranker = PairRanker(encoder, **checkpoint.get("ranker_config", {})).to(device)
    ranker.load_state_dict(checkpoint["ranker_state"])
    ranker.eval()
    return ranker


def restore_training_state(path, model, optimizer, device):
    checkpoint = torch.load(path, map_location=device, weights_only=False)
    model.load_state_dict(checkpoint["model_state"])
    if checkpoint.get("optimizer_state"):
        optimizer.load_state_dict(checkpoint["optimizer_state"])
    return checkpoint["training_state"]


def save_checkpoint(path, model, optimizer, model_config, state, args):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "model_state": model.state_dict(),
        "model_config": model_config,
        "optimizer_state": optimizer.state_dict() if optimizer is not None else None,
        "training_state": state,
        "arguments": vars(args),
        "torch_version": torch.__version__,
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    torch.save(payload, temporary)
    temporary.replace(path)


def write_json(path, values):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(values, indent=2, sort_keys=True, default=str) + "\n")


def log_metrics(path, record, mode="a"):
    with Path(path).open(mode, encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
    print(record, flush=True)


def autocast_context(device):
    if device.type != "cuda":
        return torch.autocast(device_type="cpu", enabled=False)
    return torch.autocast(device_type="cuda", dtype=torch.bfloat16)


def token_loss(logits, labels):
    return F.cross_entropy(logits.reshape(-1, logits.shape[-1]), labels.reshape(-1),
                           ignore_index=-100)


@torch.inference_mode()
def corpus_token_nll(model, sources, targets, device, batch_size):
    """Token-weighted mean NLL, including EOS, for an aligned corpus."""
    model.eval()
    weighted, tokens = 0.0, 0
    for start in range(0, len(sources), batch_size):
        batch = make_batch(sources[start:start + batch_size], device,
                           conditional_rows=targets[start:start + batch_size])
        with autocast_context(device):
            loss = token_loss(model(batch["source"], batch["decoder"]), batch["labels"])
        count = int(batch["labels"].ne(-100).sum().item())
        weighted += loss.item() * count
        tokens += count
    return weighted / max(tokens, 1)


@torch.inference_mode()
def sequence_mean_nll(model, sources, targets, device, batch_size):
    """One mean target-token NLL per sequence, including EOS, in input order."""
    model.eval()
    scores = []
    for start in range(0, len(sources), batch_size):
        batch = make_batch(sources[start:start + batch_size], device,
                           conditional_rows=targets[start:start + batch_size])
        with autocast_context(device):
            logits = model(batch["source"], batch["decoder"]).float()
        labels = batch["labels"]
        mask = labels.ne(-100)
        token_nll = -logits.log_softmax(-1).gather(
            2, labels.masked_fill(~mask, 0).unsqueeze(-1)).squeeze(-1)
        scores.extend(((token_nll * mask).sum(1) / mask.sum(1).clamp_min(1)).cpu().tolist())
    return scores


def denoising_metrics(model, rows, device, batch_size=256, seed=9107):
    model.eval()
    losses, damaged_nll, correct, damaged = [], 0.0, 0, 0
    copy_correct, copy_all_correct, residues = 0, 0, 0
    with torch.no_grad():
        for batch_index, start in enumerate(range(0, len(rows), batch_size)):
            batch_rows = rows[start:start + batch_size]
            batch = make_batch(batch_rows, device, corrupt=True,
                               seed=seed + batch_index)
            with autocast_context(device):
                logits = model(batch["source"], batch["decoder"])
                loss = token_loss(logits, batch["labels"])
            losses.append((loss.item(), int(batch["labels"].ne(-100).sum().item())))
            mask = batch["damaged_mask"]
            residue_mask = batch["labels"].ge(6)
            copy_matches = batch["aligned_copy_ids"].eq(batch["labels"])
            copy_correct += int((copy_matches & mask).sum().item())
            copy_all_correct += int((copy_matches & residue_mask).sum().item())
            residues += int(residue_mask.sum().item())
            if mask.any():
                target = batch["labels"]
                indices = mask.nonzero(as_tuple=True)
                target_ids = target[indices[0], indices[1]]
                damaged_nll += F.cross_entropy(
                    logits[mask].float(), target_ids, reduction="sum").item()
                prediction_ids = logits.argmax(dim=-1)[indices]
                correct += int(prediction_ids.eq(target_ids).sum().item())
                damaged += int(mask.sum().item())
    total_tokens = sum(count for _, count in losses)
    mean_loss = sum(loss * count for loss, count in losses) / max(total_tokens, 1)
    return {"token_nll": mean_loss,
            "damaged_token_nll": damaged_nll / max(damaged, 1),
            "damaged_residue_accuracy": correct / max(damaged, 1),
            "aligned_copy_damaged_residue_accuracy": copy_correct / max(damaged, 1),
            "aligned_copy_residue_accuracy": copy_all_correct / max(residues, 1),
            "copy_control": "original-position alignment; mask/deletion is incorrect; no target imputation",
            "n_sequences": len(rows), "n_damaged_residues": damaged}
