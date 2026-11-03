# Scientific and document consistency audit

The final supervisor draft passed 866 checks in scripts/audit_supervisor_draft.py.
The audit reads the current sources and their compiled PDFs and independently
checks the saved results; it does not reuse a previous pass conclusion.
No scientific discrepancy was found in the checked material.

## Frozen evidence and numerical presentation

- All 225 scientific files match paper/final_submission/scientific_freeze.json.
  Primary evidence SHA256 is 5badb3b9b8ead02c57afeb5f578f85f3a5e343bad9714fb7daa08f48342b2f3b;
  revision summary SHA256 is d19a7f3a517058dc230e73b6b10c2bbc19cfdd83c9b0a9a407945804a277ef70.
- All three main table blocks are identical to the verified e7f4fc0 manuscript.
  The mean and sample SD summaries were independently reconstructed from
  34,296 saved query rows, including NLL, coverage and all available Hit@5
  ordering scores. Model seeds are averaged inside split; directions receive
  equal weight in the primary macro endpoint.
- Conditional/prior likelihood events were rechecked for all fits. Nonzero
  conditional delta-to-gamma results are 2/900 (split 17, seed 3407) and 1/906
  (split 3407, seed 3508). The prior and all gamma-to-delta results are zero.
  Saved prior-minus-conditional contrasts are negated with interval ends
  swapped: equal-direction differences 0.11 [0.00,0.27] and 0.06 [0.00,0.17]
  percentage points, with four zero-event [0,0] contrasts. All six include zero.
- Primary NLL and recovery excerpts, retrieval averages, nearest-input ranking,
  training-size NLL, source/directional diagnostics, query-balanced unseen-gamma
  counts and intervals, and within-giant counts were checked against frozen
  evidence or revision summaries. No inferential giant-component interval was
  introduced. Source/component strata recompose the primary estimates.
- Eight migrated result/sensitivity sections preserve their numerical tokens
  in the original order, excluding document numbering. Complete exposure and
  sampling/calibration outcomes remain in the supplement. The descriptive
  failure counts 879/19/2 and 527/2/0 were reconstructed from saved queries.
- NLL formula and prose were compared with src/gdtcr/training.py:123,145,
  scripts/train_generator.py:82 and scripts/evaluate_free_v2.py:118,173,194.
  These implement token mean per partner, partner mean per query, query mean
  per direction and equal directional mean. Token-weighted reports and the
  minibatch optimization loss are explicitly distinguished.

## Structure, references and interpretation

The main scientific prose has 5,054 tokens under the recorded counter (headings
and numerical prose tokens included; abstract, bibliography, floats and math
excluded). The abstract has 253 words under that counter and uses the required
Background/Results/Conclusions headings, without references. Counts are an
editing guide, not an assertion of a universal journal counting convention.
Methods has six subsections, Results six and Discussion four. CONTENT_MAP.tsv
records the relocation of methods, sensitivity and historical results.

All 18 citations resolve to bibliography entries in first-citation order.
DOI metadata, issue-year distinctions and the two contextual additions are
recorded in references.json and REFERENCE_AUDIT.md. All six Additional files
are described; main Figures 1–6, Tables 1–3, supplementary S1–S3 and Table S1
resolve correctly. Abbreviations are defined in the prose/list or the detailed
supplementary methods. Existing research papers/preprints retain accurate
publication labels.

The claim review preserves the distinctions between recorded pairing and
biological function, truth-containing retrieval and free generation, direct
partner transfer and partner-similarity ranking, and exposed-component edge
recovery versus unseen-component generalization. The ranker remains secondary.
Neither neighborhood comparisons nor exact target exclusion prove memorization
or a biological mechanism. Figure 3 uncertainty is descriptive across-split SD;
Figure 5 retains actual edge counts and the nominal 50% / actual 31.0% caveat.

## Native compilation and visual checks

Main and supplementary PDFs use A4, 11 pt, 1.5 spacing and 25 mm margins; page
numbers remain. Both omit author/affiliation/date/line-number material,
administrative placeholders and the project-assistance account. PDF Author
metadata is empty. Both one-page review notes also have empty Author metadata.
Native compilation has no missing-character, undefined-reference/citation or
overfull-box diagnostic. Fonts are embedded and no Type 3 fonts are present.

All 40 final pages were rendered at 144 dpi and inspected, including enlarged
mathematical and dense figure/table pages. No clipping, overlap or missing
symbols were found. PLACEMENT_AUDIT.md records the new page mapping. The
original build profile is checked separately in build_regression.json.

## Limits of this audit

This is scientific consistency and document quality control, not new external
validation or author approval. Models were not retrained, bootstrap intervals
were not regenerated and the scientific release was not retagged. Package
integrity and frozen-source restoration are recorded in ATTACHMENT_AUDIT.md
and package_verification.json. Author-owned declarations, licensing and the
planned archive remain decisions for the actual submission version, recorded
in SUBMISSION_DECISIONS.md. No Zenodo DOI or submission status is fabricated.
