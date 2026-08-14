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

## 2026-08-13 — All 11 inspectable seeds authorised for comparative M4

### Discoveries

- The user confirmed that several leading solutions look plausible and
  explicitly requested testing every retained candidate to determine which is
  best downstream. This authorises all 11 inspectable PDB/MTZ pairs as
  experimental M4 seeds; it does not validate any protein identity or model.
- The immutable version-2 review manifest lists 25 hypotheses, including 14
  rows whose bounded transport inventory contains only command, result, and log
  metadata. The self-contained handoff correctly transports the 11 complete
  coordinate/MTZ bundles. The approval validator nevertheless tried to open
  every listed asset before reading the decisions, so it rejected this valid
  bounded handoff on an unselected metadata-only row.

### Accomplishments and immutable evidence

- The checksum-bound empty approval template was restored byte-for-byte;
  SHA-256 remains
  `6bd5f2070522ca12adb15393df821f0f35c84bab00d25e5cf0687333fa3efad8`.
  Reviewer decisions are held separately from the immutable package.
- Approval validation now authenticates package identity and shared outputs,
  then verifies the complete asset inventory and checksums for every explicitly
  decided item. It still rejects unknown IDs, unsafe paths, missing or edited
  decided assets, stale timestamps, and uninspectable approvals without an
  override. A regression test covers a bounded package where an unselected
  metadata-only item was not transported.
- All 11 experimental approvals validated as review
  `rev_93fca367b3bec6e564a5dc1cb4a4df94a413b4ceec021306d981c1e7aedf59cf`
  against package
  `reviewpkg_fe7c36037f3a034d61aa3e335bb8a13f433da09c3c252cd5169a26ae30e9a6da`.
  The decision comment states that advancement is comparative and experimental,
  not final identification.

### Unresolved work

- Implement M4 sequential same-component placement for all 11 approved seeds,
  retaining each parent and independent packing/score evidence. Rank downstream
  refinement, map, and sequence evidence without discarding alternatives.
- Brief refinement, stable map generation, sequence-from-map catalogue search,
  and the second human-review package remain unimplemented.

### Next exact starting point

Ship the bounded-handoff approval-validator correction through the locked local
gate and GitHub Actions. Then extend the existing Phaser adapter with a
fixed-solution additional-copy operation and typed parent-child result, wire a
minimal Nextflow M4 workflow, and run the 11 approved seeds on Marmic. Do not
interpret experimental approval, a failed added copy, or numeric MR scores as
final structural identification.

## 2026-08-13 — Executable M4 copy-two slice implemented locally

### Discoveries

- Phenix 2.1-6048's installed interface supports the required fixed-parent
  operation directly: an ensemble with `solution_at_origin = True` is treated
  as already placed, while a separate search ensemble can be requested once.
  This avoids reconstructing Euler/translation parameters from PDB remarks.
- The retained review package intentionally excludes the original search-model
  files. M4 must therefore stage the checksum-matched processed models from the
  immutable upstream run; it must not use the placed parent PDB as both fixed
  content and the search model or infer composition from coordinate residues.

### Accomplishments and immutable evidence

- Added a typed `mr add-copy` adapter and `AdditionalCopyResult`. It authenticates
  approval/package provenance, parent PDB/result/command hashes, the original
  search-model hash and identity setting, exact catalogue sequence, MTZ
  preflight, and the verified Phenix manifest before execution.
- The generated PHIL fixes the approved parent at the origin, searches one
  additional same-component copy, and uses the full expected copy count and
  exact catalogue sequence for composition. A child advances only with packed
  output and at least two placement records. Every outcome retains the parent;
  a failed addition explicitly does not prove absence.
- Added `screen_additional_copies.nf` with parser-v2 typed workflow/module
  wiring, isolated per-seed fan-out, stub fixtures, and resume coverage. Paths
  containing spaces are PHIL-quoted.
- The full locked repository gate passed with 310 unit, 55 contract, and 45
  integration tests plus schemas, public controls, documentation, Actions
  lint, Nextflow syntax/stub/resume, and Bash syntax. A final focused adapter
  replay passed four tests after adding independent parent-result/command hash
  checks.

### Unresolved work

- Add a checksum-gated Marmic M4 stage/submit/collect profile that imports the
  11 approved review bundles, their original processed models, hypotheses,
  catalogue sequence groups, preflight, MTZ, and Phenix manifest from retained
  immutable evidence.
- Run the copy-two fan-out against real Phenix and inspect normalised results.
  Then iterate supported children one copy at a time to each expected count.
- Copy-count reporting, brief refinement, stable maps, sequence-from-map,
  sequence checkpoint, M5 reporting/pilot, and M6 hardening remain outstanding.

### Next exact starting point

Commit and push this executable M4 copy-two slice and monitor GitHub Actions.
Then implement the bounded wrapper profile, deploy the exact commit, and launch
all 11 approved seeds on Marmic. Do not start refinement until real additional-
copy parsing and parent-retention semantics have been checked once.

## 2026-08-13 — Comparative M4 Marmic profile ready for publication

### Discoveries

- The retained P2-diverse run contains the complete review package, catalogue
  sequence groups, preflight and hypotheses, and the original processed model
  files needed by copy-two screening. The bounded local review handoff does not
  contain those processed models, so an M4 run must resolve them inside the
  retained parent by the SHA-256 recorded in each first-copy command.
- Reusing the generic `stage` interface would not bind the human decision file
  to the new run. A dedicated checksum-confirmed stage operation is required to
  preserve the explicit checkpoint without exposing arbitrary remote paths.
- One aggregate local check encountered a pre-existing pytest `/tmp` base that
  could not be removed while another process held it. The same integration
  suite passed 45/45 with an isolated base; this was local test-state
  interference, not a pipeline regression.

### Accomplishments and immutable evidence

- Added the `m4-copy-stage` wrapper boundary. It accepts only an owned retained
  successful P2-diverse run, a pushed clean revision, and a bounded ASCII TSV
  whose SHA-256 must be repeated as confirmation. The remote dispatcher verifies
  the immutable review-manifest checksum, reruns the approval validator, requires
  exactly 11 approved seeds, and resolves each original model by recorded hash.
- Added the fixed `m4-copy` Slurm profile. It runs all 11 parents independently
  through copy two, repeats the run with `-resume`, requires all 11 tasks to be
  cached, retains every parent, and records normalised results, commands, bounded
  Phaser tails, raw support metrics, traces, provenance, and checksums. A failed
  addition remains non-absence evidence and does not remove the parent.
- Updated the operational runbook and bounded collector. Focused M4/HPC tests
  passed, as did 312 unit tests, 55 contract tests, 45 isolated integration
  tests, Ruff, mypy, schema validation, the ten-structure public panel,
  actionlint, Nextflow parser checks and stub/resume, documentation links, Bash
  syntax, and `git diff --check`. The preceding executable M4 commit
  `f03711b4041cf00e84c56ea284f8e78b436e515b` is green in GitHub Actions run
  `31702608787`.

### Unresolved work

- Publish this wrapper/profile milestone, deploy its exact reviewed tools, and
  run the real 11-seed copy-two comparison on Marmic.
- Inspect raw copy-two support, packing, placement count, LLG/TFZ and LLG delta;
  then iterate only supported children one copy at a time to each hypothesis's
  expected copy count while retaining all earlier parent states.
- Brief refinement, stable maps, sequence-from-map catalogue comparison, the
  sequence checkpoint, reporting/pilot expansion, and M6 hardening remain.

### Next exact starting point

Commit and push the comparative M4 profile, monitor GitHub Actions, build and
install the exact local wrapper, deploy the checksum-reviewed remote tools, then
invoke `m4-copy-stage` for retained P2-diverse run
`gtd-p2-diverse-20260812T045236Z-5b5100e8651c-1f2fe41a` with the separate 11-row
decision TSV and submit the returned run ID. Do not drop any candidate or begin
refinement until the real copy-two evidence has been collected and compared.

## 2026-08-13 — Real 11-seed M4 comparison submitted

### Discoveries

- Checksum-bound staging successfully found and verified the original processed
  model for every approved seed in the retained P2-diverse evidence. No model,
  decision, or review asset had to be reconstructed or substituted.

### Accomplishments and immutable evidence

- Comparative M4 profile commit
  `8396fefc26d039964641f821346a35733fdc52b5` was pushed and passed GitHub
  Actions run `31705933877`. The installed local wrapper SHA-256 is
  `cfaf44183a104c71436535f5be20a82b81861d2fd03b7e64b4964707f7780281`;
  deployed dispatcher and job SHA-256 values are respectively
  `7809949e8039b609461abdbf07d9b12130e6460a921a1954dcf6eb37ee1e4cc7`
  and `b84c57052100e6e679bf2414677e292c5ac6a6ea1c3cd48165cdcb9808d77253`.
- Staged run `gtd-m4-copy-20260813T134411Z-8396fefc26d0-54c9157e`
  authenticated parent run
  `gtd-p2-diverse-20260812T045236Z-5b5100e8651c-1f2fe41a`, all 11 decisions,
  decision checksum
  `7bbe539cf3c02b253ee94d829af6cf0b516e8eecedc6c784ab12cd707d012e2c`,
  review-manifest checksum
  `da0604426294602a23f441f6a1aea77ec564e9ef8b091ae588b9b861feef55c4`,
  Pixi 0.74.0, and nf-helper revision
  `ed7b71caccbb8244e6d1f3ff42eaa8680728e43a`.
- Slurm job `626455` was submitted and its first structured status was
  `RUNNING`. A 30-minute heartbeat named `monitor-marmic-m4-copy` now checks
  only through the installed approved wrapper.

### Unresolved work

- Wait for the immutable 11-way copy-two comparison to become terminal without
  imposing or inferring a runtime timeout. Then collect and compare all raw
  outcomes and resume evidence.
- Supported children still require sequential copy-three-to-expected-count
  testing before refinement. Refinement, maps, sequence-from-map, the second
  checkpoint, reporting, and hardening remain later roadmap work.

### Next exact starting point

Read this entry, then check only run
`gtd-m4-copy-20260813T134411Z-8396fefc26d0-54c9157e` with the installed wrapper.
If it is non-terminal, leave it untouched. If terminal, retrieve bounded logs
and collect evidence, verify all 11 parents and the fully cached resume, rank
copy-two support without discarding alternatives, and record the exact next
sequential-copy development step.

## 2026-08-13 — First M4 comparison exposed status-gated orchestration

### Discoveries

- Immutable run `gtd-m4-copy-20260813T134411Z-8396fefc26d0-54c9157e`
  became terminal after all 11 approved tasks were submitted, but Nextflow
  stopped the cohort when seed
  `sol_979f033dd494dd7b0ddb50b76bf7db346f68a546ea8f3bf66e256fd93b21fb75`
  failed the add-copy adapter's root-seed check. Its retained parent evidence is
  scientifically usable for comparative testing: one placed copy, 49 packed
  solutions, LLG 25.248, and TFZ exactly 5.0. It is stored as
  `completed_no_hit` only because it does not pass the separate strict ranking
  annotation `LLG > 50 OR TFZ > 5`.
- Requiring `completed_hit` at the M4 entry point therefore confuses a ranking
  policy with the structural precondition for continuing a user-approved
  candidate. The correct M4 precondition is successful parsed parent execution,
  exactly one placed copy, a packed parent solution, intact review-package
  checksums, and explicit approval. The score-derived status must remain
  provenance, not become a candidate-dropping gate.
- Because the process exits non-zero for this candidate, Nextflow killed six
  concurrently running sibling tasks. No comparative result or resume summary
  exists, so the run provides orchestration evidence rather than scientific
  copy-two rankings.

### Accomplishments and immutable evidence

- Bounded logs and the approved collection operation captured the retained
  failure evidence locally. Slurm job `626455` ran on
  `slurm-001.mpi-bremen.de` from `2026-08-13T13:46:01Z` to
  `2026-08-13T13:48:15Z`, ended `FAILED` with exit code 1 and failure class
  `test_failure`, and has failure signature
  `aff38209096b9728535dff097ef82be38abf67003bfe6d65a3b1c8445559f412`.
- Staging retained exactly 11 approved seed IDs. The immutable provenance is
  source `8396fefc26d039964641f821346a35733fdc52b5`, nf-helper
  `ed7b71caccbb8244e6d1f3ff42eaa8680728e43a`, Pixi 0.74.0, lock SHA-256
  `ecb7b12f890172eb53180ef5027b360b8187dff7d168a7cd8fc6507f9215fdc5`,
  decision SHA-256
  `7bbe539cf3c02b253ee94d829af6cf0b516e8eecedc6c784ab12cd707d012e2c`,
  review-manifest SHA-256
  `da0604426294602a23f441f6a1aea77ec564e9ef8b091ae588b9b861feef55c4`,
  and MTZ SHA-256
  `5eb16c3cc3a21e4b7f22cd611834529801c1829fc0a3156a2b6abc2b3de2f20d`.
- Parent and child runs remain retained. No candidate was removed, no score
  threshold was changed, and refinement was not started.

### Unresolved work

- Change the add-copy eligibility check so an explicitly approved, packed,
  exactly-one-copy `completed_no_hit` parent can run while a failed, unparsed,
  unpacked, or incorrectly placed parent still fails loudly. Add focused tests
  for both acceptance and rejection.
