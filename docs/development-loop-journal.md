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
- Journal handoff commit `2276290458b820a7c54d762251533a543617acba` is
  pushed on `main`; Ubuntu GitHub Actions run `31514837916` passed the complete
  foundation gate in 3 minutes 40 seconds.
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

## 2026-08-11 — Repaired the real P2-diverse coordinate staging collision

### Discoveries

- Retained run
  `gtd-p2-diverse-20260811T163440Z-247de6b71678-cc37d614`, Slurm job
  `625831`, ran from `2026-08-11T16:52:19Z` to `2026-08-11T17:22:10Z`
  and ended with exit code `1`, scheduler state `FAILED`, and classification
  `test_failure`. Its failure signature is
  `1036872ee349394ef99e50d6fd75e004776e2b888a85d19fcda9bde039e228d1`.
- P0, database revalidation, P1 discovery, predicted-model preparation, direct
  PDB registration, experimental-model preparation, and their resume checks
  completed before the failure. P1 qualified 1,621 catalogue queries, 15,401
  direct-PDB hits, and 14 control hits.
- The first diverse-funnel process received its predicted and PDB coordinate
  inputs under the same staged basename, `coordinate_sources.jsonl`. Both CLI
  arguments therefore resolved to the same file, and the funnel correctly
  rejected a duplicate content-addressed coordinate ID. This was a Nextflow
  staging collision, not duplicate scientific evidence in the two providers.
- Failure occurred before any Phaser task. No normalised P2 result, Phaser log,
  first-copy resume record, P2 summary, or MR seed review package exists, so
  there is no `LLG`/`TFZ`, packing, or placed-copy result to interpret.

### Accomplishments and immutable evidence

- The diverse-funnel module now stages the predicted and PDB coordinate-source
  contracts explicitly as `predicted_coordinate_sources.jsonl` and
  `pdb_coordinate_sources.jsonl`. Both distinct staged paths remain separate
  CLI inputs; scientific ranking and duplicate-ID validation are unchanged.
- A focused repository contract test protects the two `stageAs` declarations
  and both command arguments. The observed collision will regress if either
  input is allowed to reuse the other's basename.
- Focused acceptance passes: all 55 contract tests, Nextflow parser-v2 syntax,
  and the complete Nextflow stub/resume suite. The final locked repository gate
  also passes formatting, Ruff lint, strict mypy, 279 unit tests, 55 contract
  tests, 39 integration tests, schemas, the ten-entry public panel,
  documentation and workflow lint, Nextflow syntax/stubs/resume, and both HPC
  shell parsers.
- The failed remote run and its bounded collected evidence remain retained.
  No remote cleanup or source mutation occurred.

### Unresolved work

- Commit and push the focused staging repair, require Ubuntu GitHub Actions to
  pass, and stage a fresh immutable `p2-diverse` run from that exact revision.
  Do not reuse or clean job `625831`.
- Submit only after the new login-stage checksum record exists. Monitor at the
  30-minute cadence without a runtime timeout or failure inference from
  silence.
- When the replay reaches Phaser, inspect at most 25 normalised CD6 results
  against strict `LLG > 100` and `TFZ > 10`, while keeping packing and
  placed-copy evidence independent. The known-positive and deliberate
  incorrect-model controls and human approval remain prerequisites for M4.

### Next exact starting point

Commit the module, regression test, and this journal entry as one focused
repair; push `main` and monitor the exact GitHub Actions run. After CI passes,
run `readiness p2-diverse`, stage that immutable revision, collect and verify
its login-stage checksum, submit one new Slurm job, and retarget the 30-minute
heartbeat to the new run. Retain the current failed run unchanged.

## 2026-08-11 — Submitted the coordinate-staging replay

### Discoveries

- Focused repair commit `4f1cc6cb1ec8dd1d6c22863f5192f7c6a754249e`
  passed Ubuntu GitHub Actions run `31524663666` in 3 minutes 2 seconds.
- Fixed-profile readiness remained `ready=true` with Pixi `0.74.0` and the
  same checksum-bound P0 input configuration. No dispatcher or job-script
  change was required for the Nextflow-module-only repair.
- Fresh replay
  `gtd-p2-diverse-20260811T185217Z-4f1cc6cb1ec8-880f5758` completed its
  login stage from the exact repair commit and nf-helper revision
  `ed7b71caccbb8244e6d1f3ff42eaa8680728e43a`.

### Accomplishments and immutable evidence

- The replay's collected `p2-diverse-login-stage.sha256` record binds all six
  direct-PDB search and coordinate-registration artefacts before submission.
- Submission created Slurm job `625842`. Its first structured status reported
  scheduler state `RUNNING`, `terminal=false`, no exit code, and no failure
  class.
- The 30-minute heartbeat now targets only the replay run. The earlier failed
  job `625831` and its evidence remain retained and untouched.

### Unresolved work

- Let job `625842` run without interference. Check it only at the recorded
  30-minute cadence through the installed wrapper; do not infer failure from
  an SSH outage, silence, or elapsed time.
- When terminal, inspect and collect the complete bounded P2 evidence. If the
  staging fix reaches Phaser, review all normalised hypotheses against strict
  `LLG > 100` and `TFZ > 10`, with packing and placed-copy evidence preserved
  independently.
- Qualification of a scheduled known-positive control, a deliberate
  incorrect-model control, and a human-reviewed approval file remain required
  before same-component additional-copy placement.

### Next exact starting point

At the next heartbeat, run only
`nf-gtd-hpc-test --no-progress status --run-id gtd-p2-diverse-20260811T185217Z-4f1cc6cb1ec8-880f5758`.
If non-terminal, leave the job untouched. If terminal, run bounded logs and
collect as separate operations, inspect every available P2 result/review/resume
record, retain the remote run, and complete the journal/check/commit/push/CI
cycle before selecting the next control or repair.

## 2026-08-11 — Raised useful Marmic Phaser parallelism to the site cap

### Discoveries

- The small outer P2-diverse Slurm allocation is a Nextflow driver; scientific
  work is submitted as child Slurm tasks. Increasing only that driver would
  reserve idle CPU and memory without accelerating Phaser.
- Each `process_mr` task forwards its resolved `task.cpus` value to
  `phaser.keywords.general.jobs`. The current diverse funnel schedules at most
  25 independent hypotheses, while the Marmic site profile declares a 100-CPU
  limit and a queue size of 30.
- Four CPUs per MR task can therefore provide up to 100 useful Phaser workers
  when all 25 hypotheses run concurrently. No out-of-memory evidence supports
  increasing the existing 8 GB per-hypothesis request.

### Accomplishments and immutable evidence

- The Marmic `process_mr` override now requests four CPUs and 8 GB per
  hypothesis with the existing conservative scheduler margin. The 25-job cap
  prevents the aggregate request from exceeding the declared 100-CPU site
  capacity.
- Contract coverage binds the four-CPU override, the unchanged memory request,
  the documented fanout rationale, and propagation of `task.cpus` to the
  Phaser adapter.
