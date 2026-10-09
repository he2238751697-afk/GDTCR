#!/usr/bin/env python3
"""Vector publication figures for the BMC revision, from frozen numerical inputs."""
import argparse,csv,json,math,statistics
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import numpy as np
from render_results_v2 import Evidence,COLORS,DIRECTIONS,DIRECTION_LABELS,SPLITS,PRIMARY
from plot_sensitivity_v2 import seed_pair

OUT=Path('paper/results/bmc/figures')
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.titlesize':11,
                     'pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'none','axes.spines.top':False,
                     'axes.spines.right':False,'savefig.dpi':300})
RECORDS=[]

def save(fig,n,label,title,caption):
    OUT.mkdir(parents=True,exist_ok=True)
    name=f'figure_{n}_{label}'
    for extension in ('pdf','png','svg'):
        fig.savefig(OUT/(name+'.'+extension),bbox_inches='tight',facecolor='white')
    plt.close(fig)
    RECORDS.append({'number':n,'id':name,'label':label,'title':title,'caption':caption})

def box(ax,x,y,w,h,text,color='#edf3f7',size=10):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.009,rounding_size=0.012',
                              facecolor=color,edgecolor='#788894',linewidth=.8))
    ax.text(x+w/2,y+h/2,text,ha='center',va='center',fontsize=size,linespacing=1.4)

def arrow(ax,a,b,style='-'):
    ax.annotate('',xy=b,xytext=a,arrowprops={'arrowstyle':'->','color':'#475966','lw':1.2,'linestyle':style})

def workflow():
    fig,axes=plt.subplots(2,2,figsize=(12,8.6),layout='constrained')
    for ax in axes.flat:ax.set(xlim=(0,1),ylim=(0,1));ax.axis('off')
    a,b,c,d=axes.flat
    for ax,title in zip(axes.flat,['A  Task definition','B  Single-chain denoising pretraining',
                                 'C  Conditional generation and separate ranking','D  Controlled evaluation']):
        ax.set_title(title,loc='left',weight='bold',pad=12)
    box(a,.03,.70,.36,.17,'Single gamma (γ) CDR3','#e6f1f5');box(a,.60,.70,.36,.17,'Recorded delta (δ)\npartner CDR3','#fff0e5')
    arrow(a,(.41,.785),(.58,.785))
    box(a,.03,.42,.36,.17,'Single delta (δ) CDR3','#fff0e5');box(a,.60,.42,.36,.17,'Recorded gamma (γ)\npartner CDR3','#e6f1f5')
    arrow(a,(.41,.505),(.58,.505))
    a.text(.5,.23,'Two directions share one generator\nMultiple recorded partners per query are retained',ha='center',va='center')
    a.text(.5,.07,'Endpoint: recorded sequence recovery',ha='center',weight='bold',color=COLORS[0])
    box(b,.04,.73,.92,.18,'Unpaired gamma / delta CDR3 sequences\nAll paired-corpus chains excluded','#e8f2e9')
    box(b,.04,.42,.40,.20,'Masking + deletion\n15% / 30%; 80/10/10','#e8f2e9')
    box(b,.58,.42,.38,.20,'Shared Transformer\nreconstruction','#e8f2e9');arrow(b,(.46,.52),(.56,.52));arrow(b,(.50,.71),(.25,.65))
    b.text(.5,.23,'Teacher-forced token loss and aligned-copy control\nUnique-sequence-disjoint train / validation',ha='center',va='center')
    b.text(.5,.07,'Reconstruction is a separate endpoint',ha='center',weight='bold',color=COLORS[2])
    box(c,.02,.70,.25,.17,'Input CDR3','#e6f1f5');box(c,.36,.70,.29,.17,'Encoder--decoder','#e6f1f5');box(c,.75,.70,.23,.17,'Candidate\nCDR3s','#fff0e5')
    c.text(.5,.95,'Paired fine-tuning on recorded training edges',ha='center',fontsize=9.8)
    arrow(c,(.28,.785),(.35,.785));arrow(c,(.66,.785),(.74,.785))
    box(c,.06,.40,.45,.17,'Copied fine-tuned encoder\nseparately optimized','#f1eaf5');box(c,.64,.40,.32,.17,'Pair ranker\ncandidate scores','#f1eaf5')
    arrow(c,(.49,.68),(.28,.59),'--');arrow(c,(.53,.485),(.62,.485));arrow(c,(.87,.68),(.83,.59))
    c.text(.5,.29,'Same training edges; original generator stays fixed',ha='center',fontsize=9.8)
    c.text(.5,.10,'Generator: 7.40M parameters | 4 encoder + 4 decoder layers\nWidth 256 | 8 heads | FFN 1024 | dropout 0.1 | max 64 tokens',ha='center',va='center',fontsize=9.3)
    box(d,.02,.69,.45,.21,'Free generation\n64 draws; truth not guaranteed\nCoverage + Hit@5','#fff0e5',9.8)
    box(d,.53,.69,.45,.21,'Fixed-pool retrieval\nRecorded positives injected\nHit@5 + Recall + MRR','#e6f1f5',9.8)
    box(d,.02,.37,.96,.20,'Primary: whole-component split, both chains unseen\nDiagnostics: unseen / seen inputs, study exposure, giant edges','#f0f1f2',9.6)
    arrow(d,(.245,.67),(.245,.60));arrow(d,(.755,.67),(.755,.60))
    d.text(.5,.21,'Primary: equal-direction mean query-macro Hit@5 at 64 draws',ha='center',fontsize=9.7,weight='bold')
    d.text(.5,.07,'Exact-overlap and sequence-distance audits accompany recovery',ha='center',fontsize=9.2)
    save(fig,1,'workflow','Overview of the single-CDR3 partner-recovery benchmark and model workflow.',
         'A: each task maps one gamma or delta CDR3 to recorded partner CDR3s. B: denoising pretraining excludes all paired-corpus chains. C: conditional generation and separately trained ranking share training-edge and encoder provenance. The ranker optimizes its copied encoder; the original generator remains fixed. D: free generation and truth-containing retrieval are different endpoints. The primary endpoint is equal-direction mean query-macro Hit@5 at 64 draws under component-disjoint splitting; other exposure protocols are diagnostics.')

