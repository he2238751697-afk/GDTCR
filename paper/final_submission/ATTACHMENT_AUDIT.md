# Additional-file audit

All six numbered Additional files cited by the manuscript exist, their contents match the descriptions, and each is below 20,000,000 bytes. Every archived member, archive checksum and current local source was checked. This is an author-review package, with approval, declarations, licenses and Zenodo publication still pending.

| Attachment | Bytes | Payload members | Verified description |
| --- | ---: | ---: | --- |
| Additional file 1 | 663,906 | 9 | Supplementary methods PDF/TeX and Figures S1/S2 |
| Additional file 2 | 74,584 | 17 | Dataset, source, graph, distance and validation audits |
| Additional file 3 | 282,943 | 384 | Training, seeds, checkpoints, run settings and actual exposure |
| Additional file 4 | 7,357,995 | 55 | Primary/diagnostic metrics, events, paired contrasts and query outcomes |
| Additional file 5 | 8,187,860 | 110 | Frozen splits, truth-containing candidate pools and free-draw hashes |
| Additional file 6 | 3,749,007 | 552 | Current code/configs, frozen source objects, environment, task records and audits |

Payload-member counts include README_RELEASE.txt and exclude the embedded MANIFEST.json. Archive hashes are recorded in release_manifest.json and member-level details in attachment_audit.json.

- Additional file 1 contains the exact compiled six-page supplementary PDF, editable TeX and six separate S1/S2 assets.
- Additional file 3 has 378 run/summary/checksum metadata files and no weight blobs; the initialization weights remain in the separately verified public release asset.
- Additional file 4 contains 34,296 primary query rows, 168 primary event rows and 4,016 revision query rows. All 6,980 compact nearest-input baseline queries were matched to the original outputs, including the hashes of omitted repeated full-pool vectors.
- Additional file 5 contains 70 split files, 37 candidate-pool files and 690 hashes identifying free-draw outputs. These hashes do not claim that all raw candidate arrays are embedded.
- Additional file 6 restores 25 completion/revision snapshots (2,456 files) from its object store. It also embeds the public source archive, which additionally includes inherited pretraining snapshots: 27 snapshots and 2,768 files. Both inventories were verified; the counts describe different scopes.
- Historical audit/compiler records are retained for traceability. The current native compilation and page inspection records are under paper/final_submission/, and supersede historical failures.

The separate editable-source archive contains both TeX documents and figure files. journal_figure_assets.zip contains 27 current assets: vector PDF, editable SVG and 300 dpi PNG for Figures 1–7 and S1–S2. The combined review ZIP is a convenient delivery bundle; it is not one of the numbered journal attachments and is not subject to their 20 MB limit.

Verification commands:

    python scripts/build_bmc_revision_package.py
    python scripts/verify_bmc_package.py

Rebuilding these archives needs the completed local scientific artifact tree. A public clone can compile the PDFs directly and reproduce the underlying results using REPRODUCIBILITY.md; a full GPU rerun was not part of this formatting revision.
