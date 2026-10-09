#!/usr/bin/env python3
"""Freeze GSE180059 -> Suo_2022 source and exact-chain holdout tables."""

import argparse
import csv
import gzip
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gdtcr.data import assign_component_splits, assert_split_integrity, write_pairs
from gdtcr.fileio import file_sha256 as sha


def gzrows(path):
    with gzip.open(path, "rt") as handle:
        yield from csv.DictReader(handle, delimiter="\t")


def prepare(provenance, pretrain, output, seed, allow_shared_chains=False):
    pairs = list(gzrows(provenance / "unique_pairs.tsv.gz"))
    test = sorted({(r["gamma_cdr3"], r["delta_cdr3"]) for r in pairs
                   if "Suo_2022" in r["studies"].split("|")})
    base = sorted({(r["gamma_cdr3"], r["delta_cdr3"]) for r in pairs
                   if "GSE180059" in r["studies"].split("|")})
    heldout_chains = {"gamma": set(), "delta": set()}
    unreliable_chains = {"gamma": set(), "delta": set()}
    for row in gzrows(provenance / "sequence_sources.tsv.gz"):
        if row["study_id"] == "Suo_2022":
            heldout_chains[row["chain"]].add(row["sequence"])
        if row["source_db"] == "IEDB":
            unreliable_chains[row["chain"]].add(row["sequence"])
    if allow_shared_chains:
        eligible = sorted(set(base) - set(test))
    else:
        eligible = [(g, d) for g, d in base
                    if g not in heldout_chains["gamma"] and d not in heldout_chains["delta"]]
    split, split_metadata = assign_component_splits(eligible, seed, (0.9, 0.1, 0.0))
    if split["test"]:
        raise AssertionError("Internal source split unexpectedly assigned a test component")
    assert_split_integrity({"train": split["train"], "validation": split["validation"]})
    split["test"] = test
    if not allow_shared_chains:
        assert_split_integrity(split)
    assert not set(test) & (set(split["train"]) | set(split["validation"]))
    output.mkdir(parents=True, exist_ok=True)
    for name, values in split.items():
        write_pairs(output / f"{name}.tsv", values)
    pretrain_counts = {}
    for source in sorted(pretrain.glob("*.tsv")):
        target = output / "pretrain" / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".tmp")
        kept, dropped_source, dropped_unreliable = Counter(), Counter(), Counter()
        with source.open() as handle, temporary.open("w") as output_handle:
            writer = csv.DictWriter(output_handle, fieldnames=("chain", "sequence"), delimiter="\t", lineterminator="\n")
            writer.writeheader()
            for row in csv.DictReader(handle, delimiter="\t"):
                chain, sequence = row["chain"], row["sequence"]
                if sequence in heldout_chains[chain]:
                    dropped_source[chain] += 1
                elif sequence in unreliable_chains[chain]:
                    dropped_unreliable[chain] += 1
                else:
                    kept[chain] += 1
                    writer.writerow(row)
        temporary.replace(target)
        pretrain_counts[source.name] = {"kept": dict(kept), "removed_heldout_study": dict(dropped_source),
                                        "removed_untraceable_iedb": dict(dropped_unreliable)}
    manifest = {
        "protocol": "GSE180059_to_Suo2022_" + ("shared_chains_allowed_v1" if allow_shared_chains else "strict_source_and_chain_holdout_v1"),
        "train_validation_study": "GSE180059", "heldout_study": "Suo_2022",
        "heldout_doi": "10.1126/science.abo0510", "heldout_accession": "E-MTAB-11388",
        "seed": seed, "base_unique_pairs": len(base), "heldout_unique_pairs": len(test),
        "cross_study_duplicate_pairs": len(set(base) & set(test)),
        "base_pairs_removed_for_source_chain_overlap": len(base) - len(eligible),
        "allow_shared_chains": allow_shared_chains,
        "eligible_pairs": len(eligible),
        "heldout_all_valid_chains": {chain: len(rows) for chain, rows in heldout_chains.items()},
        "split_sizes": {name: len(rows) for name, rows in split.items()},
        "split_unique_chains": {name: {"gamma": len({g for g, _ in rows}), "delta": len({d for _, d in rows})}
                                for name, rows in split.items()},
        "internal_component_split": split_metadata,
        "pretrain_filter": pretrain_counts,
        "exact_chain_overlap_counts": {
            f"{a}_{b}": {"gamma": len({g for g, _ in split[a]} & {g for g, _ in split[b]}),
                          "delta": len({d for _, d in split[a]} & {d for _, d in split[b]})}
            for a, b in (("train", "validation"), ("train", "test"), ("validation", "test"))},
        "pretrain_policy": "Remove every known Suo sequence and untraceable IEDB sequence from the already pair-excluded legacy pretraining split; do not reassign validation sequences.",
        "metadata_limit": "Suo database export lacks original cell/library/donor IDs. Study-level provenance was verified against original paper; individual mapping remains unavailable.",
        "input_provenance_sha256": sha(provenance / "manifest.json"),
        "output_sha256": {str(p.relative_to(output)): sha(p) for p in sorted(output.rglob("*.tsv"))},
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: manifest[k] for k in ("base_pairs_removed_for_source_chain_overlap", "split_sizes", "split_unique_chains", "pretrain_filter")}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provenance", type=Path, default=ROOT / "data/provenance")
    parser.add_argument("--pretrain", type=Path, default=ROOT / "data/splits/pretrain")
    parser.add_argument("--output", type=Path, default=ROOT / "data/splits/source_holdout")
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--allow-shared-chains", action="store_true")
    args = parser.parse_args()
    prepare(args.provenance, args.pretrain, args.output, args.seed, args.allow_shared_chains)
