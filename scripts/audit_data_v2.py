#!/usr/bin/env python3
"""Independently assert completion-v2 data membership and describe split balance."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gdtcr.data import component_groups, read_lines, read_pairs
from gdtcr.fileio import file_sha256
from gdtcr.model import AMINO_ACIDS


ROLES = ("selection", "tuning", "calibration")
PARTS = ("train", "validation", "test")


def read_sources(path):
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        result = {}
        for row in reader:
            pair = row["gamma_cdr3"], row["delta_cdr3"]
            if pair in result:
                raise ValueError(f"Duplicate provenance pair: {pair}")
            result[pair] = row["studies"].split("|")
    return result


def describe(values):
    values = sorted(values)
    if not values:
        return {"n": 0}
    return {"n": len(values), "min": values[0], "median": statistics.median(values),
            "mean": statistics.mean(values), "max": values[-1]}


def part_summary(pairs, provenance):
    gamma_degree = Counter(g for g, _ in pairs)
    delta_degree = Counter(d for _, d in pairs)
    studies = Counter(study for pair in pairs for study in provenance[pair])
    components = component_groups(pairs)
    return {"pairs": len(pairs), "queries": {"gamma_to_delta": len(gamma_degree),
                                               "delta_to_gamma": len(delta_degree)},
            "studies": dict(sorted(studies.items())),
            "gamma_length": describe(len(g) for g, _ in pairs),
            "delta_length": describe(len(d) for _, d in pairs),
            "gamma_degree": describe(gamma_degree.values()),
            "delta_degree": describe(delta_degree.values()),
            "multi_partner_nodes": {"gamma": sum(v > 1 for v in gamma_degree.values()),
                                    "delta": sum(v > 1 for v in delta_degree.values())},
            "components": len(components),
            "largest_component_pairs": max((len(component) for component in components), default=0)}


def audit_protocol(folder, record, master, provenance):
    files = {path.name: path for path in folder.glob("*.tsv")}
    if set(files) != set(record["output_sha256"]):
        raise ValueError(f"Split file list changed: {folder}")
    for name, path in files.items():
        if file_sha256(path) != record["output_sha256"][name]:
            raise ValueError(f"Split hash mismatch: {path}")
    splits = {part: read_pairs(files[part + ".tsv"]) for part in PARTS}
    roles = {role: read_pairs(files["validation_" + role + ".tsv"]) for role in ROLES}
    for name, rows in (*splits.items(), *roles.items()):
        if len(rows) != len(set(rows)) or not set(rows) <= master:
            raise ValueError(f"Duplicate or unknown pair in {folder / name}")
    if any(set(splits[left]) & set(splits[right])
           for left, right in (("train", "validation"), ("train", "test"), ("validation", "test"))):
        raise ValueError(f"Edge overlap across roles: {folder}")
    if set().union(*(set(rows) for rows in roles.values())) != set(splits["validation"]):
        raise ValueError(f"Validation roles fail to cover the frozen validation edges: {folder}")
    if sum(map(len, roles.values())) != len(splits["validation"]):
        raise ValueError(f"Validation roles overlap: {folder}")
    chain_sets = {part: [{pair[i] for pair in rows} for i in (0, 1)]
                  for part, rows in splits.items()}
    overlap = {left + "_" + right: {
        chain: len(chain_sets[left][i] & chain_sets[right][i])
        for i, chain in enumerate(("gamma", "delta"))}
        for left, right in (("train", "validation"), ("train", "test"),
                            ("validation", "test"))}
    if overlap != record["exact_chain_overlap"]:
        raise ValueError(f"Reported chain overlaps changed: {folder}")
    name = folder.name
    if name.startswith("split_seed") or name == "source_holdout":
        if any(value for item in overlap.values() for value in item.values()):
            raise ValueError(f"Strict split shares an exact chain: {folder}")
    if name.startswith("unseen_input_") or name.startswith("seen_input_"):
        source = 0 if name.endswith("gamma_to_delta") else 1
        train = chain_sets["train"][source]
        for part in ("validation", "test"):
            held = chain_sets[part][source]
            if name.startswith("unseen_input_") and train & held:
                raise ValueError(f"Unseen input appears in training: {folder / part}")
            if name.startswith("seen_input_") and not held <= train:
                raise ValueError(f"Seen input absent from training: {folder / part}")
        if name.startswith("unseen_input_") and chain_sets["validation"][source] & chain_sets["test"][source]:
            raise ValueError(f"Unseen input appears in validation and test: {folder}")
    role_sources = {role: {pair[0 if name.endswith("gamma_to_delta") else 1] for pair in rows}
                    for role, rows in roles.items()}
    if name.startswith(("unseen_input_", "seen_input_")) and any(
            role_sources[left] & role_sources[right] for left, right in
            (("selection", "tuning"), ("selection", "calibration"), ("tuning", "calibration"))):
        raise ValueError(f"Validation tuning and calibration share a query: {folder}")
    if not name.startswith(("unseen_input_", "seen_input_")):
        for column in (0, 1):
            values = [{pair[column] for pair in roles[role]} for role in ROLES]
            if any(values[a] & values[b] for a, b in ((0, 1), (0, 2), (1, 2))):
                raise ValueError(f"Validation components cross selection/tuning/calibration: {folder}")
    if record["kind"] == "legacy_test_unchanged":
        for part in PARTS:
            original = Path("data/splits") / name / (part + ".tsv")
            if set(read_pairs(original)) != set(splits[part]):
                raise ValueError(f"Original frozen split membership changed: {original}")
    result = {"kind": record["kind"], "direction": record["direction"],
              "exact_chain_overlap": overlap,
              "parts": {part: part_summary(rows, provenance) for part, rows in splits.items()},
              "validation_roles": {role: part_summary(rows, provenance) for role, rows in roles.items()},
              "file_sha256": record["output_sha256"]}
    if "nested_subsets" in record:
        subsets = {fraction: read_pairs(files["train_fraction" + fraction + ".tsv"])
                   for fraction in ("10", "25", "50", "100")}
        if any(not set(subsets[a]) <= set(subsets[b]) for a, b in
               (("10", "25"), ("25", "50"), ("50", "100"))):
            raise ValueError("Data-curve subsets are not nested")
        if set(subsets["100"]) != set(splits["train"]):
            raise ValueError("100% data-curve subset differs from training")
        training_components = [{splits["train"][i] for i in group}
                               for group in component_groups(splits["train"])]
        for fraction, rows in subsets.items():
            selected = set(rows)
            if any(selected & group and not group <= selected for group in training_components):
                raise ValueError(f"Data-curve subset splits a whole training component: {folder}/{fraction}")
            if len(rows) != record["nested_subsets"][fraction]["pairs"]:
                raise ValueError("Data-curve count differs from the frozen manifest")
        result["nested_subsets"] = {key: part_summary(rows, provenance)
                                    for key, rows in subsets.items()}
    return result


def pretrain_exclusion(path, pairs):
    paired = [{pair[i] for pair in pairs} for i in (0, 1)]
    counts = Counter()
    with path.open(newline="", encoding="ascii") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            chain = row["chain"]
            index = 0 if chain == "gamma" else 1 if chain == "delta" else None
            if index is None or row["sequence"] in paired[index]:
                raise ValueError(f"Paired chain or invalid chain in pretraining: {row}")
            counts[chain] += 1
    return dict(counts)


def audit_pretraining(main_root, source_root, provenance_root, pairs):
    paired = {chain: {pair[i] for pair in pairs} for i, chain in enumerate(("gamma", "delta"))}
    excluded = {chain: set() for chain in paired}
    source_only = {chain: set() for chain in paired}
    with gzip.open(provenance_root / "sequence_sources.tsv.gz", "rt", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["study_id"] == "Suo_2022":
                source_only[row["chain"]].add(row["sequence"])
            if row["study_id"] == "Suo_2022" or row["source_db"] == "IEDB":
                excluded[row["chain"]].add(row["sequence"])
    parts = ("train", "gamma_validation", "delta_validation")
    allowed = set(AMINO_ACIDS)

    def load_pool(root):
        values, hashes, counts = {}, {}, {}
        for part in parts:
            path = root / (part + ".tsv")
            chains = {chain: set() for chain in paired}
            with path.open(newline="", encoding="ascii") as handle:
                for row in csv.DictReader(handle, delimiter="\t"):
                    chain, sequence = row["chain"], row["sequence"]
                    if chain not in paired or not set(sequence) <= allowed or not 6 <= len(sequence) <= 35:
                        raise ValueError(f"Invalid pretraining row in {path}: {row}")
                    if sequence in paired[chain] or sequence in chains[chain]:
                        raise ValueError(f"Paired or duplicate sequence in {path}: {row}")
                    if part != "train" and not part.startswith(chain + "_"):
                        raise ValueError(f"Wrong chain in pretraining validation: {path}")
                    chains[chain].add(sequence)
            values[part] = chains
            hashes[str(path)] = file_sha256(path)
            counts[part] = {chain: len(items) for chain, items in chains.items()}
        for chain in paired:
            if values["train"][chain] & values[chain + "_validation"][chain]:
                raise ValueError(f"Pretraining train/validation overlap for {root}/{chain}")
        return values, hashes, counts

    main, hashes, counts = load_pool(main_root)
    source, source_hashes, source_counts = load_pool(source_root)
    for part in parts:
        for chain in paired:
            if source[part][chain] != main[part][chain] - excluded[chain]:
                raise ValueError(f"Source-excluded pretraining pool differs from declared filtering: {part}/{chain}")
    for chain, filename in (("gamma", "light_chain.txt"), ("delta", "heavy_chain.txt")):
        processed = {value for value in read_lines(Path("data/processed") / filename) if len(value) >= 6}
        if main["train"][chain] | main[chain + "_validation"][chain] != processed - paired[chain]:
            raise ValueError(f"Main pretraining pool is not exactly the eligible pair-excluded data: {chain}")
    source_manifest = json.loads((source_root.parent / "manifest.json").read_text())
    for path, digest in source_hashes.items():
        relative = str(Path(path).relative_to(source_root.parent))
        if source_manifest["output_sha256"][relative] != digest:
            raise ValueError(f"Source pretraining manifest hash mismatch: {path}")
    for part in ("train", "validation"):
        for gamma, delta in read_pairs(source_root.parent / (part + ".tsv")):
            if gamma in source_only["gamma"] or delta in source_only["delta"]:
                raise ValueError("Strict source supervision contains an excluded source chain")
    shared_hashes = {part: file_sha256(Path("data/splits/source_shared/pretrain") / (part + ".tsv"))
                     for part in parts}
    if any(shared_hashes[part] != source_hashes[str(source_root / (part + ".tsv"))] for part in parts):
        raise ValueError("Source-shared and strict source pretraining tables differ")
    return {"main_counts": counts, "source_excluded_counts": source_counts,
            "exact_pair_exclusion": True, "train_validation_disjoint": True,
            "main_pool_exact_eligible_coverage": True, "source_filter_exact": True,
            "source_shared_pretraining_identical_to_strict": True,
            "source_exclusion_counts": {chain: len(items) for chain, items in excluded.items()},
            "file_sha256": {**hashes, **source_hashes}}


def audit_provenance_files(provenance_root):
    manifest_path = provenance_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    verified = {}
    for key, root in (("raw_sha256", Path("data/raw")),
                      ("processed_sha256", Path("data/processed")),
                      ("output_sha256", provenance_root)):
        for name, expected in manifest[key].items():
            path = root / name
            actual = file_sha256(path)
            if actual != expected:
                raise ValueError(f"Provenance input/output hash changed: {path}")
            verified[str(path)] = actual
    return {"manifest_sha256": file_sha256(manifest_path), "files_verified": len(verified),
            "file_sha256": verified}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split-root", type=Path, default=Path("data/splits/completion_v2"))
    parser.add_argument("--pairs", type=Path, default=Path("data/processed/paired_chain.txt"))
    parser.add_argument("--provenance", type=Path, default=Path("data/provenance/unique_pairs.tsv.gz"))
    parser.add_argument("--pretrain", type=Path, default=Path("data/splits/pretrain/train.tsv"))
    parser.add_argument("--source-pretrain-root", type=Path,
                        default=Path("data/splits/source_holdout/pretrain"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/completion_v2/data_audit.json"))
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"Completed data audit is immutable: {args.output}")
    manifest = json.loads((args.split_root / "manifest.json").read_text())
    pairs = read_pairs(args.pairs)
    provenance = read_sources(args.provenance)
    if len(pairs) != len(set(pairs)) or set(pairs) != set(provenance):
        raise ValueError("Processed pairs and provenance do not match exactly")
    if file_sha256(args.pairs) != manifest["input_pair_sha256"]:
        raise ValueError("Processed pairs changed after split creation")
    result = {"schema_version": 2,
              "input_sha256": {str(path): file_sha256(path) for path in
                               (args.pairs, args.provenance, args.pretrain,
                                args.split_root / "manifest.json", Path(__file__))},
              "paired_sequences_excluded_from_pretraining": pretrain_exclusion(args.pretrain, pairs),
              "pretraining_audit": audit_pretraining(args.pretrain.parent, args.source_pretrain_root,
                                                     args.provenance.parent, pairs),
              "provenance_files": audit_provenance_files(args.provenance.parent),
              "master": part_summary(pairs, provenance),
              "protocols": {name: audit_protocol(args.split_root / name, record,
                                                 set(pairs), provenance)
                            for name, record in manifest["protocols"].items()}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(args.output), "protocols": len(result["protocols"]),
                      "master_pairs": len(pairs)}, sort_keys=True))


if __name__ == "__main__":
    main()
