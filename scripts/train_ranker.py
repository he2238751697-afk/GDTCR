#!/usr/bin/env python3
"""Train an independent multi-positive gamma-delta pair compatibility scorer."""

from __future__ import annotations

import argparse
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

import torch
from torch.nn import functional as F

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gdtcr.data import read_pairs
from gdtcr.model import PairRanker, multi_positive_loss
from gdtcr.metrics import rank_summary
from gdtcr.negatives import TrainingNegativeSampler
from gdtcr.provenance import begin_run, finish_run
from gdtcr.training import load_checkpoint, log_metrics, set_seed, write_json


def sequence_batches(rows, batch_size):
    for start in range(0, len(rows), batch_size):
        yield rows[start:start + batch_size]


def partner_groups(pairs):
    groups = {"gamma": defaultdict(list), "delta": defaultdict(list)}
    for gamma, delta in pairs:
        groups["gamma"][gamma].append(delta)
        groups["delta"][delta].append(gamma)
    result = {}
    for chain, values in groups.items():
        partners = {sequence: tuple(items) for sequence, items in values.items()}
        result[chain] = (tuple(partners), partners)
    return result


def sample_pair_batch(groups, batch_size, seed):
    rng = random.Random(seed)
    chains = ("gamma", "delta")
    batch = []
    for _ in range(batch_size):
        chain = rng.choice(chains)
        inputs, partners = groups[chain]
        source = rng.choice(inputs)
        target = rng.choice(partners[source])
        batch.append((source, target) if chain == "gamma" else (target, source))
    return batch


def encode_pair_pool(ranker, pairs, batch_size):
    gamma_sequences = sorted({gamma for gamma, _ in pairs})
    delta_sequences = sorted({delta for _, delta in pairs})
    gamma_vectors, delta_vectors = [], []
    for chunk in sequence_batches(gamma_sequences, batch_size):
        gamma_vectors.append(ranker.encode_sequences("gamma", chunk))
    for chunk in sequence_batches(delta_sequences, batch_size):
        delta_vectors.append(ranker.encode_sequences("delta", chunk))
    return (gamma_sequences, delta_sequences, torch.cat(gamma_vectors), torch.cat(delta_vectors))


