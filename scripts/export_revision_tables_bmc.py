#!/usr/bin/env python3
"""Re-export primary events and independently recheck distant-edge membership."""
import csv
import gzip
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from gdtcr.data import read_pairs
from gdtcr.fileio import file_sha256
from render_results_v2 import tsv


def main():
    out = Path('paper/results/bmc/tables');out.mkdir(parents=True,exist_ok=True)
    runs=list(csv.DictReader(open('paper/results/v2/tables/free_runs.tsv'),delimiter='\t'))
    events=[]
    for row in runs:
        if not row['evaluation'].startswith('split_seed') or row['direction']=='equal_direction_macro':continue
        base={k:row[k] for k in ('evaluation','protocol','training_seed','direction','n_queries','n_recorded_edges')}
        for metric in ('coverage','likelihood|hit_at_5','ranker|hit_at_5','fused|hit_at_5'):
            if row.get(metric+'|events')=='':continue
            n,k=int(row[metric+'|denominator']),int(row[metric+'|events'])
            assert abs(k/n-float(row[metric+'|estimate']))<1e-12
            events.append({**base,'metric':metric,'events':k,'denominator':n,'percentage':100*k/n,
                           'cluster_lower':row[metric+'|lower'],'cluster_upper':row[metric+'|upper']})
    tsv(out/'primary_events.tsv',events)
    root=Path('artifacts/completion_v2/distances')
    pretrained={c:{r['query']:r['full'] for r in json.load(gzip.open(root/('pretrain_'+c)/'rows.json.gz','rt'))}
                for c in ('gamma','delta')}
    distant=[];summaries=[]
    for seed in (17,3407,2026):
        name=f'split_seed{seed}'
        supervised={c:{r['query']:r['full'] for r in json.load(gzip.open(root/'supervised'/name/c/'rows.json.gz','rt'))}
                    for c in ('gamma','delta')}
        pairs=read_pairs(Path('data/splits/completion_v2')/name/'test.tsv')
        selected=[]
        for gamma,delta in pairs:
            values={c+'_'+ref:pool[c][seq]['min_raw'] for c,seq in (('gamma',gamma),('delta',delta))
                    for ref,pool in (('supervised',supervised),('pretraining',pretrained))}
            if min(values.values())>=3:
                selected.append((gamma,delta));distant.append({'split_seed':seed,'gamma':gamma,'delta':delta,**values})
        gammas=sorted({g for g,d in pairs})
        summaries.append({'split_seed':seed,'test_edges':len(pairs),'test_gamma_queries':len(gammas),
                          'gamma_one_edit_pretraining':sum(pretrained['gamma'][g]['min_raw']==1 for g in gammas),
                          'gamma_ge3_pretraining':sum(pretrained['gamma'][g]['min_raw']>=3 for g in gammas),
                          'distant_edges':len(selected),'largest_component_assignment':'training'})
    assert [r['distant_edges'] for r in summaries]==[5,5,3]
    tsv(out/'distant_edges.tsv',distant);tsv(out/'distant_summary.tsv',summaries)
    sources=[{'source':'GSE180059','unique_pairs':8443,'percent_of_union':100*8443/9068,'accession':'GSE180059'},
             {'source':'Suo et al. via UcTCRdb','unique_pairs':626,'percent_of_union':100*626/9068,'accession':'E-MTAB-11388'},
             {'source':'IEDB export, original study unresolved','unique_pairs':1,'percent_of_union':100/9068,'accession':'IEDB receptor export'},
             {'source':'Union (two pairs shared by major sources)','unique_pairs':9068,'percent_of_union':100,'accession':''}]
    master=json.load(open('artifacts/completion_v2/data_audit_final.json'))['master']['studies']
    assert sorted(master.values())==[1,626,8443]
    tsv(out/'dataset_composition.tsv',sources)
    audit={'frozen_evidence_sha256':file_sha256('artifacts/completion_v2/final_evidence/evidence.json'),
           'event_rows':len(events),'distant_edges':[r['distant_edges'] for r in summaries],
           'ranker_encoder_correction':{'freeze_encoder':False,'copied_encoder_trainable':True,
               'source':'artifacts/completion_v2/ranker/main/split_seed17/seed-0/run.json'},
           'outputs':{str(p):file_sha256(p) for p in sorted(out.glob('*.tsv'))}}
    Path('artifacts/revision_bmc/primary_recheck.json').write_text(json.dumps(audit,indent=2)+'\n')
    print(json.dumps({'event_rows':len(events),'distant_edges':audit['distant_edges']}))


if __name__=='__main__':main()
