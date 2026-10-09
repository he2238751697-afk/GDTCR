# Completion-v2 delivery audit

Audit status: complete.

Completed evidence SHA256:
`5badb3b9b8ead02c57afeb5f578f85f3a5e343bad9714fb7daa08f48342b2f3b`.

This audit compares the repository with `RESEARCH_PLAN.md`, `PROGRESS.md`, the
frozen `protocol_v2.md` and its implementation notes. Historical v1 was not a
complete execution of the original proposal. The v2 work fills the required
comparison matrix without relabeling optional or unperformed extensions as
completed experiments. Scientific evidence and manuscript acceptance are recorded
below. The separate strict release certificate records archive integrity and
successful Slurm accounting; an implemented script, queued job or partial
evidence snapshot is insufficient.

## D1-W1 artifact map

Paths with directories are repository-relative. Unqualified audit filenames
refer to `artifacts/completion_v2/`, and TSV names refer to the final publication
`tables/` directory. Numerical publication exports are frozen under
`paper/results/v2/`; the authoritative complete evidence is
`artifacts/completion_v2/final_evidence/evidence.json`.

| ID | Executed scope and evidence | Interpretation boundary |
| --- | --- | --- |
| D1 | `data_audit_final.json`, `pool_audit.json`, input/provenance manifests and nine frozen data protocols. Raw/processed/split hashes, source membership, lengths, degrees, whole-component allocations and exact-chain exclusions are checked. | Two source memberships overlap. Missing donor identities are not inferred; the allocator balanced edges rather than source/length. |
| D2 | All three component splits, each with two conditional and two matched-prior fits, plus random initialization and shuffled-input controls. Generator/ranker records and `free_runs.tsv`, `primary_descriptives.tsv`, `paired_endpoints.tsv` retain every fit. | Two seeds and three overlapping splits are descriptive repetitions, not six independent biological subjects. |
| D3 | Both unseen-input directions and both seen-input/unseen-edge directions, with two conditional/prior seeds per protocol; corresponding training, evaluation and source-query-group analyses. | Unseen-gamma checkpoint selection has one query and no ranking distractors. Target overlap is allowed and quantified; these tasks do not replace the primary both-chain-unseen test. |
| D4 | Twenty-eight exact-distance tables, the corrected independent audit, all recorded minimum witnesses, sampled independent recomputation and query-level distance/overlap strata. | Strict distant test subsets have only 5/5/3 primary edges and no source-test edges. This does not establish distant transfer. |
| P1 | Frozen corruption audits for five pretraining mixtures and two seeds, with aligned-copy controls; `denoising.tsv`. | Selected sites include the unchanged fraction of the 80/10/10 corruption rule. Reconstruction accuracy is not partner-generation accuracy. |
| P2 | Eight new raw/balanced/gamma-only/delta-only pretraining fits and two reused main square-root initializations, with downstream split-17 comparisons. `pretraining_exposure.tsv`, Figure S1 and paired tables retain actual sequence/token exposure. | Equal sequence draws do not match chain-specific or token exposure. Historical replayed counts retain their reconstructed label. |
| G1 | Matched constant-source and random-initialized controls under the frozen target-sampling and downstream selection budget. | Extra pretraining computation is not matched, and the random model was not independently optimized over a hyperparameter search. |
| G2 | Query-uniform versus edge-uniform training and nominal direction-budget-matched unidirectional versus shared bidirectional models, with two seeds. | Actual early stopping and token exposure differ and are reported; no universal benefit of sharing is inferred. |
| G3 | Nested complete-component subsets with 725/1,814/2,249/7,254 actual edges and pretrained/random fits. Figure 4 and run/paired tables report both seeds. | The nominal 50% set is 31.0%; all smaller sets contain only singleton components. The curve changes graph composition as well as sample count. |
| R1 | Forty-two new rankers with audited selection and two training stages. Split-17 random/mixed negatives at ratios 1/3/5 share saved generator candidates; Figure S2 and training/paired tables retain counts and fallbacks. | Negative labels denote unrecorded combinations. Independence means separate subsequent parameters/optimization, not independent cohorts. |
| E1 | Identical frozen pools for likelihood, ranker, fusion, target prior, shuffled input, likelihood difference, exact two-chain neighbors, shallow features, frequency and seeded random scores. All 27 non-neural/baseline reports are audited. | Truth-containing retrieval is distinct from free generation. Primary and strict-source frequency scores are all zero and use lexicographic tie ordering. |
| E2 | Saved 16/64/256 prefixes for the prescribed split-17 models, allow/exclude-training-target policies, strict EOS/length checks, novelty/diversity and the six-cell tuning-only sampling grid. | Invalid/duplicate draws receive no replacement. The grid does not replace the frozen primary setting; excluding targets may remove legitimate positives in shared-target tasks. |
| E3 | Separate checkpoint-selection, score-tuning and threshold-calibration roles, frozen fusion/threshold files and test acceptance curves. | Primary gamma-to-delta free calibration has zero recorded positives; delta-to-gamma has few. Reject-all is an outcome, not a missing analysis, and no biological precision guarantee is claimed. |
| S1 | Strict and shared-source protocols, both model seeds, conditional/prior/shuffled controls and source/exposure strata. Figure 5 and `source_event_clusters.tsv` show the distinct tasks and post-hoc event concentration. | Training sizes/compositions change together with overlap. Source tests are not donor-independent; most hits occur in one component. |
| S2 | Query-macro, edge-weighted and token-weighted summaries; multi-positive Hit/Recall/MRR; 2,000-replicate paired component/source-query bootstrap, zero-event references and empty strata. | Intervals condition on fitted models and saved candidates, have no family-wise multiplicity correction, and zero-event [0,0] is not a population bound. |
| C1 | Immutable effective task records, executed source snapshots, pinned environments, input/model/output hashes, exposure recovery and indexed historical/publication archives. The release script checks unique successful Slurm identities and anonymous derivative hashes. | Original failed/superseded attempts remain private audit records. The documented historical pretraining job-header inconsistency is not fabricated away; anonymous replicas preserve original-versus-derived hash distinctions. |
| W1 | Final anonymous English manuscript, fourteen checked references, six main/two supplementary figures, three evidence-generated main tables, fifteen numerical TSV tables, data/model cards and the final journal assessment. All 23 reading-copy PDF pages were visually inspected. | Native TeX compilation remains unverified because of a platform-directory error; author declarations and public release decisions remain administrative author responsibilities. |

