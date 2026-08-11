# Development loop journal

This is the tracked hand-off record for bounded development loops. Read the
newest entry before starting a new loop. Before closing or handing off a
session, append an entry with discoveries, accomplishments, immutable evidence,
unresolved work, and the exact next starting point. Keep private paths,
biological inputs, credentials, licensed files, and generated results outside
Git.

## 2026-08-11 — Exact predicted model to first-copy MR boundary

### Discoveries

- Marmic compute nodes cannot reach the public AlphaFold API reliably. The
  fixed P1 profile therefore retrieves one authorised exact model on the login
  node, records seven SHA-256 hand-off checksums, and verifies them before
  offline compute-node use.
- One exact AFDB v6 coordinate for the pilot catalogue mapped at identity and
  coverage 1.0. Phenix 2.1-6048 confidence processing retained 429 of 442
  residues and produced identical processed-model bytes on macOS and Linux;
  platform-specific Phenix-manifest provenance intentionally changes the model
  identity.
- The CD6 target has one retained physically plausible copy hypothesis; higher
  tested copy counts are physically impossible for that candidate and must not
  enter the first-copy funnel even if a generic retention cap includes them.
- A real local Phenix 2.1-6048 probe against the public 8OOX positive control
  established the command and output conventions. With total composition of
  two copies and a one-copy search, the top refined solution had LLG 1622.9 and
  TFZ 49.7. Phaser can report an early packing advisory while the final packing
  table accepts the solution, so the parser must use final evidence and retain
  advisories rather than treating the first warning as a tool failure.
- `phaser.output_dir` did not relocate output in the observed command-line mode.
  The production adapter must instead execute in a hypothesis-owned working
  directory through the isolated Phenix runtime.

### Accomplishments and immutable evidence

- Commit `c901dafe585d1b68b117d7d216e5053ef4985230` passed the fixed Marmic P1
  discovery and predicted-model preparation slice, including a fully cached
  resume. The run ID and machine-specific paths remain in ignored local
  evidence, not this journal.
- Commit `95e6e4f30d536f39a69269aaff317f9d5492533d` recorded the passing M2 slice;
  GitHub Actions run `31472841538` completed successfully.
- The repository was clean before the current funnel implementation began.

### Unresolved work

- Implement the exact-predicted-model funnel with explicit feature fields,
  checksum verification, physically impossible-row exclusion, deterministic
  ordering, and profile/config hard caps.
- Implement and fixture-test the first-copy Phaser command, parser, strict
  provisional `LLG > 100` and `TFZ > 10` gate, final packing interpretation,
  and hit/no-hit/failure separation.
- Wire the smallest fixed CD6 Marmic route, run it from an immutable commit, and
  collect structured evidence before broadening coordinate sources or model
  variants.

### Next exact starting point

Read this entry, then inspect the installed Phenix wrapper's model-error
handling. Finish the Python funnel and Phaser adapter before extending the
Nextflow/HPC profile. Use the public 8OOX output only as a parser/positive-control
fixture; do not tune the CD6 scientific conclusion against it.

## 2026-08-11 — First-copy implementation and fixed P2 route

### Discoveries

- Phaser's early “top FTF did not pack” advisory is not final packing evidence;
  the parser must use the final accepted/packed table and preserve the advisory
  as a warning.
- A test profile cannot prove `-resume` behaviour while deleting its work after
  the first run. Test work now survives only within the harness's disposable
  temporary root and is removed when that root closes.
- The qualified P0 allowed root may span a broad shared site tree. Recursively
  searching it for the fixed CD6 MTZ would create avoidable NFS metadata I/O and
  could find stale duplicates. P2 now resolves the MTZ only from the frozen P0
  bundle's deterministic `manifests/` plus `inputs/` layout.
- Unpredictable shared-filesystem startup is not a scientific reason for a
  short Phaser deadline. The adapter has no default timeout; the fixed Marmic
  process and controller use the site's conservative 1,000-hour observation
  margin without implicit cancellation.
- The first real P2 attempt stopped during replayed database validation before
  molecular replacement. MMseqs2 returned hundreds of strong full-coverage
  ubiquitin hits but its bounded tie set omitted literal `1ubq_A`. Requiring a
  particular duplicated deposition in that result contradicts the earlier
  source-derived qualification: search function is established by a strongest
  sequence-equivalent hit, while fixed `1ubq_A` SEQRES and cached coordinate
  anchors are verified independently.

