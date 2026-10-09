#!/usr/bin/env python3
"""Verify all completed baseline outputs against the frozen pools and training inputs."""

import argparse
import gzip
import json
import math
from pathlib import Path

from analyze_run_v2 import clusters_for
from evaluate_neighbors_v2 import exact_pair_scores
from gdtcr.data import read_pairs
from gdtcr.fileio import file_sha256
from gdtcr.provenance import begin_run, finish_run


def load(path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    configs = [Path("configs/completion_v2") / name for name in ("neighbor_jobs.json", "shallow_jobs.json")]
    manifests = [json.loads(path.read_text()) for path in configs]
    begin_run(args.output, args, configs)
    reports, hashes = [], {}
    for manifest in manifests:
        for task in manifest["tasks"]:
            record_path = Path(manifest["job_records"]) / (task["id"] + ".json")
            record = json.loads(record_path.read_text())
            if record["status"] != "complete":
                raise ValueError(f"Baseline incomplete: {record_path}")
            for path, expected in record["output_sha256"].items():
                if file_sha256(path) != expected:
                    raise ValueError(f"Changed baseline output: {path}")
                hashes[path] = expected
            arguments = task["commands"][0]["args"]
            get = lambda key: arguments[arguments.index(key) + 1]
            folder, pool_root, train = Path(get("--output")), Path(get("--pool-root")), Path(get("--train"))
            summary = json.loads((folder / "summary.json").read_text())
            if summary["train_sha256"] != file_sha256(train):
                raise ValueError("Baseline train hash differs")
            n_queries = 0
            for role in ("validation_selection", "validation_tuning", "validation_calibration", "test"):
                pool_path = pool_root / (role + ".json.gz")
                if summary["pool_sha256"][role] != file_sha256(pool_path):
                    raise ValueError("Baseline pool hash differs")
                pool, result = load(pool_path), load(folder / (role + ".json.gz"))
                for direction, raw in result.items():
                    rows = raw["rows"] if manifest["phase"] == "shallow" else raw
                    expected = pool["directions"][direction]
                    if len(rows) != len(expected["rows"]):
                        raise ValueError("Baseline query count differs")
                    targets = expected["target_universe"]
                    target_lookup = {t: index for index, t in enumerate(targets)}
                    for row, item in zip(rows, expected["rows"]):
                        if row["source"] != item["source"] or row["positives"] != item["positives"]:
                            raise ValueError("Baseline query/positive pairing differs")
                        pools = {name: [target_lookup[t] for t in values] for name, values in item["pools"].items()}
                        pools["full"] = [target_lookup[t] for t in item["full_candidates"]]
                        if row["pool_indices"] != pools:
                            raise ValueError("Baseline candidates differ from the frozen pool")
                        score_vectors = [row["scores"]] if manifest["phase"] == "shallow" else list(row["scores"].values())
                        if any(len(v) != len(targets) or any(not math.isfinite(s) for s in v) for v in score_vectors):
                            raise ValueError("Baseline scores missing/nonfinite")
                    n_queries += len(rows)
                    if role == "test" and manifest["phase"] == "neighbor":
                        # Small sample across both query and target order; every
                        # training edge remains included in the exact minimum.
                        qi = sorted({0, len(rows) // 2, len(rows) - 1})
                        ti = sorted({0, len(targets) // 2, len(targets) - 1})
                        scores, witnesses = exact_pair_scores(sorted(read_pairs(train)),
                            [rows[i]["source"] for i in qi], [targets[i] for i in ti], direction, workers=1)
                        for a, i in enumerate(qi):
                            for b, j in enumerate(ti):
                                if not math.isclose(scores[a, b], rows[i]["scores"]["edit_neighbor"][j], abs_tol=1e-12):
                                    raise ValueError("Exact-neighbor score recomputation differs")
                                if int(witnesses[a, b]) != rows[i]["nearest_training_edge"][j]:
                                    raise ValueError("Nearest-edge witness differs")
            if manifest["phase"] == "shallow":
                expected_c = max((.1, 1., 10.), key=lambda c: (summary["selection_score"][str(c)], -c))
                if expected_c != summary["selected_C"]:
                    raise ValueError("Shallow C selection differs from the frozen criterion")
                if summary["training"]["constructed_negatives"] != 3 * summary["training"]["positives"]:
                    raise ValueError("Shallow training class ratio differs")
            reports.append({"task_id": task["id"], "path": str(folder), "queries_checked_across_roles": n_queries,
                            "phase": manifest["phase"], "passed": True})
            print(json.dumps(reports[-1]), flush=True)
    if len(reports) != 27:
        raise ValueError("Expected nine neighbor and eighteen shallow results")
    summary = {"schema_version": 2, "passed": True, "runs": reports, "verified_output_sha256": hashes,
               "scope": "all baseline hashes, queries, positives, candidate lists and score completeness; exact-neighbor sample re-evaluation; shallow selection and ratio verification"}
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    finish_run(args.output)


if __name__ == "__main__":
    main()