- Documentation distinguishes the outer workflow driver from the child Phaser
  allocations and explains why memory was not increased without evidence.
- The full locked repository gate passes: formatting, Ruff, strict mypy, 279
  unit tests, 55 contract tests, 39 integration tests, schemas, public-panel,
  documentation and workflow lint, Nextflow syntax/stubs/resume, and both HPC
  shell parsers.
- Resource-allocation commit `d9085e47206287de3c497ffcaccc89d876814c02`
  is pushed on `main`; Ubuntu GitHub Actions run `31529529076` passed the full
  foundation gate in 3 minutes 41 seconds.

### Unresolved work

- The running replay job `625842` remains bound to earlier commit
  `4f1cc6cb1ec8dd1d6c22863f5192f7c6a754249e` and must not be restarted or
  reinterpreted as using four CPUs per Phaser task.
- Use the new allocation only for subsequent scheduled controls or a replay
  required by terminal evidence. Inspect Slurm/Nextflow traces before any
  further CPU or memory increase.

### Next exact starting point

Continue to monitor job `625842` at the existing 30-minute cadence. When it
becomes terminal, collect and interpret its evidence under the resources
recorded by its immutable commit, then apply the qualified four-CPU allocation
to the next scientifically required job.

## 2026-08-12 — Real P2-diverse panel completed as a valid no-hit

### Discoveries

- Retained run
  `gtd-p2-diverse-20260811T185217Z-4f1cc6cb1ec8-880f5758`, Slurm job
  `625842`, ran from `2026-08-11T18:55:50Z` to
  `2026-08-11T21:40:41Z`. The outer job ended with exit code `1`, scheduler
  state `FAILED`, classification `test_failure`, and failure signature
  `fd67cad70d838ab30cc7a0b97804a3b80916d6354b144cef66c1b8e740c50375`.
- P0, P1, predicted- and experimental-model preparation, diverse funnel, and
  all 25 first-copy Phaser hypotheses completed before the review error. Every
  normalised result is `completed_no_hit`; there are zero stored or recomputed
  strict `LLG > 100` and `TFZ > 10` passers.
- Eleven results independently reported numeric scores, a solution coordinate,
  a packed top solution, and one placed copy. The best LLG was 27.383 with TFZ
  5.1; the best TFZ was 5.5 with LLG 19.726. These values are far below the
  strict gate, so packing and placed-copy evidence do not establish a credible
  molecular-replacement hit.
- The first-copy resume trace records all 26 processes as cached: one funnel
  and 25 Phaser processes. The model-preparation resume record independently
  reports one of one process cached.
- Review packaging rejected one legitimate no-solution result whose optional
  `score_gate_passed` field was absent. Its LLG and TFZ are null, packing counts
  are zero, `top_solution_packed` is false, and placed-copy count is zero. The
  review implementation incorrectly treated absence as a contradiction even
  though recomputation correctly yields false. Consequently the run has no
  review manifest, TSV/HTML package, final P2-diverse summary, or generated
  first-copy resume-check JSON, despite the complete underlying traces.

### Accomplishments and immutable evidence

- Collected bounded logs, structured state, all normalised P2 results, funnel
  records, first and resume traces, model resume evidence, and bounded Phaser
  tails through the installed wrapper. The remote run remains retained and
  unchanged.
- Review now treats an absent stored gate as the recomputed strict result. A
  present value must still be Boolean and exactly equal to the recomputation,
  so explicit contradictory evidence continues to fail loudly.
- Regression tests cover both the real no-solution shape without a stored gate
  and an explicit stored/recomputed disagreement. The focused review suite
  passes all seven tests.
- The complete locked repository gate passes formatting, Ruff lint, strict
  mypy, 281 unit tests, 55 contract tests, 39 integration tests, schemas, the
  public panel, documentation and workflow lint, Nextflow syntax/stubs/resume,
  and both HPC shell parsers.

### Unresolved work

- Commit and push the focused review-contract repair, require Ubuntu GitHub
  Actions to pass, and stage a fresh immutable P2-diverse replay from that exact
  revision. The qualified four-CPU-per-Phaser-task Marmic override applies only
  to this future replay; do not reinterpret job `625842` as using it.
- The corrected replay must publish and collect the MR seed review manifest,
  TSV/HTML package, final summary, and first-copy resume-check record while
  preserving the observed no-hit conclusion unless new scientific evidence
  differs.
- A scheduled known-positive control must demonstrate that the workflow can
  exceed the strict thresholds, and a deliberate incorrect-model control must
  remain rejected. Those controls and a human-completed approval file remain
  prerequisites for M4; this CD6 no-hit does not authorise additional-copy
  placement.

### Next exact starting point

Commit the review fix, regression tests, P2 interpretation documentation, and
this journal handoff; push `main` and monitor the exact GitHub Actions run.
After CI passes, run `readiness p2-diverse`, stage the immutable revision,
collect and verify its login-stage checksum, submit one fresh Slurm job, and
retarget the 30-minute heartbeat to that run. Retain job `625842` and its
collected evidence unchanged.

## 2026-08-12 — Submitted the review-contract replay

### Discoveries

- Review-repair commit `5914536eecf6a5409240ec93a74f44ca18036a36`
  passed Ubuntu GitHub Actions run `31541184883` in 2 minutes 56 seconds.
- Fixed-profile readiness is `ready=true` with Pixi `0.74.0` and the unchanged
  P0 configuration checksum
  `ac7ad4d2d4f9693683b89c8b492f645eddf026f782d90300b726f6be6d855dbb`.
- Fresh replay
  `gtd-p2-diverse-20260811T221301Z-5914536eecf6-2d589750` completed its login
  stage from the exact repair commit and nf-helper revision
  `ed7b71caccbb8244e6d1f3ff42eaa8680728e43a`.

### Accomplishments and immutable evidence

- The collected `p2-diverse-login-stage.sha256` record binds six direct-PDB
  search and registration artefacts. The four allowlisted payloads present in
  the bounded local collection match their recorded SHA-256 values; the two
  larger search-result payloads remain retained remotely and are bound by the
  same submit-time record.
- The fixed dispatcher accepted the staged record and submitted Slurm job
  `625882`. Its first status is scheduler state `RUNNING`, `terminal=false`,
  with no exit code or failure class.
- The 30-minute heartbeat now targets only this replay. Earlier jobs `625842`
  and `625831` and their collected evidence remain retained and untouched.

### Unresolved work

- Let job `625882` run without interference or a runtime timeout. Check it only
  through the installed wrapper at the recorded 30-minute cadence; do not infer
  failure from silence, elapsed time, or an SSH outage.
- When terminal, collect bounded evidence and require the corrected review
  manifest, TSV/HTML package, final summary, and first-copy resume-check record.
  Re-evaluate every result against strict `LLG > 100` and `TFZ > 10`, retaining
  packing and placed-copy evidence independently.
