#!/usr/bin/env bash
# Run generator, ranker, and fixed-budget evaluation on one A800.
# The array uses both A800 devices concurrently and keeps the stages
# sequential within each seed.  Set GDTCR_RANDOM_INIT=1 for the
# pretraining ablation; otherwise PRETRAIN_GPU_TAG points at an existing
# single-chain checkpoint.
#
# Example random-initialization control:
#   sbatch --partition=gpua800 --qos=2a800 --gres=gpu:a800:1 \
#     --export=ALL,GDTCR_RUN_TAG=a800_random,GDTCR_SPLIT_SEED=17,GDTCR_RANDOM_INIT=1 \
#     slurm/train_eval_a800.sbatch
#
# Example second component split using the A800 pretraining checkpoints:
#   sbatch --partition=gpua800 --qos=2a800 --gres=gpu:a800:1 \
#     --export=ALL,GDTCR_RUN_TAG=a800_split3407,GDTCR_SPLIT_SEED=3407 \
#     slurm/train_eval_a800.sbatch
#
#SBATCH --job-name=gdtcr-a800-post
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
PRETRAIN_GPU_TAG="${GDTCR_PRETRAIN_GPU_TAG:-a800}"
RUN_TAG="${GDTCR_RUN_TAG:?set GDTCR_RUN_TAG}"
SPLIT_SEED="${GDTCR_SPLIT_SEED:-17}"
TRAIN_PAIRS="data/splits/split_seed${SPLIT_SEED}/train.tsv"
VALIDATION_PAIRS="data/splits/split_seed${SPLIT_SEED}/validation.tsv"
TEST_PAIRS="data/splits/split_seed${SPLIT_SEED}/test.tsv"
PRETRAIN="artifacts/runs/pretrain/${PRETRAIN_GPU_TAG}/seed-${GDTCR_INDEX}/last.pt"
GENERATOR_DIR="artifacts/runs/generator/${RUN_TAG}/seed-${GDTCR_INDEX}"
RANKER_DIR="artifacts/runs/ranker/${RUN_TAG}/seed-${GDTCR_INDEX}"
EVALUATION="artifacts/evaluations/${RUN_TAG}/seed-${GDTCR_INDEX}/test.json"
mkdir -p "${GENERATOR_DIR}" "${RANKER_DIR}" "$(dirname "${EVALUATION}")" artifacts/slurm

echo "host=$(hostname)"
echo "job=${SLURM_JOB_ID} array=${GDTCR_INDEX} partition=${SLURM_JOB_PARTITION}"
echo "git=$(git rev-parse HEAD)"
echo "run_tag=${RUN_TAG} split_seed=${SPLIT_SEED}"
echo "pretrain=${PRETRAIN} random_init=${GDTCR_RANDOM_INIT:-0}"
INIT_ARGS=()
if [[ "${GDTCR_RANDOM_INIT:-0}" != "1" ]]; then INIT_ARGS=(--init "${PRETRAIN}"); fi

gdtcr_train_generator --train "${TRAIN_PAIRS}" --validation "${VALIDATION_PAIRS}" \
  "${INIT_ARGS[@]}" --output "${GENERATOR_DIR}" --resume
gdtcr_train_ranker --train "${TRAIN_PAIRS}" --validation "${VALIDATION_PAIRS}" \
  --init "${GENERATOR_DIR}/best.pt" --output "${RANKER_DIR}"
gdtcr_evaluate --generator "${GENERATOR_DIR}/best.pt" --ranker "${RANKER_DIR}/best.pt" \
  --pairs "${TEST_PAIRS}" --output "${EVALUATION}"
