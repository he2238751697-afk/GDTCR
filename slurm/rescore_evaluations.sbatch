#!/usr/bin/env bash
# Rescore frozen candidates after correcting the reverse-direction chain order.
#SBATCH --job-name=gdtcr-audit-scores
#SBATCH --array=0-1
#SBATCH --cpus-per-task=4
#SBATCH --mem=24G
#SBATCH --time=04:00:00
#SBATCH --gres=gpu:1
#SBATCH --output=artifacts/slurm/%x-%A_%a.out
#SBATCH --error=artifacts/slurm/%x-%A_%a.err
set -euo pipefail
cd "${SLURM_SUBMIT_DIR}"
source slurm/common.sh
export OMP_NUM_THREADS=4
for GDTCR_TAG in a800_early a800_random a800_split3407 a800_shuffled unconditional_a800_unconditional; do
  "${GDTCR_PYTHON}" scripts/rescore_evaluations.py \
    --input "artifacts/evaluations/${GDTCR_TAG}/seed-${GDTCR_INDEX}/test.json" \
    --output "artifacts/evaluations/audited/${GDTCR_TAG}/seed-${GDTCR_INDEX}/test.json" \
    --device cuda --batch-size 512 --likelihood
done
for GDTCR_TAG in candidate_pools_a800_early candidate_pools_a800_early_validation; do
  "${GDTCR_PYTHON}" scripts/rescore_evaluations.py \
    --input "artifacts/evaluations/${GDTCR_TAG}/seed-${GDTCR_INDEX}.json" \
    --output "artifacts/evaluations/audited/${GDTCR_TAG}/seed-${GDTCR_INDEX}.json" \
    --device cuda --batch-size 512
done
"${GDTCR_PYTHON}" scripts/analyze_ranker.py \
  --validation "artifacts/evaluations/audited/candidate_pools_a800_early_validation/seed-${GDTCR_INDEX}.json" \
  --evaluation "artifacts/evaluations/audited/candidate_pools_a800_early/seed-${GDTCR_INDEX}.json" \
  --output "artifacts/analysis/audited/ranker_a800_early_seed${GDTCR_INDEX}.json"
