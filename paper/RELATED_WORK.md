# Related-work comparability record

Checked 30 September 2026. Bibliographic identities and the indexed abstracts
below are preserved in `references_v2.json`. This is a scoped comparability
record, not a systematic-review claim or a claim to be the first gamma/delta
pairing method. Full training-cohort overlap, donor splits and negative-label
construction are not inferred from abstracts.

| Work | Verified inputs/task | Why its published result is not a direct GDTCR baseline |
| --- | --- | --- |
| TCRpair, Mösch and Frishman, 2021; DOI 10.1093/bioinformatics/btab573 | Predicts functional alpha/beta pairing in an HLA-A*02:01-specific setting, using CDR3 and additional flanking residues; the abstract reports AUC 0.71. | Different chain family, input information, population and classification endpoint. The abstract does not establish an equivalent gamma/delta, whole-partner free-generation experiment. |
| Milighetti et al., 2026; DOI 10.1093/bioinformatics/btag551 | Analyses intra/inter-chain CDR contacts in TCR crystal structures and sequence constraints in antigen-specific alpha/beta sets; reports partial de novo pairing prediction. | Supports the possibility of conditional sequence constraints in its setting. It neither proves gamma/delta prediction accuracy nor supplies a matched 64-draw CDR3 generation baseline. |
| Observed TCR Space, Raybould et al., 2024; DOI 10.1016/j.celrep.2024.114704 | Full-length paired-chain repository; 1.63 million nonredundant sequences across 50 studies and at least 75 individuals in the abstract. A paired-chain language model supports partner-conditioned residue infilling. | Residue infilling with paired/full-length context differs from generating the complete missing gamma/delta CDR3. Dataset overlap and the proposed transfer protocol would require a separate audit. |
| TCR-BERT, Wu et al., 2021 preprint; DOI 10.1101/2021.11.18.469186 | Self-supervised TCR representations for antigen-binding prediction, clustering and related downstream uses. | Representation learning is relevant to initialization, but the cited abstract does not establish a gamma/delta partner-generation or no-overlap evaluation. Preprint status is retained. |
| TCRBinder, Dong et al., 2026; DOI 10.1371/journal.pcbi.1014396 | Paired alpha/beta-chain, antigen-peptide and HLA-aware binding-specificity prediction. | Antigen recognition has additional conditioning inputs and different outcome labels from recovering a recorded partner given one CDR3. Its AUC/AUPRC values are not compared numerically with generation Hit@5. |
| TCRdesign, Li et al., 2025; DOI 10.1093/bib/bbaf691 | Antigen-conditioned generation of beta-chain CDR3 sequences, alongside an alpha/beta/antigen binding predictor. | It generates beta CDR3 for an antigen-conditioned task; it is not a demonstrated gamma-to-delta or delta-to-gamma partner generator. The in-silico claims in the abstract are not treated as wet-lab validation. |
| Landry and Zhang, 2025; DOI 10.1093/bioadv/vbaf028 | Studies masked-language-model pretraining dynamics for downstream peptide:TCR binding prediction. | Motivates measuring downstream performance independently of reconstruction loss. It does not establish that the same effects occur for gamma/delta pairing. |

The direct experimental controls in GDTCR are deliberately fitted/evaluated on
the same frozen gamma/delta task: matched constant-source and random-initialized
models, shuffled inputs, target-prior and conditional-minus-prior scores,
independent rankers, exact two-chain edit neighbors, shallow length/terminal
features, target frequency and seeded random ordering. Their comparability comes
from shared splits, candidate lists and budgets, not from comparing published
headline numbers across tasks.

Background biology is supported by Adams, Gu and Luoma (2015). Dataset identities
and source populations are checked against GSE180059, Suo et al. (2022), UcTCRdb,
TCRdb 2.0 and IEDB and documented in the data card. The manuscript does not claim
that an antibody or alpha/beta model has been empirically validated on gamma/delta
receptors merely because the modeling architecture could be adapted.
