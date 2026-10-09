#!/usr/bin/env python3
"""Verify final archive hashes and restore the exact frozen execution sources."""
import gzip
import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from reproduce import frozen_sources


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def vector_hash(value):return hashlib.sha256(json.dumps(value,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()


def main():
    manifest=json.load(open('output/bmc_revision/release_manifest.json'))
    records=[]
    for r in manifest['attachments']+[manifest['editable_source'],manifest['journal_figures']]:
        path=Path(r['path'])
        assert sha(path)==r['sha256']
        if 'additional_file_' in path.name:assert path.stat().st_size<20_000_000
        with zipfile.ZipFile(path) as z:
            assert z.testzip() is None
            members=json.loads(z.read('MANIFEST.json'))
            for name,m in members.items():
                p=Path(name);assert not p.is_absolute() and '..' not in p.parts
                expected=m if isinstance(m,str) else m['sha256']
                assert hashlib.sha256(z.read(name)).hexdigest()==expected
                # Entries drawn from real local files must describe the current
                # saved artifact, not a stale packaging run.
                if isinstance(m,dict) and 'source' in m:assert sha(m['source'])==expected
        records.append({'path':str(path),'sha256':sha(path),'members':len(members),'verified':True})

    baseline_queries=0
    with zipfile.ZipFile('output/bmc_revision/additional_file_4.zip') as z:
        for name in z.namelist():
            if not name.startswith('nearest_input_queries/') or name.endswith('_summary.json'):continue
            c=json.loads(z.read(name));assert sha(c['source'])==c['raw_rows_sha256']
            raw=json.load(gzip.open(c['source'],'rt'))
            for direction,rows in raw.items():
                compact=c['directions'][direction];assert len(compact)==len(rows)
                for row,copy in zip(rows,compact):
                    baseline_queries+=1
                    assert {k:v for k,v in row.items() if k!='retrieval'}=={k:v for k,v in copy.items() if k!='retrieval'}
                    for pool,v in row.get('retrieval',{}).items():
                        out=copy['retrieval'][pool]
                        assert out['metrics']=={k:m for k,m in v['metrics'].items() if k!='ranked_candidates'}
                        assert out['candidate_count']==len(v['candidates'])
                        for key,value in [('candidates',v['candidates']),('scores',v['scores']),('ranked_candidates',v['metrics']['ranked_candidates'])]:
                            assert out[key+'_sha256_canonical_json']==vector_hash(value)

    restored=0;files=0
    Path('tmp').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='bmc_snapshot_verify_',dir='tmp') as td:
        folder=Path(td)
        with zipfile.ZipFile('output/bmc_revision/additional_file_6.zip') as z:
            for name in z.namelist():
                p=Path(name);assert not p.is_absolute() and '..' not in p.parts
            z.extractall(folder)
        subprocess.run([sys.executable,str(folder/'materialize_snapshots.py')],check=True)
        index=json.loads((folder/'SNAPSHOT_INDEX.json').read_text())
        for name,r in index.items():
            restored+=1
            for path,h in r['files_sha256'].items():
                assert sha(folder/'restored_snapshots'/name/path)==h;files+=1
        public_snapshots=frozen_sources(folder/'current_source/reproducibility/frozen_source.zip')
    result={'passed':True,'archives':records,'baseline_queries_verified':baseline_queries,
            'restored_snapshots':restored,'restored_files_verified':files,
            'public_scientific_release_snapshots_verified':public_snapshots,
            'scientific_base_public':True,'persistent_archive_doi':None,
            'author_review_complete':False,'author_items_pending':True}
    Path('output/bmc_revision/package_verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='archives'}))

if __name__=='__main__':main()
