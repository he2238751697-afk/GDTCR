import csv
import gzip
import tempfile
import unittest
from pathlib import Path

from clean_data import read_gse180059


FIELDS = ["barcode", "chain", "cdr3", "is_cell", "high_confidence", "productive", "full_length"]


class RecordingCorpus:
    def __init__(self):
        self.records = []

    def add(self, gamma, delta, source):
        self.records.append((gamma, delta, source))


def write_contigs(path, records):
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for barcode, chain, cdr3, overrides in records:
            row = dict.fromkeys(FIELDS, "True")
            row.update({"barcode": barcode, "chain": chain, "cdr3": cdr3})
            row.update(overrides)
            writer.writerow(row)


class Gse180059Test(unittest.TestCase):
    def test_pairs_require_one_chain_of_each_type_in_one_library(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "GSE180059"
            source.mkdir()
            write_contigs(source / "one_filtered_contig_annotations.csv.gz", [
                ("cell1", "TRG", "CAAF", {}),
                ("cell1", "TRG", "CAAF", {}),
                ("cell1", "TRD", "CDDF", {}),
                ("cell2", "TRG", "CFFF", {}),
                ("cell2", "TRG", "CGGF", {}),
                ("cell2", "TRD", "CHHF", {}),
                ("shared", "TRG", "CIIF", {}),
                ("low_quality", "TRG", "CLLF", {"productive": "False"}),
                ("low_quality", "TRD", "CMMF", {}),
            ])
            write_contigs(source / "two_filtered_contig_annotations.csv.gz", [
                ("shared", "TRD", "CKKF", {}),
                ("cell3", "TRG", "CAGF", {"productive": "TRUE"}),
                ("cell3", "TRD", "CEEF", {"full_length": "TRUE"}),
                ("cell4", "TRG", "CNNF", {}),
                ("cell4", "TRD", "CXXF", {}),
            ])
            corpus = RecordingCorpus()
            read_gse180059(Path(temporary), corpus)

        paired = {(gamma, delta) for gamma, delta, _ in corpus.records if gamma and delta}
        self.assertEqual(paired, {("CAAF", "CDDF"), ("CAGF", "CEEF")})
        self.assertIn(("CIIF", None, "GSE180059"), corpus.records)
        self.assertIn((None, "CKKF", "GSE180059"), corpus.records)
        self.assertIn(("CFFF", None, "GSE180059"), corpus.records)
        self.assertIn(("CGGF", None, "GSE180059"), corpus.records)
        self.assertIn((None, "CHHF", "GSE180059"), corpus.records)
        self.assertIn((None, "CMMF", "GSE180059"), corpus.records)
        self.assertIn(("CNNF", None, "GSE180059"), corpus.records)
        self.assertNotIn(("CLLF", None, "GSE180059"), corpus.records)


if __name__ == "__main__":
    unittest.main()
