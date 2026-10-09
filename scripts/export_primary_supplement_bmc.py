#!/usr/bin/env python3
"""Compact primary query-level and source/distance-stratum exports without pooling fits."""
import csv,gzip,json,sys
from collections import defaultdict
from pathlib import Path
from render_results_v2 import tsv
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from gdtcr.data import component_groups,read_pairs

def main():
    out=Path('paper/results/bmc/tables');out.mkdir(parents=True,exist_ok=True)
    records=[]
    for split in (17,3407,2026):
        for condition in ('paired','constant','random','shuffled'):
            for seed in (0,1):
                p=Path('artifacts/completion_v2/analysis/runs')/f'split_seed{split}'/condition/f'seed-{seed}'/'free/query_metrics.json.gz'
                data=json.load(gzip.open(p,'rt'))
                for direction,rows in data.items():
                    for row in rows:
                        metrics={k.removeprefix('64/allow_training_targets|'):v for k,v in row['metrics'].items()
                                 if k=='query_mean_nll' or (k.startswith('64/allow_training_targets|') and
                                 ('accepted|' not in k) and any(k.endswith(m) for m in ('coverage','hit_at_5','recall_at_5','mrr')))}
                        records.append({'split_seed':split,'condition':condition,'training_seed':3407+101*seed,
                            'direction':direction,'query':row['source'],'cluster':row['cluster'],
                            'recorded_partners':json.dumps(row['positives']),**metrics})
    tsv(out/'primary_query_results.tsv',records)
    strata=[]
    for r in csv.DictReader(open('artifacts/completion_v2/final_evidence/strata.tsv'),delimiter='\t'):
        if r['evaluation_name'].startswith('split_seed') and r['mode']=='free' and r['weighting']=='query_macro' and r['metric'] in ('coverage','likelihood|hit_at_5','ranker|hit_at_5','query_mean_nll'):
            if r['stratum'].startswith(('source_pretraining_full/','source_supervised_full/','recorded_edge_study/','distant_source_and_target')):
                strata.append(r)
    tsv(out/'primary_source_distance_strata.tsv',strata)
    grouped=defaultdict(list)
    for r in strata:
        if r['stratum'].startswith('recorded_edge_study/'):
            grouped[r['evaluation_name'],r['model_seed_index'],r['direction'],r['metric']].append(r)
    balanced=[]
    for (name,seed,direction,metric),rows in grouped.items():
        nonempty=[r for r in rows if r['estimate'] not in ('','EMPTY') and int(r['n_queries'])>0]
        balanced.append({'evaluation':name,'seed_index':seed,'direction':direction,'metric':metric,
            'equal_source_descriptive_mean':sum(float(r['estimate']) for r in nonempty)/len(nonempty) if nonempty else '',
            'sources_observed':len(nonempty),'source_query_counts':json.dumps({r['stratum']:r['n_queries'] for r in rows}),
            'interpretation':'Post-hoc unweighted mean across nonempty source memberships; overlapping queries and small sources, no pooled inferential interval'})
    tsv(out/'source_balanced_descriptive.tsv',balanced)
    sizes={};distribution=[]
    for split in (17,3407,2026):
        pairs=read_pairs(Path('data/splits/completion_v2')/f'split_seed{split}'/'test.tsv')
        for i,group in enumerate(component_groups(pairs)):
            cluster=f'component_{i:05d}';sizes[split,cluster]=len(group)
            distribution.append({'split_seed':split,'test_component':cluster,'edges':len(group),
                'gamma_queries':len({pairs[j][0] for j in group}),
                'delta_queries':len({pairs[j][1] for j in group})})
    component_groups_by_fit=defaultdict(list)
    for row in records:
        n=sizes[row['split_seed'],row['cluster']]
        label='1' if n==1 else '2-5' if n<=5 else '6-20' if n<=20 else '>20'
        component_groups_by_fit[row['split_seed'],row['condition'],row['training_seed'],row['direction'],label].append(row)
    component_rows=[]
    for (split,condition,seed,direction,label),rows in sorted(component_groups_by_fit.items()):
        for metric in ('query_mean_nll','coverage','likelihood|hit_at_5','ranker|hit_at_5','fused|hit_at_5'):
            if metric not in rows[0]:continue
            component_rows.append({'split_seed':split,'condition':condition,'training_seed':seed,
                'direction':direction,'test_component_edges':label,'metric':metric,
                'queries':len(rows),'components':len({r['cluster'] for r in rows}),
                'estimate':sum(r[metric] for r in rows)/len(rows),
                'events':sum(int(r[metric]) for r in rows) if metric!='query_mean_nll' else '',
                'interpretation':'Post-hoc descriptive size stratum; saved candidates/positives unchanged; no pooled or inferential interval'})
    tsv(out/'test_component_distribution.tsv',distribution)
    tsv(out/'primary_component_size_strata.tsv',component_rows)
    print('Primary query rows',len(records),'stratum rows',len(strata),'source-balanced rows',len(balanced),
          'component-size rows',len(component_rows))
if __name__=='__main__':main()