- Make comparative process failures candidate-level records rather than a
  fail-fast cohort abort, so one unsupported addition cannot erase results from
  the other ten candidates. This is required by the retain-all review strategy,
  but should remain a small M4 orchestration change rather than a general
  fallback framework.
- Re-run the full local checks, commit, push, monitor GitHub Actions, deploy the
  checksum-reviewed tools, and launch a new immutable 11-way M4 comparison.
  Only terminal results from that corrected run can decide which candidates
  proceed to sequential copies toward their expected counts.

### Next exact starting point

Inspect `src/genome_to_diffraction/mr/add_copy.py` and its focused tests. Replace
the `completed_hit` requirement with an explicit successful-parsed-parent plus
packed-one-copy requirement, and make the M4 Nextflow module preserve a
normalised per-candidate failure result instead of aborting siblings. Run the
development cycle through local Pixi checks, commit, push, GitHub Actions, and a
new retained Marmic M4 run; compare all 11 outcomes before beginning copy three
or refinement.

## 2026-08-13 — Corrected retain-all M4 comparison running

### Discoveries

- The previous scientific failure was an entry-condition defect, not a Phaser
  failure: the adapter required the score-derived `completed_hit` label even
  when an explicitly approved parent had a successfully parsed, packed,
  exactly-one-copy solution. Score annotation and structural eligibility are
  now independent.
- The first corrected staging attempt exposed a separate state-transition race.
  The common source stage briefly published `phase=staged` before M4-specific
  review assets and models were finished. Submission during that interval
  started Slurm against a changing manifest. The compute guard correctly
  stopped job `626474` as `environment_failure`; no Phaser task ran.

### Accomplishments and immutable evidence

- Commit `b5d6558e882a07493421a1ddb7c76188d9f536c1` accepts explicitly
  approved `completed_hit` or `completed_no_hit` parents only when they are
  successfully parsed, top-solution packed, and contain exactly one placed
  copy. Failed, unpacked, and wrong-copy parents still fail loudly. Nextflow now
  uses `errorStrategy 'finish'` for genuine candidate contract failures so
  submitted siblings are not killed immediately. GitHub Actions run
  `31711606416` passed.
- Commit `0d9c3ef5b905181548f4bd64ace40c06e9153790` keeps M4 in
  `m4_input_staging` until all 11 input bundles and the final stage-manifest
  checksum exist, then publishes `staged`. GitHub Actions run `31712996408`
  passed. The full local locked gate passed with 319 unit, 55 contract, and 45
  integration tests plus schema, public-panel, documentation, actionlint,
  Nextflow syntax/stub, and shell checks.
- Failed staging-race run
  `gtd-m4-copy-20260813T145117Z-b5d6558e882a-b001832e` is retained with
  Slurm job `626474` and failure signature
  `8007912e1dbda7de7803698d1983a1f3ae30cd785b37c2e111848646c64abceb`.
- The reviewed local wrapper SHA-256 is
  `de3e161ec9eaae5da6a839908b2a5e38587e0a62c8fdbee579b913079b9a35ed`.
  The deployed dispatcher SHA-256 is
  `d7d5ba4cc67e1279c23c88a767c8d7f6652439a1028693e6d04ed65c847f72e7`;
  the unchanged job-runner SHA-256 is
  `b84c57052100e6e679bf2414677e292c5ac6a6ea1c3cd48165cdcb9808d77253`.
- Corrected run `gtd-m4-copy-20260813T150438Z-0d9c3ef5b905-1cc7e54a`
  staged all 11 seeds only after finishing the checksum-bound copy and was
  submitted as Slurm job `626475`. Its first structured state was `RUNNING`.
  It retains parent run
  `gtd-p2-diverse-20260812T045236Z-5b5100e8651c-1f2fe41a`, decision SHA-256
  `7bbe539cf3c02b253ee94d829af6cf0b516e8eecedc6c784ab12cd707d012e2c`,
  review-manifest SHA-256
  `da0604426294602a23f441f6a1aea77ec564e9ef8b091ae588b9b861feef55c4`,
  and nf-helper revision
  `ed7b71caccbb8244e6d1f3ff42eaa8680728e43a`.

### Unresolved work

- Leave job `626475` untouched until terminal. Then collect all 11 typed
  outcomes, commands, bounded logs, first/resume traces, summary, and checksum
  inventory. Verify parent retention, raw LLG/TFZ/delta, packing, placement,
  candidate-level failures, and a fully cached resume.
- Rank support without dropping alternatives. Supported copy-two children must
  then advance sequentially toward their candidate-specific expected counts.
  Brief refinement, maps, sequence-from-map catalogue comparison, the second
  checkpoint, reporting, and hardening remain after that M4 evidence.

### Next exact starting point

Read this entry and check only retained run
`gtd-m4-copy-20260813T150438Z-0d9c3ef5b905-1cc7e54a` through the installed
wrapper. If non-terminal, leave it untouched. If terminal, retrieve bounded
logs, collect the approved evidence set, compare all 11 results, verify the
cached resume and immutable provenance, and implement the smallest sequential
copy-three-to-expected-count increment supported by those results. Do not begin
refinement or discard a candidate merely because an additional-copy attempt is
unsupported.

## 2026-08-13T16:14:58Z - Sequential additional-copy adapter implemented

### Discoveries

- A read-only wrapper status request for corrected M4 run
  `gtd-m4-copy-20260813T150438Z-0d9c3ef5b905-1cc7e54a` timed out while opening
  the Marmic SSH connection. This is a local `transfer_failure`, not scheduler
  or job evidence; Slurm job `626475` therefore remains retained and untouched.
- The copy-two adapter could authenticate only the original one-copy review
  seed. Advancing copy 3..n required explicit lineage from the immediately
  preceding supported child rather than rediscovering or overwriting the root
  seed.

### Accomplishments

- `mr add-copy` now accepts an inseparable prior result/coordinate pair for
  sequential placement. It authenticates the review, seed, hypothesis,
  sequence group, expected-copy hypothesis, result/coordinate checksums,
  supported status, packing-derived placement count, and child identity.
- Attempt identities and command records now bind the immediate parent solution,
  parent copy count, parent result checksum, and parent coordinate checksum.
  Successful children advance exactly one copy; unsupported children retain
  their parent count, and an n-copy parent cannot advance beyond its expected
  count.
- Tests cover copy two to copy three, checksum drift, and the expected-copy
  stopping boundary. The complete locked local gate passed with 322 unit, 55
  contract, and 45 integration tests, plus formatting, linting, strict typing,
  schemas, public-panel contracts, documentation, GitHub workflow linting,
  Nextflow syntax/stub/resume, and shell checks.

### Immutable evidence

- Corrected real-data run remains
  `gtd-m4-copy-20260813T150438Z-0d9c3ef5b905-1cc7e54a`, source revision
  `0d9c3ef5b905181548f4bd64ace40c06e9153790`, Slurm job `626475`, parent run
  `gtd-p2-diverse-20260812T045236Z-5b5100e8651c-1f2fe41a`, decision SHA-256
  `7bbe539cf3c02b253ee94d829af6cf0b516e8eecedc6c784ab12cd707d012e2c`,
  and review-manifest SHA-256
  `da0604426294602a23f441f6a1aea77ec564e9ef8b091ae588b9b861feef55c4`.
- The only new remote observation is the structured wrapper
  `transfer_failure`; no terminal state, log, cancellation, cleanup, or inferred
  failure was recorded.

### Unresolved work

- Collect and compare the corrected copy-two results when Marmic becomes
  reachable. All 11 parent candidates remain in scope, including unsupported or
  failed additions as retained negative evidence.
- Wire the authenticated one-step adapter into bounded sequential Nextflow
  orchestration for supported children through each candidate's expected copy
  count. Brief refinement, map generation, sequence-from-map comparison, the
  second review checkpoint, reporting, and prototype hardening remain afterward.

### Next exact starting point

Read this entry, retry only the installed wrapper status for corrected M4 run
`gtd-m4-copy-20260813T150438Z-0d9c3ef5b905-1cc7e54a`, and do not infer job state
from SSH silence. If terminal, inspect bounded logs and collect the complete
copy-two evidence before choosing which supported child states enter sequential
copy placement. In parallel-safe local work, wire the tested adapter into the
smallest bounded copy-three-to-expected-count workflow increment; do not begin
refinement or drop alternative candidates.

## 2026-08-13T16:44:36Z - Bounded sequential-copy workflow completed locally

### Discoveries

- The existing Nextflow process could remain one isolated task per approved
  seed: a bounded Python series can perform one authenticated transition at a
  time, stop at expected `n` or the first unsupported addition, and retain each
  child directory. No recursive workflow or new candidate-selection layer is
  needed for this prototype increment.
- The Marmic status endpoint again timed out before returning remote state.
  This remains only a wrapper `transfer_failure`; corrected Slurm job `626475`
  is retained and no scheduler or scientific outcome is inferred.
- An interrupted earlier pytest invocation left its fixed integration basetemp
  non-empty. The full integration suite passed with a fresh isolated `/tmp`
  basetemp, showing this was test-run residue rather than a code regression.

### Accomplishments

- Commit `a9ca0161a0b5ac5e51effe52daf569f8c64e846c` published the authenticated
  one-step copy-state adapter. GitHub Actions run `31719834027` passed.
- `mr add-copy --until-expected` now advances each approved seed from copy two
  through its hypothesis-specific expected count, using only the immediately
  preceding supported child. It stops on unsupported scientific evidence and
  never treats that stop as proof of absence.
- The workflow retains copy-specific results, PDB/MTZ outputs, commands, logs,
  result checksums, an aggregate JSONL, and a per-seed series summary. The
  Marmic runner and collector now aggregate every transition and series rather
  than reporting only the root copy-two record.
- Local validation passed: 323 unit, 55 contract, and 45 integration tests;
  formatting, Ruff, strict mypy, schemas, public panel, documentation links,
  actionlint, Nextflow syntax/stub/resume, wrapper shell syntax, and
  `git diff --check`.

### Immutable evidence

- Published adapter revision:
  `a9ca0161a0b5ac5e51effe52daf569f8c64e846c`; GitHub Actions:
  `31719834027` (`success`).
- Corrected earlier real-data run remains
  `gtd-m4-copy-20260813T150438Z-0d9c3ef5b905-1cc7e54a`, source revision
  `0d9c3ef5b905181548f4bd64ace40c06e9153790`, Slurm job `626475`. The new
  sequential workflow has not yet been submitted to Marmic.
- Sequential-series unit evidence covers supported copy two to copy three,
  exact expected-count stopping, immediate-parent linkage, result/coordinate
  checksum authentication, aggregate result order, and retained-state summary.

### Unresolved work

- Commit and publish the sequential workflow/collector increment, monitor its
  GitHub Actions run, build/deploy checksum-reviewed tools, and run it as a new
  immutable Marmic M4 profile after the preceding corrected run is collected.
- Compare all candidate series and create the Matthews-intended versus
  empirically supported copy-count report. Do not remove stopped alternatives.
- Brief refinement, map generation, sequence-from-map comparison, the second
  checkpoint, reporting, and prototype hardening remain.

### Next exact starting point

Read this entry. Commit and push the validated sequential workflow increment
and monitor GitHub Actions. Retry corrected run
`gtd-m4-copy-20260813T150438Z-0d9c3ef5b905-1cc7e54a` only through the installed
wrapper; if terminal, collect and compare its 11 copy-two outcomes. After CI is
green and Marmic is reachable, deploy the checksum-reviewed tools and create a
new immutable M4 run from the retained parent evidence to qualify sequential
copy placement. Do not start refinement or discard any candidate before that
comparison.

## 2026-08-13T17:01:32Z - T11.4 typed copy-count reporting completed locally

### Discoveries

- The expected-versus-supported comparison can be built directly from the
  aggregate sequential transition JSONL. It must first verify contiguous copy
  numbers and exact parent-child identities; otherwise a superficially
  plausible count could hide a broken lineage.
- Checksum-gated deployment of green revision
  `e72522358e0a4f79c55359012ab3543c5fa68d22` reached the local wrapper but the
  Marmic SSH endpoint timed out before remote deployment. No deployed tool or
  retained-run state changed.

### Accomplishments

- Sequential workflow revision
  `e72522358e0a4f79c55359012ab3543c5fa68d22` was pushed; GitHub Actions run
  `31722338506` passed.
- Added the typed `CopyCountAssessment` contract and `mr copy-report` command.
  It validates full transition lineage, compares Matthews-intended and best
  supported counts, retains terminal LLG/TFZ/delta/packing/placement/execution
  evidence, and distinguishes an early stop from proof of copy absence.
- The report publishes checksum-bound JSONL, TSV, Markdown, and manifest files.
  Marmic M4 execution now creates and collects this report for every retained
  candidate automatically.
- The complete local gate passed with 327 unit, 56 contract, and 45 integration
  tests plus formatting, Ruff, strict mypy, schemas, public panel,
  documentation, actionlint, Nextflow syntax/stub/resume, and wrapper syntax.

### Immutable evidence

- Green sequential workflow: revision
  `e72522358e0a4f79c55359012ab3543c5fa68d22`, GitHub Actions run
  `31722338506`.
- Intended deployment hashes before the transfer failure: dispatcher
  `f69c0e65e5e72c6338256f25c48c2f00af79dcfb55db8e8138bfb2153c670198`,
  smoke job
  `00ae4980e0e2c6fc2ddba7ffa73e9ecfde5f3018598bc7129a0c99619a8ff667`,
  and recovery tool
  `0db4c5f3542ce4d387ac019e33717d5e405ac957efb216b05c52828a851808f4`.
  These were not installed because the connection timed out.
