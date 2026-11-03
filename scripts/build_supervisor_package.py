#!/usr/bin/env python3
"""Build/verify the supervisor review package without changing scientific data.

Repackaging uses the six cached e7f4fc0 author-review archives, authenticated
against paper/final_submission/release_manifest.json. Those historical ZIPs
are inputs, never overwritten. Current numbered deliverables are also copied
to paper/supervisor_review/attachments/ for versioned distribution.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'paper/supervisor_review'
OUTPUT = ROOT / 'output/supervisor_review/package'
STAMP = (2026, 11, 3, 0, 0, 0)
README = ('GDTCR supervisor-review scientific draft, 3 November 2026. '
          'Read paper/supervisor_review/SUPPLEMENT_INDEX.md for current numbering. '
          'Main figures are 1-6; supplementary figures are S1-S3. '
          'Scientific tables and frozen execution objects retain their verified values. '
          'Historical documents describe earlier versions and are retained for traceability. '
          'This is not an approved journal submission. The scientific base is '
          'https://github.com/he2238751697-afk/GDTCR/tree/reproducibility-v1 . '
          'Third-party materials retain their source terms.\n')
POST_PACKAGE = {'package_manifest.json', 'package_verification.json', 'attachment_audit.json',
                'ATTACHMENT_AUDIT.md', 'DELIVERY_INDEX.md', 'GIT_DELIVERY.md'}

def sha(data): return hashlib.sha256(data).hexdigest()
def file_sha(path): return sha(Path(path).read_bytes())
def relative(path): return str(Path(path).relative_to(ROOT))
def safe(name):
    p=Path(name)
    if p.is_absolute() or '..' in p.parts:raise ValueError('Unsafe archive path: '+name)

def bytes_file(path):
    p=Path(path);data=p.read_bytes()
    return data,{'sha256':sha(data),'bytes':len(data),'source':relative(p)}

def add_file(entries,path,name=None):
    p=Path(path);entries[name or relative(p)]=bytes_file(p)

def add_text(entries,name,text):
    data=text.encode();entries[name]=(data,{'sha256':sha(data),'bytes':len(data)})

def write_archive(path,entries,bounded=False):
    path.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,(data,record) in sorted(entries.items()):
            safe(name);assert record['sha256']==sha(data)
            info=zipfile.ZipInfo(name,STAMP);info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o644<<16;z.writestr(info,data,compresslevel=9)
        info=zipfile.ZipInfo('MANIFEST.json',STAMP);info.compress_type=zipfile.ZIP_DEFLATED
        info.external_attr=0o644<<16
        z.writestr(info,json.dumps({n:r for n,(_,r) in sorted(entries.items())},indent=2)+'\n',compresslevel=9)
    if bounded and path.stat().st_size>=20_000_000:raise ValueError('Attachment exceeds 20 MB')
    return {'path':relative(path),'bytes':path.stat().st_size,'sha256':file_sha(path),'members':len(entries)}

def read_base(directory):
    expected=json.loads((ROOT/'paper/final_submission/release_manifest.json').read_text())['attachments']
    bases={}
    for n,record in enumerate(expected,1):
        p=directory/Path(record['path']).name
        if file_sha(p)!=record['sha256']:raise ValueError('Historical ZIP checksum mismatch: '+str(p))
        entries={}
        with zipfile.ZipFile(p) as z:
            assert z.testzip() is None
            manifest=json.loads(z.read('MANIFEST.json'))
            for name,item in manifest.items():
                safe(name);data=z.read(name);assert sha(data)==item['sha256']
                entries[name]=(data,item)
        bases[n]=entries
    return bases

def current_docs():
    for p in sorted(DOCS.rglob('*')):
        if p.is_file() and 'attachments' not in p.relative_to(DOCS).parts and p.name not in POST_PACKAGE:
            if p.suffix in ('.md','.json','.tex','.tsv'):
                yield p

def verify_archive(record):
    p=ROOT/record['path'];assert file_sha(p)==record['sha256']
    with zipfile.ZipFile(p) as z:
        assert z.testzip() is None
        manifest=json.loads(z.read('MANIFEST.json'))
        assert set(z.namelist())==set(manifest)|{'MANIFEST.json'}
        current_sources=0;unavailable_sources=[]
        for name,r in manifest.items():
            safe(name);assert sha(z.read(name))==r['sha256']
            if 'source' in r:
                src=ROOT/r['source']
                if src.is_file():assert file_sha(src)==r['sha256'];current_sources+=1
                else:unavailable_sources.append(r['source'])
    return {**record,'verified':True,'current_sources_checked':current_sources,'unavailable_source_paths':unavailable_sources}

def verify(manifest):
    from reproduce import frozen_sources
    archives=[verify_archive(r) for r in manifest['attachments']+[manifest['editable_source'],manifest['figure_assets']]]
    for r in manifest['attachments']:assert r['bytes']<20_000_000
    # Restore archived execution code and verify every file; no experiment runs.
    with tempfile.TemporaryDirectory(prefix='gdtcr_snapshot_verify_',dir=OUTPUT.parent) as td:
        folder=Path(td)
        with zipfile.ZipFile(ROOT/manifest['attachments'][5]['path']) as z:
            for name in z.namelist():safe(name)
            z.extractall(folder)
        subprocess.run([sys.executable,str(folder/'materialize_snapshots.py')],check=True)
        index=json.loads((folder/'SNAPSHOT_INDEX.json').read_text());count=0
        for name,r in index.items():
            for path,h in r['files_sha256'].items():
                assert file_sha(folder/'restored_snapshots'/name/path)==h;count+=1
        public=frozen_sources(folder/'current_source/reproducibility/frozen_source.zip')
    report={'passed':True,'archives':archives,'restored_execution_snapshots':len(index),
            'restored_execution_files':count,'public_release_snapshots':public,
            'experiment_execution_performed':False,'persistent_archive_doi':None,
            'scientific_payload_comparison':manifest['scientific_payload_comparison']}
    (DOCS/'package_verification.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

def build(base_dir):
    visual=json.loads((DOCS/'visual_audit.json').read_text())
    audit=json.loads((DOCS/'crossref_numerical_audit.json').read_text())
    assert visual['passed'] and audit['passed'] and audit['frozen_files']==225
    for d in visual['documents']:
        assert file_sha(ROOT/d['source'])==d['source_sha256']
        assert file_sha(ROOT/d['pdf'])==d['pdf_sha256']
    bases=read_base(base_dir);OUTPUT.mkdir(parents=True,exist_ok=True)
    descriptions=(
        'Supplementary methods, sensitivity analyses, Table S1 and Figures S1-S3.',
        'Dataset, provenance, source, graph, component-size and sequence-distance audits.',
        'Training seeds, model settings, checkpoint provenance and actual exposure.',
        'Primary and diagnostic query outcomes, events, paired contrasts and sensitivity tables.',
        'Split assignments, validation roles, fixed pools and free-candidate hash inventory.',
        'Current source/configurations/environments and unchanged historical execution snapshots.')
    records=[];preserved=[]
    for n in range(1,7):
        entries={} if n==1 else dict(bases[n])
        if n==1:
            add_file(entries,DOCS/'GDTCR_supplementary.pdf','additional_file_1.pdf')
            add_file(entries,DOCS/'supplementary.tex')
            for stem in ('figure_S1_pretraining','figure_S2_negative_training','figure_7_budget'):
                for suffix in ('.pdf','.svg','.png'):add_file(entries,ROOT/'paper/results/bmc/figures'/(stem+suffix))
            add_text(entries,'COMPILE.txt','From paper/supervisor_review/ run pdflatex supplementary.tex twice. Original figure_7_budget is Figure S3 in this document.\n')
        if n==4:
            for name in ('paper/SUPPLEMENT_INDEX.md','paper/BMC_SUPPLEMENT_INDEX.md'):
                if name in entries:entries['historical/'+name]=entries.pop(name)
        if n==6:
            # Refresh current publication code while keeping executed snapshots fixed.
            for name in list(entries):
                if name.startswith('current_source/') and 'source' in entries[name][1]:
                    add_file(entries,ROOT/entries[name][1]['source'],name)
            for name in ('build_supervisor_package.py','audit_supervisor_draft.py','review_supervisor_sources.py'):
                add_file(entries,ROOT/'scripts'/name,'current_source/scripts/'+name)
            for p in current_docs():add_file(entries,p)
            add_text(entries,'HISTORICAL_DOCUMENTS.txt','Files under paper/ outside paper/supervisor_review/ and frozen_manifests/ preserve earlier records. They do not describe the current PDF layout or author-review status. Executed source snapshots are unchanged.\n')
        # Descriptive metadata changes are kept separate from scientific payload.
        scientific=[name for name in bases[n] if name!='README_RELEASE.txt' and
                    (n in (2,3,5) or n==4 and name not in ('paper/SUPPLEMENT_INDEX.md','paper/BMC_SUPPLEMENT_INDEX.md') or
                     n==6 and (name.startswith(('source_objects/','frozen_manifests/')) or name in ('SNAPSHOT_INDEX.json','materialize_snapshots.py','current_source/reproducibility/frozen_source.zip')))]
        for name in scientific:assert entries[name][0]==bases[n][name][0],name
        if n>1:preserved.append({'additional_file':n,'unchanged_scientific_members':len(scientific),'all_byte_identical':True})
        add_text(entries,'README_RELEASE.txt',README+'\n'+descriptions[n-1]+'\n')
        add_file(entries,DOCS/'SUPPLEMENT_INDEX.md')
        r=write_archive(OUTPUT/f'additional_file_{n}.zip',entries,True);r['description']=descriptions[n-1];records.append(r)
    source={}
    for name in ('manuscript.tex','supplementary.tex','review_notes.tex','journal_comparison.tex'):add_file(source,DOCS/name)
    figures={};mapping=[]
    for p in sorted((ROOT/'paper/results/bmc/figures').glob('*')):
        if p.suffix not in ('.pdf','.svg','.png'):continue
        add_file(source,p)
        name=p.name.replace('figure_7_budget','figure_S3_sampling')
        add_file(figures,p,name)
        mapping.append({'review_asset':name,'original_asset':relative(p),'sha256':file_sha(p)})
    assert len(mapping)==27
    add_text(source,'README.txt','Compile manuscript.tex and supplementary.tex twice with pdflatex from paper/supervisor_review/. The two optional note sources compile there too. Relative figure paths are preserved.\n')
    source_record=write_archive(OUTPUT/'GDTCR_editable_source.zip',source)
    add_text(figures,'FIGURE_MAP.json',json.dumps(mapping,indent=2)+'\n')
    add_text(figures,'README.txt','Main Figures 1-6; supplementary S1-S3. Each has vector PDF, editable SVG and 300 dpi PNG. Figure S3 is a byte-identical alias of original figure_7_budget. Captions remain in the manuscript/supplement.\n')
    figure_record=write_archive(OUTPUT/'GDTCR_figure_assets.zip',figures)
    manifest={'status':'supervisor_review_draft','baseline_commit':'e7f4fc0cf3bf91542f3ce410efcf15b87d8fa392',
              'scientific_base_release':'reproducibility-v1','branch':'codex/supervisor-review-draft',
              'persistent_archive_doi':None,'attachments':records,'editable_source':source_record,
              'figure_assets':figure_record,'scientific_payload_comparison':preserved}
    (DOCS/'package_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    verification=verify(manifest)
    delivered=DOCS/'attachments';delivered.mkdir(exist_ok=True)
    for r in records+[source_record,figure_record]:
        shutil.copyfile(ROOT/r['path'],delivered/Path(r['path']).name)
    # Readable report generated after archive hashes are known; excluded from AF6
    # to avoid a recursive package/hash dependency.
    lines=['# Attachment integrity audit','',
           'All six numbered archives were reopened and every member hash checked.',
           'Each is below 20,000,000 bytes. Current source-backed members were also',
           'checked against the working tree. Frozen execution code was restored',
           'and checked without fitting or evaluating a model.','',
           '| File | Size (bytes) | Payload members | Description |',
           '| --- | ---: | ---: | --- |']
    for n,r in enumerate(records,1):lines.append(f"| Additional file {n} | {r['bytes']} | {r['members']} | {r['description']} |")
    lines+=['',f"Restored {verification['restored_execution_snapshots']} execution snapshots / {verification['restored_execution_files']} files; public-release snapshot verification: {verification['public_release_snapshots']}.",
            '', 'Additional file 1 was rebuilt for the current supplement and S3. Files',
            '2–5 preserve all scientific tables, run objects, splits and candidates;',
            'only descriptive readmes/indexes changed. File 6 refreshes publication',
            'code and review documentation while retaining frozen execution objects.',
            '', 'package_manifest.json records archive SHA256 values; package_verification.json',
            'records integrity and restoration results. Numbered archives are copied to',
            'attachments/ for Git distribution. Figure and editable-source bundles are',
            'available in output/supervisor_review/package/.']
    (DOCS/'ATTACHMENT_AUDIT.md').write_text('\n'.join(lines)+'\n')
    return manifest

def bundle(manifest):
    entries={}
    for p in sorted(DOCS.rglob('*')):
        if p.is_file() and 'attachments' not in p.relative_to(DOCS).parts:
            add_file(entries,p,'review/'+str(p.relative_to(DOCS)))
    for r in manifest['attachments']+[manifest['editable_source'],manifest['figure_assets']]:
        add_file(entries,ROOT/r['path'],'attachments/'+Path(r['path']).name)
    add_text(entries,'START_HERE.txt','Start with review/GDTCR_supervisor_review.pdf and review/GDTCR_supplementary.pdf. The review guide and journal comparison are each one page. All sources, six Additional files, figure assets and audits are included. This is a supervisor-review draft.\n')
    record=write_archive(OUTPUT/'GDTCR_supervisor_review_bundle.zip',entries)
    record=verify_archive(record)
    (OUTPUT/'bundle_manifest.json').write_text(json.dumps(record,indent=2)+'\n')
    return record

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-package-dir',type=Path)
    parser.add_argument('--verify-only',action='store_true')
    parser.add_argument('--bundle-only',action='store_true')
    args=parser.parse_args()
    if args.verify_only or args.bundle_only:
        manifest=json.loads((DOCS/'package_manifest.json').read_text())
        if args.verify_only:
            # Fresh checkouts contain the versioned numbered ZIPs but may not
            # have output/; copy these byte-verified deliverables into place.
            OUTPUT.mkdir(parents=True,exist_ok=True)
            for r in manifest['attachments']+[manifest['editable_source'],manifest['figure_assets']]:
                p=ROOT/r['path'];src=DOCS/'attachments'/p.name
                if not p.exists() and src.exists():shutil.copyfile(src,p)
            report=verify(manifest)
            print(json.dumps({'passed':report['passed'],'archives':len(report['archives'])}))
        else:print(json.dumps(bundle(manifest),indent=2))
        return
    if not args.base_package_dir:parser.error('Supply --base-package-dir for the verified historical six-archive input set')
    manifest=build(args.base_package_dir.resolve())
    print(json.dumps({'attachments':manifest['attachments'],'bundle':bundle(manifest)},indent=2))

if __name__=='__main__':main()
