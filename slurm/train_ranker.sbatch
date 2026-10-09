#!/usr/bin/env bash
# Independent pair ranker initialized from the generator encoder.
# Use --dependency=afterok:<generator-job-id> when submitting this stage.
#
#SBATCH --job-name=gdtcr-ranker
#SBATCH --array=0-1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=1-00:00:00
#SBATCH --gres=gpu:1
#SBATCH --output=artifacts/slurm/%x-%A_%a.out
#SBATCH --error=artifacts/slurm/%x-%A_%a.err

set -euo pipefail
cd "${SLURM_SUBMIT_DIR}"

source slurm/common.sh
GPU_TAG="${GDTCR_GPU_TAG:?set GDTCR_GPU_TAG}"
RUN_TAG="${GDTCR_RUN_TAG:-${GPU_TAG}}"
SPLIT_SEED="${GDTCR_SPLIT_SEED:-17}"
INIT="artifacts/runs/generator/${RUN_TAG}/seed-${GDTCR_INDEX}/best.pt"
RUN_DIR="artifacts/runs/ranker/${RUN_TAG}/seed-${GDTCR_INDEX}"
TRAIN_PAIRS="data/splits/split_seed${SPLIT_SEED}/train.tsv"
VALIDATION_PAIRS="data/splits/split_seed${SPLIT_SEED}/validation.tsv"
mkdir -p "${RUN_DIR}" artifacts/slurm

echo "host=$(hostname)"
echo "job=${SLURM_JOB_ID} array=${GDTCR_INDEX} partition=${SLURM_JOB_PARTITION}"
echo "git=$(git rev-parse HEAD)"
echo "init=${INIT} split_seed=${SPLIT_SEED}"

gdtcr_train_ranker --train "${TRAIN_PAIRS}" --validation "${VALIDATION_PAIRS}" \
  --init "${INIT}" --output "${RUN_DIR}"
