#!/usr/bin/env bash
# Identical candidate pools for all neural score controls.
#SBATCH --job-name=gdtcr-retrieval-controls
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
export OMP_NUM_THREADS=8
"${GDTCR_PYTHON}" scripts/add_retrieval_controls.py \
  --input "artifacts/evaluations/audited/candidate_pools_a800_early/seed-${GDTCR_INDEX}.json" \
  --output "artifacts/evaluations/controls/candidate_pools_a800_early/seed-${GDTCR_INDEX}.json" \
  --prior-gamma "artifacts/runs/unconditional/a800_unconditional/target-gamma/seed-${GDTCR_INDEX}/best.pt" \
  --prior-delta "artifacts/runs/unconditional/a800_unconditional/target-delta/seed-${GDTCR_INDEX}/best.pt" \
  --device cuda --seed "${GDTCR_SEED}"
for GDTCR_TAG in source_holdout source_shared; do
  GDTCR_OUTPUT="artifacts/evaluations/audited/candidate_pools_${GDTCR_TAG}/seed-${GDTCR_INDEX}.json"
  gdtcr_evaluate_pools \
    --generator "artifacts/runs/generator/${GDTCR_TAG}/seed-${GDTCR_INDEX}/best.pt" \
    --ranker "artifacts/runs/ranker/${GDTCR_TAG}/seed-${GDTCR_INDEX}/best.pt" \
    --pairs "data/splits/${GDTCR_TAG}/test.tsv" --output "${GDTCR_OUTPUT}"
  "${GDTCR_PYTHON}" scripts/add_retrieval_controls.py \
    --input "${GDTCR_OUTPUT}" \
    --output "artifacts/evaluations/controls/candidate_pools_${GDTCR_TAG}/seed-${GDTCR_INDEX}.json" \
    --prior "artifacts/runs/generator/${GDTCR_TAG}_constant/seed-${GDTCR_INDEX}/best.pt" \
    --device cuda --seed "${GDTCR_SEED}"
done
