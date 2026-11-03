# Attachment integrity audit

All six numbered archives were reopened and every member hash checked.
Each is below 20,000,000 bytes. Current source-backed members were also
checked against the working tree. Frozen execution code was restored
and checked without fitting or evaluating a model.

| File | Size (bytes) | Payload members | Description |
| --- | ---: | ---: | --- |
| Additional file 1 | 1192459 | 14 | Supplementary methods, sensitivity analyses, Table S1 and Figures S1-S3. |
| Additional file 2 | 76214 | 18 | Dataset, provenance, source, graph, component-size and sequence-distance audits. |
| Additional file 3 | 284573 | 385 | Training seeds, model settings, checkpoint provenance and actual exposure. |
| Additional file 4 | 7359661 | 56 | Primary and diagnostic query outcomes, events, paired contrasts and sensitivity tables. |
| Additional file 5 | 8189514 | 111 | Split assignments, validation roles, fixed pools and free-candidate hash inventory. |
| Additional file 6 | 3898652 | 603 | Current source/configurations/environments and unchanged historical execution snapshots. |

Restored 25 execution snapshots / 2456 files. The immutable public-release
archive also passed verification of 27 snapshots / 2768 restored files.

Additional file 1 was rebuilt for the current supplement and S3. Files
2–5 preserve all scientific tables, run objects, splits and candidates;
only descriptive readmes/indexes changed. File 6 refreshes publication
code and review documentation while retaining frozen execution objects.

package_manifest.json records archive SHA256 values; package_verification.json
records integrity and restoration results. Numbered archives are copied to
attachments/ for Git distribution. Figure and editable-source bundles are
available in output/supervisor_review/package/.

The editable-source archive and Additional file 1 were extracted into fresh
temporary directories and natively compiled. Their manuscript/supplement
text matches the verified reading copies. attachment_audit.json records
archive and reference-PDF hashes for this standalone build check.
