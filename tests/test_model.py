import math
import random
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

import torch

from gdtcr.model import (
    AA_TO_ID,
    BOS,
    ConditionalSeq2Seq,
    DELTA,
    EOS,
    PairRanker,
    make_batch,
    multi_positive_loss,
)
from gdtcr.training import save_checkpoint, token_loss
from gdtcr.metrics import levenshtein, normalized_distance
from scripts.analyze_evaluations import row_metrics
from scripts.evaluate_models import build_source_map, rank_candidates
from scripts.evaluate_candidate_pools import candidate_lists, ranker_scores
from scripts.analyze_ranker import (apply_threshold, average_precision, roc_auc,
                                    select_threshold)
from scripts.train_unconditional import load_pretrained_model, make_rows, pair_targets
from scripts.train_generator import PairDataset, read_directional_rows


class ModelSmokeTest(unittest.TestCase):
    def setUp(self):
        torch.manual_seed(3407)
        self.config = {
            "d_model": 32,
            "nhead": 4,
            "encoder_layers": 1,
            "decoder_layers": 1,
            "dim_feedforward": 64,
            "dropout": 0.0,
            "max_length": 64,
        }

    def test_conditional_batch_forward_and_backward(self):
        source = [("gamma", "CASSF"), ("delta", "CAVR")]
        target = [("delta", "CAVR"), ("gamma", "CASSF")]
        batch = make_batch(source, "cpu", conditional_rows=target, seed=7)
        self.assertEqual(batch["source"].shape[0], 2)
        self.assertEqual(batch["decoder"].shape, batch["labels"].shape)
        model = ConditionalSeq2Seq(**self.config)
        logits = model(batch["source"], batch["decoder"])
        loss = token_loss(logits, batch["labels"])
        self.assertTrue(math.isfinite(loss.item()))
        loss.backward()
        self.assertTrue(any(parameter.grad is not None for parameter in model.parameters()))

    def test_denoising_mask_is_deterministic_and_excludes_chain_token(self):
        rows = [("gamma", "CASSF")]
        first = make_batch(rows, "cpu", corrupt=True, seed=12)
        second = make_batch(rows, "cpu", corrupt=True, seed=12)
        self.assertTrue(torch.equal(first["source"], second["source"]))
        self.assertTrue(torch.equal(first["damaged_mask"], second["damaged_mask"]))
        self.assertFalse(first["damaged_mask"][0, 0])
        self.assertTrue(first["labels"][0, 0].item() == -100)

    def test_multi_positive_loss_accepts_duplicate_partners(self):
        scores = torch.tensor([[4.0, 1.0, 0.0], [3.0, 2.0, 0.0]])
        positives = torch.tensor([[True, True, False], [False, False, True]])
        loss = multi_positive_loss(scores, positives)
        self.assertTrue(math.isfinite(loss.item()))

    def test_sample_returns_valid_target_tokens(self):
        model = ConditionalSeq2Seq(**self.config).eval()
        source = make_batch([("gamma", "CASSF")], "cpu")["source"]
        samples = model.sample(source, "delta", max_new_tokens=6, top_p=0.9,
                               num_samples=3, generator=torch.Generator().manual_seed(9))
        self.assertEqual(samples.shape, (3, self.config["max_length"]))
        self.assertTrue(torch.all(samples[:, 0].eq(BOS)))
        self.assertTrue(torch.all(samples[:, 1].eq(DELTA)))
        allowed = set(AA_TO_ID.values()) | {EOS, 0}
        self.assertTrue(set(samples.flatten().tolist()) <= allowed | {BOS, DELTA})

    def test_ranker_scores_and_checkpoint_round_trip(self):
        encoder = ConditionalSeq2Seq(**self.config)
        ranker = PairRanker(encoder, projection_dim=16, hidden_dim=24)
        gamma = ranker.encode_sequences("gamma", ["CASSF", "CAVR"])
        delta = ranker.encode_sequences("delta", ["CAVR", "CASG"])
        scores = ranker.score_matrix(gamma, delta)
        self.assertEqual(scores.shape, (2, 2))
        self.assertTrue(torch.isfinite(scores).all())
        with tempfile.TemporaryDirectory() as temporary:
            args = Namespace()
            path = Path(temporary) / "model.pt"
            optimizer = torch.optim.AdamW(encoder.parameters(), lr=1e-3)
            save_checkpoint(path, encoder, optimizer, self.config,
                            {"step": 1}, args)
            payload = torch.load(path, map_location="cpu", weights_only=False)
            restored = ConditionalSeq2Seq(**payload["model_config"])
            restored.load_state_dict(payload["model_state"])
            self.assertEqual(set(restored.state_dict()), set(encoder.state_dict()))

    def test_baseline_distance_and_query_metrics(self):
        self.assertEqual(levenshtein("ABC", "ABC"), 0)
        self.assertEqual(levenshtein("ABC", "ADC"), 1)
        self.assertEqual(levenshtein("", "AA"), 2)
        self.assertAlmostEqual(normalized_distance("ABC", "ADC"), 1 / 3)
        row = {"positives": ["ABC"], "unique_candidates": ["XYZ", "ABC"],
               "reranked_candidates": ["ABC", "XYZ"]}
        metrics = row_metrics(row)
        self.assertEqual(metrics["coverage"], 1.0)
        self.assertEqual(metrics["raw_hit_at_1"], 0.0)
        self.assertEqual(metrics["reranked_hit_at_1"], 1.0)
        self.assertEqual(levenshtein("GATTACA", "GCATGCU"), 4)

    def test_unconditional_targets_follow_requested_chain(self):
        with tempfile.TemporaryDirectory() as temporary:
            pairs = Path(temporary) / "pairs.tsv"
            pairs.write_text("CASSF\tCAVR\nCASGF\tCAWS\n")
            for target_chain, source_chain, expected in (
                ("gamma", "delta", ["CASSF", "CASGF"]),
                ("delta", "gamma", ["CAVR", "CAWS"]),
            ):
                targets = pair_targets(pairs, target_chain)
                self.assertEqual(targets, expected)
                source, target = make_rows(source_chain, target_chain, targets)
                self.assertEqual(source, [(source_chain, "")] * 2)
                self.assertEqual(target, [(target_chain, value) for value in expected])
            with self.assertRaises(ValueError):
                pair_targets(pairs, "unknown")

    def test_unconditional_reuse_rejects_wrong_chain_or_stage(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "pretrain.pt"
            model = ConditionalSeq2Seq(**self.config)
            args = Namespace(target_chain="gamma")
            save_checkpoint(path, model, None, self.config,
                            {"stage": "pretrain", "step": 1}, args)
            restored, _ = load_pretrained_model(path, "gamma", "cpu")
            self.assertTrue(all(torch.equal(value, model.state_dict()[name])
                                for name, value in restored.state_dict().items()))
            with self.assertRaisesRegex(ValueError, "target chain"):
                load_pretrained_model(path, "delta", "cpu")
            save_checkpoint(path, model, None, self.config,
                            {"stage": "finetune", "step": 1}, args)
            with self.assertRaisesRegex(ValueError, "pretraining state"):
                load_pretrained_model(path, "gamma", "cpu")

    def test_shuffled_sources_are_deranged_and_candidate_pools_are_fixed(self):
        queries = ["AAA", "BBB", "CCC", "DDD"]
        mapping = build_source_map(queries, seed=19)
        self.assertEqual(set(mapping), set(queries))
        self.assertTrue(all(mapping[query] != query for query in queries))
        query_targets = {"AAA": {"CCCC"}, "BBB": {"DDDD"}}
        pools = candidate_lists(query_targets, {"CCCC", "DDDD", "EEEE", "FFFF"}, 2, 7)
        for kind in ("random", "length", "motif", "edit"):
            self.assertEqual(set(pools[kind]), set(query_targets))
            for query, candidates in pools[kind].items():
                self.assertTrue(query_targets[query] <= set(candidates))
                self.assertTrue(len(set(candidates) - query_targets[query]) <= 2)

    def test_ranker_diagnostics_handle_ties_and_validation_thresholds(self):
        labels = [1, 0, 1, 0]
        scores = [0.9, 0.9, 0.4, 0.1]
        self.assertAlmostEqual(roc_auc(labels, scores), 0.625)
        self.assertAlmostEqual(average_precision(labels, scores), 7 / 12)
        self.assertAlmostEqual(average_precision([0, 1, 1, 0], scores), 7 / 12)
        rejected = select_threshold([1, 0], [0.1, 0.9])
        self.assertGreater(rejected["threshold"], 0.9)
        self.assertEqual(rejected["tp"] + rejected["fp"], 0)
        rows = [{"positives": ["POS"], "candidates": ["POS", "NEG"],
                 "generator_scores": [0.1, 0.9], "ranker_scores": [0.8, 0.2]}]
        selected = select_threshold([1, 0], [0.8, 0.2])
        self.assertEqual(selected["threshold"], 0.8)
        metrics = apply_threshold(rows, "ranker", selected["threshold"])
        self.assertEqual(metrics["recall"], 1.0)
        self.assertEqual(metrics["constructed_negative_accept_rate"], 0.0)

    def test_both_evaluation_directions_preserve_gamma_delta_score_order(self):
        ranker = PairRanker(ConditionalSeq2Seq(**self.config),
                            projection_dim=2, hidden_dim=4).eval()
        # Deliberately asymmetric head.  Swapping gamma and delta reverses
        # candidate ordering and must be caught in both evaluator entrypoints.
        ranker.interaction = torch.nn.Linear(8, 1, bias=False)
        with torch.no_grad():
            ranker.interaction.weight.copy_(torch.tensor([[1., 0., -2., 0., 0., 0., 0., 0.]]))
        vectors = {("gamma", "GA"): [1., 0.], ("gamma", "GB"): [3., 0.],
                   ("delta", "DA"): [2., 0.], ("delta", "DB"): [4., 0.]}
        ranker.encode_sequences = lambda chain, seqs: torch.tensor(
            [vectors[chain, seq] for seq in seqs])
        self.assertEqual(ranker_scores(ranker, 'gamma', 'GA', 'delta', ['DA', 'DB']), [-3., -7.])
        self.assertEqual(ranker_scores(ranker, 'delta', 'DA', 'gamma', ['GA', 'GB']), [-3., -1.])
        self.assertEqual(rank_candidates(ranker, 'gamma', 'GA', ['DB', 'DA']),
                         ["DA", "DB"])
        self.assertEqual(rank_candidates(ranker, 'delta', 'DA', ['GA', 'GB']),
                         ["GB", "GA"])

    def test_source_ablation_preserves_target_draws_and_validation_labels(self):
        pairs = [("CASSF", "CAVR"), ("CASSF", "CAWS"), ("CATF", "CAWS")]
        paired = PairDataset(pairs, 1, 32)
        constant = PairDataset(pairs, 1, 32, source_mode="constant")
        random.seed(7)
        original = [paired[i] for i in range(32)]
        random.seed(7)
        ablated = [constant[i] for i in range(32)]
        self.assertEqual([(a, "", c, d) for a, _, c, d in original], ablated)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "pairs.tsv"
            path.write_text("CASSF\tCAVR\nCATF\tCAWS\n")
            original = read_directional_rows(path, "both")
            ablated = read_directional_rows(path, "both", "constant")
            self.assertEqual([(a, "", c, d) for a, _, c, d in original], ablated)


if __name__ == "__main__":
    unittest.main()
