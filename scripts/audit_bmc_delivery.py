#!/usr/bin/env python3
"""Check BMC numerical excerpts, unchanged primary tables and source structure."""
import csv
import hashlib
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path
from render_results_v2 import Evidence,DIRECTIONS,SPLITS


def load(path):return json.load(open(path))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def compact(s):return re.sub(r'\s+','',s)


def main():
    main=Path('paper/manuscript_bmc.tex');text=main.read_text()
    supplement=Path('paper/supplementary_methods_bmc.tex').read_text()
    e=Evidence(load('artifacts/completion_v2/final_evidence/evidence.json'))
    rev=load('paper/results/bmc/revision_summary.json');checks=[]

    def check(name,ok,source):
        if not ok:raise AssertionError(name+' | '+source)
        checks.append({'check':name,'passed':True,'source':source})

    def present(name,fragment,body=text,source='frozen evidence'):
        check(name,compact(fragment) in compact(body),source+'; expected '+fragment)

    check('unchanged primary evidence',sha('artifacts/completion_v2/final_evidence/evidence.json')==
          '5badb3b9b8ead02c57afeb5f578f85f3a5e343bad9714fb7daa08f48342b2f3b','frozen evidence SHA256')
    check('all revision tasks and saved-outcome audit',rev['task_count']==43 and rev['complete'] and rev['test_outcome_audit_passed'],'revision_summary.json')
    check('all Slurm exits successful',load('artifacts/revision_bmc/slurm_accounting.json')['passed'],'sacct COMPLETED, 0:0')

    blocks=re.findall(r'\\begin\{table\}.*?\\end\{table\}',text,re.S)
    check('three main tables',len(blocks)==3,'manuscript TeX')
    for block,name in zip(blocks,('data_table.tex','primary_table.tex','paired_primary_table.tex')):
        old=(Path('paper/results/v2/tables')/name).read_text()
        oldrows=old.split(r'\midrule')[1].split(r'\bottomrule')[0].split(r'\\')
        if name=='paired_primary_table.tex':
            panels=re.findall(r'\\midrule(.*?)\\bottomrule',block,re.S)
            check('paired table has two readable panels',len(panels)==2,'main Table 3')
            decoded=[]
            for panel in panels:
                panel=re.sub(r'\\shortstack\[l\]\{([^{}]*(?:\{\}[^{}]*)*)\}',lambda m:m[1].replace(r'\\',' ').replace('{}',''),panel,flags=re.S)
                decoded.append([re.sub(r'^\[3pt\]','',r.strip()).split('&')
                                for r in panel.split(r'\\') if re.sub(r'^\[3pt\]','',r.strip())])
            for i,row in enumerate(r for r in oldrows if r.strip()):
                cells=row.strip().split('&')
                for section,indices in enumerate(((0,1,2,3),(0,4,5))):
                    check(f'paired table row {i+1} panel {section+1} unchanged',
                          [compact(cells[k]) for k in indices]==[compact(v) for v in decoded[section][i]],
                          'frozen evidence-generated paired table; only presentation changed')
            continue
        newrows=block.split(r'\midrule')[1].split(r'\bottomrule')[0].split(r'\\')
        norm=lambda s:compact(re.sub(r'(?<=\d),(?=\d{3}(?:\D|$))','',s))
        for i,row in enumerate(oldrows):
            if row.strip():check(name+f' row {i+1} unchanged',norm(row) in {norm(r) for r in newrows},'evidence-generated primary table')

    figures=load('paper/results/bmc/figure_manifest.json')
    check('seven main figures',len(figures)==7 and [r['number'] for r in figures]==list(range(1,8)),'figure manifest')
    labels=set(re.findall(r'\\label\{([^}]+)\}',text))
    for ref in re.findall(r'\\ref\{([^}]+)\}',text):check('resolved reference '+ref,ref in labels,'manuscript TeX')
    citations={k for group in re.findall(r'\\cite\{([^}]+)\}',text) for k in group.split(',')}
    bib=set(re.findall(r'\\bibitem\{([^}]+)\}',text))
    verified={r['key']:r for r in load('paper/references_bmc.json')['references']}
    check('all citations resolve and are verified',citations==bib==set(verified),'references_bmc.json')
    for key,record in verified.items():present('DOI '+key,record['doi'],source='verified DOI metadata')
    for f in figures:
        check('figure title/legend lengths '+str(f['number']),len(f['title'].split())<=15 and len(f['caption'].split())<=300,'figure manifest')
        for ext in ('pdf','png','svg'):
            check('figure output '+f['id']+'.'+ext,(Path('paper/results/bmc/figures')/(f['id']+'.'+ext)).is_file(),'saved plot file')
    for i,block in enumerate(blocks,1):
        cap=block.split(r'\caption{',1)[1].split(r'\label',1)[0].rsplit('}',1)[0]
        check(f'table {i} title/legend lengths',len(cap.split('.')[0].split())<=15 and len(cap.split())<=300,'table caption')
    for token in (r'\doublespacing',r'\linenumbers',r'\pagestyle{plain}'):
        present('format '+token,token,source='editable source')
    check('no forced source page breaks',not re.search(r'\\(?:newpage|clearpage|pagebreak)\b',text),'editable source')
    check('no thousands separators in numeric manuscript text',not re.search(r'\d,\d{3}(?:\D|$)',text),'editable source')
    check('no unfinished scientific-result marker',not any(x in text for x in ('fits and their fixed-setting evaluations are in progress','unobserved outcomes','TODO')),'main text')
    check('verified author names and affiliation',
          all(v in text for v in ('Zihan He', 'Jia Meng', 'Academy of Life and Natural Sciences',
                                  "Xi'an Jiaotong-Liverpool University")),
          'author information supplied by the user on 2026-10-09')
    check('unconfirmed declarations remain explicit',text.count('Pending author confirmation.')>=4,
          'author review and declarations deferred by the user')
    check('public release identified without an invented DOI or license',
          all(v in text for v in ('https://github.com/he2238751697-afk/GDTCR',
                                  'fcf153c76d8eeac358d1a26da3df470eb4118992',
                                  'no archive DOI has been issued', 'licenses remain unselected')),
          'verified GitHub reproducibility-v1 release and user-confirmed pending Zenodo/licensing')

    # Aggregate NLL and recovery values are computed from the frozen runs.
    for condition in ('paired','constant','random','shuffled'):
        vals=e.split_means(condition,'free','equal_direction_macro','query_mean_nll')
        present('primary NLL mean/SD '+condition,f'{statistics.mean(vals):.3f}\\pm{statistics.stdev(vals):.3f}')
    for metric in ('coverage','likelihood|hit_at_5','ranker|hit_at_5','fused|hit_at_5'):
        vals=[100*v for v in e.split_means('paired','free','equal_direction_macro',metric)]
        # Table values place \pm in its own math span; strip dollar signs.
        present('primary conditional mean/SD '+metric,f'{statistics.mean(vals):.2f} \\pm {statistics.stdev(vals):.2f}',text.replace('$',''))

    # Reverse the saved prior-minus-conditional contrast, swapping interval ends.
    primary_contrasts=[]
    for row in csv.DictReader(open('paper/results/v2/tables/paired_endpoints.tsv'),delimiter='\t'):
        if (row['mode']=='free' and row['direction']=='equal_direction_macro'
            and row['protocol'] in {f'split_seed{s}' for s in SPLITS}
            and row['comparison'].endswith('/constant/versus_primary')
            and row['metric']=='64/allow_training_targets|likelihood|hit_at_5'):
            estimate,lower,upper=(-100*float(row[k]) if float(row[k]) else 0.0
                                  for k in ('estimate','upper','lower'))
            primary_contrasts.append((estimate,lower,upper))
            check('primary Hit@5 interval includes zero '+row['comparison']+'/'+row['seed_index'],
                  lower<=0<=upper,'saved paired component-bootstrap contrast')
            if estimate:
                present('primary Hit@5 paired interval '+row['comparison'],
                        f'[{lower:.2f},{upper:.2f}]')
    check('six saved primary conditional/prior Hit@5 contrasts',len(primary_contrasts)==6,
          'paired_endpoints.tsv')
    check('four zero-event primary contrasts',
          sum(all(v==0 for v in item) for item in primary_contrasts)==4,'paired_endpoints.tsv')
    present('primary average Hit@5 difference',
            f'{statistics.mean(v[0] for v in primary_contrasts):.2f} percentage points')

    # New test counts and selected MRR must appear in the stated diagnostic.
    for protocol in ('unseen_gamma_repaired','giant_edge_holdout'):
        for condition in ('paired','constant','random','shuffled'):
            for seed in (0,1):
                run=rev['runs'][f'{protocol}/{condition}/seed-{seed}']
                for direction,data in run['directions'].items():
                    item=data['metrics']['likelihood_hit_at_5']
                    present(f'{protocol}/{condition}/{seed}/{direction} likelihood events',f"{item['events']}/{item['denominator']}",source='revision_metrics.tsv')
                    if condition=='paired':
                        for metric in ('coverage','ranker_hit_at_5'):
                            item=data['metrics'][metric]
                            present(f'{protocol}/{seed}/{direction} {metric} events',f"{item['events']}/{item['denominator']}",source='revision_metrics.tsv')
                        if protocol=='giant_edge_holdout':
                            present(f'giant percentage {seed}/{direction}',f"{data['metrics']['likelihood_hit_at_5']['estimate']*100:.2f}\\%")
        if protocol=='giant_edge_holdout':
            check('no inferential giant interval',all('lower' not in m for k,r in rev['runs'].items() if k.startswith(protocol) for d in r['directions'].values() for m in d['metrics'].values()),'revision summary')
    for t in rev['training']:
        if t['stage']=='ranker' and t['protocol']=='unseen_gamma_repaired':
            present('repaired ranker selection MRR '+str(t['seed']),f"{t['selection_value']:.4f}")
    for c in rev['comparisons']:
        if c['protocol']=='unseen_gamma_repaired' and c['contrast']=='conditional_minus_constant' and c['metric']=='likelihood_hit_at_5':
            present('repaired paired interval '+str(c['seed']),f"[{100*c['lower']:.2f},{100*c['upper']:.2f}]")

    def rate_pair(name,direction,method='likelihood|hit_at_5'):
        return '/'.join(f"{100*e.estimate(name,s,'free',direction,method):.2f}\\%" for s in (0,1))
    for protocol,directions in [('unseen_input_delta_to_gamma',('delta_to_gamma',)),
        ('seen_input_gamma_to_delta',('gamma_to_delta',)),('seen_input_delta_to_gamma',('delta_to_gamma',)),
        ('source_holdout',('delta_to_gamma',)),('source_shared',('delta_to_gamma',))]:
        for direction in directions:
            for condition in ('paired','constant'):
                present('original diagnostic '+protocol+'/'+condition,rate_pair(protocol+'/'+condition,direction))
            if protocol.startswith('source_'):
                present('original shuffled '+protocol,rate_pair(protocol+'/shuffled',direction))
                present('original ranker '+protocol,rate_pair(protocol+'/paired',direction,'ranker|hit_at_5'))
    for condition in ('paired','constant'):
        expected=[e.metric('unseen_input_gamma_to_delta/'+condition,s,'free','gamma_to_delta','likelihood|hit_at_5') for s in (0,1)]
        for item in expected:present('preserved original unseen-gamma events',f"{item['events']}/{item['denominator']}",supplement)

    for size in (10,25,50,100):
        for condition in ('pretrained','random'):
            name=f'data_fraction{size}/{condition}' if size<100 else 'split_seed17/'+('paired' if condition=='pretrained' else 'random')
            vals=[statistics.mean(e.estimate(name,s,'free',d,'query_mean_nll') for s in (0,1)) for d in DIRECTIONS]
            if size in (10,50,100):present(f'data efficiency NLL {size}/{condition}','/'.join(f'{v:.3f}' for v in vals))

    # The retrieval prose uses rounded averages and keeps the endpoints distinct.
    for direction in DIRECTIONS:
        for pool,methods in [('random',('likelihood','prior','random')),('full',('likelihood','prior','ranker','difference')),('motif',('likelihood','difference','ranker'))]:
            for method in methods:
                value=statistics.mean(e.estimate(f'split_seed{s}/paired',seed,'pools',direction,pool+'|'+method+'|hit_at_5') for s in SPLITS for seed in (0,1))
                present(f'retrieval {direction}/{pool}/{method}',f'{100*value:.1f}\\%')
    for direction in DIRECTIONS:
        for pool in ('random','full'):
            value=statistics.mean(load(f'artifacts/revision_bmc/transfer/split_seed{s}/summary.json')['directions'][direction]['retrieval/'+pool]['metrics']['hit_at_5']['estimate'] for s in SPLITS)
            present('nearest-input retrieval '+direction+'/'+pool,f'{100*value:.1f}\\%')

    component_groups=defaultdict(list)
    for row in csv.DictReader(open('paper/results/bmc/tables/primary_component_size_strata.tsv'),delimiter='\t'):
        component_groups[row['split_seed'],row['condition'],row['training_seed'],row['direction'],row['metric']].append(row)
    for (split,condition,seed,direction,metric),rows in component_groups.items():
        queries=sum(int(r['queries']) for r in rows)
        value=sum(int(r['queries'])*float(r['estimate']) for r in rows)/queries
        target=e.estimate('split_seed'+split+'/'+condition,(int(seed)-3407)//101,'free',direction,metric)
        check('component-size recomposition '+str((split,condition,seed,direction,metric)),abs(value-target)<1e-12,'post-hoc strata versus unchanged primary query-macro mean')

    for fname in ('gdtcr_bmc_revision','additional_file_1_bmc'):
        record=load('output/pdf/'+fname+'.render.json')
        check(fname+' PDF/source hashes',record['pdf_sha256']==sha('output/pdf/'+fname+'.pdf') and record['source_sha256']==sha(record['source']),'renderer manifest')
        plain=Path('output/pdf/'+fname+'.txt').read_text()
        check(fname+' no broken glyph/reference tokens',not any(x in plain for x in ('\ufffd','??','PERCENTTOKEN','XMLTOKEN','AMPERSANDTOKEN')),'extracted PDF text')
    result={'passed':True,'checks':len(checks),'source':str(main),'source_sha256':sha(main),
       'primary_evidence_sha256':sha('artifacts/completion_v2/final_evidence/evidence.json'),
       'revision_evidence_sha256':sha('paper/results/bmc/revision_summary.json'),
       'scope':'Deterministic source/figure/reference/table checks and key numerical excerpts; sentence interpretation is documented separately',
       'native_compilation_verified':all(load('output/pdf/'+n+'.render.json')['native_compilation_verified']
                                        for n in ('gdtcr_bmc_revision','additional_file_1_bmc')),
       'author_items_pending':True,'records':checks}
    Path('paper/results/bmc/numerical_audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='records'}))

if __name__=='__main__':main()
