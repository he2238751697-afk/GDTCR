#!/usr/bin/env bash
# Short single-GPU benchmark. Submit once per GPU partition with --array=0-1.
# Example:
#   sbatch --partition=gpua800 --qos=2a800 --gres=gpu:a800:1 \
#     --export=ALL,GDTCR_GPU_TAG=a800 slurm/benchmark_denoiser.sbatch
#
#SBATCH --job-name=gdtcr-bench
#SBATCH --array=0-1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=00:30:00
#SBATCH --gres=gpu:1
#SBATCH --output=artifacts/slurm/%x-%A_%a.out
#SBATCH --error=artifacts/slurm/%x-%A_%a.err

set -euo pipefail
cd "${SLURM_SUBMIT_DIR}"

source slurm/common.sh
GPU_TAG="${GDTCR_GPU_TAG:?set GDTCR_GPU_TAG}"
RUN_DIR="artifacts/benchmarks/${GPU_TAG}/task-${GDTCR_INDEX}"
mkdir -p "${RUN_DIR}" artifacts/slurm

echo "host=$(hostname)"
echo "job=${SLURM_JOB_ID} array=${GDTCR_INDEX} partition=${SLURM_JOB_PARTITION}"
echo "git=$(git rev-parse HEAD)"
echo "cuda_visible_devices=${CUDA_VISIBLE_DEVICES:-unset}"

gdtcr_train_denoiser \
  --train data/splits/pretrain/train.tsv \
  --validation data/splits/pretrain/gamma_validation.tsv data/splits/pretrain/delta_validation.tsv \
  --output "${RUN_DIR}" --sampling sqrt --steps 100 --batch-size 256 \
  --warmup-steps 20 --validation-interval 50 --checkpoint-interval 100 --validation-sequences 512
