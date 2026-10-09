#!/usr/bin/env bash
# Evaluate the two target-chain-only models with the common fixed-budget
# evaluator.  The constant source mode retains only the input chain token.
#
#SBATCH --job-name=gdtcr-unconditional-eval
#SBATCH --array=0-1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH --gres=gpu:1
#SBATCH --output=artifacts/slurm/%x-%A_%a.out
#SBATCH --error=artifacts/slurm/%x-%A_%a.err

set -euo pipefail
cd "${SLURM_SUBMIT_DIR}"

source slurm/common.sh
GPU_TAG="${GDTCR_GPU_TAG:?set GDTCR_GPU_TAG}"
RUN_TAG="${GDTCR_RUN_TAG:-${GPU_TAG}}"
SPLIT_SEED="${GDTCR_SPLIT_SEED:-17}"
RUN_ROOT="artifacts/runs/unconditional/${RUN_TAG}"
OUTPUT="artifacts/evaluations/unconditional_${RUN_TAG}/seed-${GDTCR_INDEX}/test.json"
TEST_PAIRS="data/splits/split_seed${SPLIT_SEED}/test.tsv"

echo "host=$(hostname)"
echo "job=${SLURM_JOB_ID} array=${GDTCR_INDEX} partition=${SLURM_JOB_PARTITION}"
echo "git=$(git rev-parse HEAD)"
echo "split_seed=${SPLIT_SEED}"

gdtcr_evaluate \
  --generator-gamma-to-delta "${RUN_ROOT}/target-delta/seed-${GDTCR_INDEX}/best.pt" \
  --generator-delta-to-gamma "${RUN_ROOT}/target-gamma/seed-${GDTCR_INDEX}/best.pt" \
  --pairs "${TEST_PAIRS}" --output "${OUTPUT}" --source-mode constant
