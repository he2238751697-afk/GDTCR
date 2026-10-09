# Zenodo archive draft

The user selected Zenodo and will configure authentication later. This directory
contains reviewable metadata, not a published deposit. No record has been
created, no DOI has been reserved, and no license has been inferred.

After the author-review changes are committed, prepare local archive files:

    python scripts/prepare_zenodo_draft.py \
      --initializations /path/to/gdtcr-legacy-initializations.tar.gz

The command verifies a clean Git working tree, exports that exact commit to a
source/data ZIP, verifies its file hashes against the release inventory, copies
the checksum-verified initialization asset, and includes the verified review
bundle when present. It writes draft metadata, SHA256SUMS and an archive
inventory under output/zenodo_draft/. It has no network or upload operation and
does not read credentials. Source archives include all 43 original input exports,
three cleaned inputs, frozen assignments, code snapshots, reference tables and
the manuscript sources/figures/PDFs. Full downstream training output and raw
free-draw arrays remain reconstructable from the fixed task manifests.

Before deposition, the authors must confirm the complete author list,
contributions, correspondence and declarations; review and approve the work;
select code and model-weight licenses; and address outstanding upstream data
terms. Source article licenses do not automatically license database exports.
The proposed metadata deliberately omits a license field and is not an
API-ready publishing request. The supplied author names and affiliation are
recorded without guessing ORCIDs or email addresses.

Configure ZENODO_TOKEN locally when ready; never put it in Git or a chat.
Once the necessary decisions are available, create a draft deposit, review its
actual metadata and files, then publish the approved version. Record the real
version DOI and concept DOI separately, update the manuscript availability
statement and repository, and rebuild/recheck the final PDFs and archives.
The current GitHub release remains independently accessible:
https://github.com/he2238751697-afk/GDTCR/releases/tag/reproducibility-v1 .
