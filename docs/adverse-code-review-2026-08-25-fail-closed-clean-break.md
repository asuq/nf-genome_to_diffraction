# Adversarial review: fail-closed and clean-break policy

Reviewed source: `26e69b95d57d6c8fd543980b661fc055b08bbcc8` on
`dev/phase3`, 2026-08-25.

## Scope and interpretation

Three independent, read-only reviews examined scientific interpretation,
Nextflow/HPC execution, and architectural compatibility against the updated
global fail-closed and clean-break policy. Findings describe the source under
review; an already present test or syntactically valid SHA-256 digest is not
evidence that the scientific meaning of its input was checked.

The current, immutable `v0.1.0` and `v0.2.0` releases, their existing results,
and the explicitly required ability to read their evidence are not defects.
Also excluded are genuinely specified and bounded behaviours: sequential MR
rescue, localisation-wave reopening, the reviewed exact-source archive route,
classified transient retry, separate database preparation/M6 entry points, and
the two documented Python console scripts. The adverse findings concern active
Phase III writers, executable routes, inferred scientific values, and current
compatibility layers that do not have an independent current requirement.

`P0` means scientific identity, credible claims, a mandatory review, authoritative
execution policy, or an independent validation boundary can be bypassed. `P1`
means malformed/missing evidence becomes a valid result, a required canonical
path is bypassable, or retained compatibility introduces an active operational
or scientific ambiguity. `P2` means an obsolete executable surface creates
maintainability and accidental-route risk but has no demonstrated independent
claim bypass. A pre-pass-1 item must be closed before any operator crystal is
analysed; all remaining findings must be closed before unknown pass 2.

## P0: scientific and execution-policy violations

### FCB-P0-01: Phaser fabricates final packing evidence

`src/genome_to_diffraction/mr/phaser.py:527` and `:591` assign one accepted
and packed solution when the required final packing rows are absent. The
existing regression at `tests/unit/test_phaser_adapter.py:311` deliberately
removes those rows and asserts the fabricated packed result; a second
output-only branch does the same.

This promotes an observed placement into an unobserved packing result and can
invalidate an unknown claim or the proposed 9ECN validation.

Required correction: require explicit, installed-runtime-qualified packing
evidence; otherwise preserve an explicitly unassessed placement or emit the
existing typed parse failure. Replace the positive fabrication regressions
with missing-packing rejection regressions.

Gate: before 9ECN scientific acceptance and unknown pass 1.

### FCB-P0-02: unknown credibility trusts self-asserted evidence

`src/genome_to_diffraction/schemas/v2/unknown_assessment.py:108` and `:128`
trust caller-supplied copy, packing, refinement, residual, and review values.
`src/genome_to_diffraction/reporting/unknown_pass1.py:156` and `:279` verify
only that identically hashed files exist; they do not parse the scientific or
review semantics. The supposedly credible fixture at
`tests/unit/test_unknown_pass1_collection.py:45` and `:163` uses arbitrary
plain-text placeholder files and has no mandatory sequence decision, yet
produces `credible_single_component_solution`.

Required correction: construct every scientific status only from parsed,
owned, crystal/state-bound scientific records and independent crystallographic,
A-seed, sequence, and composition decisions. Reject placeholder bytes,
cross-crystal/state decisions, absent checkpoints, and inconsistent metrics.

Gate: before unknown pass 1.

### FCB-P0-03: refinement guesses an unresolved Free-R convention

`src/genome_to_diffraction/diffraction/free_r_identity.py:255` accepts an
unresolved raw-flag convention. `_free_r_arguments` at
`src/genome_to_diffraction/refinement/brief.py:451` then omits the
`test_flag_value`; the tool is left to infer the independent test reflections.
`tests/unit/test_brief_refinement.py:564` currently requires that unsafe route
to succeed.

Required correction: require an authoritative, explicit test flag and exact
HKL-to-test-set identity before scientific refinement; keep unresolved flags as
a typed crystallographic-review hold rather than guessing.

Gate: before unknown pass 1.

### FCB-P0-04: reviewed provider policy is optional

All three active discovery adapters accept both provider-plan and provider-entry
inputs being absent and immediately return the unvalidated request:

- `src/genome_to_diffraction/structure_search/pdb_sequence.py:123`.
- `src/genome_to_diffraction/structure_search/prostt5_foldseek.py:171`.
- `src/genome_to_diffraction/structure_search/afdb_exact.py:161`.

The active CLI also exposes these boundaries as optional. A route can therefore
execute without authoritative enabled/disabled state, reviewed model caps, or
login-versus-compute ownership.