def graph(e):
    fig,ax=plt.subplots(2,2,figsize=(11,7.5),layout='constrained');a,b,c,d=ax.flat
    a.set(xlim=(0,1),ylim=(0,1));a.axis('off');a.set_title('A  Whole-component assignment (schematic)',loc='left',weight='bold')
    for x,width,title,color in [(.01,.43,'Training\n7254 edges','#e7f1f5'),(.48,.23,'Validation\n907 edges','#f0edf6'),(.75,.23,'Test\n907 edges','#fff0e5')]:
        box(a,x,.18,width,.66,'',color)
        a.text(x+width/2,.74,title,ha='center',fontsize=9.3)
        if width>.3:
            nodes=[(x+.1,.53),(x+.1,.32),(x+.30,.58),(x+.30,.42),(x+.30,.27)]
            edges=[(0,2),(0,3),(1,3),(1,4)]
        else:
            nodes=[(x+.07,.5),(x+.16,.42)];edges=[(0,1)]
        for i,j in edges:a.plot([nodes[i][0],nodes[j][0]],[nodes[i][1],nodes[j][1]],color='#697a85')
        if width>.3:
            a.scatter(*zip(*nodes[:2]),color=COLORS[0],s=45,marker='o');a.scatter(*zip(*nodes[2:]),color=COLORS[1],s=50,marker='^')
            a.text(x+width/2,.08,'Largest: 5005 edges',ha='center',fontsize=9)
        else:a.scatter(*nodes[0],color=COLORS[0],s=45);a.scatter(*nodes[1],color=COLORS[1],s=50,marker='^')
    a.text(.5,.97,'Nodes: γ circles / δ triangles   Edges: recorded pairs',ha='center',fontsize=9)
    a.text(.73,.07,'No exact chain overlap',ha='center',fontsize=9)
    values=[5005,9068-5005];bars=b.bar(['Largest component\n(training only)','Other 3293\ncomponents'],values,color=COLORS[:2],width=.55)
    b.bar_label(bars,labels=['5005 (55.2%)','4063 (44.8%)'],padding=5);b.set_ylim(0,6000);b.set_ylabel('Recorded edges')
    b.set_title('B  Concentrated pairing graph',loc='left',weight='bold')
    table=e.raw['distance_audit']['test_strata'];bottom=np.zeros(3)
    for j,(key,label) in enumerate([('0','0 edits'),('1','1 edit'),('2','2 edits'),('ge3','≥3 edits')]):
        vals=np.array([table[f'split_seed{s}']['gamma']['pretraining'].get(key,0)/table[f'split_seed{s}']['gamma']['queries']*100 for s in SPLITS])
        c.bar(range(3),vals,bottom=bottom,label=label,color=COLORS[j],width=.6);bottom+=vals
    c.set_xticks(range(3),[str(s) for s in SPLITS]);c.set_ylim(0,104);c.set_ylabel('Primary-test gamma queries (%)');c.set_xlabel('Component split seed')
    c.set_title('C  Nearest pretraining gamma CDR3',loc='left',weight='bold');c.legend(ncols=2,fontsize=8,frameon=True,facecolor='white',framealpha=.92,loc='lower center')
    bars=d.bar(range(3),[table[f'split_seed{s}']['distant_edges'] for s in SPLITS],color=COLORS[3],width=.55)
    d.bar_label(bars,labels=['5/907','5/907','3/907'],padding=5);d.set_ylim(0,6.5);d.set_ylabel('Distant test edges');d.set_xticks(range(3),[str(s) for s in SPLITS]);d.set_xlabel('Component split seed')
    d.set_title('D  Both chains distant from both references',loc='left',weight='bold')
    save(fig,2,'data','Pairing-graph concentration and sequence exposure.',
         'A: schematic component assignment, with all 5005 edges of the largest component retained in training. Nodes are unique gamma/delta CDR3s and edges are publicly recorded pairs. Primary partitions have no exact chain overlap. B: observed component concentration. C: minimum full-CDR3 Levenshtein distance to the pretraining pool. D: a distant edge requires both chains to be at least three edits from both supervised and pretraining references. The 5/5/3 distant-edge counts are too small for stable inferential transfer claims. This figure describes dataset exposure, not a recovery endpoint.')

