#!/usr/bin/env python3
"""Reconstruct paired observations and all single-chain source memberships.

Reads frozen raw files without changing the legacy processed corpus. Keeps
library-local barcodes, source row identifiers and available V/J annotations;
never infers a donor identifier. Outputs compressed TSVs plus an audit manifest.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import sqlite3
import sys
import tempfile
import zipfile
from collections import Counter, defaultdict
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from clean_data import chain_type, clean_cdr3, csv_rows, uctcrdb_chain, xlsx_rows
from gdtcr.fileio import file_sha256 as file_hash


def stable_id(kind, *values):
    payload = "\0".join((kind, *values)).encode()
    return kind + ":" + hashlib.sha256(payload).hexdigest()


@contextmanager
def tsv_writer(path, fields):
    with path.open("wb") as binary, gzip.GzipFile(fileobj=binary, mode="wb", mtime=0) as compressed:
        with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
            writer.writeheader()
            yield writer


PAIR_FIELDS = (
    "observation_id", "pair_id", "gamma_id", "delta_id", "gamma_cdr3", "delta_cdr3",
    "source_db", "study_id", "raw_file", "record_id", "library_id", "donor_id",
    "species", "gamma_v", "gamma_j", "delta_v", "delta_j", "pairing_evidence",
    "quality_flags",
)


class Provenance:
    def __init__(self, raw, database, pair_writer):
        self.raw = raw
        self.db = database
        self.writer = pair_writer
        self.pair_observations = Counter()
        self.pair_sources = defaultdict(set)
        self.pair_observation_counts = Counter()
        self.pair_libraries = defaultdict(set)
        self.pair_species = defaultdict(set)
        self.single_counts = Counter()
        self.quality = Counter()
        self.pending = []
        self.db.execute("CREATE TABLE membership (chain TEXT, sequence TEXT, study TEXT, source TEXT, "
                        "n_observations INTEGER, PRIMARY KEY(chain, sequence, study, source)) WITHOUT ROWID")

    def single(self, chain, value, study, source):
        sequence = clean_cdr3(value)
        if sequence and chain in ("gamma", "delta"):
            self.pending.append((chain, sequence, study, source, 1))
            self.single_counts[f"{source}/{study}/{chain}"] += 1
            if len(self.pending) >= 10000:
                self.flush()
        return sequence

    def flush(self):
        with self.db:
            self.db.executemany("INSERT INTO membership VALUES(?,?,?,?,?) ON CONFLICT "
                                "DO UPDATE SET n_observations=n_observations+1", self.pending)
        self.pending.clear()

    def pair(self, gamma, delta, path, source, study, record, library="", species="",
             gamma_v="", gamma_j="", delta_v="", delta_j="", evidence="", flags=""):
        gamma, delta = clean_cdr3(gamma), clean_cdr3(delta)
        if not gamma or not delta:
            return
        rel = str(path.relative_to(self.raw))
        pair_id = stable_id("pair", gamma, delta)
        self.writer.writerow(dict(zip(PAIR_FIELDS, (
            stable_id("observation", rel, record, gamma, delta), pair_id,
            stable_id("gamma", gamma), stable_id("delta", delta), gamma, delta,
            source, study, rel, record, library, "", species, gamma_v, gamma_j, delta_v, delta_j,
            evidence, flags))))
        key = (gamma, delta)
        self.pair_sources[key].add(study)
        self.pair_observation_counts[key] += 1
        if library:
            self.pair_libraries[key].add(library)
        self.pair_species[key].add(species or "unreported")
        self.pair_observations[study] += 1


def read_geo(provenance):
    for path in sorted((provenance.raw / "GSE180059").glob("*_filtered_contig_annotations.csv.gz")):
        cells = defaultdict(lambda: {"gamma": defaultdict(list), "delta": defaultdict(list)})
        library = path.name.split("_")[0]
        for row in csv_rows(path):
            provenance.quality["geo_contigs_total"] += 1
            if any((row[key] or "").strip().lower() != "true" for key in
                   ("is_cell", "high_confidence", "productive", "full_length")):
                provenance.quality["geo_contigs_failed_quality"] += 1
                continue
            chain = chain_type(row["chain"])
            barcode = row["barcode"].strip()
            sequence = clean_cdr3(row["cdr3"])
            if barcode and chain and sequence:
                provenance.single(chain, sequence, "GSE180059", "GEO")
                cells[barcode][chain][sequence].append(row)
        for barcode, chains in sorted(cells.items()):
            if not (len(chains["gamma"]) == len(chains["delta"]) == 1):
                provenance.quality["geo_cells_not_single_gamma_delta_cdr3"] += 1
                continue
            gamma, delta = next(iter(chains["gamma"])), next(iter(chains["delta"]))
            def genes(chain, sequence, field):
                return "|".join(sorted({r[field] for r in chains[chain][sequence] if r[field] not in ("None", "")}))
            provenance.pair(gamma, delta, path, "GEO", "GSE180059", barcode,
                            library=f"GSE180059/{library}", species="Homo sapiens",
                            gamma_v=genes("gamma", gamma, "v_gene"), gamma_j=genes("gamma", gamma, "j_gene"),
                            delta_v=genes("delta", delta, "v_gene"), delta_j=genes("delta", delta, "j_gene"),
                            evidence="single_library_barcode_single_unique_gamma_delta_CDR3",
                            flags="is_cell;high_confidence;productive;full_length")


def read_uc(provenance):
    for path in sorted((provenance.raw / "UcTCRdb").glob("*.csv.gz")):
        study = path.name.removeprefix("GD_Human_").removesuffix(".csv.gz")
        for index, row in enumerate(csv_rows(path), 2):
            if "CDR3g" in row and "CDR3d" in row:
                gamma = provenance.single("gamma", row["CDR3g"], study, "UcTCRdb")
                delta = provenance.single("delta", row["CDR3d"], study, "UcTCRdb")
                provenance.pair(gamma, delta, path, "UcTCRdb", study,
                                record=f"row:{index};ID:{row.get('ID', '')}",
                                species=row.get("Species", ""), gamma_v=row.get("Vgamma", ""),
                                gamma_j=row.get("Jgamma", ""), delta_v=row.get("Vdelta", ""),
                                delta_j=row.get("Jdelta", ""), evidence="database_paired_row_original_barcode_unavailable",
                                flags="canonical_amino_acids;original_cell_quality_unavailable")
            else:
                provenance.single(uctcrdb_chain(row), row.get("CDR3"), study, "UcTCRdb")


def read_iedb(provenance):
    for path in sorted((provenance.raw / "IEDB").glob("*.xlsx")):
        for index, row in enumerate(xlsx_rows(path), 2):
            chains = {}
            for number in (1, 2):
                chain = chain_type(row.get(f"Chain {number} - Type"))
                sequence = provenance.single(chain, row.get(f"Chain {number} - CDR3 Curated"),
                                             "IEDB_untraced", "IEDB")
                if chain and sequence:
                    chains[chain] = sequence
            provenance.pair(chains.get("gamma"), chains.get("delta"), path, "IEDB", "IEDB_untraced",
                            record=f"worksheet_row:{index}", evidence="curated_receptor_export_row",
                            flags="species_reference_and_receptor_ID_missing_in_export")


def read_tcrdb(provenance):
    for path in sorted((provenance.raw / "TCRdb2.0").glob("*.zip")):
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                if member.is_dir() or not member.filename.lower().endswith(".csv"):
                    continue
                name = Path(member.filename).name.upper()
                filename_chain = "gamma" if ".TRG." in name else "delta" if ".TRD." in name else None
                with archive.open(member) as binary, io.TextIOWrapper(binary, encoding="utf-8-sig", newline="") as handle:
                    reader = csv.DictReader(handle)
                    columns = {name.lower(): name for name in (reader.fieldnames or []) if name}
                    for row in reader:
                        reported = chain_type(row.get(columns.get("chain")))
                        if reported and filename_chain and reported != filename_chain:
                            continue
                        provenance.single(reported or filename_chain, row.get(columns.get("aaseq")),
                                          path.stem, "TCRdb2.0")


def export(raw, processed, output):
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gdtcr_provenance_") as temp:
        with sqlite3.connect(Path(temp) / "sources.sqlite") as database:
            with tsv_writer(output / "pair_observations.tsv.gz", PAIR_FIELDS) as writer:
                provenance = Provenance(raw, database, writer)
                read_geo(provenance)
                read_uc(provenance)
                read_iedb(provenance)
                read_tcrdb(provenance)
                provenance.flush()
            legacy = {tuple(line.split("\t")) for line in (processed / "paired_chain.txt").read_text().splitlines()}
            reconstructed = set(provenance.pair_sources)
            if reconstructed != legacy:
                raise AssertionError(f"Legacy pair mismatch: missing={len(legacy-reconstructed)}, new={len(reconstructed-legacy)}")
            with tsv_writer(output / "unique_pairs.tsv.gz", (
                "pair_id", "gamma_cdr3", "delta_cdr3", "studies", "libraries", "n_observations", "species")) as writer:
                for (gamma, delta), studies in sorted(provenance.pair_sources.items()):
                    key = gamma, delta
                    writer.writerow({"pair_id": stable_id("pair", gamma, delta), "gamma_cdr3": gamma,
                                     "delta_cdr3": delta, "studies": "|".join(sorted(studies)),
                                     "libraries": "|".join(sorted(provenance.pair_libraries[key])),
                                     "n_observations": provenance.pair_observation_counts[key],
                                     "species": "|".join(sorted(provenance.pair_species[key]))})
            sequence_fields = ("sequence_id", "chain", "sequence", "study_id", "source_db", "n_observations")
            with tsv_writer(output / "sequence_sources.tsv.gz", sequence_fields) as writer:
                for chain, sequence, study, source, count in database.execute("SELECT * FROM membership ORDER BY chain,sequence,study,source"):
                    writer.writerow(dict(zip(sequence_fields, (stable_id(chain, sequence), chain, sequence, study, source, count))))
            single_integrity = {}
            for chain, filename in (("gamma", "light_chain.txt"), ("delta", "heavy_chain.txt")):
                expected = set((processed / filename).read_text().splitlines())
                observed = {row[0] for row in database.execute("SELECT DISTINCT sequence FROM membership WHERE chain=?", (chain,))}
                if expected != observed:
                    raise AssertionError(f"{chain} corpus differs: missing={len(expected-observed)}, new={len(observed-expected)}")
                single_integrity[chain] = len(observed)
            counts = Counter(study for studies in provenance.pair_sources.values() for study in studies)
            manifest = {
                "schema_version": 1, "legacy_pair_set_exact_match": True,
                "legacy_single_chain_sets_exact_match": single_integrity,
                "unique_pairs": len(reconstructed), "unique_pairs_by_study": dict(counts),
                "pair_observations_by_study": dict(provenance.pair_observations),
                "single_valid_observations_by_source_study_chain": dict(provenance.single_counts),
                "quality_counts": dict(provenance.quality),
                "donor_identifiers": "not inferred; absent in these raw tables",
                "raw_sha256": {str(p.relative_to(raw)): file_hash(p) for p in sorted(raw.rglob('*')) if p.is_file()},
                "processed_sha256": {p.name: file_hash(p) for p in sorted(processed.glob('*.txt'))},
                "output_sha256": {p.name: file_hash(p) for p in sorted(output.glob('*.tsv.gz'))},
            }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: manifest[k] for k in ("unique_pairs", "unique_pairs_by_study", "pair_observations_by_study", "quality_counts")}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=ROOT / "data/raw")
    parser.add_argument("--processed", type=Path, default=ROOT / "data/processed")
    parser.add_argument("--output", type=Path, default=ROOT / "data/provenance")
    args = parser.parse_args()
    export(args.raw, args.processed, args.output)


if __name__ == "__main__":
    main()