Required correction: require the exact reviewed provider plan and matching
entry in every active invocation; migrate CLI, modules, fixtures, and cache
identities together. Preserve typed configured-disabled and genuine no-hit
results without executing the disabled route.

Gate: before unknown pass 1.

### FCB-P0-05: obsolete live reports fabricate crystal identity and approvals

`src/genome_to_diffraction/review/status_engine.py:181` and `:253` derive
approved/credible counts from candidate counts and write an arbitrary
caller-supplied crystal ID. The legacy commands at
`src/genome_to_diffraction/cli.py:1771` remain executable.
`src/genome_to_diffraction/review/crystal_report.py:274` never reconciles that
ID with the underlying checkpoint. Existing tests even promote a review target
that differs from the refined sequence.

Required correction: delete or deactivate legacy status/report generation and
use the one authenticated schema-v2 evidence-derived producer. Keep immutable
historical results readable without permitting a historical writer to bypass
current claim rules.

Gate: before unknown pass 1.

### FCB-P0-06: mandatory human checkpoints can become empty channels

`main.nf:47` and `:103` permit the current single-component owned parent to be
absent. `workflows/phase3_reviewed_single_component_workflow.nf:117` then
produces `channel.empty()` for both mandatory sequence and composition review
packages while the surrounding workflow remains executable.

Required correction: make a distinct, owned single-component parent and both
human review packages mandatory for the active Phase III continuation; allow a
typed no-candidate scientific outcome without pretending an eligible state was
reviewed.

Gate: before unknown pass-1 continuation.

### FCB-P0-07: component and composition identities are self-asserted

`src/genome_to_diffraction/schemas/v2/composition.py:291`, `:445`, and `:1095`
permit exact sequence support and complete-composition claims from caller-set
fields and syntactically valid digest strings. A reproduced wrong-B example
with TFZ `5.1` and incremental LLG `327.049` was accepted as
`exact_sequence_supported` despite having no map, sequence review, or approved
identity evidence.

Required correction: derive placement identity and composition support only
from parsed, owned, crystal/component-bound sequence and composition decisions;
packing, LLG, TFZ, and opaque digests never establish identity.

Gate: before any pass-1 composition promotion and before unknown pass 2.

### FCB-P0-08: unknown pass 2 has no explicit finding-closure barrier

`docs/phase-iii-roadmap.md:694` starts the second unknown pass without a
dedicated clean-break/fail-closed stop gate.
`docs/phase-iii-finding-ledger.md:82` previously deferred the complete
adversarial closure requirement until `v0.3.0`, after both unknown passes.

Required correction: require every original and new finding to have a final
`Fixed`, `Superseded`, or `Deleted` disposition, focused regression and named
acceptance evidence before pass 2. The eventual fixed pass-2 profile must
reject an absent or stale immutable closure record.

Gate: before unknown pass 2; the documentation stop is immediate.

### FCB-P0-09: no reviewed fixed unknown-dataset HPC profile exists

`src/genome_to_diffraction/hpc/models.py:12`,
`src/genome_to_diffraction/hpc/cli.py:87`,
`bootstrap/nf-gtd-hpc-remote:7`, and `bootstrap/nf-gtd-hpc-smoke-job:8` do
not recognise `unknown-screen`, `unknown-single-component`, or an unknown
pass-2 execution profile. Their owned run-ID patterns, reviewed stage/submit
commands, remote dispatcher, and fixed job wrapper cannot authorise or
independently police any unknown-dataset operation.

Required correction: add one fixed, reviewed stage/submit/collect route for
each actually required unknown phase. Bind exact owner, source, Pixi lock,
site, execution policy, Phenix inventory, reviewed inputs, and resource
limits; require an independently verified RG7 closure record for pass 2.

Gate: before unknown pass 1; exact closure verification before pass 2.

## P1: invalid evidence and non-canonical current execution

### FCB-P1-01: malformed sequence output becomes a scientific no-hit

`src/genome_to_diffraction/refinement/brief.py:553` and `:627` treat a nonempty
corrupt sequence-from-map output as `completed_no_hit`; missing summary fields
and non-finite derived scores can also be silently discarded.

Required correction: require the installed tool's authenticated terminal and
complete expected record structure; distinguish an actual reported zero-hit
from malformed/truncated output and reject non-finite scientific values.

Gate: before unknown pass 1.

### FCB-P1-02: scientific parsers replace malformed bytes

`src/genome_to_diffraction/mr/phaser.py:585`, `:722`, and `:945`,
`src/genome_to_diffraction/mr/partner.py:527`, and
`src/genome_to_diffraction/mr/add_copy.py:651` use lossy `errors="replace"`
decoding on coordinate/log evidence that determines placements and metrics.

