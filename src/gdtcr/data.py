"""Deterministic data preparation for leakage-controlled GDTCR experiments."""

from __future__ import annotations

import csv
import json
import random
from collections import defaultdict
from pathlib import Path

from .model import AMINO_ACIDS
from .fileio import file_sha256


def read_lines(path: Path) -> list[str]:
    with path.open(encoding="ascii") as handle:
        return [line.strip() for line in handle if line.strip()]


def read_pairs(path: Path) -> list[tuple[str, str]]:
    pairs = []
    with path.open(encoding="ascii") as handle:
        for line_number, line in enumerate(handle, 1):
            fields = line.rstrip("\n").split("\t")
            if len(fields) != 2:
                raise ValueError(f"Expected two tab-separated sequences at {path}:{line_number}")
            pairs.append((fields[0], fields[1]))
    return pairs


class DisjointSet:
    def __init__(self):
        self.parent: dict[tuple[str, str], tuple[str, str]] = {}
        self.rank: dict[tuple[str, str], int] = {}

    def find(self, item):
        if item not in self.parent:
            self.parent[item] = item
            self.rank[item] = 0
        if self.parent[item] != item:
            self.parent[item] = self.find(self.parent[item])
        return self.parent[item]

    def union(self, left, right):
        left_root, right_root = self.find(left), self.find(right)
        if left_root == right_root:
            return
        if self.rank[left_root] < self.rank[right_root]:
            left_root, right_root = right_root, left_root
        self.parent[right_root] = left_root
        if self.rank[left_root] == self.rank[right_root]:
            self.rank[left_root] += 1


def component_groups(pairs: list[tuple[str, str]]) -> list[list[int]]:
    dsu = DisjointSet()
    for gamma, delta in pairs:
        dsu.union(("gamma", gamma), ("delta", delta))
    groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, (gamma, _) in enumerate(pairs):
        groups[dsu.find(("gamma", gamma))].append(index)
    return sorted(groups.values(), key=lambda group: (-len(group), group[0]))


def assign_component_splits(pairs: list[tuple[str, str]], seed: int,
                             proportions=(0.8, 0.1, 0.1)):
    groups = component_groups(pairs)
    largest = groups[0]
    rng = random.Random(seed)
    remaining = groups[1:]
    rng.shuffle(remaining)
    remaining.sort(key=len, reverse=True)
    targets = [len(pairs) * value for value in proportions]
    assigned = {"train": list(largest), "validation": [], "test": []}
    counts = {"train": len(largest), "validation": 0, "test": 0}

    for group in remaining:
        options = []
        for name in ("train", "validation", "test"):
            after = dict(counts)
            after[name] += len(group)
            score = sum(((after[key] - targets[i]) / max(targets[i], 1)) ** 2
                        for i, key in enumerate(("train", "validation", "test")))
            options.append((score, rng.random(), name))
        _, _, choice = min(options)
        assigned[choice].extend(group)
        counts[choice] += len(group)

    result = {name: [pairs[i] for i in indices]
              for name, indices in assigned.items()}
    assert_split_integrity(result)
    component_ids = {}
    for split_name, indices in assigned.items():
        for index in indices:
            component_ids[str(index)] = split_name
    return result, {
        "seed": seed,
        "n_pairs": len(pairs),
        "n_components": len(groups),
        "largest_component_edges": len(largest),
        "largest_component_fraction": len(largest) / len(pairs),
        "split_pair_counts": {name: len(rows) for name, rows in result.items()},
        "split_unique_gamma": {name: len({g for g, _ in rows}) for name, rows in result.items()},
        "split_unique_delta": {name: len({d for _, d in rows}) for name, rows in result.items()},
        "component_split_by_pair_index": component_ids,
    }


def assert_split_integrity(splits):
    gamma_owner, delta_owner, edge_owner = {}, {}, {}
    for split_name, pairs in splits.items():
        for gamma, delta in pairs:
            for chain, owner, kind in ((gamma, gamma_owner, "gamma"),
                                       (delta, delta_owner, "delta")):
                if chain in owner and owner[chain] != split_name:
                    raise AssertionError(f"{kind} sequence crosses splits: {chain}")
                owner[chain] = split_name
            edge = (gamma, delta)
            if edge in edge_owner and edge_owner[edge] != split_name:
                raise AssertionError(f"Pair crosses splits: {edge}")
            edge_owner[edge] = split_name