### Accomplishments and evidence

- Implemented the exact-predicted-model funnel with exact mapping and checksum
  validation, physical-impossibility exclusion, inspectable features,
  deterministic per-model/global caps, and one immutable record per MR job.
- Implemented the isolated first-copy Phenix adapter and parser. It records the
  resolved command and input digests, separates hit, no-hit, tool, parse,
  infrastructure, and input-contract outcomes, uses final packing evidence, and
  enforces strict `LLG > 100` and `TFZ > 10` inequalities.
- Added the typed `screen_first_copy.nf` route, process modules, frozen stubs,
  publication checks, and a verified fully cached second run.
- Added the checksum-gated fixed P2 controller route. It replays P0/P1, accepts
  no arbitrary path or scientific argument, runs only the bounded CD6
  hypothesis, validates the normalised result, requires a cached resume, and
  collects only approved small artefacts.
- The complete local gate passed: Ruff formatting/lint, strict mypy, 260 unit
  tests, 53 contract tests, 36 integration tests, schema and public-panel
  validation, documentation links, GitHub workflow linting, Nextflow syntax,
  every stub/resume route, and HPC shell syntax.
- Commit `037d257d3854084793132abd34d1161fcc3031f6` passed GitHub Actions run
  `31481766623`. Its first real P2 run produced retained failure signature
  `11bec80298639c14851a50692dd09e977deb8852f49184954026f5f80f41440e`;
  this immutable evidence establishes an upstream environment-validation
  failure, not a Phaser or CD6 scientific result.
- The bounded-MMseqs correction removes only the deposition-specific result-list
  requirement. A full smoke regression now proves that a strong
  sequence-equivalent hit is accepted only when the independent fixed 1UBQ
  mapping remains valid. The corrected complete gate passes with 259 unit, 53
  contract, and 36 integration tests plus all workflow/documentation checks.

### Unresolved work

- Commit and push the focused correction, confirm GitHub Actions, redeploy the
  checksum-verified tools, then rerun and collect the first real Marmic P2
  result.
- Review that real result before deciding whether the next smallest step is a
  parser/source correction, a broader model/provider funnel, or the remaining
  positive/no-solution and review-package work in the P2 gate.

### Next exact starting point

Read this entry, inspect the six-file correction diff, and create an immutable
commit only if it remains restricted to the observed tie-order regression and
its documentation. Then use only the reviewed wrapper for the immutable P2
retry; do not clean either remote run automatically.

## 2026-08-11 — Real P2 replay and Phaser model-format boundary

### Discoveries

- Commit `df153bebc0d1f02f6caaa9b8653fb8872aefbc65` and GitHub Actions run
  `31482902767` passed. Its immutable P2 retry successfully replayed database
  validation, P0, and P1, produced one physically possible CD6 hypothesis, and
  cached both P2 processes on resume.
- The resulting normalised MR record was `failed_tool_execution`, not a
  scientific no-hit: Phaser 2.8.4 stopped before search with `INPUT: No
  scattering in coordinate file`. The outer wrapper's former success therefore
  established route reproducibility only and must not count as P2 acceptance.
- The exact public AFDB source reproduced the remote processed mmCIF checksum.
  The file contains 429 mapped residues and atoms, but the Phenix-written atom
  site has unknown entity identifiers and the installed Phaser ensemble reader
  derives no scatterers from it.
- Asking the same verified `phenix.process_predicted_model` command for PDB
  preserves the retained residue ranges and produces a model Phaser reads. A
  local real 8OOX positive-control run reached one accepted packed solution with
  final LLG 1149.2 and TFZ 46.0. This qualifies the software-format boundary,
  not the blind CD6 scientific result.

### Accomplishments and evidence

- Predicted-model preparation now publishes a content-addressed PDB for the
  bounded single-chain prototype variant and records `pdb` in its processing
  parameters. Source coordinate archival remains mmCIF; broader chain/entity
  support remains deferred to an explicit conversion policy.
- Model-preparation, funnel, Phaser, Nextflow-stub, and repository fixtures now
  exercise the PDB boundary and its checksum.
- The fixed P2 job now preserves a schema-valid result and logs but returns
  `test_failure` when its execution status is tool, parser, or infrastructure
  failure. Only `completed_hit` and `completed_no_hit` qualify the outer route.
