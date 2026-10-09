#!/usr/bin/env bash
# Fixed-budget test evaluation after generator and ranker checkpoints finish.
# Submit with --dependency=afterok:<ranker-job-id>.
#
#SBATCH --job-name=gdtcr-evaluate
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
MODEL_RUN_TAG="${GDTCR_MODEL_RUN_TAG:-${RUN_TAG}}"
OUTPUT_RUN_TAG="${GDTCR_OUTPUT_RUN_TAG:-${RUN_TAG}}"
SPLIT_SEED="${GDTCR_SPLIT_SEED:-17}"
SOURCE_MODE="${GDTCR_SOURCE_MODE:-paired}"
GENERATOR="artifacts/runs/generator/${MODEL_RUN_TAG}/seed-${GDTCR_INDEX}/best.pt"
RANKER="artifacts/runs/ranker/${MODEL_RUN_TAG}/seed-${GDTCR_INDEX}/best.pt"
OUTPUT="artifacts/evaluations/${OUTPUT_RUN_TAG}/seed-${GDTCR_INDEX}/test.json"
TEST_PAIRS="data/splits/split_seed${SPLIT_SEED}/test.tsv"

echo "host=$(hostname)"
echo "job=${SLURM_JOB_ID} array=${GDTCR_INDEX} partition=${SLURM_JOB_PARTITION}"
echo "git=$(git rev-parse HEAD)"
echo "generator=${GENERATOR} ranker=${RANKER}"
echo "model_run_tag=${MODEL_RUN_TAG} output_run_tag=${OUTPUT_RUN_TAG}"
echo "split_seed=${SPLIT_SEED} source_mode=${SOURCE_MODE}"

gdtcr_evaluate --generator "${GENERATOR}" --ranker "${RANKER}" \
  --pairs "${TEST_PAIRS}" --output "${OUTPUT}" --source-mode "${SOURCE_MODE}"
