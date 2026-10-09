#!/usr/bin/env python3
"""Require completed revision tasks; audit saved samples and report diagnostic outcomes."""
import argparse,csv,gzip,json,math,sys
from pathlib import Path
import numpy as np
import torch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from gdtcr.data import read_pairs
from gdtcr.fileio import file_sha256
from gdtcr.evaluation import decode_sample_v2
from gdtcr.statistics import cluster_intervals
from evaluate_free_v2 import query_targets,summarize_prefix,summarize_rows
from render_results_v2 import tsv


def load(path):return json.load(open(path))
def gz(path):return json.load(gzip.open(path,'rt'))

def interval(metrics,unit,binary):
    if unit=='single_original_component':
        results={k:{'estimate':float(np.mean([r[k] for r in metrics]))} for k in metrics[0]}
        for k in binary:results[k].update(events=sum(int(r[k]) for r in metrics),denominator=len(metrics))
        return {'n_queries':len(metrics),'n_clusters':1,'metrics':results,
                'interval_unavailable_reason':'One original graph component; point estimates only'}
    return cluster_intervals(metrics,list(map(str,range(len(metrics)))),seed=20261006,binary_metrics=binary)


def verify_decoding(sample,target_chain):
    # Samples store trimmed padding. Restore the fixed 64-token buffer for
    # no-EOS records to distinguish exhausted budget from pad-before-EOS.
    from gdtcr.model import PAD
    ids=sample['tokens']+[PAD]*(64-len(sample['tokens']))
    fresh=decode_sample_v2(ids,target_chain)
    if fresh!=sample:
        # Historical decoder preserves missing_eos when its full buffer was
        # exhausted; a trimmed no-EOS sample may only differ in failure reason.
        trimmed=decode_sample_v2(sample['tokens'],target_chain)
        if trimmed!=sample:raise ValueError('Saved sample validity/token discrepancy')


