"""Paired component/source-group bootstrap for saved query-level outcomes."""

import math

import numpy as np


def wilson_reference(events, n):
    if not n:
        return None
    z = 1.959963984540054
    p = events / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return {"lower": max(0., center - half), "upper": min(1., center + half),
            "assumption": "iid binomial reference only; not the primary clustered interval"}


def cluster_intervals(rows, clusters, *, weights=None, replicates=2000, seed=20260930,
                      binary_metrics=()):
    if len(rows) != len(clusters):
        raise ValueError("Each query needs exactly one cluster")
    if not rows:
        return {"n_queries": 0, "n_clusters": 0, "metrics": {}, "empty": True}
    keys = sorted(rows[0])
    if any(set(row) != set(keys) for row in rows):
        raise ValueError("Metric columns differ across queries")
    values = np.asarray([[row[key] for key in keys] for row in rows], dtype=np.float64)
    if not np.isfinite(values).all():
        raise ValueError("Non-finite query outcome")
    weight = np.ones(len(rows)) if weights is None else np.asarray(weights, dtype=np.float64)
    if weight.shape != (len(rows),) or not np.isfinite(weight).all() or (weight <= 0).any():
        raise ValueError("Bootstrap weights must be positive and one per query")
    labels = sorted(set(clusters))
    lookup = {label: index for index, label in enumerate(labels)}
    index = np.asarray([lookup[label] for label in clusters])
    totals = np.zeros((len(labels), len(keys)))
    denominators = np.bincount(index, weights=weight, minlength=len(labels))
    np.add.at(totals, index, values * weight[:, None])
    rng = np.random.default_rng(seed)
    draws = rng.multinomial(len(labels), np.full(len(labels), 1 / len(labels)), size=replicates)
    sampled = (draws @ totals) / (draws @ denominators)[:, None]
    mean = (values * weight[:, None]).sum(axis=0) / weight.sum()
    lower, upper = np.quantile(sampled, (.025, .975), axis=0)
    result = {}
    for position, key in enumerate(keys):
        result[key] = {"estimate": float(mean[position]), "lower": float(lower[position]),
                       "upper": float(upper[position])}
        if key in binary_metrics:
            column = values[:, position]
            if not np.isin(column, (0., 1.)).all() or weights is not None:
                raise ValueError("Binomial references require unweighted binary query events")
            events = int(column.sum())
            result[key].update(events=events, denominator=len(rows),
                               iid_wilson_reference=wilson_reference(events, len(rows)),
                               zero_event=events == 0)
    return {"n_queries": len(rows), "n_clusters": len(labels), "weight_sum": float(weight.sum()),
            "bootstrap_replicates": replicates, "bootstrap_seed": seed,
            "method": "paired cluster percentile bootstrap", "metrics": result,
            "single_cluster": len(labels) < 2,
            "uncertainty": "conditional on fitted models and saved samples; repeated splits/seeds are not independent subjects"}


def bidirectional_intervals(rows_by_direction, clusters_by_direction, *, replicates=2000, seed=20260930):
    """Average direction-specific query means using the same cluster resample."""
    directions = sorted(rows_by_direction)
    if not directions or any(not rows_by_direction[d] for d in directions):
        return {"empty": True, "metrics": {}}
    keys = sorted(set.intersection(*(set(rows_by_direction[d][0]) for d in directions)))
    cluster_sets = [set(clusters_by_direction[d]) for d in directions]
    if any(value != cluster_sets[0] for value in cluster_sets):
        raise ValueError("Joint directional bootstrap needs the same paired-graph clusters")
    labels = sorted(cluster_sets[0])
    lookup = {label: index for index, label in enumerate(labels)}
    rng = np.random.default_rng(seed)
    draws = rng.multinomial(len(labels), np.full(len(labels), 1 / len(labels)), size=replicates)
    estimates = np.zeros((replicates, len(keys)))
    point = np.zeros(len(keys))
    for direction in directions:
        rows, clusters = rows_by_direction[direction], clusters_by_direction[direction]
        if len(rows) != len(clusters):
            raise ValueError("Query and cluster counts differ")
        values = np.asarray([[row[key] for key in keys] for row in rows], dtype=np.float64)
        if not np.isfinite(values).all():
            raise ValueError("Non-finite query outcome")
        index = np.asarray([lookup[label] for label in clusters])
        totals = np.zeros((len(labels), len(keys)))
        np.add.at(totals, index, values)
        counts = np.bincount(index, minlength=len(labels))
        estimates += (draws @ totals) / (draws @ counts)[:, None] / len(directions)
        point += values.mean(axis=0) / len(directions)
    lower, upper = np.quantile(estimates, (.025, .975), axis=0)
    return {"directions": directions, "n_queries": {d: len(rows_by_direction[d]) for d in directions},
            "n_clusters": len(labels), "single_cluster": len(labels) < 2,
            "bootstrap_replicates": replicates, "bootstrap_seed": seed,
            "method": "equal-direction query-macro mean with a shared paired-component bootstrap",
            "metrics": {key: {"estimate": float(point[i]), "lower": float(lower[i]), "upper": float(upper[i])}
                        for i, key in enumerate(keys)}}
