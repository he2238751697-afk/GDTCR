#!/usr/bin/env python3
"""Export the reviewed section record and sentence/context claim audit.

Judgments below are explicit editorial decisions, not an automatic truth check.
The numerical and execution audits are recorded separately.
"""
import csv
import hashlib
import json
import re
from pathlib import Path

PAPER=Path('paper')
MAIN=PAPER/'manuscript_bmc.tex'
PRIMARY='artifacts/completion_v2/final_evidence/evidence.json'
REVISION='paper/results/bmc/revision_summary.json'
TABLES='paper/results/bmc/tables/'

# (old issue, change, scientific-claim change, evidence, unresolved boundary)
META={
 'Title':('标题需要直接表述 benchmark 和 recorded-partner recovery。',
          '采用清单首选标题，保持单 CDR3、gamma-delta 和 exposure 定位。','定位明确；不新增功能主张。',PRIMARY,'作者信息待确认。'),
 'Abstract':('摘要过多审计细节，primary endpoint 不够突出。',
             '采用 Background/Methods/Results/Conclusions；保留核心 NLL 与自由恢复数值。','保留原阴性主结论。',PRIMARY,'远距离和生物学功能仍未验证。'),
 'Keywords':('检索关键词需要集中。','保留 5 个核心关键词。','无。',PRIMARY,'无科学遗留。'),
 'Background':('任务动机和 alpha/beta 文献易与 gamma/delta 恢复混淆。',
               '明确研究空白、三个问题、exposure 定义与不同文献任务；加入两篇最新文献。','收窄到同任务的记录配对恢复。','paper/references_bmc.json; '+PRIMARY,'文献更新为定向检索，并非系统综述。'),
 'Methods':('方法结构需要对应评价问题。','按数据、暴露、模型、排序、候选、统计及计算来源组织。','无。',PRIMARY,'原始与新增实验均保留其设计限制。'),
 'Data assembly and provenance':('来源集中性、供者限制及单链排除信息需要集中呈现。',
   '给出来源计数、边界处理、训练前排除及单链 train/validation 数量。','不再暗示供者独立性。','artifacts/completion_v2/data_audit_final.json; '+TABLES+'dataset_composition.tsv','一条 IEDB 原始研究未解析；供者元数据不足。'),
 'Exposure protocols and validation roles':('unseen-gamma 由单一查询选模；缺少 giant 内留边对照。',
   '保留主划分，新增 query-group 修复与保留两端训练暴露的留边诊断。','新增诊断；历史 unseen-gamma 结果降级并移入补充。','data/splits/revision_bmc/manifest.json; paper/revision_bmc_protocol.md; '+REVISION,'giant 测试仅一个原始分量，不给推断区间。'),
 'Generator, pretraining and matched controls':('超参数显示不全；random 对照计算匹配范围不清。',
   '补齐参数、腐蚀和四种对照；明确只匹配下游设置与名义预算。将 750-step 表述限定为单向敏感性对照，区分 1500-step directional exposure diagnostics 和单方向选模。','修正方法范围，不改数值；不声称总计算量匹配。','src/gdtcr/model.py; scripts/train_generator.py; configs/completion_v2/; '+TABLES+'revision_training.tsv','额外 matched-total-compute scratch 实验未做。'),
 'Separately trained pair ranking and reference methods':('清单 frozen encoder copy 与实际运行 freeze_encoder=false 冲突；缺少 nearest-input transfer。',
   '按运行记录写为可训练复制 encoder，原生成器固定；加入 k=1、k=5 transfer 和独立的 pool similarity endpoint。','修正方法描述；原主结果数值不变。','scripts/train_ranker.py; artifacts/completion_v2/ranker/main/split_seed17/seed-0/run.json; scripts/evaluate_transfer_bmc.py','复制表示与训练边共享；不声称独立数据或独立表征。'),
 'Free generation, retrieval and calibration':('候选存在性、truth injection、训练目标排除和校准含义需更明确。',
   '在 Results 前定义两类候选；保留 invalid/duplicate 不补抽和 target 排除边界。','校准仅作探索性 operating-point 分析。','scripts/evaluate_free_v2.py; scripts/prepare_candidate_pools_v2.py; scripts/calibrate_scores_v2.py','没有生物学概率或候选选择器验证。'),
 'Metrics, uncertainty and similarity audit':('事件计数、单位和零事件区间容易混读。',
   '补齐数学定义，规定 equal-direction query mean、分量/查询重采样和 distant 定义。','不把种子或划分视作独立生物重复。','src/gdtcr/statistics.py; '+TABLES+'primary_events.tsv; '+TABLES+'distant_summary.tsv','零事件 bootstrap 不是总体上界。'),
 'Computational provenance and AI assistance':('硬件、代码版本和 AI 披露需集中。',
   '区分原 A800 与新增 RTX 3090，写明冻结来源和辅助范围。','无新增性能或硬件主张。','artifacts/revision_bmc/slurm_accounting.json; configs/revision_bmc/; paper/BMC_REPRODUCIBILITY.md','公开仓库、DOI 和许可待补。'),
 'Results':('结果顺序需突出主终点与暴露诊断。','按数据特征、NLL、主恢复、检索、敏感性和暴露组织。','不删除零事件或负结果。',PRIMARY+'; '+REVISION,'所有新增拟合均是 revision-stage diagnostics。'),
 'The paired corpus is highly concentrated and near-neighbor exposed':('集中性被放在限制而未突出为数据特征。',
   '将来源、图规模、度异质性和 giant training assignment 放在结果开头。','加强数据适用范围说明。','artifacts/completion_v2/data_audit_final.json','以现有公开导出为总体；不是成人外周或供者独立样本。'),
 'Exact-chain exclusion leaves extensive near-neighbor exposure':('exact exclusion 容易被误读为 distant transfer。',
   '保留近邻计数并独立复核 5/5/3 distant edges。','明确不足以作稳定远距离推断。','artifacts/revision_bmc/primary_recheck.json; '+TABLES+'distant_edges.tsv','远距离边过少。'),
 'Denoising pretraining improves single-chain reconstruction':('reconstruction 不能作为 partner recovery 证据。',
   '仅对 frozen corruption 和 aligned-copy control 作解释。','收窄端点解释。','paper/results/v2/tables/denoising.tsv','重建是 validation endpoint。'),
 'Pretraining improves likelihood with a modest conditional contribution':('NLL 的小条件收益与预训练收益需要比较。',
   '核对 1.005/1.013/1.115 及方向值和每拟合配对区间。','保留 modest 而非夸大 conditional gain。','paper/results/v2/tables/primary_descriptives.tsv; paper/results/v2/tables/paired_endpoints.tsv','只适用于测试架构和预算。'),
 'Free recorded-partner recovery remains sparse':('极低百分比不足以体现事件稀少。',
   '突出 64 draws、coverage、likelihood/ranker/fusion 及 2/900、1/906 等计数。','原主负结果不变。',TABLES+'primary_events.tsv; '+TABLES+'primary_query_results.tsv','重复划分不合并为独立事件；零区间不是上界。'),
 'Retrieval depends on direction and distractor construction':('truth-containing pool 容易被当成生成能力。',
   '并列 neural/shallow/nearest-input 方法，另报结构性零 direct transfer。','加入新基线；不把零 transfer 当神经模型机制优势。','paper/results/v2/tables/retrieval.tsv; '+TABLES+'nearest_input_transfer.tsv','direct transfer 与 similarity retrieval 是不同端点。'),
 'Pretraining improves likelihood across nested graph subsets, but recovery remains sparse':('nominal 50% 和分量组成变化容易被误读。',
   '以 725/1814/2249/7254 实际边数解释曲线，并标出 full data 才包含 giant。','不声称纯 sample-complexity 或稳定恢复收益。','paper/results/v2/tables/free_runs.tsv; artifacts/completion_v2/data_audit_final.json','额外总计算量对照未做。'),
 'Negative-sampling sensitivity does not resolve candidate scarcity':('详细敏感性干扰主线，排序无法补回缺失候选。',
   '正文压缩核心负结果；完整 ratio/mixture 结果移入 Additional file 1。','不按测试结果更换 primary negative policy。','paper/results/v2/tables/paired_endpoints.tsv; paper/supplementary_methods_bmc.tex','只测试给定策略和预算。'),
 'Repaired unseen-gamma selection does not establish a conditional recovery advantage':('原选择集单 query/无 distractor，MRR 恒一。',
   '报告修复后 MRR、全对照事件数及配对区间；原结果移至补充。','新诊断替代历史诊断，不替换主结果。',REVISION+'; '+TABLES+'revision_query_results.tsv','64 查询且目标可暴露；无稳定 conditional-vs-prior 恢复优势。'),
 'Withheld edges within the giant component have high prior and shuffled recovery':('缺少区分 unseen component 与 exposed within-component 的对照。',
   '报告 coverage、所有对照、ranker 和 k=1/5 transfer 的事件数。','新增诊断，保留强 prior/shuffled 及 ranker 劣于 likelihood 的结果。',REVISION+'; '+TABLES+'nearest_input_transfer.tsv','500 边全来自一个原始分量，不能生成推断性分量区间。'),
 'Directional diagnostics allow recovery of exposed targets':('与双链未见主测试混为一种泛化。',
   '保留 unseen-delta、seen-input 的结果并强调目标暴露、查询组单位。','不将高恢复改称 robust generalization。','paper/results/v2/tables/free_runs.tsv; paper/results/v2/tables/paired_endpoints.tsv','不同总体与监督组成；部分原方向任务未运行 shuffled。'),
 'Study-level exposure sensitivity is directional and component-concentrated':('source holdout 容易误称 donor-independent external validation。',
   '报告 prior/shuffled、聚集事件与训练规模差异，改为 exposure sensitivity。','不删去严格 source 上的正差值，但保留区间达零与集中性。','paper/results/v2/tables/source_event_clusters.tsv; paper/results/v2/tables/free_runs.tsv','无供者独立性；exposure 与训练组成共同变化。'),
 'More sampling increases coverage without ensuring top-five recovery':('更多采样、排除 policy 与校准可能被当成新主终点。',
   '区分 prefix/coverage/order；保持主规则，校准及实例为探索性。','不以测试 policy 取代 primary endpoint。','paper/results/v2/tables/budgets_and_policies.tsv; paper/results/v2/tables/calibration.tsv; paper/results/v2/tables/sampling_grid.tsv; paper/results/v2/tables/qualitative_examples.tsv','校准正例少；无功能选择器主张。'),
 'Discussion':('需优先回答主问题并前置 graph/proximity 限制。',
   '以 NLL 与候选稀缺分离开头，纳入修复/giant/NN 的限定解释与未来设计原则。','明确当前模型的失败不等价于内在不可预测。',PRIMARY+'; '+REVISION,'未做 total-compute、外部供者队列或功能验证。'),
 'Conclusions':('重复讨论且需防止扩大范围。',
   '压缩为一段：NLL 改善、恢复稀少、无主 ranker 收益、exposure/graph 限制。','保留原主科学结论。',PRIMARY+'; '+REVISION,'适用范围严格限定。'),
 'Abbreviations':('需提供 BMC 缩略语表。','列出正文缩写。','无。','paper/manuscript_bmc.tex','无科学遗留。'),
 'Availability of data and materials':('公开 persistent identifier 缺失。','写明来源 accession、本地包及未建立的公开归档。','不声称已公开存档。','paper/BMC_AUTHOR_ITEMS.md; data/provenance/manifest.json','repository/DOI、上游再分发许可仍待作者落实。'),
 'Code availability':('repository/archive/license 未建立。','集中语言、环境和源码包位置。','不推定许可。','paper/BMC_AUTHOR_ITEMS.md; artifacts/completion_v2/environment.json','公开地址、归档版本和许可待确认。'),
 'Additional files':('需要有序、可审查、单件不超 20 MB 的附件。','定义 6 个本地附件及 editable source 包，附哈希验证。','无。','scripts/build_bmc_revision_package.py; paper/BMC_SUPPLEMENT_INDEX.md','这些是本地候选包，不代表期刊提交或公共存档。'),
}
for name in ('Ethics approval and consent to participate','Consent for publication','Competing interests','Funding',"Authors' contributions",'Acknowledgements'):
    META[name]=('缺少可核验的作者事实。','按用户明确答复保留待确认，不代填无冲突/无基金/豁免。','不虚构事实。','paper/BMC_AUTHOR_ITEMS.md','作者已确认当前全部待确认；实际投稿前须补齐。')