- Focused model/Phaser/funnel/repository tests passed. The P2 fake lifecycle
  passes for a completed no-hit and a new regression proves that a
  `failed_tool_execution` result is rejected while its evidence remains.
- The complete locked gate passed after the correction: Ruff format/lint,
  strict mypy, 259 unit tests, 53 contract tests, 37 integration tests, schema
  and public-panel validation, documentation links, GitHub workflow linting,
  Nextflow syntax and every stub/resume route, and HPC shell syntax.

### Unresolved work

- Inspect the focused diff and create/push an immutable correction commit.
- Rebuild and deploy the checksum-verified controller scripts, rerun the fixed
  CD6 P2 route, and collect the normalised result. Do not clean any remote run.
- If Phaser completes, interpret hit versus no-hit without tuning the strict
  `LLG > 100` and `TFZ > 10` gate. If another tool failure occurs, use its exact
  retained diagnostic as the next boundary.

### Next exact starting point

Read this entry, inspect the model-format and P2 status-gate diff, then create
the immutable correction commit. Do not broaden the model funnel or polish
unrelated tests before the real CD6 retry.

## 2026-08-11 — Phaser-readable PDB retry and no-solution parser boundary

### Discoveries

- The corrected model-format boundary and outer status gate passed the complete
  locked repository check and GitHub Actions. The remaining uncertainty is now
  the real molecular-replacement search, not repository validation or the
  earlier mmCIF reader failure.
- The immutable Marmic replay passed database revalidation, P0, P1 discovery,
  exact-model hand-off verification, PDB confidence processing, qualification,
  and cached P1 resume before submitting the one physically possible
  first-copy hypothesis to Phaser.
- The real Phaser process completed normally after about one hour of CPU time.
  Seventy-six translations entered final packing, zero were accepted, no
  solution files were written, the top translation TFZ was 5.11, and Phaser
  emitted `Sorry - No solution` with a successful exit.
- The adapter misclassified this valid scientific no-hit as `failed_parse`
  because its fixture used a different explicit zero-solution phrase. The raw
  final packing table and terminal no-solution marker provide sufficient,
  internally consistent zero-solution evidence; a successful exit alone still
  does not.
- The versioned Phaser source confirms that `Sorry - No solution` is emitted
  when no first component was found. It also distinguishes `No solution with
  all components` for partial solutions, so the zero-solution parser uses an
  exact terminal-line match and does not accept that longer phrase.
- The immutable parser-correction replay reproduced the same terminal Phaser
  evidence and now normalises it as `completed_no_hit`: zero accepted/packed
  solutions, no placed copy, no solution files, and no parser warnings. This
  excludes only the tested exact-model first-copy hypothesis; it does not
  exclude other catalogue sequences or coordinate/model variants.

### Accomplishments and immutable evidence

- Commit `b93bf32e6ab5871c23e8579b91fb4d15dc3339e3` contains the narrow PDB
  boundary and failure-status correction. GitHub Actions run `31486180388`
  completed successfully.
- The installed checksum-gated local controller has SHA-256
  `c874a6bd90e6d6f7ce002099083cdf55d9e121af009af30a6a223d96d29596a7`.
  The deployed fixed remote job has SHA-256
  `5705cd70a657a40e8ff768b95d055f510d9d3742eb6b4b1c76412ab9281b982d`;
  the dispatcher remains the reviewed immutable version.
- Marmic P2 readiness passed, and the immutable retry is using the exact Git
  commit and recorded `nf-helper` submodule revision.
- The collected run was correctly rejected by the outer status gate as
  `test_failure`; it also completed a fully cached P2 resume and retained
  failure signature
  `bcccb018e5dc896e877d3d875e264bf61e7ed67e495fcd367ffd5e9a79e80958`.
- A reduced real-format no-solution fixture and focused parser regression now
  pass locally. Terminal no-solution wording supersedes an earlier intermediate
  solution count only when it appears later in the log.
- The complete locked gate passes with 261 unit tests, 53 contract tests, 37
  integration tests, strict typing, formatting/lint, schemas, public controls,
  documentation, workflow lint, Nextflow syntax/stubs, cached resumes, and HPC
  shell syntax.
- Commit `4e64ce5bc10c518276a86f2c0870e4c18899f86d` contains the focused
  no-solution parser correction. GitHub Actions run `31491762880` completed
  successfully.