def primary(e):
    fig=plt.figure(figsize=(12,9));gs=fig.add_gridspec(3,3,height_ratios=[1,1,.62],hspace=.73,wspace=.34)
    fig.text(.5,.96,'Small circles: split means (two seeds each)   Diamonds and bars: mean ± between-split SD',ha='center',fontsize=9)
    for i,direction in enumerate(DIRECTIONS):
        for j,metric in enumerate(('query_mean_nll','coverage','likelihood|hit_at_5')):
            ax=fig.add_subplot(gs[i,j]);groups=[(m,metric,l) for m,l in [('paired','Conditional'),('constant','Constant'),('random','Random init.'),('shuffled','Shuffled')]]
            if j==2:groups=[('paired','likelihood|hit_at_5','Likelihood'),('paired','ranker|hit_at_5','Ranker'),('paired','fused|hit_at_5','Fused')]+groups[1:]
            for x,(model,metric,label) in enumerate(groups):
                vals=np.array(e.split_means(model,'free',direction,metric))*(1 if j==0 else 100)
                color=COLORS[4 if metric.startswith('ranker') else 5 if metric.startswith('fused') else
                             {'paired':0,'constant':1,'random':2,'shuffled':3}[model]]
                ax.scatter(x+np.array([-.12,0,.12]),vals,color=color,s=17)
                ax.errorbar(x,vals.mean(),yerr=vals.std(ddof=1),fmt='D',color=color,ms=5,capsize=3)
            ax.set_xticks(range(len(groups)),[g[2] for g in groups],rotation=35,ha='right',fontsize=8)
            ax.set_title(chr(65+i*3+j)+'  '+DIRECTION_LABELS[direction]+' | '+('NLL' if j==0 else 'Coverage' if j==1 else 'Hit@5'),loc='left')
            ax.set_ylabel('Nats / target token' if j==0 else 'Query-macro (%)');ax.grid(axis='y',alpha=.2)
            if j:ax.set_ylim(bottom=0)
            if i==0 and j==2:ax.set_ylim(0,.12);ax.text(.5,.6,'Zero top-five events\nfor every shown condition',transform=ax.transAxes,ha='center',fontsize=9)
    ax=fig.add_subplot(gs[2,:]);ax.axis('off')
    lines=['Conditional event counts (seed 3407 / 3508 within each split; fits are not pooled):',
           f"{'Direction / endpoint':<29}{'Split 17':<24}{'Split 3407':<24}{'Split 2026':<24}"]
    for direction in DIRECTIONS:
        for metric,label in [('coverage','coverage'),('likelihood|hit_at_5','likelihood H@5'),('ranker|hit_at_5','ranker H@5')]:
            counts=[]
            for split in SPLITS:
                r=[e.metric(f'split_seed{split}/paired',s,'free',direction,metric) for s in (0,1)]
                counts.append(' / '.join(f"{x['events']}:{x['denominator']}" for x in r))
            lines.append(f"{DIRECTION_LABELS[direction]+' '+label:<29}"+''.join(f'{v:<24}' for v in counts))
    ax.text(0,1,'\n'.join(lines),transform=ax.transAxes,ha='left',va='top',fontfamily='DejaVu Sans Mono',fontsize=8.2,linespacing=1.5)
    save(fig,3,'primary','Sparse free recorded-partner recovery at 64 draws.',
         'No recorded positive is injected into free candidates; training targets are allowed. Conditional, constant-source, random-initialization and shuffled-input conditions share the evaluation rule. Points are three split means after averaging two model seeds; diamonds and ranges are their mean and descriptive SD, not subject-level confidence intervals. Likelihood, ranker and fused scores order identical conditional candidates. The graphic gives conditional events:query counts for each fitted model; all conditions are tabulated in Additional file 4. Zero events are retained. A lower NLL does not imply reliable candidate availability or top-five recovery.')

