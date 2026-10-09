import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from gdtcr.statistics import bidirectional_intervals, cluster_intervals
from compare_runs_v2 import paired_difference


class ClusterStatisticsTests(unittest.TestCase):
    def test_whole_cluster_and_edge_weighting_are_preserved(self):
        rows = [{"recall": 1.}, {"recall": 0.}, {"recall": .5}]
        result = cluster_intervals(rows, ["A", "A", "B"], weights=[1, 3, 2], replicates=2000)
        self.assertAlmostEqual(result["metrics"]["recall"]["estimate"], 1 / 3)
        self.assertEqual(result["n_clusters"], 2)
        self.assertGreaterEqual(result["metrics"]["recall"]["lower"], .25)
        self.assertLessEqual(result["metrics"]["recall"]["upper"], .5)

    def test_zero_events_keep_nonzero_iid_reference_and_degenerate_cluster_flag(self):
        result = cluster_intervals([{"hit": 0.}, {"hit": 0.}], ["A", "A"], binary_metrics=["hit"])
        self.assertEqual(result["metrics"]["hit"]["upper"], 0.)
        self.assertGreater(result["metrics"]["hit"]["iid_wilson_reference"]["upper"], 0.)
        self.assertTrue(result["single_cluster"])

    def test_fractional_recall_never_gets_a_binomial_interval(self):
        with self.assertRaisesRegex(ValueError, "binary"):
            cluster_intervals([{"recall": .5}], ["A"], binary_metrics=["recall"])

    def test_identical_paired_models_have_exact_zero_difference(self):
        result = cluster_intervals([{"difference": 0.}] * 3, ["A", "A", "B"])
        self.assertEqual(result["metrics"]["difference"], {"estimate": 0., "lower": 0., "upper": 0.})

    def test_empty_strata_remain_explicit(self):
        result = cluster_intervals([], [])
        self.assertTrue(result["empty"])
        self.assertEqual(result["n_queries"], 0)

    def test_joint_endpoint_preserves_equal_direction_weight_with_unequal_queries(self):
        result = bidirectional_intervals(
            {"g_to_d": [{"hit": 1.}, {"hit": 0.}, {"hit": 0.}],
             "d_to_g": [{"hit": 0.}, {"hit": 1.}]},
            {"g_to_d": ["A", "A", "B"], "d_to_g": ["A", "B"]})
        self.assertAlmostEqual(result["metrics"]["hit"]["estimate"], 5 / 12)
        self.assertEqual(result["metrics"]["hit"]["lower"], .25)
        self.assertEqual(result["metrics"]["hit"]["upper"], .5)

    def test_actual_paired_comparison_aligns_sources_and_rejects_different_positives(self):
        left = {"gamma_to_delta": [
            {"source": "A", "positives": ["X"], "cluster": "C1", "metrics": {"full|ranker|hit_at_5": 1.}},
            {"source": "B", "positives": ["Y"], "cluster": "C2", "metrics": {"full|ranker|hit_at_5": 0.}}]}
        right = {"gamma_to_delta": [
            {"source": "B", "positives": ["Y"], "cluster": "C2", "metrics": {"full|shallow|hit_at_5": 0.}},
            {"source": "A", "positives": ["X"], "cluster": "C1", "metrics": {"full|shallow|hit_at_5": 0.}}]}
        result = paired_difference(left, right, left_method="ranker", right_method="shallow")
        self.assertEqual(result["equal_direction_macro"]["metrics"]["full|hit_at_5"]["estimate"], .5)
        right["gamma_to_delta"][0]["positives"] = ["Z"]
        with self.assertRaisesRegex(ValueError, "identical positives"):
            paired_difference(left, right, left_method="ranker", right_method="shallow")


if __name__ == "__main__":
    unittest.main()