- The rebuilt and installed controller has SHA-256
  `c187a1cbffbd0a333575aa39474030c0bbbca8fd0bd6ae08628b556aeebaacd5`.
  The reviewed dispatcher and fixed remote job were redeployed for the exact
  correction commit with unchanged script checksums, and P2 readiness passed.
- The correction replay passed database revalidation, cached P0, P1 hand-off
  checks, cached P1 discovery, cached PDB model preparation, and P1
  qualification before submitting the same one-hypothesis Phaser process. The
  scheduler still reported `RUNNING` when active polling was paused.
- Long real-data profiles now use a recorded 30-minute reactivation cadence:
  stop only the local observer, leave the scheduled job untouched, check
  structured status on reactivation, collect immediately after a terminal
  state, and never infer failure or cancel from silence.
- The same-task `Monitor Marmic P2 replay` heartbeat handled the terminal run
  and is now paused; future long real-data runs should create or reactivate a
  run-specific 30-minute heartbeat.
- The correction replay completed with scheduler state `COMPLETED`, exit zero,
  outer failure class `success`, and no failure signature. Both P2 processes
  were cached on resume. The collected normalised result, native Phaser log,
  resume record, command record, and outer job record have SHA-256 values
  `c2f9142b6a5b61a98b6b546d5b4494d9f30d2dce09533359455c4cb38d5116cf`,
  `70051d054ffc76143735a6281adc8c87bb925ef83495bf3b49aed1e70fec8bca`,
  `98e287e8a082e57a152dd19c9f42a5f6f4fe08809618eaed8afab11ee2253261`,
  `7f11bd71af4ee359e363cbb41f88e5dfad12a81555b5f5a05d79bd101e049854`,
  and
  `6ae78c9dc9547436b6a2dd5cfc98fd903f1e1881f780adb7e66dab725097e8f2`,
  respectively.

### Unresolved work

- The fixed one-hypothesis P2 route is qualified, but full P2 is not: qualify
  the scheduled positive/incorrect-model controls, enforce the per-crystal
  smoke cap, and produce the bounded review package.
- Move real-data breadth forward by registering a small, provenance-complete
  set of direct-PDB coordinates and diversity-aware candidate/model variants,
  then run no more than 25 first-copy hypotheses for the crystal. Do not tune
  the strict LLG/TFZ gate against the present no-hit.

### Next exact starting point

Read this terminal evidence, then inspect the direct-PDB hit-to-coordinate and
review-package boundaries. Implement the smallest provenance-complete,
hard-capped real-candidate expansion before adding same-component copies; do
not clean any retained remote run.

## 2026-08-11 — Direct-PDB model path and hard-capped multi-source funnel

### Discoveries

- A direct-PDB search hit needs a separate immutable hit-to-coordinate mapping.
  The searched SEQRES snapshot, downloaded mmCIF entry/entity/author chain,
  candidate alignment, source/candidate sequence digests, and cache object must
  all agree before the coordinate can become MR input.
- The smallest defensible experimental-model expansion is one cleaned source
  chain. Removing non-polymer atoms and hydrogens while retaining alternate
  conformations is deterministic; sequence adaptation, side-chain pruning,
  domains, ensembles, and additional conformers would multiply unqualified
  hypotheses and remain deferred.
- The original first-copy Phaser adapter was exact-predicted-only. It rejected
  homologous PDB models and hard-coded `phaser.model_identity=100`; merely
  wiring a diverse funnel to that adapter would therefore have failed or
  misrepresented the model. Adapter v2 now requires matching mapping IDs and
  candidate-to-source identity in hypothesis and processed-model provenance,
  uses 100% only for exact predicted models, and passes the verified homologue
  identity for cleaned PDB models.
- Marmic compute nodes have already rejected outbound HTTPS. The real route
  must therefore register/download selected PDB coordinates during a fixed,
  path-closed login-node staging operation, then let the Slurm phase verify and
  consume those shared-cache objects offline. `process_network` alone is not a
  valid Marmic download strategy.
- Diversity must be reserved before quality-only ordering. The implemented
  selector round-robins over sequence-group, provider, and model-variant
  buckets, then enforces the smoke ceiling of 25 first-copy jobs per crystal.
  This is an execution-safety bound, not evidence that 25 is scientifically
  sufficient.

