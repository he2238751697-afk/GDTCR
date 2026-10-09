#!/usr/bin/env python3
"""Cluster intervals, edge weights and frozen source/nearest-distance strata for v2."""

from __future__ import annotations

import argparse
import copy
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gdtcr.calibration import calibrated_scores
from gdtcr.data import component_groups, read_pairs
from gdtcr.fileio import file_sha256
from gdtcr.provenance import begin_run, finish_run
from gdtcr.statistics import bidirectional_intervals, cluster_intervals
from analyze_strata import source_length_bin, positive_count_bin
from audit_data_v2 import read_sources
from calibrate_scores_v2 import free_views, load_gzip
from evaluate_free_v2 import summarize_prefix


PRIMARY = "64/allow_training_targets"


def clusters_for(pairs, direction, directional):
    column = 0 if direction == "gamma_to_delta" else 1
    if directional:
        return {pair[column]: pair[column] for pair in pairs}
    output = {}
    for index, component in enumerate(component_groups(pairs)):
        for edge in component:
            output[pairs[edge][column]] = f"component_{index:05d}"
    return output


def flatten_free(row, primary_only=False):
    values = {"query_mean_nll": row["positive_query_mean_nll"]}
    for prefix, entry in row["prefixes"].items():
        if primary_only and prefix != PRIMARY:
            continue
        stem = "" if primary_only else prefix + "|"
        values.update({stem + "coverage": entry["methods"]["raw"]["coverage"],
                       stem + "partner_recovery_fraction": entry["recovered_partners"] / entry["positive_count"],
                       stem + "valid_draw_fraction": entry["valid_draws"] / entry["draws"],
                       stem + "unique_candidates": entry["unique_candidates"],
                       stem + "novel_draw_fraction": entry["novel_draw_fraction"],
                       stem + "length_entropy": entry["length_entropy"],
                       stem + "terminal_motif_entropy": entry["terminal_motif_entropy"]})
        for method, metrics in entry["methods"].items():
            for key, value in metrics.items():
                if key != "coverage":
                    values[stem + method + "|" + key] = value
        for method, metrics in entry.get("calibrated", {}).items():
            for key in ("accepted_query", "hit_at_5", "recall_at_5"):
                values[stem + "accepted|" + method + "|" + key] = metrics[key]
    return values


def flatten_pools(row):
    return {pool + "|" + method + "|" + metric: value
            for pool, methods in row["pool_metrics"].items() for method, metrics in methods.items()
            for metric, value in metrics.items()}


def binary_names(metrics):
    return [key for key in metrics if key.split("|")[-1] in
            ("coverage", "hit_at_1", "hit_at_5", "hit_at_10", "accepted_query")]


def statistics(rows, lookup, args, mode, primary_only=False):
    metrics = [flatten_free(row, primary_only) if mode == "free" else flatten_pools(row) for row in rows]
    clusters = [lookup[row["source"]] for row in rows]
    edge_counts = [len(row["positives"]) for row in rows]
    kwargs = {"replicates": args.bootstrap_replicates, "seed": args.bootstrap_seed}
    query = cluster_intervals(metrics, clusters, binary_metrics=binary_names(metrics[0]) if metrics else (), **kwargs)
    edge = cluster_intervals(metrics, clusters, weights=edge_counts if metrics else None, **kwargs)
    result = {"n_queries": len(rows), "n_recorded_edges": sum(edge_counts),
              "query_macro": query, "edge_weighted_query_metrics": edge}
    if mode == "free" and rows:
        token_rows = [{"token_nll": row["positive_nll_token_sum"] / row["positive_token_count"]} for row in rows]
        result["token_weighted_nll"] = cluster_intervals(token_rows, clusters,
                                                       weights=[row["positive_token_count"] for row in rows], **kwargs)
    return result, metrics


def distance_rows(path):
    summary = json.loads((path / "summary.json").read_text())
    if file_sha256(path / "rows.json.gz") != summary["rows_sha256"]:
        raise ValueError(f"Nearest-distance table changed: {path}")
    return {row["query"]: row for row in load_gzip(path / "rows.json.gz")}


def distance_bin(value):
    return str(value) if value < 3 else "ge3"


def verify_evaluation(folder):
    checksums = json.loads((folder / "checksums.json").read_text())
    for name in ("summary.json", "rows.json.gz", "provenance.json"):
        if file_sha256(folder / name) != checksums[name]:
            raise ValueError(f"Changed evaluation artifact: {folder / name}")