- Corrected copy-two run
  `gtd-m4-copy-20260813T150438Z-0d9c3ef5b905-1cc7e54a`, job `626475`, remains
  retained with unknown current remote state.

### Unresolved work

- Publish this T11.4 increment and monitor CI. When Marmic returns, collect the
  preceding corrected run, deploy tools from the newest green revision, and
  submit a new immutable sequential M4 run.
- Real evidence must qualify the sequential series and typed copy-count report
  before the roadmap advances to brief refinement.
- Brief refinement, maps, sequence-from-map search, the second review
  checkpoint, M5 reporting/pilot, and M6 validation/hardening remain.

### Next exact starting point

Read this entry, commit and push the T11.4 report increment, and monitor GitHub
Actions. Retry only the approved wrapper status for corrected run
`gtd-m4-copy-20260813T150438Z-0d9c3ef5b905-1cc7e54a`. When Marmic is reachable,
collect that run, deploy tools from the newest green commit, and launch a fresh
retained M4 run so every one of the 11 candidates receives sequential copy
placement and a copy-count assessment. Do not begin refinement until that
real-data evidence is terminal and inspected.

## 2026-08-13T17:09:07Z - T11.4 published; Marmic handoff retained

### Discoveries

- Marmic continued to time out during the post-CI wrapper status attempt. No
  new remote state is known and the retained run remains untouched.

### Accomplishments

- Published T11.4 revision
  `57e82853682ce76a8b83d9a3abd0002d88d8c0f4`; GitHub Actions run
  `31723743653` passed.
- Refreshed active 30-minute heartbeat
  `monitor-marmic-corrected-m4-copy`. It now records the green sequential/report
  revision and requires collection of corrected job `626475` before deploying
  the newest tools and launching a successor sequential M4 run.
- The worktree is clean.

### Immutable evidence

- Green publication chain: `a9ca0161a0b5ac5e51effe52daf569f8c64e846c`
  (`31719834027`), `e72522358e0a4f79c55359012ab3543c5fa68d22`
  (`31722338506`), and `57e82853682ce76a8b83d9a3abd0002d88d8c0f4`
  (`31723743653`).

### Unresolved work

- The remote collection/deployment/sequential-run boundary is unchanged because
  the Marmic login endpoint is unavailable. Real sequential placement and copy
  reporting remain unqualified until that run completes.
- Refinement, maps, sequence narrowing, second review, M5, and M6 remain after
  the real M4 evidence gate.

### Next exact starting point

Read this entry and follow heartbeat
`monitor-marmic-corrected-m4-copy`. Check only retained corrected run
`gtd-m4-copy-20260813T150438Z-0d9c3ef5b905-1cc7e54a` through the installed
wrapper. After terminal collection and evidence review, deploy tools from green
revision `57e82853682ce76a8b83d9a3abd0002d88d8c0f4`, stage/submit a new immutable
sequential M4 run using the retained 11-seed decision package, and create its
successor monitor. Do not begin refinement before that sequential evidence is
terminal and inspected.

## 2026-08-13T20:55:12Z - Viper cut-over implementation ready for publication

### Discoveries

- The collected retain-all P2 package contains exactly 11 entries with complete
  coordinate, MTZ, command, result, and log assets. Its historical manifest
  predates the explicit `inspectable_solution` field, so the fixed importer uses
  the checksum-bound coordinate-plus-MTZ inventory as the equivalent invariant.
- The first Viper database draft still inherited two Marmic assumptions: a
  distinct scratch filesystem and login-stage/database mutual exclusion. Viper
  needs non-overlapping roots on the same `/ptmp` filesystem for atomic rename,
  while database downloads and M4 can safely use separate managed locks.
- The user fixed the active Viper small-queue ceiling at 64 CPUs and 192 GB and
  explicitly chose login-node database downloads rather than a `datatransfer`
  Slurm job.

### Accomplishments

- Added site-aware controller and run records. Viper uses schema 1.1 with an
  explicit site ID; legacy records are Marmic-only and cannot cross the site
  boundary.
- Added a fixed `m4-import-stage` operation with no caller-supplied paths. A
  local dry run produced a 26,018,980-byte archive containing all 11 approved
  candidates and verified the immutable review, decision, and MTZ anchors.
- Cross-site M4 staging uses each first-copy solution coordinate as the next-copy
  rigid-body search model and records its new checksum separately from the
  original processed-model checksum. It retains all candidates independent of
  the preliminary numeric annotation.
- Added the pinned Viper profile and `/ptmp` work/cache/database layout. M4 uses
  seven concurrent 8-CPU/16-GB tasks; database build and full verification use
  at most 64 CPUs, 192 GB, and 24 hours. Source downloads remain a fixed,
  checksum-recorded login-node staging operation.
- Removed the obsolete distinct-filesystem invariant from database preflight,
  watchdog validation, and publication. Same-filesystem resource publication
  now uses atomic rename after complete inventory; cross-filesystem standalone
  use retains its checksum-verified copy path.
- Added a Viper runbook, rollback/site examples, Pixi 0.74.0/0.76.2 CI matrix,
  and historical labels for Marmic documentation. The Marmic monitor was stopped
  without cancelling or deleting retained remote job `626475`.

### Immutable evidence

- Authoritative migration parent remains P2-diverse run
  `gtd-p2-diverse-20260812T045236Z-5b5100e8651c-1f2fe41a`, commit
  `5b5100e8651cae0498ad2d6dd185bf8fb8fbbecb`, job `625935`.
- Review manifest SHA-256:
  `da0604426294602a23f441f6a1aea77ec564e9ef8b091ae588b9b861feef55c4`;
  decision SHA-256:
  `7bbe539cf3c02b253ee94d829af6cf0b516e8eecedc6c784ab12cd707d012e2c`;
  MTZ SHA-256:
  `5eb16c3cc3a21e4b7f22cd611834529801c1829fc0a3156a2b6abc2b3de2f20d`.
- The complete locked gate passed with 332 unit, 56 contract, and 45 integration
  tests plus format, Ruff, strict mypy, schemas, documentation, actionlint,
  Nextflow syntax/stub/resume, and wrapper syntax. The focused same-filesystem
  database regression set passed 77 tests.

### Unresolved work

- Commit and push this cut-over increment, require both Pixi CI matrix jobs to
  pass, then install checksum-reviewed tools and the mode-0600 Viper site config.
- Establish the Viper read-only Git deploy key and bare mirror without exposing
  the private key. Install and qualify Phenix 2.1-6048 at the fixed Viper prefix.
- Stage and submit the immutable 11-candidate sequential M4 run, create its
  30-minute Viper monitor, and start the independent login-download/database
  build track. Real Viper results are not yet claimed.
- After M4 collection and copy-report inspection, proceed directly to T12 brief
  refinement, maps, and sequence narrowing for scientifically viable retained
  alternatives; then M5 and M6 remain.

### Next exact starting point

Read this entry. Publish the Viper cut-over commit and monitor both GitHub
Actions Pixi versions. After green CI, preserve the current Marmic controller
configuration, install the Viper schema-1.1 configuration and reviewed tools,
bootstrap read-only Git and Phenix, then run `m4-import-stage` from the frozen
11-candidate parent. Submit M4 with the 64-CPU/192-GB ceiling and create a
30-minute Viper monitor. Start database downloads through `database-stage` on
the login node without waiting for M4, then submit the fixed compute build.

## 2026-08-13T21:25:00Z - Viper bootstrap found canonical `/ptmp` alias

### Discoveries

- GitHub Actions run `31743495911` completed successfully for cut-over commit
  `458af18a95ee5950719883ecc03b6444795a8e63` under both Pixi 0.74.0 and
  0.76.2.
- On Viper, the reviewed lexical `/ptmp/USERNAME/...` path resolves to the
  site's canonical `/viper/ptmp1/USERNAME/...` mount. The database guard's
  former exact-string realpath check therefore rejected a valid site path even
  though the final components were owned, non-symlinked, and contained below
  the intended root.
- Viper's fixed Pixi executable is present and reports 0.76.2. The stable Phenix
  prefix is not present yet, so Phenix installation and real-MTZ qualification
  remain a separate prerequisite for imported M4 execution.

### Accomplishments

- Preserved the Marmic controller configuration separately, installed the
  green immutable local controller, and activated a site-ID-isolated Viper
  configuration. Client wait bounds remain schema-valid; they do not shorten
  Viper's 24-hour Slurm job limit or introduce an adapter runtime timeout.
- Created the fixed Viper `/ptmp` run/cache/database layout and tool directory.
  Registered a Viper-only read-only GitHub deploy key without exposing its
  private half, installed GitHub's official Ed25519 host key, verified
  fingerprint `SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU`, and
  cloned the private bare mirror through the dedicated alias.
- Installed the reviewed dispatcher, Slurm job script, and recovery tool, then
  independently verified their SHA-256 values. Installed mode-0600 site, Pixi,
  and database policies outside Git. Database downloads remain login-local and
  no `datatransfer` job has been introduced.
- Updated database readiness to validate the reviewed lexical mount alias and
  its canonical target independently. It still rejects symlinked final
  components, non-owned targets, paths outside either boundary, unsafe roots,
  and configuration drift. Added a regression test that models Viper's
  canonical mount alias.

### Immutable evidence

- Green bootstrap source commit:
  `458af18a95ee5950719883ecc03b6444795a8e63`; GitHub Actions run:
  `31743495911`.
- Bootstrap tool SHA-256 values: dispatcher
  `9077e5e7416c07682a145d7e218627249ca75d935693816106428ac62b55063c`,
  job script
  `0cf395e1111b1c87935618d9c2b6e54a5af689b222c3591cfe5d5ee5a8d0fe8e`,
  recovery tool
  `0db4c5f3542ce4d387ac019e33717d5e405ac957efb216b05c52828a851808f4`,
  and local controller
  `235c5770beb4d9f8a19b80e3d47efcce6fab1e82b66379a3845a86150645353d`.
- The compatibility increment passed the complete locked gate: 332 unit, 56
  contract, and 46 integration tests plus formatting, Ruff, strict mypy,
  schemas, public controls, documentation links, actionlint, Nextflow
  syntax/stubs, and wrapper syntax.

### Unresolved work

- Commit and publish the canonical-mount compatibility fix, require both Pixi
  CI jobs to pass, then checksum-deploy the updated dispatcher.
- Re-run Viper database readiness. Do not begin the large login-node downloads
  unless the fixed boundary reports ready.
- Install and qualify Phenix 2.1-6048 on Viper. Then stage the frozen
  11-candidate M4 import, submit the sequential run, and create its 30-minute
  monitor. The database track remains concurrent and must not delay M4.

### Next exact starting point

Read this entry. Publish the two-file canonical-mount fix and monitor GitHub
Actions. After green CI, deploy the exact updated tools through the reviewed
controller, verify database readiness, and start the fixed login-local database
stage. In parallel, transfer and scheduled-install the checksum-pinned Phenix
installer; after real-MTZ qualification, execute `m4-import-stage`, submit M4,
and create a successor Viper monitor.

## 2026-08-13T22:02:00Z - Viper source staging path guard corrected

### Discoveries

- Viper database readiness became green after deployment of commit
  `dd583bc3d43af5982189d07eb1dd6fcfef75d183`, but the first immutable source
  stage stopped before downloading with `transfer_failure`. The owned run is
  `gtd-database-20260813T214925Z-dd583bc3d43a-53b38876`; it is terminal
  `stage_failed` and has no Slurm job ID.
- Its bounded structured log reports `database_root must be canonical and
  narrowly scoped`. The independent Python source/preflight layer still
  required lexical equality with `Path.resolve()`, so Viper's site-managed
  `/ptmp` ancestor alias was rejected after the dispatcher itself had been
  corrected.

### Accomplishments

- Updated the source-stage root and manifest-parent checks, compute preflight
  root checks, and preparation scratch check to accept a symlink only in an
  ancestor supplied by the site mount namespace. The configured final database
  and scratch directories must remain existing non-symlink directories;
  canonical targets remain the basis for broad-root, overlap, capacity, and
  ownership safety decisions.
- Added a unit regression that stages the fixed source set through a `/ptmp`
  alias to a canonical mount. The broader source/preflight/database unit set
  passed 72 tests.

### Immutable evidence

- Green dispatcher compatibility commit:
  `dd583bc3d43af5982189d07eb1dd6fcfef75d183`; GitHub Actions run
  `31746971702` passed both Pixi 0.74.0 and 0.76.2 jobs.
- Deployed dispatcher SHA-256:
  `b0b6767b1f8491622dfddfcc8c0c74f0755850cc58e79df66405607547d47766`.
- Failed source-stage evidence is retained in run
  `gtd-database-20260813T214925Z-dd583bc3d43a-53b38876`; structured failure
  class `transfer_failure`, phase `stage_failed`, scheduler state `FAILED`, and
  no job ID. No database source download or compute submission occurred.
- The production-path correction passed the full locked gate: 333 unit, 56
  contract, and 46 integration tests plus all repository aggregate checks.

### Unresolved work

- Publish the Python path-guard correction and require both CI matrix jobs to
  pass. Deploy the exact green tools and retry database staging as a new
  immutable run; retain the failed run untouched.