Required correction: decode authoritative scientific bytes strictly and emit a
typed parse failure. Lossy decoding is permissible only for explicitly
non-authoritative, presentation-only diagnostics.

Gate: before unknown pass 1.

### FCB-P1-03: missing component mass becomes physically assessed

`CompositionCandidateHypothesis.physical_assessed` at
`src/genome_to_diffraction/schemas/v2/composition.py:533` defaults to `True`.
A component with no exact or bounded mass and an explicit
`sequence_mass_unavailable` warning can nevertheless be accepted as a
physically possible selected hypothesis.

Required correction: derive the explicit physical assessment from actual
component and parent mass evidence; retain missing evidence as the existing
typed `unsearchable_physical_evidence` state.

Gate: before unknown pass 2.

### FCB-P1-04: Phase III approvals are converted back into synthetic v1 data

`main.nf:44`, `workflows/main_workflow.nf:367`, and
`src/genome_to_diffraction/mr/stage_add_copy.py:363`, `:465`, and `:498`
require a legacy review package, generate a v1 approval TSV, and create a v1
validation record despite already possessing an owned schema-v2 review package
and decisions.

Required correction: consume the canonical v2 package, stage, decisions, and
state directly; migrate the actual workflow consumers and tests, then remove
the legacy parameter, adapter, synthetic TSV, and synthetic v1 manifest from
active Phase III execution.

Gate: before unknown pass-1 continuation.

### FCB-P1-05: one production entry point retains two execution authorities

`main.nf:38` and `workflows/main_workflow.nf:298`, `:457`, and `:505` retain
nullable ownership inputs, an opt-in Phase III path, historical
`SELECT_SINGLE_CRYSTAL`, and independent legacy additional-copy/refinement
routes. Current execution therefore has more than one owner and can bypass
strict review contracts depending on invocation.

Required correction: make the Phase III application one canonical typed path;
isolate truly required public controls as reviewed fixed profiles, not implicit
application compatibility modes.

Gate: before unknown pass 1 and the mandatory pre-pass-2 integration gate.

### FCB-P1-06: the complete model registry emits a synthetic v1 manifest

`src/genome_to_diffraction/model_registry/all_eligible.py:393` and `:544`
produce a compatibility manifest for active funnel, first-copy Phaser, and
partner consumers, including
`modules/local/phase3_multicrystal_first_copy_tasks.nf:115` and
`src/genome_to_diffraction/mr/phaser.py:243`.

Required correction: migrate current ranking/Phaser/partner consumers to exact
verified v2 registry entries and remove the synthetic v1 production writer;
retain only genuinely required readers for immutable historical records.

Gate: before unknown pass 2 and any B--F application.

### FCB-P1-07: runtime migration repeatedly infers Phenix identity fields

`bootstrap/nf-gtd-hpc-smoke-job:1677` and `:1798` regenerate a legacy runtime
manifest during every control run.
`src/genome_to_diffraction/phenix/runtime.py:636` and `:702` infer missing
release/build fields and filter malformed notes/warnings.

Required correction: perform one explicit reviewed migration to a strict,
complete executable-hashed runtime manifest, update fixed staging/profile
contracts atomically, and delete per-run inference after the replacement is
qualified.

Gate: before unknown pass 2; do not break current reviewed controls during the
staged migration.

### FCB-P1-08: reviewed A inventories silently discard malformed rows

`src/genome_to_diffraction/mr/stage_add_copy.py:272` silently filters
non-dictionary/malformed inventory items and overwrites duplicate
`solution_id` keys when building a dictionary. Set equality catches some
missing IDs but cannot establish one-to-one source-row conservation.

Required correction: validate every source row against the canonical v2
inventory, reject malformed and duplicate entries before indexing, and require
exact original inventory cardinality.

Gate: before unknown pass-1 continuation; remove the obsolete source inventory
entirely when `FCB-P1-04` is migrated.

### FCB-P1-09: missing current HPC site identity silently becomes Marmic

`src/genome_to_diffraction/hpc/models.py:229` does not validate the owned-run
schema version and defaults an absent `site_id` to `marmic`, even for current
schema-1.1 records. A stripped current Viper capability can therefore be
reinterpreted as a Marmic run.

Required correction: require explicit site identity and exact supported schema
for every current owned run. Permit the documented Marmic-only schema-1.0
default solely inside an explicit read-only historical record reader.

Gate: before unknown pass 1.

### FCB-P1-10: malformed remote protocol fields are discarded or overwritten

