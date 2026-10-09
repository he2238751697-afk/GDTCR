#!/usr/bin/env python3
"""Freeze independent validation roles, directional splits and nested subsets."""

import argparse
import hashlib
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gdtcr.data import component_groups, read_pairs, write_pairs
from gdtcr.fileio import file_sha256


def group_by_source(pairs, column):
    groups = defaultdict(list)
    for i, pair in enumerate(pairs):
        groups[pair[column]].append(i)
    return list(groups.values())


def partition_groups(pairs, groups, names, fractions, seed):
    if len(groups) < len(names):
        raise ValueError("Insufficient groups for disjoint validation roles")
    groups = [list(g) for g in groups]
    rng = random.Random(seed)
    rng.shuffle(groups)
    groups.sort(key=len, reverse=True)
    targets = {name: len(pairs) * fraction for name, fraction in zip(names, fractions)}
    assigned = {name: [] for name in names}
    counts = dict.fromkeys(names, 0)
    for position, group in enumerate(groups):
        empty = [name for name in names if not assigned[name]]
        choices = empty if len(groups) - position == len(empty) else names
        scores = []
        for name in choices:
            after = {key: counts[key] + (len(group) if key == name else 0) for key in names}
            score = sum(((after[key] - targets[key]) / max(targets[key], 1)) ** 2 for key in names)
            scores.append((score, rng.random(), name))
        name = min(scores)[-1]
        assigned[name].extend(group)
        counts[name] += len(group)
    return {name: [pairs[i] for i in sorted(indices)] for name, indices in assigned.items()}


def validation_roles(pairs, source_column=None):
    groups = component_groups(pairs) if source_column is None else group_by_source(pairs, source_column)
    return partition_groups(pairs, groups, ("selection", "tuning", "calibration"), (.5, .25, .25), 7319)


def directional_unseen(pairs, column):
    return partition_groups(pairs, group_by_source(pairs, column),
                            ("train", "validation", "test"), (.8, .1, .1), 1729)


def directional_seen(pairs, column):
    split = {name: [] for name in ("train", "validation", "test")}
    for indices in group_by_source(pairs, column):
        source = pairs[indices[0]][column]
        if len(indices) < 3:
            split["train"].extend(pairs[i] for i in indices)
            continue
        digest = int(hashlib.sha256(source.encode()).hexdigest()[:12], 16)
        shuffled = sorted(indices)
        random.Random(1729 + digest).shuffle(shuffled)
        n_test = max(1, round(len(indices) * .1))
        n_val = max(1, round(len(indices) * .1))
        split["test"].extend(pairs[i] for i in shuffled[:n_test])
        split["validation"].extend(pairs[i] for i in shuffled[n_test:n_test + n_val])
        split["train"].extend(pairs[i] for i in shuffled[n_test + n_val:])
    return {name: sorted(rows) for name, rows in split.items()}


def nested_subsets(pairs):
    groups = component_groups(pairs)
    giant, remaining = groups[0], groups[1:]
    random.Random(1731).shuffle(remaining)
    order = remaining + [giant]
    selected = set()
    subsets = {}
    for fraction in (.10, .25, .50, 1.0):
        target = round(fraction * len(pairs))
        for group in order:
            if selected.intersection(group):
                continue
            if len(selected) + len(group) <= target:
                selected.update(group)
        subsets[str(int(fraction * 100))] = [pairs[i] for i in sorted(selected)]
    assert len(subsets["100"]) == len(pairs)
    return subsets


def overlaps(splits):
    return {a + "_" + b: {chain: len({p[i] for p in splits[a]} & {p[i] for p in splits[b]})
                            for i, chain in enumerate(("gamma", "delta"))}
            for a, b in (("train", "validation"), ("train", "test"), ("validation", "test"))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("data/splits/completion_v2"))
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Completion splits are immutable; inspect existing manifest")
    base = args.root / "data/splits"
    protocols = {}
    for name in ("split_seed17", "split_seed3407", "split_seed2026", "source_holdout", "source_shared"):
        splits = {part: read_pairs(base / name / (part + ".tsv")) for part in ("train", "validation", "test")}
        protocols[name] = (splits, None, "both", "legacy_test_unchanged")
    pairs = read_pairs(args.root / "data/processed/paired_chain.txt")
    for column, direction in ((0, "gamma_to_delta"), (1, "delta_to_gamma")):
        for label, builder in (("unseen_input", directional_unseen), ("seen_input", directional_seen)):
            splits = builder(pairs, column)
            source_sets = {s: {p[column] for p in rows} for s, rows in splits.items()}
            if label == "unseen_input":
                assert not any(source_sets[a] & source_sets[b] for a, b in (("train", "test"), ("train", "validation"), ("validation", "test")))
            else:
                assert source_sets["test"] <= source_sets["train"]
                assert source_sets["validation"] <= source_sets["train"]
            protocols[label + "_" + direction] = (splits, column, direction, label)
    manifest = {"protocol": "completion_v2", "input_pair_sha256": file_sha256(args.root / "data/processed/paired_chain.txt"),
                "validation_seed": 7319, "directional_seed": 1729, "subset_seed": 1731, "protocols": {}}
    for name, (splits, column, direction, kind) in protocols.items():
        folder = args.output / name
        for part, rows in splits.items():
            write_pairs(folder / (part + ".tsv"), rows)
        roles = validation_roles(splits["validation"], column)
        for role, rows in roles.items():
            write_pairs(folder / ("validation_" + role + ".tsv"), rows)
        assert set().union(*(set(r) for r in roles.values())) == set(splits["validation"])
        assert sum(map(len, roles.values())) == len(splits["validation"])
        record = {"kind": kind, "direction": direction, "bootstrap_unit": "component" if column is None else "source_query",
                  "sizes": {s: len(rows) for s, rows in splits.items()},
                  "validation_role_sizes": {s: len(rows) for s, rows in roles.items()},
                  "exact_chain_overlap": overlaps(splits),
                  "unique_chains": {s: {c: len({p[i] for p in rows}) for i, c in enumerate(("gamma", "delta"))}
                                    for s, rows in splits.items()}}
        if name == "split_seed17":
            subsets = nested_subsets(splits["train"])
            record["nested_subsets"] = {}
            for label, rows in subsets.items():
                write_pairs(folder / ("train_fraction" + label + ".tsv"), rows)
                record["nested_subsets"][label] = {"pairs": len(rows), "components": len(component_groups(rows)),
                                                   "actual_fraction": len(rows) / len(splits["train"])}
        record["output_sha256"] = {p.name: file_sha256(p) for p in sorted(folder.glob("*.tsv"))}
        manifest["protocols"][name] = record
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: {"sizes": v["sizes"], "validation_roles": v["validation_role_sizes"], "subsets": v.get("nested_subsets")}
                      for k, v in manifest["protocols"].items()}, indent=2))


if __name__ == "__main__":
    main()