### Accomplishments and evidence

- Direct-PDB registration now selects sequence-group-first bounded hits,
  reuses or downloads official RCSB mmCIF objects through the verified
  content-addressed cache, validates the searched SEQRES snapshot against the
  live coordinate entity, and publishes typed coordinate sources, mappings,
  and an integrity manifest.
- Experimental-model preparation now produces one content-addressed,
  Phaser-readable single-chain PDB per mapping with exact observed sequence,
  mass, atom/residue counts, source completeness, mapping identity, quality
  flags, structured logging, and bounded progress.
- The multi-source funnel verifies paired predicted/experimental preparation
  bundles, mapping joins, checksums, preflights, and physical copy hypotheses;
  it preserves independent priority features, emits one record per selected
  job, and publishes a self-contained aggregate model registry for Phaser.
- Typed parser-v2 entry points now cover coordinate registration, experimental
  model preparation, and multi-source first-copy fan-out. Every new entry point
  passes stub publication and cached resume.
- The full locked gate passes: Ruff format/lint, strict mypy, 269 unit tests,
  54 contract tests, 37 integration tests, Draft 2020-12 schemas, the ten-entry
  public panel, documentation links, GitHub workflow linting, Nextflow syntax,
  all stub/resume routes, and HPC shell syntax. No real Marmic direct-PDB model
  or diverse Phaser job was run in this loop.

### Unresolved work

- Create and push the focused immutable commit, then require GitHub Actions to
  pass before Marmic fetches it.
- Add a checksum-gated, path-closed real operation that performs PDB coordinate
  registration on the Marmic login node and schedules only offline model
  preparation, capped funnel construction, Phaser fan-out, and cached resume.
- Execute no more than 25 real CD6 first-copy hypotheses, collect every
  normalised result/log/command and the funnel manifest, and retain the remote
  run. Do not interpret external PDB identities as catalogue identities.
- Qualify the scheduled known-positive and deliberate incorrect-model controls,
  then implement the top-10/25 review package and approval validation. Do not
  start same-component additional-copy placement yet.

### Next exact starting point

Read this entry and verify the focused commit/CI. Then inspect the existing
fixed P2 stage/submit implementation and add the smallest separate
`p2-diverse` login-stage plus offline Slurm operation. Reuse immutable P1,
catalogue, MTZ, Phenix, and database evidence; accept no caller-controlled
remote path or shell fragment, do not download from a compute node, and do not
clean retained runs.

## 2026-08-11 — Fixed P2-diverse login-stage and offline Slurm lifecycle

### Discoveries

- Registering 25 direct-PDB mappings alongside the exact predicted model can
  create 26 candidates under the pilot configuration. The fixed real-feedback
  route therefore needs an explicit execution cap independent of the broader
  profile limit, and the selector must reserve exact mappings before filling
  the remaining diverse slots.
- A network-free Slurm hand-off can be checked without trusting staging
  success alone: rehash every login-stage output and require the normalised PDB
  search records to match the independently scheduled P1 search exactly.
- Result cardinality alone is insufficient for fan-out evidence. Each result
  directory must match its normalised hypothesis ID, its JSON and JSONL status
  must agree, and only completed scientific hit/no-hit states may enter the
  aggregate review package.

### Accomplishments and evidence

- The separate closed `p2-diverse` profile now supports readiness, immutable
  staging, submission, structured status/logs, bounded collection,
  owner-bound cancellation, long-margin waiting, and normalised failure
  signatures without accepting a remote path or shell fragment.
- Login-node staging runs the fixed two-thread PDB sequence search, registers
  at most three hits per group and 25 mappings overall through the shared
  coordinate cache, validates cardinality and ownership, and atomically binds
  a checksum-list digest into the run manifest.
- The offline job replays P0/P1, verifies the staging hand-off, prepares one
  cleaned experimental model per mapping, reserves exact predicted evidence,
  enforces at most 25 Phaser jobs, validates every scientific result, and
  requires both model-preparation and first-copy resumes to be fully cached.
- Full native outputs remain on the retained remote run. Collection is limited
  to mappings/manifests, hypotheses, normalised results and commands, 200-line
  log tails, traces, summaries, and a SHA-256 inventory.
