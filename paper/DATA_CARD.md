# GDTCR data card

Version: completion-v2, 30 September 2026. This card describes the frozen research
benchmark. It is not a clinical data product or a catalogue of validated negative
receptor pairs.

## Contents and provenance

The processed corpus contains 9,068 unique human gamma/delta CDR3 amino-acid
pairs, 3,944 distinct paired gamma CDR3s and 6,989 distinct paired delta CDR3s.
The associated single-chain files contain 194,887 gamma and 1,262,692 delta
sequences before the pretraining filters. The historical filenames
`light_chain.txt` and `heavy_chain.txt` mean gamma and delta, respectively;
gamma/delta TCRs do not have antibody light/heavy chains.

| Paired source | Unique pairs | Observation rows | Resolution retained |
| --- | ---: | ---: | --- |
| GSE180059 | 8,443 | 10,196 | GEO library, library-local barcode, available V/J, contig quality flags |
| Suo et al. 2022, exported through UcTCRdb | 626 | 655 | Study, export row, available genes; original cell/library/donor identities unavailable in this export |
| IEDB export | 1 | 1 | Export row; original study not resolved |

Two pairs appear in both the GSE180059 and Suo exports; source membership is
therefore not mutually exclusive. Observation counts describe the input tables,
not sampling probabilities or population clone frequencies. The dominant study
contains fetal and pediatric thymocytes (six fetal and three pediatric GEO
libraries). The held-out Suo study profiles the developing prenatal immune system.
Neither population supports generalization to all adult peripheral gamma/delta
repertoires without additional data.

Single-chain inputs also include the 17 TCRdb 2.0 project archives and 16 UcTCRdb
exports listed by file and SHA256 in `data/provenance/manifest.json`. A project
archive may contribute no usable gamma/delta sequence. Database names are not
independent biological sources: overlap is tracked at the study and sequence
levels where those fields are available.

## Processing and annotation

`src/clean_data.py` removes whitespace, uppercases residues, rejects empty,
missing and noncanonical amino-acid strings, deduplicates exact sequences/pairs,
and retains the supplied CDR3 boundaries. GEO contigs must be cells, productive,
high confidence and full length; a barcode within a library contributes a pair
only if it has one distinct accepted gamma CDR3 and one distinct accepted delta
CDR3. The other exports do not provide equivalent original cell-quality fields.
Minimum pretraining length is six residues. Decoded evaluation outputs must have
6–35 canonical residues and an observed EOS token. Data cleaning alone is not an
immunological validation of every record.

`scripts/export_provenance.py` reconstructs observation IDs, stable sequence and
pair IDs, library-local barcodes, available V/J annotations and source membership.
Donor identifiers are never imputed from a barcode or library name. The processed
plain sequence and pair tables are used for modeling; richer observation tables
remain available for inspection. Donor independence cannot be established for
all pairs in the assembled benchmark.

## Splits and exposure

The bipartite pairing graph has 3,294 connected components. Its largest component
contains 5,005 edges and is assigned wholly to training in each primary split.
The three frozen seeds (17, 3407, 2026) each contain 7,254/907/907 training,
validation and test edges, with no exact chain crossing partitions. Allocation
balances edge counts; it was not optimized for source or length balance.
Validation is further divided into checkpoint selection, score tuning and
threshold calibration, keeping components intact.

Directional unseen-input protocols allow target-chain overlap; seen-input
protocols withhold edges from sufficiently multivalent source queries. They
answer distinct questions and do not replace the primary test. Strict source
holdout removes the held-out study's traceable chains from supervised training;
source-shared retains public chains. Their supervised training sizes also differ,
so their contrast does not isolate memorization causally.
The common source test contains 626 edges in 90 components; its largest component
contains 529 edges and 323 of the 419 delta queries. Component dependence cannot
be replaced by an iid interpretation of all test queries.

The unseen-gamma checkpoint-selection subset contains only one input query and
581 recorded delta partners, with no ranking distractors in its full target pool.
Its ranker MRR is therefore uninformative for checkpoint selection. This protocol
is retained as a restricted diagnostic, not an adequate validation design for a
future unseen-gamma predictor.

All paired chains are excluded from the main pretraining pool, including those
in validation and test. Main pretraining training/validation counts are
187,092/3,818 gamma and 1,230,589/25,114 delta sequences. The source-excluded
pool has 186,949/3,815 gamma and 1,230,167/25,106 delta sequences. Both source
protocols use that filtered pool. Exact exclusion is not homology exclusion.

The distance audit measures complete CDR3, interior (excluding the first and
last three residues), and terminal (first plus last three residues) edit
distances, with raw and length-normalized minima and reference witnesses.
Requiring both chains to have full edit distance at least three from both
supervised and pretraining pools leaves only 5, 5 and 3 test edges in the three
primary splits and none in either source protocol. These are very small or empty
sensitivity strata, not a robust distant-generalization benchmark.

Nested training subsets retain whole components. Nominal 10/25/50/100% settings
contain 725/1,814/2,249/7,254 edges. The nominal 50% subset is only 31.0% of the
full training set because the giant component cannot be split. All three smaller
subsets consist exclusively of singleton components. Thus this curve
also changes component composition; it is not a clean sample-size-only experiment.

## Intended use, limitations and availability

Use this benchmark to measure recovery of recorded partners from one CDR3 and to
inspect the roles of sequence priors, target overlap and candidate ranking.
Unrecorded cross-combinations are constructed distractors, not experimentally
verified biological negatives. Generated partners and ranker scores do not
establish expression, antigen recognition, affinity, safety or therapeutic value.
No patient-level decision-making use has been validated.

Raw data are obtained from the original repositories: GEO GSE180059; the Suo
study (DOI 10.1126/science.abo0510, ArrayExpress/BioStudies E-MTAB-11388) through
the preserved UcTCRdb export; TCRdb 2.0 project archives; and the preserved IEDB
receptor export. Frozen filenames and hashes are retained so changes in upstream
exports can be detected. A fresh Git checkout does not include the ignored raw
data or model artifacts. See `REPRODUCIBILITY.md` and `LICENSE_AND_ACCESS.md` for
reconstruction and the limits of the currently documented permissions.

Authoritative local audits: `artifacts/completion_v2/data_audit_final.json` and
`artifacts/completion_v2/distance_audit_corrected/summary.json`. Earlier failed or
superseded audit records are retained and excluded from scientific evidence.
