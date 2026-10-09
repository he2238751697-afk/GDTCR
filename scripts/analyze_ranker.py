#!/usr/bin/env python3
"""Audit fixed-pool ranking scores and validation-selected rejection thresholds.

The input files are produced by ``evaluate_candidate_pools.py``.  A candidate
is labelled positive only when it is a recorded pair in that file; all other
pool members are constructed, unrecorded candidates.  The output therefore
describes this diagnostic classification task and must not be read as a
biological specificity estimate.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def _average_ranks(values: list[float]) -> list[float]:
    """Return one-based average ranks, retaining ties exactly."""
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        value = values[order[start]]
        while end < len(order) and values[order[end]] == value:
            end += 1
        rank = (start + 1 + end) / 2.0
        for position in order[start:end]:
            ranks[position] = rank
        start = end
    return ranks


def roc_auc(labels: list[int], scores: list[float]) -> float | None:
    """Compute ROC AUC with tie handling, without a third-party dependency."""
    positives = sum(labels)
    negatives = len(labels) - positives
    if not positives or not negatives:
        return None
    ranks = _average_ranks(scores)
    positive_rank_sum = sum(rank for rank, label in zip(ranks, labels) if label)
    return (positive_rank_sum - positives * (positives + 1) / 2.0) / (positives * negatives)


def average_precision(labels: list[int], scores: list[float]) -> float | None:
    """Compute non-interpolated AP, treating tied scores as one threshold.

    Summing precision at individual positive ranks would make tied-score AP
    depend on input (here lexical candidate) order rather than model scores.
    """
    positives = sum(labels)
    negatives = len(labels) - positives
    if not positives or not negatives:
        return None
    order = sorted(range(len(labels)), key=lambda index: (-scores[index], index))
    found = 0
    weighted_precision = 0.0
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and scores[order[end]] == scores[order[start]]:
            end += 1
        group_positive = sum(labels[index] for index in order[start:end])
        found += group_positive
        weighted_precision += group_positive * found / end
        start = end
    return weighted_precision / positives


def _rows_to_labels_scores(rows, score_name: str):
    labels = []
    scores = []
    query_values = []
    for row in rows:
        positives = set(row["positives"])
        candidates = row["candidates"]
        raw_scores = row[f"{score_name}_scores"]
        if len(candidates) != len(raw_scores):
            raise ValueError(f"candidate/score length mismatch for {score_name}")
        row_labels = [int(candidate in positives) for candidate in candidates]
        # Conditional NLL is lower for a better candidate; invert it so all
        # downstream threshold and AUC code uses the same high-is-positive scale.
        row_scores = [(-value if score_name == "generator" else value)
                      for value in raw_scores]
        labels.extend(row_labels)
        scores.extend(row_scores)
        query_values.append((row_labels, row_scores))
    return labels, scores, query_values


def score_summary(rows, score_name: str) -> dict:
    labels, scores, query_values = _rows_to_labels_scores(rows, score_name)
    query_auc = [roc_auc(labels_, scores_) for labels_, scores_ in query_values]
    query_ap = [average_precision(labels_, scores_) for labels_, scores_ in query_values]
    query_auc = [value for value in query_auc if value is not None]
    query_ap = [value for value in query_ap if value is not None]
    return {
        "n_queries": len(rows),
        "n_candidates": len(labels),
        "n_positive": sum(labels),
        "n_constructed_negative": len(labels) - sum(labels),
        "query_auc_macro": sum(query_auc) / max(len(query_auc), 1),
        "query_average_precision_macro": sum(query_ap) / max(len(query_ap), 1),
        "candidate_auc_micro": roc_auc(labels, scores),
        "candidate_average_precision_micro": average_precision(labels, scores),
        "score_min": min(scores) if scores else None,
        "score_max": max(scores) if scores else None,
    }


def _confusion(labels: list[int], scores: list[float], threshold: float) -> dict:
    predicted = [score >= threshold for score in scores]
    tp = sum(label and prediction for label, prediction in zip(labels, predicted))
    fp = sum((not label) and prediction for label, prediction in zip(labels, predicted))
    positives = sum(labels)
    negatives = len(labels) - positives
    fn = positives - tp
    tn = negatives - fp
    tpr = tp / positives if positives else 0.0
    fpr = fp / negatives if negatives else 0.0
    precision = tp / (tp + fp) if tp + fp else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "recall": tpr, "constructed_negative_accept_rate": fpr,
            "precision": precision, "balanced_accuracy": (tpr + (1.0 - fpr)) / 2.0}


def select_threshold(labels: list[int], scores: list[float]) -> dict:
    """Choose a validation threshold by maximum balanced accuracy.

    Every candidate score and an all-rejected cutoff are considered.  Ties
    prefer the larger cutoff, which yields the more conservative rule.
    """
    if not labels or not any(labels) or all(labels):
        raise ValueError("threshold selection needs both positive and negative labels")
    if len(labels) != len(scores) or any(not math.isfinite(score) for score in scores):
        raise ValueError("threshold selection needs aligned, finite scores")
    positives = sum(labels)
    negatives = len(labels) - positives
    # Add tied scores as one group.  This computes the same cutoff sweep as
    # repeated calls to _confusion, but in O(n log n) instead of O(n^2).
    order = sorted(range(len(scores)), key=lambda index: scores[index], reverse=True)
    true_positive = 0
    false_positive = 0
    best_threshold = math.nextafter(max(scores), math.inf)
    best_balanced_accuracy = 0.5
    start = 0
    while start < len(order):
        end = start + 1
        threshold = scores[order[start]]
        while end < len(order) and scores[order[end]] == threshold:
            end += 1
        group_positive = sum(labels[index] for index in order[start:end])
        true_positive += group_positive
        false_positive += end - start - group_positive
        recall = true_positive / positives
        false_positive_rate = false_positive / negatives
        balanced_accuracy = (recall + (1.0 - false_positive_rate)) / 2.0
        # Scores are visited from high to low, so retaining the first tied
        # optimum implements the documented conservative tie break.
        if balanced_accuracy > best_balanced_accuracy:
            best_balanced_accuracy = balanced_accuracy
            best_threshold = threshold
        start = end
    threshold = best_threshold
    metrics = _confusion(labels, scores, threshold)
    return {"threshold": threshold, "selection": "maximum_validation_balanced_accuracy",
            **metrics}


def apply_threshold(rows, score_name: str, threshold: float) -> dict:
    labels, scores, query_values = _rows_to_labels_scores(rows, score_name)
    result = _confusion(labels, scores, threshold)
    accepted_per_query = []
    accepted_positive_queries = 0
    any_accepted_queries = 0
    for query_labels, query_scores in query_values:
        accepted = [score >= threshold for score in query_scores]
        accepted_per_query.append(sum(accepted))
        if any(accepted):
            any_accepted_queries += 1
        if any(label and is_accepted for label, is_accepted in zip(query_labels, accepted)):
            accepted_positive_queries += 1
    n_queries = len(query_values)
    result.update({
        "threshold": threshold,
        "accepted_candidates_per_query": sum(accepted_per_query) / max(n_queries, 1),
        "queries_with_any_accept": any_accepted_queries / max(n_queries, 1),
        "queries_with_accepted_positive": accepted_positive_queries / max(n_queries, 1),
    })
    return result


def analyze(validation_path: Path, evaluation_path: Path) -> dict:
    validation = json.loads(validation_path.read_text())
    evaluation = json.loads(evaluation_path.read_text())
    directions = {}
    for direction, validation_pools in validation["directions"].items():
        test_pools = evaluation["directions"].get(direction, {})
        directions[direction] = {}
        for pool, validation_entry in validation_pools.items():
            if pool not in test_pools:
                raise ValueError(f"missing test pool {direction}/{pool}")
            test_entry = test_pools[pool]
            score_names = ["generator"]
            if validation_entry["rows"] and "ranker_scores" in validation_entry["rows"][0]:
                score_names.append("ranker")
            pool_result = {}
            for score_name in score_names:
                validation_rows = validation_entry["rows"]
                test_rows = test_entry["rows"]
                validation_labels, validation_scores, _ = _rows_to_labels_scores(
                    validation_rows, score_name)
                threshold = select_threshold(validation_labels, validation_scores)
                pool_result[score_name] = {
                    "validation_scores": score_summary(validation_rows, score_name),
                    "test_scores": score_summary(test_rows, score_name),
                    "validation_threshold": threshold,
                    "test_at_validation_threshold": apply_threshold(
                        test_rows, score_name, threshold["threshold"]),
                }
            directions[direction][pool] = pool_result
    return {
        "validation": str(validation_path),
        "evaluation": str(evaluation_path),
        "negative_definition": validation.get("negative_definition", evaluation.get(
            "negative_definition", "constructed unrecorded candidate")),
        "directions": directions,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.validation, args.evaluation)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    for direction, pools in result["directions"].items():
        for pool, scores in pools.items():
            compact = {name: {"auc": values["test_scores"]["candidate_auc_micro"],
                              "ap": values["test_scores"]["candidate_average_precision_micro"],
                              "threshold": values["validation_threshold"]["threshold"],
                              "test_recall": values["test_at_validation_threshold"]["recall"],
                              "test_negative_accept": values["test_at_validation_threshold"][
                                  "constructed_negative_accept_rate"]}
                       for name, values in scores.items()}
            print(direction, pool, json.dumps(compact, sort_keys=True))


if __name__ == "__main__":
    main()
