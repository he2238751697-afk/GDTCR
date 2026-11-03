# Supplementary materials for the supervisor-review manuscript

The six numbered archives accompany the current scientific draft.
Figures 1–6 and Tables 1–3 are in the main manuscript. Figures S1–S3 and
Table S1 are in Additional file 1. Original Figure 7 is now Figure S3;
its scientific asset remains unchanged.

| File | Contents and relationship to the manuscript |
| --- | --- |
| Additional file 1 | Supplementary methods and sensitivity analyses (PDF and LaTeX), Table S1, Figures S1–S3 in PDF/SVG/PNG. Sections S1–S6 specify data, training, controls, candidates and metrics; S7 contains sensitivities; S8 gives exposure diagnostics and historical estimates; S9 contains sampling/calibration results. |
| Additional file 2 | Dataset/source/graph/distance audits, provenance manifests, primary source/component strata and descriptive source-balanced summaries. |
| Additional file 3 | Pretraining and downstream run tables, seeds, selected checkpoints, model settings, actual sequence/token exposures and per-run provenance. |
| Additional file 4 | Primary and diagnostic query outcomes, events, paired contrasts, sensitivity/calibration/sampling-grid tables and qualitative examples. Includes compact nearest-input query records; repeated candidate vectors are identified by hashes against the frozen pools. |
| Additional file 5 | Split assignments, validation roles, fixed candidate pools, pool audit and free-candidate hashes. The hash inventory is not the full set of sampled sequences; reconstruction and execution are documented in Additional file 6 and the public release. |
| Additional file 6 | Current source/configuration/environment and reproduction instructions; 25 historical execution-source snapshots in a deduplicated object store, plus the immutable public-release source archive. Current manuscript build and audit records are included. Historical documentation is retained for traceability and is explicitly separate from this review version. |

All data tables and frozen computational objects are preserved. The current
supplement index replaces obsolete manuscript figure-number references;
previous index files remain under historical/ in Additional file 4.
The independent figure archive provides all nine figures as vector PDF,
editable SVG and 300 dpi PNG, with an explicit original-Figure-7/S3 mapping.
The editable-source archive preserves relative figure paths for compilation.

The public scientific base and upstream data-access instructions remain at
https://github.com/he2238751697-afk/GDTCR/tree/reproducibility-v1 .
The input exports are sequence/contig/database files, not sequencing FASTQ.
