#!/usr/bin/env python3
"""Bundle the verified local author-review delivery without publishing it."""
import hashlib
import json
import zipfile
from pathlib import Path


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    root=Path('output/bmc_revision');release=json.loads((root/'release_manifest.json').read_text())
    verified=json.loads((root/'package_verification.json').read_text());assert verified['passed']
    expected={r['path']:r['sha256'] for r in verified['archives']}
    for r in release['attachments']+[release['editable_source'],release['journal_figures']]:assert expected[r['path']]==sha(r['path'])
    paths=[Path(r['path']) for r in release['attachments']+[release['editable_source'],release['journal_figures']]]
    paths+=[root/'release_manifest.json',root/'package_verification.json']
    paths+=[Path('output/pdf')/(name+suffix) for name in ('gdtcr_bmc_revision','additional_file_1_bmc')
            for suffix in ('.pdf','.txt','.render.json')]
    paths+=[Path('paper')/name for name in ('BMC_REVISION_STATUS.md','BMC_REVISION_LOG.md',
        'BMC_CLAIM_AUDIT.tsv','BMC_SUPPLEMENT_INDEX.md','BMC_REPRODUCIBILITY.md','BMC_AUTHOR_ITEMS.md')]
    paths+=sorted(Path('paper/results/bmc').glob('*audit*.json'))
    paths+=sorted(Path('paper/results/bmc').glob('native_compile*.json'))
    paths+=sorted(p for p in Path('paper/final_submission').rglob('*')
                  if p.is_file() and p.suffix in ('.md','.json','.tsv'))
    target=root/'gdtcr_bmc_local_review.zip';members={}
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in paths:
            z.write(p,str(p));members[str(p)]={'sha256':sha(p),'bytes':p.stat().st_size}
        z.writestr('MANIFEST.json',json.dumps(members,indent=2)+'\n')
        z.writestr('README.txt','GDTCR author-review delivery, 9 October 2026. Start with output/pdf/gdtcr_bmc_revision.pdf and paper/final_submission/README.md. Both PDFs are native LaTeX builds with page-inspection audits. Six individual journal attachments are each below 20 MB; this combined review bundle is not an Additional file. The scientific base is public at https://github.com/he2238751697-afk/GDTCR/releases/tag/reproducibility-v1 . Author review, declarations, licenses and Zenodo DOI remain outstanding. No journal submission has been made.\n')
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        for name,r in members.items():assert hashlib.sha256(z.read(name)).hexdigest()==r['sha256']
    record={'path':str(target),'bytes':target.stat().st_size,'sha256':sha(target),'members':len(members),
            'verified':True,'purpose':'local author review; not a journal attachment or public release',
            'author_items_pending':True,'native_compilation_verified':True}
    (root/'local_review_manifest.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record,indent=2))

if __name__=='__main__':main()