def retrieval(e):
    methods=[('likelihood','Conditional likelihood'),('prior','Target prior'),('difference','Conditional minus prior'),('shallow','Shallow length / motif'),('input_neighbor','Nearest-input similarity'),('edit_neighbor','Two-chain edit neighbor'),('ranker','Separately trained ranker'),('fused','Fused'),('shuffled','Shuffled-input likelihood'),('random','Seeded random')]
    pools=('random','length','motif','edit','full');matrices=[]
    for direction in DIRECTIONS:
        matrix=[]
        for method,label in methods:
            row=[]
            for pool in pools:
                vals=[]
                for split in SPLITS:
                    if method=='input_neighbor':
                        r=json.load(open(f'artifacts/revision_bmc/transfer/split_seed{split}/summary.json'))
                        vals.append(r['directions'][direction]['retrieval/'+pool]['metrics']['hit_at_5']['estimate']);continue
                    for seed in (0,1):
                        if method in ('shallow','edit_neighbor'):
                            kind,bseed=('shallow',seed) if method=='shallow' else ('exact_neighbor',None)
                            report=e.baselines[(f'split_seed{split}',kind,bseed)]
                            item=e.report_metric(report,direction,pool+'|'+method+'|hit_at_5')
                        else:item=e.metric(f'split_seed{split}/paired',seed,'pools',direction,pool+'|'+method+'|hit_at_5')
                        vals.append(item['estimate'])
                row.append(100*statistics.mean(vals))
            matrix.append(row)
        matrices.append(np.array(matrix))
    fig,axes=plt.subplots(1,2,figsize=(12,5.4),layout='constrained');vmax=max(m.max() for m in matrices)
    for ax,m,direction,panel in zip(axes,matrices,DIRECTIONS,'AB'):
        im=ax.imshow(m,cmap='Blues',vmin=0,vmax=vmax,aspect='auto');ax.set_xticks(range(5),['Random','Length','Motif','Edit','Full'],rotation=15)
        ax.set_yticks(range(len(methods)),[r[1] for r in methods],fontsize=8.8);ax.set_title(panel+'  '+DIRECTION_LABELS[direction],loc='left',weight='bold')
        for i in range(len(methods)):
            for j in range(5):ax.text(j,i,f'{m[i,j]:.1f}',ha='center',va='center',fontsize=9,color='white' if m[i,j]>vmax*.57 else '#111')
    fig.colorbar(im,ax=axes,label='Query-macro Hit@5 (%)',shrink=.8)
    save(fig,4,'retrieval','Ranking within truth-containing fixed candidate pools.',
         'Fixed pools contain recorded positives by construction. Random, length, motif and edit pools add up to 100 unrecorded distractors; Full uses the complete role-specific target universe. Values average seeds within split and then the three primary splits equally. Deterministic methods have one value per split. Nearest-input similarity scores candidates by target distance to partners of the single nearest training input; direct partner transfer is reported separately. No scorer dominates all pools and directions. These retrieval outcomes cannot be equated with free-generation recovery or biological specificity.')

