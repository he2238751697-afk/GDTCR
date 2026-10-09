"""Frozen tuning/calibration rules for recorded-pair recovery, not biology."""

from __future__ import annotations

import numpy as np

from .evaluation import ranked_generation_metrics


ALPHAS = (0., .25, .5, .75, 1.)


def score_profile(values):
    values = np.asarray(values, dtype=np.float64)
    if not np.isfinite(values).all():
        raise ValueError("Non-finite score cannot be calibrated")
    if not values.size:
        return {"mean": 0., "scale": 1., "n": 0, "constant_or_empty": True}
    scale = float(values.std())
    return {"mean": float(values.mean()), "scale": scale if scale > 0. else 1.,
            "n": len(values), "constant_or_empty": scale == 0.}


def standardized(values, profile):
    return (np.asarray(values, dtype=np.float64) - profile["mean"]) / profile["scale"]


def calibrated_scores(row, profile, alpha):
    values = {"likelihood": standardized(row["scores"]["likelihood"], profile["likelihood"])}
    if "ranker" in profile:
        if row["scores"].get("ranker") is None and row["candidates"]:
            raise ValueError("Ranker scores missing for nonempty candidates")
        values["ranker"] = standardized(row["scores"].get("ranker") or [], profile["ranker"])
        values["fused"] = (1 - alpha) * values["likelihood"] + alpha * values["ranker"]
    return values


def sorted_indices(row, values, indices):
    return sorted(indices, key=lambda index: (-float(values[index]), row["candidates"][index]))


def hit5(row, values, indices):
    positives = set(row["positives"])
    return float(any(row["candidates"][index] in positives
                     for index in sorted_indices(row, values, indices)[:5]))


def fit_fusion(tuning):
    """One shared alpha, with per-direction scales and equal direction weights."""
    profiles = {}
    has_ranker = any(row["scores"].get("ranker") is not None
                     for rows in tuning.values() for row in rows)
    for direction, rows in tuning.items():
        profiles[direction] = {}
        for method in (("likelihood", "ranker") if has_ranker else ("likelihood",)):
            values = [row["scores"][method][index] for row in rows
                      for index in row["groups"][row["reference_group"]]]
            profiles[direction][method] = score_profile(values)
    results = {}
    for alpha in ALPHAS if has_ranker else (0.,):
        by_direction = {}
        for direction, rows in tuning.items():
            hits = []
            for row in rows:
                scores = calibrated_scores(row, profiles[direction], alpha)
                values = scores["fused" if has_ranker else "likelihood"]
                hits.append(float(np.mean([hit5(row, values, row["groups"][group])
                                           for group in row["selection_groups"]])))
            by_direction[direction] = float(np.mean(hits)) if hits else 0.
        results[str(alpha)] = {"directions": by_direction,
                               "mean_hit_at_5": float(np.mean(list(by_direction.values())))}
    chosen = max((float(value) for value in results),
                 key=lambda alpha: (results[str(alpha)]["mean_hit_at_5"], -alpha))
    return {"alpha": chosen, "grid": results, "score_profiles": profiles,
            "ranker_present": has_ranker,
            "selection_metric": "equal-direction mean query-macro Hit@5; pool mode averages four small pools",
            "tie_rule": "smallest ranker weight", "scaling": "pooled tuning-candidate mean and population SD"}


def choose_threshold(scores, labels):
    scores, labels = np.asarray(scores, dtype=np.float64), np.asarray(labels, dtype=np.int8)
    if len(scores) != len(labels) or not np.isfinite(scores).all() or not np.isin(labels, (0, 1)).all():
        raise ValueError("Invalid calibration scores or labels")
    positives, negatives = int(labels.sum()), int(len(labels) - labels.sum())
    base = {"mode": "reject_all", "value": None, "positives": positives, "negatives": negatives,
            "balanced_accuracy": None, "tie_rule": "highest threshold, including reject-all"}
    if not positives or not negatives:
        return {**base, "reason": "no_recorded_positive" if not positives else "no_constructed_negative"}
    order = np.argsort(-scores, kind="stable")
    values, ordered_labels = scores[order], labels[order]
    ends = np.r_[np.flatnonzero(values[1:] != values[:-1]), len(values) - 1]
    true_positive = np.cumsum(ordered_labels)[ends]
    false_positive = ends + 1 - true_positive
    accuracy = .5 * (true_positive / positives + 1 - false_positive / negatives)
    best = {**base, "balanced_accuracy": .5, "reason": "best_balanced_accuracy"}
    for index, value in enumerate(accuracy):
        if value > best["balanced_accuracy"] + 1e-12:
            best.update(mode="score", value=float(values[ends[index]]), balanced_accuracy=float(value))
    return best


def accepted(values, threshold):
    values = np.asarray(values)
    if threshold["mode"] == "reject_all":
        return np.zeros(len(values), dtype=bool)
    if threshold["mode"] == "accept_all":
        return np.ones(len(values), dtype=bool)
    return values >= threshold["value"]


def curve_thresholds(scores):
    scores = np.asarray(scores, dtype=np.float64)
    cutoffs = [{"mode": "reject_all", "value": None}]
    if scores.size:
        cutoffs.extend({"mode": "score", "value": float(value)}
                       for value in sorted(set(np.quantile(scores, np.linspace(0., 1., 101))), reverse=True))
    cutoffs.append({"mode": "accept_all", "value": None})
    return cutoffs


