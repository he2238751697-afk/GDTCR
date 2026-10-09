# Figure, table and page inspection audit

The final native PDFs contain 40 manuscript pages and 6 supplementary pages.
Every page was rendered at 144 dpi with Poppler and visually inspected in
four-page contact sheets; dense figure and table pages were also inspected
individually. Page-specific render checksums and PDF/source identities are in
visual_audit.json. Inspection was performed by the editing assistant and does
not represent author review or submission approval.

No missing mathematical glyphs, blank hyperparameters, broken equations,
clipping, overlapping elements, broken citation markers or malformed tables
were found in the final rendering. Native compilation reports no critical TeX
diagnostics. All fonts are embedded and none is Type 3. Character-bound checks
supplement, but do not replace, visual inspection.

| Object | First citation page | Figure/caption or table page | Placement rationale |
| --- | ---: | ---: | --- |
| Figure 1 | 8 | 9 | Immediately after the model/workflow description |
| Figure 2 | 16 | 16 | At the dataset and graph-exposure characterization |
| Figure 3 | 19 | 20 | Adjacent to the primary free-generation result; events and SD labels remain legible |
| Figure 4 | 21 | 23 | Beside the retrieval interpretation; full-width panels preserve labels |
| Figure 5 | 24 | 25 | Adjacent to training-size and graph-composition sensitivity, with all actual edge counts visible |
| Figure 6 | 27 | 28 | Adjacent to exposure-protocol diagnostics |
| Figure 7 | 30 | 32 | Beside sampling/calibration interpretation; retained in the main manuscript |
| Table 1 | 15 | 15 | Dataset Results |
| Table 2 | 17 | 18 | Likelihood Results; direction expressions remain intact |
| Table 3 | 17 | 21 | NLL first mentions the shared contrast table on page 17; the primary recovery interpretation cites it on page 19. Generator and ordering panels share page 21 |
| Figure S1 | 3 | 4 | Supplementary pretraining sensitivity |
| Figure S2 | 5 | 5 | Supplementary negative-training sensitivity |
| Table S1 | 2 | 2 | Supplementary control hierarchy; no cross-reference label is needed |

All figure captions share their figure's page. Figures 1–7 and Tables 1–3
remain in numerical order. Figure 4 and Figure 7 follow their first citations
by two pages to retain readable full-width graphics. Table 3's two panels keep
all original estimates and interval endpoints together. Whitespace on figure
pages is intentional; no dense figure was compressed to force citation-page
placement. Main text retains double spacing, line numbers and page numbers.

Separate vector PDFs, editable SVGs and 300 dpi PNGs are preserved for Figures
1–7 and S1–S2. The journal_figure_assets.zip archive contains those 27 files and
a content manifest. The two editable TeX documents preserve mathematical
symbols and tables as source. Earlier ReportLab copies and failed compiler
records are historical outputs superseded by native_compile.json here.
