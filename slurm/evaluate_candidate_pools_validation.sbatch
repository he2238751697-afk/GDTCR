#!/usr/bin/env bash
# Validation fixed-pool diagnostics used only to select rejection thresholds.
# The matching test-pool output is evaluated separately and is never used to
# tune the threshold.
#
#SBATCH --job-name=gdtcr-candidate-validation
#SBATCH --array=0-1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=08:00:00
#SBATCH --gres=gpu:1
#SBATCH --output=artifacts/slurm/%x-%A_%a.out
#SBATCH --error=artifacts/slurm/%x-%A_%a.err

set -euo pipefail
cd "${SLURM_SUBMIT_DIR}"

# Compatibility entry; validation selection stays explicit and separate from test.
export GDTCR_EVAL_SPLIT=validation
exec bash slurm/evaluate_candidate_pools.sbatch