`src/genome_to_diffraction/hpc/client.py:2636` silently ignores malformed
ASCII/base64 fields, ignores invalid keys, and overwrites duplicate keys.
`src/genome_to_diffraction/hpc/client.py:736` accepts any nonempty map without
an operation-specific required-field contract.

Required correction: require strict framing, unique keys, exact operation/run
and site ownership, and the complete bounded field set for each reviewed
status/stage/submit/log/collection response.

Gate: before unknown pass 1.

### FCB-P1-11: corrupt failed-job evidence removes its failure signature

`src/genome_to_diffraction/hpc/client.py:2459` publishes an extracted
collection even when `_failure_signature` at `:3197` returns `None` for an
absent result, malformed JSON, non-object result, or unsupported success state.
This can suppress owned failure classification and duplicate-failure guards.

Required correction: validate the exact owned terminal job-result schema, run,
profile, source, scheduler state, and failure class before publishing a
collection. Missing or malformed evidence must be an explicit transfer or
contract failure.

Gate: before unknown pass 1.

### FCB-P1-12: unknown scheduler state becomes an executing job

`src/genome_to_diffraction/hpc/client.py:2390` substitutes `UNKNOWN` for a
missing scheduler state and interprets every nonqueued state as execution.
Malformed or unsupported scheduler output can consequently fabricate a state
transition instead of refusing the status.

Required correction: validate one enumerated queue/running/terminal state and
its consistent terminal flag before changing monitoring phase.

Gate: before unknown pass 1.

### FCB-P1-13: missing remote logs become a fabricated empty log

`src/genome_to_diffraction/hpc/client.py:2431` defaults an absent
`content_base64` field to an empty string. Base64 decoding then succeeds and
publishes an empty log for a response that never supplied its required bytes.

Required correction: require authenticated operation and run identity plus an
explicit `content_base64` field. A genuine zero-byte log must be declared and
verified explicitly.

Gate: before unknown pass 1.

### FCB-P1-14: checkpoint assets can escape their owned directory

`src/genome_to_diffraction/review/crystal_report.py:96` checks an evidence
path lexically and inspects only its final symlink component. Parent traversal
and intermediate symlinks can therefore resolve outside the reviewed package
before the external bytes are hashed/read.

Required correction: reject absolute and `..` components, reject every
symlink component, resolve under the exact owned root, and verify the resolved
path before reading it. Migrate active consumers to the existing strict v2
path contract rather than adding a parallel parser.

Gate: before unknown pass 1.

### FCB-P1-15: compute-worker network isolation is not enforced

`modules/local/retrieve_afdb_exact.nf:4` declares the intended network/login
labels, but no tested worker-side socket prohibition exists. The current
Phase III roadmap explicitly acknowledges that compute-worker denial and real
provider staging remain unqualified.

Required correction: enforce one concrete worker-offline execution policy,
permit acquisition only in the reviewed bounded login route, and qualify both
paths once on the target HPC site.

Gate: before unknown pass 1.

## P2: remove superseded executable surfaces

### FCB-P2-01: root Nextflow stage wrappers retain competing application paths

The repository currently exposes 12 root-level `.nf` entry points. Active
fixed-wrapper consumers are present in
`bootstrap/nf-gtd-hpc-smoke-job:619`, `:823`, `:1012`, `:1453`, and `:3690`,
with corresponding public examples in `README.md:413`.

Required correction: migrate every active fixed wrapper, example, and test to
the canonical application/fixed-control route in one coherent change, then
delete superseded root stage wrappers. Preserve separately specified database
preparation and M6 entry points. Do not remove a still-owned reviewed control
route before its replacement is qualified.

Gate: before unknown pass 2.

### FCB-P2-02: permanently retired CLI commands remain executable

`src/genome_to_diffraction/cli.py:731`, `:798`, `:2351`, and `:2439` expose
historical control/M6 actions that are deliberately guaranteed to fail, while
tests and documentation preserve them solely as migration diagnostics.

Required correction: remove fail-only parser branches, dispatch, obsolete
request types/tests, and public references after confirming their canonical
Nextflow replacements. Retain genuinely used preparation/classification
helpers and immutable historical evidence readers.

Gate: before unknown pass 2.

## Review disposition

This report records observed current behaviour; it does not declare any known
control, unknown sample, M6 track, or Phase III milestone scientifically
accepted. The binding remediation order and stop criteria are recorded in the
[fail-closed and clean-break remediation roadmap](phase-iii-fail-closed-clean-break-roadmap.md)
and tracked in the
[Phase III finding ledger](phase-iii-finding-ledger.md).
