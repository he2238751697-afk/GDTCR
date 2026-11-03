# Reference and journal-source checks

Checked 3 November 2026. The draft contains 18 references, numbered by first
citation. Every DOI resolves to saved Crossref metadata in source_checks/;
references.json records the metadata hashes and bibliography fields. The new
draft audit checks all 18 keys, DOI strings, years, volumes/article identifiers
and preprint labels. Titles/authors and claim fit were also read during editing.

The original 16 records were refreshed. TCRdb 2.0 has a 2026 issue year and
2025 online publication; the IEDB 2024 update has a 2025 issue year and 2024
online publication. The Landry record contains differing print/online dates;
the bibliography retains the 2025 volume-5 article citation. These date-field
distinctions do not alter scientific results.

Two narrowly relevant references were added:

- Woods et al., Science Advances, DOI 10.1126/sciadv.aef5674: context for the
  difference between MHC:peptide:TCR specificity prediction and gamma/delta
  partner completion. No accuracy number or transferable baseline is imported.
- Maire and Zheng, bioRxiv preprint, DOI 10.64898/2026.10.13.758726: context for
  the limits of neighbor/hubness explanations in a different paired-receptor
  retrieval setting. It is not evidence of this generator's mechanism.

Candidate DOI 10.1038/s43588-026-01073-y was screened but not added: metadata
alone did not establish a sufficiently specific supporting claim. The targeted
update is not a systematic literature review. Europe PMC requests returned 503;
two Crossref update queries succeeded and one returned 429. Those limitations,
query strings and responses are retained in the search records. The two added
sentences are limited to claims supported by the retrieved records/abstracts.

Official scope, article instructions and same-year 2025 impact factors were
checked on seven publisher pages, with URLs, retrieval dates, excerpts and page
hashes retained. BMC Bioinformatics: 4.4; Briefings in Bioinformatics: 7.3;
Bioinformatics: 5.5. These are journal impact factors, not CiteScores. The
one-page journal comparison distinguishes formal requirements from the
study-specific recommendation to broaden comparisons or add an independent
cohort before considering a more demanding submission route. It does not
predict acceptance or assert that additional experiments are mandatory at BMC.
