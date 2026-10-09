#!/usr/bin/env bash
# Historical v1 three-stage pipeline, using A800 by default.
# Completion-v2 uses scripts/submit_ready_v2.py and immutable task manifests.
# Other GPU families require an explicit GDTCR_GPU_TAG selection.
#
# This command only submits jobs; it does not wait for them. Override
# GDTCR_STEPS, GDTCR_PRETRAIN_BATCH_SIZE, GDTCR_GENERATOR_BATCH_SIZE, or
# GDTCR_RANKER_BATCH_SIZE before calling it when changing the budget.

set -euo pipefail

GDTCR_DRY_RUN=0
for argument in "$@"; do
  case "${argument}" in
    --dry-run) GDTCR_DRY_RUN=1 ;;
    --help|-h)
      printf '%s\n' 'Usage: bash slurm/submit_pipeline.sh [--dry-run]' \
        'Historical v1 pipeline. Without --dry-run this submits three array jobs.' \
        'Use scripts/submit_ready_v2.py with frozen manifests for completion-v2.'
      exit 0 ;;
    *) printf 'Unknown argument: %s\n' "${argument}" >&2; exit 2 ;;
  esac
done
cd "$(git rev-parse --show-toplevel)"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
MANIFEST="artifacts/slurm/pipeline-${STAMP}.env"

submit_job() {
  local label="$1"
  shift
  if [[ "${GDTCR_DRY_RUN}" == 1 ]]; then
    printf 'sbatch --parsable' >&2
    printf ' %q' "$@" >&2
    printf '\n' >&2
    printf 'DRYRUN_%s\n' "${label}"
  else
    sbatch --parsable "$@"
  fi
}

submit_family() {
  local tag="$1" partition="$2" qos="$3" gres="$4"
  local pre gen rank
  pre="$(submit_job pretrain --partition="${partition}" --qos="${qos}" \
    --gres="${gres}:1" --export="ALL,GDTCR_GPU_TAG=${tag}" \
    slurm/train_denoiser.sbatch)"
  gen="$(submit_job generator --dependency="afterok:${pre}" \
    --partition="${partition}" --qos="${qos}" --gres="${gres}:1" \
    --export="ALL,GDTCR_GPU_TAG=${tag}" slurm/train_generator.sbatch)"
  rank="$(submit_job ranker --dependency="afterok:${gen}" \
    --partition="${partition}" --qos="${qos}" --gres="${gres}:1" \
    --export="ALL,GDTCR_GPU_TAG=${tag}" slurm/train_ranker.sbatch)"
  if [[ "${GDTCR_DRY_RUN}" == 1 ]]; then
    printf '%s_pretrain=%s\n%s_generator=%s\n%s_ranker=%s\n' \
      "${tag}" "${pre}" "${tag}" "${gen}" "${tag}" "${rank}"
  else
    printf '%s_pretrain=%s\n%s_generator=%s\n%s_ranker=%s\n' \
      "${tag}" "${pre}" "${tag}" "${gen}" "${tag}" "${rank}" | tee -a "${MANIFEST}"
  fi
}

if [[ "${GDTCR_DRY_RUN}" == 0 ]]; then
  mkdir -p artifacts/slurm
  printf 'git_sha=%s\nsubmitted_at=%s\n' "$(git rev-parse HEAD)" "${STAMP}" > "${MANIFEST}"
fi
case "${GDTCR_GPU_TAG:-a800}" in
  a800) submit_family a800 gpua800 2a800 gpu:a800 ;;
  3090) submit_family 3090 gpu3090 4gpus gpu:gtx3090 ;;
  4090) submit_family 4090 gpu4090 4gpus gpu:rtx4090 ;;
  *) echo "Unsupported GDTCR_GPU_TAG: ${GDTCR_GPU_TAG}" >&2; exit 2 ;;
esac
if [[ "${GDTCR_DRY_RUN}" == 0 ]]; then
  printf 'manifest=%s\n' "${MANIFEST}"
fi
