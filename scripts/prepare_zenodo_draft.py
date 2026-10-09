#!/usr/bin/env python3
"""Prepare a checksummed local Zenodo draft from a clean commit; never upload."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--initializations',required=True,type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'output/zenodo_draft')
    args=parser.parse_args()
    def git(*items):
        return subprocess.check_output(['git',*items],cwd=ROOT)
    if git('status','--porcelain'):
        raise ValueError('Commit intended changes and use a clean working tree before archiving')
    commit=git('rev-parse','HEAD').decode().strip()
    output=args.output.resolve()
    if output.exists():raise FileExistsError(output)
    release=json.loads((ROOT/'reproducibility/release.json').read_text())
    expected=release['initializations']
    initializations=args.initializations.resolve()
    if initializations.stat().st_size!=expected['bytes'] or digest(initializations)!=expected['sha256']:
        raise ValueError('Initialization asset differs from the immutable scientific release')
    output.mkdir(parents=True)
    prefix='GDTCR-'+commit[:12]+'/'
    source=output/('GDTCR-source-data-'+commit[:12]+'.zip')
    subprocess.run(['git','archive','--format=zip','--prefix='+prefix,'--output='+str(source),commit],cwd=ROOT,check=True)
    with zipfile.ZipFile(source) as archive:
        if archive.testzip() is not None:raise ValueError('Source archive CRC check failed')
        inventory=json.loads(archive.read(prefix+'reproducibility/MANIFEST.json'))
        payload={n[len(prefix):] for n in archive.namelist() if not n.endswith('/')}
        if payload!=set(inventory['files'])|{'reproducibility/MANIFEST.json'}:
            raise ValueError('Git archive members differ from the tracked inventory')
        for name,record in inventory['files'].items():
            h=hashlib.sha256();size=0
            with archive.open(prefix+name) as stream:
                for block in iter(lambda:stream.read(1024*1024),b''):
                    size+=len(block);h.update(block)
            if h.hexdigest()!=record['sha256'] or size!=record['bytes']:
                raise ValueError('Source archive inventory mismatch: '+name)
    shutil.copyfile(initializations,output/expected['filename'])
    files=[source,output/expected['filename']]
    review_record=ROOT/'output/bmc_revision/local_review_manifest.json'
    if review_record.is_file():
        r=json.loads(review_record.read_text());review=ROOT/r['path']
        if digest(review)!=r['sha256']:raise ValueError('Review bundle checksum mismatch')
        with zipfile.ZipFile(review) as archive:
            members=json.loads(archive.read('MANIFEST.json'))
            for name,record in members.items():
                if not (ROOT/name).is_file() or digest(ROOT/name)!=record['sha256']:
                    raise ValueError('Review bundle has a stale source: '+name)
        shutil.copyfile(review,output/review.name);files.append(output/review.name)
    draft=json.loads((ROOT/'paper/final_submission/zenodo/metadata_draft.json').read_text())
    draft['source_commit']=commit
    draft['proposed_metadata']['related_identifiers'].append({
        'identifier':'https://github.com/'+release['repository']+'/tree/'+commit,
        'relation':'isIdenticalTo','scheme':'url'})
    metadata=output/'metadata_draft.json'
    metadata.write_text(json.dumps(draft,indent=2)+'\n');files.append(metadata)
    shutil.copyfile(ROOT/'paper/final_submission/zenodo/README.md',output/'README.md')
    files.append(output/'README.md')
    records={p.name:{'bytes':p.stat().st_size,'sha256':digest(p)} for p in files}
    (output/'archive_inventory.json').write_text(json.dumps({
        'status':'prepared_locally_not_uploaded','source_commit':commit,'source_members_verified':len(inventory['files']),
        'author_review_complete':False,'license_confirmed':False,'doi':None,
        'primary_evidence_sha256':release['primary_evidence_sha256'],'files':records},indent=2)+'\n')
    records['archive_inventory.json']={'sha256':digest(output/'archive_inventory.json')}
    (output/'SHA256SUMS').write_text(''.join(r['sha256']+'  '+name+'\n' for name,r in sorted(records.items())))
    print(json.dumps({'status':'prepared_locally_not_uploaded','commit':commit,'output':str(output),
                      'source_members_verified':len(inventory['files']),'files':len(files),'doi':None}))


if __name__=='__main__':main()
