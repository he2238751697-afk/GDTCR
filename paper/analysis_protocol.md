# Supplementary analysis protocol and correction log

Recorded on 2026-09-30 after the first internal test evaluations. These are
audits and supplementary analyses, not a retrospective preregistration.

## Frozen internal evaluations

Preserve the existing checkpoints, split files, all 64 saved samples per
query, and fixed-pool candidate lists. Do not draw replacement samples.

The audit found that the asymmetric ranker was evaluated with delta vectors
in the gamma argument in the reverse direction. Its training and forward
validation used the correct gamma/delta order. Recompute both evaluation
directions with canonical chain order and archive the corrected JSON under
`artifacts/evaluations/audited/`. The original results remain for provenance
and are superseded for ranker comparisons. Recompute average precision with
all equal scores entering at one threshold. Include the all-rejected rule in
validation threshold selection. Report AP (non-interpolated), not an
unspecified trapezoidal PR area.

The legacy `raw_hit_at_k` metrics use first occurrence in sample order.
Additionally score the identical generated candidates by mean target-token
NLL including EOS and report this likelihood ranking separately. Neither
resorting can change candidate coverage. Compare generator and ranker on
exactly the same candidates; audit the invariant Hit@K <= coverage.

Threshold diagnostics are exploratory and reuse the validation set used for
checkpoint selection. They do not provide an independently calibrated risk
guarantee. Unrecorded combinations are constructed controls with unknown
biological status. Scores and positive fractions apply only to the defined
candidate universe.

## Source-held-out supplementary experiment

Recover observation-level records from the frozen raw files, with file hashes,
chain-specific sequence IDs, pair IDs, original row or within-library cell
IDs, V/J annotations where available, and study-level provenance. Missing
donor IDs remain missing. Assert that the legacy unique pair set can be
reconstructed before constructing new splits.

The intended held-out study is the paired UcTCRdb `Suo_2022` table. Verify its
original reference and relationship to the main GSE180059 study. Exclude the
untraceable IEDB singleton from this supplementary training/evaluation.
Use GSE180059 alone for supervised training and validation, and remove
Suo-overlapping gamma OR delta chains from these sets for the strict
version. Partition the remaining GSE pairs by components with seed 1729 and
90/10 train/validation proportions. Freeze the entire Suo pair table as test;
report overlap losses and remaining sizes before performance evaluation.

Audit every raw single-chain source for overlap with the held-out study,
including the study's BioProject if present in TCRdb2.0. Pretraining for this
experiment must exclude the held-out study's sequence pool as well as all
paired sequences. Reuse existing pretraining checkpoints only if provenance
demonstrates that this exclusion was already satisfied; otherwise train new
checkpoints on the filtered pool. Metadata absence cannot be evidence of
independence.

Reuse internal model sizes and the frozen learning rates/early stopping
budget. Use two seeds (3407 and 3508), 64 samples, temperature 1, top-p 0.95,
and no test-selected hyperparameters. Include a target-only baseline and
same-pool simple controls. If the original source or pretraining exclusions
cannot be verified, label the result a source-table transfer diagnostic,
not external validation or a donor-independent test.

The source audit was completed before submitting the new training jobs.
Suo's original accessions are E-MTAB-11388 / ERP135310 / PRJEB50691; this
BioProject is absent from the 17 archived TCRdb2.0 projects. The original
paper describes HDBR samples from the UK, whereas GSE180059 describes fetal
samples from Singapore and pediatric samples from Belgium. The export
still lacks individual cell/library links, so retain that limitation.

The frozen strict split contains 4,956 training, 551 validation and 626 test
pairs. Removing every known Suo gamma or delta sequence eliminates 2,936
GSE180059 edges. An audit found 275 training and 6 validation single-chain
Suo delta sequences in the legacy pretraining pool. Therefore the source
experiment starts pretraining from random weights. Also remove all
pretraining sequences present in the IEDB export, whose species and original
reference identifiers are missing. Final pretraining training counts are
186,949 gamma and 1,230,167 delta sequences.

The source-only ablation shares the same denoising initialization and
paired-target sampling as the conditional model, then replaces source
residues with the chain token during training and evaluation. This is a
matched source-ablation control; the older internally evaluated target-only
models used separate autoregressive pretraining and are reported separately.
The source experiment includes a shuffled-input control with frozen
checkpoints and the same 64-sample budget.

Suo records were present in the earlier merged-corpus experiments. This new
source split is a supplementary transfer experiment with separately trained
models, not an untouched prospective validation cohort or a claim that the
overall development process never encountered this study.

Before viewing source-experiment performance, add a complementary transfer
protocol that allows public chains across studies, while removing the two
duplicate cross-study PAIR edges from the GSE training/validation pool.
Use the same seed-1729 component split within GSE and the same 626 Suo test
pairs. Reuse the clean, newly trained source-excluded pretraining checkpoints;
the paired-training initialization, optimizer, budgets and constant-source
control stay the same. This answers a different question from strict
unseen-chain transfer. Report exact source and target overlap explicitly,
and do not treat higher performance under shared chains as evidence of
generalization to unseen chains. The baseline probability of finding a
recorded target among training targets is reported for both protocols.

Supplement fixed-pool scoring with conditional likelihood, a deterministic
shuffled-source control, the target-only model, and their token-normalized
log-likelihood difference (coefficient fixed at 1). For comparability, use
the same saved candidates for all methods and two matched training seeds.
The likelihood difference is a diagnostic score, not a calibrated mutual
information or natural-pairing probability. A uniform random ranking has an
analytic multi-positive Hit@K baseline. The legacy frequency baseline is
degenerate on strictly unseen targets and is labelled accordingly.

## Statistical reporting

Report each training seed rather than treating seeds as new subjects. For
comparisons on shared queries use paired differences; do not infer absence
of a difference from overlap of separate confidence intervals. Supplement
query bootstrap with component-cluster resampling, because some queries
share targets. A zero-hit percentile bootstrap is degenerate and is not a
population upper bound. Report the denominator and event count for sparse
strata and any assumption behind a nonzero upper interval.

All analyses added after viewing internal results remain labelled as
supplementary/exploratory. Failures of these implementations are empirical
limits under the evaluated protocols, not proofs of information-theoretic
non-identifiability of CDR3 pairing.
