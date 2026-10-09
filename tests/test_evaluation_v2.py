import sys
import argparse
import gzip
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gdtcr.evaluation import decode_sample_v2, ranked_generation_metrics
from gdtcr.model import BOS, DELTA, EOS, GAMMA, PAD, encode_sequence
from prepare_candidate_pools_v2 import build_role
from evaluate_free_v2 import evaluate_direction
from evaluate_pools_v2 import summary_for_pool
from evaluate_shallow_v2 import evaluate_role as evaluate_shallow_role, train_models
from nearest_sequences_v2 import calculate_chunk, nearest, transform
from audit_data_v2 import read_sources
from evaluate_neighbors_v2 import exact_pair_scores
from train_ranker import ranking_metrics
from rapidfuzz.distance import Levenshtein


class EvaluationV2Tests(unittest.TestCase):
    def test_strict_decoding_requires_chain_eos_and_allowed_length(self):
        valid = [BOS, DELTA, *encode_sequence("CASSLF"), EOS, PAD]
        self.assertEqual(decode_sample_v2(valid, "delta")["sequence"], "CASSLF")
        self.assertEqual(decode_sample_v2(valid[:-2], "delta")["reason"], "missing_eos")
        self.assertEqual(decode_sample_v2([BOS, GAMMA, *encode_sequence("CASSLF"), EOS], "delta")["reason"], "invalid_prefix")
        self.assertEqual(decode_sample_v2([BOS, DELTA, *encode_sequence("CASSL"), EOS], "delta")["reason"], "too_short")
        self.assertEqual(decode_sample_v2([BOS, DELTA, *encode_sequence("C" * 36), EOS], "delta")["reason"], "too_long")
        self.assertEqual(decode_sample_v2(valid + [GAMMA], "delta")["reason"], "tokens_after_eos")

    def test_other_known_partners_are_not_constructed_negatives(self):
        pairs = [("CASSLF", "CAWDDF"), ("CASSGF", "CAWDAF"), ("CASSHF", "CAWDGF")]
        all_known = pairs + [("CASSLF", "CAWDAF")]
        role = build_role(pairs, all_known, 10, 17)["gamma_to_delta"]
        row = next(row for row in role["rows"] if row["source"] == "CASSLF")
        self.assertNotIn("CAWDAF", row["full_candidates"])
        for candidates in row["pools"].values():
            self.assertIn("CAWDDF", candidates)
            self.assertNotIn("CAWDAF", candidates)

    def test_multi_positive_recall_uses_positive_denominator(self):
        result = ranked_generation_metrics(["A", "B"], ["A", "C", "B"])
        self.assertEqual(result["recall_at_1"], .5)
        self.assertEqual(result["hit_at_1"], 1.)
        self.assertEqual(result["mean_positive_rank"], 2.)
        partial = ranked_generation_metrics(["A", "B"], ["A", "C"])
        self.assertEqual(partial["mean_positive_rank"], 2.)

    def test_free_evaluation_uses_nested_fixed_draws(self):
        class FakeModel:
            def eval(self):
                return self

            def sample(self, *args, **kwargs):
                outputs = [
                    [BOS, DELTA, *encode_sequence("CAWDDF"), EOS, PAD],
                    [BOS, DELTA, *encode_sequence("CAWDAF"), EOS, PAD],
                    [BOS, DELTA, *encode_sequence("CAWDDF"), EOS, PAD],
                    [BOS, DELTA, *encode_sequence("CAWDGF"), PAD, PAD],
                ]
                return torch.tensor(outputs)

        args = argparse.Namespace(source_mode="paired", ranker_source_mode="paired",
                                  seed=17, samples=4, temperature=1., top_p=.95,
                                  batch_size=8)
        with patch("evaluate_free_v2.sequence_mean_nll", side_effect=lambda model, source, targets, device, size: [1.] * len(targets)):
            rows, summary = evaluate_direction(FakeModel(), None,
                                               [("CASSLF", "CAWDDF")],
                                               [("CASSGF", "CAWDAF")],
                                               "gamma_to_delta", args, torch.device("cpu"))
        allowed = rows[0]["prefixes"]["4/allow_training_targets"]
        excluded = rows[0]["prefixes"]["4/exclude_training_targets"]
        self.assertEqual(allowed["draws"], 4)
        self.assertEqual(allowed["valid_draws"], 3)
        self.assertEqual(allowed["unique_candidates"], 2)
        self.assertEqual(excluded["unique_candidates"], 1)
        self.assertEqual(excluded["methods"]["raw"]["hit_at_1"], 1.)
        self.assertEqual(summary["prefixes"]["4/allow_training_targets"]["valid_draw_fraction"], .75)

    def test_pool_scores_use_same_candidates_and_keep_all_positives(self):
        targets = ["CAWDAF", "CAWDDF", "CAWDGF", "CAWDHF"]
        scores = {"likelihood": [0., 3., 2., 1.],
                  "prior": [3., 2., 1., 0.]}
        result = summary_for_pool(["CAWDDF", "CAWDGF"], targets, [0, 1, 2], scores)
        self.assertEqual(result["likelihood"]["hit_at_1"], 1.)
        self.assertEqual(result["likelihood"]["recall_at_1"], .5)
        self.assertEqual(result["likelihood"]["recall_at_5"], 1.)
        self.assertEqual(result["prior"]["hit_at_1"], 0.)

    def test_chunked_nearest_distances_match_exhaustive_search(self):
        queries = ["CASSLF", "CAWDDF", "CASSGF"]
        references = ["CAWDAF", "CASSAF", "CAWDGF", "CASSHF"]
        transformed = {feature: [transform(value, feature) for value in references]
                       for feature in ("full", "interior", "end")}
        rows = calculate_chunk(queries, references, transformed, 1)
        for row, query in zip(rows, queries):
            for feature in transformed:
                values = [(Levenshtein.distance(transform(query, feature), value),
                           Levenshtein.distance(transform(query, feature), value) /
                           max(len(transform(query, feature)), len(value), 1))
                          for value in transformed[feature]]
                self.assertEqual(row[feature]["min_raw"], min(raw for raw, _ in values))
                self.assertAlmostEqual(row[feature]["min_normalized"],
                                       min(normalized for _, normalized in values), places=6)
                self.assertIn(row[feature]["nearest_raw"], references)
                self.assertIn(row[feature]["nearest_normalized"], references)

    def test_shallow_control_trains_only_from_given_pairs_and_scores_both_directions(self):
        pairs = [("CASSLF", "CAWDDF"), ("CASSGF", "CAWDAF"),
                 ("CASSHF", "CAWDGF"), ("CASSKF", "CAWDHF")]
        vectorizer, models, audit = train_models(pairs, 17)
        self.assertEqual(audit["positives"], 4)
        self.assertEqual(audit["constructed_negatives"], 12)
        pool = {"directions": build_role(pairs, pairs, 2, 17)}
        result = evaluate_shallow_role(pool, models[0.1], vectorizer,
                                       ("gamma_to_delta", "delta_to_gamma"))
        for direction in ("gamma_to_delta", "delta_to_gamma"):
            self.assertEqual(result[direction]["n_queries"], 4)
            self.assertEqual(result[direction]["summary"]["full"]["recall_at_10"], 1.)

    def test_provenance_audit_counts_cross_study_pair_in_both_studies(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pairs.tsv.gz"
            with gzip.open(path, "wt", encoding="utf-8") as handle:
                handle.write("gamma_cdr3\tdelta_cdr3\tstudies\nG\tD\tStudyA|StudyB\n")
            self.assertEqual(read_sources(path)["G", "D"], ["StudyA", "StudyB"])

    def test_two_chain_neighbor_search_checks_every_training_edge(self):
        pairs = [("AAAAAA", "GGGGGG"), ("AAAACC", "CCCCCC"), ("TTTTTT", "CCCCCC")]
        gamma_queries, delta_queries = ["AAAAAA", "AAAAC"], ["CCCCCC", "GGGGG"]
        for direction in ("gamma_to_delta", "delta_to_gamma"):
            sources, targets = (gamma_queries, delta_queries) if direction == "gamma_to_delta" \
                else (delta_queries, gamma_queries)
            scores, witnesses = exact_pair_scores(pairs, sources, targets, direction, 1, 1)
            for i, source in enumerate(sources):
                for j, target in enumerate(targets):
                    gamma, delta = (source, target) if direction == "gamma_to_delta" else (target, source)
                    costs = [(Levenshtein.normalized_distance(gamma, g) +
                              Levenshtein.normalized_distance(delta, d)) / 2 for g, d in pairs]
                    self.assertAlmostEqual(scores[i, j], -min(costs))
                    self.assertAlmostEqual(costs[witnesses[i, j]], min(costs))
            self.assertEqual(witnesses[0, 0], 1)

    def test_ranker_selection_excludes_known_alternatives_in_both_directions(self):
        class FakeRanker:
            def eval(self):
                return self

            def score_matrix(self, *args):
                return torch.tensor([[0., 2.], [2., 1.]])

        pairs = [("GA", "D1"), ("GB", "D2")]
        encoded = (["GA", "GB"], ["D1", "D2"], torch.zeros(2, 1), torch.zeros(2, 1))
        with patch("train_ranker.encode_pair_pool", return_value=encoded):
            legacy = ranking_metrics(FakeRanker(), pairs, 2)
            corrected = ranking_metrics(FakeRanker(), pairs, 2, known_pairs=set(pairs + [("GA", "D2")]))
        self.assertEqual(legacy["mrr"], .5)
        self.assertEqual(corrected["mrr"], .75)
        for direction in ("gamma_to_delta", "delta_to_gamma"):
            self.assertEqual(corrected["directions"][direction]["mrr"], .75)


if __name__ == "__main__":
    unittest.main()
