#!/usr/bin/env bash
# Submit explicitly with --array and GDTCR_MANIFEST; this script never submits jobs.
#SBATCH --job-name=gdtcr-completion
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH --gres=gpu:a800:1
#SBATCH --output=artifacts/slurm/%x-%A_%a.out
#SBATCH --error=artifacts/slurm/%x-%A_%a.err
set -euo pipefail
cd "${SLURM_SUBMIT_DIR}"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-8}"
export MKL_NUM_THREADS="${SLURM_CPUS_PER_TASK:-8}"
export PYTHONDONTWRITEBYTECODE=1
GDTCR_TASK_PYTHON="${GDTCR_PYTHON:-/gpfs/work/bio/zihanhe25/miniconda3/envs/mhcii-esm2/bin/python}"
exec "${GDTCR_TASK_PYTHON}" scripts/execute_manifest.py \
  --manifest "${GDTCR_MANIFEST:?provide immutable task manifest}" \
  --task "${SLURM_ARRAY_TASK_ID:?submit an array}"
