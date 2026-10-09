# BMC revision protocol

Frozen before new model fitting on 6 October 2026. All experiments below are
revision-stage diagnostics following inspection of the completed benchmark.
They do not replace the primary component-disjoint estimates or constitute a
preregistration. The original inputs, runs and publication exports are retained.

## Nearest-input partner transfer

For each query, find the nearest supervised-training source CDR3 using full-CDR3
Levenshtein distance divided by the longer sequence length. Ties use sequence
lexicographic order. Transfer the recorded training partners of that source,
ordered by training-target degree (descending), then lexicographically. Retain
at most 64 unique candidates. Report coverage, Hit@5, Recall@5 and MRR. The
primary baseline uses one nearest source; five sources are a fixed sensitivity
analysis, concatenating each source's ordered partners before deduplication.
Neither test positives nor test-target candidates enter this proposal step.
Consequently, direct transfer has structurally zero recovery when every test
target is excluded from supervised training. This limitation is reported, not
interpreted as proof of a superior learned pairing mechanism.

In the existing truth-containing retrieval pools, separately evaluate a
nearest-input **partner-similarity** score: minus the minimum normalized target
distance to any recorded partner of the single nearest training source. This
scores the same frozen candidate lists as the neural and shallow methods; it
does not turn retrieval into free recovery. No neighborhood size or distance
definition is selected on test outcomes. Query-level witnesses and counts are
retained. Primary uncertainty resamples complete test components; directional
diagnostics use source-query groups. Repeated fits/splits are not pooled.

## Unseen-gamma validation repair

Keep the original train, aggregate validation and test memberships unchanged.
Reassign whole validation gamma-query groups by query count, with fixed seed
7319: approximately 50/25/25 percent to selection/tuning/calibration. Require at
least two queries per role and at least one eligible retrieval distractor for
every selection query. Audit exact group disjointness, retained edge union and
unchanged train/test hashes before fitting. Refit conditional, matched
constant-source and random-initialized generators for seeds 3407 and 3508, using
the original 1500-step downstream budget and query-macro selection criterion.
Refit the conditional ranker using the original 3000-step mixed-negative
protocol. Use fixed 64-draw sampling (temperature 1, top-p 0.95) and report
likelihood/ranker outcomes, with no new fusion or threshold tuning. A shuffled
input control uses the newly selected conditional model. The old pathological
selection results remain explicitly exploratory and are superseded for this
diagnostic; primary results are unaffected.

## Within-giant-component edge holdout

Start with the split-17 training graph, whose largest component has 5005 edges.
Shuffle its edges with seed 1729. Greedily reserve 1000 edges, removing an edge
only while both endpoints retain at least one supervised-training edge. Shuffle
the reserved edges again with seed 1730, assigning 500 to validation and 500 to
test. Keep all other original training edges. Neither original primary
validation nor test edges enter this fit. Use all 500 validation edges for
checkpoint selection; there is no score/sampler/threshold tuning. Both input
and target sequences of every held-out edge must remain supervised-exposed.
Fit the same three generators, conditional ranker and shuffled control as above,
with the same seeds and budgets. This estimates withheld-edge recovery inside
one exposed component, not unseen-component transfer. Report seed-specific
event counts and point estimates only: there is one original component, so a
component bootstrap cannot support an inferential interval. Compare the
populations descriptively, without attributing differences solely to exposure.

## Integrity and manuscript boundaries

Record source snapshots, split/input/checkpoint/candidate hashes, actual model
exposure, selection behavior and Slurm task status. Recompute distant-edge
counts from frozen distance witnesses and re-export primary per-fit event
counts. Preserve zero events and negative results. Supplement all conditions,
including failed runs if any. No biological specificity/function, donor
independence, optimality over model families or total-compute matching is claimed.

The checklist's phrase "frozen encoder copy" conflicts with the executed
ranker configuration: `freeze_encoder=false`, with all 7594779 parameters
enabled for training. The generator checkpoint remains unchanged; the ranker's
copied encoder is separately optimized. The manuscript and diagram must state
this actual behavior. This is a methods-description correction, not a change
to the numerical evidence.

Public deposition, data redistribution license, author identity and author-owned
declarations require factual information absent from the repository. Prepare a
local release candidate and track these open fields without inventing them.
