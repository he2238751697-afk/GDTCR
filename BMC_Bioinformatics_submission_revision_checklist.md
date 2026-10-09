# BMC Bioinformatics 投稿版修改清单

> 2026-10-09 当前状态：已完成作者审阅前版本的科学一致性修订、原生 LaTeX 编译和 40 页主稿／6 页补充说明的逐页视觉检查；原始输入导出、代码及初始化权重已公开于 GitHub 的 reproducibility-v1 发布。作者尚未审阅，通讯邮箱、贡献及其他声明仍待确认，代码／权重许可待定，Zenodo 认证和 DOI 发布由用户延后。完整交付与审计见 [final_submission/README.md](paper/final_submission/README.md)，剩余事项见 [BMC_AUTHOR_ITEMS.md](paper/BMC_AUTHOR_ITEMS.md)。下方 2026-10-06 状态保留为历史记录，不代表当前编译或仓库状态。

> 适用稿件：`gdtcr_anonymous.pdf`
> 目标期刊：BMC Bioinformatics（首选）
> 文章定位：controlled benchmark / evaluation study of single-CDR3 recorded-partner recovery in human gamma-delta TCRs
> 执行原则：先解决 scientific validity，再做 narrative/English，再做 journal formatting。禁止为了提高结果观感而删除、替换或弱化 negative results。

## 0. Codex 总执行规则

### 0.1 论文定位必须固定
- 将论文核心贡献固定为：**controlled benchmark of single-CDR3 recorded-partner recovery under explicit exposure protocols**。
- 不把文章定位为“validated TCR design system”。
- 不声称 biological specificity、binding probability、functional receptor activity，除非新增实验真正支持。
- 不把模型 NLL 改善等同于 partner recovery 改善。
- 不把 retrieval（真值注入 candidate pool）与 free generation（模型自己产生 candidate）混为同一个 endpoint。
- “recorded partner”统一作为主要术语；避免把数据库记录的 paired chain 写成 biological/functional partner。

### 0.2 不允许自动改动科学结论
- 所有数值必须从现有结果文件/代码重新读取或核对，不得凭文本记忆修改。
- 若正文数字与表格/代码不一致，以冻结的分析产物为准，并记录修正。
- 不删除 negative / zero-event result 以改善叙事。
- 不把 exploratory、diagnostic、post-hoc analysis 改写成 primary confirmatory result。
- 不把 component bootstrap interval 写成传统 iid confidence interval。
- 不把两个模型 seed 或三个 graph splits 当作独立 biological replicates。

### 0.3 术语统一
统一检查并规范：
- gamma-delta / γδ
- gamma chain / δ chain（首次出现给出完整名称）
- CDR3
- recorded partner
- conditional model
- constant-source / target-prior control
- random initialization
- shuffled-input control
- free generation
- fixed-pool retrieval
- pair ranker / separately trained ranker
- chain-disjoint / component-disjoint / source holdout
- Hit@5 / Recall@5 / MRR / NLL
- near-neighbor / distant-sequence evaluation

---

# 1. Abstract

## 必须修改

### A1. 重写成 BMC 风格的四段式逻辑
保持：**Background → Methods → Results → Conclusions**。

### A2. 删除 Abstract 中过度审计化的细节
从 Abstract 删除或显著压缩：
- “all six fitted paired intervals...”
- “5,005-edge component dominates...”
- “only 5, 5 and 3 primary-test edges...”
- 具体 seed / split / bootstrap 细节

这些移动到 Results/Methods。

### A3. Abstract 只保留最关键数字
建议保留：
- 9,068 unique human CDR3 pairs
- pretrained conditional NLL vs constant-source vs random initialization
- 64-draw primary free-generation Hit@5
- ranker primary result

### A4. 明确 primary endpoint
Abstract 必须明确：primary endpoint 是 **equal-direction mean query-macro Hit@5 at 64 draws**。

### A5. 结论严格限定
将 conclusion 明确写成：
- pretraining improved target-token likelihood;
- conditional information beyond the matched target prior was small/modest;
- free recorded-partner recovery remained sparse;
- separately trained reranking did not show reproducible primary benefit;
- higher recovery under exposed/source-specific protocols is interpretation-sensitive;
- biological function and distant-sequence transfer remain unresolved。

## 强烈建议修改
- 将第一句从泛泛的“recovering partner...”改为明确提出 benchmark problem。
- 将“single-chain denoising”改为更可读的“single-chain denoising pretraining”。
- 把“independent pair ranker”统一改为 **separately trained pair ranker** 或 **separately optimized pair ranker**。

## 可选修改
- Keywords 控制在 4–8 个，避免把所有指标都放进去。
- Abstract 避免连续出现超过 2 个百分比数字。

---

# 2. Title

## 必须修改
选择一个明确表述“benchmark + recorded partner recovery”的标题。

优先：
**Benchmarking single-CDR3 partner recovery in human gamma-delta T-cell receptors under controlled exposure protocols**

备选：
**A controlled benchmark of single-CDR3 recovery of recorded partners in human gamma-delta T-cell receptors**

