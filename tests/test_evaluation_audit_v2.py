import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_evaluations_v2 import decode_saved_sample, same
from gdtcr.evaluation import decode_sample_v2
from gdtcr.model import AA_TO_ID, BOS, CHAIN_TO_ID, EOS, PAD


class SavedTokenAuditTests(unittest.TestCase):
    def test_budget_exhaustion_keeps_invalid_flag_and_original_reason(self):
        # Reproduce a real 36-residue no-EOS output. The model pads its 38-token
        # decoding prefix to 64 columns before the stored decoder trims padding.
        full = [BOS, CHAIN_TO_ID["delta"]] + [AA_TO_ID["A"]] * 36 + [PAD] * 26
        stored = decode_sample_v2(full, "delta")
        self.assertEqual(stored["reason"], "pad_before_eos")
        self.assertFalse(stored["valid"])
        self.assertEqual(len(stored["tokens"]), 38)
        self.assertEqual(decode_saved_sample(stored["tokens"], "delta", 64), stored)
        corrupted = {**stored, "valid": True}
        with self.assertRaises(ValueError):
            same(corrupted, decode_saved_sample(stored["tokens"], "delta", 64), "saved sample")

    def test_observed_eos_reconstruction_preserves_valid_sequence(self):
        tokens = [BOS, CHAIN_TO_ID["gamma"]] + [AA_TO_ID["C"]] * 6 + [EOS]
        stored = decode_sample_v2(tokens + [PAD] * (64 - len(tokens)), "gamma")
        self.assertTrue(stored["valid"])
        self.assertEqual(decode_saved_sample(stored["tokens"], "gamma", 64), stored)


if __name__ == "__main__":
    unittest.main()
