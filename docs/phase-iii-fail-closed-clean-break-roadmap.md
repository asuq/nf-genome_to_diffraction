# Phase III fail-closed and clean-break remediation roadmap

## Purpose and non-negotiable stop gates

This roadmap implements the updated global fail-closed and clean-break policy
for the active Phase III application. Its source is the independent
[2026-08-25 adverse review](adverse-code-review-2026-08-25-fail-closed-clean-break.md);
all finding IDs and final dispositions belong to the single
[Phase III finding ledger](phase-iii-finding-ledger.md).

The objective is one small, reviewable execution path, not a second defensive
framework. Missing, malformed, contradictory, or unreviewed state fails
explicitly. Scientific no-hit, configured-disabled, deferred, unknown, and
insufficient-evidence states remain honest typed outcomes; none is silently
converted into a stronger result.

Two mandatory stop gates supersede any more permissive ordering elsewhere:

1. **Before unknown pass 1:** close every issue that can affect provider policy,
   packing, Free-R, scientific byte parsing, sequence output, crystal identity,
   mandatory human decisions, or first-pass claim generation.
2. **Before unknown pass 2:** close every original and newly discovered
   scientific, fail-closed, execution, and clean-break finding. Every ledger
   row must have an evidenced final `Fixed`, `Superseded`, or `Deleted`
   disposition; local-only fixes and pending real controls are not acceptance.

No unknown dataset is a validation control. The frozen 6RTZ, 3U7Q, wrong-B,
homomer, and 9ECN controls retain their original interpretation; MR scores and
packing never establish sequence identity. Immutable historical v0.1/v0.2
evidence remains readable but does not justify an active compatibility writer.

## RG0 - Record the review and close the planning bypass

Scope: `FCB-P0-08` and every new finding inventory entry.

- Record the reviewed commit, exact locations, reproduction, severity,
  dependency, required focused regression, and scientific stop gate.
- Add this roadmap and review to the main Phase III roadmap and documentation
  index.
- Insert an unconditional stop immediately before Phase III `PH7`.
- Require the future fixed unknown-pass-2 stage/submit profile to consume one
  immutable, exact-source finding-closure record; an absent, stale, or
  incomplete record refuses scheduling.
  Completed locally: one content-addressed verifier binds the exact source
  commit/tree, ledger bytes, all final finding dispositions, exact-source CI,
  adverse review, integration gate, public controls, M6, and pass-1 evidence.
  It rejects local/pending dispositions, incomplete inventories, changed
  ledger bytes, malformed/duplicate JSON, and cross-source records. Fixed
  pass-2 profile integration remains for RG7.
- Distinguish required historical readers and explicitly approved, bounded
  operational/scientific exceptions from removable current compatibility.

Acceptance: documentation links pass; the new ledger lists every reviewed
finding; the Phase III roadmap explicitly forbids pass 2 before RG7.

## RG1 - Make execution, scheduler, and review ownership mandatory

Scope: `FCB-P0-04`, `FCB-P0-06`, `FCB-P0-09`, `FCB-P1-04`, `FCB-P1-05`,
`FCB-P1-08`, and `FCB-P1-09` through `FCB-P1-15`.

- Add one concrete reviewed fixed profile for `unknown-screen` and
  `unknown-single-component`. Add pass-2 execution only with its independent
  RG7 closure record; no unknown operation may bypass the reviewed wrapper.
- Make the reviewed provider plan and matching route entry mandatory in PDB,
  Foldseek, and AFDB discovery commands, modules, fixtures, and cache IDs.
- Preserve typed configured-disabled and genuine completed-no-hit routes
  without scheduling unapproved work.
- Require explicit current-schema HPC site identity and an operation-specific
  strict remote protocol; reject malformed/duplicate/missing fields, unsupported
  scheduler states, missing log payloads, and incomplete failed-job evidence.
- Reject escaped/intermediate-symlink review assets before reading them.
- Enforce a worker-offline network policy and qualify reviewed login-side
  provider staging separately from compute-worker socket denial. Completed
  locally: every Marmic and Viper in-job Nextflow task uses the fixed
  fail-closed user/network-namespace shell; controller-local labels are not a
  network exception. The fixed argument-free Marmic qualification profile now
  schedules one independent Slurm child and one controller-local task, binds
  both policy checksums, and accepts only distinct namespaces plus explicit
  TEST-NET-1 socket denial. Exact-source CI `32908137245` passed on `18036c9`;
  one real Marmic result and bounded pre-submit login staging remain. The other
  site must qualify before it is used scientifically.
