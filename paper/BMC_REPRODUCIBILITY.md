# Reproducing the BMC revision

Current author-review update (9 October 2026): the scientific base is publicly
available at https://github.com/he2238751697-afk/GDTCR/releases/tag/reproducibility-v1 .
Use the root `REPRODUCIBILITY.md` for a fresh public clone. The scientific
results below remain unchanged; `final_submission/` records the current
manuscript compilation, consistency and page-inspection audits.

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
python scripts/build_submission_pdfs.py --copy-reading-copies
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

`build_submission_pdfs.py` compiles both current TeX documents with native
pdflatex, stabilizes references and retains the logs and input hashes. It
requires TeX Live and Poppler; compilation needs neither model fitting nor
the large artifact tree. The earlier `render_bmc_pdf.py` and its ReportLab
outputs remain historical reading-copy tools, not the current publication
build. Every final PDF page is rendered and inspected separately.

The six local Additional-file archives are intended for author review and each
must remain below 20 MB. Public repository access is established. A persistent
archive DOI, code/weight licenses, unresolved third-party terms and author
declarations remain pending; see `BMC_AUTHOR_ITEMS.md`.

## Local delivery verification

After source/PDF/figure/claim audits and all documentation are final:

```bash
artifacts/completion_v2/publishing_runtime/bin/python scripts/build_bmc_revision_package.py
python scripts/verify_bmc_package.py
python scripts/bundle_bmc_delivery.py
```

The second command checks all archive/member hashes against the current local
files, every compact nearest-input query against its original full record, and
materializes every exact frozen source snapshot in a temporary directory;
the verification report gives the snapshot and restored-file counts.
The six individual attachments are each smaller than 20,000,000 bytes. Large
weight files and full raw free-draw arrays remain outside these bounded
attachments. The four inherited initialization weights are available as a
verified GitHub release asset; full raw free-draw arrays are reconstructed by
the frozen execution workflow. Hashes and rerun instructions identify them.
No Zenodo DOI is claimed until a real deposit is completed.
