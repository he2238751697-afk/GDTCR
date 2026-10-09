import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gdtcr.calibration import (calibration_observations, choose_threshold,
                               acceptance_curves, fit_calibration, fit_fusion,
                               rejection_metrics, score_profile)


def candidate_row(source, positives, likelihood, ranker=None):
    candidates = list("ABCDEF")
    return {"source": source, "positives": positives, "candidates": candidates,
            "scores": {"likelihood": likelihood, "ranker": ranker},
            "groups": {"free": list(range(6))}, "reference_group": "free",
            "selection_groups": ["free"]}


class CalibrationTests(unittest.TestCase):
    def test_threshold_uses_balanced_accuracy_and_never_splits_ties(self):
        result = choose_threshold([3., 2., 2., 0.], [1, 0, 1, 0])
        self.assertEqual(result["mode"], "score")
        self.assertEqual(result["value"], 3.)
        self.assertEqual(result["balanced_accuracy"], .75)
        tied = choose_threshold([1., 1.], [0, 1])
        self.assertEqual(tied["mode"], "reject_all")

    def test_no_generated_positive_means_reject_all(self):
        result = choose_threshold([0., 1., 2.], [0, 0, 0])
        self.assertEqual(result["mode"], "reject_all")
        self.assertEqual(result["reason"], "no_recorded_positive")
        self.assertIsNone(result["balanced_accuracy"])

    def test_fusion_favors_smallest_ranker_weight_when_hit5_ties(self):
        tuning = {"gamma_to_delta": [candidate_row("T", ["A"], [6, 5, 4, 3, 2, 1], [1, 2, 3, 4, 5, 6])]}
        self.assertEqual(fit_fusion(tuning)["alpha"], 0.)

    def test_calibration_values_do_not_fit_score_scaling_or_fusion(self):
        tune = {"gamma_to_delta": [candidate_row("T", ["A"], [6, 5, 4, 3, 2, 1], [1, 2, 3, 4, 5, 6])]}
        cal = {"gamma_to_delta": [candidate_row("C", ["F"], [100, 200, 300, 400, 500, 600], [600, 500, 400, 300, 200, 100])]}
        settings = fit_calibration(tune, cal, {("T", "A"), ("C", "F")})
        self.assertEqual(settings["fusion"]["alpha"], 0.)
        self.assertEqual(settings["fusion"]["score_profiles"]["gamma_to_delta"]["likelihood"]["mean"], 3.5)
        with self.assertRaisesRegex(ValueError, "overlap"):
            fit_calibration(tune, tune, set())

    def test_other_known_partners_are_omitted_from_calibration_negatives(self):
        row = candidate_row("Q", ["A"], [6, 5, 4, 3, 2, 1])
        scores, labels, omitted = calibration_observations(
            [row], "gamma_to_delta", {"likelihood": score_profile([6, 5, 4, 3, 2, 1])},
            0., {("Q", "A"), ("Q", "B")})
        self.assertEqual(omitted, 1)
        self.assertEqual(sum(labels), 1)
        self.assertEqual(len(labels), 5)
        self.assertEqual(len(scores["likelihood"]), 5)

    def test_constant_score_scaling_is_finite(self):
        result = score_profile(np.ones(5))
        self.assertEqual(result["scale"], 1.)
        self.assertTrue(result["constant_or_empty"])

    def test_saved_curve_endpoints_and_threshold_match_direct_rejection(self):
        tuning = {"gamma_to_delta": [candidate_row("T", ["A"], [6, 5, 4, 3, 2, 1])]}
        calibration = {"gamma_to_delta": [candidate_row("C", ["A"], [6, 5, 4, 3, 2, 1])]}
        known = {("T", "A"), ("C", "A"), ("Q", "A")}
        settings = fit_calibration(tuning, calibration, known)
        row = candidate_row("Q", ["A"], [6, 5, 4, 3, 2, 1])
        curve = acceptance_curves([row], "gamma_to_delta", settings, known)["likelihood"]
        self.assertEqual(curve["points"][0]["accepted_queries"], 0)
        self.assertEqual(curve["points"][-1]["accepted_candidates"], 6)
        self.assertEqual(curve["points"][-1]["recorded_hit_at_5"], 1.)
        for point in curve["points"]:
            profile = settings["fusion"]["score_profiles"]["gamma_to_delta"]["likelihood"]
            values = (np.asarray(row["scores"]["likelihood"]) - profile["mean"]) / profile["scale"]
            direct = rejection_metrics(row, values, row["groups"]["free"], point)
            self.assertEqual(direct["accepted_candidates"], point["accepted_candidates"])
            self.assertEqual(direct["hit_at_5"], point["recorded_hit_at_5"])


if __name__ == "__main__":
    unittest.main()
