#!/usr/bin/env bash
# Explicit CPU task submission, with the same immutable manifest runner as GPU jobs.
#SBATCH --job-name=gdtcr-v2-cpu
#SBATCH --partition=cpudebug
#SBATCH --qos=cpudebug
#SBATCH --account=jiameng_mres
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=artifacts/slurm/%x-%A_%a.out
#SBATCH --error=artifacts/slurm/%x-%A_%a.err
set -euo pipefail
cd "${SLURM_SUBMIT_DIR}"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"
export MKL_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"
export OPENBLAS_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"
export PYTHONDONTWRITEBYTECODE=1
GDTCR_TASK_PYTHON="${GDTCR_PYTHON:-/gpfs/work/bio/zihanhe25/Programs/GDTCR/artifacts/completion_v2/runtime/bin/python}"
exec "${GDTCR_TASK_PYTHON}" scripts/execute_manifest.py \
  --manifest "${GDTCR_MANIFEST:?provide immutable task manifest}" \
  --task "${SLURM_ARRAY_TASK_ID:?submit an array}"