def efficiency(e):
    fig,axes=plt.subplots(2,2,figsize=(10,6.8),layout='constrained');x=np.array([725,1814,2249,7254])
    fig.suptitle('Two fitted seeds per setting; shading spans their values (not a confidence interval)',fontsize=10)
    for i,direction in enumerate(DIRECTIONS):
        for j,metric in enumerate(('query_mean_nll','likelihood|hit_at_5')):
            ax=axes[i,j]
            for color,model in zip(COLORS,('pretrained','random')):
                names=[f'data_fraction{n}/{model}' for n in (10,25,50)]+['split_seed17/'+('paired' if model=='pretrained' else 'random')]
                v=np.array([seed_pair(e,n,'free',direction,metric,1 if j==0 else 100) for n in names])
                ax.plot(x,v.mean(1),'o-',color=color,label=model.capitalize());ax.fill_between(x,v.min(1),v.max(1),color=color,alpha=.14)
                ax.scatter(np.repeat(x,2),v.ravel(),s=12,color=color)
            ax.set_xscale('log');ax.set_xticks(x,['725','1814','2249\n31.0%','7254\n+ giant'],rotation=20,fontsize=9);ax.minorticks_off()
            ax.set_title(chr(65+i*2+j)+'  '+DIRECTION_LABELS[direction],loc='left');ax.set_xlabel('Actual training edges (log scale)')
            ax.set_ylabel('Nats / target token' if j==0 else 'Likelihood Hit@5 (%)');ax.grid(axis='y',alpha=.2)
            if j:ax.set_ylim(bottom=0)
    axes[0,0].legend(frameon=False,fontsize=9)
    save(fig,5,'efficiency','Likelihood and recovery across nested complete-component training subsets.',
         'The actual subsets contain 725/1814/2249/7254 edges. The nominal 50% subset contains only 31.0% of training edges. All smaller subsets contain singleton components; the giant component enters only at full data, so composition and size change together. Lines average two model seeds and shading spans their fitted estimates; it is not a confidence interval. Lower NLL does not provide a consistent small-data free-recovery advantage.')

def budget(e):
    evals={r['seed']:r for r in e.raw['evaluations'].values() if r['evaluation_name']=='split_seed17/paired'}
    fig,axes=plt.subplots(2,3,figsize=(12.5,7.1),layout='constrained')
    fig.suptitle('Calibration panels: solid / circles = seed 3407; dashed / crosses = seed 3508',fontsize=9.5)
    for i,direction in enumerate(DIRECTIONS):
        for j,metric in enumerate(('coverage','likelihood|hit_at_5')):
            ax=axes[i,j]
            for k,model in enumerate(('paired','constant')):
                for policy,style in (('allow_training_targets','-'),('exclude_training_targets','--')):
                    v=np.array([seed_pair(e,'split_seed17/'+model,'free',direction,metric,100,f'{n}/{policy}') for n in (16,64,256)])
                    ax.plot((16,64,256),v.mean(1),style,marker='o',ms=4,color=COLORS[k],label=('Conditional' if k==0 else 'Constant')+(', allowed' if style=='-' else ', excluded'))
            ax.set_xscale('log',base=4);ax.set_xticks((16,64,256),('16','64','256'));ax.set_xlabel('Nested draw prefix');ax.set_ylabel(('Coverage' if j==0 else 'Likelihood Hit@5')+' (%)');ax.grid(alpha=.2);ax.set_ylim(bottom=0)
            ax.set_title(chr(65+i*3+j)+'  '+DIRECTION_LABELS[direction],loc='left')
        ax=axes[i,2]
        for seed,result in sorted(evals.items()):
            s=result['modes']['free']['analyzed']['directions'][direction]
            for k,method in enumerate(('likelihood','ranker','fused')):
                points=s['acceptance_curves'][method]['points']
                ax.plot([100*p['accepted_query_fraction'] for p in points],[100*p['recorded_hit_at_5'] for p in points],color=COLORS[k],linestyle='-' if seed==0 else '--',label=method.capitalize() if seed==0 else None)
                chosen=s['calibrated'][PRIMARY][method];ax.scatter(100*chosen['accepted_query_fraction'],100*chosen['hit_at_5'],color=COLORS[k],marker='o' if seed==0 else 'x',s=26)
        ax.set(xlim=(-2,102),xlabel='Queries accepted (%)',ylabel='Hit@5 / all queries (%)');ax.set_ylim(bottom=0);ax.grid(alpha=.2);ax.set_title(chr(67+i*3)+'  Exploratory calibration',loc='left')
        if i==0:ax.set_ylim(0,.1);ax.text(.5,.5,'Zero top-five events\nat all thresholds',transform=ax.transAxes,ha='center',fontsize=9)
    axes[0,0].legend(frameon=False,fontsize=7.2);axes[1,2].legend(frameon=False,fontsize=8)
    save(fig,7,'budget','Sampling budgets and exploratory calibration.',
         'The 16/64/256 budgets are prefixes of the same saved draws on split 17. Left and middle panels separate candidate coverage from likelihood Hit@5, with exact training targets allowed (solid) or excluded (dashed); lines average two seeds. Coverage is unchanged by target exclusion in the chain-disjoint primary test. Right panels are exploratory calibration-quantile operating curves; solid/dashed lines identify seeds and markers identify independently calibrated thresholds. All test queries remain in recovery denominators. More draws can increase coverage without improving top-five ordering. No threshold is a validated biological selector.')

