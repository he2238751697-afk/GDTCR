#!/usr/bin/env python3
"""Evaluate target-frequency and edit-distance pair retrieval baselines.

The baselines use the same strict component split as the trained models.  For
each test query, candidates are all unique target-chain sequences in the test
split.  The frequency baseline ignores the query and ranks targets by their
training degree.  The edit-distance baseline scores a candidate with the
closest training pair among a reproducible pool of source-chain neighbours.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gdtcr.data import read_pairs
from gdtcr.metrics import normalized_distance


def rank_metrics(query_targets, order_by):
    hits = {1: 0, 5: 0, 10: 0}
    covered = 0
    output_rows = []
    for query in sorted(query_targets):
        candidates = order_by(query)
        positives = query_targets[query]
        covered += int(any(candidate in positives for candidate in candidates))
        for k in hits:
            hits[k] += int(any(candidate in positives for candidate in candidates[:k]))
        output_rows.append({
            "source": query,
            "positives": sorted(positives),
            "ranked_candidates": candidates,
            "best_positive_rank": min(
                (candidates.index(positive) + 1 for positive in positives
                 if positive in candidates),
                default=None,
            ),
        })
    count = max(len(query_targets), 1)
    return {
        "n_queries": len(query_targets),
        "candidate_coverage": covered / count,
        **{f"hit_at_{k}": value / count for k, value in hits.items()},
        "rows": output_rows,
    }


def evaluate_direction(train_pairs, test_pairs, source_chain, source_neighbors):
    if source_chain == "gamma":
        target_chain = "delta"
        train_source = [gamma for gamma, _ in train_pairs]
        train_target = [delta for _, delta in train_pairs]
        test_target = [delta for _, delta in test_pairs]
    else:
        target_chain = "gamma"
        train_source = [delta for _, delta in train_pairs]
        train_target = [gamma for gamma, _ in train_pairs]
        test_target = [gamma for gamma, _ in test_pairs]

    query_targets = defaultdict(set)
    for gamma, delta in test_pairs:
        query_targets[gamma if source_chain == "gamma" else delta].add(
            delta if source_chain == "gamma" else gamma)
    candidates = sorted(set(test_target))
    train_target_degree = Counter(train_target)
    # Stable lexical tie-breaking makes the result independent of hash order.
    frequency_order = sorted(candidates, key=lambda target: (-train_target_degree[target], target))

    frequency = rank_metrics(
        query_targets,
        lambda _query: list(frequency_order),
    )

    source_target_pairs = list(zip(train_source, train_target))
    source_cache = {}
    target_cache = {}

    def source_distances(query):
        if query not in source_cache:
            distances = sorted(
                ((normalized_distance(query, source), index)
                 for index, (source, _) in enumerate(source_target_pairs)),
                key=lambda item: (item[0], source_target_pairs[item[1]]),
            )
            source_cache[query] = distances[:source_neighbors]
        return source_cache[query]

    def target_distance(candidate, train_index):
        key = (candidate, train_index)
        if key not in target_cache:
            target_cache[key] = normalized_distance(candidate, source_target_pairs[train_index][1])
        return target_cache[key]

    def edit_order(query):
        selected = source_distances(query)
        scored = []
        for candidate in candidates:
            score = min(
                source_distance + target_distance(candidate, train_index)
                for source_distance, train_index in selected
            )
            scored.append((score, candidate))
        return [candidate for _, candidate in sorted(scored, key=lambda item: (item[0], item[1]))]

    edit = rank_metrics(query_targets, edit_order)
    # Keep only the metrics/rows needed downstream and expose the approximation
    # explicitly: the source-neighbour pool avoids an intractable all-pairs scan.
    edit["source_neighbors"] = source_neighbors
    return {
        "direction": f"{source_chain}_to_{target_chain}",
        "n_train_pairs": len(train_pairs),
        "n_test_pairs": len(test_pairs),
        "n_test_candidates": len(candidates),
        "target_frequency": {key: value for key, value in frequency.items() if key != "rows"},
        "edit_distance": {key: value for key, value in edit.items() if key != "rows"},
        "rows": {
            "target_frequency": frequency["rows"],
            "edit_distance": edit["rows"],
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--test", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-neighbors", type=int, default=1,
                        help="Training-pair neighbour pool for edit-distance scoring")
    args = parser.parse_args()
    if args.source_neighbors < 1:
        raise ValueError("source-neighbors must be positive")
    train_pairs = read_pairs(args.train)
    test_pairs = read_pairs(args.test)
    result = {
        "arguments": {key: str(value) if isinstance(value, Path) else value
                      for key, value in vars(args).items()},
        "train": str(args.train),
        "test": str(args.test),
        "directions": {},
    }
    for source_chain in ("gamma", "delta"):
        result["directions"][source_chain] = evaluate_direction(
            train_pairs, test_pairs, source_chain, args.source_neighbors)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: {
        "target_frequency": value["target_frequency"],
        "edit_distance": value["edit_distance"],
    } for key, value in result["directions"].items()}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
