#!/usr/bin/env bash
# Full single-chain denoising pretraining. Submit once per GPU partition with
# --array=0-1; each array member is an independent seed and resumable run.
#
#SBATCH --job-name=gdtcr-pretrain
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
GPU_TAG="${GDTCR_GPU_TAG:?set GDTCR_GPU_TAG}"
RUN_DIR="artifacts/runs/pretrain/${GPU_TAG}/seed-${GDTCR_INDEX}"
mkdir -p "${RUN_DIR}" artifacts/slurm

echo "host=$(hostname)"
echo "job=${SLURM_JOB_ID} array=${GDTCR_INDEX} partition=${SLURM_JOB_PARTITION}"
echo "git=$(git rev-parse HEAD)"

gdtcr_train_denoiser \
  --train data/splits/pretrain/train.tsv \
  --validation data/splits/pretrain/gamma_validation.tsv data/splits/pretrain/delta_validation.tsv \
  --output "${RUN_DIR}" --resume
