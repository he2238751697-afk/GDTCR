#!/usr/bin/env python3
"""Score shuffled input and target-only controls on identical frozen pools."""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gdtcr.data import build_source_map
from gdtcr.metrics import rank_summary

from gdtcr.training import load_checkpoint, sequence_mean_nll, set_seed
from gdtcr.fileio import file_sha256 as sha256


@torch.inference_mode()
def score_jobs(model, source_chain, jobs, device, batch_size):
    target_chain = "delta" if source_chain == "gamma" else "gamma"
    values = sequence_mean_nll(model, [(source_chain, source) for source, _ in jobs],
                               [(target_chain, target) for _, target in jobs], device, batch_size)
    return dict(zip(jobs, values))


def add_controls(args):
    if args.input.resolve() == args.output.resolve():
        raise ValueError("Preserve the input evaluation")
    device = torch.device(args.device)
    payload = json.loads(args.input.read_text())
    set_seed(args.seed)
    generator, _ = load_checkpoint(payload["generator"], device)
    prior_paths = {"gamma_to_delta": args.prior_delta or args.prior,
                   "delta_to_gamma": args.prior_gamma or args.prior}
    for direction, pools in payload["directions"].items():
        source_chain = "gamma" if direction == "gamma_to_delta" else "delta"
        union = defaultdict(set)
        for entry in pools.values():
            for row in entry["rows"]:
                union[row["source"]].update(row["candidates"])
        queries = sorted(union)
        mapping = build_source_map(queries, args.seed + (source_chain == "delta"))
        shuffled_jobs = [(mapping[q], t) for q in queries for t in sorted(union[q])]
        shuffled = score_jobs(generator, source_chain, shuffled_jobs, device, args.batch_size)
        prior_model, _ = load_checkpoint(prior_paths[direction], device)
        prior_targets = sorted(set().union(*union.values()))
        prior = score_jobs(prior_model, source_chain, [("", t) for t in prior_targets], device, args.batch_size)
        del prior_model
        for entry in pools.values():
            for row in entry["rows"]:
                candidates = row["candidates"]
                p = [prior["", t] for t in candidates]
                s = [shuffled[mapping[row["source"]], t] for t in candidates]
                # All controls are high-is-better; generator_scores are NLL.
                values = {"target_only": [-v for v in p], "shuffled_input": [-v for v in s],
                          "conditional_minus_prior": [a - b for a, b in zip(p, row["generator_scores"])]}
                row["control_scores"] = values
                row["controls"] = {}
                row["shuffled_source"] = mapping[row["source"]]
                for method, score in values.items():
                    ranked = rank_summary(candidates, row["positives"], score, descending=True)
                    ranked.pop("ranked_candidates")
                    row["controls"][method] = ranked
                indices = [i for i, t in enumerate(candidates) if t in set(row["positives"])]
                row["positive_mean_token_nll"] = {
                    "conditional": sum(row["generator_scores"][i] for i in indices) / len(indices),
                    "target_only": sum(p[i] for i in indices) / len(indices),
                    "shuffled_input": sum(s[i] for i in indices) / len(indices),
                }
            entry["controls"] = {
                method: {metric: sum(row["controls"][method][metric] for row in entry["rows"]) / len(entry["rows"])
                         for metric in ("hit_at_1", "hit_at_5", "hit_at_10", "mrr")}
                for method in ("target_only", "shuffled_input", "conditional_minus_prior")}
        print(direction, "scored", len(shuffled_jobs), "shuffled pairs", len(prior_targets), "prior targets", flush=True)
    payload["control_audit"] = {
        "input": str(args.input), "input_sha256": sha256(args.input), "seed": args.seed,
        "generator_sha256": sha256(payload["generator"]),
        "prior_paths": {k: str(v) for k, v in prior_paths.items()},
        "prior_sha256": {k: sha256(v) for k, v in prior_paths.items()},
        "candidate_pools_unchanged": True, "likelihood_difference_coefficient": 1.0,
        "all_control_scores_high_is_better": True,
        "nll_unit": "mean_target_token_NLL_including_EOS; positive summaries average partners within query",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n")
    print(args.output, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prior", type=Path)
    parser.add_argument("--prior-gamma", type=Path)
    parser.add_argument("--prior-delta", type=Path)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--seed", type=int, default=3407)
    args = parser.parse_args()
    if not args.prior and not (args.prior_gamma and args.prior_delta):
        parser.error("provide --prior or both direction-specific prior checkpoints")
    add_controls(args)