## 强烈建议修改
- 避免标题暗示 de novo TCR design。
- 避免使用“functional partner”或“specificity”。

## 可选修改
- 全文首次出现时使用 `gamma-delta T-cell receptor (γδ TCR)`，标题可使用 gamma-delta 以提高可检索性。

---

# 3. Background

## 必须修改

### B1. 第一段必须从“pairing is biologically relevant”转向“evaluation problem”
建立三步逻辑：
1. γδ TCR 是 paired receptor；
2. paired repertoire data 允许学习 sequence regularities；
3. single-chain generation 可以产生 plausible sequences，但未必恢复 recorded partner。

### B2. 明确研究空白
把 gap 写成：
> 缺少一个在同一任务下严格区分 target prior、conditional information、free candidate availability、retrieval 与 exposure 的 γδ TCR partner-recovery benchmark。

### B3. 重新表述 alpha/beta 相关文献
不要暗示 alpha/beta pairing 结果可以直接迁移到 γδ。
明确说明 population/input/task/endpoints 不同。

### B4. 三个 research questions 保留，但语言简洁化
建议最终为：
1. Does denoising pretraining improve downstream partner modeling relative to matched random initialization?
2. Does the input chain improve recorded-partner recovery beyond a matched target prior?
3. Does separate pairwise ranking improve candidate ordering under fixed and free-candidate settings?

## 强烈建议修改
- 加一个简短的 **Study overview / Contributions** 结尾段。
- 明确“recorded-pair recovery”是 benchmark endpoint，不等价于 biological interaction。
- 引入“exposure protocol”术语，并在 Background 末尾说明为什么必须控制它。

## 可选修改
- 减少对具体数据库和前人模型的逐篇描述；把细节压到 Related Work 段。

---

# 4. Methods

# 4.1 Data assembly and provenance

## 必须修改
- 更清晰地列出每个 source 的 pair 数量：GSE180059、Suo et al./UcTCRdb、IEDB export。
- 明确 8,443/9,068（93.1%）来自 GSE180059，指出这一集中性是 dataset characteristic，不要只在 limitation 中出现。
- 明确 paired corpus 是 **publicly recorded pairing**，不是完整生物学 pairing ground truth。
- 保留 source membership、barcode 和 available V/J annotations，但明确模型只使用 CDR3。
- 说明 donor identity 无法从现有 exports 完整恢复，并因此不声称 donor-independent validation。

## 强烈建议修改
- 增加一个 `Dataset composition` 小表或转入 Table 1。
- 明确不同 source 的 CDR3 boundary processing convention 可能不同。

---

# 4.2 Pretraining data

## 必须修改
- 明确 paired-corpus sequences 被排除出 pretraining。
- 给出过滤前/后的 gamma/delta sequence counts。
- 明确 pretraining train/validation 完全 disjoint 的单位是 unique CDR3 sequence。
- 在 supplement 提供 SHA256 manifest 或说明其位置。

## 强烈建议修改
- 把“raw / processed / split / provenance artifact”整理成一个 reproducibility subsection，而不是散落在 Methods。

---

# 4.3 Exposure protocols and graph splitting

## 必须修改

### M1. 加一幅正式的 split schematic
正文必须让读者一眼理解：
- paired records = bipartite graph edges
- nodes = unique gamma/delta CDR3
- primary split = whole connected-component assignment
- no exact gamma/delta overlap across primary partitions

### M2. 明确 giant component 问题
写明：largest component = 5,005 edges（55.2%），被整体分配到 training。

### M3. 不再把所有 exposure protocol 当作同一种 validation
明确分类：
- **Primary component-disjoint evaluation**
- **Unseen-input diagnostic**
- **Seen-input / withheld-edge diagnostic**
- **Strict study holdout diagnostic**
- **Source-shared sensitivity analysis**

### M4. 解决 unseen-gamma checkpoint selection 问题
必须重新检查/修改 validation selection，使其不由单一 gamma query（581 partners）决定。

如果历史实验不能重跑：
- 降级为 exploratory diagnostic；
- 不得将其用于支持 robust unseen-gamma generalization claim；
- 在 Results 及 figure caption 中显著标注。

### M5. 重新命名“study holdout”
使用：**study-level exposure sensitivity analysis** 或 **source-exposure analysis**，不要称 external validation。

## 强烈建议修改
- 新增 **nearest-input partner transfer baseline**：根据 training 中最相似输入链寻找其 recorded partner，测试模型收益是否超过 sequence proximity transfer。
- 新增或至少实施 **within-giant-component edge-held-out analysis**，区分“unseen component”与“大组件内的 edge prediction”。

## 可选修改
- 给每个 split 提供 component-size distribution。
- supplement 提供 graph statistics 完整表。

---

# 4.4 Generator architecture

## 必须修改
- 补齐 PDF 中显示为空缺/缺失的超参数字段，例如 learning rate、top-p、fusion weight 等。
- 对所有关键超参数逐项核对代码/配置文件，不能保留空白。
- 给出总参数量、层数、hidden width、heads、FFN width、dropout、max length。