def protocols(e):
    p=Path('paper/results/bmc/revision_summary.json')
    if not p.exists():return
    rev=json.loads(p.read_text());fig,axes=plt.subplots(1,2,figsize=(12.5,7.6),layout='constrained')
    for ax,direction,panel in zip(axes,DIRECTIONS,'AB'):
        names=['split_seed17','unseen_gamma_repaired' if direction=='gamma_to_delta' else 'unseen_input_delta_to_gamma','seen_input_'+direction,'source_holdout','source_shared','giant_edge_holdout']
        labels=['Primary component-disjoint','Unseen input (repaired γ selection)' if direction=='gamma_to_delta' else 'Unseen input','Seen input / withheld edge','Strict study holdout','Source-shared','Within giant / withheld edge']
        for row,(name,label) in enumerate(zip(names,labels)):
            for j,condition in enumerate(('paired','constant','shuffled')):
                if condition=='shuffled' and (name.startswith('seen_input_') or name=='unseen_input_delta_to_gamma'):
                    continue  # Not evaluated in these original directional fits.
                vals=[];counts=[];n=None
                for seed in (0,1):
                    if name in ('unseen_gamma_repaired','giant_edge_holdout'):
                        data=rev['runs'][f'{name}/{condition}/seed-{seed}']['directions'][direction]
                        item=data['metrics']['likelihood_hit_at_5'];v=item['estimate'];counts.append(f"{item['events']}/{item['denominator']}")
                        n=item['denominator']
                    else:
                        item=e.metric(name+'/'+condition,seed,'free',direction,'likelihood|hit_at_5');v=item['estimate'];counts.append(f"{item['events']}/{item['denominator']}");n=item['denominator']
                    vals.append(v*100)
                color=COLORS[(0,1,3)[j]]
                y=row+(j-1)*.18;ax.plot(vals,[y,y],color=color,alpha=.5);ax.scatter(vals,[y,y],color=color,marker=['o','s','^'][j],s=27,label=['Conditional','Constant source','Shuffled input'][j] if row==0 else None)
                if j==0:ax.text(max(vals)+1,y-.03,'; '.join(counts),fontsize=8.2,va='center')
            train=rev['splits']['protocols'][name]['sizes']['train'] if name in ('unseen_gamma_repaired','giant_edge_holdout') else e.raw['data_audit']['protocols'][name]['parts']['train']['pairs']
            labels[row]=label+f'\n{n} queries; {train} training edges'
        ax.axhline(.5,color='#a2a9ae',lw=.9);ax.set_yticks(range(6),labels,fontsize=8.6);ax.invert_yaxis();ax.set_xlim(-1,64);ax.set_xlabel('Likelihood Hit@5 (%)');ax.grid(axis='x',alpha=.2);ax.set_title(panel+'  '+DIRECTION_LABELS[direction],loc='left',weight='bold')
    axes[0].legend(loc='lower right',frameon=False,fontsize=8)
    save(fig,6,'protocols','Recovery across distinct exposure populations.',
         'Each point is one model seed at 64 free draws; labels give conditional events/queries in seed order 3407;3508. The first row is the primary split-17 reference; all other rows are diagnostic populations with different training composition. Original unseen-gamma selection used a single query and had degenerate MRR; the plotted revision refits use 31 selection queries, leaving train/test membership unchanged. Unseen-input tasks permit target exposure; seen-input and within-giant tasks retain supervised input exposure, with both endpoints exposed in the latter. Missing shuffled points in original directional tasks mean not evaluated. Strict study holdout excludes held-study chains; source-shared retains common chains. Neither is donor-independent external validation. All within-giant edges arise from one original component; no inferential component interval is asserted.')

def main():
    e=Evidence(json.load(open('artifacts/completion_v2/final_evidence/evidence.json')))
    workflow();graph(e);primary(e);retrieval(e);efficiency(e);protocols(e);budget(e)
    Path('paper/results/bmc/figure_manifest.json').write_text(json.dumps(sorted(RECORDS,key=lambda r:r['number']),indent=2)+'\n')
    print('Figures:',[r['number'] for r in RECORDS])
if __name__=='__main__':main()
