# Phase III roadmap: hardening and general composition search

## Purpose

Phase III turns the experimental v0.2 two-component prototype into a validated
research workflow. It closes all remaining old and newly discovered defects,
repairs and accepts M6, generalises composition states to `A+B+C+...`, and runs
the three operator crystals as exploratory applications rather than validation
truth.

The application search supports arbitrary component-list records. The fixed
Phase III profile is bounded to six distinct components, three retained parent
states per depth, 25 expansion attempts per depth, and 100 expansion attempts
per crystal. Three-component placement is validated with 9ECN. Depths four to
six remain provisional until an independent positive control exists.

## Entry gate

Start implementation only after experimental `v0.2.0` is tagged from a clean
commit that passed the corrected P6 control and exact-source Marmic replay.
Preserve v0.1 and v0.2 evidence as immutable read-only inputs.

## Finding ledger

Rebaseline the 34 findings from the 2026-08-17 adverse review and every later
finding in one tracked ledger. Current disposition before Phase III is 12 fixed,
one superseded/deleted, five partial, and 16 open.

The remaining work is grouped as follows:

- execution: `PIPE-P1-01`--`PIPE-P1-04`, `PIPE-P2-06`, `PIPE-P2-07`;
- crystallographic/reporting: `PIPE-P1-06`--`PIPE-P1-09`, `PIPE-P2-01`,
  `PIPE-P2-02`;
- M6: `DEV-P1-02`--`DEV-P1-04`, `DEV-P1-06`, `DEV-P1-07`, `DEV-P2-01`,
  `DEV-P2-02`;
- packaging/maintenance: `PIPE-P3-01`, `DEV-P2-03`; and
- newer findings covering composition claims, fixed-control coupling,
  all-model availability, parent uncertainty, report promotion, and empty
  channel execution.

Every row must finish as `fixed`, `superseded`, or `deleted`, with a regression
and immutable evidence pointer.

## Foundation gates before unknown samples

1. Bind raw FAA/annotation/MTZ, dataset identity, database inventory, source and
   adapter versions, Pixi lock, and Phenix executable identities into task IDs
   and cache keys.
2. Fan out every crystal, hypothesis, seed, finalist, and composition state as
   complete Nextflow items. Enabled no-hit, disabled, and no-model providers
   compose as typed empty bundles.
3. Perform network acquisition only during bounded login staging. Retry only
   classified transient infrastructure failures.
4. Split fixed controls from the general application workflow and publish an
   all-eligible-model registry independently of A-search execution caps.
5. Propagate dataset-qualified observations, space group, resolution limits,
   and overrides through Phaser and refinement.
6. Validate Free-R labels, distribution, and exact HKL-to-flag membership.
7. Preserve parent model uncertainty and separate placed, packed, refined,
   review-supported, and composition-supported states.
8. Use attempt-owned outputs, require parsed final Rwork/Rfree, emit typed
   sequence-map failures, and refuse credible reports with mismatched crystal
   identity or unsupported copy counts.

## General composition records and search

Schema-v2 writes:

- `ComponentSpec` for sequence group, model, requested copies, and mass/model
  evidence;
- `ComponentPlacement` for requested/observed copies and component-specific MR
  evidence;
- `CompositionState` for the ordered component list, parent state, combined
  assets, refinement/map evidence, and support state;
- `CompositionExpansionPlan` for selected/deferred/unsearchable hypotheses and
  budgets;
- `ComponentScopeDecision` for stop reason and claim boundary; and
- `CompositionAssessment` for evidence-derived scientific interpretation.

Historical v1 results remain readable and immutable; new execution writes only
v2 composition states.

Search A jointly over plausible `n=1..4`; sequential placement is rescue-only.
After user/supervisor approval of at most three A states, automatically expand
through B--F. At each depth, consider distinct catalogue sequence groups and
physically possible copy counts `1..4`, rank by localisation wave, SDS/native
PAGE, total-composition Matthews plausibility, model quality, and structural
diversity, and allocate 25 attempts deterministically across parents and
candidates.