## 强烈建议修改
- 在正文保留关键 architecture 参数，其余放 Supplementary Table。
- 明确 chain identity / control token 的含义。

## 必须修改
- 增加模型架构图，并将其设置为主文 **Figure 1**。架构图不是装饰图，而是让读者在进入 Results 前明确 benchmark 的输入、输出、训练阶段和评价路径。
- Figure 1 必须同时表达 **task definition + denoising pretraining + conditional generation + separately trained ranker + controlled evaluation workflow**。

## 强烈建议修改
- Figure 1 采用 4-panel 结构：
  - **A. Task definition**：gamma CDR3 → recorded delta partner，以及 delta CDR3 → recorded gamma partner；明确 prediction target 是 `recorded partner CDR3`。
  - **B. Denoising pretraining**：single-chain sequence → corruption/masking/deletion → Transformer → reconstructed sequence；明确 paired-corpus chains excluded from pretraining。
  - **C. Conditional generation and ranking**：input CDR3 → shared encoder/decoder → generated partner candidates；同时从 frozen encoder copy → separately trained ranker → candidate score。
  - **D. Benchmark/evaluation**：free generation 与 fixed-pool retrieval 分开，并展示 exposure protocols、coverage、Hit@5、Recall/MRR、similarity/leakage audit。
- Figure 1 的视觉重点应是 **benchmark design > model architecture**，不要做成“模型宣传图”。
- 图中给出关键 architecture 参数：7.40M parameters、4 encoder layers、4 decoder layers、256 hidden width、8 attention heads、1024 FFN、0.1 dropout、maximum 64 tokens。
- 明确 ranker 使用 fine-tuned generator encoder 的 frozen copy，不能视觉上制造“independent data/model”印象。

## 可选修改
- 将详细 tensor dimensions、token-level implementation 和 negative-sampling 细节移至 Supplementary。

---

# 4.5 Denoising pretraining

## 必须修改
- 明确 mask rate 15% / 30%、80/10/10 replacement、deletion strategy。
- 明确 damaged-mask definition，避免读者误解 selected-but-unchanged 是否算 corrupted。
- 明确 denoising validation 仅用于验证 reconstruction，不用于证明 partner recovery。

## 强烈建议修改
- 把 aligned-copy control 单独介绍为 sanity control。
- 明确 pretraining-vs-random comparison 不是 matched total-computation comparison，因为 pretrained model 有额外 denoising compute。

## 可选修改
- 将完整 corruption protocol 放 Supplementary Methods。

---

# 4.6 Paired fine-tuning and controls

## 必须修改
- 清晰列出四个核心 conditions：
  1. pretrained conditional
  2. matched constant-source prior
  3. random initialization
  4. shuffled-input control
- 说明 constant-source control 只改变 source residues，其余 initialization / target sampling / optimization 不变。
- 说明 random initialization 不等于 equal-compute comparison。

## 强烈建议修改
- 把每个 control 的“它控制了什么”整理成一个小表。
- 统一“target prior / constant source”术语。

---

# 4.7 Pair ranker

## 必须修改
- 全文删除“independent ranker”作为可能误解为 independent data 的表达。
- 统一为 `separately trained ranker`。
- 明确 ranker 使用 fine-tuned generator encoder 的 frozen copy，因此不是 independent representation pretraining、不是 independent cohort。
- 明确训练数据仍来自相同 training edges。
- ranker 的 subsequent optimization independence 要写清楚。

## 强烈建议修改
- 增加一个 baseline hierarchy：likelihood → conditional-minus-prior → shallow feature model → nearest-neighbor → separately trained ranker。

## 可选修改
- 将详细 negative construction 放 Supplementary Methods，但正文保留 primary 3:1 mixed negative design。

---

# 4.8 Candidate generation and fixed-pool retrieval

## 必须修改
- 在正文明确区分：
  - free generation：candidate existence is not guaranteed;
  - fixed-pool retrieval：true recorded positives are injected into candidate pool。
- 这是全文关键概念，必须在 Results 前定义清楚。
- 明确 invalid/duplicate draws 不 replacement。
- 明确 train-target exclusion 在不同 evaluation settings 下可能删除 legitimate recorded positives，因此只能作为 sensitivity/policy analysis。

## 强烈建议修改
- Figure 2 与 Figure 3 caption 中分别再次强调这一区别。

---

# 4.9 Metrics and statistical analysis

## 必须修改
- 给出数学定义：Coverage、Hit@5、Recall、MRR、mean positive rank。
- 明确 primary endpoint：equal-direction mean of query-macro Hit@5 at 64 draws。
- 明确 bootstrap unit：complete test component；directional task 使用 source query groups。
- 明确 two seeds / three splits are not independent biological subjects。
- 明确 intervals are conditional/descriptive and no multiplicity adjustment。
- 不把 zero-event [0,0] bootstrap interval 写成 population upper bound。

