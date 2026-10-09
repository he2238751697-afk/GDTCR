import unittest
import itertools
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from scripts.analyze_strata import positive_count_bin, source_length_bin
from scripts.summarize_results import (clustered_interval, component_lookup,
                                       free_metrics, random_ap, random_hit,
                                       summarize_free)
from scripts.analyze_ranker import average_precision


class StrataTest(unittest.TestCase):
    def test_source_length_bins_are_fixed(self):
        self.assertEqual(source_length_bin(12), "short_<=12")
        self.assertEqual(source_length_bin(13), "medium_13-16")
        self.assertEqual(source_length_bin(16), "medium_13-16")
        self.assertEqual(source_length_bin(17), "long_>=17")

    def test_positive_count_bins_are_fixed(self):
        self.assertEqual(positive_count_bin(1), "one")
        self.assertEqual(positive_count_bin(3), "two_to_three")
        self.assertEqual(positive_count_bin(4), "four_or_more")

    def test_random_ranking_expectations_match_exhaustive_rankings(self):
        labels = [1, 1, 0, 0, 0]
        permutations = set(itertools.permutations(labels))
        expected_hit = sum(any(p[:2]) for p in permutations) / len(permutations)
        expected_ap = sum(average_precision(list(p), [5, 4, 3, 2, 1])
                          for p in permutations) / len(permutations)
        self.assertAlmostEqual(random_hit(5, 2, 2), expected_hit)
        self.assertAlmostEqual(random_ap(5, 2), expected_ap)

    def test_shared_partner_connects_bootstrap_units(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pairs.tsv"
            path.write_text("G1\tD1\nG2\tD1\nG2\tD2\nG3\tD3\n")
            lookup = component_lookup(path)
        self.assertEqual(lookup["gamma", "G1"], lookup["gamma", "G2"])
        self.assertEqual(lookup["gamma", "G1"], lookup["delta", "D2"])
        self.assertNotEqual(lookup["gamma", "G1"], lookup["gamma", "G3"])
        # Differences within a component cancel in every cluster replicate.
        interval = clustered_interval([1, -1, 0], [0, 0, 1], replicates=100)
        self.assertEqual(interval["lower"], 0)
        self.assertEqual(interval["upper"], 0)

    def test_reranking_cannot_inject_a_recorded_positive(self):
        row = {"positives": ["P"], "unique_candidates": ["A", "B"],
               "reranked_candidates": ["P", "A"]}
        with self.assertRaises(AssertionError):
            free_metrics(row)

    def test_fractional_recall_is_not_a_binomial_event(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pairs.tsv").write_text("G\tP1\nG\tP2\n")
            path = root / "evaluation.json"
            path.write_text(json.dumps({
                "pairs": "pairs.tsv",
                "directions": {"gamma_to_delta": {"conditional_token_nll": 1.0}},
                "rows": {"gamma_to_delta": [{
                    "source": "G", "positives": ["P1", "P2"],
                    "unique_candidates": ["P1", "X"],
                }]},
            }))
            with patch("scripts.summarize_results.ROOT", root):
                intervals = summarize_free(path, 100)["directions"]["gamma_to_delta"]["intervals"]
        self.assertEqual(intervals["sample_order_hit_at_5"]["events"], 1)
        self.assertEqual(intervals["sample_order_recall_at_5"]["estimate"], 0.5)
        self.assertNotIn("events", intervals["sample_order_recall_at_5"])
        self.assertNotIn("iid_wilson_reference", intervals["sample_order_recall_at_5"])


if __name__ == "__main__":
    unittest.main()
