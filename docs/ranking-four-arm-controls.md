# RF-G4 four-arm known-control qualification

## Status and authority

This is the pre-execution specification for the comparison already required by
[RF-G4](v0.3-v0.4-development-plan.md#rf-g4-validate-production-admission-and-advancement-through-m6).
It is not a new production policy, an executed benchmark, or release acceptance.
The native C001/C025 resource control remains a separate prerequisite. Its
structural verification cannot close this comparison.

The cohort below was fixed on 2026-09-11 before four-arm execution or inspection
of four-arm results. The current C001/C025 native control had submitted its
planning task but had not emitted a scientific result at that point. Cohort
selection uses only the existing public, truth-side M6 protocol; no operator
crystal, supervisor-confirmed identity, or ranking output is used for selection.
Do not replace a difficult case after observing results.

## Fixed cohort and inputs

Use the unchanged [M6 protocol](../benchmarks/m6/protocol.yaml), SHA-256
`d735b3dfd9aae43df2f55a5fe5e25ad5e087eb933ffccd37eeb20f0519f159de`, and the
corresponding qualified opaque runner. This comparison is a five-case subset,
not a replacement for either complete M6 track or its frozen thresholds.

| Case | Existing protocol role | Required comparison evidence |
| --- | --- | --- |
| M6C001 | Small, 86-residue positive; two expected ASU copies | Actual scheduled/recommended/advanced recovery and model provenance |
| M6C010 | 180-residue positive; six expected ASU copies | Small/high-copy and uncommon-copy coverage |
| M6C055 | Existing non-top-Matthews variation of the six-copy target | Actual selection and completed execution of the non-top expected-copy alternative, not retention alone |
| M6C025 | Target absent from the C001 catalogue | No false exact assignment; family-level or unresolved outcomes remain permitted |
| M6C037 | C001 target with the predeclared wrong related catalogue | No false exact assignment; preserve ambiguity and execution failures distinctly |

Retain every protein in each corresponding runner catalogue, including the
positive identities. Keep the target-absent and wrong-catalogue transformations
exactly as prepared in the original protocol. Do not insert synthetic proteins,
reduce catalogues, add target-aware models, or manufacture favourable decoys.

The pinned Matthews reference is SHA-256
`4114691d739f79ade662dc9ee1df5bd5f0e89c0499d1175337c7295b0191d906`.
Its empirical frequencies are 0.027694759912333135 for six copies and
0.34156206415620644 for two copies. These document the existing uncommon-copy
control; they are not acceptance thresholds or evidence for an ASU assignment.
Six copies are observed, not unobserved, in that reference. The separate
zero-frequency synthetic/reviewer-selection tests must not be represented as
native unobserved-copy recovery.

For plausible large-protein decoy coverage, audit the complete eligible
inventories from these same catalogues, with sequence-derived masses, physical
status, model availability and scheduling disposition. Report individual
non-target candidates larger than the corresponding positive, including those
that displace it or receive stronger MR evidence. This is a reporting stratum,
not a mass filter or permission to alter admission. If the native inventories
do not contain such model-backed physically admissible competitors, report
coverage as incomplete; do not claim that a large-protein positive supplies
decoy evidence or silently replace the cohort.

## Comparison semantics

Keep the predeclared arms unchanged:

| Arm | Admission prior | Review order |
| --- | --- | --- |
| A | Resolution-conditioned solvent density | Prior-first reference |
| B | Solvent density times observed copy frequency | Prior-first reference |
| C | Resolution-conditioned solvent density | Corrected MR-led |
| D | Solvent density times observed copy frequency | Corrected MR-led production baseline |

All arms use the current physical-status meaning, complete finite copy range,
model eligibility, leakage rules, diversity buckets, per-model retention
budget, initial one-copy search, 25-hypothesis cap and five-seed cap. Copy
completion and scientific tool settings stay fixed. Do not restore historical
solvent-window clipping, benchmark top-25 protein preselection, aggregate
packing inference, or strict rejection of evidenced coupled tNCS.

Keep the two current retention limits distinct: the frozen M6 configuration
retains four Matthews alternatives per candidate, while its existing `pilot`
profile admits at most three alternatives per model before the 25-task cap.
Apply both unchanged in every arm. Neither limit is a static ceiling on the
expected copy count itself; complete physical alternatives stay in the inventory.

The solvent-only reference must recompute its candidate-local prior ranks and
which expected-copy hypotheses survive the unchanged per-model budget. Merely
reordering the already copy-weighted top rows does not test solvent-only
admission. Preserve the production solvent density, frequency and product as
independent raw fields; never overwrite the product with density or disguise
reference rows as valid production Matthews records.

Within an admission pair, both review orders consume the same immutable,
current-parser selected-solution MR evidence. Both keep the current completed-
execution/inspectability checks first. The prior-first reference places the
physical-status/prior/candidate-local-rank block before the remaining packing,
copy-interpretation and numerical-MR block. Corrected MR-led review places that
MR block first. Use the same deterministic identity tie-breaks and unchanged
seed-eligibility rules. This isolates the declared ordering comparison; it is
not a replay of every defect in the historical parser and pipeline.

Arm D must match the actual production admission and review functions exactly.
Reference ordering belongs only in benchmark fixtures or checksum-frozen
reference runs. Do not add a production CLI switch, alternate ranking engine,
mutable feature flag, or compatibility mode. Freeze executable reference
fixture/source hashes and prove baseline parity before native comparison.

## Evidence reuse and execution accounting

1. Bind source, runner, database, Phenix, Pixi lock, reference backend, execution
   policy and all scientific settings before planning. Input/physical/model
   eligibility inventories must agree across the four arms.
2. Freeze both complete admission inventories and their selected cohorts before
   starting comparison MR. A/C share the solvent-only cohort; B/D share the
   copy-weighted cohort. Record expected-copy and requested one-copy states
   separately, even where two hypotheses request identical physical searches.
3. Reuse genuinely identical completed MR only through authenticated scientific
   input/output identities. A changed scheduled cohort needs real MR results
   for its additional hypotheses. Missing, failed or cancelled tasks are not
   inferred no-hits. Shared execution does not allow any arm to exceed its
   own 25-hypothesis budget.
4. Freeze MR output inventories before computing paired review orders. Publish
   the full ordered inventory and the eligible top-five recommendations for
   each arm. A recommendation is not a human approval or an advancement receipt.
5. When review order changes the selected seeds, obtain genuine native
   continuation evidence for any newly selected seed through the qualified
   benchmark authority and the shared executor. Do not reuse another seed's
   output or count a planned seed as advanced. Retain each arm's five-seed
   accounting even if identical scientific work is shared between arms.
6. Freeze output inventories/checksums before truth-side evaluation. Report
   target-sequence and family recovery at the scheduled, recommended and
   actually advanced boundaries, unique proteins separately from models/copy
   hypotheses/tasks, non-top-copy execution, false exact assignments, gains,
   losses, failures and missing evidence. Keep raw MR metrics and copy caveats.
7. Require source-bound native child/tool/resource provenance and an equivalent
   fully cached resume. The comparison remains incomplete if any required arm,
   coverage stratum, scientific result or provenance binding is unavailable.

## Remaining implementation and release boundary

The first local reference-only increment is
[`ranking_four_arm_reference.py`](../tests/fixtures/ranking_four_arm_reference.py).
It rederives comparison ranks and retention from the complete production
enumeration without changing its raw factors, and applies paired review orders
to the same joined MR records. Arm D calls the production review function.
The [real-enumerator tests](../tests/unit/test_ranking_four_arm_reference.py)
cover baseline parity, newly retained solvent-only alternatives, permutation
stability, incomplete/stale inputs, foreign joins, impossible states and
failed/uninspectable MR. Their mathematical ordering probe explicitly uses a
larger synthetic retention cap; it is not the native comparison budget.
These tests use synthetic MR, never native qualification or advancement claims.

The next read-only fixture,
[`ranking_four_arm_admission.py`](../tests/fixtures/ranking_four_arm_admission.py),
uses the actual production loaders, complete physical/factor validation, verified
model bytes and hypothesis construction. It annotates the full model-backed
physical inventory with reference retention and cap dispositions. The weighted
baseline uses the production selector; the solvent-only reference preserves its
existing diversity-bucket rounds and deterministic tie-breaks. It does not write
a runnable bundle, fabricate a review decision or change production records.
Its [admission tests](../tests/unit/test_ranking_four_arm_admission.py) compare
ordered hypotheses directly with the production funnel, preserve a 93-model/
31-protein fixture through the 25-task cap, distinguish four-row retention from
the three-per-model limit, and exercise newly admitted omitted-copy alternatives
on explicit synthetic mass/volume inputs. Corrupt factors, missing inventories,
changed models and foreign scope/budgets fail closed. Input permutation does not
change the selected cohort. These are local fixture checks, not native recovery.

The [paired recommendation fixture](../tests/fixtures/ranking_four_arm_seeds.py)
rederives that admission and requires its exact scheduled hypothesis inventory.
It uses actual production review-package validation to authenticate MR assets
and derive eligibility for all rows, including eligible states outside the
production top five. Comparison ranks/recommendations are separate annotations;
the original production rows and MR results remain unchanged. Arm D must agree
with the production recommendation table exactly. The fixture writes neither
execution authority nor continuation receipts. A zero-scheduled case still needs
its native early-outcome evidence; it cannot be replaced by a manufactured review.
The [paired tests](../tests/unit/test_ranking_four_arm_seeds.py) use explicitly
synthetic MR and real production review validation for both admission cohorts.
They demonstrate changed top-five membership with identical within-pair MR,
preserved eligibility, empty recommendations for no-hit results, and rejection
of missing/foreign cohorts, changed result/model bytes and altered review fields.

The [reference authority fixture](../tests/fixtures/ranking_four_arm_advancement.py)
rederives both complete paired recommendation tables and binds them to the
fixed five-case scope, source files, original review assets and admission inputs.
Its `truth_blind_rf_reference` authority is distinct from production M6 and human
approval. Each arm retains at most five seeds; the pair's union may contain up
to ten authentic solutions, each executed once without changing either arm's
budget. Changed or rehashed source/input/policy/recommendation records fail closed.

The [reference copy fixture](../tests/fixtures/ranking_four_arm_copy.py) runs one
selected seed's dependent chain through the shared production scientific input
checks, Phaser command, parser and sequential continuation implementation.
Independent seeds still require Nextflow fan-out. Authority is revalidated for
every attempt, with reference-only adapter identity
`phenix-add-copy-rf-reference-v1`; public human/Phase III/M6 routes cannot consume
this manifest. Original model, MTZ/preflight, sequence, parent/child and parameter
bindings remain mandatory. No human decision or production ranking switch is
created. An already-complete root emits an authenticated zero-attempt receipt;
it is not a native additional-copy search. Tool and parse failures retain their
typed status and best supported parent, not a successful copy-placement claim.

The [stage-accounting fixture](../tests/fixtures/ranking_four_arm_stages.py)
requires exactly the paired union of authenticated continuation bundles, with
no missing, duplicate or foreign seed. It reuses the production structural
`M6StageInventory`/count definitions under explicit reference authority: unique
sequence groups, models, sequence-group/expected-copy states and hypothesis
tasks are distinct. Each arm has its own scheduled, recommended and actually
advanced rows; a receipt selected only by its partner is not its advancement.
Here, as in production M6, advanced means an authenticated continuation task,
including an already-complete root or failed copy attempt, not scientific
success. The separate full typed attempt inventory preserves that distinction.
Receipt hashes include native logs as well as parent/child coordinates, results,
commands and parameters. Freeze the inventory before truth-side evaluation;
later changed evidence must not be accepted under the saved inventory digest.

The [authority/copy tests](../tests/unit/test_ranking_four_arm_advancement.py)
and [stage tests](../tests/unit/test_ranking_four_arm_stages.py) use the real
shared adapters with explicitly simulated Phenix output. They exercise reference
seeds outside production's top five, source/policy/asset tampering, sequential
parents, input overrides, zero-attempt roots, no-hit recommendations, execution
failures and separate per-arm conservation. They are not native runtime evidence.
Full first/resume/native route qualification remains outstanding.

The current fixed M6 production route implements arm D, not the complete
reference comparison. Before submitting comparison work, qualify the isolated
reference fixture, its admission/retention parity checks, paired-output joins,
actual advancement accounting and a reviewed fixed execution route using the
existing controller. First/resume, malformed/stale/foreign evidence and missing-
result checks must pass locally and on exact-source CI.

Do not relabel the two-case native resource control, existing unit fixtures,
historical M6 results, or a production-only full M6 run as this four-arm result.
Complete M6 operational/leakage/mutation qualification, remaining finding
closure and the separately authorised three-crystal rank-recovery test remain
required. Preserve the release hold if the frozen criteria fail; do not tune
weights, smooth zero frequencies, change thresholds or weaken the benchmark.