def write_pairs(path: Path, pairs):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii", newline="\n") as handle:
        for gamma, delta in pairs:
            handle.write(f"{gamma}\t{delta}\n")


def write_sequences(path: Path, sequences):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="ascii", newline="\n") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(("chain", "sequence"))
        writer.writerows(sequences)
    temporary.replace(path)


def prepare_experiment(root: Path, output: Path, seeds=(17, 3407, 2026),
                       validation_fraction=0.02, min_pretrain_length=6):
    processed = root / "data" / "processed"
    gamma_all = set(read_lines(processed / "light_chain.txt"))
    delta_all = set(read_lines(processed / "heavy_chain.txt"))
    pairs = read_pairs(processed / "paired_chain.txt")
    paired_gamma = {gamma for gamma, _ in pairs}
    paired_delta = {delta for _, delta in pairs}
    if not paired_gamma <= gamma_all or not paired_delta <= delta_all:
        raise AssertionError("A paired sequence is missing from the corresponding single-chain file")
    amino_acid_set = set(AMINO_ACIDS)
    if any(set(seq) - amino_acid_set for seq in gamma_all | delta_all):
        raise AssertionError("Non-canonical amino acid found in processed sequence files")

    output.mkdir(parents=True, exist_ok=True)
    manifests = []
    for seed in seeds:
        splits, manifest = assign_component_splits(pairs, seed)
        seed_dir = output / f"split_seed{seed}"
        for name, rows in splits.items():
            write_pairs(seed_dir / f"{name}.tsv", rows)
        manifest["input_pair_sha256"] = file_sha256(processed / "paired_chain.txt")
        manifests.append(manifest)

    pretrain = []
    for chain_name, pool, paired in (("gamma", gamma_all, paired_gamma),
                                     ("delta", delta_all, paired_delta)):
        eligible = sorted(seq for seq in pool - paired if len(seq) >= min_pretrain_length)
        random.Random(3407 + (0 if chain_name == "gamma" else 1)).shuffle(eligible)
        n_val = max(1, round(len(eligible) * validation_fraction))
        pretrain.extend((chain_name, seq) for seq in eligible[n_val:])
        pretrain_val = [(chain_name, seq) for seq in eligible[:n_val]]
        write_sequences(output / "pretrain" / f"{chain_name}_validation.tsv", pretrain_val)
    write_sequences(output / "pretrain" / "train.tsv", pretrain)

    manifest = {
        "input_files": {
            str(path.relative_to(root)): file_sha256(path)
            for path in sorted(processed.glob("*.txt"))
        },
        "unique_gamma": len(gamma_all),
        "unique_delta": len(delta_all),
        "unique_pairs": len(pairs),
        "paired_gamma": len(paired_gamma),
        "paired_delta": len(paired_delta),
        "pretrain_min_length": min_pretrain_length,
        "pretrain_gamma_train": sum(chain == "gamma" for chain, _ in pretrain),
        "pretrain_delta_train": sum(chain == "delta" for chain, _ in pretrain),
        "pretrain_validation_fraction": validation_fraction,
        "pretrain_pair_overlap": {
            "gamma": len({seq for chain, seq in pretrain if chain == "gamma"} & paired_gamma),
            "delta": len({seq for chain, seq in pretrain if chain == "delta"} & paired_delta),
        },
        "component_splits": manifests,
    }
    if any(manifest["pretrain_pair_overlap"][chain] for chain in ("gamma", "delta")):
        raise AssertionError("Pretraining pool overlaps a paired sequence")
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def build_source_map(queries, seed):
    """Return a deterministic derangement for shuffled-input controls."""
    if len(queries) < 2:
        return {query: query for query in queries}
    shuffled = list(queries)
    random.Random(seed).shuffle(shuffled)
    for index, query in enumerate(queries):
        if shuffled[index] != query:
            continue
        swap = (index + 1) % len(shuffled)
        shuffled[index], shuffled[swap] = shuffled[swap], shuffled[index]
    return dict(zip(queries, shuffled))
