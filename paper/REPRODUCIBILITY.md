# Reproducing completion-v2

The scientific unit is an immutable manifest task linked to its code snapshot,
inputs, checkpoint, saved candidates and analysis. A Git commit alone is
insufficient because the local working tree also contains tracked modifications
and new files; source-content SHA256s and frozen code directories identify the
executed version. Historical v1 results retain their original provenance.

## Required material

Use the original raw files with the hashes in `data/provenance/manifest.json`.
The processed corpus, provenance tables and split TSVs are local data artifacts;
they are not all distributed in Git. The expected primary corpus has 9,068 pairs,
194,887 gamma and 1,262,692 delta sequences. Obtain changed upstream exports only
as a new data version; never silently substitute them into the frozen benchmark.
No universally applicable redistribution license is implied; see
`LICENSE_AND_ACCESS.md`.

The tested core environment is Python 3.10.20 with Torch 2.7.1+cu126, NumPy 2.2.6,
SciPy 1.15.3, scikit-learn 1.7.2 and RapidFuzz 3.9.7. Exact computational pins are
in `configs/completion_v2/requirements-lock.txt`; the complete effective package
inventory is `artifacts/completion_v2/environment.json`. Plot export additionally
uses Matplotlib 3.10.9. The downstream virtual environment inherits the base
environment's site packages; both resolve the same core Torch and NumPy versions.
The original pretraining manifest uses the base interpreter, while downstream
manifests use the recorded virtual-environment interpreter. Hardware and numeric
settings are recorded per run.

PDF export has a separate publishing environment with exact versions in
`configs/completion_v2/publishing_requirements.txt`. Installing those packages
does not alter the frozen training runtime. The native LaTeX compiler returned a
platform-directory error; a ReportLab reading copy is generated from the saved
manuscript source and inspected visually. A generated reading copy is not evidence
that the TeX source compiled successfully in the native editor.

The final local TeX source has SHA256
`fcbcb5077aaa210de898a86a70599bf1e21cb232499f9720814619af90dcb5e7`;
the inspected PDF has SHA256
`351c949ed4261abd532ad262e1edd56a0c4c10065d6905efd966ed12b6d9042a`.
The final renderer, `scripts/render_manuscript_pdf.py`, has local source SHA256
`6f2ab21671b68a47d4ebcc6dfe189f947701a1846f4481c37ebee753e44ba605`.
Its render record separately identifies the source, PDF and renderer hashes.
Use the current renderer in `source/scripts/` of the anonymous package to make a
reading copy, not the older renderer incidentally preserved inside numerical
export snapshots. The final repair handles escaped percent symbols inside math;
the rejected candidate and its failed inspection remain in the private audit.
No numerical output or manuscript source was changed by that repair.

In a fresh repository replica with the publishing dependencies available, render
to a new location and inspect the result:

```bash
python -B scripts/render_manuscript_pdf.py --source paper/manuscript_v2.tex --output tmp/pdfs/reproduction/manuscript.pdf
```

In the review ZIP the manuscript is at `manuscript.tex`, its figures are in
`figures/`, and the renderer is at `source/scripts/render_manuscript_pdf.py`.
The package manifest distinguishes original hashes from anonymous derivatives;
path-porting and fresh PDF metadata need not preserve original file byte hashes.

## Data reconstruction

Run these steps only in a fresh replica, with the raw inputs already obtained.
Several legacy preparation commands replace outputs and must not be run over
the immutable completed experiment tree.

```bash
python -B src/clean_data.py --raw-dir data/raw --output-dir data/processed
python -B scripts/export_provenance.py
python -B scripts/prepare_experiment.py --seeds 17 3407 2026
python -B scripts/prepare_source_holdout.py
python -B scripts/prepare_source_holdout.py --allow-shared-chains --output data/splits/source_shared
python -B scripts/prepare_completion.py
python -B scripts/prepare_candidate_pools_v2.py
```

Compare the processed and split hashes, counts, exact chain overlaps and source
memberships against the preserved manifests and independent data/pool audits.
Compressed JSON byte hashes can depend on gzip metadata; sequence membership,
frozen scientific content and recorded artifact hashes must be distinguished.
Do not revise the already inspected test sets to improve balance or results.

## Task graph and execution

The immutable manifests in `configs/completion_v2/` record exact commands, model
seeds (3407 and 3508), code snapshots, requirements and outputs. Read
`task_supersessions.json`: four source-shared generator tasks and all 42 original
ranker entries were corrected before those tasks ran. The replacement manifests
are authoritative. The failed first distance-export audit is retained; its
replacement is `distance_audit_corrected_jobs.json`.

Run dependencies in this order:

1. Pair-excluded denoising initialization and frozen denoising validation.
2. Generators and independent rankers with selection-validation checkpoints.
3. Exact-distance, exact-neighbor/frequency and shallow baseline tasks.
4. Tuning and calibration evaluations, frozen fusion/threshold settings, test
   evaluations, then application of the frozen settings.
5. The analysis manifest: per-run component/source-query intervals, strata,
   baseline intervals and paired differences.
6. Complete training and evaluation-content audits, then verified evidence
   collection, figures/tables and manuscript export.

The generic executor is:

```bash
python -B scripts/execute_manifest.py --manifest CONFIG_PATH --task TASK_INDEX
```

On a new machine, first preserve the original manifests, then create separately
named execution manifests with the new workspace, interpreter and snapshot root.
Retain the commands, scientific inputs and original-to-new path mapping. Copying
the original local absolute paths into a new environment is not sufficient.
The queue helper's account, partitions and QoS are site-specific; port scheduler
settings while preserving the scientific command. Do not submit the same task
twice or overwrite a completed task record.

Primary training uses A800 GPUs. Evaluation may use other recorded CUDA devices;
TF32 and matmul precision are recorded, and all rescoring entry points initialize
the same numeric settings. Bitwise identity across GPU models is not assumed.
Within a saved-candidate rescore check on the same device and ranker, the audited
maximum score difference is zero. Wall time and peak allocated/reserved memory
are descriptive runtime measurements, not a controlled GPU benchmark.

The 64-draw primary setting remains fixed. The tuning sampling grid does not
change it. Split-17 budgets share the first 16/64/256 saved draws. Fixed-pool
comparisons must share the exact pool SHA256; free-generation comparisons pair
test queries while retaining each model's own saved draws. Training negatives
use only training edges, whereas evaluation may exclude any other recorded
partner from the distractor labels.

## Evidence and failures

The completed evidence at
`artifacts/completion_v2/final_evidence/evidence.json` has SHA256
`5badb3b9b8ead02c57afeb5f578f85f3a5e343bad9714fb7daa08f48342b2f3b`.
It contains all 557 effective tasks, 193 run/baseline reports and 552 paired
comparisons. Numerical exports were executed from the immutable snapshot named
by `artifacts/completion_v2/final_export_code_v2.json`; its source hashes are
independent of subsequent documentation and PDF-renderer changes.

`scripts/collect_evidence_v2.py` refuses a final export unless every required
manifest task is complete and its outputs match the recorded hashes. The explicit
`--allow-partial` option creates a progress snapshot, clearly marked unsuitable
as final evidence. It exports per-seed metrics, empty strata and paired intervals,
and computes split means by averaging the two model seeds within each split
before the descriptive three-split SD. This is not a test based on six independent
biological replicates.

The first distance audit checked all 28 tables but failed during test-stratum
export because a string was supplied where a Path was required. Its replacement
uses a new output directory. Historical invalid-target prior runs, a failed GPU
smoke, and this export failure are retained as non-results. The archival index
and failed task records document them; no failed artifact contributes to the
scientific tables.

Run checks with `PYTHONPATH=src:. python -B -m unittest discover -s tests -v`.
Tests include multi-positive handling, held-out-pair exclusion boundaries,
directional scoring, EOS validity, candidate retention, calibration leakage
gates, exact-neighbor scoring and cluster/paired-bootstrap behavior. Integration
checks exercise the complete GPU evaluation and CPU analysis paths. Tests verify
implementation behavior; they are not substitutes for full experimental outputs.

`evaluation_audit_jobs.json` checks all 88 model-evaluation records, including
every saved draw, frozen pool, prefix metric, re-fitted calibration setting and
its test application. Rescored ranker ablations must preserve the original samples
and non-ranker scores. `training_audit_jobs.json` verifies selected checkpoint
weights and the logged criteria, stage schedules and exposure accounting for all
118 newly trained models. These audits verify saved scores and their downstream
use; they do not claim to rerun every GPU forward pass.

Use `evaluation_audit_supersessions.json` for the final evaluation-audit union:
14 original passing tasks plus 74 tasks in `evaluation_audit_corrected_jobs.json`.
The correction restores deterministic 64-column tensor padding before checking
saved token prefixes. A budget-exhausted no-EOS sample remains invalid; its
original diagnostic reason is preserved. The failed first audit is retained and
does not contribute to the final evidence. See the implementation notes.

Anonymous review materials omit local host/account paths and provenance headers
that identify the researcher. The unmodified private audit tree remains available
for later reproducibility work. Public deposition, author declarations and
license assignment are separate from the anonymous scientific manuscript.