- The known-positive and deliberate incorrect-model controls, followed by a
  human-completed approval file, remain prerequisites for M4 even if the CD6
  replay reproduces its 25 scientific no-hits.

### Next exact starting point

At the next heartbeat, run only
`nf-gtd-hpc-test --no-progress status --run-id gtd-p2-diverse-20260811T221301Z-5914536eecf6-2d589750`.
If non-terminal, leave the run untouched. If terminal, run bounded logs and
collect as separate operations, inspect the complete review/result/resume
evidence, retain the remote run, and close the development loop with
documentation, checks, a focused commit, push, and exact GitHub Actions result.

## 2026-08-12 — Lowered the provisional acceptance score gate

### Discoveries

- The user explicitly replaced the prototype score-gate policy with strict
  `LLG > 50` or `TFZ > 5` acceptance. Equality fails each branch. Final packing
  and the requested placed-copy count remain independent requirements, and the
  handoff still requires raw metrics, calibration, and human review rather than
  universal hard-threshold claims.
- Recomputing the 25 preserved CD6 results from job `625842` under the new rule
  yields six score-gate passers, all through `TFZ > 5`; none passes through
  `LLG > 50`. All six also record accepted top-solution packing and one placed
  copy. Their TFZ range only reaches 5.5, so they are sensitive provisional
  candidates, not validated structures.
- Active job `625882` is immutable at commit
  `5914536eecf6a5409240ec93a74f44ca18036a36` and therefore stores the
  superseded `LLG > 100` and `TFZ > 10` classification. It remains untouched;
  its raw values are sufficient for policy reclassification after collection.

### Accomplishments and immutable evidence

- A central versioned MR policy now defines the two strict thresholds,
  disjunctive operator, and policy identifier. The Phaser adapter is version 3,
  records the thresholds and `or` operator in every solution result, and uses
  the policy for hit/no-hit classification.
- MR review version 2 recomputes the current gate from raw scores, includes the
  policy in its cache/package identity and manifest, ranks automatic
  eligibility explicitly, and accepts a known version-2 legacy policy for
  reclassification. Unknown policies and contradictions under the current
  policy still fail loudly.
- The three runnable public-control specifications now bind `LLG > 50`,
  `TFZ > 5`, and `combination: or`. Operational documentation explains the
  increased sensitivity and keeps packing, copy agreement, maps, refinement,
  scheduled controls, and expert review separate.
- Regression coverage proves strict equality failures, acceptance through
  either individual branch, rejection when both branches fail, policy metadata
  emission, and legacy raw-score reclassification. The complete locked gate
  passes formatting, Ruff, strict mypy, 284 unit tests, 55 contract tests, 39
  integration tests, schemas, the ten-entry public panel, documentation and
  workflow lint, Nextflow syntax/stubs/resume, and both HPC shell parsers.
- Policy-migration commit `69b69c4bead9db81501707b0c5dc6809509488e2`
  is pushed on `main`; Ubuntu GitHub Actions run `31543208944` passed the full
  foundation gate in 3 minutes 31 seconds.
- The 30-minute heartbeat now applies `LLG > 50` or `TFZ > 5` to raw terminal
  evidence and explicitly recognises that job `625882` predates the change.

### Unresolved work

- Do not stage a second P2-diverse run while job `625882` is active.
- When job `625882` becomes terminal, collect its bounded package and recompute
  eligibility from the raw scores. Its generated version-1 review package, if
  present, remains evidence of the old policy and must not be relabelled in
  place.
- After terminal collection, decide whether one new immutable version-2 review
  replay is needed to publish a policy-correct approval package. The scheduled
  known-positive and deliberate incorrect-model controls and a human-completed
  approval file remain prerequisites for M4.

### Next exact starting point

Continue monitoring only job `625882` through the installed wrapper at the
30-minute cadence; do not cancel, clean, or infer failure from silence. When
terminal, collect and compare the old stored classification with the new
raw-score recomputation before choosing the next immutable run. The next source
change should be driven by that terminal evidence or by the scheduled control
requirements, not by additional synthetic-test polishing.

## 2026-08-12 — P2-diverse replay completed with six current-policy candidates

### Discoveries

- Retained run
  `gtd-p2-diverse-20260811T221301Z-5914536eecf6-2d589750`, Slurm job
  `625882`, ran from `2026-08-11T22:16:04Z` to
  `2026-08-12T02:06:44Z`. It completed with scheduler state `COMPLETED`, exit
  code `0`, and failure class `success` from commit
  `5914536eecf6a5409240ec93a74f44ca18036a36`, nf-helper revision
  `ed7b71caccbb8244e6d1f3ff42eaa8680728e43a`, Pixi `0.74.0`, and lock
  checksum `ecb7b12f890172eb53180ef5027b360b8187dff7d168a7cd8fc6507f9215fdc5`.
- The immutable run used the superseded score policy and therefore stored 25
  `completed_no_hit` results, zero `completed_hit` results, and a version-1
  review package ordered by strict `LLG > 100` and `TFZ > 10`.
- Recomputing from the preserved raw metrics under current strict `LLG > 50`
  or `TFZ > 5` yields six provisional score-gate passers and six automatically
  eligible candidates after independent packing, one-placed-copy, coordinate,
  and MTZ checks. All six pass only through TFZ; no result has LLG above 50.
- The six candidates map to catalogue accessions `WP_042686707.1`,
  `WP_042684271.1`, `WP_042684304.1`, `WP_042684748.1`, `WP_042686121.1`,
  and `WP_042685919.1`. Their LLG range is 19.726–27.383 and TFZ range is
  5.1–5.5. The corresponding experimental model targets are 6SKF, 9ZNF, 9O17,
  and 9NRI, with expected ASU copy counts from three to seven.
- Bounded Phaser tails warn that these top TFZ values are below Phaser's own
  cutoff of 8 for a definite solution. The current user gate therefore retains
  them as sensitive review candidates, not validated structures or automatic
  permission to begin additional-copy placement.
- All 25 first-copy tasks completed. The largest observed task used 334.1% CPU
  and 4.2 GB peak RSS, supporting the qualified four-CPU/eight-GB allocation
  without evidence for a further memory increase.

### Accomplishments and immutable evidence

- The run published exactly 25 hypotheses: one predicted and 24 experimental,
  across 24 sequence-equivalence groups. Login and scheduled PDB search hashes
  match, and every result completed scientifically.
- Model preparation resumed one of one process from cache. The first-copy
  replay resumed all 26 processes from cache: one funnel plus 25 Phaser tasks.
- Review package
  `reviewpkg_8db1defec6c9e2a2c6e77c4abd6a95967ed072280c30ae23baf04b7f9708b848`
  contains 25 candidates, 25 approval-candidate rows, HTML review, and a
  header-only approval template. Its manifest SHA-256 is
  `7f26e828a5dabeb6832e37818a5d82956e556da81c328f416e5f4f738d87c9ac`,
  matching the summary and collected file.
- All four review-output checksums match their manifest records. The broader
  bounded artifact inventory binds the summary, results, commands, Phaser
  tails, resume checks, review package, and approval template.