def main():
    parser=argparse.ArgumentParser(description=__doc__);args=parser.parse_args()
    paths=sorted(Path('configs/revision_bmc').glob('revision_*.json'))
    tasks=[]
    for path in paths:
        manifest=load(path)
        for task in manifest['tasks']:
            rp=Path(manifest['job_records'])/(task['id']+'.json')
            if not rp.exists() or load(rp)['status']!='complete':
                raise RuntimeError('Revision results incomplete: '+task['id'])
            record=load(rp)
            assert record['manifest_sha256']==file_sha256(path)
            for p,h in record['output_sha256'].items():
                if file_sha256(p)!=h:raise ValueError('Changed task output: '+p)
            tasks.append({'task':task['id'],'slurm_job_id':record['slurm_job_id'],
                          'slurm_array_job_id':record['slurm_array_job_id'],
                          'slurm_array_task_id':record['slurm_array_task_id'],
                          'record_sha256':file_sha256(rp),'manifest_sha256':file_sha256(path)})
    splits=load('data/splits/revision_bmc/manifest.json');runs={};flat=[];query_rows=[];training=[];all_metrics={}
    for protocol,meta in splits['protocols'].items():
        folder=Path('data/splits/revision_bmc')/protocol
        for filename,h in meta['output_sha256'].items():assert file_sha256(folder/filename)==h
        train,test=read_pairs(folder/'train.tsv'),read_pairs(folder/'test.tsv')
        for condition in ('paired','constant','random','shuffled'):
            for seed in (0,1):
                out=Path('artifacts/revision_bmc/evaluation')/protocol/condition/f'seed-{seed}'
                data=gz(out/'rows.json.gz');summary=load(out/'summary.json');prov=load(out/'provenance.json')
                assert prov['arguments']['samples']==64
                assert prov['input_sha256'][str((folder/'test.tsv').resolve())]==file_sha256(folder/'test.tsv')
                key=f'{protocol}/{condition}/seed-{seed}';result={'directions':{},'candidate_sha256':file_sha256(out/'rows.json.gz'),
                                                              'device':prov['device_name'],'source':str(out)}
                for direction,rows in data.items():
                    truths=query_targets(test,direction)
                    assert [r['source'] for r in rows]==list(truths)
                    col=0 if direction=='gamma_to_delta' else 1
                    targets={p[1-col] for p in train};metrics=[]
                    for row in rows:
                        assert row['positives']==truths[row['source']]
                        assert len(row['samples'])==64
                        for sample in row['samples']:verify_decoding(sample,row['target_chain'])
                        nll=row['candidate_nll'];scores={'likelihood':dict(zip(row['candidate_sequences'],[-v for v in nll])),
                            'ranker':dict(zip(row['candidate_sequences'],row['candidate_ranker_score'])) if row['candidate_ranker_score'] is not None else None}
                        assert all(math.isfinite(v) for v in nll+row['positive_nll'])
                        assert math.isclose(row['positive_query_mean_nll'],np.mean(row['positive_nll']),abs_tol=1e-12)
                        fresh=summarize_prefix(row['samples'],row['positives'],targets,scores,[16,64])
                        assert fresh==row['prefixes']
                        pre=fresh['64/allow_training_targets'];lik=pre['methods']['likelihood']
                        m={'nll':row['positive_query_mean_nll'],'coverage':lik['coverage'],
                           'likelihood_hit_at_5':lik['hit_at_5'],'likelihood_recall_at_5':lik['recall_at_5'],'likelihood_mrr':lik['mrr']}
                        if 'ranker' in pre['methods']:m['ranker_hit_at_5']=pre['methods']['ranker']['hit_at_5']
                        metrics.append(m)
                        query_rows.append({'protocol':protocol,'condition':condition,'seed':3407+101*seed,
                            'direction':direction,'source':row['source'],'recorded_partners':json.dumps(row['positives']),
                            'original_component':'giant' if protocol=='giant_edge_holdout' else '',**m})
                    assert summarize_rows(rows)==summary['directions'][direction]
                    binary=[k for k in m if k=='coverage' or 'hit_at_5' in k]
                    stats=interval(metrics,meta['uncertainty_unit'],binary)
                    all_metrics[key,direction]=metrics;result['directions'][direction]=stats
                    for metric,estimate in stats['metrics'].items():flat.append({'protocol':protocol,'condition':condition,
                        'training_seed':3407+101*seed,'direction':direction,'metric':metric,
                        'queries':len(rows),'uncertainty_unit':meta['uncertainty_unit'],**estimate})
                runs[key]=result
        for condition in ('paired','constant','random'):
            for seed in (0,1):
                out=Path('artifacts/revision_bmc/generator')/protocol/condition/f'seed-{seed}'
                run,summary=load(out/'run.json'),load(out/'summary.json');records=[json.loads(l) for l in (out/'metrics.jsonl').read_text().splitlines()]
                best=torch.load(out/'best.pt',map_location='cpu',weights_only=False)
                criterion=[r['validation']['selection_nll'] for r in records if 'validation' in r]
                state=best['training_state']
                assert math.isclose(state['best_validation_nll'],min(criterion),abs_tol=1e-12)
                assert str(best['arguments']['validation'])==str(folder/'validation_selection.tsv')
                training.append({'protocol':protocol,'condition':condition,'seed':3407+101*seed,'stage':'generator',
                    'steps':summary['steps_completed'],'best_step':state['step'],'selection_value':state['best_validation_nll'],
                    'checkpoint_sha256':file_sha256(out/'best.pt'),'device':run['device_name'],
                    'actual_sequences':json.dumps(summary['direction_sequences_this_invocation']),
                    'actual_target_tokens':json.dumps(summary['direction_target_tokens_this_invocation'])})
                del best
        for seed in (0,1):
            out=Path('artifacts/revision_bmc/ranker')/protocol/f'seed-{seed}'
            run,summary=load(out/'run.json'),load(out/'summary.json')
            records=[json.loads(l) for l in (out/'metrics.jsonl').read_text().splitlines()]
            vals=[r['validation']['mrr'] for r in records if 'validation' in r and r['step']>1500]
            best=torch.load(out/'best.pt',map_location='cpu',weights_only=False)
            assert math.isclose(summary['best_validation_mrr'],max(vals),abs_tol=1e-12)
            assert not run['arguments']['freeze_encoder']
            assert len(set(vals))>1 and not all(v==1 for v in vals)
            batch_size=run['arguments']['batch_size']
            contrastive_steps=min(summary['steps_completed'],run['arguments']['contrastive_steps'])
            bce_steps=summary['steps_completed']-contrastive_steps
            negative_draws=sum(summary['negative_audit'].get(k,0) for k in ('source_gamma','source_delta'))
            assert negative_draws==bce_steps*batch_size*run['arguments']['negative_ratio']
            training.append({'protocol':protocol,'condition':'paired','seed':3407+101*seed,'stage':'ranker',
                'steps':summary['steps_completed'],'best_step':summary['best_step'],
                'selection_value':summary['best_validation_mrr'],'selection_range':json.dumps([min(vals),max(vals)]),
                'checkpoint_sha256':file_sha256(out/'best.pt'),'device':run['device_name'],
                'copied_encoder_trainable':True,'actual_sequences':'not tracked for legacy ranker loops; training draw counts in negative_audit',
                'actual_target_tokens':'not logged; no token-matching claim',
                'positive_pair_draws':summary['steps_completed']*batch_size,
                'contrastive_positive_pair_draws':contrastive_steps*batch_size,
                'bce_positive_pair_draws':bce_steps*batch_size,
                'bce_negative_pair_draws':negative_draws,
                'pair_count_scope':'sampled pairs with replacement, not unique sequences or encoded-token exposure',
                'negative_counts':json.dumps(summary['negative_audit'],sort_keys=True)})
            del best
    comparisons=[]
    for protocol,meta in splits['protocols'].items():
        directions=DIRECTIONS if meta['direction']=='both' else (meta['direction'],)
        for direction in directions:
            for seed in (0,1):
                left=all_metrics[f'{protocol}/paired/seed-{seed}',direction]
                for other in ('constant','random','shuffled'):
                    right=all_metrics[f'{protocol}/{other}/seed-{seed}',direction]
                    keys=set(left[0])&set(right[0]);delta=[{k:a[k]-b[k] for k in keys} for a,b in zip(left,right)]
                    stats=interval(delta,meta['uncertainty_unit'],[])
                    for metric,estimate in stats['metrics'].items():comparisons.append({'protocol':protocol,
                        'seed':3407+101*seed,'direction':direction,'contrast':'conditional_minus_'+other,
                        'metric':metric,'unit':'nats/token' if metric=='nll' else 'fraction',**estimate})
                delta=[{'hit_at_5':r['ranker_hit_at_5']-r['likelihood_hit_at_5']} for r in left]
                estimate=interval(delta,meta['uncertainty_unit'],[])['metrics']['hit_at_5']
                comparisons.append({'protocol':protocol,'seed':3407+101*seed,'direction':direction,
                    'contrast':'ranker_minus_likelihood','metric':'hit_at_5','unit':'fraction',**estimate})
    transfer=[]
    for p in sorted(Path('artifacts/revision_bmc/transfer').glob('*/summary.json')):
        r=load(p)
        for direction,values in r['directions'].items():
            for setting,stats in values.items():
                for metric,v in stats['metrics'].items():transfer.append({'protocol':p.parent.name,'direction':direction,
                    'setting':setting,'metric':metric,'uncertainty_unit':r['unit'],**v})
    target=Path('paper/results/bmc');tables=target/'tables';tables.mkdir(parents=True,exist_ok=True)
    tsv(tables/'revision_metrics.tsv',flat);tsv(tables/'revision_query_results.tsv',query_rows)
    tsv(tables/'revision_training.tsv',training);tsv(tables/'revision_paired_contrasts.tsv',comparisons)
    tsv(tables/'nearest_input_transfer.tsv',transfer)
    report={'complete':True,'tasks':tasks,'task_count':len(tasks),'runs':runs,'splits':splits,
            'training':training,'comparisons':comparisons,'test_outcome_audit_passed':True,
            'audit_scope':'All output hashes; decoded candidates and prefix metrics; test membership; logged selection checkpoints. GPU scores are not recomputed.',
            'primary_evidence_unchanged':file_sha256('artifacts/completion_v2/final_evidence/evidence.json')=='5badb3b9b8ead02c57afeb5f578f85f3a5e343bad9714fb7daa08f48342b2f3b'}
    (target/'revision_summary.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'tasks':len(tasks),'model_evaluations':len(runs),'training':len(training),'passed':True}))

DIRECTIONS=('gamma_to_delta','delta_to_gamma')
if __name__=='__main__':main()