- Phenix is still absent from its Viper stable prefix. Transfer the verified
  installer, install through the fixed scheduled resource profile, qualify the
  commands and real MTZ, then stage/submit imported M4 and create its monitor.

### Next exact starting point

Read this entry. Commit and push the database Python path-guard correction,
monitor GitHub Actions, deploy the exact green revision, then retry
`database-stage` on the login node. If staging completes, submit the separate
64-CPU/192-GB offline database build. Continue Phenix installation and M4 import
in parallel without waiting for database completion.

## 2026-08-14T00:18:00Z - Viper database build submitted and Phenix staged

### Discoveries

- The corrected source stage completed the fixed download set successfully.
  The Foldseek PDB archive was 2,326,827,389 bytes; source logging preserved the
  requested URL and its resolved Steinegger Lab S3 URL. The Viper filesystem
  reported approximately 4.79 PB free, so the 1.6-TB required-capacity gate is
  comfortably satisfied without raising the 2.0-TB project safety ceiling.
- The user-selected stable Phenix prefix `phenix_v2.1-6048` was documented but
  the installer guard accepted only the older `phenix-2.1-6048` spelling. This
  was detected before installation; no alternate tree or symlink was created.

### Accomplishments

- Database source staging completed as immutable run
  `gtd-database-20260813T220325Z-d689a7e7a65e-6e72920c` at commit
  `d689a7e7a65ece1d3694b7531f97c452b8675a60` with nf-helper revision
  `ed7b71caccbb8244e6d1f3ff42eaa8680728e43a` and Pixi 0.76.2. Downloads ran
  on the Viper login node; no datatransfer job was used.
- Submitted the independent offline database build as Slurm job `10910110` with
  the reviewed 64-CPU, 192-GB, 24-hour ceiling. Initial structured state was
  `PENDING`; the run remains immutable and is covered by a 30-minute heartbeat.
- Transferred the 3,610,320,749-byte licensed Phenix installer resumably to the
  fixed Viper `/ptmp` location. Its Viper SHA-256 exactly matches
  `a2455e281f11241debdb25d9788ada8337420b9ff4c92935f97157f0cc9b9795`.
  Installation has not started.
- Extended the installer prefix guard to accept exactly the established
  `phenix-<version>` or `phenix_v<version>` versioned forms. The requested
  stable prefix now passes all 14 focused installer tests.

### Immutable evidence

- Database path-fix commit `d689a7e7a65ece1d3694b7531f97c452b8675a60`
  passed GitHub Actions run `31747988081` under Pixi 0.74.0 and 0.76.2.
- Database run `gtd-database-20260813T220325Z-d689a7e7a65e-6e72920c` and job
  `10910110` retain source, lock, site, Pixi, nf-helper, and commit provenance.
- The prefix compatibility increment passed the complete locked gate: 334 unit,
  56 contract, and 46 integration tests plus all aggregate validations.

### Unresolved work

- Publish the Phenix prefix increment and require both CI jobs to pass. Then use
  its immutable checkout for the scheduled 4-CPU/32-GB Phenix installation and
  preserve controller, installer, and verification logs.
- Qualify the installed runtime with all command probes and real CD6 MTZ
  execution. Only then create the fixed 11-candidate M4 import, submit its
  sequential run, and create a separate 30-minute monitor.
- The database job remains independent; handle its terminal evidence through
  the existing monitor without delaying Phenix or M4.

### Next exact starting point

Read this entry. Commit and push the two-file Phenix prefix increment, monitor
both GitHub Actions jobs, then schedule the checksum-pinned installation to
`phenix_v2.1-6048` with 4 CPUs and 32 GB using `/ptmp` temporary storage. After
manifest and real-MTZ qualification, run `m4-import-stage`, submit the 11-seed
sequential M4 profile, and create its successor heartbeat.

## 2026-08-14T00:40:00Z - Viper `/u` file quota blocks Phenix runtime

### Discoveries

- Phenix job `10910201` failed after 49 seconds with exit code 1 while extracting
  the main Phenix conda package. The controller had already verified the full
  3,610,320,749-byte installer and its expected SHA-256. Slurm measured only
  about 0.32 GB MaxRSS, so CPU and memory were not limiting.
- The official GPFS quota command reports only about 58 GB used against the
  1-TB `/u` byte quota, but exactly 262,144 files against its 262,144-file hard
  limit. The preserved partial Phenix tree occupied 9.7 GB and 148,413 entries;
  existing Miniforge and cache trees account for about 78,760 and 23,101 entries.
  The generic `quota` command misleadingly reported no quota.
- Viper's official storage policy applies no quota to `/ptmp`, but `/ptmp` is
  unbacked and files not accessed for more than 12 weeks may be removed. A Phenix
  runtime there is suitable for the prototype only with installer/checksum
  retention and explicit ageing/reinstallation guidance.

### Accomplishments

- Preserved bounded controller and official-installer logs, exact checksums,
  Slurm accounting, tree size, and file-count evidence for failed job
  `10910201`. The exact failed partial tree was then removed from `/u` to release
  its exhausted file quota; that tree is not recoverable, while all diagnostic
  evidence and the licensed installer remain.
- Updated the active Viper layout to place the Phenix runtime below the fixed
  `/ptmp` project root while retaining its small manifest and logs under `/u`.
  No mutable current link is introduced.

### Immutable evidence

- Failed job `10910201`: state `FAILED`, exit `1:0`, elapsed 49 seconds,
  allocated CPUs 8 due to the queue allocation granularity, batch MaxRSS
  308,952 KB. Submitted script SHA-256:
  `52076dd46daa018132acda20277ddaf4cc68fadc87fcd093244d3820683252d6`.
- Installer SHA-256 remained
  `a2455e281f11241debdb25d9788ada8337420b9ff4c92935f97157f0cc9b9795`.
  The failure is classified operationally as filesystem quota exhaustion, not
  installer corruption.

### Unresolved work

- Publish and CI-validate the `/ptmp` runtime location update, then submit one
  corrected scheduled installation. Verify quota recovery before submission.
- After successful command and real-MTZ qualification, execute the fixed M4
  import/submit path. Database job `10910110` remains independently monitored.

### Next exact starting point

Read this entry. Run locked checks, commit and push the Viper Phenix storage
correction, and require both CI jobs. Verify `/u` file quota is below its hard
limit. Submit one checksum-pinned installation to
`/ptmp/USERNAME/nf-genome_to_diffraction/software/phenix_v2.1-6048`, retaining
manifest/logs under `/u`; then qualify commands and real CD6 MTZ before M4.

## 2026-08-13T22:44:48Z - Corrected Viper Phenix retry submitted

### Discoveries

- After removal of only the failed partial Phenix tree, the official Viper `/u`
  quota fell from 262,144 to 113,731 files and from about 58 GB to about 48 GB.
  The small durable manifest/log area therefore has sufficient headroom again.
- Viper's small/default queue allocated eight CPUs to the first job despite the
  four-CPU request; this is queue granularity, not an increase in the requested
  application parallelism. The corrected job retains the same four-CPU request.

### Accomplishments

- CI run `31750581075` passed under Pixi 0.74.0 and 0.76.2 for the documented
  `/ptmp` runtime correction at commit
  `8b888c5686a8325337ad231d0bcdbb0abf8d4db0`.
- Preserved the first official installer log under failed job ID `10910201`.
  Created a detached checkout of the green correction and installed its frozen
  HPC Pixi environment on the login node.
- Submitted corrected Slurm job `10910267` from checksum-reviewed script
  `viper-phenix-install-8b888c5.slurm`. It targets
  `/ptmp/USERNAME/nf-genome_to_diffraction/software/phenix_v2.1-6048`, keeps
  manifest/logs under `/u`, creates no current link, and has initial state
  `PENDING`. The combined 30-minute heartbeat now monitors this job and the
  independent database job.

### Immutable evidence

- Corrected script SHA-256:
  `df775cbffa848822944221f265147b4ca00b1d545b9a2bdca5a521097a690395`;
  installer SHA-256:
  `a2455e281f11241debdb25d9788ada8337420b9ff4c92935f97157f0cc9b9795`;
  source commit: `8b888c5686a8325337ad231d0bcdbb0abf8d4db0`.
- Failed predecessor job `10910201` remains represented by Slurm accounting,
  bounded controller and installer logs, script/installer checksums, and the
  recorded 9.7-GB/148,413-entry partial-tree measurements. Only the failed
  partial tree itself was removed, and it is not recoverable.

### Unresolved work

- Await job `10910267` without timeout inference. On success, verify the
  manifest and all command probes, then run real CD6 MTZ qualification through
  that manifest. On failure, preserve its bounded log evidence before deciding
  any action.
- Database job `10910110` remains independently monitored. It must not delay
  Phenix qualification or the subsequent fixed M4 import.
- After Phenix qualification, stage and submit all 11 retained M4 candidates
  and update the heartbeat to monitor that sequential run.

### Next exact starting point

Read this entry and follow heartbeat `monitor-viper-database-build`. Check
database run `gtd-database-20260813T220325Z-d689a7e7a65e-6e72920c` only through
the approved wrapper and Phenix job `10910267` only through the fixed bounded
scheduler commands. Leave non-terminal jobs untouched. After Phenix terminal
success, qualify commands and real CD6 MTZ, then immediately execute the fixed
M4 import/submit path without waiting for database completion.

## 2026-08-13T23:02:00Z - Phenix create-only log collision cleared

### Discoveries

- Corrected `/ptmp` job `10910267` failed safely after 16 seconds, before any
  installation, because the installer correctly refused to replace the base
  install log left by failed predecessor `10910201`. Slurm recorded exit 1 and
  batch MaxRSS 162,545 KB. The installer checksum passed again.
- Both the corrected `/ptmp` prefix and create-only manifest remained absent, so
  no partial runtime or false installation record required recovery.

### Accomplishments

- Preserved the original base install log under a unique predecessor-job name.
  Resubmitted the unchanged checksum-reviewed `/ptmp` script as job `10910306`;
  no code, resource, prefix, checksum, or scientific parameter changed.
- Updated the combined 30-minute heartbeat to monitor job `10910306` and the
  independent database job while preserving both predecessor failure records.

### Immutable evidence

- Job `10910267`: `FAILED`, exit `1:0`, elapsed 16 seconds, batch MaxRSS
  162,545 KB, allocated CPUs 8. Bounded log reason: create-only refusal to
  replace `phenix-2.1-6048.install.log`.
- Active successor `10910306` uses script SHA-256
  `df775cbffa848822944221f265147b4ca00b1d545b9a2bdca5a521097a690395`,
  installer SHA-256
  `a2455e281f11241debdb25d9788ada8337420b9ff4c92935f97157f0cc9b9795`,
  and green source commit `8b888c5686a8325337ad231d0bcdbb0abf8d4db0`.

### Unresolved work

- Await job `10910306` without inferring failure from silence. Qualify all
  commands and the real CD6 MTZ only after terminal success.
- Continue the fixed M4 import immediately after Phenix qualification; database
  job `10910110` remains independent.

### Next exact starting point

Read this entry and follow heartbeat `monitor-viper-database-build`. Check
Phenix job `10910306` and database run
`gtd-database-20260813T220325Z-d689a7e7a65e-6e72920c` only through their fixed
bounded interfaces. Leave non-terminal jobs untouched. On Phenix success,
qualify the manifest and real CD6 MTZ, then stage/submit all 11 M4 candidates.

## 2026-08-14T00:05:00Z - Database allocation reduced before execution

### Discoveries

- Database job `10910110` was still pending and had consumed no compute time.
  Its 64-CPU/192-GB request was an unmeasured ceiling rather than a minimum.
- The fixed inputs are prebuilt Foldseek PDB and ProstT5 archives. The main
  constructed search resource is the PDB-SEQRES MMseqs index, so a large-memory
  allocation is not justified before observing terminal MaxRSS.

### Accomplishments

- Cancelled only pending job `10910110`, preserving its immutable run and staged
  source bundle. Changed the fixed database job to 8 CPUs, 32 GB, and 24 hours;
  the long wall-time margin is retained for shared-filesystem I/O.
- Updated integration/contract assertions and active Viper documentation. M4's
  separate 64-CPU/192-GB site ceiling and seven concurrent Phaser tasks remain
  unchanged.

### Immutable evidence

- The approved controller reported `CANCEL_REQUESTED` for job `10910110`.
- Contract tests passed 56/56, the integration suite passed, documentation links
  passed, and `git diff --check` was clean before commit.

### Unresolved work

- Commit, push, require green CI, deploy checksum-reviewed tools, and create a
  fresh database run using 8 CPUs/32 GB. Use its MaxRSS to decide whether even
  less memory is defensible or a measured increase is necessary.
- Phenix job `10910306` remains independent and must be left untouched while
  non-terminal. After qualification, continue M4 without waiting for databases.

### Next exact starting point

Complete the focused resource-right-sizing development cycle. Then stage and
submit one new immutable database run through the fixed wrapper and update the
existing heartbeat to replace cancelled job `10910110` with its successor.

## 2026-08-14T00:22:00Z - Right-sized database launch exposed mount alias

### Discoveries

- Green resource commit `1d7601fe4b422da7379c714aa5a03dd4b0c2c81e`
  was deployed and successor job `10910414` reached a compute node, then failed
  safely in four seconds with exit 2 and negligible memory use.