- Evidence collection succeeded after the documented transient Marmic SSH
  outages. The remote run remains retained and unchanged; no cleanup, cancel,
  or remote source mutation occurred.

### Unresolved work

- The collected version-1 package is authoritative evidence of the policy that
  produced it, but its stored `automatic_eligibility=false` fields and solution
  ranking must not be relabelled in place. A new immutable version-2 review run
  is required to publish current-policy solution IDs, ranking, and approval
  candidates.
- The current six candidates require human inspection of maps and packing.
  Their marginal TFZ values make the known-positive control and deliberate
  incorrect-model control especially important for calibrating the sensitive
  disjunctive gate.
- Do not start M4 until a policy-correct review package exists, at least one
  human-reviewed seed is approved, and the scheduled controls demonstrate
  useful separation. The CD6 result alone does not identify a structure.

### Next exact starting point

Commit and push this terminal-evidence handoff and require the exact GitHub
Actions run to pass. Disable the completed-run heartbeat. Then run
`readiness p2-diverse` and stage one fresh immutable replay from the qualified
current-policy revision; collect and verify its login-stage checksum before
submission. Monitor that replay without a runtime timeout. Its purpose is to
publish the current-policy review package from real data, after which prioritise
the known-positive and deliberate incorrect-model controls over further
synthetic-test polishing.

## 2026-08-12 — Current-policy P2-diverse replay submitted

### Discoveries

- Terminal-evidence commit `5b5100e8651cae0498ad2d6dd185bf8fb8fbbecb`
  passed GitHub Actions run `31564419845`; the foundation check completed in
  3 minutes 42 seconds. The completed-run monitor was then removed.
- Marmic reported the fixed `p2-diverse` staging prerequisites ready with Pixi
  `0.74.0`. The readiness record bound P0 configuration checksum
  `ac7ad4d2d4f9693683b89c8b492f645eddf026f782d90300b726f6be6d855dbb`.
- New immutable run
  `gtd-p2-diverse-20260812T045236Z-5b5100e8651c-1f2fe41a` binds source commit
  `5b5100e8651cae0498ad2d6dd185bf8fb8fbbecb` and nf-helper commit
  `ed7b71caccbb8244e6d1f3ff42eaa8680728e43a`. Its current code publishes the
  strict `LLG > 50` or `TFZ > 5` policy rather than reclassifying the retained
  version-1 evidence.
- The collected login-stage evidence retained structural-hit checksum
  `dabf35703d83fb1c8368337a1225025d1c4aee4ddc50db33c3ce10231470db5a`,
  identical to the successful preceding run. This controls the real-data input
  set while testing only the policy-correct review publication path.

### Accomplishments and immutable evidence

- The local tree was clean before staging, and the wrapper recorded the run
  atomically under ignored `.untracked/hpc-test/` state.
- Staging and bounded evidence collection completed without arbitrary SSH or
  remote source changes. The staged search, result, structural-hit, coordinate,
  mapping, and registration checksums were collected before submission.
- The fixed wrapper submitted Slurm job `625935`. The first structured status
  snapshot reported scheduler state `RUNNING`, phase `submitted`, and
  `terminal=false`; no timeout, cancellation, or cleanup was requested.

### Unresolved work

- Wait for job `625935` to become terminal without inferring failure from
  silence. On success, collect and verify the version-2 review manifest, TSV,
  HTML, approval candidates, raw result scores, packing evidence, placed-copy
  counts, Phaser tails, and resume records.
- Confirm that current stored classifications and review ordering implement
  strict `LLG > 50` or `TFZ > 5`. The expected six marginal TFZ-only candidates
  remain review candidates, not validated structures.
- Human map/packing review plus known-positive and deliberate incorrect-model
  controls remain prerequisites for M4.

### Next exact starting point

Check only run `gtd-p2-diverse-20260812T045236Z-5b5100e8651c-1f2fe41a`
through the installed wrapper at the 30-minute cadence. Leave the run retained;
do not use raw SSH, cancel, clean, set a runtime timeout, or infer failure from
silence. If terminal, inspect bounded logs, collect the approved artefacts, and
compare the generated current-policy package with the six candidates derived
from the preceding immutable raw scores before selecting a human-review target.

## 2026-08-12 — Current-policy P2-diverse package qualified

### Discoveries

- Retained run
  `gtd-p2-diverse-20260812T045236Z-5b5100e8651c-1f2fe41a`, Slurm job
  `625935`, ran from `2026-08-12T04:57:45Z` to
  `2026-08-12T06:04:25Z`. It completed with scheduler state `COMPLETED`, exit
  code `0`, and failure class `success` from source commit
  `5b5100e8651cae0498ad2d6dd185bf8fb8fbbecb`, nf-helper revision
  `ed7b71caccbb8244e6d1f3ff42eaa8680728e43a`, Pixi `0.74.0`, and lock
  checksum `ecb7b12f890172eb53180ef5027b360b8187dff7d168a7cd8fc6507f9215fdc5`.
- All 25 raw results agree with their stored classifications: six
  `completed_hit` and 19 `completed_no_hit`. The six hits pass only through
  strict `TFZ > 5`; none passes `LLG > 50`. A result with TFZ exactly `5.0`
  was correctly rejected, demonstrating that the implemented comparison is
  strict rather than inclusive.
- The version-2 package places the six eligible candidates at ranks 1–6. In
  rank order they are `WP_042686707.1`/6SKF (LLG 27.383, TFZ 5.1),
  `WP_042684271.1`/9ZNF (25.838, 5.2),
  `WP_042684304.1`/9O17 (24.822, 5.3),
  `WP_042684748.1`/9O17 (22.148, 5.1),
  `WP_042686121.1`/9O17 (20.336, 5.2), and
  `WP_042685919.1`/9NRI (19.726, 5.5).
- Every eligible result has an independently parsed packed final solution, one
  placed copy matching the requested first-copy search increment, coordinate
  output, and MTZ output. The separate Matthews estimates remain three to seven
  total copies per ASU; first-copy eligibility does not claim that the full ASU
  has been placed.
- Phaser warns that all six TFZ values are below its cutoff of 8 for a definite
  solution. Rank 4 also retains the advisory that an earlier top FTF did not
  pack, while the later accepted final solution did pack. These are sensitive
  review candidates, not identified proteins or validated structures.
- All 25 Phaser tasks completed. The largest observed task used 317.5% CPU and
  4.3 GB peak RSS, which remains compatible with the qualified four-CPU/eight-GB
  task allocation.

### Accomplishments and immutable evidence

- Review package
  `reviewpkg_fe7c36037f3a034d61aa3e335bb8a13f433da09c3c252cd5169a26ae30e9a6da`
  uses adapter `mr-seed-review-v2` and records policy
  `strict_llg_gt_50_or_tfz_gt_5`, operator `or`, thresholds 50 and 5, and the
  policy-aware ordering. Its manifest SHA-256 is
  `da0604426294602a23f441f6a1aea77ec564e9ef8b091ae588b9b861feef55c4`,
  matching the run summary and collected file.
