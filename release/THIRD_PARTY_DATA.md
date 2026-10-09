# Original data and attribution

The repository preserves the exact 43 local input files used by GDTCR. Their
SHA256s are in `data/provenance/manifest.json`; `scripts/reproduce.py verify`
checks every one. Do not replace a file with a newer database export and call
it the same benchmark version.

| Source | Original files | Source record |
| --- | ---: | --- |
| GEO GSE180059 | 9 contig-annotation CSV.gz files | [GEO accession](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE180059); [source article](https://doi.org/10.1038/s41467-022-33488-2) |
| TCRdb 2.0 | 17 BioProject ZIP files | [database article](https://doi.org/10.1093/nar/gkaf876); BioProject IDs are retained in filenames |
| UcTCRdb | 16 study CSV.gz exports | [database article](https://doi.org/10.3389/fimmu.2023.1158295) |
| IEDB | 1 receptor-table XLSX export | [IEDB](https://www.iedb.org/); original study for its one paired row remains unresolved |

The paired UcTCRdb study is Suo et al., 2022, accession E-MTAB-11388,
[DOI 10.1126/science.abo0510](https://doi.org/10.1126/science.abo0510). Paired
source membership is not mutually exclusive: two pairs occur in both the GEO
and Suo exports. The 9,068 unique pairs comprise 8,443 GEO pairs, 626 Suo pairs
and one IEDB pair before accounting for that overlap.

The original exports are processed sequence/contig/database tables obtained
upstream. They are **not original FASTQ sequencing reads**. GDTCR uses the
tables, not FASTQs. Original reads, if required for a different analysis, must
be obtained from their study repositories.

Source articles were recorded as CC BY 4.0 for GEO's study, Suo and UcTCRdb, and
CC BY-NC 4.0 for TCRdb 2.0. An article license does not automatically establish
the redistribution terms of every database export. The exact evidence and its
unresolved points remain in `paper/LICENSE_AND_ACCESS.md`. These files retain
their original source terms; GDTCR makes no claim to own or relicense them.

Observation metadata are preserved as provided. Donor identifiers are absent
from the modeled raw tables and are not inferred. Library-local barcodes are
not donor IDs. No claim of donor independence or clinical suitability is made.

The public-repository and data-upload preparation was explicitly requested by
the project user on 9 October 2026. That instruction supersedes the earlier
local-only release plan; it does not create third-party rights or an ethics
determination. Author declarations and a code/weight license remain pending.