def ranking_metrics(ranker, pairs, batch_size, direction="both", known_pairs=None):
    ranker.eval()
    with torch.no_grad():
        gammas, deltas, gamma_vectors, delta_vectors = encode_pair_pool(ranker, pairs, batch_size)
        matrix = ranker.score_matrix(gamma_vectors, delta_vectors).cpu()
        directions = {}
        for name, queries, targets, scores, column in (
                ("gamma_to_delta", gammas, deltas, matrix, 0),
                ("delta_to_gamma", deltas, gammas, matrix.T, 1)):
            if direction != "both" and name != direction:
                continue
            positives = defaultdict(set)
            for pair in pairs:
                positives[pair[column]].add(pair[1 - column])
            rows = []
            for index, query in enumerate(queries):
                selected = [j for j, target in enumerate(targets)
                            if target in positives[query] or known_pairs is None or
                            ((query, target) if column == 0 else (target, query)) not in known_pairs]
                rows.append(rank_summary([targets[j] for j in selected], positives[query],
                                         scores[index, selected].tolist(), True))
            keys = ("mrr", "hit_at_1", "hit_at_5", "hit_at_10", "recall_at_1", "recall_at_5",
                    "recall_at_10", "mean_positive_rank")
            directions[name] = {key: sum(r[key] for r in rows) / len(rows) for key in keys}
            directions[name]["n_queries"] = len(rows)
        return {"mrr": sum(r["mrr"] for r in directions.values()) / len(directions),
                "directions": directions, "selection_direction": direction,
                "n_pairs": len(pairs), "n_gamma": len(gammas), "n_delta": len(deltas)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--validation-known-pairs", type=Path,
                        help="Observed pairs used ONLY to exclude known alternative partners in validation scoring")
    parser.add_argument("--init", type=Path, required=True,
                        help="Frozen generator checkpoint used to initialize the encoder")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--seed", type=int, default=3407)
    parser.add_argument("--steps", type=int, default=3000)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--embedding-batch-size", type=int, default=256)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--validation-interval", type=int, default=250)
    parser.add_argument("--early-stopping-patience", type=int, default=8,
                        help="Number of validation checks without MRR improvement; 0 disables early stopping")
    parser.add_argument("--freeze-encoder", action="store_true")
    parser.add_argument("--ranker-version", type=int, choices=(1, 2), default=1)
    parser.add_argument("--validation-direction", choices=("both", "gamma_to_delta", "delta_to_gamma"), default="both")
    parser.add_argument("--negative-mode", choices=("inbatch", "random", "mixed"), default="inbatch")
    parser.add_argument("--negative-ratio", type=int, choices=(1, 3, 5), default=3)
    parser.add_argument("--contrastive-steps", type=int, default=1500)
    parser.add_argument("--compact-checkpoints", action="store_true")
    args = parser.parse_args()
    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but no GPU is visible; submit through Slurm")
    set_seed(args.seed)
    device = torch.device(args.device)
    begin_run(args.output, args, [args.train, args.validation, args.init, args.validation_known_pairs])
    train_pairs, validation_pairs = read_pairs(args.train), read_pairs(args.validation)
    validation_known_pairs = set(read_pairs(args.validation_known_pairs)) if args.validation_known_pairs else None
    if validation_known_pairs is not None and not set(validation_pairs) <= validation_known_pairs:
        raise ValueError("Validation contains pairs absent from the observed-pair exclusion table")
    train_groups = partner_groups(train_pairs)
    known_pairs = set(train_pairs)
    encoder, checkpoint = load_checkpoint(args.init, device)
    ranker = PairRanker(encoder, version=args.ranker_version).to(device)
    negative_sampler = (TrainingNegativeSampler(train_pairs, args.negative_mode)
                        if args.negative_mode != "inbatch" else None)
    if args.freeze_encoder:
        for parameter in ranker.encoder.parameters():
            parameter.requires_grad_(False)
    optimizer = torch.optim.AdamW((parameter for parameter in ranker.parameters()
                                   if parameter.requires_grad), lr=args.learning_rate,
                                  weight_decay=args.weight_decay,
                                  fused=device.type == "cuda")
    write_json(args.output / "run.json", {
        "arguments": vars(args), "generator_checkpoint": str(args.init), "ranker_config": ranker.config,
        "train_pairs": len(train_pairs), "validation_pairs": len(validation_pairs),
        "parameter_count": sum(p.numel() for p in ranker.parameters()),
        "trainable_parameter_count": sum(p.numel() for p in ranker.parameters() if p.requires_grad),
        "torch_version": torch.__version__, "device": str(device),
        "device_name": torch.cuda.get_device_name(device) if device.type == "cuda" else "cpu",
    })
    log_path = args.output / "metrics.jsonl"
    best_path = args.output / "best.pt"
    best_mrr = float("-inf")
    best_step = None
    validations_without_improvement = 0
    started = time.time()
    for step in range(1, args.steps + 1):
        ranker.train()
        batch = sample_pair_batch(train_groups, args.batch_size, args.seed + step)
        explicit_stage = negative_sampler is not None and step > args.contrastive_steps
        negative_pairs = negative_sampler.sample(batch, args.negative_ratio, args.seed + 100000 + step) if explicit_stage else []
        if explicit_stage and not negative_pairs:
            raise ValueError("No eligible unrecorded combinations for BCE stage")
        gamma_sequences, delta_sequences, gamma_vectors, delta_vectors = encode_pair_pool(
            ranker, batch + negative_pairs, args.embedding_batch_size)
        if explicit_stage:
            gamma_lookup = {s: i for i, s in enumerate(gamma_sequences)}
            delta_lookup = {s: i for i, s in enumerate(delta_sequences)}
            aligned = batch + negative_pairs
            gamma_index = torch.tensor([gamma_lookup[g] for g, _ in aligned], device=device)
            delta_index = torch.tensor([delta_lookup[d] for _, d in aligned], device=device)
            scores = ranker.score_pairs(gamma_vectors[gamma_index], delta_vectors[delta_index])
            # Balance positive and negative class weight; ratios change negative diversity.
            loss = .5 * (F.softplus(-scores[:len(batch)]).mean() + F.softplus(scores[len(batch):]).mean())
        else:
            scores = ranker.score_matrix(gamma_vectors, delta_vectors)
            positive = torch.tensor([[(gamma, delta) in known_pairs for delta in delta_sequences]
                                     for gamma in gamma_sequences], device=device, dtype=torch.bool)
            loss = multi_positive_loss(scores, positive)
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(ranker.parameters(), 1.0)
        optimizer.step()
        if step == 1 or step % 50 == 0:
            record = {"step": step, "train_loss": loss.item(), "stage": "bce" if explicit_stage else "contrastive",
                      "elapsed_seconds": time.time() - started}
            log_metrics(log_path, record)
        if step % args.validation_interval == 0 or step == args.steps:
            metrics = ranking_metrics(ranker, validation_pairs, args.embedding_batch_size,
                                      args.validation_direction, validation_known_pairs)
            record = {"step": step, "validation": metrics,
                      "elapsed_seconds": time.time() - started}
            log_metrics(log_path, record)
            state = {"ranker_state": ranker.state_dict(),
                     "generator_config": checkpoint["model_config"],
                     "ranker_config": ranker.config, "training_stage": "bce" if explicit_stage else "contrastive",
                     "step": step, "arguments": vars(args)}
            torch.save(state, args.output / "last.pt")
            current_mrr = float(metrics["mrr"])
            eligible = explicit_stage or negative_sampler is None or args.contrastive_steps >= args.steps
            if eligible and current_mrr > best_mrr:
                best_mrr = current_mrr
                best_step = step
                validations_without_improvement = 0
                state["validation"] = metrics
                torch.save(state, best_path)
            elif eligible:
                validations_without_improvement += 1
            if args.early_stopping_patience > 0 and validations_without_improvement >= args.early_stopping_patience:
                print({"early_stopping": True, "step": step, "best_mrr": best_mrr}, flush=True)
                break
    steps_completed = step
    final = ranking_metrics(ranker, validation_pairs, args.embedding_batch_size,
                            args.validation_direction, validation_known_pairs)
    write_json(args.output / "summary.json", {"steps_completed": steps_completed, "validation": final,
                                               "best_step": best_step, "best_validation_mrr": best_mrr,
                                               "negative_audit": dict(negative_sampler.stats) if negative_sampler else {},
                                               "elapsed_seconds": time.time() - started})
    if not args.compact_checkpoints:
        torch.save({"ranker_state": ranker.state_dict(), "generator_config": checkpoint["model_config"],
                    "ranker_config": ranker.config,
                    "step": steps_completed, "arguments": vars(args)}, args.output / "final.pt")
    finish_run(args.output)
    print(final, flush=True)


if __name__ == "__main__":
    main()
