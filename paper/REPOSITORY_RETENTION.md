# Repository retention and cleanup record

Version: completion-v2. Cleanup separates authoritative results, historical
evidence and temporary publishing files. It does not erase unsuccessful runs or
claim that moving files to an archive frees their storage space.

## Preserved scientific records

| Material | Location and disposition |
| --- | --- |
| Raw downloads and cleaned sequences | `data/raw/`, `data/processed/`; retained with original-source access and redistribution limits. |
| Observation/source lineage and frozen splits | `data/provenance/`, `data/metadata/`, `data/splits/`; retained. Missing donor identities are not reconstructed. |
| Historical v1 evidence | `artifacts/evaluations/audited/`, `paper/results/evidence.json`, `paper/initial_draft.md`; explicitly historical, excluded from v2 aggregate estimates. |
| V2 models, candidates, calibration and analyses | `artifacts/completion_v2/`; completed records and their input/output hashes are immutable. |
| Executed source versions | `artifacts/completion_v2/code/`; retained independently of the uncommitted worktree. |
| Superseded manifests and failed audits | Retained alongside explicit supersession registries; not counted as effective completed experiments. |
| Pre-revision repository snapshots | `artifacts/code_snapshots/`; recovery copies, not new experiment results. |
| Private journal/literature webpages | Ignored `artifacts/literature/`; original webpages may contain proxy metadata and are excluded from anonymous review packages. Public metadata and checked excerpts remain in `paper/reference_metadata/`. |

The effective task union is determined by both
`configs/completion_v2/task_supersessions.json` and
`configs/completion_v2/evaluation_audit_supersessions.json`. File counts over the
entire artifact tree would incorrectly combine valid tasks, integrations,
superseded attempts and failures.

## Executed historical cleanup

`artifacts/archive/cleanup_20260930T013727Z/README.md` documents the preserved
redundant checkpoint copies, obsolete runs, benchmark outputs, unused caches,
wrong-target runs and accidental Slurm submissions. Formal selected checkpoints,
valid reused pretraining weights, input data and audited historical results were
retained. The archive is approximately 14 GB; it is retained evidence, not
reclaimed disk space.

The pre-cleanup source snapshot is
`artifacts/code_snapshots/cleanup_before_20260930T013727Z.tar.gz`, SHA256
`6bd4f91a43d19ab06d9decd4e53084d0a5dbc2858a0d05897a9faaae8d26888a`.
It contains the removed `configs/model_base.json`, `configs/model_smoke.json`
and `slurm/train_eval_4090.sbatch`, so these deletions are recoverable.

The historical launcher `slurm/submit_pipeline.sh` now honors `--dry-run` without
calling `sbatch` or writing submission records. Unknown arguments fail before
submission. Two tests use a substitute `sbatch` and verify those behaviors; the
v2 workflow uses the frozen manifest executor instead of this legacy launcher.

## Publication cleanup and final handoff

Status: cleanup complete; historical records and final publication entry points indexed.

The authoritative manuscript is `paper/manuscript_v2.tex`, with verified
figures and tables under `paper/results/v2/` and the anonymous PDF under
`output/pdf/`. The final review-package path is
`output/gdtcr_anonymous_review.zip`; its authoritative integrity certificate is
`artifacts/completion_v2/release_v2/release_manifest.json`, issued by the strict
release gate. Progress snapshots and provisional figures are not substitutes.

The working PDF, its render record and text, and 19 earlier preview files were
archived under `artifacts/archive/publication_cleanup_20260930T101408Z/`.
Its `manifest.json` records all 22 original paths, byte sizes and SHA256s;
manifest SHA256 is
`846d7b252d092f4c879718f176e384baf4acb1d50cce3fe378ed76912b106d08`.
All files were checked after moving, and no frozen task manifest references
these paths. The retained archive is 5,527,356 bytes and reclaims no disk space.
Current rendering intermediates stay under ignored `tmp/pdfs/`; final inspected
pages are retained with the publication audit.

The first final PDF candidate had a renderer escape-token defect in a percentage
expression. Its PDF, render record, extracted text, page images and failed review
are retained under
`artifacts/completion_v2/publication_reviews/rejected_percent_tokens/`.
The corrected PDF passed inspection of all 23 pages; the source manuscript and
completed numerical exports were unchanged. This rejected publishing candidate
is an audit record, not an alternative scientific result.

No active Slurm output directory is moved for tidiness. No Git reset, forced
checkout, history rewrite, remote push, public deposition or license assignment
is part of this cleanup. The shared worktree's pre-existing changes and the
completed research changes remain available for inspection.