- The package contains 25 candidates across 24 sequence groups, a primary
  shortlist of 10, an extended set of 25, and full remote asset bundles for the
  first 20. Its TSV and approval-candidate files each contain 25 data rows; the
  approval template remains header-only, so no human approval was fabricated.
- All four review-output checksums match the manifest. All 16 rows of the
  broader bounded artifact inventory also match their collected files. The
  login and scheduled structural-hit checksum remains
  `dabf35703d83fb1c8368337a1225025d1c4aee4ddc50db33c3ce10231470db5a`.
- Row-wise audit found zero mismatches between automatic eligibility and the
  conjunction of score-gate, final-packing, and requested-copy checks. Model
  resume cached one of one process; first-copy resume cached all 26 processes,
  comprising one funnel and 25 Phaser tasks.
- The compact local collection retains indices, normalised results, logs,
  manifests, checksums, and review files. Large coordinate/MTZ asset bundles
  remain bound by checksums in the retained remote package rather than being
  copied outside the wrapper's approved small-artifact boundary.

### Unresolved work

- Human map and packing review is now the immediate scientific decision point.
  Add a checksum-gated wrapper operation for bounded review-asset collection so
  selected PDB/MTZ/log bundles can be inspected without raw SSH or unrestricted
  transfer.
- The known-positive control and deliberate incorrect-model control remain
  necessary to calibrate whether the sensitive TFZ-only gate separates useful
  candidates from noise. Do not tune the gate further from this single crystal.
- Do not start M4 or additional-copy placement until at least one seed is
  explicitly approved from map/packing review and the controls demonstrate
  useful separation. The current header-only approval file authorises nothing.

### Next exact starting point

Keep the successful run retained and disable its completed monitor. Implement
and test the smallest checksum-gated review-asset collection operation, then
collect only the six eligible bundles identified by the version-2 manifest for
human inspection. In parallel development order, add the already-planned
known-positive and deliberate incorrect-model control profiles. Preserve the
current raw scores and package unchanged; do not rerun P2-diverse merely to
polish the test case and do not begin M4 before review and controls.

## 2026-08-12 — Six eligible MR review bundles collected securely

### Discoveries

- The retained current-policy run can supply the six eligible review bundles
  without another P2-diverse execution. A fixed operation can derive its entire
  allowlist from the collected version-2 manifest, so neither a remote path nor
  a caller-selected candidate identifier is needed.
- The six bundles total about 22 MiB. Each contains one normalised result, one
  resolved Phaser command, the native Phaser log, one solution PDB, and one
  solution MTZ. All six PDBs and MTZs parse with Gemmi, contain one placed
  coordinate chain, agree on space group `I 1 2 1`, and each MTZ contains
  57,222 reflections plus `FC/PHIC`, `FWT/PHWT`, and
  `DELFWT/PHDELWT` coefficients. This is mechanical integrity evidence, not a
  map-quality judgement.
- Recomputed raw results remain unchanged: LLG values 19.726–27.383, TFZ values
  5.1–5.5, packed top solutions, and exactly one placed copy. All candidates
  pass only through strict `TFZ > 5`; none is thereby a validated structure.

### Accomplishments and immutable evidence

- Commit `0fc9b30794641deaf401df0784c68f147092d6e6` adds
  `review-collect`. Both local and remote sides validate the successful terminal
  run, package identity, adapter/policy metadata, exact eligible count, five
  fixed asset roles, every SHA-256, strict `LLG > 50` or `TFZ > 5`, final
  packing, and one placed copy. It permits at most 25 candidates, 128 MiB per
  file, and 512 MiB total and publishes local evidence atomically.
- Local `pixi run check` passed with 291 unit, 55 contract, and 41 integration
  tests plus schema, public-panel, documentation, actionlint, and Nextflow
  syntax/stub checks. GitHub Actions run `31594142714` passed for the same
  commit.
- The installed local wrapper SHA-256 is
  `3125dda3d2fabf81e10ce6e17161ec3d3ad4de54d586f6d226cf7c6e2eb11a38`.
  The deployed dispatcher is bound to the same commit with SHA-256
  `495b5a4a6acb7c303e657dfe4cb0305943200497470de8a374be5860baca6c34`;
  the unchanged job driver SHA-256 is
  `ffdcb323878662070f191259313229460802c3f9c9f89a340b8d627f272d6b9f`.
- The collected package remains
  `reviewpkg_fe7c36037f3a034d61aa3e335bb8a13f433da09c3c252cd5169a26ae30e9a6da`
  with manifest SHA-256
  `da0604426294602a23f441f6a1aea77ec564e9ef8b091ae588b9b861feef55c4`.
  Exactly 33 files were published: 30 candidate assets plus the manifest,
  P2-diverse summary, and outer job result. The retained remote run was not
  modified or cleaned.

### Unresolved work

- The P2 acceptance gate still needs one scheduled known-positive control and
  one deliberate incorrect-model/no-solution control through the same adapter.
  These should calibrate useful separation without retuning the provisional
  threshold from the CD6 panel.
- Human map and packing inspection is still required. The presence of readable
  map coefficients and one packed coordinate chain does not demonstrate that
  density supports the candidate or that the complete ASU has been explained.
- The header-only approval file remains unchanged. No candidate is approved,
  and M4 additional-copy placement remains blocked by design.

### Next exact starting point

Implement the smallest fixed scheduled control profile using the existing
checksum-frozen public-control specifications. Run a correct-model positive and
a deliberately unrelated model against the same fixed control diffraction
data, preserve raw LLG/TFZ/packing/copy evidence, and collect the result through
the normal wrapper cycle. Do not rerun the 25-model CD6 panel, do not tune its
threshold, and do not begin M4 until the controls and human review are complete.

## 2026-08-12 — Scheduled P2 controls launched

### Discoveries

- Marmic's Git executable currently fails before repository operations because
  it cannot open a required system descriptor. The installed wrapper therefore
  could neither update its bare mirror nor create an immutable checkout even
  though GitHub and the stored repository configuration were valid.
- The first fixed-control staging attempt,
  `gtd-p2-control-20260812T172729Z-5b1c97806fd3-2f72998b`, then exposed one
  scientific input-contract mismatch. The 8OOX specification used an obsolete
  short catalogue identifier, while the accepted P0 manifest binds
  `GCF_000711905.1` to
  `methermicoccus_shengliensis_gcf_000711905_1_refseq_2025_11_20`. Its assembly,
  frozen proteome checksum, target sequence, coordinates, MTZ, and score policy
  were already consistent.
- The corrected staging run verified the checksum-frozen public-control
  preparation, P0 catalogue and crystal manifests, derived 8OOX MTZ, exact
  8OOW model, and catalogue sequence records before scheduling Phaser.

### Accomplishments and immutable evidence

