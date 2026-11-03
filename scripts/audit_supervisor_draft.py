#!/usr/bin/env python3
"""Recheck the supervisor draft against frozen artifacts and its own compiled PDFs.

No fitting or bootstrap resampling is performed. Saved per-query observations
are reaggregated, and saved paired intervals are checked with their signs.
"""
import csv
import hashlib
import json
import re
import statistics
import subprocess
from collections import defaultdict
from pathlib import Path
import pdfplumber
from PIL import Image
from render_results_v2 import Evidence, DIRECTIONS, SPLITS

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'paper/supervisor_review'
BUILD = ROOT / 'output/supervisor_review'

def load(path): return json.loads((ROOT / path).read_text())
def sha(path): return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
def compact(value): return re.sub(r'\s+', '', value)
def write(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')

def prose_tokens(body):
    body=re.sub(r'(?m)^\s*%.*$', '', body)
    body=re.sub(r'\\begin\{(figure|table|equation|align)\}.*?\\end\{\1\}', '', body, flags=re.S)
    body=re.sub(r'\\(?:cite|ref|label|url|texttt)\{[^}]*\}', '', body)
    body=re.sub(r'\$[^$]*\$', '', body)
    body=body.replace(r'\gtd{}','gamma-to-delta').replace(r'\dtg{}','delta-to-gamma').replace(r'\gd{}','gamma-delta')
    body=re.sub(r'\\[A-Za-z]+\*?(?:\[[^\]]*\])?', '', body)
    return re.findall(r"[A-Za-z0-9]+(?:[.'\-][A-Za-z0-9]+)*", body)

def main():
    import os
    os.chdir(ROOT)
    records=[]
    def check(name, ok, source):
        records.append({'check':name, 'passed':bool(ok), 'source':source})
        if not ok:
            write('audit_failure.json', {'failed_check':name, 'source':source, 'records':records})
            raise AssertionError(name+' | '+str(source))
    text=(OUT/'manuscript.tex').read_text()
    supplement=(OUT/'supplementary.tex').read_text()
    combined=text+'\n'+supplement
    def present(name, fragment, body=combined, source='frozen saved results'):
        check(name, compact(fragment) in compact(body), source+'; expected '+fragment)

    frozen=load('paper/final_submission/scientific_freeze.json')
    for name,expected in frozen['files'].items():
        check('Frozen file '+name, sha(name)==expected, expected)
    check('Exactly 225 frozen scientific files', len(frozen['files'])==225, 'original manifest')
    check('Primary evidence unchanged',sha('artifacts/completion_v2/final_evidence/evidence.json')==
          '5badb3b9b8ead02c57afeb5f578f85f3a5e343bad9714fb7daa08f48342b2f3b','SHA256')
    e=Evidence(load('artifacts/completion_v2/final_evidence/evidence.json'))
    rev=load('paper/results/bmc/revision_summary.json')
    check('Saved revision experiments complete',rev['complete'] and rev['test_outcome_audit_passed'] and rev['task_count']==43,'revision_summary.json')
    old=(ROOT/'paper/manuscript_bmc.tex').read_text()
    blocks=re.findall(r'\\begin\{table\}.*?\\end\{table\}',text,re.S)
    oldblocks=re.findall(r'\\begin\{table\}.*?\\end\{table\}',old,re.S)
    check('Three tables unchanged including every cell and interval',blocks==oldblocks and len(blocks)==3,'e7f4fc0 manuscript table blocks')
    # Recompute all primary means/SDs from individual saved query outcomes.
    groups=defaultdict(list)
    with open('paper/results/bmc/tables/primary_query_results.tsv') as f:
        for row in csv.DictReader(f,delimiter='\t'):
            groups[row['split_seed'],row['condition'],row['training_seed'],row['direction']].append(row)
    summaries={}
    with open('paper/results/v2/tables/primary_descriptives.tsv') as f:
        for row in csv.DictReader(f,delimiter='\t'):
            summaries[row['model'],row['direction'],row['metric']]=row
    for condition in ('paired','constant','random','shuffled'):
        for direction in (*DIRECTIONS,'equal_direction_macro'):
            metrics=['query_mean_nll','coverage','likelihood|hit_at_5']
            if condition!='constant': metrics+=['ranker|hit_at_5','fused|hit_at_5']
            for metric in metrics:
                vals=[]
                for split in ('17','3407','2026'):
                    fits=[]
                    for seed in ('3407','3508'):
                        dirs=DIRECTIONS if direction=='equal_direction_macro' else (direction,)
                        fits.append(statistics.mean(statistics.mean(float(r[metric]) for r in groups[split,condition,seed,d]) for d in dirs))
                    vals.append(statistics.mean(fits))
                expected=summaries[condition,direction,metric]
                check(f'Query reconstruction {condition}/{direction}/{metric}',
                      abs(statistics.mean(vals)-float(expected['mean']))<1e-12 and
                      abs(statistics.stdev(vals)-float(expected['sd_of_three_split_means']))<1e-12,
                      'query -> direction -> fitted seed -> split -> descriptive mean/sample SD')
    events=[]
    for (split,condition,seed,direction),rows in groups.items():
        if condition not in ('paired','constant'):continue
        count=sum(int(float(r['likelihood|hit_at_5'])) for r in rows)
        events.append({'split':split,'condition':condition,'seed':seed,'direction':direction,'events':count,'queries':len(rows)})
        expected=2 if (split,condition,seed,direction)==('17','paired','3407','delta_to_gamma') else (
                 1 if (split,condition,seed,direction)==('3407','paired','3508','delta_to_gamma') else 0)
        check(f'Primary likelihood events {split}/{condition}/{seed}/{direction}',count==expected,'primary_query_results.tsv')
    for d,expected in [('delta_to_gamma',(879,19,2)),('gamma_to_delta',(527,2,0))]:
        rows=groups['17','paired','3407',d]
        counts=(sum(float(r['coverage'])==0 for r in rows),
                sum(float(r['coverage'])>0 and float(r['likelihood|hit_at_5'])==0 for r in rows),
                sum(float(r['likelihood|hit_at_5'])>0 for r in rows))
        check('Illustrative failure-stage counts '+d,counts==expected,'saved query outcomes, no new experiment')
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


    # Recheck the numerical sequence in each complete results section moved
    # into the supplement. Cross-document figure/file numbers are excluded.
    def subsection(body, title):
        match=re.search(r'\\(?:sub)?section\{'+re.escape(title)+r'\}',body)
        if not match: raise AssertionError('Missing section '+title)
        return re.split(r'\\(?:sub)?section\{|\\end\{document\}',body[match.end():],maxsplit=1)[0]
    def number_tokens(body):
        body=re.sub(r'\\begin\{figure\}.*?\\end\{figure\}','',body,flags=re.S)
        body=re.sub(r'\\(?:ref|label)\{[^}]+\}','',body)
        body=re.sub(r'(?:Additional file|main Figure|Section)\s+\d+','',body)
        return re.findall(r'(?<![A-Za-z])\d+(?:\.\d+)?',body)
    migrations=[
        ('Denoising pretraining improves single-chain reconstruction','Denoising pretraining improves single-chain reconstruction'),
        ('Repaired unseen-gamma selection does not establish a conditional recovery advantage','Query-balanced unseen-gamma evaluation'),
        ('Withheld edges within the giant component have high prior and shuffled recovery','Within-component withheld-edge evaluation'),
        ('Directional diagnostics allow recovery of exposed targets','Directional exposure comparisons'),
        ('Study-level exposure sensitivity is directional and component-concentrated','Study-level exposure comparisons'),
        ('More sampling increases coverage without ensuring top-five recovery','Sampling budgets, decoding and calibration')]
    for previous,current in migrations:
        a=number_tokens(subsection(old,previous)); b=number_tokens(subsection(supplement,current))
        check('Migrated numbers in order: '+current,a==b,{'original_subsection':previous,'numerical_tokens':len(a)})
    oldsup=(ROOT/'paper/supplementary_methods_bmc.tex').read_text()
    for heading in ('Pretraining mixture and downstream sampling have distinct effects',
                    'Changing negative training does not resolve candidate scarcity'):
        check('Preserved sensitivity numbers: '+heading,
              number_tokens(subsection(oldsup,heading))==number_tokens(subsection(supplement,heading)),
              'original supplement vs new supplement, without figure/file numbering')
    citations=[]
    for group in re.findall(r'\\cite\{([^}]+)\}',text):
        for key in group.split(','):
            if key not in citations:citations.append(key)
    bib=re.findall(r'\\bibitem\{([^}]+)\}',text)
    refs=load('paper/supervisor_review/references.json')['references']
    check('18 citations match bibliography and verified records',citations==bib and set(bib)=={r['key'] for r in refs} and len(bib)==18,'first-citation order')
    for ref in refs:
        check('Reference metadata hash '+ref['key'],sha(ref['source'])==ref['source_sha256'],ref['source'])
        item=re.search(r'\\bibitem\{'+ref['key']+r'\}(.*?)(?=\\bibitem|\\end\{thebibliography\})',text,re.S)[1]
        present('Reference DOI '+ref['key'],ref['doi'],item,ref['source'])
        present('Reference year '+ref['key'],str(ref['year_in_bibliography']),item,ref['source'])
        for field in ('volume','pages_or_article'):
            if ref.get(field):
                norm=lambda v:str(v).replace('–','').replace('--','').replace('-','')
                check('Reference '+field+' '+ref['key'],norm(ref[field]) in norm(item),ref['source'])
        if ref['type']=='preprint':present('Preprint label '+ref['key'],'[preprint]',item)
    abstract=text.split(r'\begin{abstract}',1)[1].split(r'\end{abstract}',1)[0]
    abstract_words=len(prose_tokens(abstract))
    core=text.split(r'\section{Background}',1)[1].split(r'\section*{Abbreviations}',1)[0]
    core_words=len(prose_tokens(core))
    check('BMC abstract three-part structure',re.findall(r'\\textbf\{([^}]+)\}',abstract)==['Background:','Results:','Conclusions:'],'BMC research-article instructions')
    check('Abstract 250 to 350 words and citation-free',250<=abstract_words<=350 and r'\cite' not in abstract,{'words':abstract_words,'method':'prose_tokens, heading words included'})
    sections=re.findall(r'\\section\{([^}]+)\}',text)
    check('Main scientific sections',sections==['Background','Methods','Results','Discussion','Conclusions'],sections)
    for section,nextsection,expected in [('Methods','Results',6),('Results','Discussion',6),('Discussion','Conclusions',4)]:
        body=text.split(r'\section{'+section+'}',1)[1].split(r'\section{'+nextsection+'}',1)[0]
        check(section+' subsection count',len(re.findall(r'\\subsection\{',body))==expected,'requested structure')
    for source,body,nfig in [('manuscript.tex',text,6),('supplementary.tex',supplement,3)]:
        check(source+' no line numbering',r'\linenumbers' not in body and '{lineno}' not in body,'editable source')
        check(source+' A4/11pt/25mm/1.5 spacing',all(v in body for v in ('a4paper,11pt','margin=25mm',r'\onehalfspacing',r'\pagestyle{plain}')),'editable source')
        check(source+' empty author/date',r'\author{}' in body and r'\date{}' in body,'editable source')
        check(source+' no administrative or project-assistance narrative',not re.search(r'Pending author|author confirmation|ChatGPT|Codex|AI[- ]assisted|AI assistance|Author contributions|Funding\}|Ethics approval|Competing interests\}|Zihan He|Jia Meng|Xi.an Jiaotong',body,re.I),'supervisor PDF scope')
        labels=re.findall(r'\\label\{([^}]+)\}',body)
        check(source+' unique labels',len(labels)==len(set(labels)),'TeX labels')
        check(source+' resolved internal references',set(re.findall(r'\\ref\{([^}]+)\}',body))<=set(labels),'TeX labels')
        check(source+' figure count',len(re.findall(r'\\begin\{figure\}',body))==nfig,'figure blocks')
    check('S3 points to unchanged original Figure 7',r'figure_7_budget.pdf' in supplement and r'figure_7_budget.pdf' not in text and 'Figure S3' in text,'source include paths and cross-document citation')
    present('Figure 3 descriptive SD label','across-split descriptive SD, not confidence intervals',text)
    present('Figure 5 actual counts','725/1814/2249/7254 edges',text)
    present('Figure 5 nominal/actual caveat',r'nominal 50\% subset contains only 31.0\%',text)
    present('NLL hierarchy formula',r'\sum_{y\in P_q}\ell(q,y)',text)
    present('Same NLL hierarchy in supplement',r'\sum_{y\in P_q}\ell(q,y)',supplement)
    # Readable forms of ranges (e.g. Additional files 1 and 2) and individual mentions.
    check('All six Additional files described',all(f'Additional file {n} ' in text for n in range(1,7)),'Supplementary materials index')
    check('No obsolete main Figure 7 citation',not re.search(r'Figure\s*~?7\b',text+supplement),'Figure 7 is now S3')

    placement=[]
    document_records=[]
    docs=[('manuscript.tex','GDTCR_supervisor_review'),('supplementary.tex','GDTCR_supplementary'),
          ('review_notes.tex','GDTCR_review_notes'),('journal_comparison.tex','GDTCR_journal_comparison')]
    for source,name in docs:
        body=(OUT/source).read_text();pdf=BUILD/(name+'.pdf')
        record=load(str((BUILD/(name+'.render.json')).relative_to(ROOT)))
        check('Compiled source hash '+name,sha(OUT/source)==record['source_sha256'],'native compilation manifest')
        check('Compiled/readable PDF hash '+name,sha(pdf)==record['pdf_sha256']==sha(OUT/(name+'.pdf')),'native compilation and reading copy')
        check('No critical TeX diagnostics '+name,record['native_compilation_verified'] and not record['critical_tex_diagnostics'],'native compilation log')
        fonts=subprocess.check_output(['pdffonts',str(pdf)],text=True).splitlines()[2:]
        check('Embedded fonts, no Type 3 '+name,all(re.search(r'\byes\s+(?:yes|no)\s+(?:yes|no)\s+\d+\s+\d+\s*$',line) and 'Type 3' not in line for line in fonts),'pdffonts')
        with pdfplumber.open(pdf) as doc:
            check('Empty PDF Author '+name,not doc.metadata.get('Author'),'PDF metadata')
            check('A4 page sizes '+name,all(abs(p.width-595.276)<1 and abs(p.height-841.89)<1 for p in doc.pages),'PDF media boxes')
            if 'notes' in name or 'comparison' in name:check('One-page note '+name,len(doc.pages)==1,'PDF pages')
            pages=[p.extract_text() or '' for p in doc.pages]
            for p in doc.pages:
                check(f'Character page bounds {name}/{p.page_number}',all(-.5<=c['x0']<=c['x1']<=p.width+.5 and -.5<=c['top']<=c['bottom']<=p.height+.5 for c in p.chars),'character boxes; overlap checked visually')
            check('No missing glyph/reference markers '+name,all(not any(x in p for x in ('??','\ufffd','PERCENTTOKEN','XMLTOKEN','AMPERSANDTOKEN')) for p in pages),'pdftotext/pdfplumber and native compile')
            aux=(BUILD/'tex'/name/(Path(source).stem+'.aux')).read_text()
            labels=re.findall(r'\\label\{([^}]+)\}',body)
            for kind,prefix in [('Figure','fig:'),('Table','tab:')]:
                for label in (v for v in labels if v.startswith(prefix)):
                    m=re.search(r'\\newlabel\{'+re.escape(label)+r'\}\{\{([^}]+)\}\{([^}]+)\}',aux)
                    check('Compiled float label '+label,bool(m),'aux label record')
                    number,page=m[1],int(m[2])
                    caps=[i for i,p in enumerate(pages,1) if re.search(kind+r'\s*'+re.escape(number)+r':',p)]
                    check('Single intact caption '+label,caps==[page],caps)
                    cited=[i for i,p in enumerate(pages,1) if re.search(kind+r'\s*'+re.escape(number)+r'(?![0-9A-Za-z:])',p)]
                    placement.append({'document':name,'kind':kind,'label':label,'number':number,
                                      'first_citation_page':min(cited) if cited else None,'caption_page':page})
            document_records.append({'source':str((OUT/source).relative_to(ROOT)),'source_sha256':sha(OUT/source),
                                     'pdf':str(pdf.relative_to(ROOT)),'pdf_sha256':sha(pdf),'pages':len(doc.pages)})
    assets=[]
    for p in sorted((ROOT/'paper/results/bmc/figures').glob('*.pdf')):
        with Image.open(p.with_suffix('.png')) as im:dpi=im.info.get('dpi',(0,0));dims=im.size
        check('Editable/high-resolution assets '+p.stem,p.with_suffix('.svg').is_file() and min(dpi)>=299,{'pixels':dims,'dpi':dpi})
        assets.append({'id':p.stem,'pdf_sha256':sha(p),'svg_sha256':sha(p.with_suffix('.svg')),'png_sha256':sha(p.with_suffix('.png')),'pixels':dims,'dpi':dpi})
    write('placement_audit.json',placement)
    write('crossref_numerical_audit.json',{'passed':True,'checks':len(records),'records':records,
          'frozen_files':len(frozen['files']),'query_rows':sum(map(len,groups.values())),
          'primary_event_records':events,'references':len(refs),'abstract_words':abstract_words,
          'main_prose_words':core_words,'word_count_method':'prose_tokens: headings and numerical prose tokens included; abstract, bibliography, captions, tables and displayed/inline math omitted; guidance not a rigid limit',
          'scientific_discrepancies_found':[],'documents':document_records,'assets':assets,
          'scope':'Independent draft checks plus saved-result numerical logic adapted from the historical audit; no old pass result reused. Visual review and attachments have separate records.'})
    (OUT/'audit_failure.json').unlink(missing_ok=True)
    print(json.dumps({'passed':True,'checks':len(records),'abstract_words':abstract_words,'main_prose_words':core_words,'placement':placement},indent=2))

if __name__=='__main__':main()