def filtered_row(raw, positives, train_targets, profile, alpha):
    # Reuse the saved candidates and their scores, changing only the eligible
    # recorded-partner set for an explicitly declared edge stratum.
    values = free_views([raw], 64)[0]
    scores = calibrated_scores(values, profile, alpha)
    score_maps = {name: dict(zip(values["candidates"], method_values)) for name, method_values in scores.items()}
    nll_lookup = dict(zip(raw["positives"], raw["positive_nll"]))
    nll = [nll_lookup[target] for target in positives]
    return {"source": raw["source"], "positives": positives,
            "positive_query_mean_nll": sum(nll) / len(nll),
            "positive_nll_token_sum": sum(value * (len(target) + 1) for value, target in zip(nll, positives)),
            "positive_token_count": sum(len(target) + 1 for target in positives),
            "prefixes": summarize_prefix(raw["samples"], positives, train_targets, score_maps, [64])}


def strata(raw_rows, analyzed_rows, direction, settings, train_pairs, provenance,
           supervised, pretrain, lookup, args):
    source_chain, target_chain = ("gamma", "delta") if direction == "gamma_to_delta" else ("delta", "gamma")
    train_targets = {pair[1 if direction == "gamma_to_delta" else 0] for pair in train_pairs}
    profile = settings["fusion"]["score_profiles"][direction]
    alpha = settings["fusion"]["alpha"]
    analyzed = {row["source"]: row for row in analyzed_rows}
    result = {}

    def add(name, source_predicate=lambda row: True, target_predicate=None):
        rows = []
        for raw in raw_rows:
            if not source_predicate(raw):
                continue
            if target_predicate is None:
                # Remove acceptance metrics so all strata share a consistent set
                # of primary recovery endpoints regardless of edge filtering.
                row = copy.deepcopy(analyzed[raw["source"]])
                for entry in row["prefixes"].values():
                    entry.pop("calibrated", None)
            else:
                positives = [value for value in raw["positives"] if target_predicate(raw, value)]
                if not positives:
                    continue
                row = filtered_row(raw, positives, train_targets, profile, alpha)
            rows.append(row)
        result[name] = statistics(rows, lookup, args, "free", True)[0]

    for reference_name, reference in (("supervised", supervised), ("pretraining", pretrain)):
        for label in ("0", "1", "2", "ge3"):
            add(f"source_{reference_name}_full/{label}",
                source_predicate=lambda row, reference=reference, label=label:
                    distance_bin(reference[source_chain][row["source"]]["full"]["min_raw"]) == label)
            add(f"target_{reference_name}_full/{label}",
                target_predicate=lambda row, target, reference=reference, label=label:
                    distance_bin(reference[target_chain][target]["full"]["min_raw"]) == label)
    add("distant_source_and_target_from_both",
        source_predicate=lambda row: all(ref[source_chain][row["source"]]["full"]["min_raw"] >= 3
                                         for ref in (supervised, pretrain)),
        target_predicate=lambda row, target: all(ref[target_chain][target]["full"]["min_raw"] >= 3
                                                 for ref in (supervised, pretrain)))
    for label in ("short_<=12", "medium_13-16", "long_>=17"):
        add("source_length/" + label, source_predicate=lambda row, label=label: source_length_bin(len(row["source"])) == label)
    for label in ("one", "two_to_three", "four_or_more"):
        add("recorded_partner_count/" + label, source_predicate=lambda row, label=label: positive_count_bin(len(row["positives"])) == label)
    for label in ("GSE180059", "Suo_2022", "IEDB_untraced"):
        add("recorded_edge_study/" + label,
            target_predicate=lambda row, target, label=label: label in provenance[
                (row["source"], target) if direction == "gamma_to_delta" else (target, row["source"])])
    for label, is_seen in (("seen", True), ("unseen", False)):
        add("training_target_overlap/" + label,
            target_predicate=lambda row, target, is_seen=is_seen: (target in train_targets) == is_seen)
    return {"definitions": {
                "distance": "exact full-sequence Levenshtein distance: 0/1/2/>=3",
                "distant": "source and each eligible recorded target both have distance >=3 from supervised and pretraining references",
                "target_and_study_strata": "filter recorded positive edges, retain original candidates and original test-cluster identities",
                "pretraining_reference": "frozen benchmark pool, also used to define comparable strata for random/single-chain ablations",
                "study_strata": "may overlap for cross-study duplicate recorded pairs",
                "empty_strata": "reported explicitly; do not imply successful distant generalization"},
            "groups": result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("free", "pools"), required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--settings", type=Path, required=True)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--pairs", type=Path, required=True)
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bootstrap-replicates", type=int, default=2000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260930)
    args = parser.parse_args()
    if args.bootstrap_replicates < 100:
        parser.error("At least 100 bootstrap replicates required")
    for folder in (args.input, args.raw):
        verify_evaluation(folder)
    analyzed_summary = json.loads((args.input / "summary.json").read_text())
    if analyzed_summary["settings_sha256"] != file_sha256(args.settings):
        raise ValueError("Calibration settings differ from the analyzed evaluation")
    if Path(analyzed_summary["raw_evaluation"]).resolve() != args.raw.resolve():
        raise ValueError("Analysis/raw evaluation lineage differs")
    inputs = [args.pairs, args.train, args.settings,
              *[folder / name for folder in (args.input, args.raw) for name in
                ("summary.json", "rows.json.gz", "checksums.json", "provenance.json")]]
    distance_root = Path("artifacts/completion_v2/distances")
    dataset = "data_fraction" + args.train.stem.removeprefix("train_fraction") \
        if args.train.stem.startswith("train_fraction") else args.protocol
    supervised_paths = {chain: distance_root / "supervised" / dataset / chain for chain in ("gamma", "delta")}
    pretrain_paths = {chain: distance_root / (("pretrain_source_excluded_" if args.protocol.startswith("source_") else "pretrain_") + chain)
                      for chain in ("gamma", "delta")}
    provenance_path = Path("data/provenance/unique_pairs.tsv.gz")
    if args.mode == "free":
        inputs.append(provenance_path)
        inputs.extend(folder / name for folder in (*supervised_paths.values(), *pretrain_paths.values())
                      for name in ("rows.json.gz", "summary.json"))
    begin_run(args.output, args, inputs)
    pairs, train = read_pairs(args.pairs), read_pairs(args.train)
    analyzed, raw = load_gzip(args.input / "rows.json.gz"), load_gzip(args.raw / "rows.json.gz")
    settings = json.loads(args.settings.read_text())
    if args.mode == "free":
        supervised = {chain: distance_rows(path) for chain, path in supervised_paths.items()}
        pretrain = {chain: distance_rows(path) for chain, path in pretrain_paths.items()}
        provenance = read_sources(provenance_path)
    directions, compact_rows, joint_rows, joint_clusters = {}, {}, {}, {}
    for direction, rows in analyzed.items():
        directional = args.protocol.startswith(("seen_input_", "unseen_input_"))
        lookup = clusters_for(pairs, direction, directional)
        if set(lookup) != {row["source"] for row in rows} or len(rows) != len(lookup):
            raise ValueError("Analyzed queries do not exactly match the frozen test split")
        result, metrics = statistics(rows, lookup, args, args.mode)
        result["bootstrap_unit"] = "source_query" if directional else "connected_component_of_frozen_test_graph"
        if args.mode == "free":
            result["strata"] = strata(raw[direction], rows, direction, settings, train,
                                       provenance, supervised, pretrain, lookup, args)
        directions[direction] = result
        joint_rows[direction] = [flatten_free(row, True) if args.mode == "free" else flatten_pools(row) for row in rows]
        joint_clusters[direction] = [lookup[row["source"]] for row in rows]
        compact_rows[direction] = [{"source": row["source"], "positives": row["positives"],
                                    "cluster": lookup[row["source"]], "metrics": value}
                                   for row, value in zip(rows, metrics)]
    with gzip.open(args.output / "query_metrics.json.gz", "wt", encoding="utf-8", compresslevel=6) as handle:
        json.dump(compact_rows, handle, sort_keys=True, separators=(",", ":"))
    result = {"schema_version": 2, "mode": args.mode, "protocol": args.protocol,
              "directions": directions, "query_metrics_sha256": file_sha256(args.output / "query_metrics.json.gz"),
              "equal_direction_macro": bidirectional_intervals(joint_rows, joint_clusters,
                                                                replicates=args.bootstrap_replicates,
                                                                seed=args.bootstrap_seed),
              "input_sha256": {str(path): file_sha256(path) for path in inputs},
              "zero_event_note": "A percentile [0,0] is not a population upper bound; iid Wilson reference is labelled separately",
              "weights": "query macro and recorded-positive-count weighted query metrics; weighted Recall equals edge-micro Recall"}
    if args.mode == "pools":
        result["test_pool_sha256"] = json.loads((args.raw / "summary.json").read_text())["pool_sha256"]
    (args.output / "summary.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    finish_run(args.output)
    print(json.dumps({"output": str(args.output), "mode": args.mode, "protocol": args.protocol}), flush=True)


if __name__ == "__main__":
    main()