- Commits `4097d756bab8ce2b4ea2969af86e53ad1f927d8c`,
  `be9ada90708ae2da41a79eb315de32c0e48a9dc6`,
  `1e827bda7d559066b289e2c61432258721beb838`, and
  `5b1c97806fd346be68198f97743d53bad5d2d8a2` added checksum-gated recovery for
  the reviewed tools and clean, pushed source archive staging when the exact
  Marmic Git failure occurs. These paths remain bounded, checksum-verified, and
  restricted to repository-controlled files and an exact immutable commit.
- Commit `f8b0ea3bbc352c5fe955598133dc3435ada1cf4b` corrects only the frozen 8OOX
  catalogue binding and adds a focused regression assertion. The public-panel
  check and all ten public-control unit tests passed locally. GitHub Actions run
  `31623369146` passed the full repository gate.
- Run `gtd-p2-control-20260812T173905Z-f8b0ea3bbc35-e185cae0`, Slurm job
  `626388`, was staged from that exact commit with nf-helper revision
  `ed7b71caccbb8244e6d1f3ff42eaa8680728e43a` and Pixi `0.74.0`. It was running
  after its fixed input-integrity checks and had begun verifying the installed
  Phenix runtime. The preceding failed run remains retained as bounded evidence.

### Unresolved work

- Collect the terminal P2-control evidence and require the exact 8OOW model to
  be a packed `completed_hit` while the unrelated 1UBQ model is a parsed
  `completed_no_hit` under strict `LLG > 50` or `TFZ > 5`. Preserve raw scores,
  placed-copy evidence, commands, logs, checksums, and cached-resume results.
- Compare the control separation with the six marginal TFZ-only CD6 review
  candidates without retuning the gate from one crystal.
- Human map and packing review plus an explicit approval or rejection remain
  the final M3 checkpoint. M4 additional-copy placement remains blocked until
  that checkpoint is recorded.

### Next exact starting point

Check only run `gtd-p2-control-20260812T173905Z-f8b0ea3bbc35-e185cae0`
through the installed wrapper. If it is terminal, inspect bounded logs, collect
the approved small artefacts, verify positive/negative separation and resume
provenance, and retain the remote run. Do not add more fallback engineering,
rerun P2-diverse, tune the provisional gate, clean remote evidence, or begin M4
before the scientific control result and human-review decision are recorded.

## 2026-08-12 — P2-control monitor corrected

### Discoveries

- The first attempt to create a 30-minute monitor was not persisted because a
  thread heartbeat requires `destination=thread`. Absence of an automation
  record confirmed that no scheduled check had been active.
- The next wrapper-only status request at `2026-08-12T20:11:52Z` received
  `transfer_failure` because the Marmic SSH endpoint refused the connection.
  This is transport evidence only and says nothing about Slurm job `626388` or
  the scientific run state.

### Accomplishments and immutable evidence

- Active heartbeat `monitor-marmic-p2-control` is now persisted for this task
  at a 30-minute interval. It is restricted to wrapper-only status, bounded
  logs, and collection for retained run
  `gtd-p2-control-20260812T173905Z-f8b0ea3bbc35-e185cae0`; terminal handling
  includes the exact positive/negative scientific checks and journal handoff.
- The remote run was not cancelled, cleaned, modified, or classified from the
  failed transfer.

### Unresolved work

- Await a successful wrapper connection and terminal scheduler evidence, then
  collect and validate the two P2 controls exactly as specified in the previous
  entry.

### Next exact starting point

At the next 30-minute heartbeat, read this entry and issue one wrapper-only
status request for
`gtd-p2-control-20260812T173905Z-f8b0ea3bbc35-e185cae0`. If transport still
fails, leave the run untouched and wait for the next recurrence. If terminal,
perform bounded log inspection and approved collection before drawing any
scientific conclusion.

## 2026-08-12 — Two-control fan-out corrected and replayed

### Discoveries

- Retained run
  `gtd-p2-control-20260812T173905Z-f8b0ea3bbc35-e185cae0`, Slurm job
  `626388`, reached terminal scheduler state `FAILED`, exit code `4`, and
  wrapper class `test_failure`. It ran from `2026-08-12T17:41:29Z` to
  `2026-08-12T18:12:34Z`; this was not a runtime, Phenix, MTZ, or scheduler
  failure.
- All fixed inputs passed their checksums, Phenix 2.1-6048 verification passed,
  xtriage accepted the 8OOX MTZ in `P 43 3 2` at 3.088 A, and the control bundle
  contained both the exact 8OOW positive and unrelated 1UBQ negative. However,
  the Nextflow trace contained only the 1UBQ hypothesis, which completed in
  28.5 minutes with four CPUs, 1 GB peak RSS, and exit code zero; the resume
  replay cached that same single task.
- The control workflow consumed its one-item `control_bundle` queue both to
  enumerate hypotheses and as the prepared-models process input. Nextflow
  therefore paired that consumable item with only one hypothesis instead of
  broadcasting the directory to both. The final two-control summary was
  correctly absent, so no scientific separation result was fabricated.
- Repeated login-shell `/dev/null: Permission denied` messages are consistent
  with one malformed or inaccessible Marmic `/dev/null` device exposed by many
  ordinary shell redirects. They are a system issue distinct from this
  Nextflow fan-out defect; hiding redirects in shell startup files would not
  repair Git or other affected tools.

### Accomplishments and immutable evidence

- Commit `1085b3a088bfd35a397195a4425ca48bf0d79813` converts the prepared-model
  directory to a reusable value before the process fan-out. Its stub acceptance
  now requires exactly two trace rows and both frozen hypothesis IDs.
- Nextflow syntax, the two-hypothesis stub and cached resume, all 45 integration
  tests, Ruff formatting, and Ruff lint passed locally. GitHub Actions run
  `31639054057` passed the full repository gate.
- Corrected retained run
  `gtd-p2-control-20260812T204719Z-1085b3a088bf-fca7a26c`, Slurm job
  `626394`, was staged from that exact commit with nf-helper revision
  `ed7b71caccbb8244e6d1f3ff42eaa8680728e43a` and Pixi `0.74.0`; its first
  wrapper status was `RUNNING`.
- Heartbeat `monitor-marmic-p2-control` remains active at a 30-minute interval
  and is now bound to the corrected run and job. Both remote runs are retained.

### Unresolved work

- Collect the corrected run only after terminal evidence exists. Verify that
  both trace tasks ran, then apply the fixed positive-hit and negative-no-hit
  acceptance conditions to raw scores, packing, and placed-copy evidence.
- The Marmic administrator should inspect `/dev/null` as a system device. Do
  not attempt an unprivileged recreation and do not treat its shell messages as
  scientific failure evidence.
- Human map and packing review remains the final M3 checkpoint before M4.

### Next exact starting point

At the next 30-minute heartbeat, check only
`gtd-p2-control-20260812T204719Z-1085b3a088bf-fca7a26c` through the installed
wrapper. Leave it untouched if non-terminal. If terminal, inspect bounded logs,
collect the approved artefacts, validate both controls and resume provenance,
and retain both runs. Do not add fallback engineering, retune the score gate,
rerun P2-diverse, clean remote evidence, or start M4 before this control result
and the human-review decision are recorded.

