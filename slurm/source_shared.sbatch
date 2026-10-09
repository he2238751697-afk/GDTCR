#!/usr/bin/env bash
# Complementary source transfer with shared chains allowed, duplicate edges excluded.
# Requires successful source_holdout pretraining for both seeds.
#SBATCH --job-name=gdtcr-source-shared
#SBATCH --array=0-1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --gres=gpu:1
#SBATCH --output=artifacts/slurm/%x-%A_%a.out
#SBATCH --error=artifacts/slurm/%x-%A_%a.err
set -euo pipefail
cd "${SLURM_SUBMIT_DIR}"
source slurm/common.sh
GDTCR_PRETRAIN="artifacts/runs/pretrain/source_holdout/seed-${GDTCR_INDEX}"
export OMP_NUM_THREADS=8

gdtcr_source_post source_shared "${GDTCR_PRETRAIN}"
