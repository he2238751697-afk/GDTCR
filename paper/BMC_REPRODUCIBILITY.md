# Reproducing the BMC revision

This revision preserves the original completed benchmark and adds explicitly
post-primary diagnostics. The authoritative original evidence remains
`artifacts/completion_v2/final_evidence/evidence.json`, SHA256
`5badb3b9b8ead02c57afeb5f578f85f3a5e343bad9714fb7daa08f48342b2f3b`.
Original manuscripts, figures and release certificates describe that original
version and are not silently replaced by this revision.

## Revision experiments

The prospective-to-new-fits scientific settings are in `revision_bmc_protocol.md`.
`data/splits/revision_bmc/manifest.json` identifies the unchanged unseen-gamma
train/test memberships and repaired query-group validation, and the new giant
component edge holdout. These are revision diagnostics, not preregistered primary
endpoints. Test outcomes were not used to select repair allocations or budgets.

`configs/revision_bmc/revision_training.json`, `revision_evaluation.json` and
`revision_transfer.json` contain 16 training tasks, 16 free evaluations and 11
nearest-input baseline tasks. Every task references an immutable executed source
snapshot; the generic `execute_manifest.py` runner verifies it and records all
output hashes. GPU fits were moved from pending A800 requests to available RTX
3090 resources without changing scientific commands. Scheduler updates and all
completed task records are retained under `artifacts/revision_bmc/`.

The original and new models therefore have different training hardware, and no
hardware comparison or strict bitwise cross-device equivalence is claimed.
Within the new diagnostics, conditional/prior/random/ranker models use the same
recorded device class and optimizer/sampling settings. The original pretraining
checkpoints are reused unchanged. Keep original results and diagnostic results
separate in all summaries.

Reconstruction in a fresh replica follows `REPRODUCIBILITY.md` for upstream
source acquisition and original frozen experiments. Do not run preparation over
existing immutable data/run trees. Port absolute workspace/interpreter/scheduler
paths in a separately named execution manifest, keeping scientific inputs and
source snapshots unchanged. Once all revision tasks have completed:

```bash
OMP_NUM_THREADS=2 PYTHONPATH=src:. artifacts/completion_v2/runtime/bin/python scripts/analyze_revision_bmc.py
artifacts/completion_v2/runtime/bin/python scripts/export_revision_tables_bmc.py
artifacts/completion_v2/runtime/bin/python scripts/export_primary_supplement_bmc.py
artifacts/completion_v2/publishing_runtime/bin/python scripts/plot_revision_bmc.py
artifacts/completion_v2/publishing_runtime/bin/python scripts/render_bmc_pdf.py --source paper/manuscript_bmc.tex --output output/pdf/gdtcr_bmc_revision.pdf
```

The analysis checks task hashes, test membership, candidate token decoding,
prefix metrics and checkpoint selection logs. It does not rerun all GPU forward
passes. New within-giant results have one original component and deliberately
have no inferential component-bootstrap interval. The nearest-input transfer
candidate budget is at most 64 unique copied training targets, not 64 stochastic
draws. Its fixed-pool partner-similarity extension is a different endpoint.

The runtime used for scientific analysis includes RapidFuzz. The separate local
publishing runtime supplies ReportLab, pypdf and plotting tools; it does not
include RapidFuzz and cannot run the scientific audit unchanged. A portable
environment must combine these dependencies or preserve the two-runtime split.
Post-hoc source-balanced and component-size tables are descriptive and do not
replace the frozen primary endpoint. Ranker exposure includes exact sampled
positive/negative pair draws reconstructed from executed steps and audited
negative counts; encoded-token counts were not recorded and are not imputed.

## Publication files

`manuscript_bmc.tex` is the editable main source; `supplementary_methods_bmc.tex`
is Additional file 1. Figures are exported as vector PDF/SVG and 300-dpi PNG from
`plot_revision_bmc.py`. Numerical supplements retain raw fractions, explicit
event counts and original fit identities. Main text uses percentages.

`render_bmc_pdf.py` produces a reading copy with numbered, double-spaced body
text and textual numeric mathematics. It is not a TeX compiler. Native editor
compilation status is recorded separately; a readable PDF must not be reported
as successful native TeX compilation. The source uses separate figure files,
which the standalone native editor may not support.

The six local Additional-file archives are intended for author review and each
must remain below 20 MB. Public deposition, source-data redistribution,
repository URL/DOI and license are pending; see `BMC_AUTHOR_ITEMS.md`. Local
packaging does not resolve these administrative requirements.

## Local delivery verification

After source/PDF/figure/claim audits and all documentation are final:

```bash
artifacts/completion_v2/publishing_runtime/bin/python scripts/build_bmc_revision_package.py
python scripts/verify_bmc_package.py
python scripts/bundle_bmc_delivery.py
```

The second command checks all archive/member hashes against the current local
files, every compact nearest-input query against its original full record, and
materializes all 25 exact frozen source snapshots in a temporary directory.
The six individual attachments are each smaller than 20,000,000 bytes. Large
weight files and full raw free-draw arrays remain outside these bounded
attachments; hashes and rerun instructions identify them without claiming
that a public archive already exists.
