#!/usr/bin/env bash
# Fixed candidate-pool ranking diagnostics for the trained generator/ranker.
# Candidate lists contain recorded test positives plus constructed negatives;
# they are saved in the JSON output for paired comparisons.
#
#SBATCH --job-name=gdtcr-candidate-pools
#SBATCH --array=0-1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=08:00:00
#SBATCH --gres=gpu:1
#SBATCH --output=artifacts/slurm/%x-%A_%a.out
#SBATCH --error=artifacts/slurm/%x-%A_%a.err

set -euo pipefail
cd "${SLURM_SUBMIT_DIR}"

source slurm/common.sh
GPU_TAG="${GDTCR_GPU_TAG:?set GDTCR_GPU_TAG}"
RUN_TAG="${GDTCR_RUN_TAG:-${GPU_TAG}}"
SPLIT_SEED="${GDTCR_SPLIT_SEED:-17}"
EVAL_SPLIT="${GDTCR_EVAL_SPLIT:-test}"
case "${EVAL_SPLIT}" in
  test) OUTPUT_SUFFIX="" ;;
  validation) OUTPUT_SUFFIX="_validation" ;;
  *) echo "GDTCR_EVAL_SPLIT must be test or validation" >&2; exit 2 ;;
esac
GENERATOR="artifacts/runs/generator/${RUN_TAG}/seed-${GDTCR_INDEX}/best.pt"
RANKER="artifacts/runs/ranker/${RUN_TAG}/seed-${GDTCR_INDEX}/best.pt"
OUTPUT="artifacts/evaluations/candidate_pools_${RUN_TAG}${OUTPUT_SUFFIX}/seed-${GDTCR_INDEX}.json"
PAIRS="data/splits/split_seed${SPLIT_SEED}/${EVAL_SPLIT}.tsv"

echo "host=$(hostname)"
echo "job=${SLURM_JOB_ID} array=${GDTCR_INDEX} partition=${SLURM_JOB_PARTITION}"
echo "git=$(git rev-parse HEAD)"
echo "run_tag=${RUN_TAG} split_seed=${SPLIT_SEED} evaluation_split=${EVAL_SPLIT}"

gdtcr_evaluate_pools --generator "${GENERATOR}" --ranker "${RANKER}" \
  --pairs "${PAIRS}" --output "${OUTPUT}"
