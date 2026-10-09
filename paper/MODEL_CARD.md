# GDTCR model card

Version: completion-v2, 30 September 2026. Model artifacts are research outputs
for recorded-pair recovery. The statistical evaluation is conditional on the
saved fitted models, data partitions and sampled candidates.

## Model and inputs

The generator is a 7,396,890-parameter shared encoder–decoder Transformer with
four encoder and four decoder layers, width 256, eight attention heads, feedforward
width 1,024 and dropout 0.1. Tokenization uses the 20 canonical amino acids and
chain/control tokens. It reads one gamma or delta CDR3 plus chain identity and
autoregressively proposes the other chain's CDR3. It does not receive V/J genes,
full-length receptor sequences, donor covariates, antigen or structural features.

Single-chain denoising initializes the same model. Paired training samples the
two directions equally, then samples an input query uniformly and a recorded
partner uniformly within that query. The matched constant-source control uses
the same initialization and target sampling, replacing only the input residues
with the chain token. Random initialization, edge sampling, single-direction
training, chain-mixture and nested-data controls are explicitly separate runs.

The v2 PairRanker starts from a separate copy of the selected condition-specific
generator after paired fine-tuning. It uses the encoder path with residue-only
pooling, 128-dimensional chain-specific projections, a normalized dot product
and a two-layer head with hidden width 256 and dropout 0.15. Its subsequent
optimization changes its own parameters, without updating the generator;
independence does not mean a separate training cohort. The implementation retains
the generator's unused decoder inside the stored ranker object, so the recorded
7,594,779 parameter total is a storage-level model count, not a count of only
the operations used for ranking. Its first 1,500 steps use multi-positive contrastive
training; the next 1,500 use explicit constructed negatives. Primary negatives
mix random and length/terminal-motif-matched combinations at a 1:3 positive-to-
negative ratio. Ratios 1:1 and 1:5 and random-only conditions test sensitivity.
Only training pairs define training-negative exclusions. Validation selection
excludes other recorded partners without allowing held-out pairs into gradients.

## Selection and output

New v2 models select checkpoints using a distinct selection-validation subset.
Generator selection uses direction-balanced query-macro target-token NLL;
ranker selection uses mean directional MRR after explicit-negative training
begins. Directional tasks select on their own direction. The original full-
validation v1 runs are historical comparisons and are not pooled into v2 results.

The primary generation budget is 64 draws at temperature 1 and top-p 0.95.
Split-17 primary conditional and constant-source models save 256 draws for
nested 16/64/256-prefix analyses. Invalid outputs and duplicates do not receive
replacement draws. Validity requires canonical residues, length 6–35 and EOS.
Both retaining and excluding exact training targets are reported.

Likelihood, ranker-only and fused ordering use the same saved candidate set.
Fusion weight is selected on tuning validation, with direction-specific score
scaling and equal direction weighting. Separate calibration validation selects
the acceptance threshold. Calibration with no recorded positive or no constructed
negative yields reject-all. Scores and thresholds are compatibility diagnostics
within the benchmark; they are not calibrated biological probabilities.

## Evaluation scope

Three component splits with two model seeds per condition assess exact-chain
generalization. Separate source and directional protocols inspect transfer and
target overlap. Fixed pools include recorded positives by construction and
therefore assess retrieval, whereas free generation does not inject test targets.
Their success rates are not interchangeable. Metrics include query-macro and
edge-weighted recovery, multi-positive Recall, MRR, NLL, format validity,
diversity, novelty and acceptance curves.

Distance strata and source/length/multipartner strata are descriptive. Repeated
splits and training seeds are not independent biological replicates. Component
bootstrap intervals describe test-query variability conditional on fitted models
and saved samples; [0,0] intervals after zero events are not population upper
bounds. The small distant test subsets cannot establish remote-sequence accuracy.

## Evaluated performance

At the frozen 64-draw primary setting with training targets allowed, the
conditional model's equal-direction NLL is 1.005 ± 0.004 nats per target token,
compared with 1.013 ± 0.003 for constant source and 1.115 ± 0.006 for random
initialization. Candidate coverage is 0.88 ± 0.19%, likelihood Hit@5 is
0.03 ± 0.03%, and ranker Hit@5 is 0.06 ± 0.03%. These are descriptive means/SDs
of three split means, each averaging two model seeds. All six primary paired
ranker-minus-likelihood Hit@5 intervals include zero; tuning selects zero free
ranker fusion weight in each primary fit.

Other exposure protocols give different results. Strict-source delta-to-gamma
likelihood Hit@5 is 11.93%/10.26% across the two seeds, compared with
6.68%/6.44% for constant source. With common supervised chains retained, those
values become 47.49%/44.39% and 43.68%/43.20%, respectively. Source-task hits
are concentrated in one component, and the conditional-minus-prior paired
intervals include zero. These estimates do not replace the primary task or
establish donor-independent transfer. Full fitted-model and uncertainty tables
are under `paper/results/v2/`, linked to the final evidence by SHA256.

The unseen-gamma selection role has one query with no ranking distractors and
cannot meaningfully choose among ranker checkpoints. Free primary gamma-to-delta
calibration has no recorded positive, while delta-to-gamma has only one to six;
the resulting thresholds do not establish a useful biological operating point.
An implemented scorer, a queued job, or a valid sequence alone is not evidence
of successful partner recovery.

## Use and limitations

Appropriate use is reproducible methodological comparison and candidate
prioritization for subsequent scientific study. The benchmark is dominated by
developmental thymic data and omits full receptor context. It does not validate
antigen recognition, cell-surface expression, therapeutic use, or general
performance across donors, tissues and disease states. Failure of this model
family does not establish information-theoretic impossibility of partner
prediction. Any use requiring receptor function needs independent evidence.

Checkpoints, commands, source snapshots, seeds, input/model hashes and actual
devices are recorded under `artifacts/completion_v2/`. A800 is used for fitted
v2 training; evaluation may run on 3090/4090 GPUs. Timings are descriptive, not a
controlled device comparison. See `LICENSE_AND_ACCESS.md` for release permissions.
