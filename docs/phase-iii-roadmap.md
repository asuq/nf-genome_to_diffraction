# Phase III roadmap: hardening, general composition search, and unknowns

## Purpose and branch boundary

Phase III turns the experimental v0.2 two-component prototype into a validated
research workflow. It closes the remaining old and newly discovered defects,
repairs and accepts M6, generalises composition states to `A+B+C+...`, and runs
the three operator crystals as exploratory applications rather than validation
truth.

Experimental `v0.2.0` is immutable at exact-source Marmic-qualified commit
`68d216f`. The `dev/phase3` history now includes that release boundary. No Phase
III real-data, M6, or unknown-crystal run may reinterpret or reuse the v0.2 P6
run; each requires its own fixed profile and Phase III acceptance evidence.

The application records support arbitrary ordered component lists. Fixed Phase
III execution is bounded to six distinct components, three retained parent
states per depth, 25 attempts per depth, and 100 additional-component attempts
per crystal. Three-component placement is validated with 9ECN. Depths four to
six remain provisional until independent positive controls exist, including
when the retained search also stops for budget exhaustion or reviewer hold.

## Mandatory fail-closed and clean-break stop gates

The independent
[2026-08-25 fail-closed/clean-break adverse review](adverse-code-review-2026-08-25-fail-closed-clean-break.md)
identified fabricated scientific state, unreviewed provider/scheduler routes,
missing human checkpoints, and active legacy execution paths. Existing status
paragraphs below establish only their specifically tested narrow behaviour;
they do not override reopened scientific or operational findings.

The [fail-closed and clean-break remediation roadmap](phase-iii-fail-closed-clean-break-roadmap.md)
defines mandatory `RG0`-`RG7` milestones. Unknown pass 1 may not stage or run
until its named scientific, provider, review, and execution prerequisites are
closed. Unknown pass 2 may not stage or run until **every** original and new
[finding-ledger](phase-iii-finding-ledger.md) row is `Fixed`, `Superseded`, or
`Deleted` with focused regression and required immutable qualification evidence.
The future fixed second-pass wrapper must independently authenticate that
exact-source closure record.

Historical v0.1/v0.2 results remain readable and immutable; that requirement
does not authorise active legacy Phase III writers, compatibility bridges, or
fallback paths.

## Milestone sequence

### PH0 - Rebaseline and preserve evidence

- Maintain one finding ledger for the original adverse review and all later
  findings.
- Bind each row to a regression, dependency, milestone, immutable evidence, and
  final disposition.
- Preserve v0.1/v0.2 schemas, outputs, control evidence, and readers as
  immutable historical records.
- Require every original and new finding to finish `fixed`, `superseded`, or
  `deleted` before unknown pass 2; recheck final dispositions at v0.3.0.

### PH1 - Execution and crystallographic foundations

Before unknown samples:

1. Bind raw FAA/annotation/MTZ, dataset identity, database inventory, source and
   adapter versions, Pixi lock, and Phenix executable identities into task IDs
   and cache keys.
2. Fan out every crystal, hypothesis, seed, finalist, and composition state as
   complete Nextflow items. Shared catalogue/provider values must be reusable by
   every item.
3. Make provider configuration authoritative. Enabled no-hit, disabled, and
   no-model branches must compose as typed empty bundles.
4. Permit network acquisition only during bounded login staging. Compute work
   must fail closed on network access. Retry only classified transient
   infrastructure failures.
5. Split fixed controls from the application workflow and publish an
   all-eligible-model registry independently of A-search caps.
6. Propagate dataset-qualified observations, space group, resolution limits,
   and overrides through Phaser and refinement.
7. Validate Free-R label, convention, distribution, and exact HKL-to-flag
   membership and verify preservation after refinement.
8. Preserve parent model identity/error and distinguish `placed`, `packed`,
   `refined`, `review_supported`, and `composition_supported`.
9. Use attempt-owned transactional outputs, require parsed final Rwork/Rfree,
   emit typed sequence-map failures, and refuse credible-report promotion when
   crystal identity, copy support, final metrics, or review evidence is absent.

Status: attempt-owned T12 outputs, the final-Rwork/Rfree boundary, and
candidate-level typed sequence-map parse failure are implemented on
`dev/phase3`. The remaining PH1 boundaries are still open or partial as
recorded in the finding ledger.

All three existing network-capable processes carry both reviewed site aliases:
`run_local` keeps Marmic execution on the outer Nextflow controller and
`needs_internet` does the same on Viper. The controller itself runs inside a
Slurm allocation, so those aliases are scheduling boundaries rather than login-
network permission. Every child and controller-local Nextflow task enters a
fail-closed Linux user/network namespace through the fixed site process shell;
absence of the runtime or a numeric Slurm context fails rather than restoring
network access. Provider objects must be staged by the reviewed dispatcher on
the login node before submission. A fixed Marmic `phase3-network-probe` now
binds the tracked site/shell checksums and schedules one ordinary Slurm child
plus one controller-local task; both must prove distinct worker namespaces and
explicit TEST-NET-1 socket denial. Its focused local contracts and dispatcher
stage/submit integration pass, and exact-source CI `32908137245` passed on
`18036c9`. The real Marmic result remains. Bounded provider staging is a
separate qualification gate; only the selected scientific execution site gates
the next run.

Transient infrastructure recovery now uses one explicit boundary instead of a
general retry framework. Classified temporary transport/HTTP failures return
`EX_TEMPFAIL` 75; Nextflow retries that exit exactly once. Permanent provider,
input-contract, parser, and scientific failures are never retried, and the
existing candidate-level sibling `finish` behaviour is retained. A real local
Nextflow fixture proves both the two-attempt recovery and one-attempt contract
failure; real scheduler-node/preemption qualification remains separate.
Both approved Phase III control profiles now also retain their own normalised
application-log diagnostics in the existing controller failure signature, so
different root causes cannot collapse into one feedback-chain failure.