def calibration_observations(rows, direction, profile, alpha, known_pairs):
    methods = ("likelihood", "ranker", "fused") if "ranker" in profile else ("likelihood",)
    scores, labels, omitted = {name: [] for name in methods}, [], 0
    for row in rows:
        values = calibrated_scores(row, profile, alpha)
        positives = set(row["positives"])
        for index in row["groups"][row["reference_group"]]:
            target = row["candidates"][index]
            pair = (row["source"], target) if direction == "gamma_to_delta" else (target, row["source"])
            if target not in positives and pair in known_pairs:
                omitted += 1
                continue
            labels.append(int(target in positives))
            for method in methods:
                scores[method].append(float(values[method][index]))
    return scores, labels, omitted


def fit_calibration(tuning, calibration, known_pairs):
    if set(tuning) != set(calibration):
        raise ValueError("Tuning and calibration directions differ")
    fusion = fit_fusion(tuning)
    thresholds = {}
    for direction, rows in calibration.items():
        tune_queries = {row["source"] for row in tuning[direction]}
        if tune_queries & {row["source"] for row in rows}:
            raise ValueError("Tuning and calibration query groups overlap")
        values, labels, omitted = calibration_observations(
            rows, direction, fusion["score_profiles"][direction], fusion["alpha"], known_pairs)
        thresholds[direction] = {"excluded_other_known_partners": omitted,
                                 "methods": {name: choose_threshold(scores, labels) for name, scores in values.items()},
                                 "curve_thresholds": {name: curve_thresholds(scores) for name, scores in values.items()}}
    return {"schema_version": 2, "fusion": fusion, "calibration": thresholds,
            "scope": "recorded-pair benchmark compatibility; not a biological probability"}


def rejection_metrics(row, values, indices, threshold):
    mask = accepted(values, threshold)
    selected = [index for index in sorted_indices(row, values, indices)
                if mask[index]]
    ordered = [row["candidates"][index] for index in selected]
    return {"accepted_query": float(bool(selected)), "accepted_candidates": len(selected),
            **ranked_generation_metrics(row["positives"], ordered)}


def acceptance_curves(rows, direction, settings, known_pairs):
    """Apply calibration-derived thresholds with no threshold selection on test."""
    fusion = settings["fusion"]
    profile, alpha = fusion["score_profiles"][direction], fusion["alpha"]
    threshold_sets = settings["calibration"][direction]["curve_thresholds"]
    output = {}
    for method, thresholds in threshold_sets.items():
        n = len(thresholds)
        query_accepted, query_hit5 = np.zeros(n), np.zeros(n)
        candidate_accepted, positives_accepted, negatives_accepted = np.zeros(n), np.zeros(n), np.zeros(n)
        n_candidates = n_positives = n_negatives = n_other_known = n_edges = 0
        cutoffs = np.asarray([item["value"] if item["mode"] == "score" else 0. for item in thresholds])
        for row in rows:
            values = calibrated_scores(row, profile, alpha)[method]
            indices = sorted_indices(row, values, row["groups"][row["reference_group"]])
            scores = np.asarray([values[index] for index in indices])
            positives = set(row["positives"])
            positive_flags, negative_flags = [], []
            for index in indices:
                target = row["candidates"][index]
                pair = (row["source"], target) if direction == "gamma_to_delta" else (target, row["source"])
                positive_flags.append(target in positives)
                negative_flags.append(target not in positives and pair not in known_pairs)
            positive_flags, negative_flags = np.asarray(positive_flags), np.asarray(negative_flags)
            cumulative_positive = np.r_[0, np.cumsum(positive_flags)]
            cumulative_negative = np.r_[0, np.cumsum(negative_flags)]
            counts = np.searchsorted(-scores, -cutoffs, side="right")
            for i, threshold in enumerate(thresholds):
                if threshold["mode"] == "reject_all":
                    counts[i] = 0
                elif threshold["mode"] == "accept_all":
                    counts[i] = len(indices)
            best = int(np.flatnonzero(positive_flags)[0] + 1) if positive_flags.any() else len(indices) + 1
            query_accepted += counts > 0
            query_hit5 += (best <= 5) & (best <= counts)
            candidate_accepted += counts
            positives_accepted += cumulative_positive[counts]
            negatives_accepted += cumulative_negative[counts]
            n_candidates += len(indices)
            n_positives += int(positive_flags.sum())
            n_negatives += int(negative_flags.sum())
            n_other_known += len(indices) - int(positive_flags.sum()) - int(negative_flags.sum())
            n_edges += len(positives)
        output[method] = {"n_queries": len(rows), "n_recorded_edges": n_edges,
                          "n_candidates": n_candidates, "recorded_positive_candidates": n_positives,
                          "constructed_unrecorded_candidates": n_negatives,
                          "other_known_partner_candidates": n_other_known,
                          "threshold_origin": "held-out calibration candidate quantiles plus endpoint policies",
                          "points": [{**threshold,
                                      "accepted_queries": int(query_accepted[i]),
                                      "accepted_query_fraction": float(query_accepted[i] / max(len(rows), 1)),
                                      "recorded_hit_at_5": float(query_hit5[i] / max(len(rows), 1)),
                                      "recorded_hit_at_5_among_accepted": float(query_hit5[i] / query_accepted[i]) if query_accepted[i] else None,
                                      "accepted_candidates": int(candidate_accepted[i]),
                                      "recorded_candidate_recall": float(positives_accepted[i] / n_positives) if n_positives else None,
                                      "unrecorded_candidate_acceptance": float(negatives_accepted[i] / n_negatives) if n_negatives else None,
                                      "edge_weighted_recorded_partner_recovery": float(positives_accepted[i] / max(n_edges, 1))}
                                     for i, threshold in enumerate(thresholds)]}
    return output