- The complete locked repository gate passes from base commit
  `b0b2ad35d606b6c64f119ec99c731b7992254f80`: 274 unit tests, 54 contract
  tests, 39 integration tests, strict typing and formatting/lint, schemas, the
  ten-entry public panel, documentation/action lint, Nextflow syntax and all
  stub/resume routes, plus both HPC shell parsers. The network download tests
  were rerun outside the restricted sandbox so their loopback server could
  bind; no public biological data or credentials were transmitted.
- Focused implementation commit `8372f1c530a9bd9a2f311a60376cf4ec7ddbd382`
  contains the closed profile, execution cap, remote lifecycle, tests, and
  operational documentation. The rebuilt and installed local controller has
  matching SHA-256
  `6e935a8f47ca44a2cf7dae68288e5e6f0ab517a9ae16c13fd25cfd70ecb58d2c`.

### Unresolved work

- Push the focused implementation commit, require GitHub Actions to pass, and
  deploy the checksum-verified dispatcher/job pair before Marmic can fetch this
  profile. The local controller is already installed from that commit.
- Run the real `p2-diverse` stage/submit sequence, retain the remote run,
  inspect all normalised CD6 results against the strict `LLG > 100` and
  `TFZ > 10` gate, and record resource/cache behaviour. The fake lifecycle is
  software evidence, not real-candidate scientific qualification.
- Qualify the known-positive and deliberate incorrect-model scheduled
  controls, then implement approval-file validation and the final top-10/25
  review checkpoint. Same-component additional-copy placement remains
  deferred.

### Next exact starting point

Push implementation commit `8372f1c530a9bd9a2f311a60376cf4ec7ddbd382`
and require GitHub Actions to pass. Then deploy the reviewed remote tools, run
`readiness p2-diverse`, and stage the same pushed revision. Do not submit until
the login-node search/registration checksum record is present; after
submission, use structured status with the recorded 30-minute monitoring
cadence and never infer failure from silence or clean the retained run.

## 2026-08-11 — Added the file-based MR seed review checkpoint

### Discoveries

- The retained handoff requires MR review decisions to target content-derived
  `sol_...` solution IDs, not mutable row numbers or an external PDB identity.
  The solution identity therefore has to bind the current hypothesis, result,
  funnel, command, raw log, and result-asset checksums before approval.
- A schema-valid approval template must not imply an approval. A header-only
  review TSV satisfies the existing contract while requiring the reviewer to
  add every decision explicitly.
- A preliminary strict score-gate pass is not a complete seed decision. The
  review row must retain packing, placed-copy agreement, warnings, Matthews/SDS
  context, and raw metrics independently, and an approval outside automatic
  eligibility must preserve a written override reason.
- The development cycle is now explicit in the roadmap: write code, run focused
  Pixi tests and the full locked gate, commit, push, require GitHub Actions,
  deploy checksum-verified control tools when changed, run the fixed Marmic
  profile, collect evidence, and record the next journal handoff.

### Accomplishments and immutable evidence

- Implementation commit `f44fe6be3f5afa6b722d3aac640e6f9022afbfdf` adds
  `review build-mr-seed` and
  `review validate-mr-seeds`, deterministic top-10/top-25 sequence-group views,
  checksum-bound `sol_...`/`reviewpkg_...`/`rev_...` identities, a
  schema-valid empty approval template, and loud stale/edited/unsafe-input
  failures.
- The fixed `p2-diverse` job now generates the MR checkpoint after all bounded
  first-copy results, binds its package ID and manifest checksum into the run
  summary, and exposes the approved small review files through bounded
  collection. It still creates no automatic decision and starts no
  additional-copy search.
- Focused tests pass for credible hit packaging, no-hit override semantics,
  stale IDs, edited review files, path traversal, CLI wiring, and the complete
  fake Git/Slurm/Nextflow P2-diverse lifecycle.
- The final locked repository gate passes: 279 unit tests, 54 contract tests,
  39 integration tests, strict formatting/lint/type checking, schemas, the
  ten-entry public panel, documentation and GitHub workflow lint, Nextflow
  syntax/stub/resume, and both HPC shell parsers. Loopback-only network tests
  ran outside the restricted sandbox; no biological data or credentials were
  transmitted.
- The rebuilt local controller artefact has SHA-256
  `d24afacb12b8d395fbd59ae49bf167d56bbff0bc5bf2e115e620338773d9f679`.

### Unresolved work