## 强烈建议修改
- 把 pooled AUROC/AUPRC 降级为 secondary diagnostic，并明确 labels/scores do not define biological specificity。
- 对每个主要 endpoint同时报告 event count，例如 `2/900`，避免仅给 0.22%。

## 可选修改
- supplement 给出每个 query-level metric distribution。

---

# 4.10 Similarity audit

## 必须修改
- 明确 distance 定义、序列范围（完整 CDR3 / internal / terminal）和至少 3 edits threshold。
- 用此分析支持“exact exclusion ≠ distant generalization”。
- 不把 5/5/3 distant edges 当作稳定统计估计。

## 强烈建议修改
- 增加 nearest-neighbor transfer baseline，使 similarity audit 从“描述”升级为直接 benchmark control。

---

# 4.11 Computational provenance / AI assistance

## 必须修改
- 保留 Python / PyTorch / CUDA / GPU 信息。
- 给出代码仓库或归档版本。
- 将 OpenAI coding assistant disclosure 重新组织为简洁、合规的 AI-use statement：用于 code development、orchestration、artifact checking、literature organization、drafting；scientific interpretation and responsibility remain with authors。
- 不要暗示 AI 为作者。

## 强烈建议修改
- 增加 `Code availability`，包括 repository、archived DOI/version、OS、Python version、license、requirements。
- 发布 frozen configurations、seeds、candidate hashes。

---

# 5. Results

# 5.1 Paired corpus characterization

## 必须修改
结果标题改成能直接表达发现，例如：
**The paired corpus is highly concentrated and near-neighbor exposed**

必须突出：
- 9,068 pairs
- 3,944 gamma nodes / 6,989 delta nodes
- 3,294 components
- 2,897 singleton components
- 5,005-edge largest component = 55.2%
- 93.1% pairs from GSE180059
- degree heterogeneity

## 强烈建议修改
- 把 dataset concentration 从“限制”提升为主要 benchmark result。

---

# 5.2 Pretraining / denoising

## 必须修改
- denoising result 只用于证明 model learned reconstruction beyond copy control。
- 不要在这一节暗示 downstream partner recovery 已被证明。

## 强烈建议修改
- 标题建议：
  **Denoising pretraining improves single-chain reconstruction**

---

# 5.3 Likelihood results

## 必须修改
- 修复 PDF 中目前缺失的数值占位/空值问题。
- 明确 1.005 vs 1.013 的差异小于 1.115 vs 1.005 的 pretraining effect。
- 强调 conditional-vs-prior effect 是 modest，而不是 large。

## 强烈建议修改
- 同时报告 mean ± split SD 和 paired interval。
- 不仅报告 aggregate number，也报告 direction-specific NLL。

---

# 5.4 Primary free-generation recovery

## 必须修改
这一节成为全文核心结果。

必须直接呈现：
- 64 draws
- coverage
- likelihood Hit@5
- ranker Hit@5
- fused Hit@5
- gamma→delta vs delta→gamma
- event counts

核心结论：
**Likelihood improvement did not translate into reliable free recorded-partner recovery.**

## 强烈建议修改
- 把 0.03% 这种极小百分比同时写成实际 event counts。
- 解释 candidate scarcity 是 failure mode，而不是仅仅“accuracy is low”。

---

# 5.5 Retrieval / ranking

## 必须修改
明确说明 Figure 3 的 fixed pools 包含 truth，因此不能与 free generation 直接比较。

## 强烈建议修改
- 重点展示：不同 scorer 在不同 distractor pool 中不具有一致 dominance。
- 将 shallow length/terminal-feature model 与 ranker 放在一起，证明 ranking gains 可能来自简单 sequence properties。

---

# 5.6 Data efficiency

## 必须修改
- 明确 nested graph subsets 并非单纯 sample-size curve。
- 725/1,814/2,249/7,254 edges 的 component composition 不同。
- nominal 50% 只有 31.0%，不能写成真实 50%。

## 强烈建议修改
- 标题改成：
  **Pretraining improves likelihood across nested graph subsets, but recovery remains sparse**

---

# 5.7 Negative sampling sensitivity

## 必须修改
- 这一节降级为 robustness/sensitivity result。
- 明确 ranker cannot create candidate sequences absent from free sampler。

## 可选修改
- 移到 Supplementary Results，正文只保留一句核心结论。

---

# 5.8 Exposure protocols

## 必须修改
这是第二核心结果。

必须把：
- primary both-chain-unseen
- unseen input
- seen input / unseen edge
- strict study holdout
- source-shared
分开标识为不同 exposure populations。

## 强烈建议修改
避免使用：
- “generalization improves to 45.9%”

改成：
- “recorded-partner recovery was higher under target-exposed/source-specific protocols”

并强调：这些任务不是 donor-independent prospective validation。

---

# 5.9 Sampling and calibration

## 必须修改
- 保留 16/64/256 draws 的 coverage vs Hit@5 dissociation。
- 强调更多 draws 增加 coverage，但不保证 top-five recovery。
- calibration 只作为 exploratory operating-point analysis，不要声称 useful biological selector。

