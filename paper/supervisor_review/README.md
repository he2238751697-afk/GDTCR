# GDTCR supervisor-review draft

This English scientific draft is prepared for supervisor review before journal
submission. It follows BMC Bioinformatics research-article structure and keeps
the scientific results frozen at the verified e7f4fc0 baseline.

Start with GDTCR_supervisor_review.pdf and GDTCR_supplementary.pdf.
GDTCR_review_notes.pdf explains the research question and requested feedback;
GDTCR_journal_comparison.pdf compares BMC Bioinformatics, Briefings in
Bioinformatics and Bioinformatics using official instructions and same-year
2025 impact factors checked on 3 November 2026.

Both scientific PDFs use A4, 11 pt, 1.5 spacing and page numbering. They omit
author/affiliation information, line numbering, dates and administrative
placeholders. Submission declarations are retained outside the review PDFs in
SUBMISSION_DECISIONS.md, with historical facts in ../BMC_AUTHOR_ITEMS.md.
This is an internal review version, not a complete
journal submission or an assertion of author approval.

## Build

From the repository root with TeX Live and Poppler installed:

    python scripts/build_submission_pdfs.py --profile supervisor-review --copy-reading-copies

Use --pdflatex /absolute/path/to/pdflatex if needed. Build artifacts and logs
are written to output/supervisor_review/. The original bmc build profile keeps
its prior sources, output locations and date. The new main/supplementary
sources are manuscript.tex and supplementary.tex in this directory.

The optional one-page notes are compiled with --include-review-notes.
The manuscript source/data/figure identities are recorded in native_compile.json.
Scientific verification and visual inspection are recorded independently.

## Evidence and attachments

Main Figures 1–6 and Tables 1–3 retain their identities. Original Figure 7 is
Supplementary Figure S3; Figures S1–S2 keep their numbering.
All vector PDF, editable SVG and 300 dpi PNG scientific figure assets remain
unchanged under ../results/bmc/figures/. CONTENT_MAP.tsv records the migration
of detailed methods, sensitivity and diagnostic outcomes.

The six Additional files, editable-source and figure archives are versioned
in attachments/; working copies and the combined review package are under
output/supervisor_review/package/. They are generated and verified by
scripts/build_supervisor_package.py. Original table data and
frozen computational objects remain intact; supplementary descriptions are
updated only for this review version. Each numbered attachment is below 20 MB.

The public data/code release remains reproducibility-v1. This revision adds
an independent review branch; it does not modify its scientific release tag,
publish to Zenodo, or submit the manuscript.

## Verification and packaging

With the frozen local analysis artifacts available:

    python scripts/audit_supervisor_draft.py

This checks the new draft independently. It does not fit models or resample
intervals. Numerical data files and all 225 frozen scientific file hashes
remain unchanged. Visual checks are recorded in visual_audit.json.

Verify the distributed archives and restore/check frozen source snapshots:

    python scripts/build_supervisor_package.py --verify-only

Repackaging from the cached, verified historical six-archive set:

    python scripts/build_supervisor_package.py --base-package-dir /path/to/verified/e7f4fc0/archives

The old input ZIPs are authenticated against the preserved historical manifest
and are never overwritten. This packaging step only updates document material
and its metadata. It is distinct from reproducing scientific experiments,
whose portable workflow is in ../../REPRODUCIBILITY.md.

The combined local reading bundle can be refreshed without repackaging inputs:

    python scripts/build_supervisor_package.py --bundle-only