def sections(text):
    abstract=re.search(r'\\begin\{abstract\}(.*?)\\end\{abstract\}',text,re.S)
    title=re.search(r'\\title\{([^\n]+)\}',text)
    keyword=re.search(r'\\noindent\\textbf\{Keywords:\}.*?(?=\\section)',text,re.S)
    yield 'Title',title.group(0),text[:title.start()].count('\n')+1
    yield 'Abstract',abstract.group(0),text[:abstract.start()].count('\n')+1
    yield 'Keywords',keyword.group(0).strip(),text[:keyword.start()].count('\n')+1
    headings=list(re.finditer(r'\\(?:section|subsection)\*?\{([^{}]+)\}',text))
    for i,m in enumerate(headings):
        end=headings[i+1].start() if i+1<len(headings) else text.index(r'\begin{thebibliography}')
        yield m.group(1),text[m.start():end].strip(),text[:m.start()].count('\n')+1


def context(name):
    primary={'test':'Frozen primary test; reconstruction/selection explicitly separate',
       'split':'Whole-component and both-chain disjoint; no donor claim',
       'truth':'Free: no injected positive; NLL evaluates known positives',
       'events':'Sparse: gamma likelihood 0 in all fits; delta 2/900 and 1/906, otherwise 0; not pooled',
       'unit':'Complete test components; seed-averaged split SD descriptive',
       'neighbor':'Extensive near-neighbor exposure; only 5/5/3 distant edges',
       'overlap':'No exact supervised target overlap in primary test',
       'role':'Primary fixed 64-draw endpoint; NLL/coverage secondary'}
    if name in ('Title','Keywords','Background','Methods','Results','Abbreviations'):
        primary.update(test='Framing, literature or section organization; not a new test estimate',events='Not an event-count claim',role='Definitions and scope')
    if name in ('Data assembly and provenance','The paired corpus is highly concentrated and near-neighbor exposed','Exact-chain exclusion leaves extensive near-neighbor exposure'):
        primary.update(test='Observed corpus/split/proximity audit',truth='No ranking candidate endpoint',events='9068 pairs; 8443 from main study; giant 5005; distant 5/5/3',role='Dataset characterization; not functional or transfer validation')
    if name=='Denoising pretraining improves single-chain reconstruction':
        primary.update(test='Frozen denoising validation, not paired test recovery',split='Unique-CDR3-disjoint pretraining train/validation; paired chains excluded',truth='Teacher-forced reconstruction, not free candidates',events='Residue accuracy over frozen corruptions; not partner-hit events',unit='Two model seeds shown separately',overlap='Paired-corpus chains excluded',role='Reconstruction sanity endpoint')
    if 'Retrieval depends' in name:
        primary.update(truth='Recorded positives injected into fixed pools; direct transfer separately has no injection',events='Per-fit pool counts and nearest_input_transfer.tsv; no single scorer dominates',role='Secondary retrieval; new nearest-input baseline is revision diagnostic')
    if 'Repaired unseen' in name:
        primary.update(test='Repaired-selection refits on unchanged 907-edge / 64-query test',split='Gamma input disjoint; targets may overlap',events='Conditional 8/64,10/64; prior 8/64,9/64; ranker 6/64,8/64',unit='64 source-query groups, conditional paired bootstrap',overlap='252 distinct target deltas exposed in training',role='Revision-stage diagnostic; selection MRR is validation, not test')
    if 'Withheld edges within' in name:
        primary.update(test='500 held giant-component test edges',split='Edges held; both chain endpoints supervised-exposed',events='Conditional 60/177,50/177 and 123/261,118/261; prior/shuffled strong',unit='One original component: counts and point estimates only',neighbor='Exact endpoint exposure by construction',overlap='Every test target appears in supervised training',role='Revision-stage within-component diagnostic')
    if 'Directional diagnostics' in name:
        primary.update(split='Unseen-input or seen-input/withheld-edge; target overlap allowed',events='161 unseen-delta; 450 seen-gamma; 264 seen-delta queries; per-fit events retained',unit='Source-query groups',overlap='Target exposure allowed; input exposure depends on task',role='Directional diagnostic populations')
    if 'Study-level exposure' in name:
        primary.update(split='Strict held-study chain exclusion vs source-shared; not donor-independent',events='Strict delta 50/419,43/419; shared 199/419,186/419; gamma 0',unit='90 test components; largest dominates hits',neighbor='No source-test edge passes strict distant criterion',overlap='Strict: no supervised overlap; shared: 144 gamma and 13 delta overlaps',role='Study-level exposure sensitivity; training size changes')
    if 'More sampling' in name:
        primary.update(test='Split-17 test for prefixes/policies; tuning and calibration are validation roles',truth='Free candidates, nested saved 16/64/256 prefixes',events='Test primary events sparse; calibration gamma zero and delta only 1-6 positives',role='Budget/policy/calibration diagnostics; primary rule unchanged')
    if 'nested graph' in name or 'Negative-sampling' in name:
        primary.update(events='Zero or few free events; fitted results preserved separately',role='Sensitivity, not a newly selected primary protocol')
    if name in ('Abstract','Discussion','Conclusions'):
        primary.update(test='Synthesis: primary test and explicitly identified exposure diagnostics',split='Primary component-disjoint; diagnostics have different exposure populations',truth='Free versus truth-containing retrieval explicitly distinguished',overlap='None in primary; permissible exposure only in identified diagnostics',role='Bounded synthesis of primary and diagnostic evidence')
    if name in ('Exposure protocols and validation roles','Generator, pretraining and matched controls','Separately trained pair ranking and reference methods','Free generation, retrieval and calibration','Metrics, uncertainty and similarity audit','Computational provenance and AI assistance'):
        primary.update(test='Methods / executed settings; no new outcome inferred',split='Protocol-specific; primary, directional, source and giant explicitly distinguished',truth='Candidate construction explicitly distinguishes free and fixed pools',events='Definitions/settings; per-fit events in Additional file 4',unit='Components or source queries; no giant inferential interval',overlap='Protocol-specific overlap audited',role='Methods and limitations')
    if name in ('Availability of data and materials','Code availability','Additional files','Ethics approval and consent to participate','Consent for publication','Competing interests','Funding',"Authors' contributions",'Acknowledgements'):
        primary={k:'Administrative statement; not an experimental claim' for k in primary}
        primary['role']='Pending author facts' if name!='Additional files' else 'Local release-candidate inventory'
    return primary