## 可选修改
- calibration 细节可全部移至 Supplementary。

---

# 6. Discussion

## 必须修改

### D1. 第一段必须直接回答 primary question
首段建议围绕：
> sequence-modeling quality improved, but free recorded-partner recovery remained extremely sparse under strict chain-disjoint evaluation.

### D2. 明确三层指标的逻辑关系
必须明确区分：
1. likelihood
2. candidate coverage / free generation
3. recorded-partner ranking/recovery

### D3. 明确 ranker negative result 是信息，不是失败
强调：separately trained ranker did not show reproducible primary benefit。

### D4. 对高 recovery protocol 限制表述更严格
不得称作 external validation 或 biological generalization。

### D5. Giant component / near-neighbor exposure 必须成为主要 limitation
不要埋在 Discussion 后半段。

### D6. 明确模型限制
当前 architecture/budget 不代表所有模型的上限；random-init comparison 也不是 fully computation-matched。

### D7. 明确 biological interpretation boundary
只能讨论 sequence-level recorded pairing，不讨论 function、binding、specificity。

## 强烈建议修改
用一个小段落明确列出“what this benchmark establishes / what it does not establish”。

### 可以明确写入：
**Establishes**
- audited benchmark protocol;
- sparse free recovery under primary chain-disjoint setting;
- small conditional likelihood contribution;
- sensitivity to exposure and graph structure。

**Does not establish**
- biological receptor function;
- antigen specificity;
- donor-independent validation;
- distant-sequence generalization;
- intrinsic impossibility of partner prediction。

## 可选修改
- 最后一段可改成未来 benchmark design principles，而非泛泛“future work”。

---

# 7. Conclusion

## 必须修改
压缩为 1–2 段，避免重复 Discussion。

必须保留三个点：
1. lower NLL after denoising;
2. sparse free partner recovery and no reproducible ranker benefit;
3. exposure/graph dependence limits generalization claims。

## 强烈建议修改
最后一句落在 benchmark methodology：
> Future γδ TCR pairing studies should report sequence modeling, candidate availability, recovery, and exposure dependence as separate endpoints.

---

# 8. Figure 1 — Model architecture and benchmark workflow

## 必须修改
Figure 1 改为全文总览图，标题建议：
**Overview of the single-CDR3 partner-recovery benchmark and model workflow**

Figure 1 必须让读者一眼看到：
- 输入：single gamma or delta CDR3；
- 目标：recorded partner CDR3；
- pretraining：single-chain denoising；
- paired fine-tuning：conditional generation；
- candidate scoring：separately trained ranker；
- evaluation：free generation / fixed-pool retrieval / exposure-controlled diagnostics。

## 强烈建议修改
采用 4-panel 结构：
- **A. Task definition**：`gamma CDR3 → delta CDR3` 与 `delta CDR3 → gamma CDR3`；标注 recorded partner。
- **B. Denoising pretraining**：single-chain sequence → corruption → shared Transformer → reconstruction。
- **C. Generation + ranker**：conditioned input → encoder-decoder → candidate sequences；parallel branch 为 frozen encoder copy → separately trained ranker → score。
- **D. Evaluation**：free candidate generation 与 truth-containing fixed retrieval pool 明确分叉；下方放 exposure protocols 与 primary endpoint。
- 图中使用不同视觉编码区分 **training / candidate generation / ranking / evaluation**。
- 不在架构图中暗示 biological function、binding affinity 或 antigen specificity。

## 可选修改
- 详细 architecture hyperparameters 放 Supplementary Table。
- 如果版面允许，在 Figure 1 右下角加入一个 mini schematic：`sequence prior → conditional information → recovery`，帮助读者理解 benchmark 的核心问题。

# 9. Figure 2 — Pairing graph concentration and sequence exposure

## 必须修改
将现有 Figure 1 改编号为 Figure 2。

Figure 2 负责：
1. pairing graph structure；
2. giant component concentration；
3. near-neighbor exposure。

必须检查：
- panel labels；
- legend；
- axis labels；
- exact `5,005` / `55.2%`；
- distance definition；
- primary split designation。

## 强烈建议修改
- visually highlight the largest component。
- 在同一图中明确展示 primary component-disjoint allocation。
- 将 near-neighbor exposure 与 distant subset 分开表现。

## 可选修改
- 若信息过多，把 detailed graph statistics 放 Supplementary，Figure 2 保留最关键的 graph/proximity evidence。

# 10. Figure 3 — Primary free-generation result

## 必须修改
将现有 Figure 2 改编号为 Figure 3。

必须明确：
- primary free-generation result at 64 draws；
- training targets allowed；
- conditional / constant-source / random / shuffled-input conditions；
- coverage；
- likelihood Hit@5；
- ranker Hit@5；
- fused Hit@5。

## 强烈建议修改
- 图中直接给出 event counts（例如 `2/900`）。
- NLL improvement 与 recovery outcome 使用不同视觉编码，避免读者把 likelihood gain 误认为 recovery gain。

# 11. Figure 4 — Fixed-pool retrieval and ranking

