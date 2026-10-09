# Numerical supplement and review-package guide

Version: completion-v2. These definitions describe the final export schema.
Progress snapshots carry `complete: false` and do not constitute final evidence.
Paths below are relative to the anonymous review ZIP; the private release
manifest retains the original local paths and byte hashes.

| File | Contents and reading rule |
| --- | --- |
| `manuscript.pdf`, `manuscript.tex`, `manuscript.render.json` | Anonymous scientific manuscript, editable source and render record. The record identifies whether native TeX compilation or the ReportLab reading-copy renderer produced it. |
| `figures/` | Six main and two supplementary figures as vector PDF and PNG. Point/range definitions are in each caption. |
| `tables/free_runs.tsv` | Per fitted model, protocol and direction; the default is 64 draws with exact training targets allowed. Probabilities are fractions, not percentages. |
| `tables/primary_descriptives.tsv` | Seeds are averaged within split, then the three split means are summarized by their mean and descriptive SD. This SD is not an independent-subject standard error or confidence interval. |
| `tables/retrieval.tsv` | Hit@5, Recall@5 and MRR for each frozen pool and scorer. The pools contain the recorded positives by construction. |
| `tables/paired_endpoints.tsv` | Compact NLL, coverage and recovery contrasts with 2,000-replicate paired cluster-bootstrap intervals. Every difference is **left minus right**, including ablation-minus-primary contrasts. |
| `tables/budgets_and_policies.tsv` | Nested saved sampling prefixes and allow/exclude-training-target policies. Invalid and duplicate draws do not receive replacements. |
| `tables/sampling_grid.tsv` | All six temperature/top-p cells, both seeds and both directions on split-17 tuning validation. Likelihood Hit@5, coverage, validity, uniqueness and novelty retain the frozen 64-draw setting. Tuning tie resolution does not change the primary test rule. |
| `tables/calibration.tsv` | Validation-selected fusion weights and direction-specific thresholds, calibration class counts, and test acceptance/recovery. Reject-all after zero calibration positives is an explicit outcome. |
| `tables/training.tsv` | New pretraining, generator and ranker budgets, selected checkpoints and actual exposure. Reused historical pretraining is identified separately in the evidence. |
| `tables/pretraining_exposure.tsv` | Sequence and target-token draws for the eight new initializations and four reused main/source square-root runs. Replayed historical counts are explicitly marked `reconstructed`. |
| `tables/denoising.tsv` | Per-chain frozen corruption metrics and aligned-copy controls for all five main pretraining mixtures and both seeds. The saved `damaged` mask includes every selected corruption position, including the unchanged part of the 80/10/10 rule, plus deleted sites. |
| `tables/data_protocols.tsv` | Edge/query/component counts, validation-role sizes, source membership, exact chain overlap and actual nested subset sizes. Source memberships can overlap. |
| `tables/validation_information.tsv` | Query and target counts and the number of actual full-pool unrecorded distractors in each validation role/direction. The unseen-gamma selection role has one query and no distractors. |
| `tables/frequency_ties.tsv` | Counts of all-zero/all-tied training-frequency score vectors per test protocol and direction, checked against the saved baseline scores. Under primary chain exclusion, all scores are zero and the reported frequency retrieval follows deterministic lexicographic tie breaking. |
| `tables/source_event_clusters.tsv` | Post-hoc descriptive distribution of 64-draw likelihood Hit@5 events across the source-test components. These counts explain event concentration and do not introduce an additional significance test. |
| `tables/qualitative_examples.tsv` | Descriptive seed-0 examples from split 17 and both source protocols at 64 draws. Within each direction/category, select the lexicographically first input. Categories are no recovered recorded partner, a partner outside likelihood top five, and a likelihood top-five hit; category sizes and empty categories are retained. This post-hoc illustration does not estimate an additional effect or label unrecorded candidates as biologically wrong. |
| `supplement/metrics.tsv.gz` | Full numerical metric export for run reports and paired comparisons, including secondary endpoints and weighting choices. |
| `supplement/strata.tsv.gz` | Source, length, partner multiplicity, distance, target exposure and distant-edge strata. `EMPTY` denotes a genuinely empty stratum. |
| `supplement/evidence.json.gz` | Complete structured evidence, per-run uncertainty details, zero-event reference intervals, input/output hashes, calibration summaries and audit outcomes. Anonymous paths are derivatives of private originals. |
| `documentation/` | Frozen protocol, deviations/limitations, data and model cards, reproducibility and licensing records, journal assessment and this guide. |
| `source/` | Source/configuration review replica. Workspace, interpreter and account strings are anonymized; port execution paths in a fresh replica as explained in the reproducibility guide. |
| `source/frozen/`, `supplement/task_records/` | Executed source versions and all effective task records. Archived document drafts inside a frozen source snapshot describe that earlier execution state; the top-level manuscript is the final paper. Original byte hashes and anonymous derivative hashes remain distinct. |
| `source/exports/`, `supplement/collection/`, `supplement/presentation/` | The actual source hashes and frozen source files used for final evidence collection and figure/table export, including their run provenance and checksums. |
| `PACKAGE_MANIFEST.json` | Package member SHA256s, original-versus-derivative hashes and completed evidence identity. |

The completed inventory comprises 557 effective manifest tasks, 193
run/baseline statistical reports and 552 paired comparison reports. The release
gate verifies those counts and all required audits before issuing a final ZIP.
Superseded, failed and integration-only runs remain in the private archive and
are excluded from this inventory.

## Interpreting denominators and uncertainty

The two directions have different query counts and are first averaged separately.
`equal_direction_macro` is their equal-weight mean; it does not pool all direction
queries into one denominator. A model seed index of 0 or 1 maps to training seed
3407 or 3508. Different evaluation sampling RNGs are recorded in the run metadata.

`query_macro` gives each input equal weight. `edge_weighted_query_metrics` weights
queries by their number of eligible recorded partners; this turns Recall into
edge-micro recovery but does not turn Hit into an independent-edge Bernoulli
outcome. Token-weighted NLL is a separate quantity. NLL is in nats per target
token, including EOS. Differences in probabilities can be multiplied by 100 to
obtain percentage points; they are not relative percentage changes.

Within-model scorer contrasts reorder identical candidates. Different-model free
generation contrasts share test queries and cluster resamples but retain their
own saved draws. They do not require identical candidate sets. The fixed-pool
contrasts require the same pool hashes. Intervals condition on fitted models and
saved candidates and have no family-wise multiplicity correction. A [0,0]
percentile interval after zero events is not a population upper bound; the JSON
retains a separately labelled iid Wilson reference where applicable.

Generated candidates are not validated receptor partners. Unrecorded combinations
are constructed comparisons, not experimentally established negatives. A score
threshold is not a biological probability guarantee. The distant-edge subset has
only 5, 5 and 3 main-test edges and is empty for both source tests. Its estimates
must retain those denominators.