## Plan compliance and necessary design improvements

Completion is assessed against the explicitly frozen v2 requirements, not an
unqualified claim that every suggestion in the original plan was executed.
Preserved deviations include edge-only split allocation, the reused historical
pretraining, source/ranker manifest corrections made before the affected fits,
and the padding-only evaluation-audit repair. These are recorded in
`protocol_v2_implementation_notes.md`; test memberships and scientific evaluation
commands were not retrospectively tuned to improve results.

The original suggested 6--8 learning-rate/dropout settings per component,
encoder/head-specific learning rates, alternative direct-denoiser ranker
initialization, top-k neighbor variants and extra architectures were not an
executed complete search. Donor-independent prospective testing, biological
function and a new sequence-distant cohort were not obtained. They are explicitly
outside the completed v2 evidence and remain future work.

The next design should check validation query and distractor counts before
freezing, control graph composition in data-efficiency curves, independently
tune scratch models and compare total computation, and plan sample size around
independent clusters and a prespecified useful recovery improvement. New cohorts
need traceable donor/library metadata and enough distant pairs. A frequency
lookup with unseen targets and a calibration role with no positives must be
identified as uninformative before interpreting its output.

Execution completeness is separate from confirmation of the hypotheses:

| Research question | Bounded conclusion |
| --- | --- |
| Does denoising help? | NLL improves under the matched downstream budget, but lower NLL does not yield a consistent small-data free-recovery advantage. Total computation and independently optimized scratch training were not matched. |
| Does the input add information beyond a target prior? | Primary conditional-minus-prior NLL intervals are below zero, but primary free Hit@5 is sparse. Some source/seen-input fitted contrasts are larger; their clustered intervals and target exposure must accompany the estimates. |
| Does ranking/rejection help? | All six primary ranker-minus-likelihood Hit@5 intervals include zero, and primary free fusion selects zero ranker weight. Fixed-pool sensitivity and severely limited calibration positives do not establish reliable biological candidate selection. |

