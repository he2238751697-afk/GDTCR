"""Sequence distances and query-level summaries with no model dependency.

Query bootstrap is deliberately separate from component-cluster bootstrap.
The legacy percentile indexing and random-number sequence are preserved.
"""

import random


def levenshtein(left: str, right: str) -> int:
    """Unit-cost edit distance, using Myers' recurrence for short sequences."""
    if not left or not right:
        return max(len(left), len(right))
    if len(left) <= 63 and len(right) <= 63:
        if len(left) > len(right):
            left, right = right, left
        masks = {}
        for index, char in enumerate(left):
            masks[char] = masks.get(char, 0) | (1 << index)
        high_bit = 1 << (len(left) - 1)
        bit_mask = (1 << len(left)) - 1
        positive = bit_mask
        negative = 0
        score = len(left)
        for char in right:
            equal = masks.get(char, 0)
            vertical = equal | negative
            horizontal = (((equal & positive) + positive) ^ positive) | equal
            add = negative | ~(horizontal | positive)
            remove = positive & horizontal
            if add & high_bit:
                score += 1
            elif remove & high_bit:
                score -= 1
            add = ((add << 1) | 1) & bit_mask
            remove = (remove << 1) & bit_mask
            positive = (remove | ~(vertical | add)) & bit_mask
            negative = (add & vertical) & bit_mask
        return score
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, 1):
        current = [i]
        for j, right_char in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[j] + 1,
                               previous[j - 1] + (left_char != right_char)))
        previous = current
    return previous[-1]


def normalized_distance(left: str, right: str) -> float:
    return levenshtein(left, right) / max(len(left), len(right), 1)


def generation_metrics(row, rankings, *, include_unique=False, verify_candidates=False):
    positives = set(row["positives"])
    candidates = row["unique_candidates"]
    result = {"coverage": float(bool(positives & set(candidates)))}
    if include_unique:
        result["unique_candidates"] = len(candidates)
    for name, ordered in rankings:
        if verify_candidates:
            assert set(ordered) == set(candidates), f"{name} changes candidate membership"
        for k in (1, 5, 10):
            hit = float(bool(positives & set(ordered[:k])))
            if verify_candidates:
                assert hit <= result["coverage"]
            result[f"{name}_hit_at_{k}"] = hit
            result[f"{name}_recall_at_{k}"] = len(positives & set(ordered[:k])) / max(len(positives), 1)
    return result


def row_metrics(row):
    return generation_metrics(row, (("raw", row["unique_candidates"]),
                                    ("reranked", row["reranked_candidates"])),
                              include_unique=True)


def summarize_metric_rows(metric_rows):
    if not metric_rows:
        return {}
    return {key: sum(row[key] for row in metric_rows) / len(metric_rows)
            for key in metric_rows[0]}


def bootstrap_metric_rows(metric_rows, replicates, seed):
    if not metric_rows:
        return {}
    rng = random.Random(seed)
    keys = tuple(metric_rows[0])
    metrics = {key: [] for key in keys}
    n_rows = len(metric_rows)
    for _ in range(replicates):
        totals = dict.fromkeys(keys, 0.0)
        for _ in range(n_rows):
            sampled = metric_rows[rng.randrange(n_rows)]
            for key in keys:
                totals[key] += sampled[key]
        for key in keys:
            metrics[key].append(totals[key] / n_rows)
    means = summarize_metric_rows(metric_rows)
    output = {}
    for key, values in metrics.items():
        values.sort()
        output[key] = {"mean": means[key],
                       "lower": values[int(0.025 * (len(values) - 1))],
                       "upper": values[int(0.975 * (len(values) - 1))]}
    return output


def rank_summary(candidates, positives, scores, descending):
    order = sorted(range(len(candidates)), key=lambda index: (-scores[index] if descending else scores[index], candidates[index]))
    ranked = [candidates[index] for index in order]
    positive_set = set(positives)
    ranks = [index + 1 for index, candidate in enumerate(ranked) if candidate in positive_set]
    best = min(ranks, default=None)
    return {
        "hit_at_1": float(best is not None and best <= 1),
        "hit_at_5": float(best is not None and best <= 5),
        "hit_at_10": float(best is not None and best <= 10),
        **{f"recall_at_{k}": len(positive_set & set(ranked[:k])) / max(len(positive_set), 1)
           for k in (1, 5, 10)},
        "mrr": 1.0 / best if best is not None else 0.0,
        "mean_positive_rank": sum(ranks) / len(ranks) if ranks else len(candidates) + 1,
        "best_positive_rank": best,
        "ranked_candidates": ranked,
    }
