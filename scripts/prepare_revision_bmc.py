#!/usr/bin/env python3
"""Freeze BMC revision splits without altering the completed benchmark."""
import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gdtcr.data import component_groups, read_pairs, write_pairs
from gdtcr.fileio import file_sha256


def query_roles(pairs, column=0, seed=7319):
    groups = defaultdict(list)
    for pair in pairs:
        groups[pair[column]].append(pair)
    queries = sorted(groups)
    if len(queries) < 8:
        raise ValueError("At least eight query groups are needed for three useful roles")
    random.Random(seed).shuffle(queries)
    n_selection = len(queries) // 2
    n_tuning = (len(queries) - n_selection) // 2
    parts = (queries[:n_selection], queries[n_selection:n_selection+n_tuning],
             queries[n_selection+n_tuning:])
    return {name: sorted(pair for query in selected for pair in groups[query])
            for name, selected in zip(("selection", "tuning", "calibration"), parts)}


def giant_edge_split(pairs, held_per_role=500, seed=1729):
    pairs = sorted(pairs)
    giant = [pairs[i] for i in component_groups(pairs)[0]]
    counts = [Counter(p[i] for p in giant) for i in (0, 1)]
    order = giant.copy()
    random.Random(seed).shuffle(order)
    held = []
    for gamma, delta in order:
        if counts[0][gamma] > 1 and counts[1][delta] > 1:
            held.append((gamma, delta))
            counts[0][gamma] -= 1
            counts[1][delta] -= 1
            if len(held) == 2 * held_per_role:
                break
    if len(held) != 2 * held_per_role:
        raise ValueError("Insufficient edges while preserving both training endpoints")
    random.Random(seed + 1).shuffle(held)
    return {"train": sorted(set(pairs) - set(held)),
            "validation": sorted(held[:held_per_role]),
            "test": sorted(held[held_per_role:])}


def selection_information(pairs, known_pairs, column):
    known = defaultdict(set)
    positives = defaultdict(set)
    for p in known_pairs:
        known[p[column]].add(p[1-column])
    for p in pairs:
        positives[p[column]].add(p[1-column])
    universe = set().union(*positives.values())
    distractors = [len(universe - known[q]) for q in positives]
    return {"queries": len(positives), "edges": len(pairs),
            "largest_query_edges": max(map(len, positives.values())),
            "target_universe": len(universe), "minimum_distractors": min(distractors),
            "queries_without_distractors": sum(n == 0 for n in distractors)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/splits/revision_bmc"))
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Revision splits are immutable")
    base = Path("data/splits/completion_v2")
    known = read_pairs(Path("data/processed/paired_chain.txt"))
    manifest = {"protocol": "paper/revision_bmc_protocol.md",
                "protocol_sha256": file_sha256("paper/revision_bmc_protocol.md"),
                "known_pairs_sha256": file_sha256("data/processed/paired_chain.txt"),
                "protocols": {}}
    source = base / "unseen_input_gamma_to_delta"
    unseen = {p: read_pairs(source / (p + ".tsv")) for p in ("train", "validation", "test")}
    roles = query_roles(unseen["validation"])
    assert set().union(*(set(v) for v in roles.values())) == set(unseen["validation"])
    sets = [{g for g, _ in r} for r in roles.values()]
    assert all(not a & b for i, a in enumerate(sets) for b in sets[i+1:])
    protocols = {"unseen_gamma_repaired": (unseen, roles, "gamma_to_delta", "source_query")}
    original_train = read_pairs(base / "split_seed17/train.tsv")
    giant = giant_edge_split(original_train)
    for col in (0, 1):
        train_nodes = {p[col] for p in giant["train"]}
        assert {p[col] for p in giant["validation"] + giant["test"]} <= train_nodes
    assert all(not set(giant[a]) & set(giant[b]) for a,b in
               (("train", "validation"), ("train", "test"), ("validation", "test")))
    assert set().union(*(set(r) for r in giant.values())) == set(original_train)
    protocols["giant_edge_holdout"] = (giant, {"selection": giant["validation"]},
                                        "both", "single_original_component")
    for name, (splits, role_rows, direction, unit) in protocols.items():
        folder = args.output / name
        for part, rows in {**splits, **{"validation_"+k: v for k,v in role_rows.items()}}.items():
            write_pairs(folder / (part + ".tsv"), rows)
        columns = (0, 1) if direction == "both" else (0,)
        information = {str(c): selection_information(role_rows["selection"], known, c) for c in columns}
        assert all(v["queries"] > 1 and v["queries_without_distractors"] == 0 for v in information.values())
        entry = {"direction": direction, "uncertainty_unit": unit,
                 "sizes": {part: len(rows) for part, rows in splits.items()},
                 "unique_chains": {part: [len({p[c] for p in rows}) for c in (0,1)]
                                   for part,rows in splits.items()},
                 "validation_roles": {k: {"edges": len(v), "gamma_queries": len({g for g,d in v})}
                                      for k,v in role_rows.items()},
                 "selection_information": information,
                 "train_test_overlap": [len({p[c] for p in splits["train"]} &
                                            {p[c] for p in splits["test"]}) for c in (0,1)],
                 "output_sha256": {p.name: file_sha256(p) for p in sorted(folder.glob("*.tsv"))}}
        if name == "unseen_gamma_repaired":
            entry["unchanged_original_membership"] = {p: set(splits[p]) == set(read_pairs(source / (p+".tsv")))
                                                       for p in ("train", "validation", "test")}
            entry["original_sha256"] = {p: file_sha256(source/(p+".tsv")) for p in ("train", "validation", "test")}
        manifest["protocols"][name] = entry
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True)+"\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