## Repository cleanup

Cleanup was warranted because legacy/invalid runs, current evidence and working
publication previews previously coexisted without a clear completion boundary.
The repository now has explicit historical versus v2 entry points, immutable
supersession registries and preservation indexes. `REPOSITORY_RETENTION.md`
records the retained approximately 14 GB historical archive and the 22-file
publication-preview archive with per-file hashes. These moves improve traceability
and do not claim disk-space recovery.

Valid checkpoints, samples, splits and unsuccessful audit evidence are retained.
No Git reset, remote publication, license assignment or task-output deletion
forms part of this cleanup. The current working tree remains uncommitted and
reviewable, including the user's pre-existing modifications.

## Final acceptance record

| Check | Accepted evidence |
| --- | --- |
| Strict scientific collection | `artifacts/completion_v2/final_evidence/evidence.json` has `complete: true`; all 557 effective tasks and their recorded output hashes, including model weights, were verified. The evidence SHA256 is stated above. |
| Statistical coverage | 193 run/baseline reports, 552 paired comparisons, 298,562 full metric rows and 236,898 stratum rows; both directions and all prespecified seeds are retained. |
| Model audits | All 88 evaluation-content audits pass. The training audit passes for 118 new models: 68 generators, 42 rankers and eight pretraining fits. Reused initialization diagnostics and historical exposure recovery are identified separately. |
| Regression and integration | All 54 scientific regression checks pass in `artifacts/completion_v2/regression_final.log`. Completed GPU/CPU integration checks and the renderer's escaped-character regression remain separate from experimental results. |
| Frozen numerical export | `artifacts/completion_v2/final_export_code_v2.json` identifies the actual collection/presentation source snapshot. Its 8 figures, 3 verbatim manuscript tables and 15 numerical TSV tables are preserved under `paper/results/v2/`. |
| Manuscript | `paper/manuscript_v2.tex`, SHA256 `fcbcb5077aaa210de898a86a70599bf1e21cb232499f9720814619af90dcb5e7`; anonymous English manuscript with 14 matched citations/references. |
| PDF and visual acceptance | `output/pdf/gdtcr_anonymous.pdf`, SHA256 `351c949ed4261abd532ad262e1edd56a0c4c10065d6905efd966ed12b6d9042a`. The passed audit at `artifacts/completion_v2/publication_reviews/final_visual_audit.json` identifies all 23 inspected pages and their PNG hashes. |
| Renderer limitation and repair | The ReportLab reading-copy renderer is SHA256 `6f2ab21671b68a47d4ebcc6dfe189f947701a1846f4481c37ebee753e44ba605`. A rejected PDF with internal percent tokens is retained with its failed review; the correction changes neither TeX source nor numerical evidence. Native compilation returned `Unable to find standard directories for platform` and is not reported as successful. |
| Journal scope | `paper/JOURNAL_ASSESSMENT.md` is final for this evidence: BMC Bioinformatics research article first, Bioinformatics Advances after shortening as an alternative. |
| Archive certificate | `artifacts/completion_v2/release_v2/release_manifest.json` certifies `output/gdtcr_anonymous_review.zip`, its SHA256, 557 unique successful Slurm task identities, anonymous derivatives and ZIP/member integrity. The certificate is issued only after those release checks pass. |

The release certificate, rather than this document or an earlier progress
snapshot, is the authoritative archive-verification record. The scientific
protocol is complete; actual journal submission and unresolved author-owned
administrative decisions are outside this local anonymous delivery.