## 2026-08-13 — P2 control exposes insufficient screening specificity

### Discoveries

- Corrected retained run
  `gtd-p2-control-20260812T204719Z-1085b3a088bf-fca7a26c`, Slurm job
  `626394`, ran from `2026-08-12T20:49:14Z` to
  `2026-08-13T00:51:18Z`. It reached scheduler state `FAILED`, exit code `4`,
  and wrapper class `test_failure` because the predeclared positive/negative
  separation assertion failed; both Phaser processes themselves completed
  successfully.
- The exact 8OOW positive is a decisive packed `completed_hit`: LLG 1622.755,
  TFZ 49.7, two accepted and packed solutions, and one requested placed copy in
  the expected `P 43 3 2` space group.
- The deliberately unrelated 1UBQ negative is also classified
  `completed_hit` under strict `LLG > 50` or `TFZ > 5`: LLG 30.089 does not
  pass, but TFZ 6.8 does. Its final top solution packed and placed one copy in
  `P 41 3 2`; Phaser warns that TFZ is below its cutoff of 8 for a definite
  solution and that an earlier top FTF did not pack. The negative therefore
  demonstrates a false-positive classification under the current sensitive
  score gate, not a validated molecular-replacement solution.
- The six CD6 review candidates have TFZ 5.1–5.5 and LLG below 50, all weaker
  on these scores than this unrelated negative. Their existing treatment as
  marginal review candidates remains appropriate, but the current disjunctive
  gate is not specific enough to serve as an acceptance rule.

### Accomplishments and immutable evidence

- Both fixed hypotheses ran: native jobs `626398` (1UBQ) and `626399` (8OOW)
  exited zero. The negative used 4 CPUs, 1 GB peak RSS, and 2 h 2 min realtime;
  the positive used 4 CPUs, 703 MB peak RSS, and 2 min 15 s realtime. The
  resume trace contains exactly the same two tasks as `CACHED`, and the
  normalised resume record reports two of two cached.
- The collected package contains the outer result, summary, raw JSONL results,
  exact command records, bounded Phaser tails, first and resume traces, control
  manifest, model records, and artifact checksum inventory. All 11 recomputed
  SHA-256 values match the inventory. Summary SHA-256 is
  `66b386a7986694213a966e7b1a164fc5d8aab7a0e4d88ac3c379393b47743ab7`;
  raw-results SHA-256 is
  `f7371ea2619b22948897e3fa3b15599b0faaa6ffe4ca16b18d34674d10b03c88`.
- Immutable provenance is source commit
  `1085b3a088bfd35a397195a4425ca48bf0d79813`, nf-helper revision
  `ed7b71caccbb8244e6d1f3ff42eaa8680728e43a`, Pixi `0.74.0`, lock checksum
  `ecb7b12f890172eb53180ef5027b360b8187dff7d168a7cd8fc6507f9215fdc5`,
  and immutable source-archive checksum
  `081e6856422ba34fabb799a7431eccc65fe7803b0050fd06db7b499e1ddd6365`.
  Both this run and the preceding one-sided run remain retained.

### Unresolved work

- The M3 control gate is not accepted. Do not relabel the unrelated negative,
  silently tighten the threshold, or reinterpret the six marginal CD6 results
  as validated structures.
- A scientific-policy decision is required: retain `LLG > 50` or `TFZ > 5`
  only as a sensitive review-screen rule and define a separate acceptance
  class, or explicitly revise the acceptance threshold with this negative and
  further controls as calibration evidence. Phaser's TFZ 8 warning is relevant
  evidence but is not adopted automatically here.
- Human map and packing review remains necessary. M4 additional-copy placement
  remains blocked until the acceptance policy and at least one explicit seed
  approval are recorded.

### Next exact starting point

Present the immutable positive/negative comparison for the user's scientific
policy decision. After approval, make the smallest policy-and-classification
change with regression tests using these frozen scores, then replay only the
fixed summary/classification path if possible; do not rerun the expensive
Phaser controls unless the immutable results cannot be safely reclassified.
Do not clean either retained run, rerun P2-diverse, or start M4.

## 2026-08-13 — Retain-all Coot review policy implemented locally

### Discoveries

- The user clarified the intended M3 boundary: the workflow may rank multiple
  Phaser solutions, but it must not discard a parsed candidate before human
  Coot inspection. The `LLG > 50` or `TFZ > 5` rule is therefore a
  higher-priority annotation, not an acceptance or transfer gate.
- The current-policy immutable CD6 run contains 25 tested hypotheses and 11
  parsed one-copy PDB/MTZ solutions. Six pass the numeric screen; five do not.
  All 11 already have complete PDB, MTZ, command, normalised-result, and log
  asset inventories bound by SHA-256 in the retained version-2 review manifest.
  The old collector exposed only the six `automatic_eligibility=true` items,
  so a Phaser rerun is unnecessary.
- The unrelated 1UBQ control also produced a parsed packed one-copy solution
  (LLG 30.089, TFZ 6.8). That does not justify deleting it. Its role is to show
  that exact 8OOW (LLG 1622.755, TFZ 49.7) overwhelmingly outranks an unrelated
  model while both raw outcomes remain inspectable.

### Accomplishments and immutable evidence

- Review adapter version 3 replaces `automatic_eligibility` with
  `inspectable_solution`. Every tested hypothesis remains in TSV/HTML, and
  every parsed PDB/MTZ solution carries its command, log, result, coordinate,
  and coefficients into the Coot package regardless of numeric tier. The
  existing full-artifact cap now applies only to ancillary Phaser `.sol` and
  rotation files.
- The first-copy normaliser now uses `completed_hit` for any internally
  consistent parsed coordinate/MTZ solution and `completed_no_hit` only when
  Phaser reports no solution. LLG/TFZ, packing, copy agreement, and review
  advisories remain separate fields. Explicit human approval remains mandatory.
- The checksum-gated `review-collect` path accepts both version-3 packages and
  immutable version-2 packages. For version 2 it derives the inspectable set
  only from complete five-role asset inventories, revalidates every checksum on
  both sides, and publishes to a new `review-assets-all/` directory. It does
  not rewrite the old manifest or trust caller-provided candidate IDs.
- The collected handoff also includes the manifest-bound review TSV, HTML
  report, approval-candidate TSV, and approval template. Older items with a
  checksum-bound PDB and MTZ remain directly approvable without an artificial
  override merely because their original numeric screen was negative.
- The control profile now requires both parsed controls to remain retained and
  the exact positive to exceed the unrelated model on both raw LLG and TFZ. It
  no longer demands that a weak unrelated solution disappear.