- The failure preceded Pixi and database preparation: Viper resolves the
  documented `/ptmp` alias to a different physical mount path on compute nodes,
  while the job body still required lexical and physical roots to be identical.
  The dispatcher already handled this site behaviour.

### Accomplishments

- Preserved the failed run and its bounded log. Extended the job's path guard to
  accept an alias only for an immutable run explicitly recorded as `viper-cpu`,
  and only when the resolved path preserves the exact suffix beneath the fixed
  run root. Arbitrary aliases and non-Viper noncanonical roots remain rejected.
- Added an integration regression that executes the database job through an
  aliased run root, plus contract assertions for the site-ID boundary.

### Immutable evidence

- Job `10910414`: `FAILED`, exit `2`, elapsed four seconds; bounded diagnostic
  was `managed run root is not canonical`. This is wrapper failure evidence,
  not evidence that 8 CPUs or 32 GB is insufficient.
- Contract tests passed 56/56, integration tests passed, and the fixed Bash job
  passed syntax validation after the correction.

### Unresolved work

- Complete checks, commit, push, require both Pixi CI jobs green, deploy the new
  tool checksums, and stage a fresh 8-CPU/32-GB database run. Preserve jobs
  `10910110` and `10910414`.
- Continue independent Phenix monitoring and proceed to M4 on qualification.

### Next exact starting point

Finish the focused Viper mount-alias regression cycle, then submit one fresh
right-sized database run and replace job `10910414` in the existing heartbeat.

## 2026-08-14T00:31:00Z - Corrected minimal database run submitted

### Discoveries

- The bounded Viper alias correction passed the complete local gate and both
  supported Pixi versions in GitHub Actions; no further wrapper fallback was
  needed.

### Accomplishments

- Deployed green commit `0aac8b16f0dc66bf2ce5e15de7fd7ccaf5f163f6`
  with dispatcher SHA-256
  `6de30d69147e9dbbe727d67d7baa73a962a45feb6a9914a188a5626e77c579b0`
  and job-wrapper SHA-256
  `d8873923b6aa67981c66016c92ba9ca71e7d0b440e8704b258109416b1f1efe9`.
- Staged and submitted right-sized database run
  `gtd-database-20260813T232453Z-0aac8b16f0dc-90fd140f` as Slurm job
  `10910484`. Its initial state is `PENDING` with 8 CPUs, 32 GB, and 24 hours.
- Updated the existing 30-minute heartbeat to monitor this successor and the
  independent Phenix installation while retaining all predecessor evidence.

### Immutable evidence

- GitHub Actions run `31753440627` passed under Pixi 0.74.0 and 0.76.2.
- The staged run records nf-helper revision
  `ed7b71caccbb8244e6d1f3ff42eaa8680728e43a` and Pixi 0.76.2.

### Unresolved work

- Leave database job `10910484` untouched while non-terminal. On completion,
  collect full provenance and use MaxRSS to assess the minimal allocation.
- Continue independent Phenix qualification and launch imported M4 immediately
  after it succeeds; database completion must not block M4.

### Next exact starting point

Follow heartbeat `monitor-viper-database-build`. Check the database only through
the fixed wrapper and Phenix only through its bounded scheduler query. Do not
infer failure from silence or modify either non-terminal job.

## 2026-08-14T00:42:00Z - Viper databases built with measured small footprint

### Discoveries

- Database job `10910484` completed the build, functional qualification, and
  anchored full verification in 2m45s. Slurm measured 3.266 GB maximum memory
  per node and 1.7% CPU utilisation under an 8-CPU/32-GB request.
- The final resource set occupies 15,919,134,898 bytes, far below the safety
  capacity ceiling. Thus the prior 64-CPU/192-GB request was unnecessary, and
  even 8 CPUs/32 GB retained substantial unused capacity.

### Accomplishments

- Collected the complete approved evidence package. All four resources are
  ready and smoke-qualified: Foldseek PDB, PDB SEQRES/MMseqs, ProstT5, and the
  content-addressed coordinate cache. Full verification reused every immutable
  resource and preserved source, version, inventory, and checksum provenance.
- Set future fixed database rebuilds to 4 CPUs and 8 GB, retaining the 24-hour
  shared-I/O margin. No repeat database build is scientifically or operationally
  necessary; the current verified resources remain authoritative.

### Immutable evidence

- Run `gtd-database-20260813T232453Z-0aac8b16f0dc-90fd140f`, job `10910484`:
  `COMPLETED`, exit 0, success, 2m45s. Manifest ID is
  `dbm_af289054ab487b181f9bf10e6468478361af991883b0a762e38a14c69d4d58fa`.
- Full-verified manifest SHA-256 is
  `04e138e4b9781490fc6ac2cf08652b5d1a15f51828d828c2b4e42f0bc4d4c1d8`;
  source-bundle SHA-256 is
  `62406488ba5a6f1aee68acf35b66fee5a9a06d8e749e9d29b6b40bd4a33be165`.
- Foldseek 10.941cd33 and MMseqs2 18.8cc5c were recorded. The PDB Foldseek
  snapshot is 2025-01-01 at provider commit
  `1815f0d76d7b5807e63b13f9d446dcef43c1f3b1`; PDB SEQRES contains 1,084,311
  protein records and passed the known ubiquitin search.

### Unresolved work

- Complete checks and CI for the evidence-based future resource reduction; do
  not rerun the already successful database build solely to test the smaller
  ceiling.
- Remove the terminal database run from the heartbeat after its documentation
  milestone is green. Continue Phenix qualification and launch M4 immediately
  when Phenix succeeds.

### Next exact starting point

Finish the focused 4-CPU/8-GB policy cycle. Then update the heartbeat to monitor
only Phenix job `10910306`; the database track is complete and must not block M4.

## 2026-08-14T02:40:00Z - Phenix installed and imported M4 submitted on Viper

### Discoveries

- Phenix install job `10910306` completed with exit 0 in 12m24s and used about
  2.28 GB MaxRSS. The fixed imported-M4 staging path accepted its site manifest,
  but full qualification remains contingent on the scheduled real-CD6 command
  verification and molecular-replacement execution.
- The first imported-M4 stage revealed two operational cut-over defects: its
  diagnostic log was not collectable, and imported solution-coordinate
  provenance mixed Viper's lexical `/ptmp` path with its physical
  `/viper/ptmp1` mount. Neither defect changed candidate data or scientific
  policy.
- The first otherwise-valid Viper submission was rejected before execution
  because the dispatcher still requested Marmic's `41-16:00:00` walltime.
  Viper requires a runtime no greater than 24 hours.

### Accomplishments

- Added the bounded `m4-import-stage.log` to the approved collection inventory,
  fixed cross-site model provenance to use a canonical owned staging root, and
  covered the mount alias with a regression fixture.
- Replaced the inherited multi-day request for real-data profiles with Viper's
  `24:00:00` maximum without increasing CPUs or memory. All focused corrections
  completed the code, locked-Pixi test, commit, push, dual-CI, and
  checksum-reviewed deployment cycle.
- Staged exactly 11 retained candidates and submitted immutable run
  `gtd-m4-copy-20260814T003459Z-add9a1a2a724-77bef3bf` as Slurm job `10910784`.
  Its current scheduler state is `PENDING`; leave it untouched.

### Immutable evidence

- Active source commit is `add9a1a2a724843454961b1133cefc3e7b422f39`;
  GitHub Actions run `31757539962` passed under Pixi 0.74.0 and 0.76.2.
- Import archive SHA-256 is
  `da0584c2be7c549c8d86d7d248b127e652c174937b14cc0c4273fb94679e6096`;
  decision SHA-256 is
  `7bbe539cf3c02b253ee94d829af6cf0b516e8eecedc6c784ab12cd707d012e2c`;
  review-manifest SHA-256 is
  `da0604426294602a23f441f6a1aea77ec564e9ef8b091ae588b9b861feef55c4`.
- Frozen CD6 MTZ SHA-256 is
  `5eb16c3cc3a21e4b7f22cd611834529801c1829fc0a3156a2b6abc2b3de2f20d`;
  nf-helper revision is `ed7b71caccbb8244e6d1f3ff42eaa8680728e43a` and
  the staged Pixi version is 0.76.2.
- Retain failed staging runs ending `eb6a8d2e` and `31e90d56`, plus the staged
  submission-rejection run ending `39fdb7fb`; they delimit the corrected path
  and scheduler contracts and must not be cleaned automatically.

### Unresolved work

- Wait for job `10910784` without inferring failure from silence. On terminal
  state, collect the bounded Phenix verification, all 11 candidate series,
  copy transitions, raw results, checksums, and fully cached resume evidence.
- Claim Phenix qualification only if its stable manifest command probes and
  real frozen-CD6 execution pass. Then proceed directly to the smallest T12
  refinement/maps/sequence-narrowing increment with all viable alternatives.

### Next exact starting point

Follow the updated 30-minute heartbeat. Check only
`gtd-m4-copy-20260814T003459Z-add9a1a2a724-77bef3bf` through the fixed wrapper;
do not poll databases, use raw SSH, cancel, clean, or retune the candidate gate.

## 2026-08-14T02:58:00Z - Self-contained Viper M4 successor submitted

### Discoveries

- M4 job `10910784` failed before Phenix verification with the bounded message
  `fixed P0 configuration is absent or unsafe`. The imported M4 stage already
  carries checksum-bound hypotheses, sequence groups, preflight, MTZ, Phenix
  manifest, review decisions, and all models, so requiring legacy P0 site paths
  was an obsolete environment precondition.

### Accomplishments

- Removed only the P0-config loader call from the self-contained M4 job and
  added a contract assertion preventing its return. Contract tests passed
  56/56 and the fixed Bash wrapper passed syntax validation.
- Committed and pushed `001d791649d0ed942ab4b7136f158adaa67b2b57`;
  GitHub Actions run `31758472426` passed under Pixi 0.74.0 and 0.76.2.
- Deployed job-wrapper SHA-256
  `6a36dab597e27cf96f05c675970d44b8754e04138701eda6d6862f8ee70f73ec`,
  staged all 11 candidates again, and submitted corrected run
  `gtd-m4-copy-20260814T005058Z-001d791649d0-2fc95156` as Slurm job
  `10910824`. Its current state is `PENDING`.

### Immutable evidence

- Failed predecessor `gtd-m4-copy-20260814T003459Z-add9a1a2a724-77bef3bf`,
  job `10910784`, is retained with failure signature
  `ab0405409dee57422ed5778d97cefe7d4077d4fd643bd97c8296474daa05416d`.
  It did not execute Phenix and is not scientific failure evidence.
- Successor import archive SHA-256 is
  `bb5aaa099730b205ab065fbac799c1e3dea4deaccb46abe14e1c80d5c0ac1b62`;
  its decision, review-manifest, MTZ, nf-helper, and Pixi provenance match the
  preceding accepted import.

### Unresolved work

- Leave job `10910824` untouched while non-terminal. Full Phenix qualification
  still requires its manifest probes and real frozen-CD6 execution to pass.
- On terminal success, collect all 11 sequential copy series and cached-resume
  evidence, then begin the smallest T12 refinement/maps/sequence-narrowing step.

### Next exact starting point

Follow the updated 30-minute heartbeat and check only run
`gtd-m4-copy-20260814T005058Z-001d791649d0-2fc95156` through the fixed wrapper.

## 2026-08-14T07:06:00Z - Viper controller guard corrected and M4 relaunched

### Discoveries

- Run `gtd-m4-copy-20260814T005058Z-001d791649d0-2fc95156`, Slurm job
  `10910824`, ended as `test_failure` before molecular replacement because
  nf-helper's Viper launch guard recognised only the login hosts and rejected
  the scheduled Nextflow controller host `vipc2547`.
- The same bounded evidence verified all seven Phenix command probes against
  `/viper/ptmp1/ashima/nf-genome_to_diffraction/software/phenix_v2.1-6048`.
  This proves command-level installation health, but not yet real-CD6
  molecular-replacement qualification because Nextflow stopped before any
  scientific process ran.

### Accomplishments

- Kept login-host enforcement as the default and added a narrow managed-compute
  exception: `vipc[0-9]+` is accepted only with a numeric `SLURM_JOB_ID` and the
  fixed wrapper's `NF_HELPER_VIPER_COMPUTE_CONTROLLER=managed-slurm` marker.
  Unmanaged compute launches still fail loudly.
- nf-helper's four Viper profile tests passed through the parent locked
  environment; direct managed and unmanaged Nextflow evaluations passed, the
  parent contract suite passed 56/56, and the fixed M4 Bash wrapper passed
  syntax validation. A fresh standalone nf-helper Pixi installation could not
  resolve packages under sandbox DNS, so no claim is made for that redundant
  installation path.
- Pushed nf-helper commit `82431e4c56cb4cd2ef4ea67321fd01fad7ba65cb`
  and parent commit `dc3c545a0cd616ca97b6cb9d5d75b6176370d987`.
  GitHub Actions run `31778155576` passed under Pixi 0.74.0 and 0.76.2.
- Deployed dispatcher SHA-256
  `fe1059bf857a17bec29a50aff25008f36aa43a646f36c956690432a428d27799`,
  staged all 11 retained candidates, and submitted immutable successor
  `gtd-m4-copy-20260814T070304Z-dc3c545a0cd6-98156a5d` as Slurm job
  `10911920`. Its first observed scheduler state was `RUNNING`.

