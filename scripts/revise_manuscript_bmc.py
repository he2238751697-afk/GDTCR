#!/usr/bin/env python3
"""Create the BMC scientific revision while retaining the frozen v2 manuscript."""
import re
from pathlib import Path

SOURCE = Path('paper/manuscript_v2.tex')
TARGET = Path('paper/manuscript_bmc.tex')

def replace_section(text, start, end, replacement):
    a,b=text.index(start),text.index(end,text.index(start)+len(start))
    return text[:a]+replacement+'\n\n'+text[b:]

def main():
    if TARGET.exists():
        raise FileExistsError('Edit the existing BMC source; do not regenerate over follow-up edits')
    t=SOURCE.read_text()
    t=t.replace(r'\documentclass[10pt]{article}',r'\documentclass[12pt]{article}')
    t=t.replace(r'\usepackage{graphicx}',r'\usepackage{graphicx}'+'\n'+r'\usepackage{setspace,lineno}'+'\n'+r'\doublespacing'+'\n'+r'\pagestyle{plain}')
    t=t.replace(r'\begin{document}',r'\begin{document}'+'\n'+r'\linenumbers')
    t=t.replace(r'\title{A controlled benchmark of single-CDR3 partner recovery for human gamma-delta T-cell receptors}',r'\title{Benchmarking single-CDR3 partner recovery in human gamma-delta T-cell receptors under controlled exposure protocols}')
    t=t.replace(r'\author{Anonymous submission}',r'\author{Author details pending confirmation}')
    abstract=r'''\begin{abstract}
\textbf{Background:} Single-chain receptor models can generate plausible CDR3
sequences without recovering the partner recorded for an input chain. A
benchmark must distinguish sequence priors, conditional information, candidate
availability and exposure to related sequences.

\textbf{Methods:} We assembled 9068 unique human gamma-delta T-cell receptor
CDR3 pairs and compared a denoising-pretrained conditional Transformer with
matched constant-source, random-initialization and shuffled-input controls.
The primary endpoint was equal-direction mean query-macro Hit@5 at 64 draws
under component-disjoint splitting. Free generation, fixed-pool retrieval and
additional exposure protocols were evaluated separately, including a separately
trained pair ranker.

\textbf{Results:} Mean target-token negative log likelihood was 1.005 nats for
the pretrained conditional model, 1.013 for the matched constant-source prior
and 1.115 for random initialization. Primary free-generation likelihood Hit@5
was 0.03\%; ranker Hit@5 was 0.06\%, without a reproducible improvement across
fitted comparisons. Recovery was higher under some target-exposed and
source-specific protocols, alongside substantial prior-model recovery.

\textbf{Conclusions:} Denoising pretraining improved target-token likelihood,
while the conditional contribution beyond the matched target prior was modest.
Free recorded-partner recovery remained sparse, and separately trained
reranking did not show reproducible primary benefit. Higher recovery in exposed
populations is sensitive to evaluation design. Biological function and
transfer to distant sequences remain unresolved.
\end{abstract}'''
    t=replace_section(t,r'\begin{abstract}',r'\noindent\textbf{Keywords:}',abstract)
    t=t.replace('Gamma-delta T-cell receptors are heterodimers','Gamma-delta T-cell receptors (\\gd{} TCRs) are heterodimers')
    t=t.replace('and an independent','and a separately trained').replace('independently trained ranker','separately trained ranker')
    t=t.replace('Independent reranking','Separately trained reranking').replace('independent ranker','separately trained ranker').replace('independent-ranking benefit','separate-ranking benefit')
    t=t.replace('Independent\nreranking','Separate\nreranking')
    t=t.replace('Here we ask three questions. Does single-chain denoising improve a matched\nconditional model relative to random initialization? Does the input CDR3 improve\nrecorded-partner recovery beyond a constant-source target prior? Does an\nseparately trained ranker improve ordering or support useful rejection of\nlow-scoring candidates?',
'''Here we ask three questions. Does denoising pretraining improve downstream
partner modeling relative to matched random initialization? Does the input
chain improve recorded-partner recovery beyond a matched target prior? Does
separate pairwise ranking improve ordering in fixed and free-candidate settings?''')
    # The previous grammar can also retain the original article after replacement.
    t=t.replace('Does an\nindependently trained ranker improve ordering or support useful rejection of\nlow-scoring candidates?', 'Does separate pairwise ranking improve ordering in fixed and free-candidate settings?')
    overview=r'''The benchmark addresses the lack of a common evaluation that separates target
priors, conditional information, free candidate availability, truth-containing
retrieval and sequence exposure within this gamma-delta task. An exposure
protocol specifies which input chains, target chains and graph components have
been seen during training. Our contribution is a controlled comparison with
saved candidates and explicit endpoint definitions, rather than a claim of
validated receptor function (Figure~\ref{fig:workflow}). Recent epitope-conditioned
diffusion models address a different generation task \cite{dtcr}; a recent
immune-receptor retrieval preprint further motivates checking alignment
baselines and clonal exposure \cite{germline_shortcut}. Neither supplies a direct
performance baseline for single-CDR3 gamma-delta recorded-partner recovery.
'''
    t=t.replace(r'\section{Materials and methods}',overview+'\n'+r'\section{Methods}')
    t=t.replace('Two pairs occur in both major sources.', 'Two pairs occur in both major sources. GSE180059 contributes 93.1\\% of the\nunique-pair union; this source concentration is a defining dataset characteristic.\nThese are publicly recorded pairings, not a complete biological pairing ground truth.\nDataset composition and full processing details are provided in Additional file 1;\nsource and split tables are provided in Additional file 2.')
    t=t.replace('The models use CDR3 alone.','The models use CDR3 alone. Donor identity cannot be fully recovered from these\nexports, so no evaluation is described as donor-independent. Source-provided\nCDR3 boundary conventions can differ across collections.')
    t=t.replace('with disjoint validation sets of 3,818 and 25,114 sequences.', 'with validation sets of 3818 and 25114 sequences. Training and validation are\nfully disjoint at the unique CDR3-sequence level.')
    t=t.replace('SHA256 manifests identify raw,\nprocessed, split and provenance artifacts.', 'SHA256 manifests identify raw, processed, split and provenance artifacts;\ntraining seeds, selected checkpoints and actual exposure appear in Additional file 3.')
    t=t.replace('The largest component is assigned to training.', 'The largest component, containing 5005 edges (55.2\\%), is assigned wholly to\ntraining (Figure~\\ref{fig:data}).')
    t=t.replace('These protocols are not donor-independent\nprospective external validation.', 'These are study-level exposure sensitivity analyses. They do not provide\ndonor-independent prospective validation.')
    t=t.replace('The v2\ncompletion protocol was specified after examining historical v1 results; it is\nnot a preregistration of the historical study. V1 estimates retain their earlier\nselection and decoded-output validity rules and are excluded from v2 summaries.', 'The primary analysis protocol was specified after earlier exploratory results\nhad been examined. It is not a preregistration; the earlier estimates, which\nused different selection and output-validity rules, are excluded from the\nreported primary summaries. Version history is retained in the reproducibility appendix.')
    start='Grouped allocation has an important directional exception.'
    end=r'\subsection{Generator, pretraining and matched controls}'
    repair=r'''The original unseen-gamma validation allocation contained one selection query
with 581 recorded targets and no ranking distractors. Its ranker MRR was
therefore identically one, and generator selection depended on one input. We
retain those results as exploratory diagnostics and repair selection without
changing training, aggregate validation or test membership. Whole gamma-query
groups are reassigned by query count with fixed seed 7319, producing 31/16/16
selection/tuning/calibration queries. Selection now includes 275 edges and at
least 118 eligible distractors per query. Conditional, constant-source and
random-initialized generators and the conditional ranker are refitted for two
seeds. Fixed 64-draw likelihood and ranker results are reported without new
fusion or threshold tuning. This repair is a revision-stage sensitivity analysis.

A separate within-giant-component diagnostic reserves 1000 edges from the
split-17 training graph, removing each edge only while both endpoints retain
training edges. Fixed seeds 1729 and 1730 define reservation and assignment of
500 validation and 500 test edges. The remaining training set contains 6254
edges; every test input and target is still exposed in supervised training.
All 500 validation edges select checkpoints, with no subsequent sampling,
score or threshold tuning. The original primary validation and test edges do
not enter this fit. Because all held edges originate from one component, we
report seed-specific point estimates and event counts without a component-based
inferential interval. This measures withheld-edge recovery within an exposed
component, a distinct population from unseen-component recovery.
'''
    t=replace_section(t,start,end,repair)
    t=t.replace('The generator is a shared encoder--decoder Transformer', 'Figure~\\ref{fig:workflow} shows the training and evaluation paths.\nThe generator is a shared encoder--decoder Transformer')
    t=t.replace('Random initialization changes\nonly initial weights. Edge-uniform sampling is a separate control.', 'Random initialization changes only initial weights. It matches downstream\ntraining settings but receives no denoising pretraining, so this is not a\nmatched-total-computation comparison. Shuffled-input evaluation applies a\ndeterministic query permutation to the fitted conditional model, disrupting the\ninput--recorded-partner association. Edge-uniform sampling is a separate control.\nThe roles of these four controls are summarized in Additional file 1.')
    t=t.replace(r'\subsection{Independent pair ranking and reference methods}',r'\subsection{Separately trained pair ranking and reference methods}')
    t=t.replace('The v2 ranker starts', 'The ranker starts')
    t=t.replace('Independence\nrefers to its subsequent parameters and optimization; it does not use an\nindependent training cohort or update the frozen generator.', 'The copied encoder and ranking head are optimized on the same training edges\nused by the generator. The original generator remains frozen, but the copied\nencoder is trainable. Separate training refers to the subsequent parameters\nand optimization; neither the representations nor the cohort are independent.')
    needle=r'\subsection{Free generation, retrieval and calibration}'
    nearest=r'''A complementary nearest-input partner-transfer baseline finds the closest
training input using normalized full-CDR3 Levenshtein distance, resolves ties
lexicographically, and proposes that input's recorded training partners. Targets
are ordered by descending training degree and then lexicographically, retaining
at most 64 unique candidates. A fixed five-neighbor sensitivity concatenates
those lists in neighbor order. No test target is injected into these proposals;
under exact target exclusion their recovery is necessarily zero. For frozen
retrieval pools, a separate nearest-input partner-similarity score ranks each
candidate by its minimum normalized distance to any partner of the single
nearest training input. This similarity extension scores truth-containing
pools and is not direct partner transfer.
'''
    t=t.replace(needle,nearest+'\n'+needle)
    t=t.replace('Candidates are evaluated both with and without exact training targets.', 'Candidates are evaluated both with and without exact training targets. The\nexclusion policy may remove legitimate recorded positives in exposed-target\nsettings, and is reported only as a separate sensitivity analysis. Free\ngeneration does not guarantee that any recorded partner exists among candidates.')
    t=t.replace('For query $q$, let $P_q$ be its recorded test partners and $C_q$ its unique valid\ncandidates. Coverage is $\\mathbf{1}(P_q\\cap C_q\\ne\\varnothing)$; Hit@$K$ records\nany partner among the top $K$ candidates, while Recall@$K$ is the recovered\nfraction of $P_q$. MRR uses the first recorded partner, assigning zero if absent.\nMean positive rank averages all partner ranks, assigning $|C_q|+1$ to absent\npartners.',r'''For query $q$, let $P_q$ be its recorded test partners, $C_q$ its unique valid
candidates and $C_q^{(K)}$ its first $K$ ranked candidates. Define
\begin{equation}
\mathrm{Coverage}(q)=\mathbf{1}(P_q\cap C_q\ne\varnothing),\qquad
H_K(q)=\mathbf{1}(P_q\cap C_q^{(K)}\ne\varnothing).
\end{equation}
\begin{equation}
R_K(q)=\frac{|P_q\cap C_q^{(K)}|}{|P_q|}.
\end{equation}
If $r_q(t)$ is the one-based candidate rank, reciprocal rank is
$1/\min_{t\in P_q\cap C_q}r_q(t)$ when a partner is present and zero otherwise.
Mean positive rank is $|P_q|^{-1}\sum_{t\in P_q}\widetilde r_q(t)$,
where $\widetilde r_q(t)=r_q(t)$ for present partners and $|C_q|+1$ for absent
partners. MRR averages reciprocal rank across queries.''')
    t=t.replace('NLL, token-weighted NLL, raw ordering,','Per-fit event counts and query-level results appear in Additional file 4;\nall frozen retrieval pools, candidate hashes and split assignments are supplied\nin Additional file 5. NLL, token-weighted NLL, raw ordering,')
    t=t.replace('Training uses A800 GPUs;', 'The original benchmark uses A800 GPUs; revision diagnostics use recorded\navailable GPUs with the same scientific settings. No hardware-performance\ncomparison is inferred. Training and')
    t=t.replace('Author review and\nresponsibility for the scientific content are required before journal submission.', 'Scientific interpretation and responsibility remain with the human authors.\nSource, environment, configuration and execution records are provided in\nAdditional file 6. Public release and author declarations remain administrative\nitems in this local revision.')
    t=t.replace(r'\subsection{A highly connected and source-concentrated paired corpus}',r'\subsection{The paired corpus is highly concentrated and near-neighbor exposed}')
    t=t.replace(r'\subsection{Denoising reconstruction exceeds aligned copying}',r'\subsection{Denoising pretraining improves single-chain reconstruction}')
    t=t.replace('This establishes reconstruction beyond the specified\ncopy control.', 'This shows reconstruction beyond the specified aligned-copy sanity control.')
    t=t.replace(r'\subsection{Likelihood improves more consistently than free partner recovery}',r'\subsection{Pretraining improves likelihood with a modest conditional contribution}')
    t=t.replace('The free-generation primary endpoint is much smaller.',r'\subsection{Free recorded-partner recovery remains sparse}'+'\n'+ 'Likelihood improvement did not translate into reliable free recorded-partner\nrecovery. The primary endpoint is much smaller.')
    t=t.replace('A zero-event bootstrap interval\ndoes not establish absence of possible recovery in the population.', 'Candidate scarcity is a central failure mode: a ranker cannot recover a\nrecorded partner absent from the candidate set. Additional file 4 retains\ncoverage, likelihood, ranker and fused event counts for every fit. A zero-event\nbootstrap interval does not establish absence of possible recovery in the population.')
    # Supplement the detailed mixture and negative-sampling analyses.
    mixture_start=t.index(r'\subsection{Pretraining mixture and downstream sampling have distinct effects}')
    mixture_end=t.index(r'\subsection{The component-data curve mixes size and composition changes}')
    mixture=t[mixture_start:mixture_end]
    t=t[:mixture_start]+t[mixture_end:]
    neg_start=t.index(r'\subsection{Changing negative training does not resolve candidate scarcity}')
    neg_end=t.index(r'\subsection{Directional tasks permit recovery of already exposed targets}')
    negative=t[neg_start:neg_end]
    t=t[:neg_start]+r'''\subsection{Negative-sampling sensitivity does not resolve candidate scarcity}
Alternative negative ratios and matching policies show no reproducible
free-recovery gain over the primary ranker. All paired intervals include zero;
no ranker supplies sequences absent from the saved free candidate set. Detailed
negative-sampling, pretraining-mixture and directional-budget sensitivities are
reported in Additional file 1.

'''+t[neg_end:]
    t=t.replace(r'\subsection{The component-data curve mixes size and composition changes}',r'\subsection{Pretraining improves likelihood across nested graph subsets, but recovery remains sparse}')
    # Insert completed revision results later, with an explicit, auditable marker.
    t=t.replace(r'\subsection{Directional tasks permit recovery of already exposed targets}',r'''% BEGIN REVISION DIAGNOSTIC RESULTS
\subsection{Revision diagnostics}
Revision model fits and their fixed-setting evaluations are in progress. No
unobserved outcomes are included here; the completed results will replace this
paragraph before scientific acceptance.
% END REVISION DIAGNOSTIC RESULTS

\subsection{Directional diagnostics allow recovery of exposed targets}''')
    t=t.replace('For unseen gamma inputs, conditional','In the original, single-query-selection exploratory run, conditional')
    t=t.replace('The estimate cannot establish robust unseen-gamma conditional benefit.', 'These original estimates do not establish robust unseen-gamma conditional\nbenefit and are superseded by the repaired-selection diagnostic above.')
    t=t.replace(r'\subsection{Source recovery is directional and concentrated in a large component}',r'\subsection{Study-level exposure sensitivity is directional and component-concentrated}')
    t=t.replace('The audited corpus exposes several distinct limits on interpreting partner\nrecovery.', 'The giant component and near-neighbor exposure are central limitations of\nthis benchmark.')
    # Put the central dataset limitation immediately after the discussion lead.
    ds=t.index(r'\section{Discussion}')
    a=t.index('The giant component and near-neighbor exposure',ds);b=t.index('\n\nLikelihood, sampling coverage',a)
    limitation=t[a:b];t=t[:a]+t[b:]
    p=t.index('\n\nThe direction and exposure comparisons',ds);t=t[:p]+'\n\n'+limitation+t[p:]
    t=t.replace(r'\section{Conclusion}',r'\section{Conclusions}')
    t=replace_section(t,r'\section{Conclusions}',r'\section*{Declarations}',r'''\section{Conclusions}
Denoising pretraining lowered target-token NLL, with modest conditional
information beyond a matched target prior. Free recorded-partner recovery
remained sparse under strict component-disjoint evaluation, and separately
trained reranking showed no reproducible primary benefit. Exposure and graph
composition limit broader transfer claims. Future gamma-delta TCR pairing
studies should report sequence modeling, candidate availability, recovery and
exposure dependence as separate endpoints.

\section*{Abbreviations}
CDR3: complementarity-determining region 3; TCR: T-cell receptor;
NLL: negative log likelihood; MRR: mean reciprocal rank; EOS: end of sequence;
AUROC: area under the receiver operating characteristic curve;
AUPRC: area under the precision--recall curve; SD: standard deviation.
''')
    a=t.index(r'\section*{Declarations}');b=t.index(r'\begin{thebibliography}',a)
    declarations=r'''\section*{Availability of data and materials}
The source collections are traceable through GEO accession GSE180059, the
Suo et al. study accession E-MTAB-11388 and its UcTCRdb export, and an IEDB
receptor export with one unresolved original-study record. Additional files
provide processed source descriptions, frozen splits, configuration and
candidate hashes. Third-party data remain subject to source-specific access
and redistribution terms. A local reproducibility package has been prepared;
a public benchmark repository and persistent archive identifier have not yet
been established. Public deposition is a pending submission requirement.

\section*{Code availability}
Project: GDTCR. Language: Python 3.10.20. Platform: Linux; dependencies include
PyTorch 2.7.1, CUDA 12.6, NumPy, scikit-learn and RapidFuzz. Additional file 6
contains editable source and pinned environment information. Public repository,
archived version/DOI and code license are pending author decisions. No public
license or unrestricted third-party redistribution permission is inferred.

\section*{Ethics approval and consent to participate}
This computational study reuses published sequence collections, with no new
participant recruitment, specimen collection or intervention. Original ethical
oversight is described in the source publications. The institutional
secondary-use determination and the final declaration are pending author
confirmation; no exemption is asserted.

\section*{Consent for publication}
Pending author confirmation.

\section*{Competing interests}
Pending author confirmation.

\section*{Funding}
Pending author confirmation.

\section*{Authors' contributions}
Author identities, affiliations, order, contributions and corresponding-author
information are pending author confirmation.

\section*{Acknowledgements}
Pending author confirmation. AI assistance is disclosed in Methods and does
not confer authorship.

\section*{Additional files}
Additional file 1 (PDF and editable TeX): supplementary methods, control
hierarchy and sensitivity results. Additional file 2 (ZIP/TSV): dataset
composition, source membership, graph and distance audits. Additional file 3
(ZIP/TSV/JSON): all seeds, selected checkpoints and actual training exposure.
Additional file 4 (ZIP/TSV): primary query outcomes, event counts, paired
contrasts and revision diagnostics. Additional file 5 (ZIP/TSV/JSON): frozen
candidate pools, split assignments and SHA256 manifests. Additional file 6
(ZIP): source, frozen configurations, environment and reproduction instructions.
Every attachment is limited to 20 MB. These are local release candidates;
author declarations, licensing and public deposition remain open.

'''
    t=t[:a]+declarations+t[b:]
    t=t.replace('Cellular Immunology. 2015;296:31--40.','Cellular Immunology. 2015;296(1):31--40.')
    t=t.replace('2026;54:D504--D510','2026;54(D1):D504--D510').replace('2026;22:e1014396','2026;22(6):e1014396')
    t=t.replace('2025;26:bbaf691','2025;26(6):bbaf691').replace('2026;42:btag551','2026;42(8):btag551')
    t=t.replace('2021;37:3938--3940','2021;37(21):3938--3940').replace('2022;13:5842','2022;13(1):5842')
    t=t.replace('2022;376:eabo0510','2022;376(6597):eabo0510').replace('2025;53:D436--D443','2025;53(D1):D436--D443').replace('2015;10:e0118432','2015;10(3):e0118432')
    t=t.replace(r'\end{thebibliography}',r'''\bibitem{dtcr} Wang H, Zang T, Liu Y.
DTCR: generating realistic, diverse, and epitope-specific T cell receptor
sequences via a discrete diffusion model. Briefings in Bioinformatics.
2026;27(4):bbag438. doi:10.1093/bib/bbag438.
\bibitem{germline_shortcut} Wang S, Sengupta A, Li S, Standley DM.
A germline shortcut in protein language model retrieval of adaptive immune
receptors. bioRxiv [preprint]. 2026. doi:10.64898/2026.07.21.739963.
\end{thebibliography}''')
    # Main figures are produced as a new export; no original figure is overwritten.
    a=t.index('% BEGIN GENERATED FIGURES')
    t=t[:a]+'% BEGIN BMC FIGURES\n% Figures inserted after numerical and layout validation.\n% END BMC FIGURES\n\\end{document}\n'
    # No forced page breaks and no thousands separators in numbers.
    t=t.replace(r'\clearpage','').replace(r'\newpage','')
    t=re.sub(r'(?<=\d),(?=\d{3}(?:\D|$))','',t)
    t=t.replace('Table~\\ref{tab:data}; Figure~\\ref{fig:data}', 'Table~\\ref{tab:data}; Figure~\\ref{fig:data}')
    t=t.replace('Distant test edges & 5 & 5 & 3\\\\','Distant test edges & 5 & 5 & 3\\\\\nLargest-component assignment & Training & Training & Training\\\\')
    t=t.replace('Distance bins use unique test gamma queries.', 'Distance bins use unique test gamma queries; these are not donor-level external tests.')
    TARGET.write_text(t)
    supplement=r'''\documentclass[11pt]{article}
\usepackage[margin=25mm]{geometry}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{amsmath,amssymb,graphicx,booktabs,array}
\usepackage{hyperref}
\newcommand{\gtd}{\ensuremath{\gamma\!\rightarrow\!\delta}}
\newcommand{\dtg}{\ensuremath{\delta\!\rightarrow\!\gamma}}
\title{Additional file 1: supplementary methods and sensitivity analyses}
\author{GDTCR scientific revision}
\date{}
\begin{document}
\maketitle
\section{Corruption and reconstruction}
Each single-chain sequence is assigned a masking rate of 15\% or 30\% with equal
probability. Exactly the larger of one and the rounded rate times sequence
length is selected without replacement. Each selected residue independently
receives a mask token (80\%), a uniform canonical amino acid (10\%) or its
original token (10\%). Deletion starts are sampled uniformly, with span lengths
uniformly 1--3, until at least the rounded 8\% target is covered; spans can
overshoot that target. Deletion follows masking and can overlap selected sites.
The damaged mask includes selected-but-unchanged residues and deleted sites.
The aligned-copy control copies the corrupted aligned token and uses a mask at
deleted sites. Reconstruction includes EOS in token NLL; residue accuracy is
separately evaluated on original residue positions. No reconstruction metric
is interpreted as partner recovery.

\section{Controls and training}
The conditional and constant-source generators share initialization, target
sampling, optimizer and nominal downstream budget. Constant-source input keeps
the chain token and removes source residues. Random initialization removes
pretraining and retains downstream settings; total training computation is not
matched. Shuffled-input evaluation permutes queries without fixed points and
keeps the original recorded-partner labels. A separate copy of the fine-tuned
generator initializes the ranker. Its copied encoder is trainable; the source
generator is not updated. All paired fits use the same protocol-specific
training edges. Seeds, selected checkpoints and actual exposure accompany
Additional file 3.

\section{Constructed negatives and candidate construction}
The primary ranker first uses multi-positive contrastive training, then equally
weighted positive and constructed-negative binary cross-entropy. Three negative
draws per positive are drawn from supervised-training combinations, excluding
known training partners. The mixed policy combines random and length/terminal
matching; actual fallbacks and draw counts are recorded. Unrecorded combinations
are not biological negatives. Sensitivities change ratios to one or five, or
use random-only draws. Fixed retrieval pools inject all role-specific recorded
positives and up to 100 unrecorded targets from that role's universe. Other
recorded partners are excluded from distractors. Random, length, terminal-motif
and normalized-edit matching are deterministic at fixed seed. All scorers use
the same frozen lists. Free sampling instead makes 64 draws with temperature
one and top-p 0.95; 6--35 canonical residues and observed EOS are required.
Invalid and duplicate draws are never replaced. Training-target exclusion is
an explicitly separate policy that can delete legitimate exposed positives.

\section{Uncertainty and event reporting}
Query-macro metrics weight inputs equally, with directions averaged equally for
the primary endpoint. The bootstrap uses 2000 resamples of complete test graph
components, shared across directions and paired model contrasts. Directional
tasks use source-query groups. The repair of unseen-gamma selection retains
this directional uncertainty unit. The within-giant-component experiment has
one original component and reports no inferential interval. Intervals condition
on fitted models and saved samples, without multiplicity adjustment. A zero-event
[0,0] interval is not a population upper bound. Across primary splits, seeds
are averaged first and the three split means have a descriptive SD; neither
fits nor repeated splits are independent biological replicates.

\section{Supplementary sensitivity results}
'''+mixture+negative+r'''
\section{Revision protocol}
Nearest-input transfer uses the normalized full-CDR3 distance, lexicographic
input ties and training-degree/lexicographic target ordering. One nearest
input is primary; five is a fixed sensitivity. At most 64 unique training
targets are returned. The separate nearest-input partner-similarity retrieval
score extends to the role-specific target universe using minimum target edit
distance to the nearest input's known training partners. Neither neighborhood
size nor distance rule was selected using test outcomes. Test memberships,
selection repairs and the giant-component edge reservation are frozen in the
revision split manifest. These are post-primary revision diagnostics.

\begin{thebibliography}{99}
\bibitem{protocol} GDTCR. Frozen benchmark and revision protocols. Included in
Additional file 6; local release candidate, 2026.
\end{thebibliography}
\setcounter{figure}{0}
\renewcommand{\thefigure}{S\arabic{figure}}
\begin{figure}[htbp]
\centering
\includegraphics[width=\linewidth]{results/v2/figures/figure_S1_pretraining.pdf}
\caption{Pretraining mixture sensitivity. Dots retain fitted seeds. Equal sequence draws do not imply equal chain-specific or token exposure. Reconstruction is a single-chain endpoint.}
\label{fig:figure_S1_pretraining}
\end{figure}
\begin{figure}[htbp]
\centering
\includegraphics[width=\linewidth]{results/v2/figures/figure_S2_negative_training.pdf}
\caption{Ranker negative-sampling sensitivity. All settings reuse the same saved free candidates and frozen truth-containing retrieval pools. No ranker adds absent candidate sequences.}
\label{fig:figure_S2_negative_training}
\end{figure}
\end{document}
'''
    supplement=re.sub(r'(?<=\d),(?=\d{3}(?:\D|$))','',supplement)
    Path('paper/supplementary_methods_bmc.tex').write_text(supplement)
    print(TARGET)

if __name__=='__main__':main()
