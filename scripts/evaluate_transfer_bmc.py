#!/usr/bin/env python3
"""Training-only nearest-input transfer and separate fixed-pool similarity."""
import argparse
import gzip
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from rapidfuzz.distance import Levenshtein

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gdtcr.data import component_groups, read_pairs
from gdtcr.evaluation import ranked_generation_metrics
from gdtcr.fileio import file_sha256
from gdtcr.metrics import rank_summary
from gdtcr.provenance import begin_run, finish_run
from gdtcr.statistics import cluster_intervals


def training_index(pairs, column):
    partners = defaultdict(set)
    for p in pairs:
        partners[p[column]].add(p[1-column])
    return dict(partners), Counter(p[1-column] for p in pairs)


def transfer(source, partners, frequency, n_neighbors=1, budget=64):
    neighbors = sorted(partners, key=lambda s: (Levenshtein.normalized_distance(source, s), s))[:n_neighbors]
    proposed = []
    for neighbor in neighbors:
        proposed.extend(sorted(partners[neighbor], key=lambda t: (-frequency[t], t)))
    candidates = list(dict.fromkeys(proposed))[:budget]
    return candidates, neighbors


def partner_similarity(targets, partners):
    return [-min(Levenshtein.normalized_distance(t, p) for p in partners) for t in targets]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--test", type=Path, required=True)
    parser.add_argument("--pool", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--directions", choices=("both", "gamma_to_delta", "delta_to_gamma"), default="both")
    parser.add_argument("--unit", choices=("component", "source_query", "single_original_component"), default="component")
    args = parser.parse_args()
    begin_run(args.output, args, [args.train, args.test, args.pool])
    train, test = read_pairs(args.train), read_pairs(args.test)
    pools = json.load(gzip.open(args.pool, "rt")) if args.pool else None
    if pools and pools["pair_sha256"] != file_sha256(args.test):
        raise ValueError("Frozen pool belongs to different test pairs")
    cluster_by_node = {}
    for cluster, indices in enumerate(component_groups(test)):
        for i in indices:
            for col in (0,1):
                cluster_by_node[col, test[i][col]] = str(cluster)
    output, summary = {}, {}
    for direction, col in (("gamma_to_delta", 0), ("delta_to_gamma", 1)):
        if args.directions not in ("both", direction):
            continue
        partners, freq = training_index(train, col)
        positives, _ = training_index(test, col)
        pool_rows = {r["source"]: r for r in pools["directions"][direction]["rows"]} if pools else {}
        rows = []
        for source, truth in sorted(positives.items()):
            row = {"source": source, "positives": sorted(truth), "transfer": {}, "retrieval": {}}
            for k in (1,5):
                candidates, neighbors = transfer(source, partners, freq, k)
                row["transfer"][str(k)] = {
                    "neighbors": neighbors,
                    "distances": [Levenshtein.normalized_distance(source, n) for n in neighbors],
                    "candidates": candidates, "metrics": ranked_generation_metrics(truth, candidates)}
            if pools:
                pr = pool_rows[source]
                if set(pr["positives"]) != truth:
                    raise ValueError("Pool positive set differs")
                nearest_partners = partners[row["transfer"]["1"]["neighbors"][0]]
                for name, candidates in {**pr["pools"], "full": pr["full_candidates"]}.items():
                    scores = partner_similarity(candidates, nearest_partners)
                    row["retrieval"][name] = {"scores": scores, "candidates": candidates,
                        "metrics": rank_summary(candidates, truth, scores, True)}
            row["cluster"] = (source if args.unit == "source_query" else "original_giant"
                              if args.unit == "single_original_component" else cluster_by_node[col, source])
            rows.append(row)
        direction_summary = {}
        for kind, names in (("transfer", ("1", "5")), ("retrieval", tuple(rows[0]["retrieval"]))):
            for name in names:
                keys = ("coverage", "hit_at_5", "recall_at_5", "mrr") if kind == "transfer" else ("hit_at_5", "recall_at_5", "mrr")
                metrics = [{k: r[kind][name]["metrics"][k] for k in keys} for r in rows]
                if args.unit == "single_original_component":
                    result = {"n_queries": len(rows), "n_clusters": 1,
                              "interval_unavailable_reason": "One original graph component; point estimates only",
                              "metrics": {k: {"estimate": sum(m[k] for m in metrics)/len(metrics)} for k in keys}}
                    for k in ("coverage", "hit_at_5"):
                        if k in keys:
                            result["metrics"][k].update(events=sum(int(m[k]) for m in metrics), denominator=len(rows))
                else:
                    result = cluster_intervals(metrics, [r["cluster"] for r in rows],
                        binary_metrics=[k for k in ("coverage", "hit_at_5") if k in keys])
                direction_summary[f"{kind}/{name}"] = result
        output[direction], summary[direction] = rows, direction_summary
    with gzip.open(args.output/"rows.json.gz", "wt") as handle:
        json.dump(output, handle, separators=(",", ":"), sort_keys=True)
    record = {"directions": summary, "unit": args.unit, "pool_sha256": file_sha256(args.pool) if args.pool else None,
              "proposal_budget": "at most 64 unique training targets, not 64 stochastic draws",
              "distance": "full-CDR3 Levenshtein divided by longer sequence length",
              "truth_injected": {"transfer": False, "retrieval": True}}
    (args.output/"summary.json").write_text(json.dumps(record, indent=2, sort_keys=True)+"\n")
    finish_run(args.output)
    print(json.dumps({"output": str(args.output), "queries": {d: len(r) for d,r in output.items()}}))


if __name__ == "__main__":
    main()
