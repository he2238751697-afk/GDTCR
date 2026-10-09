# BMC scientific revision status

**Historical scientific status recorded on 6 October 2026.** The public
GitHub release was established on 9 October. The current author-review
manuscript uses native TeX compilation and the supplied author names.
See `final_submission/README.md` for current delivery and audit records and
`BMC_AUTHOR_ITEMS.md` for the remaining declarations, licenses and Zenodo DOI.
The dated account below is retained for traceability.

Updated: 6 October 2026. The local scientific revision and supplemental
experiments are complete. **This is not yet a submission-ready public release.**
Author declarations, repository/DOI and licensing remain pending as explicitly
confirmed by the user. No journal submission or external publication was made.

## Required scientific additions

| Checklist item | Status | Evidence and boundary |
| --- | --- | --- |
| P0-1 nearest-input partner transfer | Complete | 11 deterministic baseline tasks, fixed k=1 and k=5; separate similarity scoring on original truth-containing pools. No test-selected neighborhood. Direct transfer's structural zeros are explained. |
| P0-2 unseen-gamma validation | Complete | Original train/aggregate validation/test memberships retained; validation roles now 31/16/16 gamma queries. Selection has 275 edges, largest query 137 partners and at least 118 distractors per query. Two-seed conditional/prior/random/ranker refits and shuffled evaluation completed. |
| P0-3 within-giant sensitivity | Complete | 6254 train, 500 validation and 500 held test edges; both endpoints of each test edge remain supervised-exposed. One original component: counts and point estimates only. |
| P0-4 distant-sequence recheck | Complete | Original minimum-distance witnesses independently recover 5/5/3 distant primary edges. No stable distant-transfer claim is made. |
| P0-5 reproducibility package | Local component complete; public component pending | Six bounded attachment ZIPs, editable-source ZIP, frozen code/configurations, seeds, pools/splits, hashes and environments. Public repository/DOI/license remain open. |

All 43 new tasks completed: 16 fits (12 generators and 4 rankers), 16 free
evaluations and 11 nearest-input baseline tasks. All 43 Slurm records are
`COMPLETED` with exit code `0:0`. The audit verifies output hashes, test
membership, saved token decoding, prefix and summary metrics, logged model
selection and nondegenerate ranker validation. It does not rerun every GPU
forward pass. New fits used RTX 3090 GPUs; original fits used A800 GPUs.

The frozen primary evidence retains SHA256
`5badb3b9b8ead02c57afeb5f578f85f3a5e343bad9714fb7daa08f48342b2f3b`.
Neither its original negative results nor the three primary splits were replaced.

## Main scientific outcomes

The original equal-direction NLL remains 1.005 for conditional pretraining,
1.013 for the matched constant-source prior and 1.115 for random initialization.
Primary free-generation likelihood Hit@5 remains 0.03%, and ranker Hit@5 0.06%,
without a reproducible primary reranking advantage.

Repaired unseen-gamma conditional likelihood recovers 8/64 and 10/64 queries;
the prior recovers 8/64 and 9/64, random initialization 10/64 and 8/64, shuffled
input 6/64 and 7/64, and ranker ordering 6/64 and 8/64. Selected ranker MRR is
0.1405/0.1618 instead of the original degenerate 1. These diagnostic outcomes
do not establish a stable conditional recovery benefit over the matched prior.

Within the giant component, conditional likelihood gives 60/177 and 50/177
gamma-query hits and 123/261 and 118/261 delta-query hits. Prior and shuffled
controls remain strong; ranker ordering is lower in every fit. The population
has exposed endpoints and one original component, so high recovery is not
evidence of distant or unseen-component transfer. All control counts and
paired point differences are retained in the numerical supplement.

Nearest-input partner-similarity retrieval reaches mean Hit@5 of 9.2%/7.9%
in random pools and 1.5%/1.5% in full pools. Direct transfer has a distinct
candidate mechanism and structurally zero primary recovery. It is not evidence
that the neural method learned a biological pairing mechanism.

## Manuscript and review deliverables

- `manuscript_bmc.tex`: editable BMC manuscript with structured abstract,
  complete methods, bounded recorded-partner claims, 7 main figures and 3 tables.
- `supplementary_methods_bmc.tex`: complete extended methods and sensitivity
  results, including the preserved original unseen-gamma diagnostic.
- `BMC_REVISION_LOG.md`: every revised section's previous problem, changes,
  exact replacement text, scientific-claim effect, numerical sources and open items.
- `BMC_CLAIM_AUDIT.tsv`: sentence inventory with section-specific answers to
  all ten claim-audit questions. Interpretation review is separate from the
  deterministic numerical checks; it does not replace author responsibility.
- `results/bmc/numerical_audit.json`: unchanged primary-table rows, key numerical
  excerpts, reference/figure cross-references, file hashes and component-stratum
  recomposition checks.
- `BMC_REFERENCE_AUDIT.md`: 16 verified references and a targeted literature
  update through 2026-10-06, with metadata and query results cached.
- `BMC_SUPPLEMENT_INDEX.md`, `BMC_REPRODUCIBILITY.md`: attachment inventory,
  runtime separation, snapshot restoration and execution instructions.

The 31-page main and 8-page supplementary reading PDFs have double-spaced body text, page/line
numbers and inspected figures/tables. Figure outputs include vector PDF/SVG and
300-dpi PNG; fonts are embedded. Editable TeX contains no forced page breaks.
The built-in compiler failed with `Unable to find standard directories for
platform`. The source remains in the editor; the reading copies use ReportLab.
**Native TeX compilation is unverified.**

The existing 58 scientific regression tests passed. Publication checks are
recorded separately: 418 source/numerical checks passed; every one of 6980
compact nearest-input query records agrees with its full original; 25 exact
source snapshots (2456 files) restore successfully. Archive member hashes and
the <20 MB limit are verified. The combined `gdtcr_bmc_local_review.zip` is a
convenience bundle, not an individual journal Additional file.

## Strongly suggested and optional work

| Item | Status |
| --- | --- |
| Per-direction events/intervals | Complete; seed/split identities preserved. |
| Component-size sensitivity | New within-giant diagnostic plus post-hoc 1 / 2–5 / 6–20 / >20 edge strata; no pooled inferential claim. |
| Near-neighbor strata | Re-exported original source-distance results and distant-edge witnesses. |
| Source-balanced description | Complete as post-hoc equal weighting of nonempty, potentially overlapping source memberships; no new primary endpoint. |
| Matched-total-compute random-initialization comparison | Not performed. It is a P1 recommendation; current comparison matches downstream settings, not total training computation. No total-compute efficiency claim is made. |
| Larger/alternative architecture or further decoder search | Not added. Original frozen sampler grid retained. No architecture-wide optimality claim. |
| Donor-aware/new external cohort | Not performed; sufficient donor/library metadata and a newly frozen independent cohort are absent. |
| Structural/functional validation | Not performed. No binding, specificity or receptor-function claim. |

## Submission blockers retained

Authors/affiliations/correspondence/contributions, funding, competing interests,
ethics secondary-use determination, publication consent and acknowledgements
are all pending. The repository, persistent archive/DOI and code/data licensing
must be finalized before public release. One IEDB record lacks original-study
provenance and remains transparently identified. The final manuscript therefore
intentionally retains administrative placeholders. These items are not marked
complete in the original submission checklist.

Two methods wording corrections are explicit in the revision log: the ranker's
copied encoder is trainable (`freeze_encoder=false`), and the 750-step budget
applies only to the unidirectional sensitivity controls, whereas directional
exposure diagnostics retain a 1500-step maximum. Neither correction changes
the frozen numerical evidence.
