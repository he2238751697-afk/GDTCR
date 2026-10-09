#!/usr/bin/env python3
"""Rescore saved candidates without resampling or changing checkpoints.

Corrects the legacy delta-to-gamma ranker argument order.  For free samples,
also adds an explicit length-normalized likelihood ordering; legacy raw
metrics refer to first occurrence in sample order, not likelihood ranking.
Original files are never overwritten.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gdtcr.metrics import rank_summary
from gdtcr.fileio import file_sha256 as sha256

from gdtcr.training import load_checkpoint, load_ranker, sequence_mean_nll, set_seed


@torch.inference_mode()
def encode_cache(ranker, chain, sequences, batch_size):
    sequences = sorted(set(sequences))
    if not sequences:
        return {}
    vectors = []
    for start in range(0, len(sequences), batch_size):
        vectors.append(ranker.encode_sequences(chain, sequences[start:start + batch_size]))
    return dict(zip(sequences, torch.cat(vectors)))


@torch.inference_mode()
def likelihood_scores(model, rows, source_chain, batch_size, device):
    target_chain = "delta" if source_chain == "gamma" else "gamma"
    jobs = [(i, row.get("conditioned_source", row["source"]), candidate)
            for i, row in enumerate(rows) for candidate in row["unique_candidates"]]
    values = sequence_mean_nll(model, [(source_chain, source) for _, source, _ in jobs],
                               [(target_chain, candidate) for _, _, candidate in jobs],
                               device, batch_size)
    scores = [[] for _ in rows]
    for (index, _, _), value in zip(jobs, values):
        scores[index].append(value)
    return scores


@torch.inference_mode()
def rescore(path, output, device, batch_size=512, likelihood=False):
    if path.resolve() == output.resolve():
        raise ValueError("Output must be separate from the original evaluation")
    payload = json.loads(path.read_text())
    free_generation = "rows" in payload
    ranker_path = payload.get("ranker")
    ranker = load_ranker(ranker_path, device) if ranker_path else None
    # Preserve exactly the saved candidates, positives, source condition and
    # generator scores for fixed pools. Only the ranker argument order changes.
    for direction in ("gamma_to_delta", "delta_to_gamma"):
        chain = "gamma" if direction == "gamma_to_delta" else "delta"
        target_chain = "delta" if chain == "gamma" else "gamma"
        pools = {"free": {"rows": payload["rows"][direction]}} if free_generation else payload["directions"][direction]
        all_rows = [row for entry in pools.values() for row in entry["rows"]]
        candidate_key = "unique_candidates" if free_generation else "candidates"
        source_mode = payload.get("arguments", {}).get("source_mode", "paired")
        for row in all_rows:
            if "conditioned_source" not in row:
                if source_mode == "shuffled":
                    raise ValueError("Shuffled evaluation lacks saved conditioned_source")
                row["conditioned_source"] = "" if source_mode == "constant" else row["source"]
        if ranker is not None:
            sources = encode_cache(ranker, chain,
                                   [row["conditioned_source"] for row in all_rows], batch_size)
            targets = encode_cache(ranker, target_chain,
                                   [candidate for row in all_rows for candidate in row[candidate_key]],
                                   batch_size)
            for entry in pools.values():
                for row in entry["rows"]:
                    candidates = row[candidate_key]
                    scores = ranker.score_queries(chain, sources[row["conditioned_source"]][None],
                                                   torch.stack([targets[c] for c in candidates]))[0]
                    values = scores.float().cpu().tolist()
                    summary = rank_summary(candidates, row["positives"], values, descending=True)
                    row["ranker_scores"] = values
                    if free_generation:
                        row["reranked_candidates"] = summary["ranked_candidates"]
                    else:
                        row["ranker"] = summary
                if not free_generation:
                    for metric in ("hit_at_1", "hit_at_5", "hit_at_10", "mrr"):
                        entry["ranker"][metric] = sum(row["ranker"][metric] for row in entry["rows"]) / len(entry["rows"])
            del sources, targets
        if free_generation:
            rows = payload["rows"][direction]
            if likelihood:
                model_path = payload.get("generators", {}).get(direction) or payload.get("generator")
                model, _ = load_checkpoint(model_path, device)
                model.eval()
                values = likelihood_scores(model, rows, chain, batch_size, device)
                for row, scores in zip(rows, values):
                    row["generator_scores"] = scores
                    summary = rank_summary(row["unique_candidates"], row["positives"], scores, False)
                    row["likelihood_ranked_candidates"] = summary["ranked_candidates"]
                del model
            for k in (1, 5, 10):
                metric = f"reranked_hit_at_{k}"
                payload["directions"][direction][metric] = sum(
                    bool(set(row["positives"]) & set(row["reranked_candidates"][:k])) for row in rows) / len(rows)
                if likelihood:
                    payload["directions"][direction][f"likelihood_hit_at_{k}"] = sum(
                        bool(set(row["positives"]) & set(row["likelihood_ranked_candidates"][:k])) for row in rows) / len(rows)
        print(path, direction, "rescored", len(all_rows), "rows", flush=True)
    payload["audit"] = {
        "protocol": "canonical_gamma_delta_score_order_v1",
        "original": str(path), "original_sha256": sha256(path),
        "ranker_sha256": sha256(ranker_path) if ranker_path else None,
        "script_sha256": sha256(__file__),
        "resampled": False, "raw_order": "first_occurrence_in_saved_samples",
        "added_likelihood_order": likelihood and free_generation,
        "likelihood_score": "mean_target_token_NLL_including_EOS",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(output, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--likelihood", action="store_true")
    args = parser.parse_args()
    set_seed(3407)
    rescore(args.input, args.output, torch.device(args.device), args.batch_size, args.likelihood)


if __name__ == "__main__":
    main()
