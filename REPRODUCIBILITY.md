# Reproducing GDTCR from the public release

Use a fresh clone for inspection, and a separate run directory for computation.
The release contains all 43 original input exports, all cleaned inputs and
frozen split tables. `THIRD_PARTY_DATA.md` describes source attribution and
license evidence. The original data are upstream sequence/contig exports,
not raw FASTQ reads.

## 1. Verify and rebuild the data

```bash
python scripts/reproduce.py verify
python scripts/reproduce.py rebuild-processed --output ../GDTCR-cleaned
```

Verification checks the release inventory, all raw/processed/provenance hashes,
and every object in the frozen source archive. Cleaning is actually rerun on the
raw exports and must match all three original processed-file SHA256s. Expected
counts: 194,887 gamma sequences, 1,262,692 delta sequences and 9,068 pairs.

Primary splits use seeds 17, 3407 and 2026 and contain 7,254/907/907 edges each.
The held-out chains must be disjoint in the primary protocol. Directional,
source and revision splits intentionally answer different questions. Do not
substitute one protocol for another or regenerate test sets to improve balance.

## 2. Install the tested runtime

```bash
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install -r configs/completion_v2/requirements-lock.txt
OMP_NUM_THREADS=2 PYTHONPATH=src:. python -B -m unittest discover -s tests -v
```

The pinned core runtime uses PyTorch 2.7.1+cu126, NumPy 2.2.6, SciPy 1.15.3,
scikit-learn 1.7.2 and RapidFuzz 3.9.7. The much larger recorded `pip freeze`
inventories contain unrelated packages and local editable paths: they are
historical inventories, not portable installation requirements. For plots and
reading-copy PDFs additionally install
`configs/completion_v2/publishing_requirements.txt`.

## 3. Prepare an isolated run workspace

```bash
python scripts/reproduce.py prepare --output ../GDTCR-run --python .venv/bin/python
python scripts/reproduce.py status --workspace ../GDTCR-run
```

Preparation refuses an existing output directory. It copies the scientific
inputs, restores the exact frozen code files, and creates separate execution
manifests under the new run's `configs/`. Original manifests remain intact in
the clone and are also preserved under `reproducibility/original_configs/` in
the run workspace. Only execution-root, interpreter and corresponding path/hash
references are ported; model hyperparameters, seeds, commands, task indices and
scientific inputs remain fixed. `reproducibility/porting_record.json` records
original and ported hashes. The two supersession tables are updated to refer to
the ported manifest hashes, so superseded tasks do not reappear.
Preparation also records the actual new interpreter/package environment; the
historical environment inventory stays under the labeled reference inputs.

The task index selects the 557 effective original tasks and 43 revision tasks
from the completed records, including the corrected generator/ranker and
evaluation-audit manifests. The runner never uses every historical manifest
indiscriminately. It runs sequentially without requiring Slurm; use an allocated
GPU for CUDA phases. The old Slurm wrappers contain site-specific accounts and
queues and are not the portable entry point.

## 4. Restore the inherited initializations

```bash
python scripts/reproduce.py fetch-initializations --workspace ../GDTCR-run
```

The repository is read from `reproducibility/release.json`; `--repository
OWNER/GDTCR` can explicitly select a fork. The command obtains the
`gdtcr-legacy-initializations.tar.gz` asset from the `reproducibility-v1` release,
checks its size and SHA256, and checks every extracted checkpoint. Downloaded
content is never used before those checks pass. Local/offline use is supported:

```bash
python scripts/reproduce.py fetch-initializations --workspace ../GDTCR-run \
  --archive /path/to/gdtcr-legacy-initializations.tar.gz
```

These four immutable checkpoints supply the original sqrt-sampling and
source-excluded sqrt initializations. Their original run arguments, metrics and
metadata are provided. The remaining pretraining ablations and downstream fits
are rerun by the manifests. Checkpoints serialize PyTorch objects and should be
loaded only after verifying the release checksum. This release does not promise
that retraining the inherited initializations on another GPU yields identical
weights.

## 5. Run the scientific tasks

```bash
python scripts/reproduce.py status --workspace ../GDTCR-run
python scripts/reproduce.py run --workspace ../GDTCR-run --suite all --max-tasks 1
```

The `run` command executes computation. `status` is read-only. To continue the
whole experiment graph, use `--max-tasks 600`; completed records and every output
hash are verified before being skipped. The runner selects only tasks with
completed producers and present inputs, reports unresolved dependencies, and
stops on failures. It does not resubmit failed tasks or silently overwrite
outputs. Subsets are `--suite primary` and `--suite revision`; revision-only
fits still require the inherited initializations. The nearest-input revision
baselines require only their fixed data/pools.

The first `pretrain_delta` distance result predates the 557-task graph; its
recorded deterministic output is supplied among the reference inputs. Its
recorded command is retained with the other distance metadata. The four legacy
pretraining runs and this distance job are dependencies, not additional entries
invented in the original task count.

Full retraining is a GPU workload, not a quick verification. Original fitting
used A800 GPUs; the revision used RTX 3090 GPUs. Floating-point results and
compressed output bytes can differ across hardware/runs. Compare scientific
memberships, metrics and uncertainty units rather than asserting identical
timestamps, Slurm IDs, timings or new checkpoint hashes.

## 6. Audit new outputs and compare with the reference

From the run directory, after the relevant tasks finish:

```bash
python scripts/audit_data_v2.py --output artifacts/completion_v2/data_audit_final.json
python scripts/audit_candidate_pools_v2.py
python scripts/collect_evidence_v2.py --output artifacts/completion_v2/reproduced_evidence
python scripts/analyze_revision_bmc.py
```

The original primary evidence is restored to its historical path to support
revision checks, and must not be overwritten with new results. The new original
benchmark evidence therefore uses `reproduced_evidence`. The immutable reference
SHA256 is `5badb3b9b8ead02c57afeb5f578f85f3a5e343bad9714fb7daa08f48342b2f3b`.
New task records are generated locally; historical records are not installed as
if they had run on the new machine. Portability checks and data reconstruction
do not claim that all 600 computational tasks were retrained during publication.

The two BMC diagnostic protocols preserve their recorded interpretation. The
within-giant test has one original component, so it has no inferential
component-bootstrap confidence interval. Fixed-pool retrieval and free
generation are different endpoints. See `paper/BMC_REPRODUCIBILITY.md`,
`paper/protocol_v2.md`, and `paper/revision_bmc_protocol.md` for scientific detail.
