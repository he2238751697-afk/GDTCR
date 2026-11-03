# Figure and table placement audit

Final PDFs: manuscript 24 pages; supplement 14 pages. Every page was rendered
at 144 dpi and inspected; the two one-page notes were inspected separately.
All captions remain on the same page as their graphics or tables.

| Document | Item | First citation page | Figure/table page |
| --- | --- | ---: | ---: |
| Main | Figure 1 | 5 | 6 |
| Main | Figure 2 | 9 | 10 |
| Main | Figure 3 | 12 | 13 |
| Main | Figure 4 | 15 | 16 |
| Main | Figure 5 | 17 | 17 |
| Main | Figure 6 | 18 | 19 |
| Main | Table 1 | 9 | 9 |
| Main | Table 2 | 11 | 11 |
| Main | Table 3 | 11 | 14 |
| Supplement | Figure S1 | 7 | 8 |
| Supplement | Figure S2 | 9 | 9 |
| Supplement | Figure S3 | 12 | 14 |
| Supplement | Table S1 | 2 | 3 |

All main figures are on the citation page or the following page. Dense figures
use full text width and, when needed, a dedicated page. Figures 1–6 retain
order and their model/data/primary/retrieval/size/exposure interpretation.

Table 3 is first signposted in the NLL paragraph on page 11, then discussed
with the primary Hit@5 comparison on page 12. Its two panels appear together
on page 14 beside the ranking comparison, following Figure 3; it covers both
NLL and recovery and has not been split or detached from its interpretation.
Tables 1 and 2 share their first-citation pages.

Figure S3 is cited on supplement page 12, after the brief main-text reference
on page 15. Its budget, exclusion and calibration interpretation occupies
pages 12–13, followed by the intact figure/caption on page 14. No panel was
shrunk merely to fit the first-citation page. Original Figures S1/S2 retain
numbering; Table S1 has an explicit internal reference.

visual_audit.json binds this inspection to source/PDF hashes and rendered
page hashes. placement_audit.json derives page locations from the new TeX
auxiliary files and extracted PDF text; no previous placement audit was reused.
