# Changes for author review, 9 October 2026

Baseline: public release reproducibility-v1, commit
fcf153c76d8eeac358d1a26da3df470eb4118992. Work is isolated on
codex/bmc-submission-ready; the original dirty working tree is preserved.

## Scientific presentation edits

No experiments, architectures, settings, populations, denominators, saved
statistics or conclusions were changed. These edits clarify existing evidence.

| Location and previous problem | Final change and resulting text | Evidence and claim boundary |
| --- | --- | --- |
| Primary Results: events existed, but the primary conditional/prior contrast was dispersed | Added the 0.03 percentage-point mean contrast; the event-bearing delta-to-gamma fits are 2/900 versus 0/900 and 1/906 versus 0/906. Their equal-direction differences are 0.11 [0.00, 0.27] and 0.06 [0.00, 0.17] percentage points; the four remaining contrasts are zero [0, 0] | Frozen primary_events.tsv and paired_endpoints.tsv; reversed the saved prior-minus-conditional contrast and swapped interval ends. No pooling across overlapping fits; all six intervals include zero |
| Methods: the meaning of target-token NLL could be confused with a corpus token average | Added explicit token → partner → query → direction equations and distinguished minibatch optimization, selection, query-macro reporting and separately reported token-weighted NLL | model.py make_batch; training.py sequence_mean_nll/token_loss; train_generator.py query_validation_metrics; evaluate_free_v2.py; analyze_run_v2.py; render_results_v2.py |
| Background and ranker Methods: contribution hierarchy could be ambiguous | Described ranking as a secondary evaluation of ordering the generator's candidates | No change to ranker training, candidates, comparisons or negative result |
| Figure 3: SD label could be read as inferential uncertainty | “Across-split descriptive SD, not confidence intervals” appears in the graphic, caption and Methods | Seeds averaged within each of three splits, sample SD across split means; unchanged values |
| Figure 4: diagnostic nature needed emphasis | “Diagnostic ranking in truth-containing fixed candidate pools” | Recorded positives are injected; this is not free generation |
| Figure 5: training-size and composition were confounded | “Training-size and graph-composition sensitivity”; visible actual counts 725/1814/2249/7254; retained nominal 50% versus actual 31.0% | Same nested subsets, fitted values, two-seed ranges and giant-component caveat |
| Discussion: nearest-input similarity needed a bounded interpretation | Explained neighborhood ranking, direct transfer's structural zero under exact target exclusion, and why neither proves memorization or a biological mechanism | Existing transfer/retrieval results; no mechanism or new superiority claim |
| Supplement: revision-log headings interrupted scientific flow | Formal pretraining/negative-sampling, nearest-input/exposure, validation-design and source/component-stratification headings | Historical degenerate unseen-gamma estimates remain explicitly labeled and superseded |

## Formatting edits

- Native pdflatex builds replace ReportLab reading copies; compilation logs and
  source/figure hashes are recorded.
- Figures 1–7 are inserted at the relevant Methods/Results locations, each
  with its caption. Tables 1–3 remain in Results.
- Dense panels were rearranged within the same numbered composite figures;
  graphic text is larger at manuscript width. Figure 7's caption describes
  its new row arrangement. No dense figure was reduced to fit a citation page.
- Table 2's direction arrows are unbreakable and narrow cells are left
  aligned. Table 3 has generator and ordering panels, preserving every cell.
- Supplementary figures use the same frozen plotting calculations with larger
  labels and updated panel placement; historical figure assets remain intact.
- Bibliography entries were reordered by first citation, with unchanged
  verified metadata. Added abbreviation expansions and removed PDF link boxes.
- Vector PDF, editable SVG and 300 dpi PNG assets remain separate. The PDFs
  retain embedded fonts, equation numbering and main-text line/page numbers.

## Author and availability updates

- Added user-supplied Zihan He (first author), Jia Meng (corresponding author)
  and their Academy of Life and Natural Sciences, Xi'an
  Jiaotong-Liverpool University affiliation.
- Explicitly labeled the draft as preceding author review. No review,
  contribution, approval or declaration was inferred.
- Replaced obsolete “repository not established” wording with the verified
  GitHub URL, reproducibility-v1 tag, commit, raw-export inventory,
  initialization release asset and reproduction instructions.
- Updated the AI-use disclosure to identify OpenAI Codex and the outstanding
  human verification. Neither AI authorship nor completed author review is claimed.
- Prepared local Zenodo metadata and archive instructions without assigning
  an unconfirmed license or inventing/reserving a DOI.

## Outstanding items

The correspondence email, complete author list, contributions, funding,
conflicts, ethics/consent, acknowledgements, author review/approval, code/weight
licenses and actual Zenodo deposit remain unresolved or explicitly deferred.
Third-party database/export terms and one IEDB row's study provenance retain
their existing limitations. See ../BMC_AUTHOR_ITEMS.md.