## 必须修改
将现有 Figure 3 改编号为 Figure 4。

Figure 4 caption 第一段必须声明：
> fixed pools contain recorded positives by construction.

必须区分：
- random small pools；
- length-matched pools；
- motif-matched pools；
- edit-neighbor pools；
- full target universe。

## 强烈建议修改
统一比较：
- conditional likelihood；
- target prior；
- conditional-minus-prior；
- shallow feature model；
- nearest-input transfer baseline；
- separately trained ranker。

并强调：没有单一 scorer 在所有 retrieval conditions 下都占优。

# 12. Figure 5 — Data-efficiency and pretraining sensitivity

## 必须修改
将现有 Figure 4 改编号为 Figure 5。

- 明确 nominal 50% 实际为 31.0%。
- 强调 sample size 与 component composition 同时变化。
- shading 不得写成 confidence interval。

## 强烈建议修改
- 在 full-data point 标出 giant component enters。
- 图中注明 725/1,814/2,249/7,254 edges。
- 如果 pretraining-mixture sensitivity 仍保留在主文，与 data-efficiency 用 panel 或 supplementary 明确区分。

# 13. Figure 6 — Exposure protocols

## 必须修改
将现有 Figure 5 改编号为 Figure 6。

必须分别标注：
- primary component/chain-disjoint；
- unseen-input；
- seen-input / withheld-edge；
- strict study holdout；
- source-shared。

必须标注 query population、training composition 与是否存在 target/source exposure。

unseen-gamma 的 single-query checkpoint-selection pathology 必须在 caption 中明确。

strict study holdout 不得称 donor-independent external validation。

## 强烈建议修改
- 用视觉分组区分 primary result 与 diagnostic/sensitivity analyses。
- 每个 exposure result 同时标出 event count。

# 14. Figure 7 — Sampling budget and calibration

## 必须修改
将现有 Figure 6 改编号为 Figure 7。

- 明确 16/64/256 draws 的 prefix relationship。
- 区分 training targets allowed vs excluded。
- 左侧强调 coverage 与 Hit@5 的 dissociation。
- 右侧 calibration 仅作为 exploratory operating-point analysis。
- 不把 calibration 写成 validated biological candidate selector。

## 强烈建议修改
- calibration 若版面紧张可移到 Supplementary。

# 14. Table 1

## 必须修改
当前 Table 1 内容较好，但需要增加 dataset/exposure context。

建议列：
- split seed
- train/validation/test edges
- test gamma queries
- test delta queries
- gamma 1-edit-to-pretraining
- gamma >=3 edits-to-pretraining
- distant test edges
- largest-component assignment

## 强烈建议修改
- 将 `distant edges` 定义写入 table legend。
- 在表注中说明它不是 donor-level external validation。

---

# 15. Table 2

## 必须修改
- 核对所有当前 PDF 中疑似丢失/空缺的数值字段。
- 每个百分比同时保留统一 precision。
- `Equal mean` 必须明确是 two directions weighted equally。
- `dash` 与 `0` 的语义保持一致。

## 强烈建议修改
- 增加 event counts（例如 `2/900`）到 Supplementary Table，而正文表保留 percentage。
- 在表注明确 SD 是 across split means，不是 subject-level SD。

---

# 16. Table 3

## 必须修改
- 把所有 contrast definition 放到 caption。
- 明确 negative NLL difference favors first named condition。
- 明确 Hit@5 difference 单位为 percentage points。
- 明确 no multiplicity adjustment。
- 明确 zero-event interval 不构成 population upper bound。

## 强烈建议修改
- 增加 `event count` 或 supplementary paired query table。
- 让每个 contrast 都能追溯到 Table 2。

---

# 17. Supplementary material

## 必须修改
至少准备：
- Supplementary Methods：完整 corruption、negative sampling、candidate construction、bootstrap details。
- Supplementary Table：dataset/source composition。
- Supplementary Table：all seeds / checkpoints / actual exposure。
- Supplementary Table：query-level primary results。
- Supplementary files：all frozen candidate pools / hashes / split assignments（在许可允许的前提下）。

## 强烈建议修改
把以下内容从正文降到 Supplement：
- detailed negative ratio sensitivity;
- temperature/top-p grid;
- calibration curves;
- deterministic example queries;
- full pretraining mixture sensitivity。

## 可选修改
- 增加 `Data Card` 与 `Model Card`，但需在 manuscript 主文中简洁引用。

---

# 18. Declarations

## 必须修改

### Ethics approval and consent to participate
当前 wording 不能保留“作者将确认”这种未来式占位。
投稿前必须给出真实、可核验的声明。

根据具体 source 和学校/机构要求，选择：
- Not applicable；或
- secondary-use determination / exemption 信息。

绝对禁止假设 exemption；必须由作者确认。

### Consent for publication
当前“submission-specific consent remains for authors to confirm”必须删除。
如果确实不涉及可识别个体、图片或可识别信息，可按期刊允许的格式写 `Not applicable`，但最终由作者确认。

