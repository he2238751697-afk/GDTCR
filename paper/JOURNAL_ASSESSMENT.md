# Journal scope and manuscript preparation

Decision status: final.

Completed evidence: `artifacts/completion_v2/final_evidence/evidence.json`, SHA256
`5badb3b9b8ead02c57afeb5f578f85f3a5e343bad9714fb7daa08f48342b2f3b`.
All 557 effective tasks, 193 run/baseline reports and 552 paired comparisons are
complete. The final anonymous reading-copy PDF contains 23 visually inspected
pages, six main figures, two supplementary figures and three generated tables.

Assessment date: 30 September 2026. This is a scope and format decision for the
anonymous scientific manuscript, not a submission or acceptance claim.

## Recommended scope

The appropriate contribution is a controlled computational benchmark of recorded
human gamma/delta CDR3 partner recovery. The study combines explicit exposure
protocols, matched target-prior and initialization controls, fixed-pool versus
free-generation endpoints, paired cluster uncertainty and an auditable task
graph. It should not be presented as a new validated receptor-design platform,
a demonstration of biological incompatibility, or a proof that partner prediction
is intrinsically impossible.

The primary exact-chain-disjoint results favor pretraining and conditioning in
token likelihood, but free top-five recovery remains sparse and the independent
ranker does not establish a reproducible primary gain. Higher delta-to-gamma
recovery in source and target-exposed tasks must also be reported: source-shared
conditional recovery is approximately 44--47%, while its constant-source control
is already approximately 43%. Test events are concentrated in a large component.
This mixture of positive likelihood results, weak primary recovery and exposure
sensitivity supports an evaluation paper with explicit limitations.

## First choice: BMC Bioinformatics, research article

The journal's [aims and scope](https://link.springer.com/journal/12859/aims-and-scope)
include biological sequence analysis, computational models, machine learning and
statistical methodology, with scientific validity central to assessment. That
scope fits this benchmark better than a claim of a major generative-method advance.

The checked [research-article instructions](https://link.springer.com/journal/12859/submission-guidelines/research-article)
require an abstract of at most 350 words with Background, Results and Conclusions,
three to ten keywords, the required Declarations sections and disclosure of LLM
assistance in Methods. The manuscript uses that abstract structure, five keywords,
complete declaration headings and a Methods disclosure. It contains six main
figures, two supplementary figures, three generated main tables and fourteen
verified references. The anonymous version preserves the user's requested absence
of author identities; it does not assert that the journal requires anonymous review.

The manuscript's strongest basis is methodological control and transparent
evaluation. Its limitations remain a small and source-concentrated paired corpus,
incomplete donor/context metadata, sparse distant pairs, one uninformative
directional validation role and limited evidence for ranking benefit. Stronger
biological or externally generalizable claims would require new evidence.

## Alternative: Bioinformatics Advances, research article

This is a secondary option for a shorter computational benchmarking paper.
The checked [author guidelines](https://academic.oup.com/bioinformaticsadvances/pages/author-guidelines)
specify up to eight formatted pages, an abstract of at most 200 words, up to five
keywords, fifty references and six main figures/six tables. The present BMC-style
manuscript would require shortening and journal-specific formatting, especially
its abstract and detailed methods. The reading-copy page count is not a claim
about fit in the journal's typeset template. AI use must also be disclosed in a
cover letter if this option is chosen.

Bioinformatics, PLOS Computational Biology and Briefings in Bioinformatics are
not prioritized for the current version: its evidence is centered on a bounded
benchmark, with no prospective donor-independent cohort, functional validation
or consistent primary improvement from the proposed ranker. This ranking concerns
the current contribution, not a prediction of editorial decisions.

## Administrative boundary

The anonymous scientific manuscript can be delivered locally. Before actual
submission, the authors must confirm identities and contributions, funding,
competing interests, the secondary-use ethics determination and any necessary
consent statement. Public data/code access and source-specific redistribution
rights must also be resolved by the rights holders. No public repository DOI,
license, author attestation or actual journal submission is invented here.

The official requirements were checked on 30 September 2026; public excerpts and
page hashes are preserved in `reference_metadata/journal_guidelines_v2.json`.
Private HTML with proxy metadata is excluded from anonymous materials.
