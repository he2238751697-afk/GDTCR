# BMC author-review attachment guide

These six archives accompany `manuscript_bmc.tex` and its native LaTeX PDF.
They are the author-review attachments prepared on 9 October 2026.
The underlying scientific code, original input exports and reference results
are public at https://github.com/he2238751697-afk/GDTCR/releases/tag/reproducibility-v1 .
The updated attachments have no Zenodo DOI or newly assigned license.
`output/bmc_revision/release_manifest.json` records archive sizes and SHA256
hashes; every archive contains a member manifest.

| Attachment | Main contents | Reading rule |
| --- | --- | --- |
| Additional file 1 | Supplementary methods in PDF/TeX; Figures S1/S2 in editable plot outputs | Corruption, controls, negative construction, candidate construction, bootstrap, mixture/negative sensitivity and original unseen-gamma pathology. The new main text supersedes that historical diagnostic. |
| Additional file 2 | Source composition, distant-edge witnesses, graph/split/validation audits, source-distance and component-size strata | Source memberships may overlap. Source-balanced and component-size tables are post-hoc descriptions; they do not replace the primary endpoint. Distant edges remain 5/5/3. |
| Additional file 3 | Original/new seeds, selected-checkpoint hashes, run settings and actual exposure | Includes checkpoint identifiers and metadata, not the large weight files. Ranker pair draws are not unique-chain or encoded-token counts. Missing encoded-token counts are explicitly unlogged. |
| Additional file 4 | Original/new metric tables; primary and revision query outcomes; events, paired contrasts and nearest-input baseline witnesses | Fractions in raw tables become percentages in the manuscript. Preserve fit/split identities. Direct transfer and truth-containing partner-similarity retrieval are different endpoints. |
| Additional file 5 | All frozen original/revision split assignments and original fixed candidate pools; free-candidate SHA256s | Fixed pools contain recorded positives. Large raw free-draw arrays remain in the local artifact tree and are identified by hashes; they are not all embedded in the small attachment. |
| Additional file 6 | Current source/configuration, frozen executed source objects, environment, task records, reference audit and revision documentation | Restore exact snapshots with `materialize_snapshots.py`; port workspace, interpreter and scheduler paths in a separately named execution manifest. No changes to scientific inputs are implied by porting. |

The separate `gdtcr_bmc_editable_source.zip` includes the main and supplementary
TeX sources and all figure files. Compile from its `paper/` directory so relative
figure paths resolve, or use `scripts/build_submission_pdfs.py` from a repository
clone. The current PDFs were compiled with native TeX Live 2026, with logs,
source/figure hashes and stabilized cross-references recorded in
`paper/final_submission/native_compile.json`. The earlier ReportLab reading
copies and failed standalone-compiler records remain in the historical
`reproducibility-v1` release; they do not describe the current compilation.

## New numerical tables

All paths below are under `paper/results/bmc/tables/` in the working tree.
Additional file 4 stores them under `revision_tables/`; selected data tables
also appear under `tables/` in Additional file 2.

| Table | Interpretation |
| --- | --- |
| `primary_events.tsv` | Per-fit coverage and likelihood/ranker/fused Hit@5 events and denominators; 168 rows. Repeated splits are not independent samples. |
| `primary_query_results.tsv` | 34296 directional query records across the primary fits and controls; positives and original component IDs retained. |
| `primary_source_distance_strata.tsv` | Frozen primary source/proximity/distant strata re-exported without changing candidate sets. |
| `source_balanced_descriptive.tsv` | Equal average of nonempty source membership strata. Memberships overlap and small sources are unstable. No source-independent inferential interval. |
| `test_component_distribution.tsv` | Complete primary-test component edge and directional query counts. |
| `primary_component_size_strata.tsv` | Post-hoc bins of 1, 2–5, 6–20 and >20 edges, nonempty bins only; query means and event counts, no inferential intervals. |
| `revision_metrics.tsv` | All conditions, directions and model seeds from repaired unseen-gamma and within-giant diagnostics. |
| `revision_query_results.tsv` | Per-query new outcomes with test positives; all within-giant rows identify the same original component. |
| `revision_paired_contrasts.tsv` | Conditional-minus-prior/random/shuffled and ranker-minus-likelihood. Fractions, or nats/token for NLL. Within-giant contrasts are point estimates only. |
| `revision_training.tsv` | 12 generators and 4 rankers, selected steps, selection values, devices, checkpoint hashes and actual exposure. |
| `nearest_input_transfer.tsv` | Direct k=1/k=5 transfer and separate nearest-input partner-similarity retrieval; deterministic baseline fit identities retained. |
| `dataset_composition.tsv`, `distant_edges.tsv`, `distant_summary.tsv` | Source union, accessions and exact saved minimum-distance witnesses. |

Original `free_runs.tsv`, `paired_endpoints.tsv`, `retrieval.tsv`,
`budgets_and_policies.tsv`, `sampling_grid.tsv`, `calibration.tsv`,
`qualitative_examples.tsv` and other original exports remain unchanged under
`original_tables/` in Additional file 4. The original `SUPPLEMENT_INDEX.md`
describes those completion-v2 schemas and its historical package layout; it is
not the BMC archive's top-level inventory.

The compact `nearest_input_queries/` JSON files retain every baseline query,
its positives, cluster, nearest training inputs/distances, all direct-transfer
proposals and all scalar retrieval metrics. Repeated full-pool candidate,
ranking and score arrays are represented by canonical-JSON hashes, with raw
output hashes also retained. The frozen pools in Additional file 5 and the
deterministic evaluator reconstruct those scores. Full original rows remain
unchanged in the local artifact tree. This avoids duplicating the same large
candidate universes in an attachment constrained to less than 20 MB.

## Boundaries

Primary inference resamples complete test components; directional diagnostics
resample source queries. Two seeds and three overlapping graph splits are not
independent biological replicates. New within-giant results have one original
component and no inferential component interval. New scientific tasks passed
saved-output/hash/metric/checkpoint audits; this audit did not rerun every GPU
forward pass. Public code/data access is established; the permanent archive DOI,
code/weight licenses, unresolved third-party terms and final author declarations
remain on the author-owned checklist.
