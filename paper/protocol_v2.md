# Completion protocol v2

Frozen design date: 2026-09-30. This protocol is a prospective specification for
additional runs after the internal v1 results were inspected. It is **not** a
preregistration of the historical experiments. All v1 data, checkpoints, samples,
and audited results remain immutable and are reported separately. The worktree
before this revision is preserved in
`artifacts/code_snapshots/before_completion_20260930T035442Z.tar.gz` (SHA256
`192d48e21290deb50e8e891f2f896a1649d96bfb99ff876719b7f90061b96491`).

## Questions and completion criteria

The questions remain pretraining benefit, conditional information beyond the
target prior, and independent ranking/rejection benefit. An experiment is
complete when its frozen comparison, artifacts, uncertainty and limitations are
reported; a positive result is not a completion requirement. No original required
ablation is removed in response to its expected result.

| ID | Required deliverable | Authoritative evidence |
| --- | --- | --- |
| D1 | Input/provenance hashes, component/source/length/degree audits, exact leakage assertions | Data audit JSON and split manifests |
| D2 | Three complete component splits: 17, 3407, 2026, with model seeds 3407 and 3508 | Six conditional and six matched-prior run/evaluation records |
| D3 | Direction-specific unseen-input splits and seen-input/unseen-edge diagnostics | Separate directional manifests and both-seed conditional/prior comparisons |
| D4 | Nearest supervised/pretraining distances for sources and targets, normalized/full/interior/end distances and distant subsets | Query-level distance tables and stratified results |
| P1 | Denoising copy control and damaged-residue metrics | Frozen validation corruption audit |
| P2 | sqrt/raw/balanced and gamma-only/delta-only denoising initialization | Two seeds per pretraining condition and downstream split-17 comparisons |
| G1 | Random initialization and matched constant-source controls | Same target sampling, initialization where applicable, optimizer and selection protocol |
| G2 | Bidirectional/unidirectional and input-uniform/edge-uniform training | Split-17 comparisons, per-direction sequence/token exposure |
| G3 | Nested 10/25/50/100% component-data curves | Actual component/edge counts and pretrained/random comparisons |
| R1 | Bidirectional ranker selection; random and mixed length/motif negatives at ratios 1/3/5 | Training manifests, negative audits, fixed-pool and free-candidate results |
| E1 | Same-pool likelihood, ranker, target prior, shuffled source, likelihood difference, exact edit-neighbor, shallow-feature and random controls | Frozen candidate lists and method scores |
| E2 | 16/64/256 sampling budgets and allow/exclude-training-target policy | Nested saved samples, validity, novelty, diversity, Hit and Recall |
| E3 | Validation-selected fusion and held-out validation threshold; acceptance curves | Separate tuning/calibration manifests and frozen settings applied to test |
| S1 | Both source protocols, constant/shuffled controls, source/overlap strata | Strict and shared-source artifacts with exact overlap counts |
| S2 | Query-macro and edge-weighted results, multi-positive Recall/MRR, paired component intervals | Machine-generated tables and evidence JSON |
| C1 | Recover run metadata, immutable code/input/model/evaluation lineage, documented archive, pinned environment | Release manifest, README, environment and recovery log |
| W1 | Final manuscript, references, figures/tables, supplements, model/data cards and journal-scope assessment | Rendered manuscript and deliverable audit |

## Frozen data and validation use

Reuse the original three component splits and the two source splits without
moving any test edge. Source metadata and length distributions will be audited;
the historical allocator balances edge counts, not source/length. This deviation
is disclosed rather than retrospectively optimizing the test composition.

Within each original validation set, assign whole connected components to
checkpoint selection, score/sampling tuning, and threshold calibration with
proportions 0.50/0.25/0.25 and seed 7319. Save the actual counts. New v2 training
uses only the selection part for early stopping. Calibration never selects a
checkpoint or fusion weight. Old checkpoints selected on the full validation
set retain the explicitly exploratory status of their threshold analyses.

Directional unseen-input splits use seed 1729 and 80/10/10 source-group splits;
target overlap is allowed and quantified. Seen-input diagnostics hold out edges
only for source groups with at least three observed partners, retaining at least
one training edge per input. Other groups stay in training. These tasks are
reported separately from unseen-chain generation. Validation subpartitioning for
these tasks preserves source-query groups. All observed pairs may exclude known
partners from *evaluation* distractors; training negatives use training edges
only and never inspect held-out pairs.

The pretraining pool remains the pair-excluded pool with minimum length 6.
Source experiments use the additional source-excluded pool. No unavailable donor
identity is inferred. External independence and biological function remain
limitations; obtaining a new cohort or wet-lab data is not represented as a
completed experiment.

## Training