One schema-v2 `PhaseIIIExecutionIdentity` now binds every raw catalogue FAA and
annotation, crystal MTZ, database inventory, source commit/tree, nf-helper,
Pixi lock, execution policy, required Phenix executable, and adapter version
without retaining machine paths. Independent mutation tests change the identity
for each surface and refuse missing annotations, MTZs, or Phenix commands.
The composition-attempt fan-out now carries this identity into every selected
task/cache item. The complete unknown-screen panel inventory remains retained
once outside independent child inputs: an actual local Nextflow candidate
mutation reruns its one affected crystal while 33 shared/sibling tasks keep
their exact cache hashes and published bytes. Selective reruns for independent
raw/tool mutations and consumption by other Phase III task families remain
pending.

The all-eligible model registry is now separated from the A-search execution
cap. It retains every validated catalogue sequence-group/model/provider/variant
and typed no-model inventories under one deterministic content identity. The
schema-v2 composition planner now reloads that registry and binds every parent
component and candidate-copy input to a checksum-verified entry or typed
unavailable reason. Models outside the 25-item A shortlist remain schedulable;
registry, provider, variant, and exact-model absences remain retained
unsearchable hypotheses. Candidate generation and composition execution remain
separate pending slices.

An opt-in schema-v2 diffraction selection now binds the MTZ dataset,
dataset-qualified observations, space group, resolution range, overrides, and
command identities. Observation labels, Phaser/refinement space group,
Phaser/refinement low/high limits, and sequence-from-map high resolution are
explicit. The Phaser PHIL names are bound to the previously retained no-data
installed-runtime defaults; legacy commands are unchanged. The real Phase III
multi-crystal production path now explicitly creates one crystal-owned
diffraction-selection record plus its complete same-dataset raw Free-R identity
before scheduling Phaser. Each first-copy task consumes that exact selection,
derives its content-bound hypothesis from the same immutable item, and applies
the qualified space-group/resolution parameters; ambiguous, missing, constant,
or cross-dataset Free-R arrays refuse publication. Real installed-tool execution
remains a separate qualification gate. Phase III refinement
now verifies its exact checksum-bound raw source before comparing the parent
against the selected dataset, every HKL-to-observation/sigma value, and the
complete source HKL-to-Free-R mapping. These permutation-invariant derivation
proofs are retained in the command identity before Phenix can start; the
refined child is checked independently. Reindexing/symmetry equivalence is not
inferred.

Reviewed Phase III single-component continuation now regenerates the same
authenticated diffraction selection and Free-R identity in its single-crystal
dispatch. Each approved same-component seed independently verifies the selected
dataset against its exact crystal, hypothesis, preflight, and raw MTZ; its
Phaser PHIL explicitly retains the selected labels, space group, and both
resolution limits. Each refinement finalist also receives the exact Free-R
identity and complete crystal/catalogue/Phenix evidence. Deep content caching
reruns only the two affected placement tasks and two affected finalists after a
selection-byte mutation; all seven neighbouring historical scientific tasks
retain their cache entries. Rejected/deferred A states schedule no placement.
Historical placement/refinement processes remain unchanged. Real installed-tool
execution and complete three-crystal continuation remain separate gates.

