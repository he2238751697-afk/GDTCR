# Author-review delivery, 9 October 2026

The scientific presentation, native PDF layout and reproducibility checks are
complete for author review. This is not an approved BMC Bioinformatics
submission. The authors have not yet reviewed the draft; the remaining facts
and decisions are listed in [BMC_AUTHOR_ITEMS.md](../BMC_AUTHOR_ITEMS.md).

| Requested deliverable | Location |
| --- | --- |
| Main manuscript source | [manuscript_bmc.tex](../manuscript_bmc.tex) |
| Native manuscript PDF, 40 pages | [gdtcr_bmc_revision.pdf](../reading_copies/gdtcr_bmc_revision.pdf) |
| Supplementary source | [supplementary_methods_bmc.tex](../supplementary_methods_bmc.tex) |
| Native supplementary PDF, 6 pages | [additional_file_1_bmc.pdf](../reading_copies/additional_file_1_bmc.pdf) |
| Six Additional files, each below 20 MB | output/bmc_revision/additional_file_1.zip through additional_file_6.zip; [content audit](ATTACHMENT_AUDIT.md) |
| Separate high-resolution/editable figures | output/bmc_revision/journal_figure_assets.zip; tracked files under paper/results/bmc/figures/ |
| Editable journal-source bundle | output/bmc_revision/gdtcr_bmc_editable_source.zip |
| Combined author-review bundle | output/bmc_revision/gdtcr_bmc_local_review.zip |
| Figure/table placement and every-page inspection | [PLACEMENT_AUDIT.md](PLACEMENT_AUDIT.md), [visual_audit.json](visual_audit.json) |
| Cross-reference and numerical consistency | [CONSISTENCY_AUDIT.md](CONSISTENCY_AUDIT.md), [crossref_numerical_audit.json](crossref_numerical_audit.json) |
| Changes, separated by type | [CHANGES.md](CHANGES.md) |
| Zenodo metadata and local archiving instructions | [zenodo/README.md](zenodo/README.md), [metadata_draft.json](zenodo/metadata_draft.json) |

The native compile records and PDF/source/figure identities are in
native_compile.json. All 46 pages passed visual inspection. The 437-check BMC
numerical audit and 418-check final audit passed, including 225 unchanged
scientific file hashes and independent reconstruction of primary summaries
from 34,296 saved query rows. No scientific discrepancy was identified.
The existing 63-test suite also passed; regression_tests.json records its
scope and the log identity. Model fitting was not restarted.

All six attachments and the editable/figure archives passed hash and content
checks. Verification restored 25 local completion/revision code snapshots and
also verified the embedded public archive's 27 snapshots, which include the
inherited pretraining sources. The current package manifests are copied here
after packaging to avoid self-referential archive hashes. The combined bundle's
checksum is recorded separately in output/bmc_revision/local_review_manifest.json.

The revision is isolated on the Git branch codex/bmc-submission-ready, based on
fcf153c76d8eeac358d1a26da3df470eb4118992. The original dirty working tree and
immutable reproducibility-v1 scientific release are preserved. Changes to
scientific wording clarify existing evidence; formatting changes do not alter
results, denominators, model settings, protocols, intervals or conclusions.

The public base is https://github.com/he2238751697-afk/GDTCR . Its release
contains all 43 original input exports and the verified initialization asset.
The current branch inventory is refreshed before committing; the original
release inventory remains available at its tag. Source/data and initialization
files for the planned Zenodo deposit are prepared from the final clean commit
under output/zenodo_draft/, with an archive inventory and SHA256SUMS. Local
output archives are not Git blobs. Zenodo authentication, license selection,
final declarations and author approval are deferred; no DOI or deposit is
claimed and no journal submission has been made.
