#!/usr/bin/env python3
"""Create compact publication evidence from audited, frozen evaluations.

Uncertainty is conditional on fitted checkpoints and their saved samples.
Resample complete pair-graph components; compare methods on the same queries.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gdtcr.data import component_groups, read_pairs
from gdtcr.fileio import file_sha256
from gdtcr.metrics import generation_metrics


def random_hit(n_candidates, n_positive, k):
    """Exact probability of >=1 recorded positive in uniform top-K."""
    k = min(k, n_candidates)
    if k > n_candidates - n_positive:
        return 1.0
    miss = 1.0
    for i in range(k):
        miss *= (n_candidates - n_positive - i) / (n_candidates - i)
    return 1.0 - miss


def random_ap(n_candidates, n_positive):
    if n_candidates == 1:
        return float(n_positive > 0)
    harmonic = sum(1.0 / k for k in range(1, n_candidates + 1))
    return (harmonic + (n_positive - 1) * (n_candidates - harmonic) / (n_candidates - 1)) / n_candidates


def component_lookup(pair_path):
    pairs = read_pairs(pair_path)
    lookup = {}
    for component, indices in enumerate(component_groups(pairs)):
        for index in indices:
            gamma, delta = pairs[index]
            lookup["gamma", gamma] = component
            lookup["delta", delta] = component
    return lookup


def clustered_interval(values, clusters, replicates=2000, seed=20260930):
    values = np.asarray(values, dtype=float)
    unique = sorted(set(clusters))
    cluster_index = {c: i for i, c in enumerate(unique)}
    indices = np.array([cluster_index[c] for c in clusters])
    totals = np.bincount(indices, weights=values, minlength=len(unique))
    counts = np.bincount(indices, minlength=len(unique))
    rng = np.random.default_rng(seed)
    weights = rng.multinomial(len(unique), np.full(len(unique), 1.0 / len(unique)), size=replicates)
    estimates = (weights @ totals) / (weights @ counts)
    return {"estimate": float(values.mean()), "lower": float(np.quantile(estimates, .025)),
            "upper": float(np.quantile(estimates, .975)), "n_queries": len(values),
            "n_components": len(unique), "method": "component_cluster_percentile_bootstrap"}


def wilson_interval(successes, total):
    # Descriptive iid-binomial reference only; not the primary interval when
    # queries are dependent. Unlike a percentile bootstrap, nonzero at 0 hits.
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return {"lower": max(0.0, center - half), "upper": min(1.0, center + half),
            "assumption": "independent_queries_binomial_reference_only"}


def free_metrics(row):
    rankings = [(name, row[key]) for name, key in (
        ("sample_order", "unique_candidates"), ("likelihood", "likelihood_ranked_candidates"),
        ("ranker", "reranked_candidates")) if key in row]
    return generation_metrics(row, rankings, verify_candidates=True)


def summarize_free(path, replicates):
    payload = json.loads(path.read_text())
    lookup = component_lookup(ROOT / payload["pairs"])
    result = {"path": str(path.relative_to(ROOT)), "sha256": file_sha256(path),
              "pairs": payload["pairs"], "directions": {}}
    for direction, rows in payload["rows"].items():
        chain = "gamma" if direction == "gamma_to_delta" else "delta"
        clusters = [lookup[chain, row["source"]] for row in rows]
        metrics = [free_metrics(row) for row in rows]
        intervals = {metric: clustered_interval([row[metric] for row in metrics], clusters, replicates)
                     for metric in metrics[0]}
        for metric in metrics[0]:
            if metric == "coverage" or "_hit_at_" in metric:
                values = [row[metric] for row in metrics]
                assert all(value in (0.0, 1.0) for value in values)
                events = int(sum(values))
                intervals[metric]["events"] = events
                intervals[metric]["iid_wilson_reference"] = wilson_interval(events, len(rows))
        # Compare ranker to likelihood and to sample order on identical rows.
        comparisons = {}
        if payload.get("ranker"):
            for baseline in ("likelihood", "sample_order"):
                key = f"{baseline}_hit_at_5"
                if key in metrics[0]:
                    differences = [r["ranker_hit_at_5"] - r[key] for r in metrics]
                    comparisons[f"ranker_minus_{baseline}_H5"] = clustered_interval(differences, clusters, replicates)
        result["directions"][direction] = {
            "n_queries": len(rows), "n_components": len(set(clusters)),
            "conditional_token_nll": payload["directions"][direction]["conditional_token_nll"],
            "unique_candidates_mean": sum(len(row["unique_candidates"]) for row in rows) / len(rows),
            "intervals": intervals, "paired_differences": comparisons,
            "ranker_present": bool(payload.get("ranker")),
        }
    return result


def compare_free(left_path, right_path, replicates):
    left = json.loads(left_path.read_text())
    right = json.loads(right_path.read_text())
    if left["pairs"] != right["pairs"]:
        raise ValueError("Paired comparison requires the same split")
    lookup = component_lookup(ROOT / left["pairs"])
    output = {}
    for direction, rows in left["rows"].items():
        chain = "gamma" if direction == "gamma_to_delta" else "delta"
        other = {row["source"]: row for row in right["rows"][direction]}
        if set(other) != {row["source"] for row in rows}:
            raise ValueError("Paired comparison requires identical queries")
        clusters = [lookup[chain, row["source"]] for row in rows]
        diffs = defaultdict(list)
        for row in rows:
            if set(row["positives"]) != set(other[row["source"]]["positives"]):
                raise ValueError("Positive labels differ across paired evaluations")
            a, b = free_metrics(row), free_metrics(other[row["source"]])
            for metric in ("coverage", "sample_order_hit_at_5", "likelihood_hit_at_5"):
                diffs[metric].append(a[metric] - b[metric])
        output[direction] = {metric: clustered_interval(values, clusters, replicates)
                             for metric, values in diffs.items()}
    return {"left": str(left_path.relative_to(ROOT)), "right": str(right_path.relative_to(ROOT)),
            "directions": output}


def summarize_pools(path, replicates):
    payload = json.loads(path.read_text())
    lookup = component_lookup(ROOT / payload["pairs"])
    directions = {}
    for direction, pools in payload["directions"].items():
        chain = "gamma" if direction == "gamma_to_delta" else "delta"
        directions[direction] = {}
        for pool, entry in pools.items():
            rows = entry["rows"]
            clusters = [lookup[chain, row["source"]] for row in rows]
            result = {"n_queries": len(rows), "generator": entry["generator"], "ranker": entry.get("ranker"),
                      "random_expected_hit_at_5": sum(random_hit(len(r["candidates"]), len(r["positives"]), 5)
                                                      for r in rows) / len(rows),
                      "random_expected_macro_AP": sum(random_ap(len(r["candidates"]), len(r["positives"]))
                                                      for r in rows) / len(rows)}
            if "ranker" in entry:
                result["ranker_minus_generator_H5"] = clustered_interval(
                    [row["ranker"]["hit_at_5"] - row["generator"]["hit_at_5"] for row in rows], clusters, replicates)
            directions[direction][pool] = result
    return {"path": str(path.relative_to(ROOT)), "directions": directions}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "artifacts/evaluations/audited")
    parser.add_argument("--output", type=Path, default=ROOT / "paper/results/evidence.json")
    parser.add_argument("--bootstrap-replicates", type=int, default=2000)
    args = parser.parse_args()
    # Normalize CLI paths once so relative invocations work from any cwd and
    # all stored artifact paths remain relative to the repository root.
    args.root = args.root.expanduser().resolve()
    args.output = args.output.expanduser().resolve()
    paths = sorted(args.root.glob("*/seed-*/test.json"))
    free = {str(p.parent.parent.name) + "/" + p.parent.name: summarize_free(p, args.bootstrap_replicates) for p in paths}
    comparisons = {}
    for left, right in (("a800_early", "unconditional_a800_unconditional"), ("a800_early", "a800_shuffled"),
                        ("a800_early", "a800_random"), ("source_holdout", "source_holdout_constant"),
                        ("source_holdout", "source_holdout_shuffled"),
                        ("source_shared", "source_shared_constant"),
                        ("source_shared", "source_shared_shuffled")):
        for seed in (0, 1):
            a, b = (args.root / name / f"seed-{seed}" / "test.json" for name in (left, right))
            if a.exists() and b.exists():
                comparisons[f"{left}_minus_{right}/seed-{seed}"] = compare_free(a, b, args.bootstrap_replicates)
    pools = {p.parent.name + "/" + p.stem: summarize_pools(p, args.bootstrap_replicates)
             for p in sorted(args.root.glob("candidate_pools_*/seed-*.json")) if "validation" not in p.parent.name}
    output = {"bootstrap_replicates": args.bootstrap_replicates, "uncertainty": "conditional_on_fitted_model_and_saved_samples",
              "free_generation": free, "paired_free_generation_comparisons": comparisons, "fixed_pools": pools}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(args.output, "free runs", len(free), "comparisons", len(comparisons), "pool runs", len(pools))


if __name__ == "__main__":
    main()
