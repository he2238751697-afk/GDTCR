#!/usr/bin/env python3
"""Build six bounded local release-candidate attachments, with content hashes."""
import gzip,hashlib,json,zipfile
from pathlib import Path

ROOT=Path.cwd();OUT=Path('output/bmc_revision')

def digest(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

class Archive:
    def __init__(self,number):
        self.path=OUT/f'additional_file_{number}.zip'
        self.zip=zipfile.ZipFile(self.path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9)
        self.entries={};self.names=set()
    def add(self,path,name=None):
        path=Path(path);name=name or str(path)
        if not path.is_file():raise FileNotFoundError(path)
        if name in self.names:return
        self.names.add(name);self.zip.write(path,name)
        self.entries[name]={'sha256':digest(path),'bytes':path.stat().st_size,'source':str(path)}
    def text(self,name,value):
        data=value.encode();self.zip.writestr(name,data);self.names.add(name)
        self.entries[name]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
    def finish(self):
        self.text('README_RELEASE.txt','BMC author-review attachment, 9 October 2026. The scientific base is public at https://github.com/he2238751697-afk/GDTCR/releases/tag/reproducibility-v1 . The manuscript PDFs are native LaTeX builds. Author review, final declarations, code/weight licenses and a Zenodo archive DOI remain pending. Third-party data retain original source terms. This is not an approved journal submission.\n')
        self.zip.writestr('MANIFEST.json',json.dumps(self.entries,indent=2,sort_keys=True)+'\n');self.zip.close()
        if self.path.stat().st_size>=20_000_000:raise ValueError(f'Additional file exceeds 20 MB: {self.path}')
        with zipfile.ZipFile(self.path) as z:
            assert z.testzip() is None
            for name,record in self.entries.items():assert hashlib.sha256(z.read(name)).hexdigest()==record['sha256']
        return {'path':str(self.path),'bytes':self.path.stat().st_size,'sha256':digest(self.path),'members':len(self.entries),'verified':True}

def main():
    revision=json.load(open('paper/results/bmc/revision_summary.json'))
    assert revision['complete'] and revision['test_outcome_audit_passed'] and revision['primary_evidence_unchanged']
    visual=json.load(open('paper/final_submission/visual_audit.json'))
    assert visual['passed'] and visual['total_pages_inspected']==46
    for document in visual['documents']:
        assert digest(document['source'])==document['source_sha256']
        assert digest(document['pdf'])==document['pdf_sha256']
    OUT.mkdir(parents=True,exist_ok=True);records=[]
    a=Archive(1)
    a.add('output/pdf/additional_file_1_bmc.pdf','additional_file_1.pdf')
    a.add('paper/supplementary_methods_bmc.tex','paper/supplementary_methods_bmc.tex')
    for p in Path('paper/results/bmc/figures').glob('figure_S*'):
        a.add(p)
    records.append(a.finish())
    a=Archive(2)
    for name in ('dataset_composition.tsv','distant_edges.tsv','distant_summary.tsv','primary_source_distance_strata.tsv','source_balanced_descriptive.tsv','test_component_distribution.tsv','primary_component_size_strata.tsv'):
        a.add(Path('paper/results/bmc/tables')/name,'tables/'+name)
    for name in ('data_protocols.tsv','validation_information.tsv','source_event_clusters.tsv'):
        a.add(Path('paper/results/v2/tables')/name,'tables/'+name)
    for p in ['paper/DATA_CARD.md','data/provenance/manifest.json','data/metadata/geo_samples.json','artifacts/completion_v2/data_audit_final.json','artifacts/completion_v2/distance_audit_corrected/summary.json','artifacts/revision_bmc/primary_recheck.json']:
        a.add(p)
    records.append(a.finish())
    a=Archive(3)
    for name in ('training.tsv','pretraining_exposure.tsv','denoising.tsv'):
        a.add(Path('paper/results/v2/tables')/name,'tables/'+name)
    a.add('paper/results/bmc/tables/revision_training.tsv','tables/revision_training.tsv')
    for folder in ('artifacts/completion_v2/generator','artifacts/completion_v2/ranker','artifacts/revision_bmc/generator','artifacts/revision_bmc/ranker'):
        for filename in ('summary.json','run.json','checksums.json'):
            for p in sorted(Path(folder).rglob(filename)):a.add(p)
    a.add('paper/MODEL_CARD.md')
    records.append(a.finish())
    a=Archive(4)
    for p in Path('paper/results/bmc/tables').glob('*.tsv'):a.add(p,'revision_tables/'+p.name)
    for p in Path('paper/results/v2/tables').glob('*.tsv'):a.add(p,'original_tables/'+p.name)
    a.add('paper/results/bmc/revision_summary.json')
    for p in Path('artifacts/revision_bmc/transfer').glob('*/rows.json.gz'):
        raw=json.load(gzip.open(p,'rt'));compact={}
        vector_hash=lambda value:hashlib.sha256(json.dumps(value,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
        for direction,rows in raw.items():
            compact[direction]=[]
            for row in rows:
                entry={k:v for k,v in row.items() if k!='retrieval'}
                entry['retrieval']={}
                for pool,v in row.get('retrieval',{}).items():
                    entry['retrieval'][pool]={
                        'metrics':{k:m for k,m in v['metrics'].items() if k!='ranked_candidates'},
                        'candidate_count':len(v['candidates']),
                        'candidates_sha256_canonical_json':vector_hash(v['candidates']),
                        'scores_sha256_canonical_json':vector_hash(v['scores']),
                        'ranked_candidates_sha256_canonical_json':vector_hash(v['metrics']['ranked_candidates'])}
                compact[direction].append(entry)
        a.text('nearest_input_queries/'+p.parent.name+'.json',json.dumps({
            'source':str(p),'raw_rows_sha256':digest(p),
            'representation':'All queries, positives, clusters, direct-transfer candidates/neighbors/distances and scalar retrieval metrics retained. Repeated retrieval candidate/ranking/score arrays are represented by hashes; frozen pools are in Additional file 5. Recompute deterministic scores with evaluate_transfer_bmc.py. Original full rows remain in the local artifact tree.',
            'hash_serialization':'UTF-8 json.dumps(value,separators=(comma,colon),ensure_ascii=True)',
            'directions':compact},sort_keys=True,indent=2)+'\n')
        a.add(p.parent/'summary.json','nearest_input_queries/'+p.parent.name+'_summary.json')
    a.add('paper/SUPPLEMENT_INDEX.md')
    a.add('paper/BMC_SUPPLEMENT_INDEX.md')
    records.append(a.finish())
    a=Archive(5)
    for root in ('data/splits/completion_v2','data/splits/revision_bmc','artifacts/completion_v2/pools'):
        for p in sorted(Path(root).rglob('*')):
            if p.is_file():a.add(p)
    candidates={}
    for root in ('artifacts/completion_v2/evaluation','artifacts/revision_bmc/evaluation'):
        for p in sorted(Path(root).rglob('rows.json.gz')):
            candidates[str(p)]={'sha256':digest(p),'bytes':p.stat().st_size}
    a.text('FREE_CANDIDATE_HASHES.json',json.dumps(candidates,indent=2,sort_keys=True)+'\n')
    a.add('artifacts/completion_v2/pool_audit.json')
    records.append(a.finish())
    a=Archive(6)
    for folder in ('src','scripts','slurm','tests','configs'):
        for p in sorted(Path(folder).rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts and p.suffix in ('.py','.json','.sbatch','.sh','.txt','.yml','.yaml','.toml'):a.add(p,'current_source/'+str(p))
    for name in ('README.md','REPRODUCIBILITY.md','THIRD_PARTY_DATA.md','requirements.txt','BMC_Bioinformatics_submission_revision_checklist.md'):
        a.add(name,'current_source/'+name)
    for name in ('release.json','tasks.json','frozen_source.zip'):
        a.add(Path('reproducibility')/name,'current_source/reproducibility/'+name)
    for p in sorted(Path('paper').glob('*.md')):a.add(p)
    for p in ('paper/references_bmc.json','paper/BMC_CLAIM_AUDIT.tsv','paper/BMC_REVISION_LOG.md',
              'artifacts/completion_v2/environment.json','artifacts/revision_bmc/regression.log',
              'artifacts/revision_bmc/submissions.jsonl','artifacts/revision_bmc/scheduler_updates.json',
              'artifacts/revision_bmc/scheduler_migrations.jsonl','artifacts/revision_bmc/slurm_accounting.json'):
        if Path(p).exists():a.add(p)
    for p in Path('paper/reference_metadata/revision_bmc').glob('*'):
        if p.is_file():a.add(p)
    for p in Path('artifacts/revision_bmc/jobs').rglob('*.json'):a.add(p)
    for p in Path('paper/results/bmc').glob('*audit*.json'):a.add(p)
    for p in Path('paper/results/bmc').glob('native_compile*.json'):a.add(p)
    for p in Path('paper/results/bmc').glob('visual*.json'):a.add(p)
    # Current pre-packaging audits; archive-hash reports must not include themselves.
    for name in ('README.md','CHANGES.md','PLACEMENT_AUDIT.md','CONSISTENCY_AUDIT.md',
                 'scientific_freeze.json','native_compile.json','visual_audit.json',
                 'placement_audit.json','crossref_numerical_audit.json'):
        p=Path('paper/final_submission')/name
        if p.is_file():a.add(p)
    # Deduplicate identical frozen files by their content hash. Manifests are
    # sufficient to restore the exact snapshot directories before execution.
    objects={};snapshots={}
    for base in ('artifacts/completion_v2/code','artifacts/revision_bmc/code'):
        for p in sorted(Path(base).glob('*/snapshot.json')):
            m=json.load(open(p));key=p.parent.name
            snapshots[key]={'manifest':str(p),'files_sha256':m['files_sha256'],'original_root':m['root']}
            a.add(p,'frozen_manifests/'+key+'.json')
            for relative,h in m['files_sha256'].items():
                source=p.parent/relative
                if h not in objects:
                    assert digest(source)==h;objects[h]=source;a.add(source,'source_objects/'+h)
    a.text('SNAPSHOT_INDEX.json',json.dumps(snapshots,indent=2,sort_keys=True)+'\n')
    a.text('materialize_snapshots.py',"""import hashlib,json,shutil\nfrom pathlib import Path\nroot=Path(__file__).resolve().parent\nindex=json.loads((root/'SNAPSHOT_INDEX.json').read_text())\nfor name,record in index.items():\n    out=root/'restored_snapshots'/name\n    out.mkdir(parents=True,exist_ok=True)\n    for relative,h in record['files_sha256'].items():\n        path=Path(relative)\n        assert not path.is_absolute() and '..' not in path.parts\n        src=root/'source_objects'/h\n        assert hashlib.sha256(src.read_bytes()).hexdigest()==h\n        dst=out/path;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)\n    shutil.copyfile(root/'frozen_manifests'/(name+'.json'),out/'snapshot.json')\nprint('Restored',len(index),'exact source snapshots; port execution manifest paths separately.')\n""")
    records.append(a.finish())
    main=OUT/'gdtcr_bmc_editable_source.zip'
    members={}
    with zipfile.ZipFile(main,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in [Path('paper/manuscript_bmc.tex'),Path('paper/supplementary_methods_bmc.tex'),*Path('paper/results/bmc/figures').glob('*'),*Path('paper/results/v2/figures').glob('figure_S*')]:
            z.write(p,str(p));members[str(p)]=digest(p)
        z.writestr('MANIFEST.json',json.dumps(members,indent=2)+'\n')
        z.writestr('README.txt','Compile both TeX documents with pdflatex from paper/ so relative figure paths resolve. These sources were natively compiled and every final page inspected. Figure PDF/SVG/PNG assets remain separate. This is an author-review draft: final declarations, licenses and Zenodo DOI remain outstanding. The scientific base is public at https://github.com/he2238751697-afk/GDTCR/releases/tag/reproducibility-v1 .\n')
    with zipfile.ZipFile(main) as z:
        assert z.testzip() is None
        for name,h in members.items():assert hashlib.sha256(z.read(name)).hexdigest()==h
    figures=OUT/'journal_figure_assets.zip';figure_members={}
    with zipfile.ZipFile(figures,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in sorted(Path('paper/results/bmc/figures').glob('*')):
            if p.suffix not in ('.pdf','.svg','.png'):continue
            z.write(p,p.name);figure_members[p.name]={'sha256':digest(p),'bytes':p.stat().st_size,'source':str(p)}
        assert len(figure_members)==27
        z.writestr('MANIFEST.json',json.dumps(figure_members,indent=2)+'\n')
        z.writestr('README.txt','Figures 1-7 and S1-S2 for the 9 October 2026 author-review manuscript. Each figure has a vector PDF, editable SVG and 300 dpi PNG. Upload the appropriate individual files to the journal system after author approval. Captions are in the manuscript and supplementary TeX/PDF, not detached from their readable figures.\n')
    report={'status':'author_review_draft','scientific_base_public':True,
            'repository':'https://github.com/he2238751697-afk/GDTCR',
            'base_release':'reproducibility-v1','persistent_archive_doi':None,
            'author_review_complete':False,'author_items_pending':True,
            'native_compilation_verified':True,
            'revision_evidence_sha256':digest('paper/results/bmc/revision_summary.json'),
            'attachments':records,'editable_source':{'path':str(main),'bytes':main.stat().st_size,'sha256':digest(main),'verified':True},
            'journal_figures':{'path':str(figures),'bytes':figures.stat().st_size,'sha256':digest(figures),'members':len(figure_members)},
            'source_snapshots':len(snapshots),'distinct_source_objects':len(objects)}
    (OUT/'release_manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
