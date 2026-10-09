#!/usr/bin/env python3
"""Reconstruct historical denoising draw counts from the frozen worker RNG schedule."""

import argparse
import json
import math
import random
import re
from pathlib import Path

import torch

from train_denoiser import read_sequences
from gdtcr.fileio import file_sha256
from gdtcr.provenance import begin_run, finish_run


def replay(rows, args):
    lengths = {chain: [len(sequence) + 1 for typ, sequence in rows if typ == chain]
               for chain in ("gamma", "delta")}
    if args["sampling"] == "sqrt":
        gamma_probability = math.sqrt(len(lengths["gamma"])) / sum(math.sqrt(len(v)) for v in lengths.values())
    elif args["sampling"] == "raw":
        gamma_probability = len(lengths["gamma"]) / sum(map(len, lengths.values()))
    else:
        raise ValueError("Exposure reconstruction is only specified for sqrt/raw")
    rng = torch.Generator().manual_seed(args["seed"])
    base_seed = int(torch.empty((), dtype=torch.int64).random_(generator=rng).item())
    workers = args["num_workers"]
    if workers != 4:
        raise ValueError("Historical reconstruction expects the verified four-worker schedule")
    sequences, tokens = {"gamma": 0, "delta": 0}, {"gamma": 0, "delta": 0}
    for worker in range(workers):
        generator = random.Random(base_seed + worker)
        batches = len(range(worker, args["steps"], workers))
        for _ in range(batches * args["batch_size"]):
            chain = "gamma" if generator.random() < gamma_probability else "delta"
            target_tokens = generator.choice(lengths[chain])
            sequences[chain] += 1
            tokens[chain] += target_tokens
    return {"chain_sequences_this_invocation": sequences, "chain_target_tokens_this_invocation": tokens,
            "gamma_sampling_probability": gamma_probability, "loader_base_seed": base_seed,
            "total_draws": sum(sequences.values())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    validation = Path("artifacts/completion_v2/pretrain/raw/seed-0")
    folders = [Path(f"artifacts/runs/pretrain/{pool}/seed-{seed}")
               for pool in ("a800", "source_holdout") for seed in (0, 1)]
    inputs = [folder / name for folder in [validation, *folders] for name in ("run.json", "summary.json")]
    for folder in [validation, *folders]:
        inputs.append(Path(json.loads((folder / "run.json").read_text())["arguments"]["train"]))
    begin_run(args.output, args, sorted(set(inputs)))
    cache, recovered = {}, []
    for folder in [validation, *folders]:
        run = json.loads((folder / "run.json").read_text())
        arguments = run["arguments"]
        source = arguments["train"]
        if source not in cache:
            cache[source] = read_sequences(Path(source))
        actual = replay(cache[source], arguments)
        if folder == validation:
            observed = json.loads((folder / "summary.json").read_text())
            for key in ("chain_sequences_this_invocation", "chain_target_tokens_this_invocation"):
                if actual[key] != observed[key]:
                    raise ValueError(f"Independent logged-count validation failed: {key}")
        else:
            actual.update(path=str(folder), reconstructed=True, seed=arguments["seed"],
                          train_sha256=file_sha256(source), checkpoint_sha256=file_sha256(folder / "last.pt"))
            recovered.append(actual)
        print(json.dumps({"folder": str(folder), "replayed_draws": actual["total_draws"]}), flush=True)
    note = "DataLoader generator supplies base seed; Python RNG is base+worker; batches are round-robin. Source corruption uses torch RNG and does not consume Python draw RNG. Replay is not contemporaneous logging."
    result = {"schema_version": 2, "validation": {"path": str(validation), "exact_match_to_logged_sequence_and_token_counts": True},
              "recovered": recovered, "method": note,
              "legacy_job_id_note": "Main seed-0 log filename/accounting identify array 2995691_0, but its embedded header says job=2995696. Preserve this header mismatch; checkpoint identity is established by SHA256, not by silently rewriting the log."}
    (args.output / "summary.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    finish_run(args.output)


if __name__ == "__main__":
    main()