### Immutable evidence

- Failed predecessor job `10910824` is retained with failure signature
  `d98ef01185f144777408f8dc38aad04f0a3e4861bc8290ba13ce2a914bd48bbf`.
  It is controller-configuration evidence, not a negative scientific result.
- Successor import archive SHA-256 is
  `9735673e9b51b111185881d2086c8f70bbf1982cdfd151b497e6dc0e10d026a0`;
  decision SHA-256 is
  `7bbe539cf3c02b253ee94d829af6cf0b516e8eecedc6c784ab12cd707d012e2c`;
  review-manifest SHA-256 is
  `da0604426294602a23f441f6a1aea77ec564e9ef8b091ae588b9b861feef55c4`;
  frozen MTZ SHA-256 is
  `5eb16c3cc3a21e4b7f22cd611834529801c1829fc0a3156a2b6abc2b3de2f20d`.

### Unresolved work

- Leave job `10911920` untouched while non-terminal. On terminal state,
  collect and verify exactly 11 sequential candidate outcomes, raw Phaser
  evidence, model derivation and complete provenance, plus a fully cached
  resume pass.
- Claim full Viper Phenix qualification only after real frozen-CD6 molecular
  replacement succeeds. Then continue directly to T12 refinement, maps, and
  sequence narrowing for every scientifically viable retained alternative.

### Next exact starting point

Follow the updated 30-minute heartbeat. Check only
`gtd-m4-copy-20260814T070304Z-dc3c545a0cd6-98156a5d` through the fixed wrapper;
do not poll databases, use raw SSH, cancel, clean, drop candidates, or infer a
timeout from silence.

## 2026-08-14T07:20:00Z - Fixed Viper container cache propagated to M4

### Discoveries

- Job `10911920` passed the corrected managed-controller guard and all seven
  Phenix command probes, then stopped before molecular replacement because the
  immutable Slurm wrapper had not exported the approved Viper Apptainer cache.
  nf-helper therefore rejected the profile with the explicit request for
  `NXF_APPTAINER_CACHEDIR`.
- The failure signature remained
  `d98ef01185f144777408f8dc38aad04f0a3e4861bc8290ba13ce2a914bd48bbf`
  because both failures ended at Nextflow configuration parsing. The bounded
  causal exception distinguishes this missing cache setting from the preceding
  host-guard rejection. No Phaser candidate executed in either run.

### Accomplishments

- Exported the fixed site path `/ptmp/ashima/apptainer-cache` immediately before
  Nextflow profile evaluation in the immutable M4 wrapper and added a contract
  assertion. Candidate retention, scores, resources, and scientific behaviour
  are unchanged.
- The focused contract suite passed 56/56, Bash syntax validation passed, and
  the complete `pixi run --locked check` suite passed. Parent commit
  `72bf37746bb3dad70678bf4fa8eaf6ba7471903e` and GitHub Actions run
  `31779137987` passed under Pixi 0.74.0 and 0.76.2.
- Deployed fixed job-wrapper SHA-256
  `4d52581c7b5a830f70efd9fcd295afb77c90f13259be735721b9926183c6c2a0`,
  imported all 11 candidates again, and submitted successor
  `gtd-m4-copy-20260814T071851Z-72bf37746bb3-44f56209` as Slurm job
  `10912594`. Its first observed scheduler state was `PENDING`.

### Immutable evidence

- Retained failed run `gtd-m4-copy-20260814T070304Z-dc3c545a0cd6-98156a5d`,
  job `10911920`, contains the valid Phenix probe log and bounded Nextflow
  exception proving that execution stopped before any scientific task.
- Successor import archive SHA-256 is
  `51a0724d2ae62f186d15d89d93df13f0719c62c38854a7b51a697b95298c6c6f`;
  decision SHA-256 is
  `7bbe539cf3c02b253ee94d829af6cf0b516e8eecedc6c784ab12cd707d012e2c`;
  review-manifest SHA-256 is
  `da0604426294602a23f441f6a1aea77ec564e9ef8b091ae588b9b861feef55c4`;
  frozen MTZ SHA-256 remains
  `5eb16c3cc3a21e4b7f22cd611834529801c1829fc0a3156a2b6abc2b3de2f20d`.

### Unresolved work

- Leave job `10912594` untouched while non-terminal. It is the first successor
  carrying both the managed-controller marker and fixed shared container cache.
- Full Phenix qualification still requires real-CD6 molecular replacement,
  exactly 11 typed sequential outcomes, and a fully cached resume. After that
  evidence is collected, continue directly to T12 for all viable alternatives.

### Next exact starting point

Follow the updated 30-minute heartbeat and check only
`gtd-m4-copy-20260814T071851Z-72bf37746bb3-44f56209` through the fixed wrapper.
Do not poll databases or predecessors, use raw SSH, cancel, clean, drop
candidates, or infer timeout from silence.

## 2026-08-14T10:51:00Z - Cross-site staged-model provenance corrected

### Discoveries

- Job `10912594` successfully passed Viper configuration, Phenix command
  verification, and Nextflow launch, then submitted real candidate processes.
  The first completed task failed before invoking Phaser because the adapter
  still required the staged search model to hash-identically to the original
  first-copy processed model.
- That equality is invalid for the approved cross-site design: each additional
  search intentionally uses the first-copy solution coordinate after Phaser's
  rigid-body placement. The stage already checksum-freezes that derived file
  and separately records the original processed-model checksum.
- Nextflow emitted non-fatal warnings for several `executor.$slurm` and
  `executor.$local` config keys but did submit Slurm tasks. These warnings are
  retained for later profile cleanup and do not justify delaying the prototype
  candidate run.

### Accomplishments

- Carried `search_model_sha256` from the immutable seed TSV through the typed
  workflow and module into the adapter. The adapter now verifies the actual
  staged coordinate against that checksum while preserving
  `original_first_copy_model_sha256` independently in every command record.
  Direct same-site callers retain the original checksum default.
- Added a regression test proving that a checksum-frozen rigid-body solution
  coordinate can differ from the original model without losing either
  provenance value. Focused unit tests passed 14/14, contract tests passed
  56/56, lint and strict typing passed, and both Nextflow syntax and stub runs
  passed.
- Pushed commit `380cc8e7b14e758c89397ab8127c0906aa57b475`;
  GitHub Actions run `31793470648` passed under Pixi 0.74.0 and 0.76.2.
  Staged all 11 candidates again and submitted successor
  `gtd-m4-copy-20260814T105014Z-380cc8e7b14e-0caf3dc2` as Slurm job
  `10914542`. Its first observed scheduler state was `PENDING`.

### Immutable evidence

- Retained run `gtd-m4-copy-20260814T071851Z-72bf37746bb3-44f56209`, job
  `10912594`, has failure signature
  `1258d7ebecf18adb4685406b007264c5db78965803d61d1c4d8941e8b5d334dd`.
  It proves real scheduler wiring but contains no Phaser scientific result
  because input validation stopped the candidate before runtime.
- Successor archive SHA-256 is
  `d3d37001405a20a1b030001dfbfbc6065e1511d9c2cbce265195791c1bcacbb3`;
  decision SHA-256 is
  `7bbe539cf3c02b253ee94d829af6cf0b516e8eecedc6c784ab12cd707d012e2c`;
  review-manifest SHA-256 is
  `da0604426294602a23f441f6a1aea77ec564e9ef8b091ae588b9b861feef55c4`;
  frozen MTZ SHA-256 remains
  `5eb16c3cc3a21e4b7f22cd611834529801c1829fc0a3156a2b6abc2b3de2f20d`.

### Unresolved work

- Leave job `10914542` untouched while non-terminal. Verify that all 11
  candidates now reach real Phaser execution and retain candidate-level stop
  states rather than aborting on the first unsupported addition.
- Require typed sequential outcomes and a fully cached resume before advancing.
  Then begin T12 refinement, maps, and sequence narrowing for all scientifically
  viable alternatives without score-based dropping.

### Next exact starting point

Follow the updated 30-minute heartbeat and check only
`gtd-m4-copy-20260814T105014Z-380cc8e7b14e-0caf3dc2` through the fixed wrapper.
Do not poll databases or predecessors, use raw SSH, cancel, clean, retune, drop
candidates, or infer timeout from silence.

## 2026-08-14T13:31:18Z - Viper M4 accepted and T12 implementation started

### Discoveries

- Retained Viper run
  `gtd-m4-copy-20260814T105014Z-380cc8e7b14e-0caf3dc2`, Slurm job
  `10914542`, completed successfully after real Phenix execution against the
  frozen CD6 MTZ. It produced 22 typed transitions: copy two was supported for
  every one of the 11 retained seeds and copy three was attempted for every
  seed.
- Ten copy-three attempts parsed but retained only two placed copies; one
  copy-three attempt had no parseable final solution count. All 11 two-copy
  parents remain valid retained alternatives. An unsupported addition is not
  evidence that another copy is absent, and none of the 11 candidates is
  dropped before refinement/map review.
- Phenix `sequence_from_map` reports one raw score per FASTA entry and preserves
  FASTA headers, so exact-sequence-group IDs can be carried through a complete
  catalogue ranking and mapped back to every source record/locus without
  forcing a paralogue.
- Nextflow reported non-fatal warnings for legacy executor-scoped Slurm/local
  keys. They did not prevent real jobs or cached resume and are deferred until
  after the prototype path rather than delaying T12.

### Accomplishments

- Verified exactly 11 candidate series, 22 raw result/command records, distinct
  staged-versus-original model checksums for every transition, copy report,
  stage/decision provenance, all artifact checksums, and 11/11 cached processes
  on resume. Viper Phenix 2.1-6048 is now qualified by command probes plus real
  CD6 molecular replacement.
- Added typed T12 refinement and sequence-map result contracts plus a fixed
  adapter that performs one conservative refinement macrocycle, generates a
  sigma-scaled whole-cell `2mFo-DFc` map without filling missing observations,
  and scores the complete exact-sequence catalogue while retaining source/locus
  ambiguity.
- Added the `genome-to-diffraction refinement brief` interface, typed
  `refine_finalists.nf` workflow, candidate-level failure handling, structured
  logging, bounded progress, stub fixtures, cached-resume acceptance, and the
  tracked T12 interface note. Viper T12 resources are bounded to four CPUs and
  16 GB per task with four simultaneous finalists.
- Focused T12 unit tests pass 4/4; Ruff, strict mypy, Nextflow syntax, and the
  standalone T12 stub publication passed. The complete repository gate remains
  the next local command before this increment is committed.

### Immutable evidence

- M4 source commit is
  `380cc8e7b14e758c89397ab8127c0906aa57b475`; nf-helper revision is
  `82431e4c56cb4cd2ef4ea67321fd01fad7ba65cb`; run archive SHA-256 is
  `d3d37001405a20a1b030001dfbfbc6065e1511d9c2cbce265195791c1bcacbb3`.
- Decision SHA-256 is
  `7bbe539cf3c02b253ee94d829af6cf0b516e8eecedc6c784ab12cd707d012e2c`,
  review-manifest SHA-256 is
  `da0604426294602a23f441f6a1aea77ec564e9ef8b091ae588b9b861feef55c4`,
  and MTZ SHA-256 is
  `5eb16c3cc3a21e4b7f22cd611834529801c1829fc0a3156a2b6abc2b3de2f20d`.
- The result summary records 11 attempted seeds, 22 attempted transitions, 11
  supported transitions, zero expected-count completions, one candidate-level
  parse failure, all parents retained, and a fully cached resume. The outer job
  ended `COMPLETED` with exit code zero.

### Unresolved work

- Run the complete locked repository gate, commit/push this coherent T12
  adapter increment, and require both Pixi CI versions to pass.
- Add the smallest fixed Viper T12 stage/submit/collection boundary, deriving
  one checksum-bound two-copy parent PDB/MTZ per retained seed from the accepted
  M4 run. Then execute all 11 finalists without score-based filtering and
  require cached resume.
- T12.5 top-10/top-25/full rendering, second approval template, M5 reporting,
  three-dataset pilot, and M6 validation remain after real T12 evidence.

### Next exact starting point

Run `pixi run --locked check`, inspect the focused diff, and commit/push the T12
scientific adapter increment. Then implement the fixed Viper T12 stage from
retained run `gtd-m4-copy-20260814T105014Z-380cc8e7b14e-0caf3dc2`; do not rerun
M4, drop candidates, or poll the completed database track.

## 2026-08-14T13:47:30Z - T12 scientific adapter increment is green

### Discoveries

- The complete local gate needs about six minutes because the integration and
  all-entry-point Nextflow stub suites are intentionally serial. The new T12
  workflow itself parsed and published its stub outputs normally; no fallback
  or additional synthetic case is needed before the real run.
- The accepted M4 import does not contain the catalogue `source_records.jsonl`.
  A fixed T12 stage must therefore transfer that small checksum-bound crosswalk
  while reusing the retained Viper parent PDB/MTZ assets; it must not repeat M4
  or accept an arbitrary local path.

### Accomplishments

- The complete locked repository gate passed: 341 unit, 56 contract, and 46
  integration tests; schema, docs, actionlint, public panel, Nextflow syntax,
  all stub/resume entry points, and Bash wrapper checks also passed.
- Pushed T12 adapter commit
  `539e2845be9e7cb537747b82267240e8925dcd66`. GitHub Actions run
  `31805869956` passed under Pixi 0.74.0 and 0.76.2.