A separate schema-v2 Free-R foundation now binds an exact label and MTZ dataset
to the diffraction selection, rejects non-finite, non-integral, constant, and
ambiguous arrays, records the complete raw-value distribution, and hashes the
sorted HKL-to-raw-flag mapping. A derived-MTZ comparison fails on missing HKLs
or changed flags and is invariant to row order. The test flag value remains
explicitly unresolved unless supplied from reviewed external provenance.
Opt-in Phase III brief refinement now requires that content-address-valid
identity from the same diffraction selection, includes the exact label and
convention state in its command identity, rejects an unproven parent before
tool execution, and refuses completion or downstream sequence-map execution
unless the refined MTZ also preserves the exact raw mapping.
The comparison deliberately recognises row permutation only; it does not claim
symmetry or reindexing equivalence.
Phase III refinement now passes the officially documented second
`miller_array.labels.name` for the exact Free-R label, requires existing flags,
and fixes `r_free_flags.generate=False`. A reviewed explicit test value is
passed when available; otherwise Phenix's automatic test-value selection is
recorded as unresolved rather than fabricated. Preservation against a real
Phenix-derived MTZ remains the qualification boundary. Parameter names follow
the [official `phenix.refine` command-line reference](https://phenix-online.org/documentation/reference/refinement.html).

Fixed-component partner searches now preserve the reviewed parent's original
model identity/error source in Phaser, command/result records, and cache
identity. Placement no longer silently resets a lower-identity A model to 100%
for the B-F searches.

The normal heteromer application no longer depends on the fixed 6RTZ control.
Its reviewed approved A seed feeds the existing complete-catalogue partner
planner, one task per selected B candidate, and the typed attempt summary.
The fixed-control Phaser task executes only when its optional control
preparation is explicitly supplied. A focused real local Nextflow stub proves
the separate application/control process inventories and cached application
resume; scientific Phenix qualification and the general depth-three adapter
remain separate gates.

The schema-v2 component-expansion execution input now binds one authoritative
selected depth candidate to a packed parent, component-only fixed coordinates
and distinct original error models for every existing component, the exact
parent LLG, a registry-resolved candidate model/copy count, diffraction
selection, and Free-R identity. It rejects combined-coordinate or duplicate
coordinate collapse. The command/parser adapter remains deliberately blocked:
retained evidence qualifies only one fixed-at-origin ensemble, not the
multi-fixed partial syntax required for a depth-two-or-higher parent.

A fixed `phase3-phenix-probe` profile now captures only the exact installed
`phenix.phaser --show_defaults` output under the checksum-frozen Marmic runtime.
It exposes no paths or command arguments and performs no scientific execution.
The real Marmic probe passed at exact source `a962e97` and qualified
`phaser.keywords.general.xyzout_ensemble=True` plus exact `.sol` output. The
fixed partner command now requests both explicitly, and a content-addressed
parser binds exact `SOLU 6DIM` entries to source-model-matched combined-PDB
chains because the installed wrapper does not emit native per-ensemble PDBs.
The local bridge validates atom-complete grouped coordinates against the packed
parent and preserves each component's independent original uncertainty in the
existing fixed-execution contract. A retained real 3U7Q replay reconstructs
all 16,116 atoms after canonicalising mathematically equivalent signed-zero
coordinates. The reviewed collector now permits 128 MB per file and 512 MB
overall, retaining the 40,035,916-byte 3U7Q input MTZ and partner output.
Fresh two-control qualification and multi-fixed command syntax remain pending.

The isolated complete-item workflow now proves three crystal items can reuse
one catalogue and one provider preparation through a byte-identical cached
resume. The composition-attempt boundary additionally binds each selected row
to its parent state, depth candidate, parent/candidate model resolutions,
diffraction selection, Free-R identity, all-model registry, and global
execution identity. Every task now also carries its exact
`ComponentExpansionExecutionInput`, preserving component-only fixed coordinates,
per-component uncertainties, candidate evidence, and parent LLG. It proves one
25-attempt budget shared across three parents, typed empty/no-model scheduling,
and byte-identical cached resume, but remains stub-only. The ordinary application
first-copy, approved-seed, and refinement workflows now broadcast their shared
singleton catalogue/review/diffraction inputs as reusable values. One local
production-workflow regression schedules exactly three independent hypotheses,
two seeds, and two finalists, then caches all seven identical tasks on resume;
the original one-task-per-stage failure is retained as focused red/green
evidence. Live Phenix execution and general composition integration remain
separate pending gates.

The authoritative provider plan now also drives a fixed local typed-empty graph.
One enabled local scientific no-hit, two configured-disabled routes, and one
unsupported/provider-unavailable route retain every catalogue query and finish
as one content-addressed `completed_no_model` all-model registry. Its dedicated
stub resumes byte-identically and the normal enabled route fails before provider
or network execution. The ordinary application now also propagates documented
enabled no-hits and disabled routes through zero-coordinate registration,
zero-model predicted/experimental preparation, the complete typed model
registry, and a zero-candidate file-based MR-seed checkpoint. Each empty input
requires its complete upstream typed result or checksum-bound registration
manifest; unexplained truncation still fails. Real provider/HPC qualification
remains a separate pending gate.

### PH2 - General component contracts and bounded search

New schema-v2 writes use:

- `ComponentSpec` for sequence group, model, requested copies, and mass/model
  evidence;
- `ComponentPlacement` for requested/observed copies and component-specific MR
  evidence;
- `CompositionState` for ordered components, parent state, combined assets,
  refinement/map evidence, and support state;
- `CompositionExpansionPlan` for selected/deferred/unsearchable hypotheses and
  deterministic budgets;
- `ComponentScopeDecision` for supported depth, stop reason, residual content,
  and claim boundary; and
- `CompositionAssessment` for evidence-derived scientific interpretation.

Historical v0.2/v1 results remain readable and immutable. New Phase III
execution writes schema-v2 states.

Status: all six immutable schema-v2 composition records, the supporting model-
resolution record, the authoritative parent-bound depth plan, and the
content-addressed selected-attempt inventory are implemented. The deterministic
planner shares one 25-attempt budget across at most three parents, preserves
every disposition, enforces the 100-attempt global bound, and binds the
independent all-model registry without consulting the A shortlist. A stub-only
Nextflow fan-out now proves exact complete task identities and resume caching;
live general-component Phaser execution remains a separate pending slice. The
fixed 6RTZ/3U7Q control profile now binds `.sol` entries to exact source-model
polymer sequences, derives one multi-copy coordinate per component, and proves
complete atom recombination in a separate 46-file Phase III checksum boundary.
The retained real 6RTZ result reconstructs all 3,543 atoms locally; fresh
two-control Marmic qualification remains the next gate. A pure local bridge
binds those verified coordinates to the packed parent and each original
component-specific Phaser error model without inventing a command. The pure-Python
candidate generator now supplies complete parent/catalogue rows with four
parent-specific total-composition copy assessments, typed gel/localisation
priors, cap-independent model selection, quality/diversity evidence, and exact
retained counts.

The schema-v2 score boundary now binds a complete verified placement inventory
to the newly searched component's own ensemble and TFZ. It retains the fixed
parent's combined LLG, the new combined LLG, and the independently checked
increment between them as separate raw values. Exact parent/candidate models,
copy counts, result checksum, and candidate-only coordinates remain bound;
packing cannot promote a sequence or composition claim. Live general-component
Phaser parsing remains a separate post-control gate.

The ordinary diverse-model funnel has an explicit Phase III joint-A mode. It
preserves all four configured, physically possible Matthews copy alternatives,
excludes counts above four before applying any per-model cap, and constructs
one joint Phaser hypothesis per retained candidate/copy count. The 25-attempt
hard ceiling applies across the complete A search. The canonical
`phase3_application.nf` root always selects this mode and exposes no legacy
single-copy switch; archival application and standalone controls remain
separate.
Every schema-v2 unknown-screen task now binds the selected hypothesis's exact
requested copy count; a mismatched task is rejected before fan-out. Real Phase
III Phaser execution remains a separate control-qualified gate.

The canonical `phase3_application.nf` first-copy operation owns the Phase III
multi-crystal route. One shared catalogue/provider
preparation feeds one manifest-owned MTZ dispatch and one existing diverse
funnel per crystal. Every selected hypothesis becomes a complete independent
Phaser task, and each crystal receives its own unapproved MR-seed checkpoint;
empty/no-model branches retain a separate review rather than blocking siblings.
A synthetic three-crystal actual Nextflow regression verifies exact shared/task
counts, independent packages, unchanged cached identities and published bytes,
and canonical-root routing. Archival `main.nf` has no Phase III parameters, and
both roots reject cross-authority inputs before scheduling. Real Phase III
Phenix execution remains a separate control-qualified gate. Exact-source CI
`32904417863` passed on `b55348a`.

Search A jointly over plausible `n=1..4`; sequential placement is rescue-only.
After review approval of at most three A states, automatically expand through
B-F. At each depth, exclude represented sequence groups, consider physically
possible copy counts `1..4`, rank by localisation wave, SDS/native-PAGE,
total-composition Matthews plausibility, model quality, and structural
diversity, and allocate at most 25 attempts deterministically across parents,
candidates, and copy counts.

Stop on the first applicable condition: no physical hypothesis, no retained
packed state, depth six, 100 total expansion attempts, explicit review hold, or
infrastructure/contract failure. Retain every state and terminal attempt. No
automatic scientific claim is made between depths.

### PH3 - Known-control validation ladder

- 6RTZ `1A+1B`: recover two components and do not support false C.
- 3U7Q `2A+2B`: recover joint multi-copy composition and do not support false C.
- 9ECN `2A+2B+2C`: recover McrA/McrB/McrG and validate depth three.
- Missing/wrong B and wrong C: packing or fallback scores cannot establish
  identity or composition.
- Homomer controls: no false additional distinct component.
- Depths four to six: executable and reviewable but always
  `provisional_unvalidated_component_depth`.

The schema-v2 scope/assessment boundary now applies this depth limitation
before incomplete-stop classification, so budget exhaustion or reviewer hold
cannot relabel a four-to-six-component retained state as an ordinary partial
or complete result. Review evidence, packing, and final refinement never make
such a composition eligible for a complete claim.

Status: the fixed 9ECN input preparation now binds all three frozen catalogue
identities, exact A/B/C source entities and chain pairs, the 73-residue McrG
expression-tag alignment, McrA modified residues, three experimental models,
and one joint two-copy McrA hypothesis. Real frozen inputs produce a 147,424-row
MTZ; this is preparation evidence only, and execution remains blocked until the
6RTZ/3U7Q native-placement recombination gate passes.

### PH4 - Localisation and gel evidence

Status: the schema-v2 JSON/TSV gel manifest, crystal-reference validator, and
checksum/version-bound offline PSORTb archaeal adapter are implemented on
`dev/phase3`. The catalogue-wide local workflow emits one PSORTb item and one
typed blocked DeepTMHMM result per sequence group, requires exact result coverage,
retains all first-wave exclusions, and gates deterministic reopen on a complete
zero-pack active wave. DeepTMHMM remains `blocked_unverified_cli` until the supplied
image exposes a verifiable local entrypoint/output format. Composition-planner
consumption is now implemented through the complete candidate-generation
inventory; real runtime/profile qualification remains pending.

Run checksum-pinned local PSORTb 3.0.6 with its archaeal model and DeepTMHMM
1.0 from a user-provided academic runtime image. Record runtime/image digests,
versions, licences, commands, raw outputs, and one typed result per sequence
group. Do not submit catalogue sequences to a public service.

Explicit membrane, cell-wall/surface, extracellular, or transmembrane calls are
excluded from the first MR wave but retained and reopened only when active
waves produce no packed result. Unknown, conflicting, or failed predictions are
neutral.

Before unknown pass 1, require a typed gel manifest with observation/crystal
IDs, SDS or native method, apparent mass, absolute uncertainty, condition, band
role, replicate, notes, and source. SDS ranks component monomer mass; native
PAGE ranks total composition mass. Missing evidence remains neutral.

### PH5 - Unknown-dataset pass 1

Stop gate: complete the applicable `RG1`-`RG3` scientific, provider, owned
execution, human-review, and evidence-derivation requirements in the
[fail-closed and clean-break roadmap](phase-iii-fail-closed-clean-break-roadmap.md)
before staging or scheduling any unknown crystal. A matching SHA-256 digest, a
self-asserted status, or a green synthetic fixture without parsed evidence is
not acceptance.

Use the checksum-frozen catalogue and MTZs. Require file-based `proceed|hold`
crystallographic review for AD4 completeness/Patterson evidence, CD4
completeness/direction-dependent resolution, and the previously unassessed CD6
anisotropy signal.

The fixed `unknown-screen` profile shares catalogue, localisation, and provider
preparation and emits exactly three crystal items. Run direct PDB plus
full-catalogue ProstT5/Foldseek in 13 deterministic batches of at most 128
queries, one large-memory batch at a time. AFDB exact remains explicit-mapping
only and ESM Atlas remains disabled. Run at most 25 first-copy hypotheses per
crystal and emit three seed-review packages.

The worker-offline boundary requires one explicit operational checkpoint. The
user approved a compute-only `unknown-discovery` run, bounded reviewed
login-side coordinate staging, and then an offline `unknown-screen` MR run.
The current application now exposes `provider_discovery`: it authenticates the
owned three-crystal crystallographic review bundle before catalogue import,
runs only local PDB/MMseqs2 and full-catalogue ProstT5/Foldseek tasks, and emits
no network, coordinate-registration, model-preparation, or Phaser task. Its
focused stub and byte-identical cached replay pass. The owned discovery package
is now implemented: it requires exact PDB and Foldseek query coverage,
provider/config/database agreement, the three reviewed crystal IDs, and a
complete content-addressed copied-file inventory. Four focused failure/
round-trip regressions and the packaged Nextflow cached replay pass. Bounded
login staging and offline consumption are now implemented locally: the
controller accepts only the owned discovery package, fixes PDB selection at
three hits per group and 25 mappings, uses only explicit AFDB accessions, emits typed disabled
ESM results, and inventories referenced coordinates. `first_copy` independently
matches both packages to the execution identity before any model/Phaser task
and schedules no provider or network process. The complete three-crystal graph
and both discovery/offline resumes are green. Exact-source CI `32926373409`
passed on `a6d8fd1` under Pixi 0.76.2. Fixed wrapper profiles and real HPC
qualification remain. The fixed `unknown-discovery` wrapper is now locally
wired: it accepts no runtime path argument, reads one mode-0600 untracked spec,
streams a deterministic path-free private archive, revalidates it inside the
exact staged source, refuses submit without it, and requests 8 CPUs, 32 GB, and
24 hours. Its controller and real-dispatcher stage/submit tests pass; the exact
job remains unsubmitted pending CI/deployment and the remaining fixed profiles.
The fixed `unknown-screen` child is now locally parent-bound: only a successful
owned discovery can trigger login staging, submit is refused without the exact
provider preparation, and the Slurm body rejects provider/search processes and
requires a fully cached offline replay. Its real-dispatcher/fake-Slurm lifecycle
passes; `unknown-single-component`, deployment, and Marmic evidence remain.

Status: the explicit Phase III application now plans complete deterministic
Foldseek batches of at most 128 exact sequence groups, invokes the existing
provider-bound adapter in one Nextflow task per batch, enforces one concurrent
large-memory search, and independently merges every typed query, hit, and raw
tool/log checksum. A synthetic 1,621-group catalogue fans out exactly 13
searches and retains byte-identical fully cached resume; missing, duplicated,
deferred, or changed batches fail closed. Direct PDB search and historical
single-batch application modes remain unchanged. Real full-catalogue provider
and fixed-HPC execution remain pending.

`unknown-stage-selected` accepts only an owned parent run, review TSV, and
confirmation SHA. Approve at most three A states per crystal.
`unknown-single-component` performs same-component placement, refinement, maps,
complete-catalogue sequence narrowing, and Coot review while retaining mixed
terminal outcomes.

Status: the explicit production first-copy workflow can now publish one
authenticated, owned schema-v2 A-seed package per proceeding crystal. The narrow
adapter independently verifies its complete execution identity, crystal-bound
hypotheses, original hypothesis checksum, content-derived legacy review/solution
identities, retained result assets, review outputs, and exact candidate counts.
Completed no-model crystals receive an honest empty target worksheet; held
crystals schedule no A review. The scheduler-owned parent run is explicit and
cannot be inferred from the preceding crystallographic review parent. Historical
review output remains unchanged when ownership is not requested.

Status: the A-seed handoff authenticates the canonical schema-v2 decision stage,
registered owned package, complete execution identity, exact `unknown-screen`
parent, and original crystal-bound hypotheses. The package now contains every
checksum-bound MR review output and per-solution scientific asset, so active
execution has no external legacy review-directory input. The resulting
`phase3_seed_stage_manifest.json` binds approval/rejection/deferral, hypotheses,
models, complete byte-identical package/stage snapshots, and both seed tables.
It does not translate decisions into `approved_mr_seeds.tsv`,
`validated_mr_seed_decisions.json`, or a schema-v1 live-M4 manifest.

Current same-component Phaser and T12 adapters explicitly consume that exact
schema-v2 seed stage and reject legacy or dual approval authority. Only approved
states schedule work; rejected or deferred checkpoints retain header-only seed
tables, and an approved state already at its expected copy count reaches
refinement without a fabricated addition. The complete-item continuation joins
placement and supported-finalist inputs only by crystal identity. One- and
three-crystal local workflows preserve cached replay, selected diffraction,
Free-R, refinement, and sequence checkpoints while changing one crystal cannot
cross-consume a sibling's review. Historical fixed and normal-workflow schema-v1
controls remain immutable on their genuinely separate route. Exact-source CI
`32899255889` passed on `b615c34`; owned-HPC qualification remains before the
finding is final evidence. The canonical `phase3_application.nf`
`reviewed_single_component` operation accepts a bounded private reviewed-
crystal route manifest plus its exact completed-screen registry, complete
execution identity, and owned parent. Each A package is resolved exclusively
from that registry; each independent stage revalidates its full registry,
package, original MR evidence, and execution identity before placement. A-seed
packages produced during the screening job may correctly predate that job's
completion; pre-completion crystallographic packages remain rejected. A real
three-crystal canonical-entry regression schedules three owned approvals, one
required additional placement, two finalist stages, two refinements, two
independent sequence-review checkpoints, two owned schema-v2 sequence packages,
and two separately owned composition packages, while retaining the deferred
crystal without scientific work. Each
real checkpoint independently verifies its exact crystal-owned refinement
directory, schema-v2 selected dataset, Free-R identity, source MTZ, preflight,
complete catalogue/source inventory, final result, and Phenix command. Its
owned package independently revalidates every retained map, coordinate, command,
catalogue row, review output, content identity, and checksum; targets are the
complete reviewed sequence-equivalence groups, not guessed exact loci, or the
one-to-three successfully refined seed/composition states. The
parent is the current `unknown-single-component` scheduler run and cannot be
replaced by the earlier screening run. Human sequence approvals remain empty.
All tasks cache on resume; revising one review reruns only its approval,
required placement, finalist stage, sequence checkpoint, and both owned
packages while unchanged refinement and sibling tasks remain cached. The fixed
local composition-decision handoff accepts only the matching single-component
run, owned crystal package, and independently confirmed operator TSV. The
fixed remote profile and real licensed execution remain pending.

A scientifically completed zero-model crystal now also receives its own
content-bound schema-v2 A-seed package and an empty target worksheet. This
exception applies only when retained legacy MR evidence independently proves
`completed_success`, zero candidates, zero inspectable solutions, and no items.
Missing, contradictory, or failed evidence still fails closed; crystallographic,
composition, and sequence checkpoints continue to require review targets.

Status: the opt-in schema-v2 file contract for crystallographic, A-seed,
composition, and sequence decisions is implemented and documented in
`docs/phase-iii-review-contract.md`. It content-binds one checkpoint to an owned
parent-run identifier and checksum-qualified review package, rejects duplicate
or conflicting targets, and enforces the three-state A/composition limits.
The local stager now verifies caller-supplied owned parent run/profile/phase,
exact package-manifest and transported-decision checksums, canonical decision
identity, permitted target membership, and review chronology before publishing
only canonical decisions plus a typed stage manifest into a new directory.
A focused local generator now emits one content-addressed, path-free package for
exactly one crystallographic, A-seed, composition, or sequence checkpoint and
crystal. It binds the exact Phase III execution identity, complete targets,
copied evidence roles/relative paths/checksums/sizes, and a checksum-qualified
complete checkpoint-specific target worksheet; it rejects source mutation,
symlinks, escape, duplicate roles/paths, incomplete coverage, and non-empty
publication targets. Existing package and registry identities remain unchanged;
composition/sequence packages and mixed registries receive explicit v2 adapter
identities and remain resolvable through the same owned-run trust boundary.
Sequence packages are now published by the actual reviewed application. A
fixed local sequence-decision handoff independently resolves one crystal's
package from its completed `unknown-single-component` run, requires the exact
pass-1 run/profile/phase and confirmed ASCII decision checksum, and retains
only explicit `approve`, `retain_alternative`, or `no_assignment` review;
neither the predecessor screen nor an unreviewed locus can substitute. The
reviewed application now publishes both composition and sequence packages per
eligible crystal, with separate owned operator handoffs. Final status
production, fixed HPC profiles, and remote staging remain pending.

The unknown-pass-1 crystallographic bridge now accepts one exact owned-run ID
and exactly three crystal-bound decision files/checksums, resolves every
package by run/crystal/checkpoint through the trusted registry, and passes only
the resolved canonical package manifest to the existing stager. It atomically
publishes a content-addressed path-free three-stage index after revalidating the
registry. The screen builder requires that index and rejects missing, duplicate,
mutated, cross-run, cross-crystal, cross-parent, or cross-execution state; it no
longer accepts an arbitrary directory of caller-staged packages.

The actual multi-crystal first-copy workflow now also consumes this reviewed
index plus its exact Phase III execution identity. An existing-adapter command
revalidates all three canonical stages, manifest-crystal membership, and frozen
MTZ checksums before any scientific branch. A synthetic real Nextflow execution
retains one held crystal separately, schedules only its two proceeding siblings,
binds each decision bundle into the corresponding child cache item, and proves
fully cached replay without fabricating approvals. Historical unreviewed control
paths remain unchanged; the fixed unknown HPC profile and real Phaser run still
require their own gates.

A fixed local stub now binds one synthetic public-fixture
`PhaseIIIExecutionIdentity`, three registry-resolved checksum-verified
single-crystal packages and their indexed crystallographic review stages, one
catalogue/provider/offline-localisation
preparation, exact MTZ/model bytes, three complete crystal items, and an exact
25-task A inventory. It fans out three review-stage preparation items, retains
one hold and one proceeding empty-no-model branch, and proves byte-identical
cached resume. Changing a typed candidate in the third crystal reruns only its
own complete crystal item; both unaffected siblings, their shared/review
preparations, and all 25 first-crystal A hypotheses remain cached with unchanged
outputs. The full three-crystal inventory is retained at the run boundary,
never inserted into an independent child cache key. The stub exposes no scientific
paths, crystal selectors, thresholds, remote profile, or live Phaser execution;
it is not an operator-data analysis or an unknown-screen qualification.

A separate tool-free local collector now consumes exactly three schema-v2
terminal assessments from one owned execution plus their checksum-declared
per-crystal command/result/evidence allow-lists. It independently re-derives
assessment IDs and statuses, refuses missing, duplicate, cross-crystal,
symlinked, unsafe, mutated, or unexpected evidence, and publishes canonical
assessment JSONL, one panel summary, per-crystal and cross-crystal checksum
manifests, and a minimal portable HTML status table. Mixed and uncertain
endpoints remain independently typed, and the report explicitly makes no
identity, composition, or validation claim beyond each assessment. Live
unknown-screen production of these terminal inputs and remote collection remain
pending.

Valid pass-1 endpoints are:

- `credible_single_component_solution`;
- `credible_partial_or_residual`;
- `candidate_shortlist_no_credible_mr_solution`;
- `no_supported_catalogue_candidate`;
- `mtz_or_symmetry_review_required`;
- `execution_failure`; and
- `insufficient_evidence`.

Historical CD6 results remain `insufficient_evidence` and are not reused as an
answer.

### PH6 - M6, packaging, and remaining hardening

After pass 1, remove target-derived map/phase columns from ordinary M6 inputs,
filter leakage before accepted-hit truncation, stage coordinates only through
bounded network tasks, remove largest-copy seed preference, verify real cache
mutations/child completeness, canonically sort every aggregation boundary, and
use run-owned Apptainer caches.

Run M6 operational first and collect/classify it before separately running the
leakage track against the unchanged protocol. Unknown samples must not tune
thresholds or contribute to M6.

Status: the local `DEV-P1-03` ordering correction is implemented. Shared
truthless discovery now uses a checksum-bound 25-hit/query/route envelope;
operational policy preserves its historical first-three effective input, while
leakage policy consumes only runner-visible amino-acid identity/coverage
evidence before the unchanged three-hit accepted-model cap. A seven-hit-per-
route regression retains safe direct and Foldseek ranks four through six,
deterministically defers each rank seven, is invariant to input-row permutation
for the scientific outputs, and emits a typed empty result when every hit is
excluded. M6 execution and acceptance remain pending the other PH6 stop gates.

Status: the `DEV-P1-02` source correction is implemented locally ahead of the
PH6 execution gate. Ordinary M6 preparation now emits only HKL, the
deterministically selected observation/sigma array(s), and one validated Free-R
array; it preserves exact sorted HKL-to-flag membership and refuses missing or
ambiguous arrays. A path-free record binds only the sanitised output and stays
outside the runner archive, while the original frozen structure-factor
checksums remain in the trusted source inventory. The explicit map-only edge
cases are unchanged. No M6 run has been launched, so operational/leakage
acceptance remains pending.

Status: the local `DEV-P1-06` advancement correction is implemented. Every
packing-eligible first-copy hypothesis now remains in a deterministic seed
advancement inventory, including alternative copy counts for the same model.
The unchanged five-seed cap is applied only after ordering by retained LLG,
TFZ, and candidate-rank evidence; copy count is not a ranking or replacement
criterion, and the immutable hypothesis ID is only the final deterministic
tie-break. Selected and cap-deferred alternatives remain explicit, input-order
permutations produce identical inventories, and the changed seed semantics use
adapter/cache identity `m6-nextflow-seeds-v2`. M6 execution and acceptance
remain pending the other PH6 stop gates.

Status: the production `DEV-P1-07` child-output boundary now snapshots every
completed task's exact process, tag, cache hash, and non-staged child-file
checksums before cached resume. Resume must reproduce the same complete task
and file inventory; deleting or changing even one cached catalogue
`source_records.jsonl` now aborts the actual production verifier despite all
26 Nextflow directory-cache hits. Both path-free inventories and trace hashes
are retained through the reviewed remote collection, bound into resume
provenance and final checksums, and independently reconciled with every Slurm
child and controller stage at the truth-side gate. The real protocol mutation
continues to rerun exactly ten dependent tasks while 16 unaffected tasks keep
their cache identities and outputs. Real M6 execution and observed mutation
qualification of the remaining cache-key components remain separate gates.

Status: the local `DEV-P1-04` coordinate boundary is implemented. A dedicated
login/controller-labelled process resolves only the bounded policy-selected
PDB hits, reuses the qualified coordinate cache, and transports checksum-bound
objects with relative source records. M6 case workers consume those local
objects without receiving the database manifest or invoking HTTPS; no-hit and
missing-model paths remain typed. A future M6 run must still qualify the real
site executor mapping and collected coordinate-stage inventory.

Status: the M6 fixed-smoke/resource verifier now recognises the resulting
26-task graph instead of rejecting the new coordinate stage as an unexpected
25th Slurm child. Exactly 25 scheduler jobs and one bounded controller stage
remain separate in retained resource evidence. Operational resume caches all
26 tasks; leakage caches exactly six truthless discovery tasks and reruns 20
track-specific tasks, including coordinate staging. The scientific collector
reconciles total tasks against both inventories without changing historical
resource records. Real M6 execution remains blocked by the earlier Phase III
control gates.

Status: reviewed M6 scientific staging, scheduling, collection, and evaluation
now support both immutable Viper and Marmic site contracts. Marmic accepts only
its frozen Phenix manifest, the exact `m6_nextflow_slurm_marmic_v1` policy,
the configured `marmic` Nextflow profile, and a run-owned Apptainer cache;
Phase III source must be explicitly reachable from `origin/dev/phase3`.
The controller refuses endpoint-site mismatch, and paired tracks cannot mix
sites or policy identities. Historical Viper/main evidence remains readable.
The local fake scheduler exercises complete Marmic staging and both reviewed
submission policies. No scientific M6 profile has been launched; real
execution remains behind the earlier Phase III control gates.

Status: the fixed M6 scientific controller now also reuses the reviewed
exact-commit source-archive fallback when the selected site's bare Git mirror
is absent or invalid. One bounded stream carries the source archive before the
independently confirmed runner archive; both remain separately size/checksum
verified, and pinned nf-helper, Phenix, execution policy, and site identity
remain bound. A fake Marmic stage succeeds with its mirror absent and all 63
runner cases present. No scientific job has been submitted.

Status: the local `DEV-P2-01` completion-order correction is implemented. The
active discovery and policy writers already canonicalised validated provider,
result, hit, accepted/rejected-model, and evidence-ranked candidate records;
seed/finalist/track assembly already used evidence order with immutable-ID
tie-breaks or fixed protocol case order. The three Nextflow `groupTuple`
boundaries now sort their unordered child bundles by hypothesis or seed ID
before forming a process input/cache identity. Case assembly rejects duplicate
refinement children and orders paired refinement/sequence evidence by seed ID,
without reordering seed ranks or sequential copy-series evidence. Reversed
provider batches produce identical validated result/hit/manifest inventories,
and reversed complete refinement children produce byte-identical case-evidence
trees; existing tests cover all seed permutations and byte-identical outputs
for reversed model-policy rows. Scientific adapter versions remain unchanged
because no ranking, status, threshold, or record meaning changed.

Status: `DEV-P2-02` is fixed locally for every remaining scientific wrapper.
M6 operational/leakage, the archived M4 copy profile, and T12 now create and
export the Apptainer cache inside their exact owned run. The already isolated
M6 smoke retains its separately verified run-owned cache. No hard-coded user
or shared account cache remains in the job wrapper; real-site execution
evidence remains pending.

Add a locked offline wheel build, isolated install, both entry points, packaged
schemas, and version parity. Remove or migrate legacy nested thread-pool
benchmark execution. Repeat the adverse review before release.

Status: `DEV-P2-03` is fixed locally. The two archival public benchmark actions
that formerly launched independent Phenix attempts through Python thread pools
now fail before reading inputs or creating outputs with an actionable DSL2/
Nextflow migration diagnostic. Their shared preparation and classification
helpers remain available to current Nextflow-owned workflows, but neither
production benchmark driver contains a thread/process-pool primitive. No
historical control profile or evidence was reinterpreted as Phase III evidence.

The current executable surface is also locally consolidated. The repository
root now contains only archival `main.nf`, current `phase3_application.nf`,
database preparation, M6, and one typed `qualification.nf` owner. Nine
superseded stage roots were removed only after all replacement operations,
unknown/incomplete operation rejection, fixed-wrapper integrations, and the
complete Nextflow stub gate passed. Exact-source CI `32910230567` passed on
`de2f4c4`; real fixed-profile qualification remains before `FCB-P2-01`
receives its final disposition.

Status: the exact Hatchling backend is now pinned in both build metadata and
the Pixi lock, and one fixed `offline-wheel-check` builds without isolation,
inspects every packaged Python/schema byte, installs into a fresh virtual
environment without dependency resolution while reusing the locked runtime,
executes both metadata-declared entry points, and checks release-version parity
across package, Pixi,
CLI, Nextflow, wheel, and installed metadata. Focused missing-schema,
missing-entry-point, and version-divergence regressions pass. The positive task
now passes completely with `pixi run --locked --offline offline-wheel-check` on
clean source `1fd2a37`: the exact Hatchling 1.32.0 backend, both entry points,
all nine packaged schemas, and package/CLI/Pixi/Nextflow version `0.2.0` were
verified without contacting a package index. `PIPE-P3-01` is fixed; final
release qualification must repeat this same gate after the version changes.

### PH7 - Unknown-dataset pass 2

Hard stop: do not stage, submit, resume, or otherwise execute the second pass
until `RG0`-`RG7` in the
[fail-closed and clean-break roadmap](phase-iii-fail-closed-clean-break-roadmap.md)
are complete. Every old and new finding requires a final `Fixed`, `Superseded`,
or `Deleted` disposition with its focused regression, exact-source acceptance,
and any required fixed-HPC evidence. The reviewed second-pass profile must
reject an absent, stale, changed, or incomplete closure record.

Status: the content-addressed closure-record verifier is implemented locally.
It authenticates the exact source commit/tree and ledger bytes, requires one
final entry for every finding plus exact-source CI/control/M6/pass-1 evidence,
and rejects local/pending wording, stale or incomplete inventories, malformed
JSON, and cross-source records. Exact-source CI `32912485774` passed on
`cd2c6a7`; fixed pass-2 profile integration and the real RG7 evidence remain
pending.

Reuse identical frozen inputs, gel/localisation evidence, thresholds,
databases, and tools. For a credible A state, launch the automatic B-F beam
within the depth-six/100-attempt envelope. If no credible A exists, expand the
first-copy search from 25 to a cumulative 200 hypotheses in bounded batches and
review newly retained A states before component expansion.

Refine or map-check at most three retained states per depth when needed for
review. Require final composition and sequence decisions. Exact sequence/locus
claims require map-supported approval; equivalence groups remain valid
endpoints. Report budget exhaustion, unresolved residual content, suspected
non-protein content, or depth-six truncation explicitly. Never tune thresholds
from these unknown outcomes.

### PH8 - Completion and v0.3.0

Each crystal must end in a checksum-reconstructible report with an honest
scientific and execution status. Uncertain, partial, provisional-depth, and
no-supported-candidate reports count as completed analyses.

Each per-crystal package must retain immutable input/tool/database provenance,
crystallographic warnings and review decisions, complete pre/post-localisation
candidate inventories, provider/model coverage, every tested and untested A or
multi-component hypothesis, raw LLG/TFZ/incremental-LLG/packing evidence,
Rwork/Rfree, maps, coordinates, sequence/locus alternatives, terminal reasons,
resource/cache/retry evidence, checksums, and a portable HTML report. The
cross-crystal report must compare task counts, cache identity, model coverage,
attempted/deferred/unsearchable counts, resources, scientific statuses, and the
unchanged-threshold guarantee.

No exact identity or complete composition may be reported from MR scores or
packing alone. An honest uncertain endpoint is completion; forcing an answer is
not.

Release validated research version `v0.3.0` only when:

- M6 operational and leakage gates pass;
- every old/new finding has a final disposition;
- 9ECN validates depth three;
- both unknown passes produce complete reports;
- depths four to six remain explicitly provisional;
- packaging/install/schema parity passes; and
- the exact release commit passes full local, CI, and fixed-HPC gates.

## Testing and HPC policy

- Add one focused regression per defect; do not run the full suite after every
  edit.
- Run complete locked checks only at integration, M6, unknown-pass, and release
  gates.
- Run one CI workflow per pushed milestone.
- Fixed wrappers expose no paths, crystal IDs, thresholds, or arbitrary
  commands.
- Pass-1 MR: 75 attempts, 4 CPUs/16 GB each, at most 25 concurrent.
- Refinement: at most nine finalists, 4 CPUs/16 GB, at most four concurrent.
- Pass-2 expansion: at most 100 additional-component attempts per crystal, 25
  per depth, beam width three, depth six.
- No-A expansion: at most 175 new first-copy attempts per crystal.
- Retain actual CPU, wall, MaxRSS, I/O, cache, and storage evidence.

## Required human inputs and checkpoints

- User-provided DeepTMHMM academic runtime image and checksum.
- Typed SDS/native-PAGE observations before unknown pass 1; missing values may
  be declared explicitly and remain neutral.
- User/supervisor decisions at crystallographic, A-seed, final-composition, and
  sequence checkpoints.
