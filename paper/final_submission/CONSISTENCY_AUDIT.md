# Scientific and cross-reference audit

The final author-review manuscript preserves the frozen scientific results.
No discrepancy between the audited manuscript numbers and saved evidence was
found. No new model fitting or broad architecture change was performed.

- 225 frozen data, configuration, model-code and saved-result files have
  unchanged SHA256 hashes (scientific_freeze.json).
- Primary evidence SHA256 remains
  5badb3b9b8ead02c57afeb5f578f85f3a5e343bad9714fb7daa08f48342b2f3b.
- Diagnostic summary SHA256 remains
  d19a7f3a517058dc230e73b6b10c2bbc19cfdd83c9b0a9a407945804a277ef70.
- The 437-check BMC audit verifies numerical excerpts, all original table cells,
  diagnostic events, paired contrasts and component-stratum recomposition.
- The 418-check final audit independently reconstructs primary NLL, coverage
  and likelihood Hit@5 means and SDs from 34296 saved directional query rows;
  it also verifies references, frozen hashes, assets, PDF bounds and labels.
- All 16 cited DOI records match their cached metadata hashes, year,
  volume and page/article fields. Bibliography numbering follows first citation.
  TCRdb 2.0 retains its 2026 issue year, distinct from the 2025 online date.
  TCR-BERT and the germline-shortcut work remain explicitly labeled preprints.
  The targeted literature/DOI verification was performed on 6 October 2026;
  metadata was rechecked against those saved records on 9 October. A new
  literature search is not claimed.
- Every main/supplementary figure and table reference resolves. Main figures
  and tables appear in numerical order; Additional files are first cited 1–6.
  The attachment inventory separately validates that all six archives exist.
- Native TeX compilation has stabilized references and no missing-glyph,
  overfull-box, undefined-reference or undefined-citation diagnostics. All
  PDF fonts are embedded; none is Type 3. Visual inspection is separate.

The NLL audit follows the actual implementation: make_batch excludes padding
and chain-control prediction, sequence_mean_nll averages residues plus EOS for
each target, positive_query_mean_nll averages partners, directional summaries
average queries, and the reported joint value equally averages directions.
Seed averages precede the sample SD of three split means. Token-weighted NLL
and minibatch optimization loss have different weighting and are described
separately. Selection uses the same query hierarchy on selection data.

The conditional/prior Hit@5 paragraph reverses saved prior-minus-conditional
estimates and interval endpoints. Event counts and denominators are retained
per fitted model. The four zero-event intervals are not population upper bounds,
and repeated fits are not independent biological observations.

Recorded pairing remains distinct from biological function. Retrieval pools
contain positives by construction; free sampling does not. Direct transfer
returns only training targets, whereas nearest-input partner-similarity ranks
a supplied candidate universe. The within-giant diagnostic retains one original
component and has no inferential component-bootstrap interval.

Administrative pending statements are intentional in this pre-review version,
following the user's explicit deferral. They are submission blockers, not
missing scientific results. See ../BMC_AUTHOR_ITEMS.md. Current numerical and
cross-reference evidence is in crossref_numerical_audit.json and
../results/bmc/numerical_audit.json; historical claim interpretations remain in
../BMC_CLAIM_AUDIT.tsv and are supplemented by CHANGES.md.