- Push the implementation and journal commits, require GitHub Actions to pass,
  install the rebuilt controller, and deploy the matching reviewed dispatcher
  and job script before Marmic staging.
- Run the real fixed `p2-diverse` profile, retain the remote run, collect the MR
  checkpoint, and inspect the at-most-25 CD6 results against the strict
  `LLG > 100` and `TFZ > 10` gate plus independent packing/copy evidence.
- Qualify the scheduled known-positive and deliberate incorrect-model controls.
  Only then may a human-completed MR approval file be validated for the next
  milestone. Same-component additional-copy placement remains deferred until
  this evidence is reviewed.

### Next exact starting point

Commit this journal handoff and push through
`f44fe6be3f5afa6b722d3aac640e6f9022afbfdf`, then monitor GitHub
Actions to success. Install the controller with the recorded SHA-256, deploy
the two checksum-verified remote tools from the same pushed revision, run
`readiness p2-diverse`, and stage that revision. Verify the login-stage checksum
record before submit; monitor at the recorded 30-minute cadence, never infer
failure from silence, and do not clean the retained run.

## 2026-08-11 — Repaired Linux Gemmi typing after CI feedback

### Discoveries

- GitHub Actions run `31510865883` reached the locked foundation gate but
  failed only at strict mypy. Linux's typed Gemmi build exposed twelve type
  errors that the macOS build treated as dynamic: a reused variable changed
  from an mmCIF entity key to a parsed entity record, residue sequence numbers
  were typed as optional, and `gemmi.__version__` was absent from the stubs.
- The failure was platform typing feedback, not a Phaser, coordinate, model,
  parser, or scientific-result difference. The repair must still validate
  absent residue numbers loudly instead of adding an unchecked cast.

### Accomplishments and immutable evidence

- Focused commit `cb66aae193e82fc6166bafaff0ef9cd9f4a4b21c` gives the
  mmCIF entity key and parsed entity distinct variables, validates every Gemmi
  residue sequence number before range arithmetic, and obtains the runtime
  version through an explicit non-empty string check.
- The coordinate-registration and experimental-model unit tests pass. The full
  locked local gate again passes with 279 unit, 54 contract, and 39 integration
  tests plus every formatting, type, schema, documentation, workflow,
  Nextflow, and HPC shell check. No scientific policy or output contract
  changed.

### Unresolved work

- Push the focused CI repair and this journal update, then require a new Ubuntu
  GitHub Actions run to pass. The Linux-specific type repair is not qualified
  until that remote gate succeeds.
- After CI passes, install and deploy the review-package controller/tools from
  the new immutable revision before real P2-diverse staging.

### Next exact starting point

Commit this journal entry, push through
`cb66aae193e82fc6166bafaff0ef9cd9f4a4b21c`, and monitor the exact GitHub
Actions run. If it passes, rebuild/install the local controller, deploy the
matching dispatcher and job script, run `readiness p2-diverse`, and stage the
same pushed revision. If it fails, inspect only the failing log before making
another focused change.

## 2026-08-11 — Fixed the real P2-diverse login-stage tool environment

### Discoveries

- Ubuntu GitHub Actions run `31511471600` passed for revision
  `586caa42cf01cb108e62f5645feb46ae9575f0b3`; the Linux Gemmi typing repair is
  therefore qualified.
- The CI-qualified controller was installed with SHA-256
  `68bf2c82818da78396c6413ebe7d12a292746006c13d334abbc1813c97b8e6bf`,
  the remote tools were deployed with recorded checksums, and
  `readiness p2-diverse` returned `ready=true`.
- Retained run
  `gtd-p2-diverse-20260811T162025Z-586caa42cf01-24575cdc` failed during login
  staging before any Slurm submission. The collected structured log shows that
  Pixi installed the locked HPC environment, but the absolute Python CLI
  inherited a shell `PATH` that did not contain the same environment's
  `mmseqs`; its fixed version probe failed with executable-not-found.
- This is a dispatcher environment bug, not evidence of an invalid database,
  PDB search, coordinate cache, NFS failure, or scientific no-hit. The retained
  failed run must not be cleaned or reinterpreted as a candidate result.

### Accomplishments and immutable evidence

