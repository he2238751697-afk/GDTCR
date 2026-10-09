"""Guard against a previously observed dry-run accidentally submitting jobs."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LegacySubmissionTests(unittest.TestCase):
    def run_cli(self, argument):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "submission_was_called"
            stub = root / "sbatch"
            stub.write_text('#!/bin/sh\nprintf invoked > "$GDTCR_TEST_SUBMIT_RECORD"\nprintf "999999\\n"\n')
            stub.chmod(0o755)
            env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ["PATH"],
                       GDTCR_TEST_SUBMIT_RECORD=str(marker), GDTCR_GPU_TAG="a800")
            before = set((ROOT / "artifacts/slurm").glob("pipeline-*.env"))
            result = subprocess.run(["bash", "slurm/submit_pipeline.sh", argument],
                                    cwd=ROOT, env=env, text=True, capture_output=True)
            self.assertFalse(marker.exists(), result.stdout + result.stderr)
            self.assertEqual(before, set((ROOT / "artifacts/slurm").glob("pipeline-*.env")))
            return result

    def test_dry_run_never_submits(self):
        result = self.run_cli("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr.count("sbatch --parsable"), 3)
        self.assertIn("afterok:DRYRUN_pretrain", result.stderr)
        self.assertIn("afterok:DRYRUN_generator", result.stderr)

    def test_unknown_argument_never_submits(self):
        result = self.run_cli("--not-a-valid-option")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Unknown argument", result.stderr)


if __name__ == "__main__":
    unittest.main()
