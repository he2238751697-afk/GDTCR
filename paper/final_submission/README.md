# GDTCR author-review package

Prepared on 9 October 2026 for BMC Bioinformatics. This is the version for
**author review before submission**. The authors have not yet reviewed or
approved it. Scientific experiments, saved outcomes and evaluation protocols
remain frozen.

The editable main source is paper/manuscript_bmc.tex; the supplementary source
is paper/supplementary_methods_bmc.tex. Their native LaTeX PDFs are under
paper/reading_copies/. These replace the earlier ReportLab reading copies in
this branch. The historical PDFs remain at the immutable reproducibility-v1 tag.

Run from the repository root:

    python scripts/build_submission_pdfs.py --copy-reading-copies
    python scripts/build_bmc_revision_package.py
    python scripts/verify_bmc_package.py

Compilation requires TeX Live with pdflatex and Poppler's pdftotext,
pdfinfo, pdffonts and pdftoppm. The --pdflatex option accepts an explicit
engine path. Package reconstruction additionally requires the restored
scientific artifact tree described in REPRODUCIBILITY.md; compiling the PDFs
from the committed TeX and figure assets does not require experiments or GPUs.

The six numbered Additional-file archives, editable-source archive, journal
figure assets and final checksums are delivered together under
output/bmc_revision/. Each Additional file must remain below 20 MB.
BMC_SUPPLEMENT_INDEX.md maps each citation to its actual archive contents.
Figures are separately available in vector PDF, editable SVG and 300 dpi PNG;
tables remain editable TeX rather than images.

The audit records in this directory distinguish native compilation, page
inspection, figure/table placement, reference checks, scientific consistency
and changes made. scientific_freeze.json records the original hashes of data,
configurations, model implementation, saved numerical tables and evidence.
Historical audit outputs under paper/results/bmc/ are dated records; current
submission status is established by this directory and BMC_AUTHOR_ITEMS.md.

The public scientific base is
https://github.com/he2238751697-afk/GDTCR/releases/tag/reproducibility-v1
at fcf153c76d8eeac358d1a26da3df470eb4118992. It includes all 43 original
input exports, three cleaned inputs and four inherited initialization weights.
It is a public release, not a persistent archive DOI. See BMC_AUTHOR_ITEMS.md
for the declarations, correspondence details, licenses, third-party terms and
Zenodo steps still required before submission.