### Immutable evidence

- The committed protocol is `phenix-t12-brief-v1`; the workflow retains every
  catalogue score and uses four CPUs/16 GB per finalist with four concurrent
  Viper tasks. The adapter has no per-command timeout.
- The preceding accepted M4 run and its 11 two-copy parents remain unchanged;
  no remote job was submitted, cancelled, or cleaned during this increment.

### Unresolved work

- Implement and test the fixed `t12-stage` controller/dispatcher operation that
  binds the accepted M4 run, all 11 best-supported parents, source crosswalk,
  Phenix/MTZ/catalogue checksums, and exact source revision.
- Deploy checksum-reviewed tools, stage/submit all 11 T12 candidates, require a
  cached resume, collect bounded refinement/map/sequence evidence, then build
  the T12.5 second review package.

### Next exact starting point

Add `t12` as a site-isolated fixed HPC profile and implement `t12-stage` from
retained run `gtd-m4-copy-20260814T105014Z-380cc8e7b14e-0caf3dc2`. Transfer
only the fixed 1.1-MB source-record crosswalk, derive all parent PDB/MTZ assets
inside the retained Viper run, and keep all 11 candidates.

## 2026-08-14T14:11:53Z - Fixed Viper T12 boundary implemented and locally green

### Discoveries

- The accepted M4 candidate directory stores the supported copy-two child
  directly as `PHASER.1.pdb` and `PHASER.1.mtz`; later unsupported copy-three
  evidence is isolated below `copy_03`. T12 can therefore derive one exact
  checksum-authenticated two-copy parent per seed without rerunning Phaser or
  interpreting an unsupported third placement as absence.
- The retained M4 run already contains sequence groups, preflight, the site
  Phenix manifest, and full copy results. Only the fixed authoritative
  `source_records.jsonl` catalogue-to-locus crosswalk is absent and needs to
  cross the local-to-Viper boundary.

### Accomplishments

- Added `t12-stage`, a Viper-only controller/dispatcher operation that accepts
  only a pushed revision and an owned retained M4 run ID. It transfers the
  fixed 1.1-MB source crosswalk, validates its checksum and exact catalogue
  identity, and stages exactly 11 supported copy-two PDB/MTZ parents with a
  deterministic manifest and finalists table.
- Added the fixed `t12` scheduler profile, 24-hour outer job, four CPUs/16 GB
  per candidate, four concurrent refinements, no adapter timeout, Phenix
  verification, all-11 first and cached-resume Nextflow runs, typed aggregate
  refinement/sequence evidence, bounded log tails, checksums, and collection
  allowlist. Candidate failures remain typed and do not remove alternatives.
- Added direct stage/controller/CLI tests and the Viper runbook procedure. The
  complete locked gate passed: 344 unit, 56 contract, and 46 integration tests,
  plus Ruff, strict mypy, schema/docs/actionlint/public-panel validation,
  Nextflow syntax and stub/resume checks, and Bash wrapper syntax.

### Immutable evidence

- The T12 stage is bound to retained M4 run
  `gtd-m4-copy-20260814T105014Z-380cc8e7b14e-0caf3dc2`; that parent remains
  terminal accepted evidence and was not polled, rerun, cancelled, cleaned, or
  modified in this increment.
- The fixed local crosswalk remains
  `.untracked/m0-qualification/results/catalogue-reference-637975d/source_records.jsonl`;
  no caller-supplied source or destination path was added to the HPC interface.

### Unresolved work

- Commit and push this coherent T12 boundary, require both Pixi CI versions to
  pass, deploy the checksum-reviewed tools, then stage and submit the real
  all-11 T12 run from the accepted M4 parent.
- Require terminal bounded evidence and an 11/11 cached resume before building
  the T12.5 top-10/top-25/full sequence review and approval package.

### Next exact starting point

Inspect and commit the focused T12 boundary diff, push it, and monitor both CI
jobs. After green CI, run `deploy-tools`, `t12-stage` with parent
`gtd-m4-copy-20260814T105014Z-380cc8e7b14e-0caf3dc2`, then `submit t12` as
separate approved wrapper operations and replace this heartbeat with the
successor 30-minute T12 monitor.

## 2026-08-14T14:19:50Z - First fixed T12 stage failed safely before submission

### Discoveries

- Commit `3ef995c751eb29c95127a70833509b7e79865a32` passed both Pixi 0.74.0
  and 0.76.2 jobs in GitHub Actions run `31808432432`; reviewed remote tools
  were deployed with dispatcher SHA-256
  `810718d8b0b6e3149a523d41a1d7997af28009ce13e29138c1f0e8f3b585bb32`
  and job-wrapper SHA-256
  `99f61b59f8fe637e482e0d3b01818cdc3753e989dcc4f09d44fa83a5d959b851`.
- Fixed stage run `gtd-t12-20260814T141857Z-3ef995c751eb-5cdd8f2d`
  preserved a `test_failure` before Slurm submission. The existing bounded
  `logs` operation did not select `t12-stage.log`, so the scientific staging
  diagnostic was not observable through the approved interface.

### Accomplishments

- Preserved the failed stage unchanged and did not submit, cancel, clean, or
  use raw SSH. Added only the missing bounded stage-log selection for T12;
  Bash syntax remains green.

### Immutable evidence

- The transferred fixed source-record checksum was
  `abd1bd5c50770726343f2d1c407869d29bb91e0b4d989708bc40fc12dc22bb72`.
  A local catalogue identity check confirmed 1,621 sequence-group IDs and
  1,621 source-record group IDs with no difference in either direction.

### Unresolved work

- Commit/push/deploy the bounded-log fix, inspect only the failed run's last
  200 stage-log lines, and correct the specific staging fault. Retain the
  failed stage as immutable evidence.

### Next exact starting point

Commit the `t12-stage.log` selection, push and deploy it, then run bounded
`logs --tail 200` on
`gtd-t12-20260814T141857Z-3ef995c751eb-5cdd8f2d`; do not submit that failed
stage or use raw SSH.

## 2026-08-14T14:26:27Z - T12 stage failure reduced to one profile omission

### Discoveries

- Bounded logs from retained failed stage
  `gtd-t12-20260814T141857Z-3ef995c751eb-5cdd8f2d` showed that the T12
  adapter executable was absent because `t12` was omitted from the existing
  locked-HPC-environment installation and scientific-runtime checks. No
  catalogue, checksum, parent-asset, or Phenix failure had been reached.

### Accomplishments

- Added `t12` to those two existing profile conditions and one focused
  regression assertion. The 13 focused unit tests and Bash wrapper syntax pass.
- Committed the user-added repository instruction to follow KISS, DRY, and
  YAGNI as commit `b9c11a50c757a3283b37c9f41a42663c9a00869f`; future work
  will favour the next real prototype result over minor polish.

### Immutable evidence

- The failed stage remains untouched. Its complete bounded diagnostic was:
  `.pixi/envs/hpc/bin/genome-to-diffraction: No such file or directory`.

### Unresolved work

- Commit/push/deploy this exact environment-profile fix and retry fixed T12
  staging from the same accepted M4 parent. Do not add further synthetic cases
  unless a distinct observed failure requires one.

### Next exact starting point

Commit the two-condition fix and focused regression, deploy the reviewed tools,
then rerun `t12-stage` from the accepted M4 parent and submit immediately if it
stages exactly 11 candidates.

## 2026-08-14T14:29:34Z - T12 selects the CD6 preflight by MTZ identity

### Discoveries

- Retained failed stage `gtd-t12-20260814T142758Z-12e690c57aad-bac08e6c`
  installed the locked runtime and reached the stage adapter. It failed because
  the imported preflight JSONL correctly contains multiple crystal records,
  while T12 had required one record in the whole file.

### Accomplishments

- T12 now reads the checksum-bound M4 stage manifest and selects exactly the
  preflight record whose MTZ SHA-256 matches that manifest. The focused test
  covers one matching and one unrelated preflight record; it and strict mypy
  pass.

### Immutable evidence

- Both failed stages remain retained and unsubmitted. The second bounded
  diagnostic was `T12 requires exactly one MTZ preflight record`.

### Unresolved work

- Commit/push/deploy this MTZ-identity selection and retry the real stage. If 11
  candidates stage, submit T12 without adding unrelated polish.

### Next exact starting point

Commit the focused preflight selection, deploy it, rerun `t12-stage` from the
accepted M4 parent, and submit the returned T12 run ID.

## 2026-08-14T14:32:49Z - Real all-11 Viper T12 run launched

### Discoveries

- The MTZ-identity fix staged all 11 supported copy-two parents successfully;
  no further fallback or staging work is needed before real refinement.

### Accomplishments

- Staged immutable run
  `gtd-t12-20260814T143056Z-eb36d617bfea-72723756` from accepted M4 parent
  `gtd-m4-copy-20260814T105014Z-380cc8e7b14e-0caf3dc2` and submitted Slurm job
  `10916327`. Its first observed scheduler state is `RUNNING`.
- Replaced the old monitor with a 30-minute T12 heartbeat. It preserves all 11
  candidates, uses only the approved wrapper, and proceeds to T12.5 after
  terminal evidence rather than polishing minor cases.

### Immutable evidence

- Source commit is `eb36d617bfea93847f198364773701d8fe177da4`;
  nf-helper is `82431e4c56cb4cd2ef4ea67321fd01fad7ba65cb`; source-record
  SHA-256 is
  `abd1bd5c50770726343f2d1c407869d29bb91e0b4d989708bc40fc12dc22bb72`;
  T12 stage-manifest SHA-256 is
  `8aa4c14369f1512c4d305edf8da7d20e13e38fd76d37570a0879f5019959d5f3`.
- Failed stage predecessors
  `gtd-t12-20260814T141857Z-3ef995c751eb-5cdd8f2d` and
  `gtd-t12-20260814T142758Z-12e690c57aad-bac08e6c` remain retained and
  unsubmitted.

### Unresolved work

- Leave job `10916327` untouched while non-terminal. On completion, collect and
  verify exactly 11 typed refinement/sequence outcomes and an 11/11 cached
  resume, then implement the smallest T12.5 review package.

### Next exact starting point

Follow the 30-minute heartbeat and check only
`gtd-t12-20260814T143056Z-eb36d617bfea-72723756` through the fixed wrapper. Do
not poll completed M4/database tracks, use raw SSH, cancel, clean, drop
candidates, or add unrelated fallback work.

## 2026-08-14T15:09:14Z - T12 identifies and fixes the refinement MTZ boundary

### Discoveries

- Retained run `gtd-t12-20260814T143056Z-eb36d617bfea-72723756` completed
  operationally as Slurm job `10916327` with exit code 0 and an 11/11 cached
  resume. All 11 candidates were retained, but every refinement ended as
  `failed_tool_execution` and every sequence step as `skipped_ineligible`.
- Every bounded Phenix log reports the same direct cause: the staged Phaser
  solution MTZ contains no R-free array. The checksum-matched original CD6
  diffraction MTZ has `free_flag_status=present`; it is the correct refinement
  observations file.

### Accomplishments

- T12 staging now gives every finalist the shared, checksum-bound original
  diffraction MTZ and fails loudly if its preflight reports missing FreeR
  flags. Each candidate's Phaser solution MTZ remains copied and checksum-bound
  as provenance.
- Added one focused regression assertion and ran the complete locked project
  gate successfully. No candidates, scores, or historical runs were changed.

### Immutable evidence

- The terminal T12 run and failed stage predecessors remain untouched. The
  collected summary records 11 refinement failures, 11 skipped sequence
  outcomes, all candidates retained, and all resume processes cached.
- Source commit for the retained run is
  `eb36d617bfea93847f198364773701d8fe177da4`; parent M4 run is
  `gtd-m4-copy-20260814T105014Z-380cc8e7b14e-0caf3dc2`; original CD6 MTZ
  SHA-256 is
  `5eb16c3cc3a21e4b7f22cd611834529801c1829fc0a3156a2b6abc2b3de2f20d`.

### Unresolved work

- Commit, push, deploy, and rerun this single observed-failure correction for
  all 11 retained candidates. On accepted refinement evidence, proceed directly
  to the smallest T12.5 review package.

### Next exact starting point

Commit the original-diffraction-MTZ correction, deploy its checksum-reviewed
tools, stage and submit one successor T12 run from the same accepted M4 parent,
then monitor only that run through the fixed wrapper.

## 2026-08-14T15:17:45Z - Corrected all-11 T12 successor launched

### Discoveries

- The corrected boundary staged all 11 candidates from the accepted M4 parent;
  the original CD6 diffraction MTZ and every Phaser solution asset passed their
  checksum gates.

### Accomplishments

- Commit `14e0bca2c4296de2d39740b69e0ef26db92fab60` passed the complete
  local locked gate and both GitHub Actions Pixi jobs in run `31813198628`.
- Deployed checksum-reviewed tools, staged immutable run
  `gtd-t12-20260814T151604Z-14e0bca2c429-06d1dce8`, and submitted Slurm job
  `10916791`. Its first scheduler state is `PENDING`.
- Updated the 30-minute heartbeat to monitor only this successor.

### Immutable evidence

