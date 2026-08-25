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

## Milestone sequence

### PH0 - Rebaseline and preserve evidence

- Maintain one finding ledger for the original adverse review and all later
  findings.
- Bind each row to a regression, dependency, milestone, immutable evidence, and
  final disposition.
- Preserve v0.1/v0.2 schemas, outputs, control evidence, and readers as
  immutable historical records.
- Require every finding to finish `fixed`, `superseded`, or `deleted` before
  v0.3.0.

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

One schema-v2 `PhaseIIIExecutionIdentity` now binds every raw catalogue FAA and
annotation, crystal MTZ, database inventory, source commit/tree, nf-helper,
Pixi lock, execution policy, required Phenix executable, and adapter version
without retaining machine paths. Independent mutation tests change the identity
for each surface and refuse missing annotations, MTZs, or Phenix commands.
The composition-attempt fan-out now carries this identity into every selected
task/cache item. Observed selective reruns for independent raw/tool mutations
and consumption by the other Phase III task families remain pending.

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
command identities. Observation labels, refinement space group, refinement
low/high limits, and sequence-from-map high resolution are explicit where
qualified. Phaser space-group/resolution parameters and parent-MTZ derivation
remain deliberately pending rather than guessed.

A separate schema-v2 Free-R foundation now binds an exact label and MTZ dataset
to the diffraction selection, rejects non-finite, non-integral, constant, and
ambiguous arrays, records the complete raw-value distribution, and hashes the
sorted HKL-to-raw-flag mapping. A derived-MTZ comparison fails on missing HKLs
or changed flags and is invariant to row order. The test flag value remains
explicitly unresolved unless supplied from reviewed external provenance.
Opt-in Phase III brief refinement now requires that content-address-valid
identity from the same diffraction selection, includes the exact label and
convention state in its command identity, and refuses completion or downstream
sequence-map execution unless the refined MTZ preserves the exact raw mapping.
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
existing fixed-execution contract. Real two-control qualification and
multi-fixed command syntax remain pending.

The isolated complete-item workflow now proves three crystal items can reuse
one catalogue and one provider preparation through a byte-identical cached
resume. The composition-attempt boundary additionally binds each selected row
to its parent state, depth candidate, parent/candidate model resolutions,
diffraction selection, Free-R identity, all-model registry, and global
execution identity. Every task now also carries its exact
`ComponentExpansionExecutionInput`, preserving component-only fixed coordinates,
per-component uncertainties, candidate evidence, and parent LLG. It proves one
25-attempt budget shared across three parents, typed empty/no-model scheduling,
and byte-identical cached resume, but remains stub-only. Integration into the application graph and the
hypothesis/seed/finalist levels remain pending.

The authoritative provider plan now also drives a fixed local typed-empty graph.
One enabled local scientific no-hit, two configured-disabled routes, and one
unsupported/provider-unavailable route retain every catalogue query and finish
as one content-addressed `completed_no_model` all-model registry. Its dedicated
stub resumes byte-identically and the normal enabled route fails before provider
or network execution. Real provider no-hit qualification and integration into
the live application graph remain separate pending gates.

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

`unknown-stage-selected` accepts only an owned parent run, review TSV, and
confirmation SHA. Approve at most three A states per crystal.
`unknown-single-component` performs same-component placement, refinement, maps,
complete-catalogue sequence narrowing, and Coot review while retaining mixed
terminal outcomes.

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
exactly one crystallographic or A-seed checkpoint/crystal. It binds the exact
Phase III execution identity, complete targets, copied evidence roles/relative
paths/checksums/sizes, and a checksum-qualified complete target worksheet; it
rejects source mutation, symlinks, escape, duplicate roles/paths, incomplete
coverage, and non-empty publication targets. Composition/sequence package
generation, fixed HPC profiles, and remote staging remain pending rather than
inferred.

The unknown-pass-1 crystallographic bridge now accepts one exact owned-run ID
and exactly three crystal-bound decision files/checksums, resolves every
package by run/crystal/checkpoint through the trusted registry, and passes only
the resolved canonical package manifest to the existing stager. It atomically
publishes a content-addressed path-free three-stage index after revalidating the
registry. The screen builder requires that index and rejects missing, duplicate,
mutated, cross-run, cross-crystal, cross-parent, or cross-execution state; it no
longer accepts an arbitrary directory of caller-staged packages.

A fixed local stub now binds one synthetic public-fixture
`PhaseIIIExecutionIdentity`, three registry-resolved checksum-verified
single-crystal packages and their indexed crystallographic review stages, one
catalogue/provider/offline-localisation
preparation, exact MTZ/model bytes, three complete crystal items, and an exact
25-task A inventory. It fans out three review-stage preparation items, retains
one hold and one proceeding empty-no-model branch, and proves byte-identical
cached resume. The stub exposes no scientific
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

Status: one focused local `DEV-P1-07` probe now mutates the real protocol path
used by the full 26-task M6 stub. Exactly the policy, coordinate-stage,
active-case, first-copy, seed, additional-copy, finalist, refinement,
active-case assembly, and aggregate tasks complete again; the other 16 task tags remain cached with byte-identical
child outputs. The same probe inventories every non-staged child output, removes
one cached catalogue `source_records.jsonl`, observes a standard resume, and
derives `hold_missing_required_child` instead of accepting the unchanged
aggregate. This is local verifier evidence only. M6 collection must still carry
and validate the observed mutation/child inventory before scientific acceptance.

Status: the local `DEV-P1-04` coordinate boundary is implemented. A dedicated
login/controller-labelled process resolves only the bounded policy-selected
PDB hits, reuses the qualified coordinate cache, and transports checksum-bound
objects with relative source records. M6 case workers consume those local
objects without receiving the database manifest or invoking HTTPS; no-hit and
missing-model paths remain typed. A future M6 run must still qualify the real
site executor mapping and collected coordinate-stage inventory.

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