### Competing interests
必须恢复最终真实声明，例如：
`The authors declare that they have no competing interests.`
如果存在利益冲突，按真实情况填写。

### Funding
必须恢复真实 funding information；如果没有 funding，明确写 `This research received no specific grant from any funding agency...` 或符合事实的等效声明。

### Authors' contributions
恢复真实作者、贡献和 corresponding author 信息。

### Acknowledgements
恢复真实 acknowledgement；AI assistant 可以按期刊政策披露，但不列为作者。

### Availability of data and materials
这是投稿前的 P0 项。
不能继续使用：
`No public deposition identifier ... is asserted in this anonymous version.`

应给出：
- source accessions / repository identifiers;
- processed benchmark data location（如可公开）；
- frozen split identifiers;
- code repository;
- archived release DOI;
- access restrictions / redistribution limits。

### Code availability
建议单独增加 section，包含：
- project name;
- repository;
- archived version / DOI;
- OS;
- programming language;
- dependencies;
- license;
- use restrictions。

---

# 19. References

## 必须修改

### R1. 投稿前更新 literature
必须重新检索到投稿日附近的最新 γδ TCR pairing / generation / protein LM / TCR modeling / benchmark 文献。

### R2. 核对每一条 DOI、卷期、页码/文章编号
当前 References 中至少应逐条验证。

### R3. 引用 database / software 时补齐正式 citation
包括 UcTCRdb、TCRdb、OTS、IEDB 等，并区分 database article 与 web resource。

### R4. 避免不可追溯的非正式引用
所有关键 baseline 和 benchmark claim 必须对应可公开核验的论文或 preprint。

### R5. 数据集必须可追溯
GEO/IEDB/UcTCRdb 等数据 source 要求在 References 或 Data Availability 中可核验。

## 强烈建议修改
- 给新增的 nearest-neighbor baseline / graph-split methodology 加方法学引用（只有确有对应经典方法时才引用）。
- 让 Related Work 不超过正文合理篇幅，避免大量 baseline paper 堆砌。

## 可选修改
- 用 reference manager 统一 BibTeX 格式。

---

# 20. BMC Bioinformatics 版式合规检查

## 必须修改
- 使用可编辑的 DOC/DOCX/RTF/TeX/LaTeX 主稿，不提交 PDF 作为唯一 production source。
- 使用双倍行距。
- 主稿包含 line numbering 和 page numbering。
- 不使用 page breaks。
- 特殊字符正确嵌入。
- 图按首次出现顺序编号并上传。
- 多 panel figure 作为单个 composite file 上传。
- figure title ≤15 words；figure legend ≤300 words。
- figure key 放在 graphic 内，不放 legend。
- 表格按出现顺序编号并引用。
- table title ≤15 words；table legend ≤300 words。
- table 不使用颜色/shading 表达信息。
- 数值中不要使用逗号作为千位分隔符。
- Additional files 按 `Additional file 1`, `Additional file 2`... 命名并在正文依次引用。
- additional file 单个文件不超过 20 MB。
- Data Availability 使用期刊推荐句式并包含 persistent identifier。

## 强烈建议修改
- Figure vector graphics 优先 PDF/EPS；位图至少保持约 300 dpi at final size。
- 所有字体嵌入图形。
- 统一 Figure 1–7 的字体、线宽、marker、panel label、decimal precision。
- Table 不做成图片。

## 可选修改
- 使用 Springer Nature LaTeX template。
- 尽量让正文、图、表、supplementary 在 source tree 中可一键重建。

---

# 21. 主文结构（最终 BMC 版）

建议 Codex 最终整理为：

1. Title
2. Abstract
3. Keywords
4. Background
5. Methods
   - Data assembly and provenance
   - Pretraining data and denoising
   - Pairing graph and exposure protocols
   - Conditional generator
   - Paired fine-tuning and controls
   - Separately trained pair ranker
   - Candidate generation and retrieval
   - Metrics and statistical analysis
   - Similarity audit
   - Computational reproducibility and AI assistance
6. Results
   - Corpus concentration and near-neighbor exposure
   - Denoising reconstruction
   - Likelihood improvement
   - Sparse free partner recovery
   - Retrieval and ranking
   - Data-efficiency sensitivity
   - Exposure-protocol sensitivity
   - Sampling/calibration diagnostics
7. Discussion
8. Conclusions
9. Abbreviations
10. Availability of data and materials
11. Code availability
12. Ethics approval and consent to participate
13. Consent for publication
14. Competing interests
15. Funding
16. Authors' contributions
17. Acknowledgements
18. References
19. Figure legends
20. Tables / Additional files as appropriate

---

# 22. 投稿前 P0 实验与分析任务

按优先级执行，不满足这些条件不要提交：

## P0-1 Nearest-input partner transfer baseline
目的：判断模型收益是否超过 sequence-neighborhood transfer。

## P0-2 修复 unseen-gamma validation
目的：避免 single-query checkpoint selection 导致 metric degeneracy。