Stop on no physical hypothesis, no retained packed state, depth six, 100 total
expansion attempts, explicit review hold, or infrastructure/contract failure.
Retain every state and terminal attempt. No intermediate placement creates a
biological claim.

Validation uses 6RTZ `1A+1B`, 3U7Q `2A+2B`, and 9ECN `2A+2B+2C`, plus missing
and wrong B/C and homomer controls. Four-to-six-component results are always
`provisional_unvalidated_component_depth`.

## Localisation and gel evidence

Run checksum-pinned local PSORTb 3.0.6 with the archaeal model and DeepTMHMM
1.0. Record runtime/image digests, licence/citation, commands, raw output, and
one typed result per sequence group. Do not submit catalogue sequences to a
public service.

Explicit membrane, cell-wall/surface, extracellular, or transmembrane calls are
excluded from the first MR wave but retained. Reopen them only when active
waves produce no packed result. Unknown, conflicting, or failed predictions
remain neutral.

Before the first unknown run, require a user/supervisor gel manifest containing
observation/crystal IDs, SDS or native method, apparent mass, absolute
uncertainty, condition, band role, replicate, notes, and source. SDS ranks
component monomer mass; native PAGE ranks total composition mass. Missing data
remain neutral.

## Unknown-dataset pass 1

Use the checksum-frozen Methermicoccus catalogue and MTZs. Require explicit
`proceed|hold` crystallographic decisions for:

- `AD4QS1P4G2_18`: low completeness and off-origin Patterson peak;
- `CD4QS2P2G1_15`: low completeness and direction-dependent resolution; and
- `CD6QS2P2G1_5`: previously unassessed anisotropy signal.

The fixed `unknown-screen` profile shares catalogue/localisation/provider work,
then emits three crystal items. Run direct PDB plus full-catalogue
ProstT5/Foldseek in 13 deterministic batches of at most 128 queries, and at most
25 first-copy hypotheses per crystal. AFDB remains explicit-mapping only and
ESM Atlas remains disabled.

`unknown-stage-selected` accepts only an owned parent run, review TSV, and
confirmation SHA. `unknown-single-component` runs same-component placement,
refinement, maps, complete-catalogue sequence narrowing, and Coot review while
retaining mixed no-hit/tool/parse outcomes.

Valid pass-1 endpoints include credible single-component, credible
partial/residual, shortlist without credible MR, no supported catalogue
candidate, crystallographic review required, execution failure, and
insufficient evidence. Historical CD6 results remain insufficient evidence and
are not reused as an answer.

## M6 and remaining hardening

After pass 1, repair the remaining M6 input, leakage, network staging, seed,
cache/output, ordering, and cache-location defects. Run operational M6 first,
collect and classify it, then run leakage separately against the unchanged
protocol. Unknown samples must not tune thresholds or contribute to M6.

Add locked offline wheel build/isolated install/schema parity and remove or
migrate legacy nested thread-pool execution. Repeat the independent adverse
review before the Phase III release.

## Unknown-dataset pass 2

Reuse identical frozen inputs, evidence, thresholds, databases, and tools. For
a credible A state, launch the automatic B--F beam using the depth-six,
100-attempt envelope. If no credible A exists, expand first-copy search from 25
to a cumulative 200 hypotheses in bounded batches, then review before component
expansion.

Require final composition and sequence decisions. Exact identity requires
map-supported approval; sequence-equivalence groups are valid endpoints. Report
budget exhaustion, unresolved content, suspected non-protein content, and
depth-six truncation explicitly. Do not calibrate heuristics from these
outcomes.

## Completion gate

Release validated research version `v0.3.0` only when M6 operational/leakage
passes, all finding rows are closed, 9ECN validates depth three, both unknown
passes produce checksum-reconstructible reports, deeper states remain explicitly
provisional, packaging parity passes, and the exact release commit passes local,
CI, and fixed-HPC gates.
