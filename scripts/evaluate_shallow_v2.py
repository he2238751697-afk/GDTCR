#!/usr/bin/env python3
"""Training-only length/motif logistic control on frozen candidate pools."""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

import joblib
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gdtcr.data import read_pairs
from gdtcr.fileio import file_sha256
from gdtcr.metrics import rank_summary
from gdtcr.negatives import TrainingNegativeSampler
from gdtcr.provenance import begin_run, finish_run


DIRECTIONS = ("gamma_to_delta", "delta_to_gamma")
ROLES = ("validation_selection", "validation_tuning", "validation_calibration", "test")
POOLS = ("random", "length", "motif", "edit")
METRICS = ("hit_at_1", "hit_at_5", "hit_at_10", "recall_at_1", "recall_at_5",
           "recall_at_10", "mrr", "mean_positive_rank")
C_VALUES = (0.1, 1.0, 10.0)


def pair_features(gamma, delta):
    result = {"gamma_length": len(gamma) / 35, "delta_length": len(delta) / 35,
              "length_gap": abs(len(gamma) - len(delta)) / 35}
    for index in (0, 1, 2, -3, -2, -1):
        label = str(index)
        g, d = gamma[index], delta[index]
        result[f"gamma_{label}={g}"] = 1
        result[f"delta_{label}={d}"] = 1
        result[f"pair_{label}={g}:{d}"] = 1
        result[f"same_{label}"] = int(g == d)
    return result


def load_pool(path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def train_models(pairs, seed):
    sampler = TrainingNegativeSampler(pairs, "mixed")
    negatives = sampler.sample(pairs, 3, seed)
    if len(negatives) != 3 * len(pairs):
        raise ValueError("Shallow baseline did not obtain the frozen 1:3 class ratio")
    vectorizer = DictVectorizer(sparse=True)
    matrix = vectorizer.fit_transform(pair_features(*pair) for pair in [*pairs, *negatives])
    labels = [1] * len(pairs) + [0] * len(negatives)
    models = {c: LogisticRegression(C=c, solver="liblinear", max_iter=500,
                                    random_state=seed).fit(matrix, labels)
              for c in C_VALUES}
    return vectorizer, models, {"negative_counts": dict(sampler.stats),
                                "positives": len(pairs), "constructed_negatives": len(negatives),
                                "feature_count": matrix.shape[1]}


def score_targets(model, vectorizer, direction, source, targets, batch_size=4096):
    scores = []
    for start in range(0, len(targets), batch_size):
        batch = targets[start:start + batch_size]
        pairs = ((source, target) if direction == "gamma_to_delta" else (target, source)
                 for target in batch)
        matrix = vectorizer.transform(pair_features(*pair) for pair in pairs)
        scores.extend(model.decision_function(matrix).tolist())
    return scores


def evaluate_role(pool, model, vectorizer, directions):
    output = {}
    for direction in directions:
        entry = pool["directions"][direction]
        universe = entry["target_universe"]
        lookup = {target: index for index, target in enumerate(universe)}
        rows = []
        for row in entry["rows"]:
            scores = score_targets(model, vectorizer, direction, row["source"], universe)
            indices = {name: [lookup[target] for target in candidates]
                       for name, candidates in row["pools"].items()}
            indices["full"] = [lookup[target] for target in row["full_candidates"]]
            metrics = {}
            for name, selected in indices.items():
                ranking = rank_summary([universe[index] for index in selected], row["positives"],
                                       [scores[index] for index in selected], True)
                metrics[name] = {key: ranking[key] for key in METRICS}
            rows.append({"source": row["source"], "positives": row["positives"],
                         "scores": scores, "pool_indices": indices, "pool_metrics": metrics})
        summary = {name: {key: sum(row["pool_metrics"][name][key] for row in rows) / len(rows)
                          for key in METRICS} for name in (*POOLS, "full")}
        output[direction] = {"rows": rows, "summary": summary,
                             "target_universe": universe, "n_queries": len(rows)}
    return output


def selection_score(result):
    return sum(entry["summary"][pool]["hit_at_5"]
               for entry in result.values() for pool in POOLS) / (len(result) * len(POOLS))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--pool-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--directions", choices=("both", *DIRECTIONS), default="both")
    parser.add_argument("--seed", type=int, default=3407)
    args = parser.parse_args()
    directions = DIRECTIONS if args.directions == "both" else (args.directions,)
    paths = {role: args.pool_root / (role + ".json.gz") for role in ROLES}
    begin_run(args.output, args, [args.train, *paths.values()])
    pairs = read_pairs(args.train)
    vectorizer, models, training = train_models(pairs, args.seed)
    selection_pool = load_pool(paths["validation_selection"])
    selection = {c: evaluate_role(selection_pool, model, vectorizer, directions)
                 for c, model in models.items()}
    selection_scores = {c: selection_score(result) for c, result in selection.items()}
    chosen = max(C_VALUES, key=lambda c: (selection_scores[c], -c))
    model = models[chosen]
    joblib.dump({"vectorizer": vectorizer, "model": model, "C": chosen},
                args.output / "model.joblib")
    summaries = {}
    for role, path in paths.items():
        result = selection[chosen] if role == "validation_selection" else evaluate_role(
            load_pool(path), model, vectorizer, directions)
        with gzip.open(args.output / (role + ".json.gz"), "wt", encoding="utf-8",
                       compresslevel=6) as handle:
            json.dump(result, handle, sort_keys=True, separators=(",", ":"))
        summaries[role] = {direction: entry["summary"] for direction, entry in result.items()}
    summary = {"schema_version": 2, "train_sha256": file_sha256(args.train),
               "pool_sha256": {role: file_sha256(path) for role, path in paths.items()},
               "seed": args.seed, "C_grid": list(C_VALUES), "selected_C": chosen,
               "selection_score": selection_scores, "selection_metric":
               "mean bidirectional query-macro Hit@5 over random/length/motif/edit pools",
               "training": training, "roles": summaries,
               "negative_definition": "unrecorded combination from training pairs only"}
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    finish_run(args.output)
    print(json.dumps({"output": str(args.output), "selected_C": chosen,
                      "selection_score": selection_scores}, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
