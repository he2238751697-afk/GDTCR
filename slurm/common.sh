#!/usr/bin/env bash
# Source from the repository root after changing to SLURM_SUBMIT_DIR.
GDTCR_PYTHON="${GDTCR_PYTHON:-/gpfs/work/bio/zihanhe25/miniconda3/envs/mhcii-esm2/bin/python}"
GDTCR_INDEX="${SLURM_ARRAY_TASK_ID:?submit an array job}"
GDTCR_SEED=$((3407 + 101 * SLURM_ARRAY_TASK_ID))

gdtcr_train_denoiser() {
  "${GDTCR_PYTHON}" scripts/train_denoiser.py \
    --device cuda --seed "${GDTCR_SEED}" \
    --sampling "${GDTCR_SAMPLING:-sqrt}" --steps "${GDTCR_STEPS:-20000}" \
    --batch-size "${GDTCR_PRETRAIN_BATCH_SIZE:-1024}" --learning-rate 3e-4 \
    --warmup-steps 500 --validation-interval 500 --checkpoint-interval 2000 \
    --validation-sequences 2048 --num-workers 4 "$@"
}

gdtcr_train_generator() {
  "${GDTCR_PYTHON}" scripts/train_generator.py \
    --device cuda --seed "${GDTCR_SEED}" --direction both \
    --steps "${GDTCR_GENERATOR_STEPS:-1500}" \
    --batch-size "${GDTCR_GENERATOR_BATCH_SIZE:-256}" \
    --learning-rate "${GDTCR_GENERATOR_LR:-2e-5}" --warmup-steps 200 \
    --validation-interval "${GDTCR_GENERATOR_VALIDATION_INTERVAL:-100}" \
    --checkpoint-interval "${GDTCR_GENERATOR_CHECKPOINT_INTERVAL:-500}" \
    --early-stopping-patience "${GDTCR_GENERATOR_PATIENCE:-5}" --num-workers 2 "$@"
}

gdtcr_train_ranker() {
  "${GDTCR_PYTHON}" scripts/train_ranker.py \
    --device cuda --seed "${GDTCR_SEED}" --steps "${GDTCR_RANKER_STEPS:-3000}" \
    --batch-size "${GDTCR_RANKER_BATCH_SIZE:-256}" --embedding-batch-size 256 \
    --learning-rate 3e-4 --validation-interval "${GDTCR_RANKER_VALIDATION_INTERVAL:-250}" \
    --early-stopping-patience "${GDTCR_RANKER_PATIENCE:-8}" "$@"
}

gdtcr_evaluate() {
  "${GDTCR_PYTHON}" scripts/evaluate_models.py \
    --device cuda --seed "${GDTCR_SEED}" --batch-size 64 --samples 64 \
    --max-new-tokens 35 --temperature 1.0 --top-p 0.95 "$@"
}

gdtcr_evaluate_pools() {
  "${GDTCR_PYTHON}" scripts/evaluate_candidate_pools.py \
    --device cuda --seed "${GDTCR_SEED}" --batch-size 128 --negatives 100 "$@"
}

gdtcr_source_post() {
  local protocol="$1" pretrain="$2"
  local data="data/splits/${protocol}"
  local generator="artifacts/runs/generator/${protocol}/seed-${GDTCR_INDEX}"
  local prior="artifacts/runs/generator/${protocol}_constant/seed-${GDTCR_INDEX}"
  local ranker="artifacts/runs/ranker/${protocol}/seed-${GDTCR_INDEX}"
  local mode output model tag raw
  local -a ranker_args
  # Keep the frozen transfer budgets independent of internal-run overrides.
  for mode in paired constant; do
    output="${generator}"
    if [[ "${mode}" == "constant" ]]; then output="${prior}"; fi
    gdtcr_train_generator --train "${data}/train.tsv" --validation "${data}/validation.tsv" \
      --init "${pretrain}/last.pt" --output "${output}" --source-mode "${mode}" \
      --steps 1500 --batch-size 256 --learning-rate 2e-5 --validation-interval 100 \
      --checkpoint-interval 500 --early-stopping-patience 5
  done
  gdtcr_train_ranker --train "${data}/train.tsv" --validation "${data}/validation.tsv" \
    --init "${generator}/best.pt" --output "${ranker}" \
    --steps 3000 --batch-size 256 --validation-interval 250 --early-stopping-patience 8
  for mode in paired constant shuffled; do
    model="${generator}/best.pt"
    tag="${protocol}"
    ranker_args=(--ranker "${ranker}/best.pt")
    if [[ "${mode}" == "constant" ]]; then
      model="${prior}/best.pt"
      tag="${protocol}_constant"
      ranker_args=()
    elif [[ "${mode}" == "shuffled" ]]; then
      tag="${protocol}_shuffled"
    fi
    raw="artifacts/evaluations/${tag}/seed-${GDTCR_INDEX}/test.json"
    gdtcr_evaluate --generator "${model}" "${ranker_args[@]}" \
      --pairs "${data}/test.tsv" --output "${raw}" --source-mode "${mode}"
    "${GDTCR_PYTHON}" scripts/rescore_evaluations.py --input "${raw}" \
      --output "artifacts/evaluations/audited/${tag}/seed-${GDTCR_INDEX}/test.json" \
      --device cuda --batch-size 512 --likelihood
  done
}
