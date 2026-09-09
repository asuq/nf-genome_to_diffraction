# RF-G1-RF-G4 implementation and qualification plan

## Authority and scope

On 2026-09-09 the user cancelled the expanded identification investigation,
accepted its three rank-one candidate assessments after supervisor confirmation,
and directed work on RF-G1-RF-G4, followed by continuation through the remaining
planned v0.3 work. This plan implements the existing acceptance criteria in
[the consolidated plan](v0.3-v0.4-development-plan.md#pre-v03-ranking-release-gates);
it does not change benchmark thresholds, truth access, scientific budgets or
the deferred v0.4 scope.

The retained handoff's evidence hierarchy, separate raw feature families,
complete copy reporting and human review remain applicable. Its older static
copy ceiling and suggestion to calibrate on the unknown crystals are superseded
by current repository instructions. Supervisor-confirmed identities must not
become tuning data for these gates.

## Source audit and implementation order

### 1. RF-G1 - MR-led review

Observed: `review/mr_seed.py:_candidate_sort_key` places the Matthews status,
prior and rank ahead of packing, copy agreement and numerical MR evidence.
`test_review_priority_does_not_let_mr_only_rank_override_matthews` explicitly
protects that rejected ordering. The MR-only key also puts the numerical score
gate before packing. In addition, `mr/phaser.py` derives its top-packing Boolean
from an aggregate packed-solution count rather than an independently bound
selected-solution record.

Implement one inspectable review policy, reusable by production review and M6:
valid/inspectable evidence, selected-solution packing and explicit copy-state
interpretation, MR evidence, then Matthews tie-breaking and deterministic IDs.
Preserve independent MR and Matthews ranks, raw scores and missing states.
Qualify selected-solution and tNCS bindings with native fixtures rather than
inventing a new clash threshold or accepting every copy mismatch.

Replace the prior-dominance regression with the specified real-enumerator
50 kDa/two-copy versus 5 kDa/20-copy comparison. Cover absent/malformed packing,
competing solutions, literal one-copy and explicitly evidenced coupled-tNCS
states, ties, missing scores and unchanged full candidate inventories. Advance
the affected adapter/content identities and update report meanings together.

### 2. RF-G3 - Physical validity versus analysis preferences

Observed: `matthews/enumerate.py:physical_status` calls a solvent interval
entirely outside the configured window impossible. `dynamic_copy_counts`
also clips its upper count with the configured minimum solvent fraction.
A read-only probe reproduces both 0.09 and 0.91 being labelled impossible for
a 0.10-0.90 window, and a 5 kDa/250,000 A^3 example loses counts 37-40.

Separate mathematical mass/volume consistency from window preference. Enumerate
the complete finite mass/volume-supported range; retain the existing explicit
fail-closed safety bound rather than silently truncating extreme inputs.
Out-of-window but admissible states remain visible for review. Propagate the
meaning through schemas, retention, funnel validation, partner/composition
consumers, sequence review and explicit selection, not only display text.

Test both window tails, exact boundaries, bounded masses, invalid/non-finite
inputs, permutation stability and downstream conservation. Preserve the
configured window, unweighted solvent density, copy-frequency factor, product,
reference/backend identity and distinct zero/missing/unsupported states.
The 0.9 A insufficient-reference case remains an explicit unsupported-estimator
outcome, never a coarser-resolution or zero-score substitute.

### 3. RF-G2 - Reviewer-selected deferred hypotheses

Observed: the current retained deferred inventory and localisation reopening
path require complete zero packing. They do not implement selection after a
packed but rejected/unresolved result, and non-retained copy alternatives do
not automatically become executable by merely remaining in a report.

Use the existing model registry, complete Matthews inventory and owned review
machinery for one narrow, explicit selection operation. Bind selected IDs,
source, crystal, parent package, reviewer decision, finite attempt budget and
outputs. Reuse the first-copy executor and subsequent A checkpoint. Do not
turn human-selected recovery into automatic broad reopening or a second MR
engine. Keep the existing automatic zero-pack policy distinct where still
required; do not silently broaden its trigger.

Verify a lower/zero-copy-frequency candidate and a non-top copy state can be
selected after rejection/unresolved review of a packed result. Reject stale,
foreign, duplicate, unmodelled and over-budget selections; conserve selected,
deferred, attempted and terminal counts. Reuse genuine identical scientific
evidence only through an authenticated explicit reference, never a failed cache.

### 4. RF-G4 - Production/M6 parity and control qualification

Observed: `benchmarks/m6_nextflow.py:_write_selected_inputs` takes the first 25
provider-ranked sequence groups before the production funnel. Its
`_first_rank`/`_rank_m6_seed_candidates` form a separate advancement policy.
`m6_collection.py` currently takes target sequence rank from provider-ranking
rows rather than the actual scheduled and advanced inventories.

After unchanged leakage filtering, send the eligible inventory through the
production admission and review functions. Remove superseded benchmark-only
preselection/ranking that changes the evaluated universe. Preserve the frozen
25-hypothesis/five-seed evaluation scope, opaque runner inputs, protocol and
acceptance thresholds. Report unique proteins separately from models, copy
states and tasks, with stage-specific scheduled/recommended/advanced metrics.

Run the predeclared four-arm admission-prior/review-order comparison on known
controls only. Reuse identical native MR evidence when only review order
changes; changed scheduled cohorts require real results. Keep historical
reference policies in benchmark fixtures or frozen reference runs, not active
alternative production paths. Include required positive, copy-alternative,
decoy and open-set cases without inserting unknown-crystal truth into runners.

## Validation and completion discipline

RF-G1 local implementation now uses the shared typed review policy and selected
PDB packing/copy evidence. The prior-dominance regression is replaced by the
real-enumerator equal-solvent example. Missing or positive-clash packing is not
promoted by aggregate packed counts, and missing selected TFZ is not filled from
log maxima. Parser/review/collector contracts and rendered Nextflow cache
identities advance together. Native known-control qualification and M6 adoption
remain required; this local increment alone does not close RF-G1 or RF-G4.

RF-G3 local implementation now uses mass/volume-only finite enumeration and
separately reported configured solvent windows. Both 9% and 91% tails remain
reviewable, and out-of-window rows can enter the unchanged first-copy funnel.
Impossible one-copy diagnostics remain in the inventory but are not retained
for execution. Funnel validation, partner/component eligibility and sequence
review use the corrected meaning; content/task identities advance together.
Explicit access to non-top deferred states still requires the RF-G2 route.

The RF-G2 factor-reporting increment now preserves unweighted density, empirical
copy frequency, product, occurrence/population counts, resolution-selected
reference count and backend/checksum provenance in current hypotheses and review
outputs. Schema arithmetic/status checks and production rederivation distinguish
unobserved-copy zeros, zero density, historical missing evidence and unsupported
estimators. The [reviewer-selected execution route](reviewed-first-copy.md) now
authenticates exact deferred targets after rejected/deferred A review, constructs
them through the production funnel and uses the existing one-copy and owned
A-checkpoint tasks. Local synthetic and real-Nextflow stub checks exercise
non-top zero-frequency states and fail-closed dispatch; native qualification is
still pending. This route does not change automatic zero-pack reopening.

The first RF-G4 local increment removes M6's pre-funnel top-25 protein and
mapping cuts. All leakage-policy-accepted model candidates reach preparation;
only the production funnel imposes the unchanged 25-MR-hypothesis cap. A real
registration/preparation/enumeration/funnel regression with synthetic inputs
retains a provider-rank-31 candidate and matches direct production admission.
Shared review ordering, explicitly truth-blind advancement, stage-specific
metrics and native four-arm qualification remain outstanding.

- The pre-change focused baseline passes 70 tests covering MR review, Matthews
  inputs/probability and M6 seed selection. This is not acceptance of the new
  behaviour; several historical expectations must intentionally change.
- Use focused existing tests and necessary observed-invariant regressions per
  increment. Run the complete locked gate at the named RF integration milestone,
  then exact-source CI and required real-runtime/HPC controls under the applicable
  explicit authority. Keep source-owned scientific caches separate when content
  semantics change.
- Update schemas, current callers, examples, reports, documentation and adapter
  identities together. Do not add compatibility shims for replaced policies.
- Commit coherent, checked increments. Record local qualification separately
  from CI and real-control evidence; none alone means all four gates are closed.
- General M6 operational/mutation/leakage qualification, remaining finding
  closure, pass-2 and final release gates still follow. New remote submissions,
  publication and release actions retain their approval requirements.
- Cancellation of the separate AFDB investigation and preservation of its
  existing evidence do not authorise restarting it or block local RF work.
