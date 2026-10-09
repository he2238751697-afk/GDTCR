#!/usr/bin/env bash
# Target-chain-only autoregressive baseline.  Each array member is a model
# seed; run one target direction per submission.
#
#SBATCH --job-name=gdtcr-unconditional
#SBATCH --array=0-1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=2-00:00:00
#SBATCH --gres=gpu:1
#SBATCH --output=artifacts/slurm/%x-%A_%a.out
#SBATCH --error=artifacts/slurm/%x-%A_%a.err

set -euo pipefail
cd "${SLURM_SUBMIT_DIR}"

source slurm/common.sh
GPU_TAG="${GDTCR_GPU_TAG:?set GDTCR_GPU_TAG to a800, 3090, or 4090}"
RUN_TAG="${GDTCR_RUN_TAG:-${GPU_TAG}}"
SPLIT_SEED="${GDTCR_SPLIT_SEED:-17}"
TARGET_CHAIN="${GDTCR_TARGET_CHAIN:?set GDTCR_TARGET_CHAIN to gamma or delta}"
RUN_DIR="artifacts/runs/unconditional/${RUN_TAG}/target-${TARGET_CHAIN}/seed-${GDTCR_INDEX}"
mkdir -p "${RUN_DIR}" artifacts/slurm

echo "host=$(hostname)"
echo "job=${SLURM_JOB_ID} array=${GDTCR_INDEX} partition=${SLURM_JOB_PARTITION}"
echo "git=$(git rev-parse HEAD)"
echo "target_chain=${TARGET_CHAIN} split_seed=${SPLIT_SEED}"

PRETRAIN_ARGS=()
if [[ -n "${GDTCR_UNCONDITIONAL_PRETRAIN_ROOT:-}" ]]; then
  PRETRAIN_ARGS=(--pretrain-checkpoint "${GDTCR_UNCONDITIONAL_PRETRAIN_ROOT}/target-${TARGET_CHAIN}/seed-${GDTCR_INDEX}/pretrain_best.pt")
fi

"${GDTCR_PYTHON}" scripts/train_unconditional.py \
  --pretrain data/splits/pretrain/train.tsv \
  --pretrain-validation data/splits/pretrain/${TARGET_CHAIN}_validation.tsv \
  "${PRETRAIN_ARGS[@]}" \
  --train-pairs data/splits/split_seed${SPLIT_SEED}/train.tsv \
  --validation-pairs data/splits/split_seed${SPLIT_SEED}/validation.tsv \
  --target-chain "${TARGET_CHAIN}" \
  --output "${RUN_DIR}" \
  --device cuda \
  --seed "${GDTCR_SEED}" \
  --pretrain-steps "${GDTCR_UNCONDITIONAL_PRETRAIN_STEPS:-10000}" \
  --finetune-steps "${GDTCR_UNCONDITIONAL_FINETUNE_STEPS:-1500}" \
  --pretrain-learning-rate "${GDTCR_UNCONDITIONAL_PRETRAIN_LR:-1e-4}" \
  --finetune-learning-rate "${GDTCR_UNCONDITIONAL_FINETUNE_LR:-2e-5}" \
  --pretrain-batch-size "${GDTCR_UNCONDITIONAL_PRETRAIN_BATCH_SIZE:-2048}" \
  --finetune-batch-size "${GDTCR_UNCONDITIONAL_FINETUNE_BATCH_SIZE:-256}" \
  --validation-interval "${GDTCR_UNCONDITIONAL_VALIDATION_INTERVAL:-500}" \
  --pretrain-patience "${GDTCR_UNCONDITIONAL_PRETRAIN_PATIENCE:-0}" \
  --finetune-patience "${GDTCR_UNCONDITIONAL_FINETUNE_PATIENCE:-5}"