- Require a distinct owned single-component parent and both final human
  checkpoints for every eligible Phase III continuation.
- Consume the approved schema-v2 A review, exact decisions, and execution
  identity directly. Remove legacy review inputs, fabricated v1 TSVs/manifests,
  and duplicate/malformed inventory acceptance.
  Completed locally: the owned A package is independently portable, the active
  seed stage emits one schema-v2 authority without translated approval files,
  and current additional-copy/refinement consumers reject legacy or dual
  authority. Exact-source CI is green; owned-HPC qualification remains.
- Replace optional Phase III/legacy application switches with one canonical
  typed application route while preserving genuinely separate reviewed control
  profiles. Completed locally: `phase3_application.nf` owns the reviewed joint
  first-copy and owned single-component operations, while archival `main.nf`
  accepts only its v0.2 authority. Exact-source CI is green; owned-HPC
  qualification remains.

Acceptance: one focused negative regression for absent profile/policy, disabled
route, wrong owner/site, corrupt protocol/result, missing log, unknown
scheduler state, escaped review asset, unapproved worker network access, empty
mandatory review channel, duplicate A item, and legacy entry-path bypass;
completed legitimate zero-candidate cases remain explicit.

Stop: before unknown pass 1.

## RG2 - Refuse invented scientific observations

Scope: `FCB-P0-01`, `FCB-P0-03`, `FCB-P1-01`, and `FCB-P1-02`.

- Qualify the exact installed Phaser terminal packing representation against
  public control evidence; reject missing or contradictory packing records.
- Require one authoritative Free-R test value and exact independent reflection
  membership before refinement. Hold unresolved conventions for review.
- Require complete, explicitly successful sequence-from-map output; malformed,
  truncated, non-finite, and genuinely empty records remain distinguishable.
- Decode scientific PDB, solution, and authoritative log bytes strictly;
  preserve raw bytes and their hashes when a typed parse failure occurs.

Acceptance: one focused regression per invented/missing observation plus the
existing 6RTZ/3U7Q public controls. Missing packing blocks 9ECN acceptance;
none of these defects may be tuned or diagnosed against an unknown crystal.

Stop: before 9ECN acceptance where packing is relevant, and before unknown
pass 1 for every applicable scientific path.

## RG3 - Derive claims from complete, independently owned evidence

Scope: `FCB-P0-02`, `FCB-P0-05`, and `FCB-P0-07`.

- Remove active legacy status/report generators and their arbitrary crystal-ID
  route; preserve read-only access to immutable historical reports.
- Parse and independently authenticate the actual crystallographic, A-seed,
  sequence, and composition review packages/decisions.
- Derive copy counts, packing, final refinement metrics, residual content, and
  state/crystal identity from their checksum-bound scientific artifacts.
- Derive exact component/sequence support only from owned map-supported
  sequence decisions. Derive composition support only from the distinct
  human composition decision.
- Keep wrong-B packed states at search evidence only; scores, packing, digest
  syntax, or caller assertions cannot promote sequence/composition identity.

Acceptance: placeholder bytes, missing sequence review, swapped crystal/state,
fabricated credible status, and the frozen wrong-B TFZ/LLG all fail their
focused regressions; all four required decisions support the positive public
control fixture.

Stop: first-pass status/identity paths before unknown pass 1; all
multi-component claims before unknown pass 2.

## RG4 - Remove compatibility-only current scientific adapters

Scope: `FCB-P1-03`, `FCB-P1-06`, and `FCB-P1-07`.

- Derive physical composition eligibility from complete parent/component mass
  evidence; absent masses remain explicitly unsearchable.
- Migrate ranking, Phaser, and partner search to content-bound v2 all-model
  registry entries; delete the synthetic v1 compatibility manifest.
  The synthetic writer is now deleted locally; active first-copy consumers use
  the independently verified v2 registry, while exact-source CI and owned-HPC
  qualification remain outstanding.
- Perform one reviewed migration to a strict, complete, executable-hashed
  Phenix runtime manifest. Update owned staging, fixed profile contracts, and
  focused fake-HPC tests atomically; then remove per-run refresh/inference.

Acceptance: mass-absent selection, registry substitution, runtime version
fabrication, missing executable identity, and migration fallback each fail a
focused test; public controls pass against the single canonical contract.

