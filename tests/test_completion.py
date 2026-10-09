import argparse
import json
import random
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gdtcr.model import make_batch
from gdtcr.provenance import begin_run
from gdtcr.negatives import TrainingNegativeSampler
from train_denoiser import RandomSequenceDataset
from train_generator import query_validation_metrics
from train_ranker import ranking_metrics
from prepare_completion import directional_seen, directional_unseen, nested_subsets, validation_roles


class CompletionProtocolTests(unittest.TestCase):
    def test_query_macro_validation_keeps_query_identity_for_constant_sources(self):
        rows = [("gamma", "G1", "delta", "AAA"), ("gamma", "G1", "delta", "AAAA"),
                ("gamma", "G2", "delta", "AAA"), ("delta", "D1", "gamma", "AAAA")]
        with patch("train_generator.sequence_mean_nll", return_value=[1., 3., 6., 10.]) as score:
            result = query_validation_metrics(None, rows, "cpu", 4, "constant")
        self.assertEqual(result["direction_query_nll"], {"gamma": 4., "delta": 10.})
        self.assertEqual(result["selection_nll"], 7.)
        self.assertEqual(score.call_args.args[1], [(row[0], "") for row in rows])

    def test_reverse_direction_contributes_to_ranker_selection(self):
        class FixedRanker:
            def eval(self):
                return self
            def score_matrix(self, gamma, delta):
                return torch.tensor([[3., 4.], [2., 1.]])
        encoded = (["G1", "G2"], ["D1", "D2"], torch.zeros(2, 1), torch.zeros(2, 1))
        with patch("train_ranker.encode_pair_pool", return_value=encoded):
            result = ranking_metrics(FixedRanker(), [("G1", "D1"), ("G2", "D2")], 2)
        self.assertEqual(result["directions"]["gamma_to_delta"]["mrr"], .5)
        self.assertEqual(result["directions"]["delta_to_gamma"]["mrr"], .75)
        self.assertEqual(result["mrr"], .625)

    def test_negative_sampler_excludes_all_known_alternative_partners(self):
        pairs = [("CASSAF", "CAWDDF"), ("CASSAF", "CAWDAF"),
                 ("CASSLF", "CAWDGF"), ("CASSGF", "CAWDDF")]
        first, second = TrainingNegativeSampler(pairs), TrainingNegativeSampler(pairs)
        negatives = first.sample(pairs * 5, 5, 3407)
        self.assertEqual(negatives, second.sample(pairs * 5, 5, 3407))
        self.assertFalse(set(negatives) & set(pairs))
        self.assertTrue({g for g, _ in negatives} <= {g for g, _ in pairs})
        self.assertTrue({d for _, d in negatives} <= {d for _, d in pairs})
        self.assertGreater(first.stats["hard_draws"], 0)
        self.assertGreater(first.stats["random_draws"], 0)

    def test_directional_protocols_and_nested_components(self):
        pairs = [(f"G{i}", f"D{i}_{j}") for i in range(15) for j in range(4)]
        for column in (0, 1):
            split = directional_unseen(pairs, column)
            self.assertEqual(set().union(*(set(r) for r in split.values())), set(pairs))
            source = {s: {p[column] for p in r} for s, r in split.items()}
            self.assertFalse(source["train"] & source["test"])
        seen = directional_seen(pairs, 0)
        self.assertTrue({g for g, _ in seen["test"]} <= {g for g, _ in seen["train"]})
        roles = validation_roles(seen["validation"], 0)
        self.assertFalse({g for g, _ in roles["selection"]} & {g for g, _ in roles["calibration"]})
        nested = nested_subsets(pairs)
        for lower, upper in (("10", "25"), ("25", "50"), ("50", "100")):
            self.assertTrue(set(nested[lower]) <= set(nested[upper]))
        for subset in nested.values():
            for source in {g for g, _ in subset}:
                self.assertEqual(sum(g == source for g, _ in subset), 4)

    def test_single_chain_pretraining_never_draws_other_chain(self):
        rows = [("gamma", "CASSLF"), ("delta", "CAWDTF")]
        for chain in ("gamma", "delta"):
            random.seed(17)
            dataset = RandomSequenceDataset(rows, 100, chain)
            self.assertEqual({dataset[i][0] for i in range(100)}, {chain})
        with self.assertRaises(ValueError):
            RandomSequenceDataset([rows[0]], 100, "delta")

    def test_copy_control_cannot_recover_masked_or_deleted_residues(self):
        rows = [("gamma", "CASSLGQETQYF")]
        batch = make_batch(rows, "cpu", corrupt=True, seed=912, mask_probability=1.0)
        residues = batch["labels"].ge(6)
        self.assertTrue(torch.equal(batch["damaged_mask"], residues))
        correct = batch["aligned_copy_ids"].eq(batch["labels"]) & residues
        self.assertLess(int(correct.sum()), int(residues.sum()))
        clean = make_batch(rows, "cpu")
        mask = clean["labels"].ge(6)
        self.assertTrue(torch.equal(clean["aligned_copy_ids"][mask], clean["labels"][mask]))

    def test_completed_run_and_changed_resume_inputs_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            data = folder / "input.tsv"
            data.write_text("gamma\tCASSLF\n")
            output = folder / "run"
            args = argparse.Namespace(output=output, train=data, resume=False, seed=17)
            begin_run(output, args, [data])
            (output / "run.json").write_text("{}\n")
            with self.assertRaises(FileExistsError):
                begin_run(output, args, [data])
            args.resume = True
            begin_run(output, args, [data])
            data.write_text("gamma\tCAAWLF\n")
            with self.assertRaises(ValueError):
                begin_run(output, args, [data])
            (output / "summary.json").write_text(json.dumps({"steps_completed": 10}))
            with self.assertRaises(FileExistsError):
                begin_run(output, args, [data])


if __name__ == "__main__":
    unittest.main()