def prose_sentences(body):
    body=re.sub(r'(?<!\\)%[^\n]*','',body)
    body=re.sub(r'\\begin\{(table|equation)\}.*?\\end\{\1\}',' ',body,flags=re.S)
    body=re.sub(r'\\(?:section|subsection)\*?\{[^{}]+\}','',body)
    body=body.replace(r'\begin{abstract}','').replace(r'\end{abstract}','')
    body=re.sub(r'\s+',' ',body).strip()
    # Decimal points have no trailing whitespace and remain intact.
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+(?=[A-Z0-9\\])',body) if s.strip()]


def main():
    text=MAIN.read_text();digest=hashlib.sha256(text.encode()).hexdigest()
    revision=json.load(open(REVISION));assert revision['test_outcome_audit_passed']
    log=['# BMC 逐节修改记录','',
         '本记录对应 `paper/manuscript_bmc.tex`，SHA256 `'+digest+'`。',
         '比较基准：保留不变的 `paper/manuscript_v2.tex` 与原审阅 PDF。每节按清单第 28 节列出六项；下列 TeX 块是最终修改文本，可直接审查。',
         '','重要差异：清单要求 frozen encoder copy，但真实配置 `freeze_encoder=false`。已按实际执行记录改写为可训练复制 encoder、固定原生成器；不改动冻结主结果。',
         '','新增任务 43/43 完成。unseen-gamma 修复、giant 留边和最近输入基线全部为 revision-stage diagnostics。作者事实及公开仓库/DOI/许可依用户答复保持待办。','']
    claims=[]
    for name,body,line in sections(text):
        if name not in META:raise ValueError('Missing reviewed section: '+name)
        old,change,claim,evidence,open_item=META[name]
        log.extend(['## '+name,'','1. **修改前问题：** '+old,'2. **采取的修改：** '+change,
            '3. **修改后的文本：**','','```tex',body,'```','',
            '4. **科学 claim 是否改变：** '+claim,'5. **实验／数字来源：** '+evidence,
            '6. **尚未解决：** '+open_item,''])
        ctx=context(name)
        for i,sentence in enumerate(prose_sentences(body),1):
            administrative=ctx['role'].startswith('Pending')
            claims.append({'id':f'C{len(claims)+1:03d}','section':name,'section_start_line':line,
                'sentence_in_section':i,'exact_tex_sentence':sentence,
                'Q1_test_or_validation':ctx['test'],'Q2_disjointness':ctx['split'],
                'Q3_truth_in_candidates':ctx['truth'],'Q4_event_sufficiency':ctx['events'],
                'Q5_uncertainty_unit':ctx['unit'],'Q6_neighbor_exposure':ctx['neighbor'],
                'Q7_training_target_overlap':ctx['overlap'],'Q8_primary_or_diagnostic':ctx['role'],
                'Q9_biological_function':'No study result is interpreted as functional/binding evidence; background citations identify their own tasks',
                'Q10_model_scope':'Tested architecture, dataset and budget only; no universal impossibility/capability claim',
                'evidence':evidence,'unresolved_boundary':open_item,
                'review_decision':'pending author fact; not submission-ready' if administrative else 'retained with the stated endpoint and scope',
                'source_sha256':digest})
    bibliography=re.search(r'\\begin\{thebibliography\}.*?\\end\{thebibliography\}',text,re.S).group(0)
    log.extend(['## References','','1. **修改前问题：** 需要最新检索与逐条 DOI、卷期、文章编号核查。',
        '2. **采取的修改：** 16 条文献核验，添加 DTCR 及明确标注为 preprint 的 retrieval exposure 文献；修正 metadata typo。',
        '3. **修改后的文本：**','','```tex',bibliography,'```','',
        '4. **科学 claim 是否改变：** 更新背景；不把不同任务当作本任务性能基线。',
        '5. **实验／数字来源：** `paper/BMC_REFERENCE_AUDIT.md` 与缓存的 Crossref/Europe PMC/publisher metadata。',
        '6. **尚未解决：** 检索截至 2026-10-06；实际投稿若延后须再更新。',''])
    for kind in ('table','figure'):
        for i,m in enumerate(re.finditer(r'\\begin\{'+kind+r'\}.*?\\end\{'+kind+r'\}',text,re.S),1):
            log.extend([f'## {kind.title()} {i}','','1. **修改前问题：** '+('表格需核对数值、标题及统计解释。' if kind=='table' else '图号、流程、端点、曝光总体及图例需要符合新结构。'),
                '2. **采取的修改：** '+('保留主结果数字；补分量归属及完整图注定义。' if kind=='table' else '重绘统一七张主图；新架构流程为 Figure 1，新增诊断进入 Figure 6。'),
                '3. **修改后的文本：**','','```tex',m.group(0),'```','',
                '4. **科学 claim 是否改变：** 原主结论不变；仅 Figure 4/6 加入明确标注的新诊断。',
                '5. **实验／数字来源：** '+PRIMARY+'；'+REVISION+'；`scripts/plot_revision_bmc.py`。',
                '6. **尚未解决：** 内置编译器平台错误；独立 PDF/SVG/PNG 与审阅 PDF 已检查。',''])
    supplement=PAPER/'supplementary_methods_bmc.tex'
    log.extend(['## Supplementary material','','1. **修改前问题：** 方法细节、历史问题及敏感性需有独立可编辑附件。',
        '2. **采取的修改：** 新建 Additional file 1；六件附件分别存放数据、拟合、事件、划分及代码记录。',
        '3. **修改后的文本：**','','```tex',supplement.read_text().strip(),'```','',
        '4. **科学 claim 是否改变：** 历史 unseen-gamma 降级；新增分析始终标为诊断，source-balanced/component-size 为 post-hoc 描述。',
        '5. **实验／数字来源：** `paper/BMC_SUPPLEMENT_INDEX.md` 和各附件 `MANIFEST.json`。',
        '6. **尚未解决：** 本地包不含大型权重和全部 free draw 原始文件；保留哈希和重跑说明，公开分发许可待作者落实。',''])
    (PAPER/'BMC_REVISION_LOG.md').write_text('\n'.join(log))
    with (PAPER/'BMC_CLAIM_AUDIT.tsv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(claims[0]),delimiter='\t',lineterminator='\n');writer.writeheader();writer.writerows(claims)
    report={'source_sha256':digest,'sentences':len(claims),
        'scope':'All prose sentences in main scientific sections and declarations; figures/tables and bibliography have separate numerical/layout/reference audits',
        'method':'Sentence inventory with explicitly reviewed section-specific answers to the ten checklist questions; not automatic semantic verification',
        'author_facts_pending':True,'public_deposition_pending':True,
        'scientific_review':'bounded recorded-partner claims retained; original negative outcomes preserved',
        'revision_tasks':revision['task_count']}
    (PAPER/'results/bmc/claim_audit_summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))

if __name__=='__main__':main()
