"""Clean gamma/delta TCR CDR3 data from data/raw into three text files.

The requested light/heavy filenames mean gamma/delta here; TCR chains are not
antibody light/heavy chains. Paired lines are ``gamma<TAB>delta``. Sequences
in paired records also appear in the respective single-chain files. CDR3
boundaries are kept exactly as supplied by each source.
"""

import argparse
import csv
import gzip
import io
import re
import sqlite3
import tempfile
import zipfile
from collections import defaultdict
from contextlib import closing
from pathlib import Path
from xml.etree import ElementTree


AMINO_ACIDS = frozenset("ACDEFGHIKLMNPQRSTVWY")
MISSING_VALUES = frozenset({"NA", "N/A", "NAN", "NONE", "NULL"})
XLSX_NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
ROOT = Path(__file__).resolve().parents[1]


def clean_cdr3(value):
    if not value:
        return None
    sequence = "".join(value.split()).upper()
    if sequence in MISSING_VALUES or not sequence or any(aa not in AMINO_ACIDS for aa in sequence):
        return None
    return sequence


def chain_type(value):
    value = (value or "").strip().upper()
    if value in {"GAMMA", "TRG"}:
        return "gamma"
    if value in {"DELTA", "TRD"}:
        return "delta"
    return None


class Corpus:
    def __init__(self, database):
        self.database = database
        self.database.executescript(
            """
            CREATE TABLE light (seq TEXT PRIMARY KEY) WITHOUT ROWID;
            CREATE TABLE heavy (seq TEXT PRIMARY KEY) WITHOUT ROWID;
            CREATE TABLE paired (
                light TEXT NOT NULL,
                heavy TEXT NOT NULL,
                PRIMARY KEY (light, heavy)
            ) WITHOUT ROWID;
            """
        )
        self.pending = {"light": [], "heavy": [], "paired": []}
        self.source_counts = defaultdict(lambda: [0, 0, 0])

    def add(self, gamma, delta, source):
        gamma = clean_cdr3(gamma)
        delta = clean_cdr3(delta)
        if gamma:
            self.pending["light"].append((gamma,))
            self.source_counts[source][0] += 1
        if delta:
            self.pending["heavy"].append((delta,))
            self.source_counts[source][1] += 1
        if gamma and delta:
            self.pending["paired"].append((gamma, delta))
            self.source_counts[source][2] += 1
        if sum(map(len, self.pending.values())) >= 10_000:
            self.flush()

    def flush(self):
        with self.database:
            for table, rows in self.pending.items():
                if rows:
                    placeholders = "?, ?" if table == "paired" else "?"
                    self.database.executemany(
                        f"INSERT OR IGNORE INTO {table} VALUES ({placeholders})", rows
                    )
                    rows.clear()

    def write_files(self, output_dir):
        self.flush()
        outputs = (
            ("light", "light_chain.txt", "SELECT seq FROM light ORDER BY seq"),
            ("heavy", "heavy_chain.txt", "SELECT seq FROM heavy ORDER BY seq"),
            (
                "paired",
                "paired_chain.txt",
                "SELECT light, heavy FROM paired ORDER BY light, heavy",
            ),
        )
        for table, filename, query in outputs:
            staged = output_dir / (filename + ".tmp")
            with staged.open("w", encoding="ascii", newline="\n") as handle:
                for row in self.database.execute(query):
                    handle.write("\t".join(row) + "\n")
            staged.replace(output_dir / filename)
            count = self.database.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"{filename}: {count:,} unique records")


def csv_rows(path):
    with path.open("rb") as handle:
        compressed = handle.read(2) == b"\x1f\x8b"
    opener = gzip.open if compressed else open
    with opener(path, "rt", encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle)


def uctcrdb_chain(row):
    chain = chain_type(row.get("Gene"))
    if chain:
        return chain
    v_gene = (row.get("Vgene") or "").upper()
    j_gene = (row.get("Jgene") or "").upper()
    if v_gene.startswith(("TRGV", "TCRGV")) or j_gene.startswith(("TRGJ", "TCRGJ")):
        return "gamma"
    if v_gene.startswith(("TRDV", "TCRDV")) or j_gene.startswith(("TRDJ", "TCRDJ")):
        return "delta"
    return None


def read_uctcrdb(raw_dir, corpus):
    for path in sorted((raw_dir / "UcTCRdb").glob("*.csv.gz")):
        for row in csv_rows(path):
            if "CDR3g" in row and "CDR3d" in row:
                corpus.add(row["CDR3g"], row["CDR3d"], "UcTCRdb")
            else:
                chain = uctcrdb_chain(row)
                if chain == "gamma":
                    corpus.add(row.get("CDR3"), None, "UcTCRdb")
                elif chain == "delta":
                    corpus.add(None, row.get("CDR3"), "UcTCRdb")