Keep the existing 7,396,890-parameter generator. Denoising uses 20,000 steps,
batch 1,024, learning rate 3e-4, warmup 500 and the existing corruption mechanism.
All five chain-sampling conditions use equal total sequence draws; chain-specific
exposure and token counts are additionally reported. The sqrt checkpoints may
be reused because they exclude every paired chain. Downstream generator training
uses at most 1,500 steps, batch 256, learning rate 2e-5, warmup 200, validation
every 100 steps, patience 5. Select by the mean of the two direction-specific
query-macro target-token NLLs, averaging known partners within each query.

The constant-source ablation uses the identical initialization and PairDataset
sampling while removing only source residues. Random initialization changes only
initial weights. Edge-uniform sampling is a distinct ablation. Each unidirectional
model receives 750 steps at batch 256 (warmup 100), matching the nominal
per-direction exposure of a 1,500-step bidirectional model; report actual exposure
under early stopping. For data efficiency, use nested complete components with
seed 1731. Never split the 5,005-edge giant component to reach a nominal fraction;
report actual sizes, including an undersized 50% subset if necessary.

The v2 PairRanker shares the encoder, pools amino-acid residues only, uses separate
chain projections, and adds a normalized dot product to the two-layer interaction
head. Its v1 architecture is retained for loading historical checkpoints. Train
for 3,000 steps: multi-positive contrastive learning for the first 1,500 and
explicit constructed-negative BCE for the next 1,500. Random versus mixed
negative conditions use the same schedule. Mixed negatives allocate half of
draws to random combinations and half to length/terminal-motif matched
combinations; use ratios 1, 3 and 5 per positive. Record fallback counts and seeds.
The primary setting is mixed/3; other ratios and random controls run on split 17.
Use learning rate 3e-4, batch 256, validation every 250, and best mean bidirectional
validation MRR among checkpoints after the explicit-negative stage begins.
Source-query directions are selected individually for directional
diagnostics. Known alternative training partners are never labelled negative.

All ablations use both model seeds; auxiliary architecture expansion and joint
generator/ranker optimization remain future work, as in the original plan.

## Evaluation and selection

The primary endpoint stays bidirectional query-macro Hit@5 with 64 draws; report
likelihood, ranker-only and fused ordering separately, plus Hit@M, Recall@K, MRR,
mean positive rank, conditional NLL, sample validity and event denominators.
Report edge-weighted recovery alongside query-macro recovery. Sampling defaults
remain temperature 1 and top-p .95. On split-17 tuning data, additionally inspect
the prespecified grid temperature {0.7,1,1.2} by top-p {.9,.95}; it does not replace
the frozen primary setting. Generate 256 draws for the primary split-17 models
and priors; use saved prefixes for 16/64/256 and both training-target policies.
No extra sampling compensates for invalid or duplicate outputs.

For v2 samples, require standard amino acids, length 6--35 and an observed EOS;
save token IDs and the rejection reason. Count truncated outputs as invalid and
allow 36 new tokens to accommodate 35 residues plus EOS. Historical decoded-only
v1 samples cannot verify EOS and remain labelled with their legacy validity rule.

Freeze candidate lists per split/query/pool seed, shared across model seeds and
all scorers. Pools include all test positives and up to 100 unrecorded targets
from the same split, with random, length, motif and edit-neighbor distractors;
also report full-target retrieval. Exclude other known observed partners from
distractors without using them as additional test positives. Use exact normalized
two-chain nearest-pair scores, not only the nearest source edge. Fit the shallow
length/terminal-motif logistic baseline using training pairs and constructed
negatives, selecting C from {.1,1,10} on selection validation only.

Fit direction-specific score means/scales on tuning candidates. Choose the
generator/ranker interpolation coefficient from {0,.25,.5,.75,1} by tuning
query-macro Hit@5, with ties favouring the smaller ranker weight. Select a
threshold on calibration candidates by balanced accuracy against *recorded*
positives and constructed unrecorded combinations, including reject-all. If no
positive is generated, return reject-all and report the zero-event limitation.
Save acceptance-coverage versus recorded-hit curves; no biological probability
or independently guaranteed biological precision is claimed.

## Statistics, reporting and release

Report results for each split and training seed, then descriptive means/SD across
the three splits. Repeated splits and seeds are not new independent subjects.
Use 2,000 paired component-cluster bootstrap replicates for shared test queries;
use source groups for direction-specific tasks. Report uncertainty conditional
on fitted models and saved samples. Include counts and a clearly labelled iid
binomial reference for zero-event strata; percentile [0,0] is not a population
upper bound. Report nearest-distance 0/1/2/>=3 strata and exact training-target
overlap. Define the distant subset by both source and recorded target full-sequence
distance >=3 from the supervised and pretraining pools, and report empty subsets.

All v2 outputs live under `artifacts/completion_v2/`. Before training, record
commands, source-file hashes, input/checkpoint hashes, seed and Slurm job IDs.
Refuse completed-output overwrite. Results and paper tables must be generated
from the release evidence, and every ID above must have an inspected artifact
before the project is marked complete. Journal scope is decided from the final
evidence; the manuscript cannot infer information-theoretic impossibility from
failure of these models or call study-level transfer donor-independent validation.
