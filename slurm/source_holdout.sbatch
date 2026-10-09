#!/usr/bin/env bash
# Frozen source-held-out experiment; see paper/analysis_protocol.md.
#SBATCH --job-name=gdtcr-source-holdout
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
GDTCR_DATA=data/splits/source_holdout
GDTCR_PRETRAIN="artifacts/runs/pretrain/source_holdout/seed-${GDTCR_INDEX}"
export OMP_NUM_THREADS=8

gdtcr_train_denoiser --train "${GDTCR_DATA}/pretrain/train.tsv" \
  --validation "${GDTCR_DATA}/pretrain/gamma_validation.tsv" "${GDTCR_DATA}/pretrain/delta_validation.tsv" \
  --output "${GDTCR_PRETRAIN}" --sampling sqrt --steps 20000 --batch-size 1024

gdtcr_source_post source_holdout "${GDTCR_PRETRAIN}"
