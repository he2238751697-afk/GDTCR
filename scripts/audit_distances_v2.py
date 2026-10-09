#!/usr/bin/env python3
"""Inspect every v2 distance table, its witnesses and a deterministic exact-minimum sample."""

import argparse
import gzip
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np
from rapidfuzz import process
from rapidfuzz.distance import Levenshtein

from nearest_sequences_v2 import sequences, transform
from gdtcr.data import read_pairs
from gdtcr.fileio import file_sha256
from gdtcr.provenance import begin_run, finish_run


def load(path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def bins(values):
    count = Counter(str(value) if value < 3 else "ge3" for value in values)
    return {key: count[key] for key in ("0", "1", "2", "ge3")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    root = Path("artifacts/completion_v2/distances")
    summaries = sorted(root.rglob("summary.json"))
    if len(summaries) != 28:
        raise ValueError(f"Expected 28 complete tables, found {len(summaries)}")
    inputs = [path.parent / name for path in summaries for name in ("summary.json", "rows.json.gz", "run.json")]
    begin_run(args.output, args, inputs)
    tables, references, hashes, all_rows = {}, {}, {}, {}
    for path in summaries:
        summary = json.loads(path.read_text())
        folder, chain = path.parent, summary["chain"]
        reference_path, query_path = Path(summary["reference_path"]), Path(summary["query_path"])
        for name, source in (("reference", reference_path), ("queries", query_path)):
            hashes.setdefault(str(source), file_sha256(source))
            if summary[name + "_sha256"] != hashes[str(source)]:
                raise ValueError(f"Changed {name} input: {folder}")
        if file_sha256(folder / "rows.json.gz") != summary["rows_sha256"]:
            raise ValueError(f"Changed distance rows: {folder}")
        key = (str(reference_path), summary["reference_format"], chain)
        if key not in references:
            references[key] = sequences(reference_path, summary["reference_format"], chain)
        reference = references[key]
        queries = sequences(query_path, "pairs", chain)
        rows = load(folder / "rows.json.gz")
        if [row["query"] for row in rows] != queries:
            raise ValueError(f"Missing/duplicate/reordered distance queries: {folder}")
        if (len(reference), len(rows)) != (summary["reference_sequences"], summary["query_sequences"]):
            raise ValueError(f"Distance table count differs: {folder}")
        chunk_rows = []
        for chunk in range(summary["chunks"]):
            chunk_rows.extend(load(folder / f"chunk_{chunk:05d}.json.gz"))
        if chunk_rows != rows:
            raise ValueError(f"Merged/chunk distance content differs: {folder}")
        membership = set(reference)
        for row in rows:
            for feature in ("full", "interior", "end"):
                entry = row[feature]
                if entry["nearest_raw"] not in membership or entry["nearest_normalized"] not in membership:
                    raise ValueError(f"Distance witness not in reference: {folder}")
                query = transform(row["query"], feature)
                raw_witness, norm_witness = transform(entry["nearest_raw"], feature), transform(entry["nearest_normalized"], feature)
                if Levenshtein.distance(query, raw_witness) != entry["min_raw"]:
                    raise ValueError(f"Incorrect raw witness: {folder}")
                normalized = Levenshtein.distance(query, norm_witness) / max(len(query), len(norm_witness), 1)
                if not math.isclose(normalized, entry["min_normalized"], abs_tol=1e-7):
                    raise ValueError(f"Incorrect normalized witness: {folder}")
                if feature == "full" and ((entry["min_raw"] == 0) != (row["query"] in membership)):
                    raise ValueError(f"Exact-match distance inconsistency: {folder}")
        # Independent cdist scorers use uint16/float64 (the producer used uint8/float32).
        sampled = [rows[index] for index in sorted({0, len(rows) // 2, len(rows) - 1})]
        for feature in ("full", "interior", "end"):
            q = [transform(row["query"], feature) for row in sampled]
            ref = [transform(value, feature) for value in reference]
            raw = process.cdist(q, ref, scorer=Levenshtein.distance, dtype=np.uint16, workers=args.workers).min(axis=1)
            normalized = process.cdist(q, ref, scorer=Levenshtein.normalized_distance, dtype=np.float64, workers=args.workers).min(axis=1)
            for i, row in enumerate(sampled):
                if raw[i] != row[feature]["min_raw"] or not math.isclose(normalized[i], row[feature]["min_normalized"], abs_tol=1e-7):
                    raise ValueError(f"Independent global-minimum check failed: {folder}")
        label = str(folder.relative_to(root))
        all_rows[label] = {row["query"]: row for row in rows}
        tables[label] = {"queries": len(rows), "reference_sequences": len(reference),
                         "rows_sha256": summary["rows_sha256"], "witnesses_checked": len(rows) * 6,
                         "independent_global_minimum_queries": [row["query"] for row in sampled],
                         "raw_distance_bins": {feature: bins([row[feature]["min_raw"] for row in rows])
                                               for feature in ("full", "interior", "end")}}
        print(json.dumps({"verified": label, "queries": len(rows)}), flush=True)
    protocols = json.loads(Path("data/splits/completion_v2/manifest.json").read_text())["protocols"]
    test_strata = {}
    for protocol in sorted(protocols):
        pairs = read_pairs(Path(f"data/splits/completion_v2/{protocol}/test.tsv"))
        entry = {}
        is_distant = {}
        for i, chain in enumerate(("gamma", "delta")):
            queries = sorted({pair[i] for pair in pairs})
            supervised = all_rows[f"supervised/{protocol}/{chain}"]
            pretrain = all_rows[("pretrain_source_excluded_" if protocol.startswith("source_") else "pretrain_") + chain]
            is_distant[chain] = {q: supervised[q]["full"]["min_raw"] >= 3 and pretrain[q]["full"]["min_raw"] >= 3 for q in queries}
            entry[chain] = {"queries": len(queries),
                            "supervised": bins([supervised[q]["full"]["min_raw"] for q in queries]),
                            "pretraining": bins([pretrain[q]["full"]["min_raw"] for q in queries]),
                            "distant_from_both": sum(is_distant[chain].values())}
        distant = [pair for pair in pairs if is_distant["gamma"][pair[0]] and is_distant["delta"][pair[1]]]
        entry["distant_edges"] = len(distant)
        entry["distant_gamma_queries"] = len({p[0] for p in distant})
        entry["distant_delta_queries"] = len({p[1] for p in distant})
        test_strata[protocol] = entry
    result = {"schema_version": 2, "passed": True, "tables": tables, "test_strata": test_strata,
              "input_sha256": {str(path): file_sha256(path) for path in inputs}, "reference_and_query_sha256": hashes,
              "scope": "complete table/witness/hash validation plus three independent all-reference minima per feature/table; S2 performance strata reported separately"}
    (args.output / "summary.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    finish_run(args.output)


if __name__ == "__main__":
    main()