- Focused unit tests pass (67), including below-screen Coot assets, human
  approval, and version-2 migration without score filtering. The complete fake
  Git/Slurm/Nextflow lifecycle passes (45 integration tests). Full
  `pixi run --locked check` passes: Ruff format/lint, strict mypy, 306 unit, 55
  contract, and 45 integration tests, schemas, public panel, docs, actionlint,
  Nextflow syntax/stub/resume, and Bash syntax. The rebuilt ignored wrapper has
  SHA-256 `129ba40b63ec674804f979799038fbadc995717ad7c8011d85ac707db2a43df3`.

### Unresolved work

- Inspect the final tracked diff, commit, push, and require a green GitHub
  Actions run before installing/deploying the updated wrapper and dispatcher.
- After tool deployment, run `review-collect` once against retained immutable
  run `gtd-p2-diverse-20260812T045236Z-5b5100e8651c-1f2fe41a`. It should
  produce 11 checksum-verified Coot bundles without rerunning Phaser.
- The reviewer must inspect all 11 solutions in Coot and record explicit
  decisions. M4 remains blocked until at least one current package decision is
  validated; no score threshold supplies that decision.

### Next exact starting point

Run `git diff --check`, inspect the complete staged scope, and commit the
retain-all M3 policy as one coherent milestone. Push it, monitor GitHub Actions,
then build/install/deploy the exact committed wrapper and dispatcher. Finally
collect all 11 assets from the retained version-2 run through the approved
wrapper and prepare the Coot review handoff. Do not rerun P2-diverse or Phaser,
clean retained runs, retune numeric thresholds, or begin M4.

## 2026-08-13 — Retain-all milestone shipped; Coot transfer awaiting Marmic

### Discoveries

- The immutable version-2 review manifest contains four checksum-bound
  reviewer outputs in addition to the per-solution assets: candidate TSV, HTML
  report, approval-candidate TSV, and empty approval template. These can travel
  with all 11 parsed PDB/MTZ solutions, so the human handoff does not require a
  Phaser replay or reconstruction from partial local files.
- The new collector derived exactly 11 inspectable solution IDs from that
  retained manifest before contacting Marmic. The first collection attempt did
  not transfer any payload because the configured login endpoint refused the
  SSH connection. This is a `transfer_failure`, not missing scientific evidence
  or a reason to modify the retained run.

### Accomplishments and immutable evidence

- Commit `03f03ce2071f2df518b174cfbee6a5b8aa7d052f` implements the retain-all
  review boundary. It is pushed to `origin/main`; GitHub Actions run
  `31686694164` passed in 4 min 10 s.
- The final locked local gate passed Ruff format/lint, strict mypy, 306 unit,
  55 contract, and 45 integration tests, schemas, public controls, docs,
  actionlint, Nextflow syntax/stub/resume, and Bash syntax.
- The installed local wrapper matches SHA-256
  `129ba40b63ec674804f979799038fbadc995717ad7c8011d85ac707db2a43df3`.
  The checksum-gated deployment from the exact commit installed dispatcher
  SHA-256 `3dec6980509af8c7d263faf2c7d0994e455581b20fc5c984c81090c3fc3e09e9`
  and job-wrapper SHA-256
  `7e2ca34cd88f85957787cc7a9d86019a259358e1a0b11d771e3c11cb4595fbbd`.
- Heartbeat `retry-marmic-retain-all-review-collection` is active on a
  30-minute interval. It retries only the checksum-gated review collection and
  leaves the remote run untouched after transfer failures.

### Unresolved work

- Collect and verify the self-contained 11-solution Coot handoff when Marmic
  SSH accepts connections. Preserve the retained remote run.
- A reviewer must inspect the coordinate/coefficient pairs and record explicit
  decisions. The numeric `LLG > 50` or `TFZ > 5` screen is ordering metadata,
  not a candidate filter or validation decision.
- M4 additional-copy placement remains blocked until at least one decision from
  this retain-all package passes the review-decision validator.

### Next exact starting point

Retry only `review-collect` for retained run
`gtd-p2-diverse-20260812T045236Z-5b5100e8651c-1f2fe41a` through the installed
wrapper. If transfer succeeds, verify exactly 11 five-role solution bundles and
the four reviewer outputs against the immutable manifest, then prepare the Coot
procedure. Do not use raw SSH, rerun Phaser, clean the run, tune thresholds, or
start M4 before explicit human approval.

## 2026-08-13 — Complete retain-all Coot handoff collected

### Discoveries

- No Slurm test was running or required. `review-collect` reads the already
  completed run from retained NFS evidence and streams only manifest-approved
  files.
- After the first tool deployment, two collection attempts still returned the
  legacy six-solution archive shape even though the deployment record named the
  new dispatcher checksum. Repeating the same idempotent checksum-gated
  deployment returned the exact expected dispatcher checksum again; the next
  fresh dispatcher invocation immediately returned all 11 solutions. This is
  consistent with delayed visibility or activation of a self-updated executable
  on the shared filesystem, not a scheduler or scientific-run failure.
- The version-2 manifest records 25 hypotheses, six old
  `automatic_eligibility` rows, and 11 complete five-role solution inventories.
  The retain-all collector correctly uses the latter and ignores the obsolete
  numeric transfer filter.

### Accomplishments and immutable evidence

- The self-contained handoff was published atomically below the ignored local
  run evidence. It contains 62 files (42 MiB): 11 directories with PDB, MTZ,
  command, normalised result, and Phaser log; four reviewer outputs; the review
  manifest; the P2 summary; and the outer job result.
- All 59 manifest-bound assets were independently rehashed locally with zero
  mismatches. The wrapper additionally verified the manifest, summary, and job
  result before publication. The immutable manifest SHA-256 is
  `da0604426294602a23f441f6a1aea77ec564e9ef8b091ae588b9b861feef55c4`;
  package ID is
  `reviewpkg_fe7c36037f3a034d61aa3e335bb8a13f433da09c3c252cd5169a26ae30e9a6da`.
- The collected summary records 25 of 25 scientific completions, six legacy
  higher-priority hits, 19 legacy no-hit classifications, and a fully cached
  resume. All 11 parsed coordinate/coefficient pairs remain available for Coot
  regardless of that old classification.
- Heartbeat `retry-marmic-retain-all-review-collection` was deleted after the
  complete handoff passed verification. The remote run remains retained.

### Unresolved work

- The user must inspect all 11 PDB/MTZ pairs in Coot and enter explicit
  approve/reject decisions in the supplied template. `LLG > 50` or `TFZ > 5`
  remains ranking metadata only.
- Validate the edited decisions against the immutable review manifest. M4 is
  still blocked until at least one Coot-inspected seed is explicitly approved.
- A later operational hardening change may add an explicit post-deployment
  dispatcher-version probe; it must not delay the current human review.

### Next exact starting point

Prepare and follow the Coot inspection procedure using the 11 directories in
the verified `review-assets-all` handoff. Edit `approved_mr_seeds.tsv`, then run
the existing MR-seed decision validator against
`mr_seed_review_manifest.json`. Do not rerun Phaser, discard below-screen
solutions, clean the retained run, or start M4 before an explicit validated
approval.
