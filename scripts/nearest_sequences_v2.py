#!/usr/bin/env python3
"""Resumable exact nearest-sequence distances for all paired-chain queries."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import sys
import time
from pathlib import Path

import numpy as np
from rapidfuzz import process
from rapidfuzz.distance import Levenshtein

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gdtcr.data import read_pairs
from gdtcr.fileio import file_sha256


def sequences(path, file_format, chain):
    if file_format == "pairs":
        index = 0 if chain == "gamma" else 1
        return sorted({pair[index] for pair in read_pairs(path)})
    with path.open(newline="", encoding="ascii") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != ["chain", "sequence"]:
            raise ValueError(f"Expected chain/sequence TSV: {path}")
        return sorted({row["sequence"] for row in reader if row["chain"] == chain})


def transform(sequence, feature):
    if feature == "full":
        return sequence
    if feature == "interior":
        return sequence[3:-3]
    if feature == "end":
        return sequence[:3] + sequence[-3:]
    raise ValueError(feature)


def nearest(query, reference, workers):
    if not query or not reference:
        raise ValueError("Cannot compute nearest distance on empty sequences")
    if max(map(len, query + reference)) > 255:
        raise ValueError("uint8 edit distance could overflow")
    distances = process.cdist(query, reference, scorer=Levenshtein.distance,
                              dtype=np.uint8, workers=workers)
    query_lengths = np.asarray([len(value) for value in query], dtype=np.float32)
    reference_lengths = np.asarray([len(value) for value in reference], dtype=np.float32)
    denominator = np.maximum(query_lengths[:, None], reference_lengths[None, :])
    np.maximum(denominator, 1., out=denominator)
    normalized = distances / denominator
    raw_indices = distances.argmin(axis=1)
    normalized_indices = normalized.argmin(axis=1)
    rows = []
    for index, (raw, scaled) in enumerate(zip(raw_indices, normalized_indices)):
        rows.append({"min_raw": int(distances[index, raw]),
                     "nearest_raw_index": int(raw),
                     "min_normalized": float(normalized[index, scaled]),
                     "nearest_normalized_index": int(scaled)})
    return rows


def calculate_chunk(queries, reference, transformed, workers):
    result = [{"query": query} for query in queries]
    for feature in ("full", "interior", "end"):
        candidates = transformed[feature]
        values = nearest([transform(query, feature) for query in queries],
                         candidates, workers)
        for row, value in zip(result, values):
            value["nearest_raw"] = reference[value.pop("nearest_raw_index")]
            value["nearest_normalized"] = reference[value.pop("nearest_normalized_index")]
            row[feature] = value
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--reference-format", choices=("pairs", "sequences"), required=True)
    parser.add_argument("--queries", type=Path, default=Path("data/processed/paired_chain.txt"))
    parser.add_argument("--chain", choices=("gamma", "delta"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--chunk-size", type=int, default=32)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-chunks", type=int, help="Stop after this many new chunks; resumable benchmark")
    args = parser.parse_args()
    if args.chunk_size < 1 or args.workers < 1:
        raise ValueError("chunk size and workers must be positive")
    if (args.output / "summary.json").exists():
        raise FileExistsError(f"Completed distance audit is immutable: {args.output}")
    inputs = {"reference_sha256": file_sha256(args.reference),
              "queries_sha256": file_sha256(args.queries),
              "script_sha256": file_sha256(__file__), "chain": args.chain,
              "reference_format": args.reference_format, "chunk_size": args.chunk_size}
    args.output.mkdir(parents=True, exist_ok=True)
    run = args.output / "run.json"
    if run.exists():
        if json.loads(run.read_text()) != inputs:
            raise ValueError("Distance audit resume changed inputs or code")
    else:
        run.write_text(json.dumps(inputs, indent=2, sort_keys=True) + "\n")
    reference = sequences(args.reference, args.reference_format, args.chain)
    queries = sequences(args.queries, "pairs", args.chain)
    if not reference or not queries:
        raise ValueError("Empty reference or query set")
    transformed = {feature: [transform(sequence, feature) for sequence in reference]
                   for feature in ("full", "interior", "end")}
    chunks = (len(queries) + args.chunk_size - 1) // args.chunk_size
    started, new_chunks = time.time(), 0
    for chunk in range(chunks):
        output = args.output / f"chunk_{chunk:05d}.json.gz"
        start = chunk * args.chunk_size
        selected = queries[start:start + args.chunk_size]
        if output.exists():
            with gzip.open(output, "rt", encoding="utf-8") as handle:
                existing = json.load(handle)
            if [row["query"] for row in existing] != selected:
                raise ValueError(f"Existing chunk does not match frozen queries: {output}")
            continue
        rows = calculate_chunk(selected, reference, transformed, args.workers)
        temporary = output.with_suffix(output.suffix + ".tmp")
        with gzip.open(temporary, "wt", encoding="utf-8", compresslevel=6) as handle:
            json.dump(rows, handle, sort_keys=True, separators=(",", ":"))
        temporary.replace(output)
        new_chunks += 1
        print(json.dumps({"chain": args.chain, "chunk": chunk + 1,
                          "total_chunks": chunks, "elapsed_seconds": time.time() - started}), flush=True)
        if args.max_chunks and new_chunks >= args.max_chunks:
            return
    all_rows = []
    for chunk in range(chunks):
        with gzip.open(args.output / f"chunk_{chunk:05d}.json.gz", "rt", encoding="utf-8") as handle:
            all_rows.extend(json.load(handle))
    assert [row["query"] for row in all_rows] == queries
    with gzip.open(args.output / "rows.json.gz", "wt", encoding="utf-8", compresslevel=6) as handle:
        json.dump(all_rows, handle, sort_keys=True, separators=(",", ":"))
    summary = {**inputs, "reference_sequences": len(reference), "query_sequences": len(queries),
               "chunks": chunks, "rows_sha256": file_sha256(args.output / "rows.json.gz"),
               "reference_path": str(args.reference), "query_path": str(args.queries),
               "elapsed_seconds_this_invocation": time.time() - started}
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