def xlsx_rows(path):
    with zipfile.ZipFile(path) as workbook:
        shared_strings = []
        if "xl/sharedStrings.xml" in workbook.namelist():
            strings = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
            shared_strings = [
                "".join(part.text or "" for part in item.findall(".//x:t", XLSX_NS))
                for item in strings.findall("x:si", XLSX_NS)
            ]
        sheets = sorted(
            name
            for name in workbook.namelist()
            if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)
        )
        if not sheets:
            raise ValueError(f"No worksheet found in {path}")
        sheet = ElementTree.fromstring(workbook.read(sheets[0]))
        headers = None
        for row in sheet.findall(".//x:sheetData/x:row", XLSX_NS):
            values = {}
            for cell in row.findall("x:c", XLSX_NS):
                column = re.match(r"[A-Z]+", cell.get("r", ""))
                if not column:
                    continue
                raw_value = cell.findtext("x:v", default="", namespaces=XLSX_NS)
                if cell.get("t") == "s" and raw_value:
                    value = shared_strings[int(raw_value)]
                elif cell.get("t") == "inlineStr":
                    value = "".join(part.text or "" for part in cell.findall(".//x:t", XLSX_NS))
                else:
                    value = raw_value
                values[column.group()] = value
            if headers is None:
                headers = values
            else:
                yield {header: values.get(column, "") for column, header in headers.items()}


def read_iedb(raw_dir, corpus):
    for path in sorted((raw_dir / "IEDB").glob("*.xlsx")):
        for row in xlsx_rows(path):
            gamma = delta = None
            for number in (1, 2):
                prefix = f"Chain {number} - "
                chain = chain_type(row.get(prefix + "Type"))
                sequence = row.get(prefix + "CDR3 Curated")
                if chain == "gamma":
                    gamma = sequence
                elif chain == "delta":
                    delta = sequence
            corpus.add(gamma, delta, "IEDB")


def read_tcrdb2(raw_dir, corpus):
    for path in sorted((raw_dir / "TCRdb2.0").glob("*.zip")):
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                if member.is_dir() or not member.filename.lower().endswith(".csv"):
                    continue
                name = Path(member.filename).name.upper()
                filename_chain = "gamma" if ".TRG." in name else "delta" if ".TRD." in name else None
                with archive.open(member) as binary:
                    with io.TextIOWrapper(binary, encoding="utf-8-sig", newline="") as handle:
                        reader = csv.DictReader(handle)
                        columns = {name.lower(): name for name in (reader.fieldnames or []) if name}
                        aa_column = columns.get("aaseq")
                        chain_column = columns.get("chain")
                        if not aa_column:
                            raise ValueError(f"Missing AAseq column in {path}:{member.filename}")
                        for row in reader:
                            reported_chain = chain_type(row.get(chain_column)) if chain_column else None
                            if reported_chain and filename_chain and reported_chain != filename_chain:
                                continue
                            chain = reported_chain or filename_chain
                            if chain == "gamma":
                                corpus.add(row.get(aa_column), None, "TCRdb2.0")
                            elif chain == "delta":
                                corpus.add(None, row.get(aa_column), "TCRdb2.0")


def read_gse180059(raw_dir, corpus):
    required = {"barcode", "chain", "cdr3", "is_cell", "high_confidence", "productive", "full_length"}
    for path in sorted((raw_dir / "GSE180059").glob("*_filtered_contig_annotations.csv.gz")):
        cells = defaultdict(lambda: {"gamma": set(), "delta": set()})
        with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            missing = required - set(reader.fieldnames or ())
            if missing:
                raise ValueError(f"Missing columns in {path}: {', '.join(sorted(missing))}")
            for row in reader:
                if any((row[key] or "").strip().lower() != "true" for key in
                       ("is_cell", "high_confidence", "productive", "full_length")):
                    continue
                chain = chain_type(row["chain"])
                barcode = (row["barcode"] or "").strip()
                sequence = clean_cdr3(row["cdr3"])
                if barcode and chain and sequence:
                    cells[barcode][chain].add(sequence)

        # Barcodes are local to one library, so each file is grouped separately.
        for chains in cells.values():
            gamma, delta = chains["gamma"], chains["delta"]
            if len(gamma) == len(delta) == 1:
                corpus.add(next(iter(gamma)), next(iter(delta)), "GSE180059")
            else:
                for sequence in gamma:
                    corpus.add(sequence, None, "GSE180059")
                for sequence in delta:
                    corpus.add(None, sequence, "GSE180059")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "data" / "raw")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "processed")
    args = parser.parse_args()
    if not args.raw_dir.is_dir():
        parser.error(f"Raw data directory does not exist: {args.raw_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="gdtcr_clean_") as temporary:
        with closing(sqlite3.connect(Path(temporary) / "dedup.sqlite3")) as database:
            corpus = Corpus(database)
            read_uctcrdb(args.raw_dir, corpus)
            read_iedb(args.raw_dir, corpus)
            read_tcrdb2(args.raw_dir, corpus)
            read_gse180059(args.raw_dir, corpus)
            for source, counts in sorted(corpus.source_counts.items()):
                print(f"{source}: gamma={counts[0]:,}, delta={counts[1]:,}, paired={counts[2]:,}")
            corpus.write_files(args.output_dir)


if __name__ == "__main__":
    main()
