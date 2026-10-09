#!/usr/bin/env python3
"""Refresh current tracked-payload hashes after intentionally staging changes.

Does not stage, commit or publish anything. The immutable scientific release
retains its original manifest; this updates the working branch inventory.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = 'reproducibility/MANIFEST.json'
SECRET = re.compile(rb'-----BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY-----|'
                    rb'\bgh[pousr]_[A-Za-z0-9]{30,}\b|'
                    rb'\bgithub_pat_[A-Za-z0-9_]{40,}\b')
TEXT_SUFFIXES = {'.py','.md','.tex','.bib','.txt','.json','.tsv','.csv',
                 '.sh','.sbatch','.yaml','.yml','.toml'}


def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT)


def main():
    if git('ls-files','--others','--exclude-standard','-z'):
        raise ValueError('Stage intended new files before refreshing the release inventory')
    entries={}
    for raw in sorted(git('ls-files','-z').split(b'\0')):
        if not raw:continue
        name=raw.decode();p=ROOT/name
        if name==INVENTORY:continue
        if not p.is_file() or p.is_symlink():
            raise ValueError('Expected a regular tracked file: '+name)
        size=p.stat().st_size
        if size>=100_000_000:raise ValueError('Git payload exceeds 100 MB: '+name)
        h=hashlib.sha256()
        with p.open('rb') as stream:
            for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
        if p.suffix in TEXT_SUFFIXES and size<10_000_000 and SECRET.search(p.read_bytes()):
            raise ValueError('Credential-like content detected in '+name)
        entries[name]={'bytes':size,'sha256':h.hexdigest()}
    result={'schema_version':1,'files':entries,
            'note':'SHA256/size of every tracked working-branch payload file; excludes this inventory. Original scientific inventory remains at reproducibility-v1.',
            'scientific_base_release':'reproducibility-v1',
            'manuscript_version':'bmc-author-review-2026-10-09'}
    (ROOT/INVENTORY).write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'files':len(entries),'bytes':sum(r['bytes'] for r in entries.values()),
                      'largest_file_bytes':max(r['bytes'] for r in entries.values()),
                      'credential_scan':'passed','symlink_scan':'passed'}))


if __name__=='__main__':main()