- nf-helper revision is `82431e4c56cb4cd2ef4ea67321fd01fad7ba65cb`;
  source-record SHA-256 is
  `abd1bd5c50770726343f2d1c407869d29bb91e0b4d989708bc40fc12dc22bb72`;
  T12 stage-manifest SHA-256 is
  `8324f40085a9169ab0e477fcb7dd2e316f9088c58ec29d5814a7483f6bb2e188`.
- The preceding terminal T12 run and failed stage predecessors remain retained
  and unchanged.

### Unresolved work

- Leave job `10916791` untouched while non-terminal. On completion, collect and
  verify all 11 refinement/sequence outcomes and the cached resume, then proceed
  directly to the smallest T12.5 review package.

### Next exact starting point

At the next heartbeat, check only
`gtd-t12-20260814T151604Z-14e0bca2c429-06d1dce8` through the approved status
operation. Do not poll completed predecessors or add unrelated polish.

## 2026-08-14T16:37:39Z - T12 exposes ambiguous observation-array selection

### Discoveries

- Retained successor `gtd-t12-20260814T151604Z-14e0bca2c429-06d1dce8`
  completed as Slurm job `10916791` with exit code 0 and an 11/11 cached resume.
  All candidates were retained, but all 11 refinements again emitted
  `failed_tool_execution` and sequence assessment was skipped.
- Every bounded Phenix log gives the same direct cause: the original CD6 MTZ
  contains both merged mean intensities and anomalous intensities, so Phenix
  refuses to choose an observation array implicitly. The preflight already
  records the intended merged observation labels.

### Accomplishments

- Collected the complete bounded evidence and preserved the run unchanged.
- T12 now carries the preflight-selected observation labels through the staged
  finalist row and CLI, includes them in cache/provenance identity, and passes
  them explicitly as `data_manager.miller_array.labels.name` to Phenix.
- The focused unit suite passes with the corrected boundary.

### Immutable evidence

- Source commit is `14e0bca2c4296de2d39740b69e0ef26db92fab60`;
  T12 stage-manifest SHA-256 is
  `8324f40085a9169ab0e477fcb7dd2e316f9088c58ec29d5814a7483f6bb2e188`;
  outer scheduler state is `COMPLETED` and outer failure class is `success`.
- The normalised summary records 11 refinement failures, 11 sequence failures,
  all candidates retained, and all resume processes cached. Operational success
  is not being misreported as scientific T12 success.

### Unresolved work

- Run the full locked gate, commit, push, deploy, and submit one corrected T12
  replay from the same accepted M4 parent. Do not add unrelated fallback work.

### Next exact starting point

Validate the explicit observation-label correction, deploy its immutable green
commit, and immediately stage and submit the all-11 T12 successor.

## 2026-08-14T16:58:34Z - Observation-labelled T12 successor launched

### Discoveries

- The explicit observation-label boundary staged all 11 retained candidates
  successfully from the unchanged accepted M4 parent.

### Accomplishments

- The complete locked local gate passed. Commit
  `c04359bb301d31aa0710e9cc163aba74d18dd740` passed both Pixi variants in
  GitHub Actions run `31821010548` after a formatting-only follow-up.
- Deployed checksum-reviewed tools, staged immutable run
  `gtd-t12-20260814T165322Z-c04359bb301d-709a1894`, and submitted Slurm job
  `10917303`. Its first scheduler state is `PENDING`.

### Immutable evidence

- nf-helper revision is `82431e4c56cb4cd2ef4ea67321fd01fad7ba65cb`;
  source-record SHA-256 is
  `abd1bd5c50770726343f2d1c407869d29bb91e0b4d989708bc40fc12dc22bb72`;
  T12 stage-manifest SHA-256 is
  `41504d96e88cec9fed3a06091f9f043798866e734aec4092dcf9cad027d64bfe`.
- The two terminal all-candidate failure runs remain retained and unchanged.

### Unresolved work

- Leave job `10917303` untouched while non-terminal. On completion, collect and
  verify all 11 refinement/sequence outcomes and cached resume, then proceed
  directly to the smallest T12.5 review package.
- The Codex automation update call timed out twice during this heartbeat; retry
  updating the existing 30-minute monitor to this successor before any new
  remote operation.

### Next exact starting point

Update the existing monitor to check only
`gtd-t12-20260814T165322Z-c04359bb301d-709a1894`, then leave the run untouched
until its next 30-minute status check.

## 2026-08-14T18:17:52Z - T12 reaches refinement but misses Phenix assets

### Discoveries

- Retained run `gtd-t12-20260814T165322Z-c04359bb301d-709a1894` completed as
  Slurm job `10917303` with exit code 0 and an 11/11 cached resume. The explicit
  CD6 observation labels worked: all 11 Phenix refinements ran and produced
  raw R-work/R-free and geometry metrics.
- All 11 normalised refinement records remained `failed_parse`. Phenix 2.1-6048
  wrote a CIF model by default and did not write an MTZ until an explicit
  `electron_density_maps.map_coefficients` request was present. Its CCP4 map
  name also includes the output serial (`brief_refine_001_2mFo-DFc.ccp4`).

### Accomplishments

- Collected and preserved the complete bounded run evidence without dropping
  candidates or misreporting outer success as scientific T12 success.
- Reproduced the observed output behaviour with local Phenix 2.1-6048 and the
  checksum-frozen CD6 MTZ. A focused corrected probe wrote the required PDB,
  map-coefficient MTZ, and cell CCP4 map.
- Updated the fixed adapter to request PDB output and explicit 2mFo-DFc map
  coefficients, recognise the serialised CCP4 name, and use protocol identity
  `phenix-t12-brief-v2` so the corrected work cannot reuse stale cache entries.
  The complete locked project gate passes (346 unit, 56 contract, and 46
  integration tests plus all schema, documentation, workflow, stub, and HPC
  checks).

### Immutable evidence

- The terminal source commit is
  `c04359bb301d31aa0710e9cc163aba74d18dd740`; the T12 stage-manifest SHA-256 is
  `41504d96e88cec9fed3a06091f9f043798866e734aec4092dcf9cad027d64bfe`.
- The result records 11 attempted refinements, 11 typed parse failures, all 11
  candidates retained, and a fully cached resume. Raw final R-free values range
  from 0.5294 to 0.5510 and remain evidence, not an approval threshold.

### Unresolved work

- Commit and qualify the minimal asset-output fix, deploy it, and replay the
  unchanged all-11 T12 boundary. On scientific success, proceed directly to the
  smallest T12.5 top-10/top-25/full review package.

### Next exact starting point

Commit and push protocol v2, require both Pixi CI variants to pass, then deploy
and stage one immutable T12 successor from the accepted M4 parent.

## 2026-08-14T18:24:44Z - Phenix-output T12 successor launched

### Discoveries

- The checksum-gated T12 boundary staged all 11 candidates unchanged with the
  new protocol-v2 output contract.

### Accomplishments

- Committed the focused fix as
  `1e4edc752972ada63b421ccf68611ab2ed08cbf2`; both Pixi variants passed in
  GitHub Actions run `31828070961`.
- Deployed checksum-reviewed tools, staged immutable run
  `gtd-t12-20260814T182413Z-1e4edc752972-b9caf8a2`, and submitted Slurm job
  `10917754`. Its first observed scheduler state is `RUNNING`.

### Immutable evidence

- nf-helper revision is `82431e4c56cb4cd2ef4ea67321fd01fad7ba65cb`;
  source-record SHA-256 is
  `abd1bd5c50770726343f2d1c407869d29bb91e0b4d989708bc40fc12dc22bb72`;
  T12 stage-manifest SHA-256 is
  `8d67e9583ec5ced2708be6fe3bcf7642def3b39f6f08a960f4b02cc8410ba040`.
- The three preceding terminal T12 runs remain retained and unchanged.

### Unresolved work

- Leave job `10917754` untouched while non-terminal. On completion, collect and
  verify all 11 refinement and sequence outcomes plus the cached resume. Move
  directly to T12.5 if the required Phenix assets are present.

### Next exact starting point

At the next 30-minute loop, check only
`gtd-t12-20260814T182413Z-1e4edc752972-b9caf8a2` through the approved status
operation and do not infer failure from silence.

## 2026-08-14T18:36:30Z - T12 blocked by one Phenix runtime outage

### Discoveries

- Retained job `10917754` failed before Nextflow execution. Every Phenix probe
  reported that its bundled Python could not load the filesystem encoding from
  the `/ptmp` runtime. This is an explicit environment failure, not a protocol-v2
  refinement result.
- The same Phenix prefix had passed all probes and run real refinements in the
  immediately preceding retained job, so one unchanged replay is the smallest
  test for a transient shared-filesystem visibility failure.

### Accomplishments

- Collected and preserved the failed run with failure signature
  `427dc127f56053167d5957f90fe4d8977da068d8452dcb35e8232ded30d60241`.
- Staged unchanged run `gtd-t12-20260814T183602Z-1e4edc752972-0aaece23`
  from the same green protocol-v2 commit and submitted Slurm job `10917867`.
  Its first observed state is `RUNNING`.

### Immutable evidence

- The replay uses source commit
  `1e4edc752972ada63b421ccf68611ab2ed08cbf2`, nf-helper revision
  `82431e4c56cb4cd2ef4ea67321fd01fad7ba65cb`, and T12 stage-manifest SHA-256
  `3aadecc73e8e2b4aba85695e86763ba7a82c37e955f6df125aff7ac605bc2188`.
- Job `10917754` and all preceding T12 runs remain retained and unchanged.

### Unresolved work

- Leave job `10917867` untouched while non-terminal. If the identical Phenix
  runtime failure repeats, stop replaying T12 and repair or reinstall the
  `/ptmp` Phenix runtime before any further scientific run.
- The Codex automation update service timed out again; the persisted monitor is
  stale, so every loop must follow this newest journal entry until it can be
  retargeted.

### Next exact starting point

At the next 30-minute loop, check only
`gtd-t12-20260814T183602Z-1e4edc752972-0aaece23` through the approved status
operation; collect terminal evidence before deciding whether runtime recovery
is required.

## 2026-08-14T19:06:19Z - Viper Phenix runtime requires recovery

### Discoveries

- Unchanged replay job `10917867` failed before Nextflow on a different compute
  host with the identical bundled-Python filesystem-encoding error. The
  `/ptmp` Phenix installation is persistently incomplete or unreadable; this is
  not a transient node-specific failure and not a T12 scientific result.

### Accomplishments

- Collected and preserved the replay. Its failure signature is again
  `427dc127f56053167d5957f90fe4d8977da068d8452dcb35e8232ded30d60241`.
- Stopped T12 replay submission after the repeated signature, as required by
  the bounded development loop. No candidates, parent evidence, database data,
  or preceding runs were modified.

### Immutable evidence

- The retained replay is
  `gtd-t12-20260814T183602Z-1e4edc752972-0aaece23`, source commit
  `1e4edc752972ada63b421ccf68611ab2ed08cbf2`, Slurm job `10917867`, and T12
  stage-manifest SHA-256
  `3aadecc73e8e2b4aba85695e86763ba7a82c37e955f6df125aff7ac605bc2188`.
- Both failed probes show the same missing bundled-Python encoding library;
  jobs ran on `vipc2182` and `vipc2232`, respectively.

### Unresolved work

- Recover or reinstall checksum-verified Phenix 2.1-6048 below `/ptmp`, write a
  new installation manifest under `/u`, and qualify all probes before another
  T12 submission. Preserve the corrupt prefix and current manifest as evidence;
  do not overwrite them in place.
- After runtime qualification, replay protocol-v2 T12 once and proceed directly
  to T12.5 if all required PDB/MTZ/CCP4 assets and sequence outcomes are valid.

### Next exact starting point

Prepare one create-only scheduled Phenix recovery installation using the
retained installer SHA-256
`a2455e281f11241debdb25d9788ada8337420b9ff4c92935f97157f0cc9b9795`;
do not submit another T12 job until its new manifest passes command probes.

## 2026-08-14T21:06:13Z - Create-only Phenix recovery job prepared locally

### Discoveries

- Recovery can reuse the retained checksum-verified installer and immutable
  protocol-v2 source checkout. It does not require another download or a T12
  code change.

### Accomplishments

- Prepared ignored local job script
  `.untracked/viper-phenix-recover-1e4edc7.slurm`. It first verifies the exact
  source and installer revisions, refuses to run if bundled Python is healthy,
  preserves the corrupt prefix plus manifest and logs with the recovery Slurm
  job suffix, and then performs one create-only scheduled installation at the
  stable prefix.
- `bash -n` passes. Script SHA-256 is
  `4eb586147b470353df0e2ea0b1708f99948c113c4d7f364671e261df221836e1`.

### Immutable evidence

- The recovery binds source commit
  `1e4edc752972ada63b421ccf68611ab2ed08cbf2` and installer SHA-256
  `a2455e281f11241debdb25d9788ada8337420b9ff4c92935f97157f0cc9b9795`.
- The script is deliberately outside Git because it contains user-specific
  Viper paths; only its checksum and behaviour are recorded here.

### Unresolved work

- Transfer and submit this exact script through a bounded reviewed Viper
  operation. Raw unrestricted SSH remains outside the approved interface.
- After terminal success, verify the new manifest and all command probes before
  staging one protocol-v2 T12 replay.

### Next exact starting point

Install or approve one checksum-gated Viper Phenix-recovery operation that
accepts only script SHA-256
`4eb586147b470353df0e2ea0b1708f99948c113c4d7f364671e261df221836e1`;
do not submit T12 directly.
