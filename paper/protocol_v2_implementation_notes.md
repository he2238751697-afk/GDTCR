# Completion-v2 implementation notes

These notes record implementation resolutions and subsequent audit clarifications.
The timing of each change is stated below. They do not change the frozen test
sets or remove a required comparison.

## 2026-09-30: source-shared initialization correction

The original generator manifest accidentally assigned the main pretraining pool
to the four source-shared generator/constant-source tasks. The protocol requires
the additional source-excluded pretraining pool for the source experiments.
None of these four tasks had been submitted or run when this discrepancy was
identified. A replacement manifest uses the same source-excluded sqrt checkpoint
as strict source holdout for each seed. The original manifest remains immutable;
`configs/completion_v2/task_supersessions.json` maps each replaced task to its new
manifest. Shared exact chains in *supervised* training remain intentionally
allowed. This keeps the two source experiments comparable in initialization.

## 2026-09-30: known partners in ranker checkpoint selection

Before any full v2 ranker training started, its validation scorer was corrected
to exclude recorded alternative partners outside the selection-validation role
from distractors. This matters for the seen-input diagnostics, where an input
can have other recorded training/test partners. The same exclusion rule already
applies to all frozen evaluation pools. The observed-pair table is used only by
validation scoring, never by training-negative construction, initialization,
or gradient updates. A replacement manifest for all 42 ranker tasks records the
additional validation-only input and corrected frozen code. The original task
manifest is retained and explicitly superseded.

## 2026-09-30: metric and nearest-pair definitions

For free generation, mean positive rank averages over all recorded partners.
Every unrecovered partner receives rank `number_of_unique_candidates + 1`.
This avoids reporting an average over recovered partners alone. Hit, Recall,
MRR and coverage definitions remain unchanged. The legacy v1 evidence is retained
without rewriting.

The exact two-chain neighbor score is the negative minimum, over all training
edges, of the mean of the two normalized Levenshtein distances. Each chain's
distance is divided by the length of its longer sequence. Ties in the nearest
training edge use the first lexicographically sorted training pair. Both chains
contribute equally. Generated candidates additionally retain their nearest
supervised target distances and witness sequences; D4's supervised/pretraining
stratification uses recorded source and target chains.

## 2026-09-30: score calibration and reporting details

The ranker initialization named in each frozen task is the selected matching
paired-generator checkpoint, after supervised fine-tuning. Subsequent ranker
optimization uses a separate parameter copy and does not update the generator;
it is not a comparison of independent training cohorts. The stored ranker
object retains the generator's unused decoder for checkpoint compatibility.
Its recorded parameter total includes that storage, while ranking calls only
the encoding path. These are clarifications of the executed manifests and
architecture, not a change to fitted models.

The primary fusion coefficient is shared across directions within one fitted
model; score means and population standard deviations are direction-specific.
The selection objective gives equal weight to directions. Free-candidate tuning
uses the first 64 saved draws with training targets allowed. Fixed-pool tuning
uses the equal mean of query-macro Hit@5 over the four small pool types; its
score scaling and threshold calibration use the corresponding full target pools.
Free and fixed-pool calibration are separate because their candidate distributions
differ. A zero or empty tuning-score variance uses scale 1 and is flagged.

Calibration labels exclude known alternative partners outside the role's recorded
positive set. Balanced-accuracy ties favor the highest threshold, including
reject-all. A calibration set with no recorded positive (or no constructed
negative) yields reject-all and an undefined balanced-accuracy estimate. Reported
acceptance curves apply 101 calibration-score quantiles and reject-all/accept-all
endpoints to test, without choosing thresholds from test outcomes.

The six-cell sampling grid is inspected on split-17 tuning data for both primary
conditional-model seeds. Its descriptive best cell uses query-macro likelihood
Hit@5, with ties favoring the primary setting and then smaller temperature/top-p.
As specified in the frozen protocol, the primary test setting remains temperature
1 and top-p .95. Test samples for the split-17 primary models and matched priors
have 256 draws and are also evaluated through their saved 16/64-draw prefixes.

Full v2 training continues on A800 GPUs. Model evaluation can use the auxiliary
3090/4090 queue and available A800 capacity with the same software and checkpoint
hashes; each run records its actual device. A combined A800 queue driver gives
all ready training tasks priority over evaluations and shares the submission
ledger with the auxiliary queue to prevent duplicate task execution. The fitted
calibration settings, model hashes, and sampling
parameters are verified before the corresponding test command starts. Hardware
timings are descriptive and are not presented as a controlled hardware comparison.

## 2026-09-30: reconstruction of saved token padding during audit

The model sampling method returns a 64-column tensor, including deterministic
PAD columns after the maximum 36 decoding steps. The strict decoder records its
rejection reason on that tensor and then removes trailing PAD from the saved
token list. For one budget-exhausted, no-EOS sample in the data-fraction-25
random-initialization seed-0 test (one of 91,456 draws), directly re-decoding the
trimmed list changes the reason from `pad_before_eos` to `missing_eos`. Both
interpretations reject the sample; validity, candidates and recovery metrics
are unchanged.

The content audit now restores the deterministic padding to the generator's
recorded model maximum length before re-decoding. It still requires exact
agreement on the saved reason, EOS flag, token prefix and validity. Regression
checks cover both exhausted-budget and observed-EOS samples, including rejection
of an incorrectly changed validity label. No model evaluation is regenerated or
edited. The first failed audit, job `2996928_22`, is retained. Fourteen already
passing audits remain valid; the failed and 73 unstarted audits use a separately
frozen correction manifest and new output directories. The union is identified
by `evaluation_audit_supersessions.json`, without changing the original training
supersession registry.

## 2026-09-30: information limits of grouped validation

While preparing the v2 data summaries, the directional unseen-gamma validation
role was found to contain only one gamma query with 581 recorded delta partners
in its checkpoint-selection subset. Keeping this query group intact overshoots
the intended 50% edge allocation; tuning and calibration each contain 163 edges
(36 and 26 gamma queries). The selection target universe consists entirely of
that query's positives. Its selection Hit and MRR are therefore identically one
for any finite ranking scores, so the ranker's tie rule selects the earliest
eligible BCE checkpoint. Generator selection also relies on just this one input.
The previously frozen splits, commands and tests are retained. This directional
condition is reported as a restricted diagnostic with an uninformative ranker
selection criterion, not a well-supported generalization estimate.

The evidence export now includes validation query/target/distractor counts from
the already audited frozen pools. A future protocol should check sufficient
source-query counts and actual unrecorded distractors before freezing each
validation role, rather than relying on edge proportions alone. The 10%, 25%
and nominal 50% component-data subsets also contain only singleton components;
the 5,005-edge component enters only at full data. Their comparison must retain
this composition change as a limitation.

## 2026-09-30: uninformative frequency scores under chain exclusion

The frozen training-frequency baseline scores each target by log(1 + its
training-edge count). Primary validation/test target sequences are absent from
training, so their frequency scores are identically zero. Ranking still uses the
shared deterministic lexicographic target-sequence tie rule. Its nonzero Hit@5
therefore reflects the tie ordering within the frozen pool, not informative
frequency prediction. Seeded random scores remain the stochastic reference.
The final evidence exports per-protocol counts of all-zero and all-tied full-pool
score vectors from the hash-verified baseline files. The scores, rankings,
candidates and reported metrics are unchanged; only their interpretation is
made explicit in the manuscript and figure caption.