## P0-3 Giant-component sensitivity
至少新增一种分析区分：
- complete-component exclusion；
- within-large-component held-out edges。

## P0-4 Distant-sequence evaluation
重新确认当前 distant edges 数量，并明确仅 5/5/3 时不能做稳定 inferential claim。

## P0-5 Public reproducibility package
准备：
- code
- frozen split
- config
- seeds
- candidate hashes
- environment
- Zenodo/archive

---

# 23. P1 强烈建议实验

- additional matched-compute random initialization comparison;
- per-direction confidence / event-count report;
- component-size sensitivity;
- near-neighbor strata performance;
- source-balanced descriptive analysis；
- nearest-neighbor baseline。

---

# 24. P2 可选实验

- larger protein LM / alternative architecture；
- additional sampler/decoder comparison；
- donor-aware evaluation（只有 metadata 足够时）；
- independent newly frozen cohort；
- structural or functional validation（如果未来扩展研究问题）。

---

# 25. 英文语言统一与降重

## 必须修改
- 删除内部实验日志风格表达，如 `v1`, `v2`, `historical completion protocol` 等，除非用于 reproducibility appendix。
- 删除对内部 checkpoint step 的过度描述，除非是关键 validation pathology。
- 每段只表达一个 claim。
- 降低名词堆叠。
- 将过长句拆开。

## 强烈建议修改
避免：
- “establishes” 用在仅由当前实验支持的 descriptive result 上；
- “generalization” 用在 target-exposed/source-shared task；
- “independent” 用在共享 data/encoder provenance 的 ranker；
- “accuracy” 用于 free partner recovery，除非 metric 定义确为 accuracy。

建议频繁使用：
- recorded-partner recovery
- under the primary chain-disjoint setting
- diagnostic
- sensitivity analysis
- descriptive
- does not establish
- sequence-level evidence

---

# 26. 最终 claim-audit

Codex 在生成最终稿前必须执行一次逐句 audit：

### 每个强结论都回答
1. 结果是否真的在 test set 上？
2. test 是否 chain/component/source disjoint？
3. candidate 是否包含 truth？
4. event count 是否足够？
5. uncertainty unit 是什么？
6. 是否存在 sequence-neighbor exposure？
7. 是否存在 training-target overlap？
8. 是否属于 diagnostic 而非 primary endpoint？
9. 是否把 sequence-level pairing 说成 biological function？
10. 是否把 model result 泛化到所有模型/所有 γδ TCR？

任何不能回答清楚的问题，都必须弱化 claim 或补实验。

---

# 27. 最终投稿前检查表

- [x] Figure 1 已改为模型架构 + benchmark workflow 总览图，且明确 task / pretraining / generation / ranker / evaluation
- [x] Title 已改为 benchmark / recorded-partner framing
- [x] Abstract 已压缩并突出 primary endpoint
- [x] Background 明确 gap / contributions
- [x] nearest-neighbor baseline 已完成
- [x] unseen-gamma validation 已修复或明确降级为 exploratory
- [x] giant-component sensitivity 已完成
- [x] 所有 Methods 超参数完整无空白
- [x] 所有 Results 数值与代码/表格核对
- [x] 所有 primary endpoint 给出 event counts
- [x] Figure 1–7 caption 合规且 self-contained
- [x] Table 1–3 数值、标题、legend 合规
- [x] Supplementary files 完整并在正文依次引用
- [ ] Data Availability 完成真实 repository / accession / DOI
- [ ] Code Availability 完成 repository / archive / license
- [ ] Ethics / consent / COI / funding / contributions / acknowledgement 完成真实声明
- [x] References 全部核验并更新到投稿前最新文献
- [ ] PDF 不再出现 anonymous / withheld / must be confirmed 等最终稿占位
- [x] 主文符合双倍行距、页码、行号等 BMC submission requirements
- [x] Figures / tables 均有 editable source
- [x] 最终 claim audit 通过


> 2026-10-06 执行状态：本地科学修订与 43 个新增任务完成。上方四项行政／公开发布要求仍未完成，依用户确认保留待办。版式勾选指可编辑源文件和已检查的审阅 PDF；内置 TeX 编译器返回平台目录错误，native compilation 未验证。清单的 frozen encoder copy 与真实 `freeze_encoder=false` 冲突，按实际执行记录修正。P1 总计算量匹配及 P2 独立队列／功能验证未执行，未写成已完成。详细证据见 `paper/BMC_REVISION_STATUS.md`、`paper/BMC_REVISION_LOG.md`。

# 28. Codex 执行输出要求

每完成一个 section，Codex 必须输出：
1. 修改前问题；
2. 采取的修改；
3. 修改后的文本；
4. 是否改变任何科学 claim；
5. 涉及的实验/数字来源；
6. 尚未解决的问题。

如果发现数据、代码和 manuscript 不一致：**停止修改该处文字，先报告 discrepancy。**
如果某项实验尚未完成：**标记 TODO，不得伪造结果。**
如果期刊格式要求与当前 scientific narrative 冲突：**优先保留 scientific validity，再做版面调整。**