- Focused commit `48507c4ea825bf9c1ac336e0d31192c1f9ee354c` gives only the
  fixed login-stage catalogue/provider/search operations a closed path made of
  the per-run locked Pixi `bin` plus system `/usr/bin:/bin`. It does not source
  an interactive shell or expose caller-controlled path entries.
- The fake remote lifecycle now requires `mmseqs` to be discoverable from the
  staged command environment, so the observed real failure regresses without
  this fix.
- Both focused P2-diverse fake lifecycle tests pass. The full locked local gate
  again passes with 279 unit, 54 contract, and 39 integration tests and all
  remaining repository checks.

### Unresolved work

- Push the focused login-stage repair and this journal entry, require GitHub
  Actions to pass, and deploy the new dispatcher checksum before retrying.
- Stage a new immutable P2-diverse run. Do not reuse or clean the failed staging
  run, do not submit until the new login-stage checksum record exists, and
  retain both attempts as separate evidence.

### Next exact starting point

Commit this journal entry, push through
`48507c4ea825bf9c1ac336e0d31192c1f9ee354c`, and monitor the exact GitHub
Actions run. After success, deploy the updated remote tools, rerun readiness,
and stage a new P2-diverse attempt for the same commit. Inspect the staging JSON
for a completed checksum-bound handoff before submitting to Slurm.

## 2026-08-11 — Submitted the checksum-bound real P2-diverse run

### Discoveries

- Ubuntu GitHub Actions run `31512732384` passed in 3 minutes 33 seconds for
  pushed revision `247de6b71678b4faf416a29b8eceaa6141c8fcc4`; the login-stage
  `PATH` repair is therefore qualified by both the locked local gate and Linux
  CI.
- The matching remote dispatcher was deployed with SHA-256
  `c0b83fd937225af15d3dfd2521f6369fc831fd2e374ef4b46f1ada4398410f45`;
  the fixed job script retained SHA-256
  `ffdcb323878662070f191259313229460802c3f9c9f89a340b8d627f272d6b9f`.
  `readiness p2-diverse` returned `ready=true`.
- Fresh run
  `gtd-p2-diverse-20260811T163440Z-247de6b71678-cc37d614` completed the
  fixed login stage. Its bounded collection contains the PDB search and
  coordinate-registration manifests plus
  `state/p2-diverse-login-stage.sha256`, which binds all six generated search
  and registration artefacts. This is the required completed staging evidence;
  it is distinct from the retained pre-Slurm failure
  `gtd-p2-diverse-20260811T162025Z-586caa42cf01-24575cdc`.

### Accomplishments and immutable evidence

- The staged run records exact repository commit
  `247de6b71678b4faf416a29b8eceaa6141c8fcc4`, nf-helper submodule commit
  `ed7b71caccbb8244e6d1f3ff42eaa8680728e43a`, Pixi `0.74.0`, and the
  `p2-diverse` profile.
- Submission created Slurm job `625831`. The first structured status after
  submission reported phase `submitted`, scheduler state `RUNNING`,
  `terminal=false`, and no failure class. Silence or elapsed time must not be
  reinterpreted as failure.
- The approved 30-minute heartbeat now targets this exact run and permits only
  the installed wrapper's bounded status/log/collect operations. It explicitly
  forbids raw SSH, cancellation, cleanup, runtime timeouts, and failure
  inference from silence.

### Unresolved work

- Let job `625831` run without interference. At each 30-minute cycle, read this
  journal first and issue one wrapper status command. Do not submit another
  simultaneous P2-diverse job.
- When terminal, collect the bounded evidence and inspect the outer job result,
  normalised P2-diverse results, Phaser logs, resume records, and MR seed review
  package. Apply `LLG > 100` and `TFZ > 10` strictly while retaining packing
  and placed-copy evidence as independent fields.
- A real CD6 candidate result does not by itself authorise additional-copy
  placement. The scheduled known-positive and deliberate incorrect-model
  controls, followed by a human-completed and validated approval file, remain
  prerequisites for M4.

### Next exact starting point

At the next 30-minute heartbeat, run only
`nf-gtd-hpc-test --no-progress status --run-id gtd-p2-diverse-20260811T163440Z-247de6b71678-cc37d614`.
If non-terminal, leave it untouched. If terminal, run bounded logs and collect
as separate commands, inspect all recorded P2 and review artefacts, retain the
remote run, and complete the journal/check/commit/push/CI portion of this cycle
before choosing the next scientific control.
