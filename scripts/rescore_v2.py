#!/usr/bin/env python3
"""Apply another frozen ranker to immutable free samples or fixed-pool scores."""

import argparse
import copy
import gzip
import json
import sys
import time
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gdtcr.data import read_pairs
from gdtcr.fileio import file_sha256
from gdtcr.provenance import begin_run, finish_run
from gdtcr.training import load_ranker, set_seed
from calibrate_scores_v2 import verify_settings
from evaluate_free_v2 import score_ranker, summarize_prefix, summarize_rows
from evaluate_pools_v2 import (encode_target_universe, ranker_scores,
                              summary_for_pool, summarize)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("free", "pools"), required=True)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--ranker", type=Path, required=True)
    parser.add_argument("--pool", type=Path)
    parser.add_argument("--train", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--settings", type=Path)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--batch-size", type=int, default=128)
    args = parser.parse_args()
    original_args = json.loads((args.base / "provenance.json").read_text())["arguments"]
    for key, value in original_args.items():
        if not hasattr(args, key):
            setattr(args, key, value)
    if args.train is None and original_args.get("train"):
        args.train = Path(original_args["train"])
    if args.pool is None and original_args.get("pool"):
        args.pool = Path(original_args["pool"])
    settings_record = verify_settings(args.settings, args.mode, args)
    inputs = [args.ranker, args.pool, args.train, args.settings,
              *[args.base / name for name in ("rows.json.gz", "summary.json", "provenance.json", "checksums.json")]]
    # Keep the original generator/prior hashes in derived-run lineage as well.
    inputs.extend(getattr(args, key, None) for key in
                  ("generator", "generator_gamma_to_delta", "generator_delta_to_gamma",
                   "prior", "prior_gamma_to_delta", "prior_delta_to_gamma"))
    set_seed(args.seed)
    begin_run(args.output, args, inputs)
    ranker = load_ranker(args.ranker, torch.device(args.device))
    with gzip.open(args.base / "rows.json.gz", "rt") as handle:
        original = json.load(handle)
    summaries, result = {}, {}
    started = time.monotonic()
    pool = None
    if args.mode == "pools":
        with gzip.open(args.pool, "rt") as handle:
            pool = json.load(handle)
        if json.loads((args.base / "summary.json").read_text())["pool_sha256"] != file_sha256(args.pool):
            raise ValueError("Derived ranker scores would use a different candidate pool")
    for direction, values in original.items():
        source_chain, target_chain = ("gamma", "delta") if direction == "gamma_to_delta" else ("delta", "gamma")
        rows = copy.deepcopy(values)
        if args.mode == "free":
            train_targets = {pair[1 if direction == "gamma_to_delta" else 0] for pair in read_pairs(args.train)}
            for row in rows:
                source = row["source"] if args.ranker_source_mode == "paired" else row["conditioned_source"]
                row["ranker_source"] = source
                candidates = row["candidate_sequences"]
                scores = score_ranker(ranker, source_chain, source, target_chain, candidates, args.batch_size)
                row["candidate_ranker_score"] = scores
                budgets = sorted({int(key.split("/")[0]) for key in row["prefixes"]})
                row["prefixes"] = summarize_prefix(
                    row["samples"], row["positives"], train_targets,
                    {"likelihood": dict(zip(candidates, (-value for value in row["candidate_nll"]))),
                     "ranker": dict(zip(candidates, scores))}, budgets)
            summaries[direction] = summarize_rows(rows)
        else:
            targets = pool["directions"][direction]["target_universe"]
            target_vectors = encode_target_universe(ranker, target_chain, targets, args.batch_size)
            for row in rows:
                row["scores"]["ranker"] = ranker_scores(ranker, source_chain, row["source"], target_vectors)
                row["pool_metrics"] = {name: summary_for_pool(row["positives"], targets, indices, row["scores"])
                                       for name, indices in row["pool_indices"].items()}
            summaries[direction] = summarize(rows)
        result[direction] = rows
    with gzip.open(args.output / "rows.json.gz", "wt", encoding="utf-8", compresslevel=6) as handle:
        json.dump(result, handle, sort_keys=True, separators=(",", ":"))
    summary = {"schema_version": 2, "mode": args.mode, "directions": summaries,
               "calibration_settings": settings_record, "base": str(args.base),
               "base_rows_sha256": file_sha256(args.base / "rows.json.gz"),
               "evaluation_seconds": time.monotonic() - started,
               "sampling_performed": False, "candidate_membership_unchanged": True}
    if pool is not None:
        summary["pool_sha256"] = file_sha256(args.pool)
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    finish_run(args.output)
    print(json.dumps({"output": str(args.output), "mode": args.mode}), flush=True)


if __name__ == "__main__":
    main()