Stop: before unknown pass 2 and before any real B--F application.

## RG5 - Complete the clean break in public executable surfaces

Scope: `FCB-P2-01` and `FCB-P2-02`.

- Inventory every still-live root `.nf` caller before changing it.
- Migrate reviewed fixed wrappers, public examples, docs, Nextflow checks, and
  focused integration tests to the canonical application/control path.
- Preserve independently required database preparation and M6 entry points;
  delete superseded root stage entry points only after their replacements pass.
  Completed locally: one typed `qualification.nf` owns all nine fixed stage and
  control operations, rejects unknown or incomplete authority before
  scheduling, and is used by the reviewed HPC wrapper, examples, documentation,
  Nextflow checks, and dispatcher integrations. All replacement operations
  passed the complete stub gate before the nine superseded roots were deleted.
  Exact-source CI `32910230567` passed on `de2f4c4`; real fixed-profile
  qualification remains before final disposition.
- Remove permanently failing retired CLI subcommands, parser/dispatch branches,
  compatibility-only tests, and stale documentation.
- Preserve genuinely shared preparation helpers and historical evidence
  readers, not active legacy production routes.

Acceptance: every documented executable has one current owner and one successful
route; reviewed fixed controls still run, and no retired command or obsolete
root wrapper remains reachable.

Stop: before unknown pass 2.

## RG6 - Reconcile public validation, M6, and all previous findings

Scope: every existing `PIPE-*`, `DEV-*`, and `PH3-*` finding on which first or
second unknown-pass correctness depends.

- Finish public 6RTZ/3U7Q control and 9ECN three-component qualification using
  the canonical fail-closed execution path.
- Preserve the deliberately wrong-B and wrong-C negative controls as
  `search_evidence_only`; require no false additional component in homomers.
- Run the unchanged M6 operational track, classify/collect it, and only then
  run the separately staged leakage track under the same frozen protocol.
- Reconcile all earlier findings with focused regressions, exact-source CI,
  real fixed-HPC evidence where required, and an explicit final disposition.
- Preserve approved Phase III budgets, user/supervisor review, immutable
  first-pass outputs, and the prohibition on unknown-outcome threshold tuning.

Acceptance: old and new ledger rows are all `Fixed`, `Superseded`, or `Deleted`;
real evidence exists wherever a row previously said "fixed locally" or
"qualification pending".

## RG7 - Authorise the second unknown-dataset pass once

Dependencies: RG0--RG6 complete; complete original finding ledger; final known
control and M6 evidence; immutable supervised unknown-pass-1 evidence.

Run one named integration gate, rather than the full suite after every change:

1. Locked focused scientific, reviewed-workflow, schema, packaging, and
   documentation checks pass on the exact candidate commit.
2. A fresh adverse review confirms no active fabricated state, guessed Free-R,
   provider-policy bypass, silent missing checkpoint, optional current
   compatibility, or unowned claim generator remains.
3. Every original and new finding has exact regression, disposition, and
   required fixed-HPC evidence; no `Open`, `Partial`, or
   `qualification pending` row remains.
4. The owned 6RTZ/3U7Q/9ECN, wrong-component/homomer, M6 operational/leakage,
   and unknown-pass-1 records retain complete checksums and unchanged policy.
5. One exact-source CI run and reviewed gate record authorise the fixed
   pass-2 profile; stale, missing, or different-source gate records fail.

Only after this checkpoint may `PH7` launch the bounded second unknown pass.
The pass retains at most six distinct components, three parent states per
depth, 25 attempts per depth, and 100 additional-component attempts per
crystal. Depths four to six remain provisional; human final composition and
sequence review remain mandatory.

## Test and operational policy

- Add one focused red/green regression for each independently reproducible
  defect; share one regression only when two findings have the same mechanism.
- Run focused tests while iterating. Reserve full locked/CI gates for canonical
  integration, M6, unknown-pass, and release milestones.
- Use one reviewed Marmic/Viper fixed-profile run per accepted integration
  revision; never launch duplicate jobs or reuse failed caches.
- Do not introduce speculative generic fallback, retry, compatibility,
  migration, or plugin frameworks.
- Keep the original frozen acceptance thresholds and human decision rules.
- Require a fresh user decision when no independent authoritative Free-R,
  sequence, composition, licensed runtime, or input evidence exists.
