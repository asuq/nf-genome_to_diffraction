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

## 2026-08-14T23:05:23Z - Viper `/ptmp` ageing explains Phenix runtime loss

### Discoveries

- The user reports that Viper removes `/ptmp` files whose last access is older
  than approximately one month. This is the leading explanation for the
  missing Phenix bundled-Python encoding files: the installation was complete
  and executed real refinements before parts of its unpacked runtime vanished.
- Extracted software may retain old archive timestamps, while filesystem mount
  options may not refresh access time on every read. The exact Viper purge
  criterion (access time versus modification time) remains to be confirmed,
  but `/ptmp` must not be treated as durable software storage.

### Accomplishments

- Reclassified the incident from an unknown installation defect to an expired
  disposable runtime cache. No T12 code change or candidate replay is warranted
  until Phenix is restored.
- Kept the recovery design create-only and checksum-bound. The durable `/u`
  area should retain the licensed installer, checksums, manifests, and recovery
  evidence; the unpacked Phenix tree under `/ptmp` is reproducible cache.
- Rejected artificial timestamp touching as a maintenance strategy: it could
  conflict with site policy and create unnecessary metadata load.

### Immutable evidence

- Retained jobs `10917754` and `10917867`, on hosts `vipc2182` and `vipc2232`,
  have the identical failure signature
  `427dc127f56053167d5957f90fe4d8977da068d8452dcb35e8232ded30d60241`.
- The retained installer SHA-256 is
  `a2455e281f11241debdb25d9788ada8337420b9ff4c92935f97157f0cc9b9795`;
  the prepared recovery script SHA-256 is
  `4eb586147b470353df0e2ea0b1708f99948c113c4d7f364671e261df221836e1`.

### Unresolved work

- Confirm the official Viper purge timestamp semantics when convenient and
  ensure the installer plus small recovery records are retained below `/u`.
- Submit the prepared recovery job through a bounded checksum-gated operation,
  qualify the restored runtime, and run protocol-v2 T12 promptly while the
  restored cache is available.

### Next exact starting point

Add or approve the fixed checksum-gated Phenix-recovery operation, submit the
prepared recovery job, and require successful command probes before staging
exactly one protocol-v2 T12 replay.

## 2026-08-14T23:12:58Z - Clean Phenix reinstall submitted

### Discoveries

- The exact Viper Phenix prefix still fails its bundled-Python `encodings`
  import. The retained 3.61-GB installer remains present and matches approved
  SHA-256
  `a2455e281f11241debdb25d9788ada8337420b9ff4c92935f97157f0cc9b9795`.
- The user authorised one access-time normalisation immediately after a clean
  installation, but no periodic timestamp touching. Existing scientific and
  execution evidence remains retained.

### Accomplishments

- Revised the ignored recovery job to validate the fixed stale prefix, delete
  only that exact runtime, preserve the preceding small manifest and logs with
  the Slurm job suffix, reinstall from the verified installer, update access
  times once, and recheck the bundled-Python encoding import.
- Transferred the script, verified its remote SHA-256 as
  `147d842fce27e1a93ff64efb105724115fae40934f26bded4064b2f9bc82f7db`,
  and submitted Viper Slurm job `10919789` with 4 CPUs, 32 GB, and the existing
  24-hour scheduler ceiling. Its first observed state is `PENDING`.
- Created a 30-minute monitor for this one retained recovery job.

### Immutable evidence

- The stale runtime was confirmed before submission; the installer, existing
  durable manifest, and exact runtime prefix were all present.
- Remote job script is
  `/viper/u1/ashima/Softwares/manifests/phenix-recover-147d842f.slurm`;
  its checksum is recorded above and its only destructive target is the fixed
  stale Phenix prefix.

### Unresolved work

- Leave job `10919789` untouched while non-terminal. After it leaves the queue,
  inspect bounded scheduler and controller evidence.
- On success, verify the new installation manifest, command probes, bundled
  Python, real CD6 MTZ execution, and one-time timestamp completion. Then stage
  exactly one protocol-v2 T12 replay.

### Next exact starting point

At the next 30-minute loop, query only Slurm job `10919789`; do not submit T12
until the reinstalled runtime passes its qualification boundary.

## 2026-08-14T23:45:55Z - Phenix restored and protocol-v2 T12 replay submitted

### Discoveries

- Clean-reinstall job `10919789` completed successfully in 16m47s with exit
  code zero and approximately 1.91 GB maximum resident memory for its batch
  step.
- The restored bundled Python imports `encodings`; all seven Phenix command
  probes passed their documented conventions. The new installation manifest
  SHA-256 is
  `0410c2b835a8de91061cb727bf5eb007cfac82b787e857cefc5fd549b5c3bad1`.
- The job completed the authorised one-time access-time normalisation. A
  representative post-job check showed current access times for the prefix and
  bundled Python. No periodic timestamp operation exists.

### Accomplishments

- Removed only the fixed stale Phenix runtime, installed a fresh verified
  Phenix 2.1-6048 runtime from the approved installer, and retained the prior
  small manifest and logs with the recovery job suffix.
- Staged all 11 retained candidates from accepted M4 parent
  `gtd-m4-copy-20260814T105014Z-380cc8e7b14e-0caf3dc2` as immutable T12 run
  `gtd-t12-20260814T234527Z-1e4edc752972-ba0c62c1` and submitted Slurm job
  `10920074`. This is the single authorised real-CD6 protocol-v2 replay.

### Immutable evidence

- Recovery script SHA-256 is
  `147d842fce27e1a93ff64efb105724115fae40934f26bded4064b2f9bc82f7db`;
  installer SHA-256 remains
  `a2455e281f11241debdb25d9788ada8337420b9ff4c92935f97157f0cc9b9795`.
- T12 source commit is
  `1e4edc752972ada63b421ccf68611ab2ed08cbf2`, nf-helper revision is
  `82431e4c56cb4cd2ef4ea67321fd01fad7ba65cb`, source-record SHA-256 is
  `abd1bd5c50770726343f2d1c407869d29bb91e0b4d989708bc40fc12dc22bb72`,
  and T12 stage-manifest SHA-256 is
  `f6af2ac40e1e28739e5808b2c3898596f598aad7b64679a695f2211742445cae`.

### Unresolved work

- Leave T12 job `10920074` untouched while non-terminal. This job must provide
  the restored runtime's real-CD6 qualification; command probes alone are not
  sufficient.
- On terminal completion, collect bounded evidence and verify exactly 11 typed
  outcomes, required refinement/map/sequence assets, all-candidate retention,
  and fully cached resume before proceeding directly to T12.5.

### Next exact starting point

At the next 30-minute loop, query only retained T12 run
`gtd-t12-20260814T234527Z-1e4edc752972-ba0c62c1` through the approved status
operation and do not infer failure from silence.

## 2026-08-15T01:31:44Z - Real-CD6 T12 exposed the final output-name mismatch

### Discoveries

- Retained T12 job `10920074` completed successfully at the outer workflow
  boundary. All 11 real Phenix refinements ran, all candidates were retained,
  and the resume pass was 11/11 cached.
- Every typed refinement result was `failed_parse`, not a scientific failure.
  Phenix exited zero and reported final R values, but the adapter required
  assets under the wrong names. With `output.serial = 1`, Phenix wrote serial
  `002`; its explicitly named CCP4 map is unnumbered. The adapter expected
  serial `001` plus a numbered map name.
- Phenix 2.1-6048 defaults confirm that output serial zero is the correct input
  for first output serial `001`. Sequence-from-map was correctly skipped after
  the asset-contract failure.

### Accomplishments

- Collected the bounded terminal evidence and preserved all 11 typed failures,
  raw R values, logs, commands, checksums, and cached-resume evidence.
- Implemented the minimal protocol-v3 correction: set output serial to zero,
  expect `brief_refine_001.pdb` and `brief_refine_001.mtz`, and expect the
  explicit unnumbered `brief_refine_2mFo-DFc.ccp4` map. Added a focused unit
  assertion for the serial contract.

### Immutable evidence

- Terminal run is
  `gtd-t12-20260814T234527Z-1e4edc752972-ba0c62c1`, Slurm job `10920074`,
  source commit `1e4edc752972ada63b421ccf68611ab2ed08cbf2`, and T12 stage-manifest
  SHA-256
  `f6af2ac40e1e28739e5808b2c3898596f598aad7b64679a695f2211742445cae`.
- The summary records 11 failed-parse refinements, 11 skipped sequence
  analyses, all candidates retained, and a fully cached resume. This run
  qualifies restored Phenix real-CD6 execution, but not the T12 asset boundary.

### Unresolved work

- Run the locked repository gate, commit and push protocol v3, require green
  CI, deploy checksum-reviewed tools, and submit one unchanged all-11 T12
  replay. Do not add unrelated parser fallbacks or drop candidates.
- On asset-complete success, proceed directly to the smallest T12.5 review and
  approval package.

### Next exact starting point

Run `pixi run --locked check` for protocol v3, inspect the focused diff, then
commit and push before deploying and staging one immutable T12 successor.

## 2026-08-15T01:45:28Z - Protocol-v3 T12 successor launched

### Discoveries

- The complete locked repository gate passed after the focused output-name
  correction: 346 unit, 56 contract, and 46 integration tests passed together
  with formatting, lint, strict typing, schemas, docs, Actions, Nextflow syntax,
  stub/resume, and wrapper checks.

### Accomplishments

- Committed protocol v3 as
  `f50e02fe1b1ab8ac7e44c9782156d1f032c7eb08`; both Pixi 0.74.0 and 0.76.2
  jobs passed in GitHub Actions run `31857122152`.
- Deployed checksum-reviewed tools, staged immutable all-11 run
  `gtd-t12-20260815T014459Z-f50e02fe1b1a-4eff44ad`, and submitted Viper Slurm
  job `10920614`. Its first observed scheduler state is `RUNNING`.

### Immutable evidence

- Deployed dispatcher SHA-256 is
  `809d40d09adbd58fe5a13342f0ad8162faa433085f35321dcc6f970fd0b861ee`;
  recovery SHA-256 is
  `0db4c5f3542ce4d387ac019e33717d5e405ac957efb216b05c52828a851808f4`.
- The successor uses nf-helper
  `82431e4c56cb4cd2ef4ea67321fd01fad7ba65cb`, source-record SHA-256
  `abd1bd5c50770726343f2d1c407869d29bb91e0b4d989708bc40fc12dc22bb72`,
  and T12 stage-manifest SHA-256
  `b52ff6be476d24c3498fe44c41704c9c28b130f7b262200a5db4a5bfdb9d7914`.

### Unresolved work

- Leave job `10920614` untouched while non-terminal. On completion, collect
  bounded evidence and verify exactly 11 asset-complete refinement/sequence
  outcomes, all-candidate retention, and 11/11 cached resume.
- Proceed directly to T12.5 after accepted evidence; do not add unrelated
  fallbacks or repeat the superseded protocol-v2 run.

### Next exact starting point

At the next 30-minute loop, query only retained T12 run
`gtd-t12-20260815T014459Z-f50e02fe1b1a-4eff44ad` through the approved status
operation and do not infer failure from silence.

## 2026-08-15T12:23:36Z - Real T12 accepted and T12.5 implemented

### Discoveries

- Protocol-v3 T12 run
  `gtd-t12-20260815T014459Z-f50e02fe1b1a-4eff44ad`, Slurm job `10920614`,
  completed successfully. All 11 two-copy finalists produced typed refinement
  results, refined PDB/MTZ files, whole-cell sigma-scaled `2mFo-DFc` maps, and
  sequence-from-map results. All 11 resume processes were cached.
- Final `R_free` spans 0.5294 to 0.5510. These high values make the outputs
  narrowing and Coot-review candidates, not validated structures. No candidate
  was discarded or approved automatically.
- Each map search completed against 1,621 exact catalogue groups; 1,267 to
  1,617 groups received scores depending on the finalist. Best raw scores span
  26.56 to 94.08 and best score z values span 5.05 to 14.48. Unscored groups
  remain distinct from low-scoring groups.

### Accomplishments

- Collected and verified the bounded terminal evidence for the accepted real
  run. Implemented the T12.5 second checkpoint: fixed checksum-gated collection
  of only typed finalist PDB/MTZ/CCP4/sequence-model assets, deterministic
  top-10/top-25/full sequence views, a Coot-oriented HTML view, unique primary
  approval candidates, a header-only approval template, and a content-derived
  package manifest.
- The checkpoint retains all structural finalists and all scored sequence
  groups. Numeric scores and refinement metrics are annotations only and never
  create a decision.
- The complete locked gate passes: 350 unit, 56 contract, and 47 integration
  tests, plus formatting, lint, strict typing, schemas, documentation, Actions,
  Nextflow syntax/stub-resume, and shell validation.

### Immutable evidence

- Source commit for the real run is
  `f50e02fe1b1ab8ac7e44c9782156d1f032c7eb08`; nf-helper is
  `82431e4c56cb4cd2ef4ea67321fd01fad7ba65cb`; T12 stage-manifest SHA-256 is
  `b52ff6be476d24c3498fe44c41704c9c28b130f7b262200a5db4a5bfdb9d7914`.
- Collected T12 summary, resume, refinement-result, and sequence-result
  SHA-256 values are respectively
  `6a704cae07dfe9b4fb2a5e59c2374c11ebc57d69188eb9c8b62717a146429c6a`,
  `3531cfbf86d560a0a86daec2eb0e9b52580fb8d80ab6c7b6f269cfca0db89175`,
  `f021fcab3af830cdf3904039857e88e1357b3b93372d4ca4331d6ccf8e6abd07`,
  and `7edddb2967b1982d74c3e61897a841bbf710fdf8d4e3a8fb39662ea6229a4f93`.

### Unresolved work

- Commit and push this focused accepted-T12/T12.5 increment, require both Pixi
  CI jobs to pass, deploy the checksum-reviewed controller and dispatcher, and
  run `t12-review-collect` for the retained T12 run.
- Verify exactly 11 self-contained finalist asset bundles, 110 primary rows,
  275 extended rows, all scored rows, output checksums, HTML links, and the
  empty approval template. Then begin the smallest M5 status/report increment;
  human sequence approval can proceed independently in Coot.

### Next exact starting point

Inspect and commit the focused T12.5 diff, push it, and require GitHub Actions
to pass. Deploy the reviewed tools and invoke only `t12-review-collect` for
`gtd-t12-20260815T014459Z-f50e02fe1b1a-4eff44ad`; do not rerun T12 or remove
any retained candidate.

## 2026-08-15T13:10:44Z - T12.5 review package collected and verified

### Discoveries

- The fixed checksum-gated transfer completed without repeating T12. The
  resulting package retains 11 finalist directories and exactly four review
  assets per finalist: refined PDB, refined MTZ, `2mFo-DFc` CCP4 map, and
  sequence-from-map PDB.
- The deterministic views contain 110 top-10 rows, 275 top-25 rows, and 16,341
  full scored rows. The 107 unique primary approval candidates are suggestions
  for human review only; the approval template contains zero decisions.
- All 44 asset checksums and all six rendered-output checksums match the
  package manifest. All 330 HTML asset links resolve locally.

### Accomplishments

- Committed T12.5 as `15afb13e0e13a29932c4fcfa0f9eacc3c9672afa`, pushed it,
  and verified both Pixi 0.74.0 and 0.76.2 jobs in GitHub Actions run
  `31884562729`.
- Deployed the reviewed controller tools, installed the matching local wrapper,
  and collected the self-contained T12.5 package for retained run
  `gtd-t12-20260815T014459Z-f50e02fe1b1a-4eff44ad`.
- No finalist or scored sequence was discarded, and no scientific identity was
  approved automatically.

### Immutable evidence

- T12.5 package ID is
  `seqreview_69c4c2705c35a12bc104581c4444076cee91daae13d0a3a354d0a20e8a000c07`.
- Deployed dispatcher SHA-256 is
  `ec1577dc7910769040727cbaee9bcb3fc00fc10d22b2cec46f81242931b34f93`;
  installed local wrapper SHA-256 is
  `eeae34406c8d3a16e9185e4e0f9c9b9982a3fb10aab04aa67b2efead13eb816f`.
- The package preserves T12 stage-manifest SHA-256
  `b52ff6be476d24c3498fe44c41704c9c28b130f7b262200a5db4a5bfdb9d7914`,
  refinement-results SHA-256
  `f021fcab3af830cdf3904039857e88e1357b3b93372d4ca4331d6ccf8e6abd07`,
  and sequence-results SHA-256
  `7edddb2967b1982d74c3e61897a841bbf710fdf8d4e3a8fb39662ea6229a4f93`.

### Unresolved work

- Human Coot review and explicit sequence decisions remain required. The high
  preliminary `R_free` values prevent treating any candidate as a validated
  structure or exact identity.
- Begin M5 with the smallest T13.1 status engine. It must preserve successful
  execution independently from scientific insufficiency while the approval
  template is empty, then consume explicit human decisions without inventing
  an identity.

### Next exact starting point

Implement and unit-test a deterministic T13.1 status record from the accepted
T12/T12.5 evidence and explicit approval decisions. Do not begin the
three-dataset pilot or claim a credible structure before human review.

## 2026-08-15T13:16:12Z - Minimal T13.1 status engine applied to CD6

### Discoveries

- Successful workflow execution is not a scientific solution. With no recorded
  Coot decision and no assessed single-component assumption, the real CD6
  evidence correctly resolves to `completed_success`,
  `insufficient_evidence`, and assumption status `unknown`.
- All 11 retained finalists have a best-supported copy count of two in the
  accepted refinement evidence. This count is preserved without selecting a
  sequence identity.

### Accomplishments

- Implemented a deterministic T13.1 status builder and CLI. It validates the
  accepted T12 summary/job/refinement records, the checksum-bound T12.5
  candidate table, and explicit non-conflicting sequence decisions.
- Added focused tests proving that empty decisions cannot promote a candidate,
  while an explicit approval plus a reviewed `consistent` assumption can
  produce the corresponding credible-single-component status.
- Applied the engine to `CD6QS2P2G1_5`; its current record has no primary or
  extended sequence groups and retains both pending-review warnings.

### Immutable evidence

- The current untracked CD6 status record SHA-256 is
  `9fd1910ef2dfa0a572b62a22fe85027092242f00643ead5dc2ea305e577620b0`.
- It is derived from T12 run
  `gtd-t12-20260815T014459Z-f50e02fe1b1a-4eff44ad` and T12.5 package
  `seqreview_69c4c2705c35a12bc104581c4444076cee91daae13d0a3a354d0a20e8a000c07`.

### Unresolved work

- Run the complete locked repository gate, commit and push T13.1, and require
  both Pixi CI jobs to pass.
- Implement the smallest T13.2 self-contained report from the status and T12.5
  package. Human Coot review remains independent and can update the decisions
  before final scientific interpretation.

### Next exact starting point

Run `pixi run --locked check`, inspect the focused T13.1 diff, then commit and
push. After green CI, begin T13.2 without starting the three-dataset pilot.

## 2026-08-15T13:30:02Z - T13.2 report built from verified CD6 evidence

### Discoveries

- A report can remain portable without duplicating the 44 finalist assets by
  living inside the verified T12.5 package. All table, decision, PDB, MTZ, map,
  sequence-model, status, and manifest links then remain local.
- The current CD6 report exposes 52 direct links and all resolve. It prominently
  retains `insufficient_evidence`, the pending human approval, and the unknown
  prototype-assumption state.

### Accomplishments

- T13.1 commit `f0bed24dc05078fbbef479aeb2b51a7ac4aec4ee` passed both
  Pixi 0.74.0 and 0.76.2 jobs in GitHub Actions run `31887008617`.
- Implemented the smallest T13.2 builder. It revalidates every checksum-bound
  T12.5 table and finalist asset before adding the HTML report, machine-readable
  scientific status, and a content-derived report manifest.
- Applied it to the accepted CD6 package. No candidate, sequence group, warning,
  or human-checkpoint requirement was removed.

### Immutable evidence

- Real CD6 report ID is
  `report_e9b2c1bc4c69dafab5961c1c4bc8bc26b4bdcd8f4da3c4acb74b2ec432a0935a`.
- Both recorded T13.2 output checksums match and all 52 report links resolve
  inside T12.5 package
  `seqreview_69c4c2705c35a12bc104581c4444076cee91daae13d0a3a354d0a20e8a000c07`.

### Unresolved work

- Run the complete locked gate, commit and push T13.2, and require both Pixi CI
  jobs to pass.
- Implement T13.3 resource summary from the already collected Nextflow traces,
  Slurm result, checksums, and storage inventory. Human Coot review can proceed
  independently; do not start the three-dataset pilot yet.

### Next exact starting point

Run `pixi run --locked check`, inspect and commit the focused T13.2 diff, push,
and monitor CI. Then begin the smallest deterministic T13.3 resource summary.

## 2026-08-15T13:39:49Z - T13.2 milestone closed green

### Discoveries

- No additional defect appeared in the independent dual-Pixi CI execution.
  The local and GitHub validation results agree.

### Accomplishments

- Committed and pushed T13.2 as
  `c035a2359d60e396afa6083bb993d5f5d3cbe650`.
- Both Pixi 0.74.0 and 0.76.2 jobs passed in GitHub Actions run
  `31887603131`. The working implementation now covers T13.1 status and T13.2
  review reporting on the accepted real CD6 evidence.

### Immutable evidence

- The real report remains
  `report_e9b2c1bc4c69dafab5961c1c4bc8bc26b4bdcd8f4da3c4acb74b2ec432a0935a`
  within T12.5 package
  `seqreview_69c4c2705c35a12bc104581c4444076cee91daae13d0a3a354d0a20e8a000c07`.

### Unresolved work

- T13.3 resource summarisation is the next code increment.
- Coot review and explicit sequence decisions remain required before scientific
  promotion; the three-dataset pilot must wait for the remaining M5 boundary.

### Next exact starting point

Implement T13.3 from the retained first/resume Nextflow traces, outer Slurm job
result, and package inventory. Preserve allocated and measured resources as
separate fields and do not infer unavailable database I/O.

## 2026-08-15T14:07:08Z - T13.3 resource summary built for accepted CD6

### Discoveries

- The retained Nextflow report records exact per-task allocation and process
  counters, while the independent TSV traces prove 11 completed task identities
  and the same 11 identities on cached resume. Cached rows retain first-run
  measurements, so counting those values again would double-count resources.
- The first T12 execution used an estimated `20.492910` CPU-hours against
  `82.423786` allocated CPU-hours. Peak RSS was `2,194,018,304` bytes against
  `17,179,869,184` allocated bytes per task. These measurements support revisiting
  the four-CPU/sixteen-GB T12 default during T13.5, without changing it from one
  crystal alone.
- The outer job result records elapsed time but not its allocation or MaxRSS.
  Nextflow I/O counters are process counters rather than physical database-device
  traffic. Both unavailable measurements therefore remain null instead of being
  inferred.

### Accomplishments

- Added the typed `resource-summary` contract and the deterministic
  `review build-resource-summary` operation.
- The builder cross-checks first, resume, and report task identities; separates
  executed and cached resources; reports retries, CPU-hours, wall span, peak RSS,
  task allocations, concurrency, process I/O counters, and package storage; and
  binds every retained evidence input by SHA-256.
- Applied the builder twice to the accepted real CD6 T12/T12.5 evidence. Both
  builds produced the same identifier and file checksum, confirming deterministic
  rebuild behaviour without another Viper job.

### Immutable evidence

- Resource summary ID:
  `resources_af7d9269e8ec0ed38ed291daf436700260254c48dc2a11d5926cba32a9c94c9a`.
- Resource summary SHA-256:
  `15152ed7f4e8480cccac0a92d6e78f930fdec05ef529007760cbeaea79549b4a`.
- The first run has 11 completed processes, zero retries, `20.492910` estimated
  CPU-hours, `20,760.302` seconds process wall span, and four observed concurrent
  processes. The outer Slurm job elapsed `20,884` seconds.
- The resume has 11 cached processes and no newly counted process resources. The
  self-contained package contains 54 pre-summary files totalling `403,064,672`
  bytes.

### Unresolved work

- Run the complete locked gate, inspect and commit the focused T13.3 increment,
  push it, and require both Pixi CI jobs to pass.
- Human Coot review and explicit sequence/assumption decisions remain required.
  After this checkpoint, close the normal main-workflow integration gap and run
  the three-dataset T13.4 pilot; do not tune final defaults from CD6 alone.

### Next exact starting point

Run `pixi run --locked check`, inspect the complete T13.3 diff, then commit,
push, and monitor GitHub Actions. After green CI, proceed to the human checkpoint
and the smallest end-to-end workflow integration needed for T13.4.

## 2026-08-15T14:19:40Z - T13.3 milestone closed green

### Discoveries

- The independent GitHub runners reproduced the complete local result under
  both supported Pixi versions. No additional T13.3 defect appeared.

### Accomplishments

- Committed and pushed the deterministic resource summary as
  `676c279ecb942a8cbb850834b11f3811913a5b4c`.
- Both Pixi 0.74.0 and 0.76.2 jobs passed in GitHub Actions run
  `31889382941`. T13.1 status, T13.2 reporting, and T13.3 resource accounting
  are now closed for the accepted real CD6 evidence.
- Replaced the roadmap's stale M3 immediate-goal text with the active M5 human
  checkpoint, main-workflow integration, three-dataset pilot, and calibration
  sequence.

### Immutable evidence

- Resource summary ID remains
  `resources_af7d9269e8ec0ed38ed291daf436700260254c48dc2a11d5926cba32a9c94c9a`;
  its JSON SHA-256 remains
  `15152ed7f4e8480cccac0a92d6e78f930fdec05ef529007760cbeaea79549b4a`.
- The accepted T12.5 package remains
  `seqreview_69c4c2705c35a12bc104581c4444076cee91daae13d0a3a354d0a20e8a000c07`.

### Unresolved work

- Human Coot review must record explicit sequence-group decisions and assess
  whether the single-component assumption is consistent. High preliminary
  `R_free` values still prohibit claiming a validated structure or identity.
- The normal main workflow still ends before M4/T12. Close that integration
  gap, then execute the three-dataset T13.4 pilot and use its measurements for
  T13.5 calibration. M6 independent validation and internal release follow.

### Next exact starting point

Review `t12-sequence-checkpoint/crystal_report.html` and the linked finalist
PDB/MTZ/map bundles in Coot. Record explicit `approve`, `reject`, `defer`, or
`retain_alternative` rows in `approved_sequence_groups.tsv`, plus an assessed
prototype-assumption status. Rebuild T13.1/T13.2 from those decisions, then
implement the smallest normal-workflow connection required to run T13.4.

## 2026-08-15T14:47:47Z - Normal workflow reaches discovery and model preparation

### Discoveries

- The qualified P1 and M2 processes already compose directly from the Task 05
  catalogue bundle: exact sequence/source records feed all three discovery
  branches, direct-PDB hits feed coordinate registration and cleaned
  experimental models, and verified AFDB coordinates feed predicted-model
  preparation.
- ProstT5/Foldseek hits remain independent discovery evidence because the
  current coordinate-registration contract intentionally accepts selected
  direct-PDB hits only. This increment does not invent an unqualified provider
  union.
- Per-crystal first-copy MR still needs a manifest-derived crystal/MTZ dispatch
  and the existing file-based MR-seed checkpoint. It must not be crossed by an
  automatic score decision.

### Accomplishments

- Added the explicit normal-workflow `analysis_stage` boundary. Its default
  `task05` behaviour is unchanged; `discovery` continues through P1 searches,
  direct-PDB coordinate registration, and AFDB/PDB model preparation, then
  stops before first-copy MR.
- Exposed the existing bounded discovery and registration parameters in the
  Nextflow parameter schema and recorded the selected stage in the scope
  output.
- Added an integrated `main.nf` stub run and fully cached resume assertion in
  addition to the retained standalone adapter tests.

### Immutable evidence

- `pixi run --locked check` passes with 356 unit, 57 contract, and 47
  integration tests, plus formatting, lint, strict typing, schemas, public
  controls, documentation, Actions syntax, Nextflow syntax, both stub/resume
  paths, and shell-wrapper validation.
- This is local integration evidence only. No new Viper scientific run was
  launched, no retained candidate was changed, and no human decision was
  inferred.

### Unresolved work

- Commit and push this focused integration increment and require both supported
  Pixi CI jobs to pass.
- Add the smallest manifest-derived per-crystal dispatch and first-copy MR
  prepare stage, then publish and validate the MR-seed checkpoint before
  connecting additional copies or refinement.
- Human Coot and sequence decisions for the retained CD6 package remain
  required before scientific promotion or the three-dataset pilot.

### Next exact starting point

Inspect the focused `analysis_stage=discovery` diff, commit and push it, and
monitor dual-Pixi GitHub Actions. After green CI, derive crystal ID and MTZ paths
from the validated crystal manifest and connect the diverse first-copy workflow
without adding an automatic checkpoint bypass.

## 2026-08-15T15:17:23Z - Normal workflow reaches the MR-seed checkpoint

### Discoveries

- One crystal per structural invocation is the smallest safe normal-workflow
  boundary because both human reviews and all retained scientific outputs are
  crystal-specific. Multi-crystal manifests now fail before first-copy MR rather
  than silently selecting one dataset.
- The existing version-3 retain-all review builder already provides the required
  immutable PDB/MTZ/log package and empty decision template. Only its result
  aggregation needed to move from the qualification wrapper into Nextflow.

### Accomplishments

- Closed the preceding discovery integration at commit
  `1f1eecc7fedd596737954a1a0abf3978cdc5d6a8`; both Pixi 0.74.0 and 0.76.2
  jobs passed in GitHub Actions run `31890986782`.
- Added a manifest-derived crystal dispatch that verifies exactly one crystal,
  resolves relative MTZ paths, checks the completed preflight identity and
  checksum, and publishes a content-addressed dispatch record plus staged MTZ.
- Added the explicit normal-workflow `first_copy` stage. It reuses the qualified
  multi-source funnel and Phaser fan-out, aggregates every candidate result,
  publishes the version-3 MR-seed package, and stops with a header-only approval
  file. No candidate is filtered and no human decision is inferred.

### Immutable evidence

- `pixi run --locked check` passes with 360 unit, 57 contract, and 47
  integration tests, plus formatting, lint, strict typing, schemas, public
  controls, documentation, Actions syntax, Nextflow syntax, integrated
  first-copy stub/resume, standalone workflow stubs, and shell-wrapper checks.
- The integrated stub proves the approval template has exactly one header line
  and that the complete new boundary is cached on `-resume`.
- This is local integration evidence only. No new Viper scientific job ran and
  no retained CD6 candidate or human decision changed.

### Unresolved work

- Inspect, commit, and push this focused first-copy/checkpoint increment, then
  require both supported Pixi CI jobs to pass.
- Human Coot review of the retained CD6 alternatives remains required. The next
  code boundary must validate an explicit MR-seed file before connecting the
  already qualified sequential-copy and T12 workflows.

### Next exact starting point

Run `git diff --check`, inspect the complete focused diff, commit and push it,
and monitor dual-Pixi GitHub Actions. After green CI, add one explicit
post-checkpoint stage that consumes `approved_mr_seeds.tsv`, validates it against
the exact review manifest, and then invokes sequential same-component placement;
do not bypass or fabricate the decision.

## 2026-08-15T16:39:13Z - Normal workflow crosses the MR-seed checkpoint

### Discoveries

- The retained-run M4 staging operation cannot safely be reused by the normal
  workflow because it assumes a site-specific parent layout and exactly 11
  approvals. The normal boundary instead needs only the current review package,
  explicit decisions, and current hypothesis records.
- A first-copy solution coordinate is a rigid-body-derived form of its original
  search model. It can seed the next placement only when the stage records its
  new checksum separately from the original model checksum.
- An approved hypothesis whose expected count is one must remain a finalist but
  must not receive an invalid additional-copy search.

### Accomplishments

- Closed the preceding first-copy checkpoint at commit
  `bc87d491b0b508a64ce60da7a03c14145ce4c40d`; both Pixi 0.74.0 and 0.76.2
  jobs passed in GitHub Actions run `31892783735`.
- Added the `stage-approved-seeds` operation and normal
  `analysis_stage=additional_copy` boundary. It revalidates the exact human
  decision/package/assets, stages every approved inspectable coordinate,
  records original and rigid-body-derived model checksums, applies no numeric
  score filter, and dispatches only candidates that require another copy.
- Connected the staged seeds to the existing one-copy-at-a-time Phaser series.
  The first-copy package remains the immutable checkpoint and no decision is
  fabricated or inferred.

### Immutable evidence

- `pixi run --locked check` passes with 363 unit, 57 contract, and 47
  integration tests, plus formatting, lint, strict typing, schemas, public
  controls, documentation, Actions syntax, Nextflow syntax, the full
  parser-v2 stub suite, cached resume, and shell-wrapper validation.
- The integrated stub proves a missing decision file blocks the new stage, the
  explicit file precedes sequential-copy fan-out, approved one-copy seeds are
  retained without a Phaser job, and the complete path is cached on `-resume`.
- This increment adds no new Viper result and does not change the retained CD6
  candidates or their pending human sequence decisions.

### Unresolved work

- Build the normal live-parent handoff that selects each approved seed's best
  checksum-authenticated retained state after its bounded copy series. It must
  cover expected-one, expected-count-reached, unsupported-addition, and
  candidate-level failure outcomes without interpreting failure as absence.
- Feed every viable retained parent into the already qualified T12
  refinement/map/sequence adapter and publish the empty T12.5 sequence decision
  template with cached resume.
- Human CD6 Coot/sequence decisions, the three-dataset T13.4 pilot, T13.5 review,
  and M6 independent validation remain open.

### Next exact starting point

Implement one normal-workflow retained-parent stage from
`live_m4_stage_manifest.json`, the exact MR review package, and the collected
additional-copy series. Emit checksum-bound T12 finalist rows for every approved
seed, using the original diffraction MTZ for FreeR-preserving refinement, then
connect `BRIEF_REFINEMENT_WORKFLOW`; do not add a new ranking rule.

## 2026-08-15T17:26:21Z - Normal workflow reaches T12

### Discoveries

- A normal retained-parent handoff must represent four distinct outcomes:
  expected-one with no copy transition, expected count reached, an unsupported
  later addition, and a typed tool/parse failure. A missing result bundle is an
  execution failure and must not be converted into evidence that a copy is
  absent.
- The best supported Phaser PDB is the coordinate parent for T12, but its
  solution MTZ is provenance only. Refinement must use the original
  preflight/checksum-bound diffraction MTZ so the FreeR set is preserved.
- Expected-one candidates can be reported without changing the existing typed
  copy-assessment schema; the live stage records a zero-transition terminal
  state while retaining the candidate.

### Accomplishments

- Closed the checkpoint-crossing increment at commit
  `0e59593626c05104c342baa76b4083d279ecbf59`; both Pixi 0.74.0 and 0.76.2
  jobs passed in GitHub Actions run `31896237241`.
- Added the checksum-bound `refinement stage-live` adapter and normal
  `analysis_stage=t12` boundary. It authenticates the explicit approval,
  review assets, hypotheses, contiguous copy series, logs/commands, child
  assets, catalogue crosswalk, MTZ preflight, and Phenix provenance before
  retaining every approved best-supported state.
- Connected those finalists to the existing qualified brief-refinement,
  map-generation, and complete-catalogue sequence-narrowing workflow. The live
  copy report preserves raw typed attempts, applies no numeric filter, and
  states that every parent remains retained and failed addition does not prove
  absence.

### Immutable evidence

- `pixi run --locked check` passes with 368 unit, 57 contract, and 47
  integration tests, plus formatting, lint, strict typing, schemas, public
  controls, documentation, Actions syntax, Nextflow syntax, the complete
  parser-v2 stub matrix, fully cached normal-T12 resume, and shell-wrapper
  validation.
- Focused tests prove expected-one, expected-count-reached,
  unsupported-after-supported, typed tool-failure, and changed-child-checksum
  semantics. This is local integration evidence; no new Viper scientific job
  ran and no retained CD6 decision changed.

### Unresolved work

- Inspect, commit, and push this focused live-T12 increment and require both
  supported Pixi CI jobs to pass.
- Aggregate the normal T12 typed outputs into the qualified T12.5 top-10,
  top-25, full-results, asset, HTML, and header-only second-decision package,
  then prove cached resume without fabricating a sequence approval.
- Human CD6 Coot/sequence decisions, the three-dataset T13.4 pilot, bounded
  T13.5 review, and M6 independent validation remain open.

### Next exact starting point

Run `git diff --check`, inspect the complete focused diff, commit and push it,
and monitor dual-Pixi GitHub Actions. After green CI, add the smallest normal
T12 result aggregation and T12.5 checkpoint builder; do not begin the
three-dataset pilot before the second file-based checkpoint is present.

## 2026-08-15T18:09:10Z - Normal workflow reaches the T12.5 checkpoint

### Discoveries

- The retained-run T12.5 builder cannot be reused by inventing a Slurm result
  for a normal Nextflow execution. The normal boundary must authenticate the
  live stage and per-finalist typed directories directly while preserving the
  existing scheduled-run verification path.
- A typed refinement, sequence-tool, parse, or no-hit outcome is still a
  retained finalist outcome. It can produce no sequence-score row, but its
  stage parent, reflection provenance, result records, command, and logs must
  remain explicit instead of disappearing from the second checkpoint.

### Accomplishments

- Closed the normal-T12 increment at commit
  `55438a8fa75af7aa2b6f7279755f8e28c92a4fe6`; both Pixi 0.74.0 and 0.76.2
  jobs passed in GitHub Actions run `31898375845`.
- Added the normal `review build-live-sequence-checkpoint` adapter and
  `BUILD_LIVE_SEQUENCE_CHECKPOINT` process. `analysis_stage=t12` now publishes
  top-10, top-25, full-score, HTML, Coot-asset, provenance, and per-finalist
  evidence views after the T12 fan-out.
- The package retains every staged finalist and typed failure, applies no
  ranking filter, and writes a header-only `approved_sequence_groups.tsv`.
  The existing checksum-gated retained-HPC builder remains scheduler-specific.

### Immutable evidence

- `pixi run --locked check` passes with 371 unit, 57 contract, and 47
  integration tests, plus formatting, lint, strict typing, schemas, public
  controls, documentation, Actions syntax, Nextflow syntax, the complete stub
  matrix, normal T12-to-T12.5 publication, fully cached resume, and shell
  wrapper validation.
- Focused tests cover successful normal packaging, typed-failure retention,
  changed-parent rejection, empty approval semantics, and self-contained stage,
  command, log, reflection, and Coot-asset evidence.

### Unresolved work

- Inspect, commit, and push this focused normal-T12.5 increment and require
  both supported Pixi CI jobs to pass.
- Human Coot review and sequence-group decisions for the 11 retained CD6
  alternatives remain the next scientific gate. The three-dataset T13.4 pilot,
  T13.5 bounded review, Prototype 0.2 assessment, and M6 remain open.

### Next exact starting point

Run `git diff --check`, stage only the normal T12.5 code, tests, and docs,
commit and push the coherent increment, and monitor dual-Pixi CI. Once green,
use the existing self-contained CD6 checkpoint for the explicit human decision;
do not infer an approval from sequence score or refinement statistics.

## 2026-08-15T18:18:15Z - Normal T12.5 milestone closed green

### Discoveries

- The verified CD6 checkpoint contains 11 structural alternatives and 107
  unique sequence-group candidates in its bounded approval-candidate view. The
  decision template remains header-only, so no scientific identity or
  single-component-assumption decision can be inferred from current files.

### Accomplishments

- Committed and pushed the normal T12.5 connection as
  `f0fdc9f848c6e28d019e396db6fa33747a357a04`.
- Both Pixi 0.74.0 and 0.76.2 jobs passed in GitHub Actions run
  `31900398849`. The worktree is clean and the normal workflow now stops at a
  complete, deterministic second human checkpoint.

### Immutable evidence

- Local locked checks remain green with 371 unit, 57 contract, and 47
  integration tests plus the complete cached-resume workflow matrix.
- The accepted real CD6 checkpoint remains
  `seqreview_69c4c2705c35a12bc104581c4444076cee91daae13d0a3a354d0a20e8a000c07`;
  this increment changed orchestration, not the retained scientific evidence.

### Unresolved work

- A human must inspect the 11 CD6 PDB/MTZ/map alternatives in Coot, record
  explicit sequence-group decisions, and assess the `ASU = nA` assumption.
- T13.4 must not begin until that checkpoint is recorded. T13.5, the Prototype
  0.2 assessment, and M6 remain downstream.

### Next exact starting point

Open the accepted checkpoint report and linked assets. Add explicit `approve`,
`reject`, `defer`, or `retain_alternative` rows to its
`approved_sequence_groups.tsv`, and provide the assessed prototype-assumption
status. Then rebuild T13.1/T13.2 and start the clean immutable three-dataset
T13.4 pilot without changing ranking thresholds from CD6 alone.

## 2026-08-15T19:56:11Z - Fast type checking migrated from mypy to ty

### Discoveries

- Active mypy use was confined to the Pixi development dependency/task,
  `pyproject.toml` configuration, source suppressions, and its local cache.
  Historical reports remain unchanged because they accurately record gates that
  ran mypy at those revisions.
- `ty` cannot discover Gemmi's compiled-extension symbols. Treating only the
  `gemmi` import as `Any` preserves the previous checker boundary without
  suppressing other unresolved attributes or argument errors.
- The migration exposed a few checker-independent clean-ups: dynamic Pydantic
  writers now verify `model_dump` is callable, dataclass test variants use
  `dataclasses.replace`, and the deprecated HTTP error accessor is gone.

### Accomplishments

- Replaced mypy with locked `ty 0.0.71` for both Linux x86-64 and macOS ARM64.
  The existing `typecheck` interface now runs `ty check` over Python 3.14
  sources and tests while excluding frozen fixtures.
- Removed active mypy-specific suppressions, configuration, cache ignore, and
  the local generated cache. Added only two narrow `ty` suppressions for the
  generic Pydantic class method that the checker cannot express.
- Preserved workflow and scientific behaviour; no retained CD6 evidence,
  candidate decision, threshold, or HPC state changed.

### Immutable evidence

- `pixi run --locked typecheck` passes with no diagnostics.
- `pixi run --locked check` passes with 371 unit, 57 contract, and 47
  integration tests plus formatting, Ruff lint, schemas, public controls,
  documentation, Actions syntax, Nextflow syntax, the complete parser-v2
  stub/resume matrix, and shell-wrapper validation.
- The lock contains `ty 0.0.71` artefacts for both supported platforms and no
  installed mypy package. A remaining `mypy` string is inert optional metadata
  declared by the third-party `rfc8785` wheel.

### Unresolved work

- Inspect and commit this focused tooling migration, push it, and require both
  supported Pixi CI jobs to pass.
- The next scientific gate remains human Coot review and explicit
  sequence-group decisions for the 11 retained CD6 alternatives before T13.4.

### Next exact starting point

Run `pixi run --locked docs-check` and `git diff --check`, commit and push the
focused ty migration, and monitor dual-Pixi GitHub Actions. After green CI,
return directly to the existing CD6 human decision checkpoint.

## 2026-08-15T20:03:47Z - ty migration closed green

### Discoveries

- Both supported Pixi releases resolve and execute the same locked `ty 0.0.71`
  environment; no CI-only typing or platform issue appeared.

### Accomplishments

- Committed and pushed the mypy-to-ty migration as
  `f833fbaa4b1e4170a6316599c5b82db57eb2f555`.
- Both Pixi 0.74.0 and 0.76.2 jobs passed in GitHub Actions run
  `31905368531`. The worktree was clean after the push.

### Immutable evidence

- The complete local locked gate and both remote CI jobs passed against the
  same source commit and lock file.

### Unresolved work

- The human CD6 Coot and sequence-group decision remains the next scientific
  gate; T13.4 must not start before that explicit checkpoint is recorded.

### Next exact starting point

Open the retained CD6 checkpoint, review all 11 alternatives, and record the
sequence-group decisions plus the assessed `ASU = nA` status. Then rebuild
T13.1/T13.2 and begin the immutable three-dataset pilot.

## 2026-08-16 - CD6 checkpoint scientific caveat and report corrections

### Discoveries

- `CD6QS2P2G1_5` is an experimental crystal/diffraction-dataset identifier,
  not a known protein, gene, or PDB structure used as a truth-labelled positive
  control.
- The crystal contents remain unknown. CD6 may contain a heteromer, contaminant,
  cleavage product, or another component inconsistent with the prototype's
  `ASU = nA` single-component assumption. It is therefore a useful realistic
  challenge case but may not be ideal for validating the prototype by itself.
- Matthews coefficients can rank physically plausible copy counts using the
  unit cell, space group, ASU volume, and each candidate sequence mass. They do
  not prove molecular identity, homomeric composition, or `ASU = nA`.
- The retained checkpoint exposed three report gaps: it omitted the mFo-DFc
  difference map, did not carry Matthews/ASU context forward, and did not show
  the source genome's gene/product annotations or explain that the
  `sequence_from_map.pdb` file is a map-derived assignment hypothesis rather
  than an independently refined model.

### Accomplishments

- Began the focused checkpoint correction while preserving all candidates and
  all duplicate sequence-to-locus mappings. No CD6 identity or prototype
  assumption has been approved automatically.

### Unresolved work

- Complete and validate the dual-map, Matthews, genome-annotation, and report
  semantic changes; run the locked checks and real Viper T12 replay before
  replacing the current human-review package.
- A separate truth-labelled monomeric/homomeric positive control is still
  needed alongside CD6 to validate the single-component assumption reliably.

### Next exact starting point

Finish the focused T12/T12.5 implementation and tests, then run
`pixi run --locked check` before committing the correction milestone.

## 2026-08-16T00:25:07Z - Prokaryotic homomer control panel expanded

### Discoveries

- Restricting the truth-labelled panel to methanogens and methanotrophs was not
  scientifically necessary for the single-protein-species workflow. Public
  prokaryotic proteins are suitable when the deposited reflections, catalogue
  sequence, construct mapping, and ASU composition are independently frozen.
- The existing panel already supplied nine `ASU = nA` positives spanning one to
  six ASU copies. Two bacterial structures add useful independent cases without
  proliferating controls: tagged single-copy MreB (1JCF) and exact full-length
  two-copy RsbX (3W45).
- A negative result needs an explicit truth condition. An unrelated model may
  remain inspectable and must not displace ground truth, whereas a target-absent
  or wrong-catalogue run must not invent a reportable catalogue identity.

### Accomplishments

- Expanded the source panel to 12 structures: 11 positive single-protein-species
  ASUs and the retained 6CXH heteromeric assumption-violation control.
- Added a versioned 23-case workflow matrix containing all 11 positives, seven
  size-matched unrelated-model controls, two target-absent controls, two
  wrong-catalogue controls, and the heteromeric abstention case. Every positive
  must occur exactly once and all alternatives remain reviewable.
- Downloaded and checksum-verified the public coordinate and structure-factor
  sources, derived deterministic Gemmi 0.7.5 MTZ files, and confirmed that all
  12 prepared entries revalidate without network access.

### Immutable evidence

- The tracked panel and workflow-suite SHA-256 values are
  `80fed6487cbeee190e2ae09053147669a40f4cc10708dbde179cc5fbdf14b8ba`
  and `ebfc3a1c710596b712ed76ff9f13fc438db0a2de1aa60cca51011cf5241e868d`.
- The new 1JCF and 3W45 MTZ SHA-256 values are
  `5ffad9350783b19dec15e5cc46ea71966f46753f898f953191960f37d5eede2f`
  and `9f984c3c3211d801d49c7cf3ab144ab73f3490de8ad09e6a305e85ab365cbfc6`.
- `pixi run --locked check` passed with 374 unit, 57 contract, and 47
  integration tests plus formatting, lint, `ty`, schemas, documentation,
  Actions, Nextflow syntax/stub/resume, public-panel, and shell-wrapper checks.
  The focused final invariant test then passed 13/13 public-control tests.

### Unresolved work

- The eight source-qualified positives still require independent exact/homolog
  model selection and licensed-Phenix execution before promotion to runnable
  controls. Start with 1JCF and 3W45 rather than launching all 23 scenarios at
  once.
- These public structures are operational controls, not leakage-controlled
  evidence of generalisation. CD6 remains a separate unknown-composition
  challenge and must not substitute for a truth-labelled positive.

### Next exact starting point

Commit and push this focused panel/matrix increment and require both supported
Pixi CI jobs to pass. Then prepare the smallest real Viper smoke slice containing
1JCF and 3W45 positives plus one case from each negative class before expanding
to the complete 23-case matrix.

## 2026-08-16T00:37:13Z - Prokaryotic control milestone closed green

### Discoveries

- The expanded panel and five-class workflow matrix behave identically under
  both supported Pixi releases; no platform-specific validation or preparation
  issue appeared.

### Accomplishments

- Committed and pushed the prokaryotic homomer controls as
  `88637396076745f35e516f5c390e3e254568de26`.
- Both Pixi 0.74.0 and 0.76.2 jobs passed in GitHub Actions run `31917398119`.
  The checksum-frozen 12-entry source cache also passed offline revalidation.

### Immutable evidence

- GitHub Actions jobs `95091493574` and `95091493639` completed successfully
  against the exact pushed commit.
- The tracked workflow matrix contains 23 truth-labelled cases and the panel
  validator requires all 11 positive controls exactly once.

### Unresolved work

- Promote 1JCF and 3W45 from source-qualified to runnable by freezing their
  independent model selections and exercising them with the licensed Viper
  Phenix runtime. Then run the four negative classes on the smallest smoke
  slice before scaling to the full matrix.

### Next exact starting point

Create the focused runnable-control specifications for 1JCF and 3W45, validate
their frozen proteomes and independent search models, and submit the minimal
Viper positive/negative smoke slice. Do not use the unknown CD6 crystal as the
truth-labelled acceptance control.

## 2026-08-16T09:24:48Z - Six-case control slice and Phenix map labels frozen

### Discoveries

- Phenix 2.1 rewrites two unlabeled map-coefficient blocks to internal labels
  that differ from the old verifier's expected hyphenated labels. Requesting
  the standard Coot-compatible `2FOFCWT`/`PH2FOFCWT` and
  `FOFCWT`/`PHFOFCWT` pairs removes that ambiguity without weakening the
  requirement for both maps.
- The offline 1JCF and 3W45 preparations reproduce every frozen source,
  proteome, model, and MTZ checksum. Their exact and independent homolog models
  are therefore ready for a licensed-Phenix Viper execution boundary.
- The smallest scientifically balanced slice is six cases: two positives and
  one wrong-model, target-absent, wrong-catalogue, and assumption-violation
  case. It exercises every outcome class without paying for all 23 cases first.

### Accomplishments

- Promoted 1JCF and 3W45 to runnable controls with checksum-frozen exact and
  homolog model specifications. Offline preparation produced MTZ SHA-256
  `5ffad9350783b19dec15e5cc46ea71966f46753f898f953191960f37d5eede2f`
  and `9f984c3c3211d801d49c7cf3ab144ab73f3490de8ad09e6a305e85ab365cbfc6`.
- Added and validated `prokaryote_homomer_smoke_v1`: `POS_1JCF`, `POS_3W45`,
  `NEG_MODEL_3W45_6HF7`, `NEG_ABSENT_3W45`,
  `NEG_CATALOGUE_3W45_1JCF`, and `NEG_ASSUMPTION_6CXH`. The panel contract
  requires exactly two runnable positives and one case from every remaining
  class, with each negative bound to its matched positive context.
- Updated the brief-refinement protocol to require the four standard Coot MTZ
  coefficient labels while preserving separate 2mFo-DFc and mFo-DFc maps.
- Created the 30-minute task `continue-prokaryotic-control-roadmap`; it resumes
  this exact slice before expanding to the tracked 23-case matrix.

### Immutable evidence

- Both public controls passed offline preparation against their frozen
  proteomes and source assets. Exact/homolog model SHA-256 values are
  `00ef1bc62689f6fd6183ef6c73913abe8dca72289a00f490129fb39b16d5918f` /
  `aa17264da3d7caac140b18fcdca2cc8e6926f10681eef4deee3266e3dd16c3c3`
  for 1JCF and
  `4cc94c96e03373e9412c47887d0a120658bfd39a131e50da4a1d0e92bc80a3be` /
  `aa06a85ccb2a2ba28b1c9e06a4623413d59ed32b52490c8fe434825170f479a3`
  for 3W45.
- `pixi run --locked check` passes with 378 unit, 57 contract, and 47
  integration tests plus formatting, Ruff, `ty`, schemas, the public panel,
  documentation, Actions, Nextflow syntax/stub/resume, and shell-wrapper gates.

### Unresolved work

- Add the smallest checksum-gated Viper staging/execution boundary for the
  fixed six cases. Run the exact and homolog positives through production
  Phenix adapters, continue the two-copy 3W45 case through sequential
  placement and T12, and emit typed no-identity/abstention evidence for the
  three catalogue/assumption controls. Do not add general fallback machinery.
- Run one full locked gate, one focused commit/push, one CI watch, then deploy
  and submit the real Viper slice. Expand the same boundary to all 23 cases only
  after the six-case result is accepted.

### Next exact starting point

Implement the fixed local evidence archive and site-isolated Viper stage for
`benchmarks/public-controls/homomer_smoke_slice.yaml`, reusing the existing
first-copy, sequential-copy, and brief-refinement adapters. Accept no arbitrary
case list or data root, retain every model outcome, and keep 6CXH as a typed
`ASU = nA` abstention rather than a reconstruction target.

## 2026-08-16T09:48:25Z - Fixed six-case import archive implemented

### Discoveries

- The six-case execution boundary needs only the two frozen positive-control
  proteomes and MTZ files, their exact and homolog models, and one unrelated
  6HF7 chain-A model. The target-absent, wrong-catalogue, and 6CXH abstention
  cases can be derived from this fixed inventory without transferring a general
  catalogue or exposing caller-selected paths.
- The independently cleaned 6HF7 chain-A polymer contains 191 observed
  residues and 1,498 atoms. Its deterministic model SHA-256 is
  `2ef5d135307a6a54d7dfce07abe63c9cf20d04cb648fd09b12d19fb4f34e98de`.
- GitHub Actions run `31939333747` closed the preceding runnable-control
  milestone successfully under both supported Pixi releases. This closure is
  carried here rather than creating a documentation-only follow-up commit.

### Accomplishments

- Added a fixed, regular-file-only, checksum-inventoried control-slice archive
  builder. It accepts no case list or evidence root, validates the tracked
  panel/suite/slice identity, verifies every frozen input checksum, and records
  the derivation semantics for all six cases.
- Added focused tests for the archive inventory, unsafe member paths, and
  symlink rejection. The focused control tests pass 19/19 and project `ty`
  type checking passes.
- Built the real local archive from the frozen evidence cache. The 2,177,558
  byte archive contains six cases and has SHA-256
  `2cf8dea23e3c825bb6f7bf590058b7ffbdce291ba80b508418448c38e2f027b7`;
  its embedded import-manifest SHA-256 is
  `d974536ed6b8168ada0498662575522119ba7924258f0f7d9e92516f87b7b46b`.

### Immutable evidence

- The builder revalidated the 1JCF and 3W45 proteomes, MTZ files, and all four
  exact/homolog model checksums before creating the archive.
- The unrelated-model derivation is anchored to 6HF7 coordinate SHA-256
  `14abeb9760258361183bee3505693ef5d69c366506cc08f77d2ae55ca405e109`
  and observed-sequence SHA-256
  `01647f27a2bdd08feff355166b37a6789aadbd556e82c3e4825bad39bfdab7a7`.

### Unresolved work

- Add the Viper controller and remote-dispatcher operation that accepts this
  fixed bounded archive, validates and stages it under one immutable run, and
  exposes no arbitrary source or destination paths.
- Add the smallest six-case scheduled execution/report boundary, then run one
  complete locked gate, one commit/push, one CI watch, and one real Viper run.
  Do not expand to the 23-case matrix before this slice is accepted.

### Next exact starting point

Add `control-slice-stage` to the reviewed local controller and Viper remote
dispatcher, streaming only the fixed archive produced by
`build_fixed_control_slice_bundle`; validate its six case IDs and complete
checksum inventory before marking the immutable run staged.

## 2026-08-16T10:03:01Z - Viper six-case stage boundary closed locally

### Discoveries

- The normal scientific `stage` operation is the wrong interface for the
  control slice because it would expose a profile without binding its evidence.
  A dedicated operation can instead create the immutable source checkout and
  accept exactly one bounded archive on standard input.
- The nine transferred scientific assets are sufficient for the five real
  first-copy Phaser attempts: exact and homolog models for both positives plus
  the unrelated 6HF7 model against 3W45. Target-absent, wrong-catalogue, and
  assumption-violation outcomes remain fixed derivations rather than redundant
  structure searches.

### Accomplishments

- Added `control-slice-stage` to the controller and CLI with no case, evidence
  root, source, or destination arguments. It is Viper-only and creates a
  site-tagged `gtd-control-slice-*` run record.
- Added the remote import boundary. It validates the exact six ordered case
  IDs, exact nine-asset archive inventory, embedded-manifest checksum, every
  asset checksum and size, fixed retention policy, regular-file status, and
  path containment before changing the run phase to `staged`.
- Kept submission closed until the scientific execution body exists; both the
  local controller and remote dispatcher reject a `control-slice` submission
  rather than allowing a false successful no-op.

### Immutable evidence

- The focused archive/controller/CLI/policy/public-control suite passes 84/84.
  Project `ty` type checking passes, and all three reviewed HPC shell scripts
  pass `bash -n`.
- Collection now includes the small stage manifest, stage log, case count, and
  archive/manifest identities without collecting the transferred model or MTZ
  payloads.

### Unresolved work

- Implement the minimal scheduled execution body: prepare the fixed first-copy
  contracts, run the five real Phenix attempts, retain every parsed outcome,
  derive the target-absent/wrong-catalogue/6CXH typed cases, and continue the
  best-supported 3W45 parents through copy two and T12.
- Only after that body and its focused tests are complete should the repository
  run one full locked gate, create one coherent commit, push once, and watch CI
  once before deploying and staging on Viper.

### Next exact starting point

Add one fixed control-slice runtime preparer that consumes only the validated
`artifacts/control-slice-inputs` tree and the configured Phenix manifest. Emit
the two MTZ preflights, target sequence groups, processed-model registry, and
five first-copy hypotheses needed by a small scheduled workflow; do not add a
general benchmark-runner abstraction.

### Compaction-safe roadmap invariant

- The five first-copy Phaser attempts are only the execution-bearing portion
  of the six-case smoke slice: exact and homolog models for 1JCF and 3W45, plus
  the unrelated 6HF7 model against 3W45. `NEG_ABSENT_3W45` must remain a typed
  target-absent boundary outcome, and `NEG_ASSUMPTION_6CXH` must remain an
  `ASU = nA` abstention; neither may be converted into a fabricated MR search.
- Acceptance of this smoke slice immediately unlocks expansion of the same
  fixed boundary to the already defined 23-case matrix: **11 positives, seven
  wrong-model controls, two target-absent controls, two wrong-catalogue
  controls, and one heteromeric assumption-violation/abstention case**.
- The 23-case expansion is part of the active single-component prototype goal,
  not optional follow-up polish. Context compaction must not narrow the goal to
  the six-case slice. Retain every candidate and use LLG/TFZ for ranking only.
- The six-case slice validates only one- and two-copy mechanics and must never
  be described as general multi-copy validation. The 23-case matrix must
  execute its truth-labelled positive controls across ASU copy counts 1, 2, 3,
  4, and 6, including 7P50/6HF7 (three), 8Q5T (four), and 7L6G (six), and must
  assess retention against the expected count rather than first-copy success.
- User-confirmed terminal scope: continue development through implementation
  and real Viper execution of the complete 23-case matrix. A successful
  six-case Slurm run is an intermediate feedback gate and must be followed by
  the 23-case fixed archive, execution, evidence collection, and correction
  loop; it is not completion of the active goal.

## 2026-08-16T10:27:36Z - Six-case real-Phenix execution boundary ready

### Discoveries

- The five real first-copy searches are the exact and homolog models for 1JCF
  and 3W45 plus the unrelated 6HF7 model against 3W45. The target-absent and
  6CXH cases are identity/assumption boundaries and must not fabricate Phaser
  work merely to increase the search count.
- Gemmi reports modified residues such as selenomethionine with a lower-case
  one-letter code. Canonical upper-case normalisation is required before the
  sequence-derived mass contract can assess an experimental search model.
- The six-case slice covers expected ASU counts one and two only. The frozen
  23-case matrix provides the required higher-copy controls at counts three,
  four, and six; smoke success cannot be claimed as multi-copy validation.

### Accomplishments

- Implemented the fixed Viper runtime for five real first-copy Phenix attempts,
  all supported 3W45 copy-two transitions, and T12 refinement/sequence
  assessment of every supported copy-two child. First-copy, copy-two,
  refinement, sequence, and six typed case records are retained separately.
- A truth-labelled two-copy positive now requires a supported second copy; a
  packed first copy alone is insufficient. Candidate retention and the policy
  that LLG/TFZ are ranking annotations only remain explicit.
- Added the checksum-gated site-isolated stage, 8-CPU/32-GB/24-hour submit
  profile, bounded collection inventory, and focused scientific regression for
  modified-residue sequence normalisation.

### Immutable evidence

- The current fixed archive has six cases, nine scientific assets, size
  2,177,793 bytes, archive SHA-256
  `3526f819ec3e69b16afd2fe444f6f6bc0b4b099d067cdfc9293e086a2c1dd892`,
  and manifest SHA-256
  `3bf849dc6fb1516c6a9c52599a1d2f71c0e718859bf8c6868b97a0edaf09e524`.
- A real-data local preparation proof emitted exactly five hypotheses with
  expected counts 1, 1, 2, 2, and 2. The complete locked gate passes 387 unit,
  57 contract, and 47 integration tests plus formatting, Ruff, `ty`, schemas,
  public-panel, docs, Actions, Nextflow syntax/stub, and HPC wrapper checks.

### Unresolved work

- Commit and publish this coherent boundary once, deploy checksum-reviewed
  tools, stage and submit the six-case Viper run, then monitor and correct only
  evidence-backed failures through its next Slurm attempt.
- After smoke acceptance, implement and execute the complete fixed 23-case
  matrix. Its positive acceptance must exercise expected ASU counts 1/2/3/4/6;
  all 11 positives and every negative/abstention case remain in scope.

### Next exact starting point

Inspect the staged diff, create the focused execution-boundary commit, push and
watch one GitHub Actions run, then deploy, run `control-slice-stage`, submit the
returned immutable run ID, and attach the 30-minute monitor to that run.

## 2026-08-16T10:37:49Z - Six-case Viper attempt running; 23-case goal retained

### Discoveries

- The installed local controller zipapp predated the new staging operation even
  though the remote tools were current. Rebuilding and checksum-verifying the
  reviewed zipapp restored the intended fixed wrapper boundary; this was a
  local launch-tool version mismatch, not a Viper or scientific failure.
- The user has standardised future CI execution on Pixi 0.76.2 to avoid
  redundant same-version checks. Preserve that workflow update when it appears
  in the local source and do not recreate the old two-version matrix.

### Accomplishments

- Published green commit `dda0180cd94dc8e79605661c61506ed52a2e152d` and
  completed GitHub Actions run `31941761025`. Deployed dispatcher SHA-256 is
  `29000d7eebf2cc1d385f05565901ebbff003336cf2bed3edaa613c5735156f5b`
  and job-wrapper SHA-256 is
  `ee538a37586176b535b2821f4b7818be357433a0ab0e077e9d38fea9e25d76bd`.
- Installed local reviewed controller SHA-256
  `b3062af7cbacfae7bdc104c39ce1406444c7af5f649c24379caa9ad101598c8f`.
- Staged and submitted the immutable six-case control slice on Viper. The
  30-minute continuation now binds the exact run and retains the complete
  23-case implementation/execution goal after smoke acceptance.

### Immutable evidence

- Active run: `gtd-control-slice-20260816T103617Z-dda0180cd94d-a6450e4a`,
  Slurm job `10930288`, source commit `dda0180cd94dc8e79605661c61506ed52a2e152d`,
  archive SHA-256
  `a1833a232580936750f8433d7b85da4e41391e3cd0af5ba3b6c5c370766e64d4`,
  and import-manifest SHA-256
  `3bf849dc6fb1516c6a9c52599a1d2f71c0e718859bf8c6868b97a0edaf09e524`.
- The wrapper reports scheduler state `RUNNING`, terminal `false`; no failure is
  inferred from the absence of further output.

### Unresolved work

- On terminal evidence, collect and verify all five searches, six typed cases,
  supported 3W45 copy-two transitions, T12 outputs, checksums, provenance, and
  candidate-level failures. Fix only demonstrated software failures and submit
  the next attempt before returning to scheduled monitoring.
- After smoke acceptance, implement and execute the entire fixed 23-case
  matrix, including positive ASU copy counts 1/2/3/4/6. Do not end the active
  goal at the smoke result.

### Next exact starting point

Read this entry, query only the active run through the reviewed wrapper, and
leave it untouched while non-terminal. If terminal, inspect bounded logs and
collect; otherwise let the 30-minute continuation recur. After accepted smoke
evidence, begin the fixed 23-case archive/runtime increment immediately.

## 2026-08-16T11:17:11Z - Complete 23-case Viper matrix boundary ready

### Discoveries

- The terminal six-case job completed successfully at the scheduler/tool level,
  but all five exit-zero Phaser attempts were classified `failed_parse` because
  Phenix 2.1-6048 omitted the legacy final solution-count line. Complete top
  PDB/MTZ pairs remain valid bounded evidence; marker-free empty output does not.
- Real preparation of the full public matrix exposed standard anomalous MTZ
  amplitude types `G/L` in 7L6G and the modified residue KYN. Preflight must
  pair anomalous signs exactly, and KYN must remain in the observed model as W.
- The user-standardised launcher/CI version is Pixi 0.76.2 only. The previous
  two-version CI matrix is no longer part of the active policy.

### Accomplishments

- Added the fixed 23-case archive and runtime: 11 positives, seven wrong-model
  searches, five typed boundary outcomes, sequential placement through expected
  ASU counts 1/2/3/4/6, T12 for packed positives, and retain-all case evidence.
- Added a Viper-only `control-matrix-stage` operation with no arbitrary roots or
  case selection, exact case/distribution/copy-count validation, 64-CPU/192-GB/
  24-hour submission, bounded Phaser tails, checksums, and collection paths.
- Added narrow regressions for marker-free complete Phaser output, anomalous
  `G/L` observation selection/sign pairing, and KYN model normalisation.

### Immutable evidence

- The local archive contains exactly 23 cases and 34 regular members. Its
  current dry-run size is 21,143,071 bytes, archive SHA-256
  `a2ca7ad6f7c4b1e4f30852a2c155ef03637334d11c877e85b4ebe93322d1b84a`,
  and embedded-manifest SHA-256
  `97132162e558df1c9087aab1826a32e954eb3477b2b241eb9930b0655cf74b40`.
- Real local preparation emitted 11 usable MTZ preflights and 18 first-copy
  hypotheses, including all 11 positives and expected counts 1, 2, 3, 4, and 6.
- The complete locked gate passes 394 unit, 57 contract, and 47 integration
  tests plus formatting, Ruff, `ty`, schemas, public-panel, docs, Actions,
  Nextflow syntax/stub, and HPC-wrapper checks.

### Unresolved work

- Publish this coherent commit once, watch the single Pixi 0.76.2 CI job, deploy
  checksum-reviewed tools, stage and submit the fixed matrix on Viper, and
  monitor terminal evidence without cancelling or inferring failure from silence.
- The matrix is operational same-structure evidence. Leakage-controlled
  generalisation remains a later M6 validation activity.

### Next exact starting point

Inspect and stage only this milestone, commit and push once, watch one GitHub
Actions run, deploy tools from that green commit, run `control-matrix-stage`,
submit the returned run ID with profile `control-matrix`, and replace the stale
continuation with a 30-minute monitor for that exact retained Viper run.

## 2026-08-16T11:29:48Z - Complete 23-case Viper matrix submitted

### Discoveries

- The installed local controller again predated the new fixed staging
  operation. Rebuilding the reviewed zipapp from the green source commit was
  sufficient; no remote or scientific source change was required.
- The final tar archive checksum differs from the earlier local dry-run archive
  checksum because the archive container is rebuilt, while the canonical
  embedded manifest checksum is unchanged. The staged run record is the
  authoritative archive identity for this immutable attempt.

### Accomplishments

- Published green source commit
  `7705252f7ceeaa359514814b6def5b0d4af591d8`; GitHub Actions run
  `31943979431` passed its single Pixi 0.76.2 job.
- Deployed the reviewed remote tools and installed a checksum-matched local
  controller. Staged and submitted the complete fixed 23-case matrix on Viper.
- Replaced the obsolete six-case continuation with a 30-minute monitor bound
  only to this retained matrix run. The monitor preserves the complete case
  distribution, expected ASU counts 1/2/3/4/6, retain-all policy, and the
  evidence-backed correction loop across future context compactions.

### Immutable evidence

- Active run:
  `gtd-control-matrix-20260816T112741Z-7705252f7cee-423f9da8`, Slurm job
  `10930411`, source commit
  `7705252f7ceeaa359514814b6def5b0d4af591d8`, nf-helper commit
  `82431e4c56cb4cd2ef4ea67321fd01fad7ba65cb`, suite
  `prokaryote_homomer_workflow_v1`, 23 cases, 11 positives, and 18 real
  searches.
- Staged archive SHA-256 is
  `745cf9edab377d2327cfb1d25e9dcd90f881e7bd8954461cc0d5f8029e6f9e0d`;
  canonical embedded-manifest SHA-256 is
  `97132162e558df1c9087aab1826a32e954eb3477b2b241eb9930b0655cf74b40`.
- Local controller SHA-256 is
  `fc1fa0715427cc6da258a68708ac40f4b32471a9465d07cc44131b221df925c9`.
  Deployed dispatcher, job-wrapper, and recovery SHA-256 values are
  `cfbf35429714fe084a3abc0a74e374e7997e6f6718d6b7382c4c18162abe73ec`,
  `c74aa2a65d3fa1b386d9519acb5abc37567ae4ea58cdcd95fe3b1aef7cff289b`,
  and `0db4c5f3542ce4d387ac019e33717d5e405ac957efb216b05c52828a851808f4`.
- The reviewed wrapper reported scheduler state `PENDING`, terminal `false`.
  Queue waiting is not interpreted as failure.

### Unresolved work

- On terminal evidence, inspect bounded logs and collect through the reviewed
  wrapper. Verify exactly 23 typed cases, 18 first-copy attempts, 11 positives,
  seven wrong-model searches, five typed boundary cases, positive transitions
  through expected ASU counts 1/2/3/4/6, all downstream records, checksums,
  provenance, and candidate-level failures.
- Fix only demonstrated software failures, then complete one accelerated local
  gate/commit/push/CI/deploy cycle and reach the next Slurm attempt before
  returning to monitoring. Do not drop candidates or use LLG/TFZ as an
  acceptance filter.

### Next exact starting point

Run `/Users/asuq/.local/bin/nf-gtd-hpc-test --no-progress status --run-id
gtd-control-matrix-20260816T112741Z-7705252f7cee-423f9da8`. If non-terminal,
leave the retained run untouched. If terminal, run bounded `logs --tail 200`,
then `collect`, and classify the complete evidence before changing source.

## 2026-08-16T12:06:36Z - Complete matrix remains queued; heartbeat transferred

### Discoveries

- The reviewed status operation still reports the retained run as scheduler
  state `PENDING`, phase `submitted`, and terminal `false`; both `exit_code` and
  `failure_class` remain empty. Queue waiting is not software-failure evidence.
- Exactly one matching 30-minute heartbeat exists. Its durable prompt already
  names only the retained 23-case run, but it was paused and still attached to
  the preceding task.

### Accomplishments

- Left Slurm job `10930411` and its retained run untouched: no logs, collection,
  cancellation, cleanup, timeout inference, or replacement submission was
  attempted while the run is non-terminal.
- Transferred the existing `continue-prokaryotic-control-roadmap` heartbeat to
  the current task and resumed it at the existing 30-minute cadence. No duplicate
  monitor was created.
- Preserved this uncommitted journal update for the next coherent code/evidence
  milestone; no documentation-only commit or CI run was created.

### Immutable evidence

- Status was checked through the reviewed wrapper for run
  `gtd-control-matrix-20260816T112741Z-7705252f7cee-423f9da8`: operation
  `status`, profile `control-matrix`, phase `submitted`, scheduler state
  `PENDING`, terminal `false`, job `10930411`.
- The retained source, nf-helper, archive, embedded-manifest, controller, and
  deployed-tool identities remain those recorded in the preceding entry; no
  immutable run field changed.

### Unresolved work

- Wait for terminal evidence. On a later terminal status, run only bounded
  `logs --tail 200`, then `collect`, and verify the complete fixed 23-case
  evidence boundary before considering any source edit.
- Retain all candidates and keep LLG/TFZ as ranking annotations only. These
  operational same-structure controls still cannot establish generalisation.

### Next exact starting point

Run `/Users/asuq/.local/bin/nf-gtd-hpc-test --no-progress status --run-id
gtd-control-matrix-20260816T112741Z-7705252f7cee-423f9da8`. If it remains
non-terminal, leave it untouched. If it is terminal, run bounded
`logs --tail 200`, then `collect`, and classify the complete evidence before
editing source.

## 2026-08-16T12:12:29Z - Control-matrix scheduler request is oversized

### Discoveries

- The user's scheduler observation is confirmed by the immutable source:
  `control-matrix` requests 64 CPUs, 192 GB, and 24 hours. The job wrapper also
  refuses any CPU allocation other than 64, so this is an intentional fixed
  profile rather than a scheduler display artefact.
- The matrix runner executes at most seven Phenix attempts concurrently. Under
  the current request it assigns nine threads to each attempt and can use at
  most 63 of 64 CPUs. Earlier real first-copy evidence supports four CPUs and
  eight GB per concurrent Phaser attempt; therefore 32 CPUs and 64 GB would
  retain seven-way concurrency with measurable headroom rather than treating
  the Viper site ceiling as a per-run minimum.

### Accomplishments

- Rechecked the retained run through the reviewed wrapper. Slurm job `10930411`
  remains `PENDING`, phase `submitted`, terminal `false`, with no exit code or
  failure class.
- Classified the resource concern before editing: the narrow correction is the
  fixed `control-matrix` outer allocation plus its matching job-wrapper guard
  and one focused regression. No scientific, scoring, retention, or matrix
  concurrency policy needs to change.
- Did not cancel or mutate the retained run because the standing instruction
  forbids cancellation and the user has not yet explicitly overridden it for
  job `10930411`.

### Immutable evidence

- Source commit remains `7705252f7ceeaa359514814b6def5b0d4af591d8`;
  only this journal is modified locally.
- Retained run
  `gtd-control-matrix-20260816T112741Z-7705252f7cee-423f9da8` still maps to job
  `10930411`, profile `control-matrix`, scheduler state `PENDING`, and terminal
  `false`.
- The source-level request is 64 CPUs, 192 GB, and 24 hours; the recommended
  evidence-backed replacement is 32 CPUs, 64 GB, and the unchanged 24-hour
  outer bound.

### Unresolved work

- Explicit approval is required to cancel exactly job `10930411`, overriding
  the retained-run no-cancellation instruction. After approval, implement the
  focused 32-CPU/64-GB correction and continue without an intermediate handoff
  through focused tests, one locked gate, one commit/push/CI watch,
  checksum-reviewed deployment, staging, and the replacement Slurm attempt.
- The existing heartbeat remains bound to the current retained run until a
  replacement run is successfully submitted; do not create another monitor.

### Next exact starting point

Await explicit cancellation approval. If granted, run
`/Users/asuq/.local/bin/nf-gtd-hpc-test --no-progress cancel --run-id
gtd-control-matrix-20260816T112741Z-7705252f7cee-423f9da8`, then execute the
focused resource-policy correction continuously through the replacement Slurm
submission and rebind the existing heartbeat to that immutable run.

## 2026-08-16T12:18:06Z - Resource recommendation corrected to measured boundary

### Discoveries

- The preceding 32-CPU/64-GB recommendation preserved seven-way throughput; it
  was not a demonstrated correctness requirement. Its CPU estimate multiplied
  seven workers by the earlier four-useful-CPU observation, and its memory
  estimate added a twofold margin above seven times the prior 4.3-GB maximum.
  Neither margin has been measured for this complete matrix.
- The closer real-runtime precedent is the six-case control slice: it requested
  8 CPUs and 32 GB, capped execution at four concurrent Phaser attempts, and
  completed all five real attempts without scheduler or tool failure. The full
  matrix adds serial work but does not require greater instantaneous
  concurrency for scientific correctness.

### Accomplishments

- Corrected the proposed minimal policy before any source edit: reuse the
  measured 8-CPU/32-GB outer allocation and four-worker cap for the full matrix.
  That gives two threads and an eight-GB memory budget per concurrent attempt.
- Kept candidate retention, LLG/TFZ ranking-only policy, case inventory, and all
  scientific transitions unchanged. The trade-off is elapsed time only, which
  must be observed rather than guessed.
- Did not cancel or change job `10930411`; explicit cancellation approval is
  still required.

### Immutable evidence

- The six-case Viper profile used 8 CPUs, 32 GB, four concurrent workers, and
  five real Phenix attempts. It reached terminal scheduler/tool success; its
  observed defect was the already-corrected output parser, not resource
  exhaustion.
- The current full-matrix job remains the immutable 64-CPU/192-GB request from
  source commit `7705252f7ceeaa359514814b6def5b0d4af591d8`; no replacement has
  been staged or submitted.

### Unresolved work

- Obtain explicit approval to cancel exactly job `10930411`. If approved,
  change the full-matrix allocation and concurrency guard to 8 CPUs, 32 GB, and
  four concurrent attempts; add the smallest resource-contract regression and
  complete the single gate/commit/push/CI/deploy/resubmit loop.
- Use terminal Slurm and application evidence from the replacement to decide
  whether any later resource adjustment is justified. Do not reserve extra
  throughput pre-emptively.

### Next exact starting point

Await explicit cancellation approval. If granted, run
`/Users/asuq/.local/bin/nf-gtd-hpc-test --no-progress cancel --run-id
gtd-control-matrix-20260816T112741Z-7705252f7cee-423f9da8`, then implement the
8-CPU/32-GB/four-worker correction continuously through the replacement Slurm
submission and rebind the existing heartbeat.

## 2026-08-16T12:31:08Z - Crowded-cluster matrix correction is locally green

### Discoveries

- Job `10930411` was still `PENDING` immediately before the authorised
  cancellation, so replacing it discarded no computation. The reviewed wrapper
  then reported scheduler state `CANCELLED`, terminal `true`.
- The measured resource boundary must be consistent across three layers: the
  dispatcher allocation, the compute-job CPU guard, and the Python adapter's
  worker/default-thread policy. Changing only the Slurm request would either
  fail the guard or retain avoidable concurrency.
- The first focused dispatcher regression failed only because its synthetic
  staged run omitted the required `logs` directory. Adding that fixture
  directory made the intended resource regression pass; no product fallback
  was added.

### Accomplishments

- Replaced the complete matrix's 64-CPU/192-GB/seven-worker policy with 8 CPUs,
  32 GB, and at most four concurrent Phenix attempts. The 24-hour outer
  scheduler ceiling remains unchanged and no tool-level timeout was added.
- Updated the CLI default, compute-job guard, and Viper runbook consistently.
  Added focused unit coverage for the eight-thread/four-worker adapter boundary
  and integration coverage for the exact Slurm request and job-wrapper guard.
- The focused unit and integration regressions pass. One complete
  `pixi run --locked check` passed formatting, Ruff, `ty`, 395 unit tests,
  57 contract tests, 48 integration tests, schemas, the public panel, docs,
  Actions lint, Nextflow syntax/stub checks, and HPC wrapper syntax.

### Immutable evidence

- Cancelled retained run
  `gtd-control-matrix-20260816T112741Z-7705252f7cee-423f9da8`, job `10930411`,
  moved from `PENDING` to `CANCELLED` with no execution phase reached.
- The correction is based on the already exercised six-case Viper envelope:
  8 CPUs, 32 GB, and four concurrent workers. Scientific case inventory,
  expected counts 1/2/3/4/6, candidate retention, and ranking policy are
  unchanged.
- The immutable parent source remains
  `7705252f7ceeaa359514814b6def5b0d4af591d8`; the replacement commit and run do
  not yet exist.

### Unresolved work

- Create one coherent commit containing the carried journal and focused
  resource correction, push once, watch one GitHub Actions run, deploy only the
  resulting green commit, stage the fixed matrix again, and submit the
  replacement Viper job.
- Record new source, archive, embedded-manifest, controller, deployed-tool,
  Slurm, and monitor identities after submission. Do not create a second
  heartbeat.

### Next exact starting point

Inspect `git status --short`, the complete diff, and `git diff --check`; stage
only this correction, create its coherent commit, and continue without a
handoff through push, one CI watch, checksum-reviewed deployment, matrix
staging, replacement submission, and heartbeat rebinding.

## 2026-08-16T12:41:32Z - Right-sized complete matrix is running on Viper

### Discoveries

- The 8-CPU/32-GB replacement entered scheduler state `RUNNING` immediately
  after submission on the crowded Viper queue. The right-sized profile therefore
  met the primary operational goal without increasing resources or changing
  scientific policy.
- Rebuilding the local controller after the green commit produced a new
  checksum even though the staging interface itself was unchanged. Installing
  that exact artifact keeps local orchestration, pushed source, and deployed
  tools aligned for later provenance review.

### Accomplishments

- Created and pushed commit
  `ab3f47b2848609335423ad67279ffbf1e7ef0187` once. GitHub Actions run
  `31947352435` passed its single Pixi 0.76.2 job in 5m42s.
- Deployed checksum-reviewed dispatcher and compute-job tools, rebuilt and
  installed the matching local controller, staged the fixed public 23-case
  archive, and submitted the replacement Viper job.
- Rebound the existing `continue-prokaryotic-control-roadmap` 30-minute
  heartbeat to only the replacement run. It remains active in the current task;
  no duplicate monitor was created.

### Immutable evidence

- Active run:
  `gtd-control-matrix-20260816T123957Z-ab3f47b28486-678daa04`, Slurm job
  `10930972`, source commit
  `ab3f47b2848609335423ad67279ffbf1e7ef0187`, nf-helper commit
  `82431e4c56cb4cd2ef4ea67321fd01fad7ba65cb`, site `viper-cpu`, profile
  `control-matrix`, suite `prokaryote_homomer_workflow_v1`, 23 cases, 11
  positives, and 18 real first-copy searches.
- The outer request is 8 CPUs, 32 GB, and 24 hours; the adapter runs at most four
  concurrent Phenix attempts. Initial structured state is phase `submitted`,
  scheduler state `RUNNING`, terminal `false`, with no exit code or failure
  class.
- Staged archive SHA-256 is
  `51add8b8448f7920861efb47946d57f1526b83abc887091fcd3c3244f06d137c`;
  embedded-manifest SHA-256 is
  `97132162e558df1c9087aab1826a32e954eb3477b2b241eb9930b0655cf74b40`;
  Pixi lock SHA-256 is
  `a31c520126e559154433546f45b92d2617bc622f89ffd6b0422c0579c0dda66b`.
- Local controller SHA-256 is
  `5220857aa60735db74da4fdf065e1ed914a017d502edb926beacb0e445cfb7d2`.
  Deployed dispatcher, job-wrapper, and recovery SHA-256 values are
  `69e4959eb9ce3bcc3ff287b7e92db67425fd5b76004c9303f3e10b02cc2e0e5d`,
  `6d679a06a14f80fb68432fac38b16606486ae00d4b83bfe563adedc5de0a50a7`,
  and `0db4c5f3542ce4d387ac019e33717d5e405ac957efb216b05c52828a851808f4`.
- Superseded run
  `gtd-control-matrix-20260816T112741Z-7705252f7cee-423f9da8`, job `10930411`,
  was cancelled while still `PENDING`; it performed no matrix computation and
  must not be reused or cleaned automatically.

### Unresolved work

- While the replacement is non-terminal, leave it untouched and never infer a
  failure from silence. On terminal evidence, inspect only bounded logs with
  `--tail 200`, collect through the reviewed wrapper, and verify the complete
  23-case evidence and provenance boundary before considering source changes.
- Verify all 18 first-copy attempts, 11 positives, seven wrong-model searches,
  five typed boundary outcomes, copy transitions through 1/2/3/4/6, all
  additional-copy/refinement/sequence records, Phenix qualification, bounded
  Phaser logs, candidate-level failures, and retain-all semantics. These
  operational same-structure controls do not establish generalisation.

### Next exact starting point

Run `/Users/asuq/.local/bin/nf-gtd-hpc-test --no-progress status --run-id
gtd-control-matrix-20260816T123957Z-ab3f47b28486-678daa04`. If non-terminal,
report the structured state concisely and leave it untouched. If terminal, run
bounded `logs --tail 200`, then `collect`, and classify the complete evidence
before editing source.

## 2026-08-16T12:43:51Z - Remaining single-component gates clarified

### Discoveries

- M0–M4 and T13.1–T13.3 are implemented and have real CD6 execution evidence,
  but CD6 has unknown composition. The active 23-case truth-labelled matrix is
  therefore the remaining operational acceptance layer for the existing
  single-component machinery, not a new numbered milestone.
- After the matrix, the remaining numbered milestones are M5 and M6. M5 closes
  the three-dataset pilot, human checkpoints, bounded calibration, and
  Prototype 0.2. M6 adds leakage-controlled independent validation and the
  versioned internal research release.
- The full-program roadmap's final “next M0” status paragraph is stale relative
  to the newer single-component roadmap and development journal. It must not be
  used to restart accepted work or rerun old qualification tracks.

### Accomplishments

- Reconciled the active run with the tracked dependency path and separated
  implementation completion, truth-labelled operational acceptance,
  Prototype 0.2 acceptance, and independent generalisation/release evidence.
- Kept heteromer reconstruction, advanced crystallographic branches,
  calibrated automation, and other Phase II+ work outside the active scope.

### Immutable evidence

- Active operational gate remains run
  `gtd-control-matrix-20260816T123957Z-ab3f47b28486-678daa04`, job `10930972`,
  source commit `ab3f47b2848609335423ad67279ffbf1e7ef0187`; its last observed state
  is `RUNNING`, terminal `false`.
- The single-component roadmap explicitly states that M0–M4 and T13.1–T13.3
  passed on real CD6 evidence and names the complete fixed matrix as the
  immediate goal before M5/Prototype 0.2 and M6.

### Unresolved work

- Complete and classify the 23-case matrix, correcting only demonstrated
  software failures until its full retain-all evidence boundary passes.
- Close M5 with the human-reviewed three-dataset P0–P4 pilot and measured
  resource/heuristic review, then accept or reject Prototype 0.2 explicitly.
- Execute M6's independent leakage-controlled benchmark, release hardening,
  clean-install acceptance, documentation/licensing/provenance package, and
  maintainer-approved internal research release.
- Treat every Phase II+ expansion as a separately authorised programme after
  Gate 1; it is not remaining work within the active prototype.

### Next exact starting point

Run `/Users/asuq/.local/bin/nf-gtd-hpc-test --no-progress status --run-id
gtd-control-matrix-20260816T123957Z-ab3f47b28486-678daa04`. If non-terminal,
leave it untouched. If terminal, run bounded `logs --tail 200`, then `collect`,
and verify the complete matrix before advancing to M5.

## 2026-08-16T12:55:14Z - Matrix adapter identity failure reproduced and corrected

### Discoveries

- Replacement job `10930972` reached terminal scheduler state `FAILED` with
  outer exit code 1 and failure class `test_failure`. Bounded logs and the
  retained collection show that all 11 MTZ preflights completed before the
  adapter raised `experimental hypothesis and model mapping identities differ`;
  no real Phaser attempt began.
- The failure is a narrow matrix-adapter contract defect, not a scheduler,
  resource, archive, MTZ, Phenix-installation, or Phaser-parser failure. The
  positive `ProcessedModelRecord` retained its generated `mapping_id`, but the
  paired `MrHypothesis.priority_features` omitted the required
  `coordinate_mapping_id` used by the existing fail-loud experimental-model
  guard.
- The collected package contains the staged import manifest, Phenix
  qualification, bounded logs, outer result, events, and state. It correctly
  contains no matrix result JSON/JSONL files because execution stopped before
  the planned 18 first-copy candidates were constructed. Candidate-level
  results, copy transitions, refinements, sequences, and runtime retain-all
  evidence therefore remain unverified rather than failed.

### Accomplishments

- Added a focused synthetic runtime regression that reproduces the exact Viper
  exception by passing a generated positive hypothesis and model through the
  production experimental-identity guard. It failed before the correction and
  passes after adding only the missing `coordinate_mapping_id` field.
- Focused tests passed: 22 Phaser-adapter, matrix-resource, and matrix-runtime
  tests. One complete `pixi run --locked check` passed with 396 unit, 57
  contract, and 48 integration tests plus formatting, Ruff, ty, schema,
  public-panel, documentation, actionlint, Nextflow syntax/stub, and HPC wrapper
  checks.
- Preserved the prior uncommitted roadmap clarification in this coherent
  code/evidence milestone. No score policy, retention rule, scientific boundary,
  concurrency limit, or resource request changed.

### Immutable evidence

- Failed run:
  `gtd-control-matrix-20260816T123957Z-ab3f47b28486-678daa04`, Slurm job
  `10930972`, source commit
  `ab3f47b2848609335423ad67279ffbf1e7ef0187`, nf-helper commit
  `82431e4c56cb4cd2ef4ea67321fd01fad7ba65cb`, Pixi 0.76.2, Pixi-lock SHA-256
  `a31c520126e559154433546f45b92d2617bc622f89ffd6b0422c0579c0dda66b`,
  and Phenix 2.1-6048. Collection failure signature is
  `ade60a5db89f1d2e7d786a76a767c6438d7e8ae5665666f626384e0e2a653878`.
- The retained import proves exactly 23 typed cases: 11 positives, seven
  wrong-model controls, two target-absent controls, two wrong-catalogue
  controls, and one assumption violation. It also records positive copy counts
  1/2/3/4/6, `all_candidates_retained=true`,
  `LLG/TFZ_are_ranking_annotations_only`, and no generalisation claim.
- Archive SHA-256 remains
  `51add8b8448f7920861efb47946d57f1526b83abc887091fcd3c3244f06d137c`;
  embedded-manifest SHA-256 remains
  `97132162e558df1c9087aab1826a32e954eb3477b2b241eb9930b0655cf74b40`.
  All seven required Phenix commands passed qualification, including accepted
  command-specific non-zero help conventions where applicable.

### Unresolved work

- Inspect and commit only the focused adapter regression/fix plus the carried
  journal, push once, watch one GitHub Actions run, deploy checksum-reviewed
  tools, stage the immutable matrix again, and submit the next right-sized Viper
  attempt before returning to monitoring.
- On terminal evidence from that attempt, verify all 23 typed outcomes, exactly
  18 real first-copy attempts, copy transitions through 1/2/3/4/6, every raw
  first-copy/additional-copy/refinement/sequence record, bounded Phaser logs,
  candidate failure states, complete provenance, and retention of every
  candidate. The operational same-structure controls still do not establish
  generalisation.

### Next exact starting point

Run `git status --short`, inspect the complete staged and unstaged diff, and run
`git diff --check`; then create the single coherent correction commit and
continue through push, one CI watch, checksum-reviewed deployment, replacement
staging/submission, and rebinding the existing heartbeat without a handoff.

## 2026-08-16T13:07:14Z - Corrected matrix replacement submitted

### Discoveries

- The focused identity correction did not alter the remote dispatcher,
  job-wrapper, or recovery scripts, so their reviewed SHA-256 values remained
  unchanged when deployed from the new green source revision.
- Rebuilding the deterministic local controller from the new revision produced
  SHA-256
  `27659a8aaa8c9d4242d36c500e07957c5e7338392c065901468e332dae2c8dbf`.
  The previous installed controller was preserved under the ignored rollback
  directory with its verified checksum before replacement.
- Restaging the source-aware archive changed the outer archive digest while the
  embedded fixed-matrix manifest digest remained unchanged, as expected: the
  scientific 23-case inputs did not change.

### Accomplishments

- Created and pushed commit
  `73caf1b556dea3f82c337b8f66b1bcc10f1820e1` once. The sole GitHub Actions
  watch, run `31948420900`, passed under Pixi 0.76.2 in 5m48s.
- Deployed the reviewed remote tools, built and installed the matching immutable
  local controller, staged the complete fixed matrix, and submitted replacement
  Viper job `10931011` without changing the 8-CPU/32-GB/24-hour request or
  four-attempt concurrency cap.
- Updated the existing `continue-prokaryotic-control-roadmap` heartbeat in place
  to monitor only the new run every 30 minutes. Its task, active status, thread
  binding, and schedule were preserved; no duplicate automation was created.

### Immutable evidence

- Active run:
  `gtd-control-matrix-20260816T130359Z-73caf1b556de-b556c9e3`, Slurm job
  `10931011`, source commit
  `73caf1b556dea3f82c337b8f66b1bcc10f1820e1`, nf-helper commit
  `82431e4c56cb4cd2ef4ea67321fd01fad7ba65cb`, site `viper-cpu`, profile
  `control-matrix`, suite `prokaryote_homomer_workflow_v1`, Pixi 0.76.2, 23
  cases, 11 positives, and 18 planned real first-copy searches.
- Archive SHA-256 is
  `4a600fd1ecc48395583222e7d12d7ade14243f33e53e1a9bb02559adea683db3`;
  embedded-manifest SHA-256 is
  `97132162e558df1c9087aab1826a32e954eb3477b2b241eb9930b0655cf74b40`;
  Pixi-lock SHA-256 remains
  `a31c520126e559154433546f45b92d2617bc622f89ffd6b0422c0579c0dda66b`.
- Local controller SHA-256 is
  `27659a8aaa8c9d4242d36c500e07957c5e7338392c065901468e332dae2c8dbf`.
  Deployed dispatcher, job-wrapper, and recovery SHA-256 values are
  `69e4959eb9ce3bcc3ff287b7e92db67425fd5b76004c9303f3e10b02cc2e0e5d`,
  `6d679a06a14f80fb68432fac38b16606486ae00d4b83bfe563adedc5de0a50a7`,
  and `0db4c5f3542ce4d387ac019e33717d5e405ac957efb216b05c52828a851808f4`.
- Latest structured state is phase `submitted`, scheduler state `PENDING`,
  terminal `false`, with no exit code or failure class. Silence is not a failure
  signal; the retained run must remain untouched.

### Unresolved work

- Wait for terminal evidence from only the active replacement. Do not monitor,
  recollect, clean, or reuse predecessor run
  `gtd-control-matrix-20260816T123957Z-ab3f47b28486-678daa04` or the earlier
  cancelled oversized run.
- At terminal state, run bounded logs with `--tail 200`, collect through the
  reviewed wrapper, and verify the complete 23-case, 18-search, copy-transition,
  refinement, sequence, bounded-log, candidate-failure, provenance, and
  retain-all evidence boundary before editing or advancing to M5.

### Next exact starting point

Run `/Users/asuq/.local/bin/nf-gtd-hpc-test --no-progress status --run-id
gtd-control-matrix-20260816T130359Z-73caf1b556de-b556c9e3`. If non-terminal,
report the structured state concisely and leave the retained run untouched. If
terminal, run bounded `logs --tail 200`, then `collect`, and classify the full
evidence before making any source change.

## 2026-08-16T13:57:55Z - Complete matrix evidence exposes four narrow adapter defects

### Discoveries

- Corrected run `gtd-control-matrix-20260816T130359Z-73caf1b556de-b556c9e3`
  completed successfully at the outer job boundary. The retained package has
  exactly 23 typed case records and 18 unique real first-copy records: 11
  positives, seven wrong-model searches, and five non-search boundary outcomes.
- The operational positive gate is not yet accepted. Three positives retained
  the expected ASU count and eight did not. First-copy states are ten
  `completed_hit`, seven `failed_tool_execution`, and one `failed_parse`.
  Positive best-supported counts currently reach 1 and 2, not the complete
  expected 1/2/3/4/6 boundary.
- All seven tool exits used MTZs for which preflight selected an anomalous
  intensity quartet. The same Phenix 2.1-6048 I/O layer identifies those
  quartet arrays with a trailing `merged` array-info label and performs an exact
  label-string lookup, whereas the command passed only the four MTZ column
  labels. Every affected fixed-matrix MTZ also contains a directly usable
  non-anomalous intensity pair; the sole anomalous-amplitude-only control was
  found and executed correctly. This is a deterministic observation-selection
  interoperability defect, not seven independent scientific no-hits.
- The `PDB_7L6G` run exited successfully, wrote PDB/MTZ outputs, reported seven
  solutions, packing, top LLG 1601, and top-solution TFZ 14.2, but translational
  NCS suppressed the refined-TFZ-equivalent line. The parser therefore emitted
  `failed_parse` despite complete retained evidence.
- The `PDB_3W45` copy-two run used Phenix's `** SINGLE solution` summary and
  complete PDB/MTZ outputs. The generic parser recognises only numeric legacy
  solution-count lines, and the guarded output-file fallback is currently used
  only by first-copy execution, so the additional-copy record incorrectly
  failed parsing.
- The `PDB_8Q5T` copy-three output represents the complete two-copy fixed parent
  as one `fixed_parent` ensemble placement plus one `search_copy` placement.
  Counting raw ensemble remarks as total molecular copies therefore reports two
  instead of three and stops a packed, high-scoring sequential transition.

### Accomplishments

- Ran only bounded `logs --tail 200`, collected through the reviewed wrapper,
  and verified every declared collected digest locally. The bounded Phaser file
  contains 14 retained native-log sections of exactly 200 lines each.
- Verified all 23 case records set `all_candidates_retained=true`, all 18
  first-copy hypotheses are unique and retained, all three additional-copy
  records retain their parents, and all seven wrong-model cases forbid
  displacement while preserving their raw LLG/TFZ annotations.
- Verified five refinement records are `completed_success` and five sequence
  records are `completed_hit`. Four typed identity boundaries return
  `no_reportable_identity`, and the heteromeric control returns
  `assumption_violation_abstained` without an MR search.

### Immutable evidence

- Slurm job `10931011` ran from 2026-08-16T13:16:24Z to 13:28:29Z and ended
  `COMPLETED`, exit code 0, failure class `success`. Source commit is
  `73caf1b556dea3f82c337b8f66b1bcc10f1820e1`; nf-helper commit is
  `82431e4c56cb4cd2ef4ea67321fd01fad7ba65cb`; Pixi is 0.76.2; Pixi-lock
  SHA-256 is
  `a31c520126e559154433546f45b92d2617bc622f89ffd6b0422c0579c0dda66b`;
  Phenix is 2.1-6048 and all seven required commands passed qualification.
- Archive SHA-256 is
  `4a600fd1ecc48395583222e7d12d7ade14243f33e53e1a9bb02559adea683db3`;
  import-manifest SHA-256 is
  `97132162e558df1c9087aab1826a32e954eb3477b2b241eb9930b0655cf74b40`;
  Phenix-manifest SHA-256 is
  `0410c2b835a8de91061cb727bf5eb007cfac82b787e857cefc5fd549b5c3bad1`.
- Case, first-copy, additional-copy, refinement, sequence, and bounded-log
  SHA-256 values are respectively
  `409b3c55f7ef1a3b78a7df949ad4f1a55f8c2603536535f2db535c8380e10b7b`,
  `104f2ae6d1dcea90cf4cb53211fdf608a2d28bd8268bd8bda5b8fd60e0098426`,
  `a03e014b19f7eb383737e70c02d3038686258db65663f75fef44ef9a53e9f6fc`,
  `b37a0b9510ef7b27083a4e2c9c51a09c973cc56a34b8d8725fb70be00ce2d000`,
  `4af81855283661e2002cf8b5768e88cf93cff6914ba912797df94e0deaf22a1e`,
  and `e857af11f7a01072cd3d20ff1ed0a5c8e8b9fc70dadfe14878a841836b8e04b5`.
- The summary preserves
  `LLG/TFZ_are_ranking_annotations_only`, `all_candidates_retained=true`, and
  `none_operational_same_structure_controls`; these results make no
  generalisation claim.

### Unresolved work

- Add one focused regression for each demonstrated defect: prefer an available
  non-anomalous pair over an anomalous quartet, recognise Phenix's single-
  solution form, retain the top-solution TFZ when tNCS omits a refined
  equivalent, and count a checksum-validated fixed parent by its known copy
  count plus explicit `search_copy` placements.
- Do not suppress or reinterpret the `PDB_7L6G` three-placement tNCS outcome.
  Parse and retain it first; any multi-copy tNCS transition requires separate
  evidence after the narrow corrections, not a speculative fallback.
- After focused tests and one complete locked gate, create one coherent commit,
  push/watch once, deploy reviewed tools, and continue through the next
  right-sized complete-matrix Viper attempt before yielding to monitoring.

### Next exact starting point

Add the four focused regressions against the existing preflight, Phaser-parser,
and additional-copy adapter tests, confirm they fail for the observed reasons,
then implement only the corresponding guarded corrections.

## 2026-08-16T14:07:31Z - Four evidence-backed adapter corrections pass the locked gate

### Discoveries

- Each focused regression failed at the intended pre-correction boundary. The
  preflight selected `I(+),SIGI(+),I(-),SIGI(-)` instead of the available
  `IMEAN,SIGIMEAN` pair; the parser rejected both `** SINGLE solution` and a
  solution with only the top-solution TFZ annotation; and the additional-copy
  test could not import the absent fixed-parent placement counter.
- No broader fallback was required. The corrected selection still preserves an
  explicit user override and still permits anomalous data when no ordinary pair
  exists. Refined TFZ remains preferred, and the top-solution annotation is
  retained only when that refined value is absent.
- A fixed-parent Phaser ensemble is a coordinate representation, not a count of
  its constituent molecular copies. The narrow counter now uses the validated
  parent copy count plus explicit `search_copy` placements only when exactly one
  `fixed_parent` ensemble and at least one `search_copy` ensemble are present;
  other output forms keep the legacy raw-placement count.

### Accomplishments

- Added four focused regressions and implemented the four corresponding
  corrections. The first-copy and additional-copy adapter provenance versions
  are now `phenix-first-copy-mr-v4` and `phenix-add-copy-mr-v2`.
- The focused preflight, Phaser-parser, and additional-copy files pass all 64
  tests.
- The first locked-gate invocation stopped immediately at Ruff's format check
  and ran no test suite. After applying only Ruff's three reported mechanical
  line wraps, the single complete `pixi run --locked check` passed format,
  lint, type checking, 400 unit tests, 57 contract tests, 48 integration tests,
  schema/public-panel/docs/actionlint checks, Nextflow syntax and stub
  execution, and HPC wrapper syntax.

### Immutable evidence

- The correction remains grounded in retained Viper run
  `gtd-control-matrix-20260816T130359Z-73caf1b556de-b556c9e3`, Slurm job
  `10931011`, and its checksummed terminal evidence recorded above. No new
  scientific inputs, score policy, candidate filters, resource request, or
  heteromer behaviour were introduced.
- The focused test command completed with `64 passed in 1.12s`. The complete
  locked gate completed with exit code 0: `400 passed in 45.70s`, `57 passed in
  0.42s`, and `48 passed in 106.36s`, followed by every repository check.
- Every candidate remains retained, and LLG/TFZ remain annotations rather than
  candidate-deletion gates. The matrix remains an operational same-structure
  control and does not establish generalisation.

### Unresolved work

- Review the complete focused diff and commit it together with the accumulated
  evidence journal as one coherent milestone. Push once and watch exactly one
  GitHub Actions run.
- After green CI, deploy checksum-reviewed tools, rebuild and verify the local
  controller, stage the unchanged 23-case matrix, submit the next 8-CPU/32-GB
  Viper attempt, and rebind the existing 30-minute heartbeat before handoff.

### Next exact starting point

Run `git status --short`, then inspect the unstaged diff and run
`git diff --check` as separate commands before staging only the six focused
source/test files and this accumulated journal.

## 2026-08-16T14:17:48Z - Evidence-correction matrix submitted on Viper

### Discoveries

- The focused source change did not alter the reviewed dispatcher, job-wrapper,
  or recovery scripts. Deployment from the new green commit reproduced all
  three prior remote tool checksums.
- Rebuilding the deterministic local controller from the new commit produced
  SHA-256
  `198ba7eb00678b395b869dca7db159f823488ab788d7c3a7d09661d5274ed9ad`.
  The previous installed controller, SHA-256
  `27659a8aaa8c9d4242d36c500e07957c5e7338392c065901468e332dae2c8dbf`,
  was preserved under the ignored install-backup directory and its copied
  checksum was verified before replacement.
- Restaging changed only the source-bearing outer archive identity. The fixed
  manifest remains byte-identical, with exactly 23 cases, 11 positives, and 18
  real searches.

### Accomplishments

- Created coherent commit
  `c5b51cc61c2793c66942374bb288cd2532c75bae`, pushed `main` once, and watched
  only GitHub Actions run `31951868192`. Its sole Pixi 0.76.2 foundation-check
  job passed in 5m34s.
- Deployed the checksum-reviewed tools, installed the verified matching local
  controller, staged the unchanged complete matrix, and submitted Slurm job
  `10931163` with the retained 8-CPU/32-GB/24-hour profile and at most four
  concurrent Phenix attempts.
- Updated the existing `continue-prokaryotic-control-roadmap` heartbeat in place
  to monitor only the new run every 30 minutes. The active task binding and
  schedule were preserved; no duplicate monitor was created.

### Immutable evidence

- Active run:
  `gtd-control-matrix-20260816T141622Z-c5b51cc61c27-84b01902`, Slurm job
  `10931163`, source commit
  `c5b51cc61c2793c66942374bb288cd2532c75bae`, nf-helper commit
  `82431e4c56cb4cd2ef4ea67321fd01fad7ba65cb`, site `viper-cpu`, profile
  `control-matrix`, suite `prokaryote_homomer_workflow_v1`, Pixi 0.76.2, 23
  cases, 11 positives, and 18 planned first-copy searches.
- Archive SHA-256 is
  `757e15f73eeebbecb9d758a2b0c1c58c5d736c7167271f543bf66236557d3bb5`;
  embedded-manifest SHA-256 is
  `97132162e558df1c9087aab1826a32e954eb3477b2b241eb9930b0655cf74b40`;
  Pixi-lock SHA-256 is
  `a31c520126e559154433546f45b92d2617bc622f89ffd6b0422c0579c0dda66b`.
- Local controller SHA-256 is
  `198ba7eb00678b395b869dca7db159f823488ab788d7c3a7d09661d5274ed9ad`.
  Deployed dispatcher, job-wrapper, and recovery SHA-256 values are
  `69e4959eb9ce3bcc3ff287b7e92db67425fd5b76004c9303f3e10b02cc2e0e5d`,
  `6d679a06a14f80fb68432fac38b16606486ae00d4b83bfe563adedc5de0a50a7`,
  and `0db4c5f3542ce4d387ac019e33717d5e405ac957efb216b05c52828a851808f4`.
- First structured status is phase `submitted`, scheduler state `PENDING`,
  terminal `false`, with no exit code or failure class. Queue silence is not a
  failure signal; the retained run remains untouched.

### Unresolved work

- Wait for terminal evidence from only the active run. Do not monitor,
  recollect, clean, reuse, or reinterpret the completed predecessor or any
  earlier superseded run.
- At terminal state, retrieve only bounded logs with `--tail 200`, collect
  through the reviewed wrapper, and verify the full 23-case/18-search typed
  boundary, positive transitions through 1/2/3/4/6, every first-copy,
  additional-copy, refinement, and sequence record, bounded Phaser evidence,
  Phenix qualification, all provenance/checksums, candidate-level failures, and
  retention of every candidate before classifying the result.

### Next exact starting point

Run `/Users/asuq/.local/bin/nf-gtd-hpc-test --no-progress status --run-id
gtd-control-matrix-20260816T141622Z-c5b51cc61c27-84b01902`. If non-terminal,
report the structured state and leave the run untouched. If terminal, run
bounded `logs --tail 200`, then `collect`, and classify all evidence before any
source edit.

## 2026-08-16T15:28:59Z - Complete matrix exposes two remaining guarded transitions

### Discoveries

- Run `gtd-control-matrix-20260816T141622Z-c5b51cc61c27-84b01902`
  completed successfully at the outer boundary and produced the complete
  declared evidence package. The package has exactly 23 typed case records, 18
  unique real first-copy records, six additional-copy records, five refinement
  records, and five sequence records.
- The previous four corrections are exercised. All formerly incompatible
  merged-intensity inputs now reach real Phaser; the 7L6G top-solution TFZ 14.2
  is retained with its explicit parser warning; 7P50 advances from one to two
  to three copies; and 3W45's fixed-parent copy-two transition is counted and
  retained correctly.
- The positive gate is still not accepted. Five positive first-copy attempts
  and three positive additional-copy attempts are `failed_parse` with the sole
  reason `Phaser solution lacks final packing evidence`. Their bounded native
  logs show Phenix 2.1-6048 `** SINGLE solution`, `Top LLG (packs)`, refined
  TFZ, `PAK=0`, successful exit, and complete PDB/MTZ output. This output form
  omits the legacy accepted/packed-count row, so requiring that row after
  recognising `SINGLE solution` is an overly narrow adapter contract.
- 7L6G is a second distinct, now-demonstrated transition. Phenix's tNCS handling
  returned a packed three-copy first solution for the expected six-copy
  homomer. The first-copy result correctly retains `placed_copy_count=3`, LLG
  1601.02, TFZ 14.2, seven packed solutions, and the
  `placed_copy_count_mismatch` advisory. The matrix runner nevertheless requires
  exactly one first placement, records best count zero, and never offers the
  checksum-validated three-copy parent to the sequential homomer search.

### Accomplishments

- Retrieved only the required 200-line bounded logs and collected through the
  reviewed wrapper. Verified 24 native Phaser sections, each exactly 200 lines:
  18 first-copy and six additional-copy attempts.
- Verified exactly 11 positives, seven wrong-model searches, two target-absent
  outcomes, two wrong-catalogue outcomes, and one assumption-violation
  abstention. Every one of the 23 case records has
  `all_candidates_retained=true`; every failed addition retains its parent; all
  wrong-model results remain comparison evidence and cannot displace ground
  truth.
- Verified all five refinements are `completed_success` with checksummed model,
  MTZ, and map outputs, and all five sequence records are `completed_hit` with
  retained per-candidate scores. LLG/TFZ remain ranking annotations only.

### Immutable evidence

- Slurm job `10931163` ran from 2026-08-16T14:16:52Z to 14:59:12Z and ended
  `COMPLETED`, exit code 0, failure class `success`. Source commit is
  `c5b51cc61c2793c66942374bb288cd2532c75bae`; nf-helper commit is
  `82431e4c56cb4cd2ef4ea67321fd01fad7ba65cb`; Pixi is 0.76.2; Pixi-lock
  SHA-256 is
  `a31c520126e559154433546f45b92d2617bc622f89ffd6b0422c0579c0dda66b`.
- Archive SHA-256 is
  `757e15f73eeebbecb9d758a2b0c1c58c5d736c7167271f543bf66236557d3bb5`;
  import-manifest SHA-256 is
  `97132162e558df1c9087aab1826a32e954eb3477b2b241eb9930b0655cf74b40`;
  Phenix-manifest SHA-256 is
  `0410c2b835a8de91061cb727bf5eb007cfac82b787e857cefc5fd549b5c3bad1`.
  Phenix is 2.1-6048 and all seven required commands passed qualification.
- Summary, case, first-copy, additional-copy, refinement, sequence, and bounded-
  log SHA-256 values are respectively
  `7eb65b463e2369d5fef3c685a5b2d12187c037c0551185a8e5872e51816d231e`,
  `7d1d210c918b196784a265ad52b70e5b0ddc8a76821797f4f22fe408706e480e`,
  `c3a1029aeb1e0fea8e690fe99ec1dddd4a8c49c6cc6b5c3ff53503a9392b09c9`,
  `11f957170e7805a674502c303e100909c9df602100a6b1c919f16b8bedf8090a`,
  `e4a9702f2bd6605888478437ce9e207aac73ee1cc3e9f3596f84d79968edd566`,
  `f5fd3ecdc58edb2254cbc4c580aa95c59ec4eecb7aedb60fedbacf6e35ea675d`,
  and `d3f25bd5bb7156df8be97f1af8d7b32ee1109e35584804bfe12806fa3246748b`;
  all collected local hashes match the remote inventory.
- Current positive best-supported counts are zero, one, two, and three; only
  7P50 and 3W45 retain their expected counts. The required transitions through
  expected 1/2/3/4/6 are therefore not yet complete. These remain operational
  same-structure controls and make no generalisation claim.

### Unresolved work

- Add one focused parser regression for a complete `SINGLE solution` with
  `Top LLG (packs)` but no legacy packing-count row, then retain its explicit
  single packed solution without changing the LLG/TFZ ranking policy.
- Add one focused regression for a checksum-validated packed multi-copy first
  parent. Preserve its actual placed-copy count through matrix selection,
  additional-copy root state, refinement input, and best-count reporting so the
  7L6G homomer can continue from three towards six. Do not reinterpret tNCS or
  fabricate placements.
- After focused checks and one complete locked gate, create one coherent
  commit/push/CI cycle, deploy reviewed tools, and continue through the next
  unchanged right-sized Viper matrix attempt before returning to monitoring.

### Next exact starting point

Add the two focused regressions against the existing Phaser parser,
additional-copy root validation, and fixed matrix transition tests; confirm
they fail for the retained evidence, then implement only the guarded
single-packed and validated multi-copy-parent transitions.

## 2026-08-16T15:41:57Z - Guarded parser and copy-transition corrections pass locally

### Discoveries

- The focused regressions reproduced both retained-run defects before the
  implementation changed: a complete Phenix `SINGLE solution` without the
  legacy packing-count row failed final-packing validation, and a packed
  three-copy tNCS first result could not seed a six-copy sequential search.
- A narrow Phenix 2.1-6048 discriminator is sufficient. Only a final
  `SINGLE solution` together with `Top LLG (packs)` permits an inferred
  accepted/packed count of one; numeric and multi-solution output still
  requires explicit legacy packing evidence.
- A checksum-validated, packed first result can safely seed the existing
  homomer search at its reported count when that count is between one and the
  expected ASU count. The tNCS count-mismatch warning remains visible and no
  placements are fabricated.

### Accomplishments

- Added focused parser, additional-copy, and matrix-transition regressions.
  The three new regressions pass, and all 40 tests in the affected unit-test
  files pass.
- Bumped the narrow adapter contracts and propagated the actual validated
  first-result count through matrix selection, additional-copy parent state,
  refinement input, best-count reporting, and truth-retention accounting.
- Ran the one complete `pixi run --locked check`. Formatting, Ruff linting,
  typing, 402 unit tests, 57 contract tests, the integration and Nextflow
  checks, and the HPC wrapper syntax check all passed.

### Immutable evidence

- The regression failures were the expected pre-fix contracts: `Phaser
  solution lacks final packing evidence`, the one-copy additional-parent
  restriction, and the absent multi-copy matrix helper. No score threshold,
  candidate-retention rule, resource request, or heteromer scope changed.
- The complete locked gate ended with exit code zero on 2026-08-16 under the
  repository's existing locked Pixi environment. Unit and contract totals are
  respectively 402 and 57.

### Unresolved work

- Review and commit this code, test, and accumulated evidence as one coherent
  milestone; push once and watch exactly one GitHub Actions run.
- Deploy checksum-reviewed tools, stage the unchanged fixed 23-case matrix,
  submit the next right-sized Viper job, and bind the existing 30-minute
  heartbeat to that new retained run.

### Next exact starting point

Run `git status --short`, inspect the complete source/test/journal diff and
`git diff --check`, then stage only the seven files belonging to this guarded
parser and copy-transition milestone.

## 2026-08-16T16:05:32Z - Guarded-transition matrix submitted on Viper

### Discoveries

- The reviewed remote dispatcher, job wrapper, and recovery scripts are
  unchanged by the focused Python correction. Deployment from the green source
  commit reproduced all three previously reviewed remote checksums.
- Rebuilding the deterministic local controller from the new commit produced
  SHA-256
  `dd7c6138652766da561866bb5842ccaa56df6e91454f698e03a333fdbf0506c5`.
  The prior installed controller, SHA-256
  `198ba7eb00678b395b869dca7db159f823488ab788d7c3a7d09661d5274ed9ad`,
  was copied into the ignored install-backup directory and its checksum was
  verified before replacement.
- Restaging preserved the exact fixed matrix manifest and changed only the
  source-bearing outer archive identity. The request remains 8 CPUs, 32 GB, a
  24-hour scheduler ceiling, and at most four concurrent Phenix attempts.

### Accomplishments

- Created coherent commit
  `43db3d8c08af1c6652616814b149f08b3f38fc11`, pushed `main` once, and watched
  only GitHub Actions run `31956497804`. Its sole Pixi 0.76.2 foundation-check
  job passed in 5m32s.
- Deployed checksum-reviewed tools, installed the verified matching local
  controller, staged the unchanged 23-case matrix, and submitted Slurm job
  `10931491`.
- Updated the existing `continue-prokaryotic-control-roadmap` heartbeat in
  place to monitor only the new retained run every 30 minutes. No duplicate
  monitor was created.

### Immutable evidence

- Active run:
  `gtd-control-matrix-20260816T160423Z-43db3d8c08af-a3df06c2`, Slurm job
  `10931491`, source commit
  `43db3d8c08af1c6652616814b149f08b3f38fc11`, nf-helper commit
  `82431e4c56cb4cd2ef4ea67321fd01fad7ba65cb`, site `viper-cpu`, profile
  `control-matrix`, suite `prokaryote_homomer_workflow_v1`, Pixi 0.76.2, 23
  cases, 11 positives, and 18 planned first-copy searches.
- Archive SHA-256 is
  `98685648b27f7e1628130de3f88a27b546ccef63742f4a68039c720e339aa0af`;
  embedded-manifest SHA-256 is
  `97132162e558df1c9087aab1826a32e954eb3477b2b241eb9930b0655cf74b40`;
  Pixi-lock SHA-256 is
  `a31c520126e559154433546f45b92d2617bc622f89ffd6b0422c0579c0dda66b`.
- Local controller SHA-256 is
  `dd7c6138652766da561866bb5842ccaa56df6e91454f698e03a333fdbf0506c5`.
  Deployed dispatcher, job-wrapper, and recovery SHA-256 values are
  `69e4959eb9ce3bcc3ff287b7e92db67425fd5b76004c9303f3e10b02cc2e0e5d`,
  `6d679a06a14f80fb68432fac38b16606486ae00d4b83bfe563adedc5de0a50a7`,
  and `0db4c5f3542ce4d387ac019e33717d5e405ac957efb216b05c52828a851808f4`.
- First structured status is phase `submitted`, scheduler state `PENDING`,
  terminal `false`, with no exit code or failure class. Scheduler silence is
  not a failure signal; the retained run remains untouched.

### Unresolved work

- Wait for terminal evidence from only the active run. Do not monitor,
  recollect, clean, reuse, or reinterpret the completed predecessor or earlier
  superseded runs.
- At terminal state, retrieve only bounded logs with `--tail 200`, collect
  through the reviewed wrapper, and verify the full 23-case/18-search typed
  boundary, positive transitions through 1/2/3/4/6, every first-copy,
  additional-copy, refinement, and sequence record, bounded Phaser evidence,
  Phenix qualification, all provenance/checksums, candidate-level failures,
  and retention of every candidate before classifying the result.

### Next exact starting point

Run `/Users/asuq/.local/bin/nf-gtd-hpc-test --no-progress status --run-id
gtd-control-matrix-20260816T160423Z-43db3d8c08af-a3df06c2`. If non-terminal,
leave the run untouched and do not append a no-change journal entry. If
terminal, run bounded `logs --tail 200`, then `collect`, and classify all
evidence before any source edit.

## 2026-08-16T18:42:36Z - Complete matrix isolates one add-copy status defect

### Discoveries

- The right-sized run completed successfully and exercised the full matrix.
  Ten of eleven positives retained their declared ASU count, including counts
  1, 2, 3, and 4. The 7L6G six-copy control retained its valid packed
  three-copy tNCS parent but did not extend it.
- The 7L6G copy-four native log exits successfully and explicitly states both
  `No solution with all components` and `Search did not extend input solution
  with new components`. Its emitted PDB/MTZ represent the unchanged partial
  parent, not a new child. The add-copy adapter instead records `failed_parse`
  because the generic first-solution parser correctly does not treat this
  partial-solution phrase as a zero-solution marker.
- This demonstrates one narrow add-copy status-classification defect. It does
  not support a new tNCS search strategy, fabricated copies, score gate, or
  reinterpretation of the deposited six-copy expectation.

### Accomplishments

- Retrieved the required 200-line logs and collected through the reviewed
  wrapper. Verified exactly 23 typed cases, 18 first-copy attempts, 11
  additional-copy attempts, 11 refinements, and 11 sequence assessments. All
  29 retained native Phaser sections contain exactly 200 lines.
- All 18 first-copy records are `completed_hit`; ten add-copy records are
  supported hits and the sole remaining failure is the 7L6G classification
  above. All 11 refinements are `completed_success` with checksummed model,
  MTZ, and maps; all 11 sequence records are `completed_hit` with checksummed
  output models and explicit unscored-group warnings where applicable.
- Verified 11 positives, seven non-displacing wrong-model searches, four
  `no_reportable_identity` boundaries, and one
  `assumption_violation_abstained` boundary. Every case retains every
  candidate; LLG/TFZ remain annotations only and no generalisation is claimed.

### Immutable evidence

- Run `gtd-control-matrix-20260816T160423Z-43db3d8c08af-a3df06c2`, Slurm job
  `10931491`, ran from 2026-08-16T16:33:06Z to 18:28:05Z and ended
  `COMPLETED`, exit code 0, failure class `success`. Source commit is
  `43db3d8c08af1c6652616814b149f08b3f38fc11`; nf-helper commit is
  `82431e4c56cb4cd2ef4ea67321fd01fad7ba65cb`; Pixi is 0.76.2; Pixi-lock
  SHA-256 is
  `a31c520126e559154433546f45b92d2617bc622f89ffd6b0422c0579c0dda66b`.
- Archive, import-manifest, and Phenix-manifest SHA-256 values are
  `98685648b27f7e1628130de3f88a27b546ccef63742f4a68039c720e339aa0af`,
  `97132162e558df1c9087aab1826a32e954eb3477b2b241eb9930b0655cf74b40`,
  and `0410c2b835a8de91061cb727bf5eb007cfac82b787e857cefc5fd549b5c3bad1`.
  Phenix is 2.1-6048 and all seven required commands passed qualification.
- Summary, case, first-copy, add-copy, refinement, sequence, and bounded-log
  SHA-256 values are respectively
  `789c05a2cf804fa816c310456d0c3ed6a13f924a5259d3c92b629fd5a1064183`,
  `2521045703b7b051cdc90586bfa652e3d9257b38668a5bf3bc68bf8e13618804`,
  `cf92c8be6e651d6acb2e439417fdf489b6967a579a1e33f0ca4e7d9a8db8368d`,
  `59813b386ff3c42d2aa6e5ea601615692310ea954602bc04d6b16408d9ab872d`,
  `0ab95631bdc4a0a43da2844faa4f3bf43c69a52242f387d80154afbbae07be76`,
  `d0f3d3c1028e9d1884bea4a95c93b0ae8aa388d80732dc96f46d8b2e3f4f7276`,
  and `c2a0c3baaaf53175af0172c0c90b523d3167cb253df0c4229e2fdc99188e254c`;
  every collected local digest matches the remote inventory.

### Unresolved work

- Add one focused add-copy regression for the exact successful no-extension
  terminal form, including its partial parent PDB/MTZ, then classify it as
  `completed_no_hit` while retaining the parent and refusing to publish those
  partial files as a supported child.
- Run focused checks and one complete locked gate, commit this code/test and
  accumulated evidence once, push/watch once, deploy reviewed tools, and
  submit the next unchanged right-sized matrix before returning to monitoring.

### Next exact starting point

Add the focused no-extension regression in
`tests/unit/test_add_copy_phaser.py`, confirm the current `failed_parse`, and
implement only the add-copy-specific terminal classification.

## 2026-08-16T18:49:47Z - Add-copy no-extension classification passes locally

### Discoveries

- The exact real-log discriminator requires all three native facts: no solution
  with all components, no extension of the input solution, and successful exit.
  Keeping this logic inside the add-copy adapter preserves the generic parser's
  deliberate refusal to call a retained partial parent a zero-solution result.

### Accomplishments

- Added one focused regression with a three-copy parent and partial PDB/MTZ
  outputs. It failed as the observed `failed_parse` before the change and now
  returns `completed_no_hit`, retains best count three, and publishes no child
  coordinate or MTZ.
- Bumped only the add-copy adapter contract and added the guarded terminal
  classification. All 41 affected tests pass.
- Ran the one complete `pixi run --locked check`: formatting, linting, typing,
  403 unit tests, 57 contract tests, 48 integration tests, schemas, public
  panel, documentation, actions, Nextflow syntax/stub, and HPC wrapper checks
  all passed.

### Immutable evidence

- The focused pre-fix failure was exactly `failed_parse` instead of
  `completed_no_hit`; the post-fix focused test passed. The complete locked
  gate ended with exit code zero under the existing lock and Pixi environment.
- No search command, score policy, expected copy count, candidate-retention
  rule, resource request, or tNCS strategy changed.

### Unresolved work

- Review and commit the focused source/test change together with the compacted
  accumulated evidence, push once, and watch exactly one CI run.
- Deploy checksum-reviewed tools, stage the unchanged 23-case matrix, submit
  the next right-sized Viper job, and rebind the existing heartbeat in place.

### Next exact starting point

Run `git status --short`, inspect the complete diff and `git diff --check`, then
stage only the journal, add-copy adapter, and focused unit test.

## 2026-08-16T18:59:47Z - Add-copy-status matrix submitted on Viper

### Discoveries

- The focused Python change leaves the reviewed remote dispatcher, job wrapper,
  and recovery scripts byte-identical. Deployment reproduced all three prior
  checksums.
- Rebuilding the deterministic local controller produced SHA-256
  `aac4612df6856a357d421c14430e69e3d8378e5bf4208fa05de02c433b4b623a`.
  The previous installed controller, SHA-256
  `dd7c6138652766da561866bb5842ccaa56df6e91454f698e03a333fdbf0506c5`,
  was checksum-verified in the ignored backup directory before replacement.

### Accomplishments

- Created and pushed coherent commit
  `cbdebdb3e5348d379f8a8c0c8144753d73aa9988` once. The sole Pixi 0.76.2 job
  in GitHub Actions run `31965835301` passed in 5m40s.
- Deployed checksum-reviewed tools, installed the matching local controller,
  staged the unchanged fixed matrix, and submitted Slurm job `10932049` with
  the retained 8-CPU/32-GB/24-hour profile and at most four concurrent Phenix
  attempts.
- Rebound the existing `continue-prokaryotic-control-roadmap` heartbeat in
  place. No duplicate monitor was created, and unchanged non-terminal checks
  will not append journal entries.

### Immutable evidence

- Active run:
  `gtd-control-matrix-20260816T185831Z-cbdebdb3e534-79287e54`, Slurm job
  `10932049`, source commit
  `cbdebdb3e5348d379f8a8c0c8144753d73aa9988`, nf-helper commit
  `82431e4c56cb4cd2ef4ea67321fd01fad7ba65cb`, site `viper-cpu`, profile
  `control-matrix`, suite `prokaryote_homomer_workflow_v1`, 23 cases, 11
  positives, and 18 planned first-copy searches.
- Archive SHA-256 is
  `9d85504e9605a2ebdcb25b4a6d674104e2e2c96ca6d6dee071c3199f1dd91e21`;
  embedded-manifest SHA-256 is
  `97132162e558df1c9087aab1826a32e954eb3477b2b241eb9930b0655cf74b40`;
  Pixi-lock SHA-256 is
  `a31c520126e559154433546f45b92d2617bc622f89ffd6b0422c0579c0dda66b`.
- Deployed dispatcher, job-wrapper, and recovery SHA-256 values remain
  `69e4959eb9ce3bcc3ff287b7e92db67425fd5b76004c9303f3e10b02cc2e0e5d`,
  `6d679a06a14f80fb68432fac38b16606486ae00d4b83bfe563adedc5de0a50a7`,
  and `0db4c5f3542ce4d387ac019e33717d5e405ac957efb216b05c52828a851808f4`.
  First structured state is `PENDING`, terminal `false`, with no exit code or
  failure class.

### Unresolved work

- Wait for terminal evidence from only the active run. Do not journal unchanged
  `PENDING` or `RUNNING` checks.
- At terminal state, retrieve bounded logs and collect through the reviewed
  wrapper. Verify that the 7L6G no-extension branch is `completed_no_hit` with
  best count three and parent retained, while preserving every other typed
  result, checksum, and retain-all invariant. Do not claim six copies were
  supported or add a speculative tNCS fallback.

### Next exact starting point

Run `/Users/asuq/.local/bin/nf-gtd-hpc-test --no-progress status --run-id
gtd-control-matrix-20260816T185831Z-cbdebdb3e534-79287e54`. If non-terminal,
leave it untouched and do not append a journal entry. If terminal, run bounded
`logs --tail 200`, then `collect`, and classify all evidence before editing.

## 2026-08-16T19:37:25Z - Unknown operator crystals deferred until post-M6

### Discoveries

- The user approved a durable gate correction: the three unknown-composition
  operator crystals cannot distinguish software failure from heteromeric or
  otherwise out-of-scope biology and therefore cannot validate or calibrate the
  single-component prototype.
- M5 now uses the fixed truth-labelled 23-case matrix for operational
  acceptance and bounded resource review. M6 is the first independent
  leakage-controlled validation gate; the unknown crystals follow M6 only as
  exploratory applications.

### Accomplishments

- Reconciled `AGENTS.md`, the single-component and full-program roadmaps, the
  M0/M4/control-panel status pages, and the documentation index. Historical M0
  execution evidence remains intact.
- Updated the existing `continue-prokaryotic-control-roadmap` heartbeat in
  place. It retains the same 30-minute schedule and active matrix, forbids the
  unknown-crystal fallback, and stops before unapproved M6 execution. No
  duplicate task was created and the Viper run was untouched.

### Immutable evidence

- `AD4QS1P4G2_18`, `CD4QS2P2G1_15`, and `CD6QS2P2G1_5` are excluded from M5
  acceptance, Prototype 0.2 calibration, and M6 validation. No score policy,
  candidate-retention rule, search strategy, scientific input, or runtime
  resource request changed.

### Unresolved work

- Collect and classify only the active 23-case matrix, then perform the bounded
  M5 operational review and present an explicit Prototype 0.2 decision.
- Define and obtain approval for an independently reviewable M6 benchmark
  manifest and predeclared criteria before executing M6. Handle the three
  unknown crystals only after the M6 release gate.

### Next exact starting point

Run `/Users/asuq/.local/bin/nf-gtd-hpc-test --no-progress status --run-id
gtd-control-matrix-20260816T185831Z-cbdebdb3e534-79287e54`. If non-terminal,
leave it untouched. If terminal, run bounded `logs --tail 200`, then `collect`,
and classify the complete matrix before the M5 operational review.

## 2026-08-16T21:16:33Z - Fixed matrix completes; Prototype 0.2 held

### Discoveries

- The corrected matrix ended successfully and reproduced the guarded 7L6G
  terminal state as `completed_no_hit`: Phenix supported no extension beyond
  the checksum-validated three-copy tNCS parent. This closes the demonstrated
  adapter defect; it does not support the declared six-copy truth.
- This run demonstrates no new software failure. The remaining 7L6G
  three-of-six result is a true-copy acceptance shortfall and must not be
  relabelled, fabricated, or hidden by a speculative fallback.
- The 8-CPU/32-GB, at-most-four-attempt profile finished in 1:55:59. Slurm
  reported 11.501212 GB maximum memory. Sixteen GB is therefore the bounded
  starting recommendation for the next comparable approved run; retain eight
  requested CPUs and the four-attempt concurrency until CPU accounting is more
  interpretable. The reported 16 logical CPUs and 0.3% CPU utilisation do not
  cleanly describe the requested eight CPUs plus child Phenix processes.

### Accomplishments

- Retrieved reviewed logs with `--tail 200` and collected through the reviewed
  wrapper. Verified exactly 23 typed cases, 18 first-copy attempts, 11
  positives, seven wrong-model searches, and five typed boundaries.
- All 18 first-copy records are `completed_hit`; ten add-copy series are
  `completed_hit`; the sole no-extension series is 7L6G
  `completed_no_hit`, best count three, parent retained. All 11 refinements are
  `completed_success`, and all 11 sequence assessments are `completed_hit`.
  Required output checksums are present.
- Verified ten positive truth counts at 1, 2, 3, or 4; four
  `no_reportable_identity` boundaries; one
  `assumption_violation_abstained` boundary; and all seven wrong models retained
  for comparison without displacing truth. Every candidate was retained,
  LLG/TFZ remained ranking annotations, and no generalisation claim was made.
- Verified 29 native Phaser sections at exactly 200 lines each, all seven
  Phenix 2.1-6048 qualification probes, and matching local/remote artefact
  checksums. Updated the roadmap with the bounded resource review and explicit
  **hold; Prototype 0.2 is not yet accepted** decision. No runtime or score
  configuration changed.
- Deleted the existing `continue-prokaryotic-control-roadmap` heartbeat after
  the retained run became terminal. There is no active run left to poll, and no
  replacement monitor was created while the roadmap waits at its human gate.

### Immutable evidence

- Run `gtd-control-matrix-20260816T185831Z-cbdebdb3e534-79287e54`, Slurm job
  `10932049`, ran from 2026-08-16T18:59:06Z to 20:55:03Z and ended
  `COMPLETED`, exit code 0, failure class `success`. Source commit is
  `cbdebdb3e5348d379f8a8c0c8144753d73aa9988`; nf-helper commit is
  `82431e4c56cb4cd2ef4ea67321fd01fad7ba65cb`; Pixi is 0.76.2; Pixi-lock
  SHA-256 is
  `a31c520126e559154433546f45b92d2617bc622f89ffd6b0422c0579c0dda66b`.
- Archive, import-manifest, and Phenix-manifest SHA-256 values are
  `9d85504e9605a2ebdcb25b4a6d674104e2e2c96ca6d6dee071c3199f1dd91e21`,
  `97132162e558df1c9087aab1826a32e954eb3477b2b241eb9930b0655cf74b40`,
  and `0410c2b835a8de91061cb727bf5eb007cfac82b787e857cefc5fd549b5c3bad1`.
- Summary, case, first-copy, add-copy, refinement, sequence, and bounded-log
  SHA-256 values are respectively
  `c781d2914d5d7b6e4bdd7d626eec0bbe25d70fa4d30bd4bb9f9a25e540293d80`,
  `2521045703b7b051cdc90586bfa652e3d9257b38668a5bf3bc68bf8e13618804`,
  `b1596ec14b288aa50922898061428bdeb0e9a0b07f2700ea7045060add5e2f0d`,
  `4b7fd4d920fa02f17ed68f7977a29f04c422c88f1c74963607be97e17b9359c2`,
  `00d7508b61cc618b720eda5eea7c80b98942ee91f016eb72c80e98b0f2c76681`,
  `d0f3d3c1028e9d1884bea4a95c93b0ae8aa388d80732dc96f46d8b2e3f4f7276`,
  and `ea0ea594bf7ff834545e1c8e7798f6fb09d88102b9bf88b79e95a3bb72b33b68`;
  every collected digest matches the remote inventory.

### Unresolved work

- The user/scientific checkpoint must decide whether to accept Prototype 0.2
  with the explicit 7L6G limitation or authorise a separately scoped,
  truth-labelled same-component search-strategy increment. No further matrix
  rerun or software correction is evidence-backed now.
- M6 cannot execute until an independently reviewable leakage-controlled
  manifest and predeclared criteria receive explicit approval. The three
  unknown operator crystals remain deferred until after the M6 release gate.

### Next exact starting point

No repository command is authorised before the Prototype 0.2 disposition. Once
the user supplies it, start with `git status --short` and preserve this
uncommitted roadmap/evidence milestone for the next coherent code or benchmark
commit; do not create a documentation-only CI cycle.

## 2026-08-16T22:49:10Z - Prototype 0.2 and M6 protocol approved

### Discoveries

- The user accepted Prototype 0.2 with the explicit limitation that 7L6G
  supports three rather than its declared six copies and directed M6 to
  proceed. No 7L6G rerun, relabelling, fabricated copy, or new search fallback
  is authorised.
- The approved independent set comprises 12 prokaryotic positives in 12
  distinct RCSB 30% sequence clusters with no overlap to the 11 M5 positive
  clusters, 12 leakage-controlled replays, 20 open-set negatives, four known
  heteromeric abstention controls, and 15 typed hardening cases: exactly 63.
- All 16 public coordinate/structure-factor pairs, 15 versioned RefSeq
  proteomes, and the RCSB 30%/70% cluster snapshots were independently fetched
  outside Git and matched their frozen per-file sizes and SHA-256 values. The
  two cluster snapshot SHA-256 values are
  `2ffcb403da7de2e365d7c300a7548c6dcbdadac98b6ac5eb923abb71fdbe403d`
  and
  `dd4990122e5c1c6b8bb2a4ffbce9cfc3dabe5a52a265dab94757f9a512a699c8`.

### Accomplishments

- Added the truth-facing protocol contract and exact approved manifest, a
  deterministic content-addressed runner archive builder, a separate
  truth-side evaluator, and CLI commands to validate, build, and evaluate M6.
  The archive builder scans every byte for PDB, accession, target-sequence, and
  cluster truth tokens and emits only opaque `M6Cnnn` case IDs.
- Encoded the predeclared 100% candidate-retention, zero-false-assignment,
  4/4-abstention, 2/2-duplicate-ambiguity, typed-edge, reproducibility,
  provenance, bounded-resource, operational-performance, and
  leakage-performance gates. LLG/TFZ remain annotations only.
- Reconciled the preserved M5 evidence/roadmap changes with the accepted
  limitation and approved M6 plan, and documented module inputs, outputs,
  versions, failure states, cache identity, resource profile, and tests.
- Six focused M6 tests pass. One complete `pixi run --locked check` then passed
  formatting, lint, strict typing, 409 unit tests, 57 contract tests, 48
  integration tests, schemas, public-panel validation, documentation links,
  actionlint, Nextflow syntax/stubs, and all reviewed Bash syntax checks.

### Immutable evidence

- Protocol ID is `m6_independent_prokaryote_homomer_v1`; the tracked manifest
  is `benchmarks/m6/protocol.yaml`. The pinned leakage boundary is MMseqs2
  18.8cc5c, identity at least 70%, coverage at least 80%, across every model
  route, with exact deposited coordinates always excluded.
- The core and assumption NCBI response SHA-256 values are
  `15d4b76d6e4c3afc1cce0427b0c853b12c0c0b5a22397025696bd8cee329c736`
  and
  `60115a0cd4680d81a9aca333f51523e5a9e17e60b95250981afd9793fa428b40`.
  Exact per-proteome and RCSB file hashes are frozen in the manifest.
- Approved starting resources are two separately attributable Viper stages,
  each eight CPUs, 16 GB, at most four concurrent Phenix attempts, and a
  24-hour scheduler ceiling. This is not a tool timeout.

### Unresolved work

- Implement the trusted source preparer, all-route leakage-policy enforcement,
  normal-component runner/collector, and reviewed bounded Viper profile. Build
  the real truth-isolated archive only after those contracts pass.
- Push and watch exactly one CI run for this first coherent M6 increment, then
  deploy checksum-reviewed tooling. Do not stage biological truth to the
  runner, start unknown operator crystals, or implement heteromer
  reconstruction.

### Next exact starting point

Run `git status --short`, inspect the full diff and `git diff --check`, stage
only this coherent M5-evidence/M6-contract increment, and create one commit.

## 2026-08-16T23:39:01Z - Real M6 inputs and runner qualification ready

### Discoveries

- The frozen 8AI1 structure-factor file contains two reflection blocks but
  exactly one block with usable observations. The trusted preparer now accepts
  only that guarded form and still fails unless exactly one observed-data block
  resolves.
- Several public files expose equal-priority observation pairs with identical
  value/sigma arrays. The preflight now selects the deterministic first pair,
  records `equivalent_observation_arrays`, and preserves review status; unequal
  pairs remain the existing fail-closed `ambiguous_observation_arrays` state.
- RefSeq accessions cannot remain in the runner without breaking truth
  isolation. The benchmark therefore disables accession-keyed AFDB exact
  lookup, while retaining PDB-sequence and local ProstT5/Foldseek as its
  enabled discovery routes. This makes operational recovery stricter and does
  not weaken the all-enabled-route leakage boundary.

### Accomplishments

- Added the offline trusted M6 preparer. It verifies every frozen source size
  and checksum, sanitises MTZ metadata, replaces catalogue identifiers with
  opaque locus hashes, creates all predeclared catalogue/MTZ/fault variants,
  and keeps `private_truth_map.json` outside the runner archive.
- Added a truthless runner verifier for exactly 63 opaque cases. It rechecks
  the content-addressed inventory, FASTA/MTZ/JSON contracts, typed observation
  states, and the retain-all/LLG-TFZ-annotation-only policy.
- Added the reviewed Viper `m6-inputs` staging and qualification profile. It
  accepts only an explicitly SHA-confirmed archive below `.untracked`, repeats
  local and remote checksum/media validation, and requests only one CPU and
  4 GB because it performs no search or Phenix execution.
- The preceding protocol commit
  `a4e811508141e7b6f154b92e08a787c0b16f49e1` passed GitHub Actions run
  `31977442031` with Pixi 0.76.2. The deployed dispatcher, job-wrapper, and
  recovery SHA-256 values were respectively
  `69e4959eb9ce3bcc3ff287b7e92db67425fd5b76004c9303f3e10b02cc2e0e5d`,
  `6d679a06a14f80fb68432fac38b16606486ae00d4b83bfe563adedc5de0a50a7`,
  and `0db4c5f3542ce4d387ac019e33717d5e405ac957efb216b05c52828a851808f4`.
- Focused parser/M6/HPC/dispatcher coverage passed 156 tests. One complete
  `pixi run --locked check` then passed formatting, lint, strict typing, 419
  unit tests, 57 contract tests, 49 integration tests, schemas, public-panel
  validation, documentation links, actionlint, Nextflow syntax/stubs, and all
  reviewed Bash syntax checks.

### Immutable evidence

- The real truth-isolated candidate archive contains exactly 63 cases and 64
  unique objects. Its size is 146,780,160 bytes; archive SHA-256 is
  `91ea40f332e6d188567d0a437115c95547ebfb59b43f63bc95cd02ebb0b22f7c`;
  runner-manifest SHA-256 is
  `19b52d32cab618e04a504760b252371df62c8f58a8a233a0c23eebbd13ae9e38`.
- Local qualification verified all 64 objects and 100% retain-all policy. It
  observed 60 cases with selected observations and three deliberately typed
  no-selection cases: the two map-only controls and one conflicting-column
  control. No private truth map or public accession/PDB truth token entered the
  archive.

### Unresolved work

- Commit and deploy this coherent preparer/verifier/profile milestone, then run
  the small Viper input qualification. It is pre-execution evidence and must
  not be counted as either final M6 scientific run ID.
- Implement and execute the two approved 8-CPU/16-GB scientific stages with a
  trusted all-route model-exclusion transition and truthless downstream
  runner. Collect both immutable results, join truth only after checksums are
  fixed, evaluate every predeclared gate, and issue an explicit accept/hold
  internal-release decision. Do not substitute unknown operator crystals or
  revisit 7L6G.

### Next exact starting point

Run `git status --short`, inspect `git diff --check` and the complete diff,
stage only this M6 real-input/qualification milestone, and create one coherent
commit. Push once, watch one GitHub Actions run, deploy the reviewed tools, and
stage the confirmed archive with `m6-inputs-stage`.

## 2026-08-17T00:59:35Z - M6 scientific execution boundary passes focused checks

### Discoveries

- Foldseek `fident` is a 3Di metric and cannot satisfy the approved amino-acid
  leakage rule. A Foldseek proposal therefore advances only when the same
  opaque candidate and PDB source-sequence digest has a pinned direct-MMseqs2
  alignment; otherwise it is retained as an
  `amino_acid_alignment_unavailable` annotation and fails closed.
- The scientific outputs can exceed the reviewed collection bound if every
  sequence score is duplicated into the case report. Full raw records now stay
  retained on Viper, while collection uses compact per-case/sequence summaries
  plus a deterministic gzip containing every candidate rank.
- A completed-output `--resume` path can verify immutable inputs and every
  output checksum without rerunning Phenix. The job wrapper compares the full
  pre/post-resume output inventory byte for byte.

### Accomplishments

- Implemented the opaque operational and leakage runners: catalogue import,
  MTZ preflight, cached PDB-sequence and ProstT5/Foldseek discovery, the narrow
  trusted exact-deposition/leakage transition, bounded model preparation and
  Matthews hypotheses, first-copy/add-copy Phenix, refinement, and sequence
  assessment. Candidate and parent retention remain unconditional; LLG/TFZ
  only order the at-most-five refinement/sequence advancement seeds.
- Added deterministic output verification, cache-key invalidation probes,
  partial-output rejection, compact truth-side evidence assembly, and an
  explicit hold for any unexpected execution failure.
- Added reviewed `m6-operational` and `m6-leakage` Viper profiles. Each fixes
  8 CPUs, 16 GB, four concurrent Phenix attempts, a 24-hour Slurm ceiling, no
  tool runtime timeout, checksum-confirmed runner transfer, bounded log tails,
  and checksum-gated collection.
- Focused M6/parser/model-policy tests passed 34 cases. Focused controller,
  wrapper, build, and fake-Slurm integration tests passed 120 cases. Ruff,
  strict typing, and both reviewed Bash syntax checks also passed.
- One complete `pixi run --locked check` passed formatting, lint, strict
  typing, 429 unit tests, 57 contract tests, 50 integration tests, schemas,
  public-panel validation, documentation links, actionlint, Nextflow syntax and
  stubs, and all reviewed Bash syntax checks.

### Immutable evidence

- Input qualification run
  `gtd-m6-inputs-20260816T235752Z-61f58daec3a9-f6314643` (Slurm `10933548`)
  completed successfully with exit 0. It verified exactly 63 cases and 64
  objects; qualification SHA-256 is
  `92eddb9b26b24519ac66b6c1f5fdedd700dc2b9c5b450e3bc428af0194b17f36`.
- Its source commit is `61f58daec3a96bce060514be4ed9ed7ccff260e8`,
  nf-helper commit is `82431e4c56cb4cd2ef4ea67321fd01fad7ba65cb`,
  Pixi is 0.76.2, lock SHA-256 is
  `a31c520126e559154433546f45b92d2617bc622f89ffd6b0422c0579c0dda66b`,
  runner archive SHA-256 is
  `91ea40f332e6d188567d0a437115c95547ebfb59b43f63bc95cd02ebb0b22f7c`,
  and runner-manifest SHA-256 is
  `19b52d32cab618e04a504760b252371df62c8f58a8a233a0c23eebbd13ae9e38`.

### Unresolved work

- Commit this code, tests, profiles, documentation, and retained journal update
  together; push once, watch one GitHub Actions run, deploy checksum-reviewed
  tools, and run the operational and leakage Viper stages sequentially.
- Collect both terminal scientific runs, classify evidence before any code
  edit, assemble all 63 truth-side assessments, and issue the frozen M6
  accept/hold decision. Do not revisit 7L6G or the three unknown crystals.

### Next exact starting point

Run `git diff --check`, inspect the staged diff, and create the coherent M6
scientific-execution commit.

## 2026-08-17T01:41:09Z - Viper M6 runtime binding corrected before submission

### Discoveries

- GitHub Actions run `31984437384` passed the scientific-execution commit
  `82d34e918b82e4b1b2805b480cb182330e2e4376` under Pixi 0.76.2. The
  deterministic local controller built from that commit has SHA-256
  `8be9914f46c5b15e25a95757b6bcffbb14203ce49807bef5efc70d8490c44d67`.
- The first scientific stage reached no remote run because the desktop sandbox
  denied its existing SSH control socket. Retried through the same reviewed
  wrapper with the approved host permission, run
  `gtd-m6-operational-20260817T012344Z-82d34e918b82-04d7979d` then failed
  safely during staging, before submission or Phenix, with `environment_failure`:
  `fixed P0 configuration is absent or unsafe`.
- This was a Viper adapter defect, not scientific evidence. M6 had inherited
  the legacy P0 single-root configuration even though Viper deliberately keeps
  its verified database under `/ptmp` and its licensed Phenix installation
  under `/viper/u1`. The completed Viper database has a runtime manifest, but
  that split layout cannot be represented by the P0 single-root contract.

### Accomplishments

- Narrowed only the M6 environment binding. The operational and leakage stages
  now require the existing checksum-validated Viper database configuration in
  runtime mode and the exact Phenix manifest from the fixed Viper site
  configuration. Their paths and checksums are frozen into per-run state before
  the opaque runner archive is accepted; M6 no longer reads `P0_CONFIG`.
- Added a focused contract regression preventing the legacy dependency from
  returning. The change does not alter the frozen protocol, model exclusion,
  resource limits, Phenix concurrency, ranking, retain-all policy, or any
  acceptance criterion.
- Focused checks passed 10 repository-policy contracts and all 45 fake remote
  dispatcher integrations. One complete `pixi run --locked check` then passed
  formatting, lint, strict typing, 429 unit tests, 58 contract tests, 50
  integration tests, schemas, public-panel validation, documentation links,
  actionlint, Nextflow syntax/stubs, and all reviewed Bash syntax checks.

### Immutable evidence

- The failed stage has no Slurm job ID and made no scientific attempt. The
  approved 63-case archive remains unchanged at SHA-256
  `91ea40f332e6d188567d0a437115c95547ebfb59b43f63bc95cd02ebb0b22f7c`;
  its runner-manifest SHA-256 remains
  `19b52d32cab618e04a504760b252371df62c8f58a8a233a0c23eebbd13ae9e38`.
- The previously completed Viper database remains authoritative; it was not
  rebuilt or modified. No unknown operator crystal or 7L6G work was performed.

### Unresolved work

- Commit and push this focused adapter correction, watch exactly one GitHub
  Actions run, deploy its checksum-reviewed controller/dispatcher/job wrapper,
  and stage a new immutable operational run. Retain the failed stage untouched.
- Execute and collect the operational and leakage tracks sequentially, assemble
  the 63 truth-side assessments only after both outputs are immutable, and issue
  the frozen M6 accept/hold decision.

### Next exact starting point

Run `git status --short`, inspect the complete diff, and create the single
coherent Viper M6 runtime-binding commit.

## 2026-08-17T02:08:02Z - Opaque M6 media types restored at execution boundary

### Discoveries

- Corrected operational run
  `gtd-m6-operational-20260817T014921Z-692ed9197a9b-529417a8` staged all 63
  cases and 64 objects, then Slurm job `10934054` ran on `vipc2144`. Phenix
  2.1-6048 qualified all seven fixed commands before the scientific runner
  started.
- The job ended after 37 seconds with exit 1 and `test_failure`, before any
  search or Phaser attempt. The first catalogue import passed the opaque
  content-addressed analysis-config object directly to suffix-based contract
  loading, which failed with `cannot infer input format from suffix`.
- The runner manifest already declares every object's media type. Removing
  filename suffixes for content addressing was correct for truth isolation,
  but the blind execution adapter had not restored that non-truth format
  metadata for downstream tools. This is a software failure, not scientific or
  infrastructure evidence.

### Accomplishments

- Added one guarded materialisation boundary. Each already-qualified opaque
  object is copied once to a digest-only basename plus the suffix implied by
  its declared media type (`.json`, `.mtz`, `.faa`, or `.txt`), then its size
  and SHA-256 are rechecked before catalogue import, MTZ preflight, or Phenix.
  Case IDs and all scientific content remain opaque and unchanged.
- Bumped the scientific adapter identity to `m6-scientific-run-v2`, preventing
  a v1 output from being accepted by checksum-only resume. Added a focused
  regression covering typed materialisation and reuse of the four shared test
  objects across all 63 cases.
- Focused M6 tests passed 21 cases. One complete `pixi run --locked check`
  passed formatting, lint, strict typing, 430 unit tests, 58 contract tests, 50
  integration tests, schemas, public-panel validation, documentation links,
  actionlint, Nextflow syntax/stubs, and all reviewed Bash syntax checks.

### Immutable evidence

- Failed job `10934054` has collection failure signature
  `517298370fad69e6dc9df3da64ee66e840242cc96af2c5447201d421003a74da`.
  It used source `692ed9197a9baa2cdc827fdb957dcc32f9c6cd12`, nf-helper
  `82431e4c56cb4cd2ef4ea67321fd01fad7ba65cb`, Pixi 0.76.2, lock SHA-256
  `a31c520126e559154433546f45b92d2617bc622f89ffd6b0422c0579c0dda66b`,
  database-config SHA-256
  `bb2deb19d147769e9e2338e66c75d5c5986e336ae72deb4ae85257871ead1a30`,
  and database-manifest SHA-256
  `ffa0c2cc4b7bb68996584776c319beda7aec5d4c991f0fc3ff62c46a8d8cb68b`.
- The runner archive and manifest stayed fixed at SHA-256
  `91ea40f332e6d188567d0a437115c95547ebfb59b43f63bc95cd02ebb0b22f7c`
  and `19b52d32cab618e04a504760b252371df62c8f58a8a233a0c23eebbd13ae9e38`.
  The deployed dispatcher, job wrapper, and recovery SHA-256 values were
  `e46622449f4c088d38ee7f5836bb88a502fd4f0c5c0a7cb5409f2390b7aac7ab`,
  `3be01421bef61228e62cd3f323350b2b210162b7e0806c876155b9b80843568c`,
  and `0db4c5f3542ce4d387ac019e33717d5e405ac957efb216b05c52828a851808f4`.

### Unresolved work

- Commit and push this narrow adapter correction, watch exactly one GitHub
  Actions run, deploy the matching reviewed tools, and submit a new immutable
  operational attempt from the unchanged archive.
- If that run becomes terminal, collect and classify it before any further
  edit. Proceed to the leakage track only after operational evidence is
  complete and free of a demonstrated software defect.

### Next exact starting point

Run `git status --short`, inspect and stage only the media-materialisation code,
test, and retained journal evidence, then create one coherent commit.

## 2026-08-17T02:26:44Z - Materialised-input successor executing on Viper

### Accomplishments and immutable evidence

- Committed the guarded media-type materialisation fix as
  `39a024ad879c30ac6d5b8b782c8d96feb9473bca`, pushed once, and watched only
  GitHub Actions run `31987115933`; it passed under Pixi 0.76.2. The installed
  deterministic controller SHA-256 is
  `30ad385d250ccffe4c2170bb3ebdfa5cb82406446f74162cec03cb677c3716be`.
- Deployed matching tools with dispatcher, job-wrapper, and recovery SHA-256
  values `e46622449f4c088d38ee7f5836bb88a502fd4f0c5c0a7cb5409f2390b7aac7ab`,
  `3be01421bef61228e62cd3f323350b2b210162b7e0806c876155b9b80843568c`,
  and `0db4c5f3542ce4d387ac019e33717d5e405ac957efb216b05c52828a851808f4`.
- Staged successor
  `gtd-m6-operational-20260817T021453Z-39a024ad879c-28f5a82e` from the
  unchanged 63-case/64-object archive and submitted it as Slurm job `10934191`.
  It uses 8 CPUs, 16 GB, at most four concurrent Phenix attempts, the 24-hour
  scheduler ceiling, and no per-tool timeout. Last observed state was
  `RUNNING`, terminal=false.

### Unresolved work

- Leave job `10934191` untouched while non-terminal. On terminal state, run
  bounded 200-line logs and collect through the reviewed wrapper, then classify
  the complete evidence before any edit.
- If operational execution is sound, stage the leakage track from the same
  frozen archive. After both collections, assemble all 63 truth-side
  assessments and issue the predeclared M6 accept/hold decision.

### Next exact starting point

Run `/Users/asuq/.local/bin/nf-gtd-hpc-test --no-progress status --run-id
gtd-m6-operational-20260817T021453Z-39a024ad879c-28f5a82e`. Do not inspect
partial outputs or infer failure from scheduler silence.

## 2026-08-17T04:41:25Z - Unmapped Foldseek proposals retained fail-closed

### Discoveries

- Operational job `10934191` ran from `02:22:03Z` to `04:29:17Z` on
  `vipc2144`. Phenix 2.1-6048 qualified all seven commands. The materialised
  JSON/FASTA boundary passed, the first opaque catalogue imported 4,300 source
  records into 4,259 sequence groups, and MMseqs2 18.8cc5c completed 4,166
  eligible PDB-sequence queries with 8,161 retained hits.
- The full ProstT5/Foldseek search also completed successfully for all 4,166
  eligible queries under Foldseek 10.941cd33. Only during output normalisation
  did the adapter abort because five retained Foldseek targets (`7DU3_A`,
  `8Q4F_K`, `8Q4F_d`, `8T8O_C`, and `8T8O_N`) lacked entries in the separate
  PDB-sequence coordinate-mapping table.
- This is a software boundary failure, not a search, Phenix, infrastructure, or
  scientific no-hit result. Those raw hits are valid Foldseek observations but
  cannot safely become coordinate models without a sequence/coordinate
  mapping. Aborting discarded the entire batch instead of retaining the five
  proposals as model-ineligible annotations, contrary to the frozen M6
  retain-all policy.

### Accomplishments

- Added one explicit `retain_unmapped_targets` search option, defaulting to
  false so every non-M6 caller remains fail-loud. M6 alone enables it. Missing
  mappings now yield deferred structural-hit records with the parsed PDB/chain,
  all raw Foldseek metrics, and an explicit unavailable-mapping state; no
  sequence digest, coordinate mapping, or model is guessed.
- The trusted M6 model transition now rejects those proposals fail-closed as
  `coordinate_mapping_unavailable` while retaining each full hit as an
  annotation and retaining every catalogue candidate. Adapter identities were
  advanced for the shared Foldseek search, trusted model policy, and M6
  scientific run so cached v3/v1/v2 semantics cannot be reused.
- Focused structure-search and M6 tests passed 34 cases, including preservation
  of strict default behaviour, retained M6 unmapped-hit evidence, and the new
  trusted rejection class. One complete `pixi run --locked check` passed
  formatting, lint, strict typing, 431 unit tests, 58 contract tests, 50
  integration tests, schemas, public-panel validation, documentation links,
  actionlint, Nextflow syntax/stubs, and all reviewed Bash syntax checks.

### Immutable evidence

- Failed run
  `gtd-m6-operational-20260817T021453Z-39a024ad879c-28f5a82e` ended with exit
  1 and `test_failure`; its collection failure signature is
  `f754aa5436e4fe7a63c2f0387229f2383ffe85f73315fc805cb95fe80c51f7af`.
  No Phaser attempt started.
- Source was `39a024ad879c30ac6d5b8b782c8d96feb9473bca`, nf-helper was
  `82431e4c56cb4cd2ef4ea67321fd01fad7ba65cb`, Pixi was 0.76.2, and lock,
  database-manifest, and database-config SHA-256 values were respectively
  `a31c520126e559154433546f45b92d2617bc622f89ffd6b0422c0579c0dda66b`,
  `ffa0c2cc4b7bb68996584776c319beda7aec5d4c991f0fc3ff62c46a8d8cb68b`,
  and `bb2deb19d147769e9e2338e66c75d5c5986e336ae72deb4ae85257871ead1a30`.
  The 63-case archive and runner manifest remain unchanged.

### Unresolved work

- Commit and push this focused retain-as-annotation correction, watch one CI
  run, deploy the exact reviewed tools, and submit a new immutable operational
  attempt. Do not reuse partial predecessor outputs or alter the frozen search
  limits merely to avoid the two-hour full query.
- On terminal successor evidence, classify before editing. Begin the leakage
  track only after operational execution completes without a software defect.

### Next exact starting point

Run `git status --short`, inspect the complete diff, and create one coherent
unmapped-Foldseek retention commit carrying this journal evidence.

## 2026-08-17T04:51:52Z - Retain-as-annotation successor submitted

### Accomplishments and immutable evidence

- Committed the focused correction as
  `ebffd2b75ed7ec016be7c76ede7c868c443fd415`, pushed once, and watched only
  GitHub Actions run `31995429609`; it passed under Pixi 0.76.2. The installed
  controller SHA-256 is
  `f3e86b45819a6d3edf581218a81dc4f03fc1cdcfef4ff519e95f6c3fe836318c`.
- Deployed matching tools with dispatcher, job-wrapper, and recovery SHA-256
  values `e46622449f4c088d38ee7f5836bb88a502fd4f0c5c0a7cb5409f2390b7aac7ab`,
  `3be01421bef61228e62cd3f323350b2b210162b7e0806c876155b9b80843568c`,
  and `0db4c5f3542ce4d387ac019e33717d5e405ac957efb216b05c52828a851808f4`.
- Staged
  `gtd-m6-operational-20260817T045037Z-ebffd2b75ed7-6be05fd4` from the
  unchanged 63-case/64-object archive and submitted it as Slurm job `10934859`.
  Its fixed resources remain 8 CPUs, 16 GB, at most four concurrent Phenix
  attempts, a 24-hour scheduler ceiling, and no per-tool timeout. Initial state
  was `PENDING`, terminal=false.

### Unresolved work

- Leave job `10934859` untouched while non-terminal. On terminal state, obtain
  bounded logs and collection through the reviewed wrapper, then classify the
  complete evidence before any edit or leakage-track submission.

### Next exact starting point

Run `/Users/asuq/.local/bin/nf-gtd-hpc-test --no-progress status --run-id
gtd-m6-operational-20260817T045037Z-ebffd2b75ed7-6be05fd4`.

## 2026-08-17T11:35:13Z - M6 Nextflow/Slurm fan-out rewrite locally verified

### Discoveries and accomplishments

- Replaced future M6 execution with a typed DSL2 driver/worker graph. Unique
  catalogues, cases, hypotheses, seeds, and finalists are Nextflow channel
  items; Python now executes one task or deterministically aggregates completed
  records. The legacy v3 verifier remains so the retained monolithic
  operational run stays collectable, but its execution CLI is disabled.
- Avoided one database/model load per sample. The fixed runner's 29 catalogues
  contain 70,864 unique exact sequences and 23,020,184 unique residues after
  global deduplication. The checksummed execution policy therefore emits one
  MMseqs2 batch capped at 100,000 sequences/30 million residues and about eight
  Foldseek batches capped at 10,000 sequences/3 million residues. MMseqs2 and
  Foldseek fork independently and each search job requests 32 CPUs/16 GB.
- Bound shared truthless import/search cache identities to input content, the
  database manifest, exact parameters, the Pixi lock, the execution policy,
  and adapter versions. Policy and all downstream case work remain
  track-specific. Added a durable `AGENTS.md` invariant and architecture
  document to prevent Python/Bash multi-sample scheduling and unsafe cache
  reuse from returning.
- Added child Slurm resource evidence with native IDs, requested CPU/memory/time,
  observed CPU percentage and peak RSS, peak simultaneous jobs/aggregate
  allocation/Phenix jobs, and per-job policy checks. Mixed legacy-operational
  plus Nextflow-leakage collection is explicitly supported with both source
  commits retained.
- Added the non-acceptance `m6-nextflow-smoke` profile. It will run the two-case
  `-stub-run` graph through real Slurm process boundaries, require distinct
  32-CPU MMseqs2/Foldseek child IDs, prove byte-identical cached resume, and
  verify that only truthless discovery crosses tracks.
- Corrected two implementation defects found during review: the real catalogue
  process used the wrong tuple index, and early/zero-hypothesis cases did not
  carry the complete retained catalogue into final evidence assembly.

### Local evidence

- Focused M6 unit tests: 28 passed, including global batch/cache invalidation,
  typed early-case assembly, legacy/new collection, and execution-policy gates.
- Contract tests: 59 passed. Targeted fake-Viper submission tests: 2 passed.
- Ruff lint/format, ty type checking, Nextflow DSL2 lint, both reviewed-wrapper
  Bash syntax checks, and `git diff --check` passed.
- The complete `pixi run --locked nextflow-stub` suite passed. Its M6 branch
  demonstrated overlapping MMseqs2/Foldseek stub workers, all hypothesis/seed/
  finalist and typed-empty branches, fully cached resume, byte-identical
  outputs, and reuse of only the three truthless store stages across tracks.
- The retained production run was not queried, modified, cancelled, cleaned,
  or used to seed the new cache during this implementation turn.

### Unresolved work

- The architecture increment remains uncommitted by request to pause. Run the
  one complete locked repository gate, inspect the complete diff, then create
  one coherent code/test/docs commit, push once, and watch one CI run.
- After green CI, install and deploy the reviewed tools, run and collect the
  two-case Viper `m6-nextflow-smoke`, then branch M6 execution from the retained
  operational run's terminal evidence. Do not submit scientific M6 work before
  the smoke passes, and never import monolithic discovery output into the new
  shared store.

### Next exact starting point

After the mandatory `AGENTS.md`/newest-journal/status inspection, run
`pixi run --locked check` from the repository root.

## 2026-08-17T12:56:12Z - M6 fan-out architecture passes the locked gate

### Accomplishments and immutable local evidence

- The one complete `pixi run --locked check` passed: 438 unit, 59 contract,
  and 51 integration tests plus formatting, lint, type checking, schemas,
  public-panel validation, documentation links, actionlint, Nextflow syntax,
  the complete Nextflow stub suite, and reviewed-wrapper syntax.
- Complete diff review found and corrected two narrow provenance/authority
  issues before staging: scientific results are now declared under the actual
  `artifacts/m6-nextflow-results` retention root, and the non-acceptance
  `m6-nextflow-smoke` profile is rejected outside `viper-cpu` locally and by
  the remote dispatcher. Focused lint/type/wrapper checks and four targeted
  unit/contract/integration tests passed after those corrections; the complete
  gate was not duplicated.
- The retained monolithic operational run and the new truthless shared cache
  remain untouched by this local verification work.

### Unresolved work

- Create the single coherent architecture commit, push once, and watch one CI
  run. After green CI, install and deploy the reviewed tools and execute the
  two-case Viper `m6-nextflow-smoke` before any rewritten scientific track.

### Next exact starting point

Stage only the reviewed architecture increment with `git add`, inspect the
staged diff, and create its coherent commit.

## 2026-08-17T13:07:17Z - Fan-out rollout ready behind retained operational run

### Accomplishments and immutable evidence

- Created and pushed the single coherent architecture commit
  `aa334b47db419d9cb6fbe3eed0ffea6fd950f20d`. GitHub Actions run
  `32032519420` passed once under Pixi 0.76.2 in 6m25s.
- Built and installed the matching local controller with SHA-256
  `a7a6e694ebb25f83049112b749cc5c710433c235be3b39b52c06500c0e759f22`.
  Deployed dispatcher, job-wrapper, and recovery SHA-256 values are
  `5aa8979ec1218c8187c4ed5f5fd0e67ac130beb8956354d82d314580446a8076`,
  `be2abafdd0a988614fdaf3f0d75d32abc7cdb140bea5b16f4a947c9802f2ee3b`,
  and `0db4c5f3542ce4d387ac019e33717d5e405ac957efb216b05c52828a851808f4`.
- Staged the non-acceptance smoke as
  `gtd-m6-nextflow-smoke-20260817T130616Z-aa334b47db41-dd678eaf` from the
  immutable commit and unchanged nf-helper commit
  `82431e4c56cb4cd2ef4ea67321fd01fad7ba65cb`.

### Changed blocker and unresolved work

- Smoke submission was correctly rejected because another managed test job is
  still active. One reviewed status query then confirmed retained operational
  run `gtd-m6-operational-20260817T045037Z-ebffd2b75ed7-6be05fd4`, Slurm job
  `10934859`, remains `RUNNING`, terminal=false. It was not modified, cancelled,
  cleaned, or used to seed the new cache.
- Continue monitoring only that retained run at the approved 30-minute cadence.
  When terminal, collect and classify it first; then submit the already-staged
  smoke. Do not stage a duplicate smoke or scientific run.

### Next exact starting point

Run the single reviewed status command for retained operational run
`gtd-m6-operational-20260817T045037Z-ebffd2b75ed7-6be05fd4` at the next
30-minute heartbeat.

## 2026-08-17T13:17:50Z - Current-version Slurm fan-out smoke submitted

### Approved state change and immutable evidence

- At the user's explicit direction, cancelled only superseded monolithic run
  `gtd-m6-operational-20260817T045037Z-ebffd2b75ed7-6be05fd4`, Slurm job
  `10934859`; the scheduler returned `CANCEL_REQUESTED`. Its partial artefacts
  remain retained. Do not clean, resume, monitor, or seed the new cache from it.
- Submitted the already-staged non-acceptance current-version smoke
  `gtd-m6-nextflow-smoke-20260817T130616Z-aa334b47db41-dd678eaf` as Slurm job
  `10938045`. It uses source commit
  `aa334b47db419d9cb6fbe3eed0ffea6fd950f20d`, nf-helper
  `82431e4c56cb4cd2ef4ea67321fd01fad7ba65cb`, a 2-CPU/8-GB driver, and
  separately scheduled 32-CPU/16-GB MMseqs2 and Foldseek stub workers.
- One initial status snapshot returned `PENDING`, terminal=false. No polling or
  runtime timeout was introduced.

### Unresolved work

- Monitor only smoke job `10938045` at the existing 30-minute cadence. When
  terminal, obtain bounded logs and collection, then verify native child Slurm
  IDs, per-job bounds, fully cached byte-identical resume, typed empty/active
  branches, and truthless-only cross-track store reuse. It is orchestration
  evidence and cannot count as M6 acceptance.
- After the smoke passes, stage a fresh full operational Nextflow track from
  the same frozen 63-case runner archive; the cancelled monolithic run no
  longer supplies acceptance evidence.

### Next exact starting point

Run `/Users/asuq/.local/bin/nf-gtd-hpc-test --no-progress status --run-id
gtd-m6-nextflow-smoke-20260817T130616Z-aa334b47db41-dd678eaf` at the next
30-minute heartbeat.

## 2026-08-17T14:02:23Z - Adversarial review identifies M6 and core stop gates

### Discoveries and local evidence

- Completed three independent read-only review passes covering scientific
  validity, Nextflow/HPC behaviour, and Python/schema/test boundaries. The
  consolidated report is `docs/adverse-code-review-2026-08-17.md`; it separates
  21 enduring pipeline findings from 13 temporary HPC/validation findings.
- Identified three M6 release-decision stop gates: correct-family recovery is
  not family-verified, exact false assignments are hard-coded absent during
  collection, and several edge controls derive their result from the injected
  descriptor instead of observed behaviour.
- Confirmed enduring high-priority defects including one-item consumption in
  integrated fan-out, incomplete Nextflow cache identities, ignored provider
  configuration, unpropagated crystallographic/Free-R choices, and packing-only
  copy support.
- The fresh complete `pixi run --locked check` passed with 439 unit, 59
  contract, and 51 integration tests plus every configured static, schema,
  documentation, Nextflow, and wrapper check. Focused synthetic probes
  reproduced the semantic findings that the green fixture suite misses.
- No remote service, scheduler, HPC job, private input, or generated scientific
  result was queried or modified.

### Unresolved work

- Hold M6 acceptance and do not submit an operational or leakage scientific
  track until the three report P0 findings and the 29-catalogue partition defect
  are corrected and covered by multi-item integration tests.
- Treat the submitted two-case smoke, if it completes, as orchestration-only
  evidence. Its one-catalogue fixture cannot clear the scientific or
  cardinality findings.
- Review and prioritise the enduring pipeline P1 findings before a general
  production release. Preserve the report and immutable validation evidence
  when later removing the temporary HPC/benchmark slice.

### Next exact starting point

At the next approved heartbeat, query only
`gtd-m6-nextflow-smoke-20260817T130616Z-aa334b47db41-dd678eaf` as previously
recorded. Before any M6 scientific submission, start from the P0 remediation
order in `docs/adverse-code-review-2026-08-17.md`.

## 2026-08-17T15:15:30Z - Real Slurm trace exposes narrow resource-parser defect

### Immutable Viper evidence and classification

- Smoke run `gtd-m6-nextflow-smoke-20260817T130616Z-aa334b47db41-dd678eaf`,
  Slurm job `10938045`, finished `FAILED` with exit code 1 and
  `test_failure`. Bounded logs and collection were retrieved through the
  reviewed wrapper; collection failure signature is
  `47fdd2b6c04f940db4e207df04fd5639efdb859c3bebae798394198857bf6b25`.
- All 21 child Slurm jobs completed before the outer wrapper failed. MMseqs2 and
  Foldseek used distinct native IDs `10938131` and `10938132`; each requested
  32 CPUs/16 GB and completed successfully. The active and typed-empty branches
  reached deterministic track aggregation.
- The demonstrated software defect is confined to resource-evidence parsing:
  Nextflow 26.04.6 emits bare `0` for unmeasurably small peak RSS and `1d` for a
  24-hour request, while the adapter accepted only unit-suffixed memory and
  hour/minute/second time. The failure occurred before resume/cross-track proof,
  so this run cannot pass the non-acceptance smoke gate.
- The trace also retained Nextflow warnings that executor-specific `$slurm` and
  `$local` settings were unrecognised at runtime. Per-job requests are directly
  evidenced, but queue-size/submission-rate enforcement is not claimed from
  this smoke and remains a separate execution-configuration finding.

### Focused correction and local evidence

- Added only the guarded trace-format support for memory `0` and day-suffixed
  durations, plus one focused regression using both exact representations.
  The corrected CLI normalised the retained real trace into 21 typed jobs with
  per-job bounds passed, 32 maximum CPUs, 16 GB maximum memory, and a 24-hour
  maximum scheduler request.
- The one complete `pixi run --locked check` passed after the correction: 439
  unit, 59 contract, and 51 integration tests plus every configured static,
  schema, documentation, Nextflow, and wrapper check.
- Preserved the independent adversarial review in
  `docs/adverse-code-review-2026-08-17.md`. Its three M6 P0 findings and the
  multi-catalogue partition defect remain hard stop gates: a replacement smoke
  may test orchestration, but no operational or leakage scientific run may be
  submitted until those findings are remediated with multi-item evidence.

### Unresolved work

- Create one focused parser/evidence commit, push once, watch one CI run,
  install/deploy matching tools, and submit one replacement two-case smoke.
- Do not start M6 scientific execution after the smoke; next scientific work is
  the separately reviewed P0 remediation order in the adverse review.

### Next exact starting point

Inspect and commit the focused parser regression, retained journal evidence,
and adversarial review as one coherent code/evidence milestone.

## 2026-08-17T15:24:27Z - Parser correction pushed; CI API temporarily unavailable

### Accomplishments and immutable local evidence

- Created and pushed focused commit
  `3a724be88d969a85212533eb69f02421bee47077`, containing the exact
  `0`/`1d` trace-parser regression and correction together with the retained
  development evidence and adversarial review.
- Built the deterministic matching controller locally with SHA-256
  `b4c814f87eed5c0e69d8a8c66196906810512f6ba3845b246b7f3135ea114606`.
  It has not been installed or deployed because CI is not yet verified.

### Changed blocker and unresolved work

- Authenticated GitHub CLI access remained configured, but repeated Actions and
  repository API requests returned connection errors or HTTP 404 while Git push
  continued to work over SSH. No CI conclusion was inferred, no second push or
  CI watch was created, and deployment/replacement smoke submission did not
  proceed ahead of CI.
- When GitHub API access returns, identify the single Actions run for commit
  `3a724be88d969a85212533eb69f02421bee47077` and watch it once. Only after a
  green result may the matching controller/tools be installed/deployed and one
  replacement non-acceptance smoke be staged/submitted.
- M6 scientific execution remains held independently by the adverse-review P0
  findings and multi-catalogue defect even if the replacement smoke passes.

### Next exact starting point

Run `gh run list --commit 3a724be88d969a85212533eb69f02421bee47077
--limit 5 --json databaseId,status,conclusion,workflowName,headSha,url,createdAt`
when GitHub connectivity is restored.

## 2026-08-17T15:47:46Z - Parser-corrected replacement smoke submitted

### Accomplishments and immutable evidence

- GitHub's REST Actions endpoints remained unavailable to both `gh` and the
  connected GitHub app, but the authenticated commit check-rollup returned the
  authoritative result: Actions run `32041874452`, job `95422511782`, completed
  `SUCCESS` for commit `3a724be88d969a85212533eb69f02421bee47077`
  under Pixi 0.76.2. No duplicate CI run or watch was created.
- Installed the matching controller with SHA-256
  `b4c814f87eed5c0e69d8a8c66196906810512f6ba3845b246b7f3135ea114606`.
  Deployed tools remain dispatcher
  `5aa8979ec1218c8187c4ed5f5fd0e67ac130beb8956354d82d314580446a8076`,
  job-wrapper
  `be2abafdd0a988614fdaf3f0d75d32abc7cdb140bea5b16f4a947c9802f2ee3b`,
  and recovery
  `0db4c5f3542ce4d387ac019e33717d5e405ac957efb216b05c52828a851808f4`;
  their source commit is now the parser-corrected revision.
- Temporarily stashed the unrelated uncommitted roadmap/journal files only to
  satisfy the clean-worktree deployment guard, then restored and dropped that
  exact stash after deployment. No user documentation change was discarded.
- Staged and submitted exactly one replacement non-acceptance smoke as
  `gtd-m6-nextflow-smoke-20260817T154618Z-3a724be88d96-ad6feaf7`, Slurm job
  `10939394`. Its initial state is `PENDING`, terminal=false.

### Unresolved work

- Monitor only replacement smoke job `10939394` at the existing 30-minute
  cadence. On terminal state, collect and verify the complete orchestration,
  child-resource, resume, and truthless-store evidence. Preserve the observed
  executor-scope warnings separately; do not infer queue/rate enforcement.
- Even a passing smoke cannot authorise an M6 scientific stage. The
  adverse-review DEV-P0-01 through DEV-P0-03 and DEV-P1-01 findings remain hard
  stop gates pending separate remediation and multi-catalogue evidence.

### Next exact starting point

Run `nf-gtd-hpc-test --no-progress status --run-id
gtd-m6-nextflow-smoke-20260817T154618Z-3a724be88d96-ad6feaf7` at the next
30-minute heartbeat.

## 2026-08-17T18:29:17Z - Parser-corrected Slurm fan-out smoke passes

### Discoveries and immutable evidence

- Replacement smoke
  `gtd-m6-nextflow-smoke-20260817T154618Z-3a724be88d96-ad6feaf7`, Slurm job
  `10939394`, ran from 2026-08-17T15:48:43Z to 18:07:11Z and finished
  `COMPLETED` with exit code 0 and failure class `success` from source commit
  `3a724be88d969a85212533eb69f02421bee47077` and nf-helper commit
  `82431e4c56cb4cd2ef4ea67321fd01fad7ba65cb` under Pixi 0.76.2.
- All 21 first-pass child Slurm jobs completed. PDB-sequence and Foldseek
  workers used distinct native IDs `10939508` and `10939510`, each requesting
  32 CPUs, 16 GB, and 24 hours. Observed maxima were 32 aggregate CPUs, 16 GB,
  one running job, one concurrent Phenix job, and 0.002 GB MaxRSS; all per-job
  bounds passed.
- The active M6C001 chain and typed-empty M6C057 chain both reached aggregate
  evidence. The operational resume cached all 18 non-store tasks and reused the
  three truthless stored discovery stages. The leakage track reused only
  catalogue import, MMseqs2, and Foldseek storage; track-specific reuse was
  false. Canonical resume output was byte-identical.
- Collected summary, resume, resource, and store-reuse SHA-256 values are
  `0030c51b743180f9c5ecd062a5cbdf9e4b22112cd90c3451fbf16d9bd47afcaa`,
  `d7a9b2d73fbd505fa4cb0a4cab205122b5e88814b82e9ab295a7b5a042af3612`,
  `ca4a6584c27a553d85c756d990bcceffcf3561d29b6a6f7c41790087826af11d`,
  and `dd52ff861f3a186ac9322c608ea3ab4fb1218dbef5876dce2183c78c8031e714`;
  every collected local digest matches the remote inventory.
- Nextflow 26.04.6 still reports the tracked unrecognised `$slurm` and `$local`
  executor-scope options. Per-job requests are evidenced, but queue-size,
  submission-rate, and aggregate-concurrency enforcement remain unclaimed.

### Classification and unresolved work

- This is a successful non-acceptance orchestration smoke only. It proves real
  Slurm child fan-out, typed branches, deterministic resume, bounded per-job
  resources, and truthless-only cross-track store reuse for the two-case stub.
  It cannot clear M6 scientific or multi-catalogue gates.
- Operational and leakage M6 scientific tracks remain held. Begin the approved
  R0A remediation for `DEV-P0-01` through `DEV-P0-03` and `DEV-P1-01`; do not
  stage another Viper run until focused regressions, the complete locked gate,
  CI, reviewed deployment, and a corrected multi-item smoke are ready.

### Next exact starting point

Add the focused family-truth, emitted-identity/false-assignment,
observation-derived edge, and two-catalogue fan-out regressions. Implement only
the smallest coherent evidence-contract correction and run the affected tests
before one complete locked gate.

## 2026-08-17T19:47:35Z - M6 R0A stop-gate correction locally integrated

### Discoveries

- The frozen RCSB 30% and 70% cluster snapshots are independent partitions,
  not a guaranteed hierarchy. Their complete frozen checksums and all 24 target
  line checksums validate, but T10 has one 70%-cluster entity outside its 30%
  cluster. Leakage-safe family evidence therefore remains the explicit
  30%-minus-70% set without a containment assumption.
- T06 has operational PDB-family alternatives but no 30%-minus-70% family
  alternative. The operational correct-family denominator is consequently 12,
  while only the predeclared leakage denominator is 11.
- The real RCSB target lines were used only for a local verifier qualification
  and remain outside Git. Unit collection tests use a fully synthetic protocol
  and synthetic private truth, preventing family membership from entering the
  runner source checkout.

### Accomplishments and local evidence

- Replaced accepted-hit-count family claims with trusted snapshot verification,
  schema-1.1 private family truth, per-attempt PDB/entity classifications, and
  explicit exact-deposition/close-family prohibition gates.
- Added checksum-bound runner identity decisions derived from selected seed
  rows. Collection now carries `reported`, `ambiguous`, or `abstained`
  decisions unchanged; a complete collect-to-evaluate regression proves a
  reported wrong open-set digest produces `HOLD`.
- Replaced descriptor-derived edge success with content-addressed observed
  Matthews, MTZ, provider-authorisation, local HTTP-429, model-exhaustion, and
  Phenix-validation evidence. Contradicted or absent observations cannot pass
  the typed-edge gate.
- Converted shared M6 batch/search emissions to reusable values for every
  catalogue, expanded the stub to two catalogues plus two MMseqs2 and two
  Foldseek batches, and made batch/result aggregation independent of completion
  order with duplicate-ID rejection.
- Focused R0A tests pass: 57 tests. The complete unit suite passes 468 tests;
  contract and integration suites pass 59 and 51 tests. The expanded Nextflow
  stub, syntax check, and documentation-link check pass. The frozen public
  snapshots independently qualify 2/2 snapshots and 12/12 target families;
  T10 is correctly reported non-nested.

### Unresolved work

- Run one complete `pixi run --locked check`, inspect the full diff and staged
  scope, then create and push one coherent R0A evidence-contract correction.
- After one green CI run, deploy reviewed tools and execute a corrected fixed
  multi-catalogue/multi-batch non-acceptance Viper smoke. Operational and
  leakage scientific tracks remain held.
- The tracked Nextflow executor-scope warnings remain a separate correction;
  queue-size, submission-rate, and aggregate-concurrency enforcement are not
  claimed.

### Next exact starting point

Run `pixi run --locked check`. If it passes, inspect `git status`, the complete
diff, `git diff --check`, and stage only the coherent R0A code, tests,
roadmap/review dispositions, and this journal evidence.

## 2026-08-17T19:59:34Z - R0A correction passes the complete locked gate

### Accomplishments and immutable local evidence

- The one complete `pixi run --locked check` passed after its focused
  formatting and type corrections: Ruff format/lint, `ty`, 468 unit tests, 59
  contract tests, 51 integration tests, schemas, public-panel validation,
  documentation links, actionlint, Nextflow syntax, the expanded two-catalogue/
  four-batch Nextflow stub with cached resume, and reviewed-wrapper syntax.
- The final R0A focused set contains 57 passing family, identity, edge,
  collect/evaluate, and deterministic batch-partition tests. A separate real
  frozen-snapshot probe verified both full snapshot checksums, all 12 target
  families, and the intentional non-nested T10 partition.
- Complete scope/privacy review found no tracked private family-membership
  fixture. Actual target lines remain outside Git; only synthetic private truth
  is used by unit collection tests. No external database, unknown crystal,
  historical M5 result, or retained remote run was altered.

### Unresolved work

- Inspect and stage the complete coherent R0A diff, create one commit, push
  once, and require one CI run.
- Deploy reviewed tools after green CI and run one corrected fixed
  multi-catalogue/multi-batch non-acceptance Viper smoke. Scientific M6 tracks
  remain held pending the remaining roadmap foundations and acceptance gates.

### Next exact starting point

Run final staged-diff checks, commit the R0A evidence-contract correction, push
once, and watch exactly one CI run.

## 2026-08-17T20:10:10Z - R0A correction deployed and smoke submitted

### Accomplishments and immutable evidence

- Created and pushed coherent commit
  `7de1b5c8d25c0972956e55bfdc2eb57e8ffa3ada`. The sole GitHub Actions run
  `32063494568`, job `95489937445`, passed under Pixi 0.76.2 in 6m33s.
- Built and installed the matching local controller with SHA-256
  `f8b35bc89937ccde49e5f3d42bef536865e69fe782355af6b8d1b4a2479b5a4a`;
  the previous controller was checksum-preserved in ignored local evidence.
- Deployed the exact revision. Dispatcher, job-wrapper, and recovery SHA-256
  values remain
  `5aa8979ec1218c8187c4ed5f5fd0e67ac130beb8956354d82d314580446a8076`,
  `be2abafdd0a988614fdaf3f0d75d32abc7cdb140bea5b16f4a947c9802f2ee3b`,
  and `0db4c5f3542ce4d387ac019e33717d5e405ac957efb216b05c52828a851808f4`.
- Staged and submitted exactly one corrected non-acceptance smoke as
  `gtd-m6-nextflow-smoke-20260817T200853Z-7de1b5c8d25c-0cd67106`, Slurm job
  `10941052`, from source `7de1b5c8d25c0972956e55bfdc2eb57e8ffa3ada`
  and nf-helper `82431e4c56cb4cd2ef4ea67321fd01fad7ba65cb`. Initial state is `PENDING`,
  terminal false.
- Rebound the existing 30-minute heartbeat in place to this run and this
  thread. No duplicate monitor, CI watch, or Viper job was created.

### Unresolved work

- Monitor only job `10941052`. At terminal state, retrieve bounded logs and
  collect, then verify the corrected two-catalogue/four-batch partition,
  identity/edge evidence, complete child inventory, resource bounds, canonical
  resume, truthless store reuse, checksums, and executor-scope warnings.
- This smoke cannot authorise operational or leakage M6 science. On success,
  continue with the R1--R3 shared contract/cache/crystallographic foundations;
  on demonstrated software failure, apply only one focused regression and
  minimal correction before an unchanged replacement smoke.

### Next exact starting point

Run `nf-gtd-hpc-test --no-progress status --run-id
gtd-m6-nextflow-smoke-20260817T200853Z-7de1b5c8d25c-0cd67106` at the next
30-minute heartbeat.

## 2026-08-18T11:08:19Z - Multi-item smoke exposes stale wrapper cardinality

### Classification and immutable evidence

- Corrected R0A smoke
  `gtd-m6-nextflow-smoke-20260817T200853Z-7de1b5c8d25c-0cd67106`, Slurm job
  `10941052`, finished `FAILED` with exit code 4 and `test_failure`. Bounded
  logs and collection completed before any source edit.
- Both operational Nextflow executions succeeded. The first trace contains
  25/25 completed children: exactly two catalogue imports, two MMseqs2 jobs,
  two Foldseek jobs, two catalogue partitions, the active M6C001 chain, and
  the typed-empty M6C057 chain. The resume trace contains 19/19 cached tasks;
  the six omitted tasks are exactly the two imports and four shared-store
  database searches.
- Search children used four distinct native IDs `10941552`--`10941555`, each
  requesting 32 CPUs, 16 GB, and 24 hours. All child IDs were native numeric
  Slurm IDs; per-job bounds passed. Observed peaks were one running job,
  32 aggregate CPUs, 16 GB, and one Phenix job.
- The deterministic failure is in the qualification wrapper, not the
  scientific workflow or infrastructure. It still required three stored
  tasks and two search jobs after R0A expanded the fixed profile to six stored
  tasks and four search jobs, so it returned 4 before the leakage phase.
- First-trace, resume-trace, resource-evidence, and application-log SHA-256
  values are
  `906d958a1208301d784b4787b7b7c35458034acdd60bf7ab30558f45580487d1`,
  `bc66d27622501846447f86e3c935053a8cf7f5d3f08477adb0e979bf98edbfa4`,
  `127b5574ff96fb571c9a03c2c5ccc04cafa7bc1278f987c53b840db6fd4ae847`,
  and `61860f2ab08a5e2aa9e9ed5b401c06f2c7a7bf33ea2b2c49a15c2227cd5366a`.
  Cross-track reuse, byte-identical scientific outputs, v2 identity/edge
  payloads, and final checksums remain unverified because leakage never began.

### Correction and local evidence

- Added a focused controller regression that reproduced the stale three/two
  assumptions, then changed only the job-body qualification logic. Stored-task
  cardinality is derived from the exact two-import/two-MMseqs2/two-Foldseek
  first trace, and resource validation now requires two jobs of each search
  kind, four distinct native IDs, completed children, and 32-CPU/16-GB/24-hour
  requests.
- The focused regression now passes. Bash syntax, the reviewed-wrapper check,
  Ruff, and `git diff --check` pass. No M6 adapter, scientific criterion,
  schema, model, cache key, or retained remote run changed.
- The complete affected dispatcher suite passes 46 tests. One complete
  `pixi run --locked check` passes Ruff format/lint, `ty`, 468 unit tests,
  59 contract tests, 51 integration tests, schemas, public-panel validation,
  documentation links, actionlint, Nextflow syntax and expanded cached-resume
  stub, and all reviewed-wrapper syntax checks.

### Next exact starting point

Stage and commit only the wrapper regression, minimal correction, and material
journal evidence. Push once, watch exactly one CI run, deploy checksummed tools,
and submit exactly one unchanged replacement smoke.

## 2026-08-18T11:40:28Z - Wrapper correction deployed and replacement running

### Accomplishments and immutable evidence

- Created and pushed commit
  `feec15bdc61d606e012ae33773bb4d31fc5bb1df`. The sole GitHub Actions run
  `32131924755`, job `95694745658`, completed successfully in 6m49s under
  Pixi 0.76.2.
- The deterministic controller build remained byte-identical to the installed
  reviewed application at SHA-256
  `f8b35bc89937ccde49e5f3d42bef536865e69fe782355af6b8d1b4a2479b5a4a`.
  Deployed dispatcher, corrected job-wrapper, and recovery SHA-256 values are
  `5aa8979ec1218c8187c4ed5f5fd0e67ac130beb8956354d82d314580446a8076`,
  `f3b25ee7b86a3676ec51a73ac1470685413e357d9ca4f16595f6c08eb4a470bd`,
  and `0db4c5f3542ce4d387ac019e33717d5e405ac957efb216b05c52828a851808f4`.
- Staged and submitted exactly one unchanged replacement profile as
  `gtd-m6-nextflow-smoke-20260818T113726Z-feec15bdc61d-8faed7e6`, Slurm job
  `10945968`, from the pushed source and nf-helper
  `82431e4c56cb4cd2ef4ea67321fd01fad7ba65cb`. Its first status is `RUNNING`,
  terminal=false.
- Rebound the existing 30-minute heartbeat in place to the replacement run and
  retained this thread as its destination. No duplicate automation, CI watch,
  or Viper job was created.

### Unresolved work

- Monitor only job `10945968`. At terminal state, retrieve bounded logs and
  collect before classification. Require the exact two-catalogue/four-batch/
  two-partition topology, six stored plus 19 cached tasks accounting for the
  25-task first pass, v2 identity/edge payloads, four distinct bounded search
  jobs, byte-identical resume, truthless-only cross-track reuse, and complete
  final checksums.
- This remains non-acceptance orchestration evidence. Even on success, do not
  stage operational or leakage M6 science; continue with the R1--R3 shared
  release-stop foundations first.

### Next exact starting point

Run `nf-gtd-hpc-test --no-progress status --run-id
gtd-m6-nextflow-smoke-20260818T113726Z-feec15bdc61d-8faed7e6` at the next
30-minute heartbeat.

## 2026-08-18T13:52:22Z - Replacement passes, collection exposes evidence gap

### Immutable orchestration evidence

- Wrapper-corrected replacement
  `gtd-m6-nextflow-smoke-20260818T113726Z-feec15bdc61d-8faed7e6`, Slurm job
  `10945968`, completed successfully from source
  `feec15bdc61d606e012ae33773bb4d31fc5bb1df`, nf-helper
  `82431e4c56cb4cd2ef4ea67321fd01fad7ba65cb`, Pixi 0.76.2, and the expected
  lock and execution-policy digests. Bounded logs and collection completed
  before further source edits.
- The operational first trace has 25/25 completed tasks: exactly two catalogue
  imports, two MMseqs2 batches, two Foldseek batches, two partitions, the full
  active M6C001 branch, and the typed-empty M6C057 branch. The resume trace has
  19/19 cached tasks plus exactly six stored discovery tasks, accounting for
  all 25. The leakage trace has 19/19 newly completed track-specific tasks.
- Search native IDs are `10945987`, `10945988`, `10945989`, and `10945991`;
  each completed with requests of 32 CPUs, 16 GB, and 24 hours. All 25 child
  IDs are distinct native numeric Slurm IDs. Per-job bounds passed; observed
  maxima were one running child, 32 aggregate CPUs, 16 GB, one concurrent
  Phenix job, and 0.002 GB peak RSS.
- Cross-track reuse contains exactly two imports, two PDB searches, and two
  Foldseek searches, with no policy, MR, copy, or refinement reuse. The
  collected summary/resume/resource/store SHA-256 values are
  `e1baaf75dd6c7caa10cf143b91d563da7fdadf5fd605db92d155b129dab876d7`,
  `0e291e76468185712957e6595d8c07ad8f08ea7642dee09efb46b3a9140d53e2`,
  `d0090f79eca773938b1c8628a1a883c5aa34823b02cbd87593221be3b5dec044`,
  and `cc6df3393c5d95eacf62067ec75ca4e470fbafd75c103ff57243a73a4ad0351d`;
  all match the remote manifest. The checksum-manifest digest is
  `63ea5d9afb369a5c6e8f01cd3e34ec53728b38cceb2b7b5f45fd0c7a109d8522`.
- The unrecognised `$slurm`/`$local` executor-option warnings remain visible.
  Per-job requests are proven; aggregate queue/rate enforcement remains
  unclaimed.

### Evidence-gap classification

- This run passes the fixed multi-item orchestration smoke, but R0A is not yet
  closed. The collector retrieved only qualification reports, not the retained
  synthetic scientific tree. Consequently the local bundle cannot directly
  inspect the v2 case identity/edge payloads.
- The wrapper compared ten output digests before and after resume, then deleted
  both digest lists. Its success proves that the execution-time comparison
  passed, but an independent local reviewer cannot recompute the claimed byte
  identity. The final checksum manifest covers only four qualification files.
- Treat this as a software evidence-contract defect, not a scientific or
  infrastructure failure. Do not stage R1 or an M6 scientific track until a
  small collected v2 contract report and retained before/after digest lists
  close the gap. Deeper raw-input/cache-key truthlessness remains assigned to
  R2 and must not be falsely claimed from process names alone.

### Next exact starting point

Add one focused wrapper/collector regression requiring a collected redacted v2
identity/edge contract report and both output-digest manifests. Preserve those
files, include them in the fixed collection allowlist and qualification
checksums, run the focused checks plus one complete locked gate, then repeat
the immutable commit/CI/deploy/single-smoke loop.

### Evidence correction and local verification

- Added a bootstrap-only v2 contract validator/report. It verifies the
  aggregate and execution records are `m6-nextflow-run-v2`, both fixed case
  records are `m6-nextflow-case-evidence-v2`, and each carries a case-bound
  `m6-identity-decision-v1` object plus typed edge-observation list. The report
  retains those redacted payloads and source-file digests.
- Preserved both ten-file before/after scientific-output digest manifests and
  added them, the contract report, and the exact operational synthetic outputs
  to the bounded remote collection allowlist. An unlisted sibling remains
  uncollectable. The portable final checksum manifest now covers the contract
  report and both digest lists with relative paths.
- Two focused wrapper/collector regressions pass, including direct execution
  of the embedded validator against the tracked v2 fixture. All 47 dispatcher
  integration tests pass. One complete `pixi run --locked check` passes Ruff
  format/lint, `ty`, 468 unit tests, 59 contract tests, 52 integration tests,
  schemas, public-panel validation, documentation links, actionlint, Nextflow
  syntax and cached-resume stub, and all Bash wrapper checks.
- No scientific adapter, schema, model, threshold, cache key, frozen protocol,
  retained run, or unknown crystal changed. The controller zipapp remains
  generic; only the dispatcher and fixed job body require new deployment
  checksums.

### Revised next exact starting point

Stage and commit only the two bootstrap scripts, focused integration coverage,
and material journal evidence. Push once, watch exactly one CI run, deploy the
checksummed scripts, and submit exactly one final unchanged replacement smoke.

## 2026-08-18T14:34:52Z - Evidence-complete replacement smoke running

### Accomplishments and immutable evidence

- Created and pushed commit
  `c6e384d8b5883c0e2245115c274dc60fe83b60ef`. The sole GitHub Actions run
  `32148254240`, job `95747299990`, completed successfully in 6m33s under
  Pixi 0.76.2.
- The deterministic controller remains byte-identical at SHA-256
  `f8b35bc89937ccde49e5f3d42bef536865e69fe782355af6b8d1b4a2479b5a4a`.
  Deployed dispatcher, job-wrapper, and recovery SHA-256 values are
  `d903afa955b3758f2e3874986cf0d1c1831e306d3062e98f698e11ed2af1bb60`,
  `c33bc2f30172d8ff32db9ed78f1a446b745dc6753544850bef937df53d472ef4`,
  and `0db4c5f3542ce4d387ac019e33717d5e405ac957efb216b05c52828a851808f4`.
- Staged and submitted exactly one evidence-complete replacement as
  `gtd-m6-nextflow-smoke-20260818T143325Z-c6e384d8b588-de9c14b8`, Slurm job
  `10947942`, from the pushed source and nf-helper
  `82431e4c56cb4cd2ef4ea67321fd01fad7ba65cb`. Its first status is `RUNNING`,
  terminal=false.
- Rebound the existing 30-minute heartbeat in place to this run and retained
  this thread as its destination. No duplicate automation, CI watch, or Viper
  job was created.

### Unresolved work

- Monitor only job `10947942`. On terminal state, collect bounded logs and the
  exact allow-listed evidence. In addition to topology/resources/reuse, require
  the collected v2 identity/edge contract report, identical before/after
  ten-file digests, operational synthetic outputs matching those digests, and
  a portable relative-path checksum manifest.
- Treat process-level shared-store membership as orchestration evidence only;
  raw-input and cache-key truthlessness remains an R2 release stop. Preserve
  the executor-option warnings without claiming queue/rate enforcement.
- If every fixed smoke gate passes, close R0A and begin the smallest R1 strict
  contract slice. Do not stage operational or leakage M6 science first.

### Next exact starting point

Run `nf-gtd-hpc-test --no-progress status --run-id
gtd-m6-nextflow-smoke-20260818T143325Z-c6e384d8b588-de9c14b8` at the next
30-minute heartbeat.

## 2026-08-18T15:23:33Z - Parallel foundation slices merge cleanly in isolation

### Accomplishments and local evidence

- Created three isolated local worktree branches from pushed source
  `c6e384d8b5883c0e2245115c274dc60fe83b60ef`; none touched main, the active
  smoke, remote state, or GitHub.
- R1 commit `f2f364b` rejects duplicate top-level and nested JSON/YAML mapping
  keys before schema validation and reports source plus array-aware pointer.
  Six red/green regressions pass; the complete typed-contract file passes 52.
- R2 commit `720b5f3` records and verifies every required Phenix command digest,
  refuses unrecorded or same-path replaced executables before both spawn
  boundaries, and exposes a verified runtime identity for later cache-key
  integration. Its focused set passes 32 tests; downstream cache consumers
  remain an explicit R2 task.
- R3 commit `edf1096` carries MTZ dataset identity through observation
  candidates and selections, compares arrays within the correct dataset, and
  rejects label-only overrides that are ambiguous across datasets. Its
  focused diffraction suite passes 90 tests; the additive record migration is
  backward-readable.
- The three commits cherry-pick without conflict into the local
  `foundation-integration` branch. Combined focused tests pass 109. One full
  `pixi run --locked check` passes Ruff format/lint, `ty`, 472 unit tests,
  66 contract tests, 52 integration tests, schemas, public-panel validation,
  documentation links, actionlint, Nextflow syntax and cached-resume stub, and
  all Bash wrapper checks against pinned nf-helper
  `82431e4c56cb4cd2ef4ea67321fd01fad7ba65cb`.

### Unresolved work and exact next starting point

- These branches are local review points only; do not push or integrate them
  into main while the evidence-complete R0A smoke is non-terminal.
- At the next heartbeat, monitor only Slurm job `10947942`. If its collected
  gates pass, close R0A, inspect the three foundation commits again, and
  integrate them in R1/R2/R3 dependency order. Preserve the R2 runtime-identity
  cache-consumer gap and the R3 downstream dataset-identity propagation as
  named follow-up work rather than overstating those gates as complete.

## 2026-08-18T15:36:31Z - R0A evidence-complete smoke passes

### Immutable evidence and classification

- Evidence-complete smoke
  `gtd-m6-nextflow-smoke-20260818T143325Z-c6e384d8b588-de9c14b8`, Slurm job
  `10947942`, completed successfully from source
  `c6e384d8b5883c0e2245115c274dc60fe83b60ef`, nf-helper
  `82431e4c56cb4cd2ef4ea67321fd01fad7ba65cb`, Pixi 0.76.2, lock SHA-256
  `a31c520126e559154433546f45b92d2617bc622f89ffd6b0422c0579c0dda66b`,
  and execution-policy SHA-256
  `533f28c049cff718242718b6af6584684dd675a612f30adfcce928c86669d527`.
- First, resume, and leakage traces contain respectively 25/25 completed,
  19/19 cached, and 19/19 completed tasks. Six stored tasks are exactly two
  catalogue imports, two PDB batches, and two Foldseek batches; both catalogue
  partitions and the active M6C001 plus typed-empty M6C057 branches complete.
- Search native IDs `10947998`--`10948001` are distinct and completed with
  32 CPUs, 16 GB, and 24-hour requests. Per-job bounds pass. Peak observed
  concurrency is two children, 33 aggregate CPUs, 20 GB, and one Phenix job,
  within the reviewed Viper project ceiling.
- The collected v2 report directly verifies `m6-nextflow-run-v2`, two
  `m6-nextflow-case-evidence-v2` rows, case-bound identity decisions, and edge
  lists. Both ten-file resume manifests have identical SHA-256
  `f420ad722126e2ae9af97437428ac167a74493355609c9ca617923e479666bff`;
  every allow-listed operational output verifies against both manifests.
- Summary, resume, resource, contract, store, and final-manifest SHA-256 values
  are
  `ea53439398f1b18919242b4afac1aaad935ea7cb21fe42c2e713c579a9b64f41`,
  `0e291e76468185712957e6595d8c07ad8f08ea7642dee09efb46b3a9140d53e2`,
  `967b29bcc86c9f71b456eb475fc4adb0dc81fef35a03e3f4883dc8c67e08e35a`,
  `4590714909d059e0247a9c8ffb088010f906d4b837e4bca18ef0aab99e6bfe1c`,
  `413363d6fa4669f0d2f1db6939b999063c68363814c3135feb25061096908a27`,
  and `823c19aa187188fff083f5c563618a7846f22e4a679c553373503d18d04e40b4`.
- R0A is complete as non-acceptance orchestration/evidence qualification. It
  does not clear R1--R4, M6 scientific Gate 1, or v0.1 release. Process-level
  reuse membership is proven; raw-input/cache-key truthlessness remains R2.
  Executor-scope warnings remain visible and aggregate queue/rate enforcement
  remains unclaimed.

### Marmic migration decision and exact next starting point

- The user requested migration to less-crowded Marmic after the Viper job had
  already completed, so no cancellation or duplicate rerun was performed.
- The current controller and dispatcher intentionally refuse
  `m6-nextflow-smoke` outside Viper, the job hard-codes `-profile viper-cpu`,
  and its Apptainer path is Viper-specific. Marmic execution therefore requires
  a separately reviewed site-parameterisation/configuration slice before any
  submission; merely changing the SSH target would be unsafe.
- Keep the completed Viper evidence immutable. Review and integrate the local
  R1/R2/R3 foundation commits in dependency order while developing a fixed
  Marmic smoke profile in an isolated worktree. Run no Marmic job until its
  controller guard, dispatcher site validation, Nextflow profile, Apptainer
  cache, resource mapping, collection, fake-Marmic lifecycle tests, and script
  deployment checks pass one complete locked gate and CI.

## 2026-08-18T16:44:59Z - Foundation slices integrated; Marmic profile locally green

### Accomplishments and immutable local evidence

- Integrated the reviewed foundation commits into main in dependency order:
  `667fab2` rejects duplicate JSON/YAML mapping keys, `77bde73` binds verified
  Phenix command digests, and `b193869` qualifies MTZ observation selection by
  dataset. The previously tracked follow-up limits remain explicit; these do
  not complete all of R1, R2, or R3.
- Added a fixed two-site M6 smoke contract. Immutable stage state now binds
  `site_id` to either `marmic` or `viper-cpu`, the corresponding Nextflow
  profile, a site-specific execution-policy ID and checksum, and a run-owned
  Apptainer cache. Unsupported sites, endpoint/config mismatches, altered
  policy state, and unsafe cache paths fail closed before submission.
- Added Marmic execution policy `m6_nextflow_slurm_marmic_v1` with truthful
  queue size 30 and submission rate `10/1s`. Both sites retain the fixed
  32-CPU/16-GB/24-hour search bounds. The Viper managed-controller environment
  is set only on Viper; both sites pass the cache directory explicitly.
- Focused Marmic/Viper site tests pass nine cases; the broader controller, M6,
  contract, and fake-dispatcher selection passes 147. The focused M6 stub
  retains 25/25 first-pass tasks and a resume of 19 cached plus six stored
  discovery tasks.
- One complete integrated-main `pixi run --locked check` passes Ruff
  format/lint, `ty`, 475 unit tests, 67 contract tests, 55 integration tests,
  schemas, public-panel validation, documentation links, actionlint, Nextflow
  syntax and the complete cached-resume stub, and all Bash wrapper checks.
  The complete stub performs 33 subprocess launches, explaining its long but
  successful runtime.

### Remaining migration boundary and exact next starting point

- No Marmic remote operation has occurred. Inspect the full staged diff and
  privacy scope, commit the migration with this journal, push once, and watch
  exactly one CI run.
- After green CI, create a separate mode-0600 Marmic controller configuration
  and local state root from the retained approved settings; do not overwrite
  the Viper configuration. Deploy the exact checksummed dispatcher/job script
  through the Marmic wrapper and run reviewed readiness before staging.
- The completed Viper smoke must not be duplicated merely as another
  scientific claim. A Marmic M6 smoke is justified only as the requested new
  site-profile validation; it remains non-acceptance orchestration evidence.
  Real Phenix and production databases are not needed for that stub, but are
  still required before Marmic scientific M6 tracks.

## 2026-08-18T17:08:47Z - Linux submit-response regression corrected

### Observed CI failure and root cause

- The sole Actions run `32162113507`, job `95793175682`, for pushed head
  `107f013131dcee178fc881cda8706e586efcdc92` failed during integration after
  475 unit and 67 contract tests passed. Three fake staged-run tests failed on
  Ubuntu because their legacy/manual state intentionally omits `state/site-id`.
- The new common submit response read that optional file unconditionally.
  Linux Bash exited on the failed redirection; macOS Bash emitted an empty
  `site_id`, explaining why the complete local gate had passed. Scheduling had
  already succeeded and the failure was confined to response rendering.

### Focused correction and evidence

- Added a regression requiring a non-M6 manual staged run to report the
  dispatcher's validated immutable `SITE_ID`. The red regression reproduced an
  empty value locally.
- Changed only the common response to emit the already validated dispatcher
  `SITE_ID`; M6 site-policy state validation and all submission behavior remain
  unchanged. The three CI failures now pass locally.
- One complete `pixi run --locked check` passes Ruff format/lint, `ty`,
  475 unit tests, 67 contract tests, 55 integration tests, schemas,
  public-panel validation, documentation links, actionlint, Nextflow syntax
  and complete cached-resume stub, and all Bash wrapper checks.

### Next exact starting point

Commit only the dispatcher response, regression, and this evidence. Push once,
watch exactly one CI run, and require green CI before creating the separate
Marmic controller configuration or deploying any remote script.

## 2026-08-18T17:43:44Z - Fresh Marmic root bootstrap locally qualified

### Discoveries and external evidence

- Replacement Actions run `32164148221`, job `95799680466`, passed pushed
  commit `c227e7d7d70697a9e63d278b5b300aec3e488bf2` in 5m06s under Pixi 0.76.2.
- Created an ignored mode-0600 Marmic controller configuration from the
  retained approved SSH alias and dispatcher path without overwriting the
  Viper configuration. The controller schema requires both site configs to
  share the site-bound local capability store; each run record prevents
  cross-site operation.
- The reviewed Marmic `deploy-tools` operation reached the host but the fixed
  dispatcher path was absent. The user then confirmed all previous Marmic test
  working directories had been deleted and authorised rebuilding them. No raw
  SSH, fallback transfer, remote cancellation, or job submission occurred.

### Fresh-bootstrap correction and local evidence

- Extended only the checksum-gated recovery path to recognise the exact
  configured missing-dispatcher error. It may create the exact run root only
  beneath an existing owned non-symlink parent, then create the fixed tooling
  directory and install only the two size- and SHA-256-bound payloads.
- Existing upgrades still preserve and roll back both tools. Fresh bootstrap
  removes a partial install on failure and refuses foreign/symlinked roots or
  a one-file partial tool state. Deployment records distinguish tool and root
  bootstrap.
- An absent bare mirror now triggers the existing checksum-bound source-archive
  staging route; arbitrary Git, transfer, or caller path authority was not
  added. Four focused red/green bootstrap/archive tests pass.
- One complete `pixi run --locked check` passes Ruff format/lint, `ty`,
  475 unit tests, 67 contract tests, 56 integration tests, schemas,
  public-panel validation, documentation links, actionlint, Nextflow syntax
  and complete cached-resume stub, and all Bash wrapper checks.
- Per user direction, the roadmap now requires focused checks while iterating
  and one full gate per coherent integration/push/deployment batch, rather than
  repeating the full 33-launch stub after every small edit. The documentation
  check passes after this policy update.

### Next exact starting point

Commit the fresh-bootstrap code, regressions, loop-policy update, and this
evidence. Push once and watch one CI run. Only after green CI, rebuild/install
the controller, retry the checksum-gated Marmic deployment, then stage from a
source archive if the deleted mirror remains absent. Run readiness before one
Marmic site-validation smoke; do not stage scientific M6 tracks.

## 2026-08-18T17:54:57Z - Deleted Marmic parent chain handled explicitly

### External evidence and focused correction

- Actions run `32167317780`, job `95809831126`, passed pushed fresh-bootstrap
  commit `a4c9237318d65809d9282237ebd3ec40d97d3e69` in 6m15s. The rebuilt local
  controller checksum is
  `5a7c28e54c2a8001ba53b76b235073538e44d27ff119f8830ffa8d03e120bfea`.
- Checksum-gated recovery reached Marmic and correctly refused because the
  user-deleted scope also included the recorded run-root parent
  `codex-hpc-runs`. No files were installed and no job was staged.
- The fresh-bootstrap path now walks only the fixed configured path toward its
  nearest existing ancestor, requires that ancestor to be owned, a real
  directory, and not `/` or a symlink, then recreates the missing chain with
  mode-protected directories and verifies the final physical path exactly.
  Existing roots retain the stricter direct ownership check.
- The missing-chain bootstrap and missing-dispatcher controller regressions
  pass two focused tests; Bash syntax and targeted Ruff pass. Per the updated
  loop policy, the complete gate is not repeated for this two-line-scope safety
  refinement; CI remains the full-platform gate before deployment.

### Next exact starting point

Commit and push this focused recovery refinement, watch one CI run, rebuild the
controller only after green CI, and retry the same checksum-gated Marmic
deployment. If the nearest existing ancestor is not owned, stop and request the
administrator/user-created root rather than weakening the guard.

## 2026-08-18T18:06:48Z - Marmic Pixi path restored from retained evidence

### External evidence and focused correction

- Actions run `32168246397`, job `95812919596`, passed pushed directory-chain
  commit `bd62c6607ab02e4ff8fff5f867dbfb77dc980a9c` in 6m23s.
- Checksum-gated recovery then rebuilt the deleted Marmic directory chain and
  installed the fixed tools. Immutable source-archive staging correctly
  stopped before creating a runnable job because the deleted root also removed
  `_tooling/pixi.path`, and non-login SSH could not discover Pixi from `PATH`.
- Locally retained Marmic run manifests consistently identify the qualified
  executable as `/home/ashima/.local/bin/pixi`; the executable lies outside the
  deleted test root. Fresh recovery now checks the fixed
  `/home/${USER}/.local/bin/pixi` candidate, then a safe absolute `PATH`
  fallback, requires an executable Pixi 0.74.0 or 0.76.2, writes a mode-0600
  path record, and binds the path plus bootstrap status into deployment
  evidence. Existing path records must be owned regular non-symlink files.
- The focused missing-root/Pixi recovery regression and Bash syntax pass. Per
  the approved cadence, no redundant complete local gate was run; CI is the
  full-platform boundary before remote retry.

### Next exact starting point

Commit and push the focused Pixi-path recovery, watch one CI run, then retry
the checksum-gated deployment so the path record is created. Stage the exact
pushed SHA through source-archive fallback; submit only if stage reports
`site_id=marmic`, the Marmic policy ID/checksum, and a run-owned cache.

## 2026-08-18T18:16:13Z - Runtime standardised on Pixi 0.76.2

### Evidence and focused correction

- Actions run `32169323897`, job `95816382360`, passed pushed Pixi-path
  recovery commit `043d8c73eef0904633958c7509c98c57ac0621ec` in 6m47s under
  Pixi 0.76.2.
- The remaining Pixi 0.74.0 allowance was legacy Marmic-prototype
  compatibility. The project manifest, local runtime, Marmic runtime, Viper
  runtime, and single CI job are now all standardised on Pixi 0.76.2.
- Recovery, readiness, database readiness, and staging now require exactly
  Pixi 0.76.2. The fake remote runtime defaults to 0.76.2, and explicit
  regressions prove that 0.74.0 is reported as a version mismatch and cannot
  recover tools or create a staged run.
- Seven focused dispatcher/recovery tests pass, including both-site M6 policy
  staging. Bash syntax, targeted Ruff, and `git diff --check` pass. Per the
  agreed loop cadence, the complete local suite was not repeated for this
  narrow compatibility correction.

### Next exact starting point

Commit and push this exact-version correction once and use its single CI job
as the batch gate. After green CI, rebuild and checksum the controller, deploy
the reviewed tools to the rebuilt Marmic root, then stage the exact pushed SHA
through source-archive fallback. Submit no job unless the staged record binds
the Marmic site, fixed Marmic policy, and run-owned Apptainer cache.

## 2026-08-18T18:23:47Z - Absent Marmic mirror recovery completed

### Observed failure and focused correction

- Actions run `32170166049`, job `95819123019`, passed exact-Pixi commit
  `95252d30576dd26fb13306de9e8c3fab7b24db30` in 4m53s under Pixi
  0.76.2. The rebuilt and installed controller checksums are both
  `5a7c28e54c2a8001ba53b76b235073538e44d27ff119f8830ffa8d03e120bfea`.
- Reviewed Marmic deployment stopped with typed `filesystem_failure` and exact
  message `bare Git mirror is absent`. No job or scientific run was created.
  The controller already recovered an invalid bare mirror but omitted this
  equivalent absent-mirror state from the deploy-only allow-list; archive
  staging already handled both states.
- Added only the exact absent-mirror state to checksum-gated tool recovery and
  extended the existing allow-list regression. The focused unit test, targeted
  Ruff and `ty`, and `git diff --check` pass. No full local suite was repeated.

### Next exact starting point

Commit and push this one-branch controller correction and watch its single CI
job. After green CI, rebuild and verify the controller checksum, retry the same
reviewed Marmic deployment, and then stage the exact pushed SHA through the
source-archive boundary. Do not submit unless all fixed Marmic state is bound.

## 2026-08-18T18:37:00Z - Marmic site-validation smoke submitted

### Immutable evidence

- Actions run `32170847319`, job `95821360004`, passed controller recovery
  commit `2592061740e03892b90bba1a9bf13236bb68004e` in 6m43s under
  Pixi 0.76.2. The installed controller checksum is
  `a729afe769ac21ebe8c4045df0fd963105f948a05a5a632171fb25b12d560e9b`.
- Direct version inspection showed the Marmic user-local Pixi remained 0.74.0.
  The user supplied the Mamba environment root; its fixed executable reports
  Pixi 0.76.2 and was atomically recorded in the rebuilt tool directory.
- Checksum-gated recovery deployed dispatcher
  `e1ff791bfd5067465bb9ae59bce2b51258630d912d28378dfd9ce11bf15ee628`,
  job wrapper
  `4f1c6a8da0ee3a77f4fbe775e3dd034da3601cf832f5c44679b09fe1b113f2f2`,
  and recovery
  `5334a95d54a5c990c975b1db6814e77435652618181c11070584e379a35a4ab6`.
- Source-archive staging completed for
  `gtd-m6-nextflow-smoke-20260818T183126Z-2592061740e0-cffe35fb`, binding
  site `marmic`, the fixed Marmic execution policy, and the run-owned
  Apptainer cache. Slurm job `629472` was submitted and its first status was
  `RUNNING`, terminal false. This remains site/orchestration evidence only.

### Next exact starting point

Monitor only this exact run through the reviewed wrapper. At terminal, collect
bounded logs and artifacts, verify the complete R0A evidence contract and
Marmic resource/provenance bindings, and classify before any source edit. Do
not create a duplicate run or treat this site-validation smoke as M6 science.

## 2026-08-18T19:12:43Z - Wrapper-only Nextflow failure diagnostics restored

### Failure evidence and correction

- Marmic run `gtd-m6-nextflow-smoke-20260818T183126Z-2592061740e0-cffe35fb`,
  Slurm `629472`, terminated `FAILED` with signature
  `0d7564d00d12009af1c5c1b6e96dcc007f02f9916ef84c20e07f2bd7259dfded`.
  Bounded logs and collection showed the first synthetic catalogue-import
  output was not registered; no scientific M6 work ran.
- The existing wrapper returned the application log but omitted the failed
  Nextflow task's retained `.command.log`, so exact permission evidence was not
  available through the approved interface. The dispatcher now derives the
  task directory only from Nextflow's `Work dir:` record, requires a canonical
  owned path below the run cache with the fixed Nextflow hash layout, and
  rejects escaped paths and symlinks.
- `logs` appends a bounded failed-command tail. `collect` includes only seven
  fixed task files and excludes unlisted siblings. Five focused compatibility,
  positive, and escape tests pass.
- One complete `pixi run --locked check` passes Ruff format/lint, `ty`, 475
  unit tests, 67 contract tests, 60 integration tests, schemas, public-panel
  validation, documentation links, actionlint, Nextflow syntax and full
  stub/resume coverage, and all Bash wrapper checks.
- The roadmap now records the Marmic hold and the v0.2 target of exactly two
  public root Nextflow entrypoints while preserving the v0.1 historical
  interface in its immutable tag.

### Next exact starting point

Commit and push the wrapper diagnostic boundary once, watch one CI run, deploy
the checksum-reviewed dispatcher, and re-run `logs` plus `collect` on this
already-terminal run to prove diagnosis without raw SSH. Then integrate the
separately focused writable-stub correction and submit exactly one replacement
Marmic smoke.

## 2026-08-18T19:39:33Z - Nextflow diagnostics fail closed and remain collectable

### Review findings and correction

- Commit `969e8372a87e601ba7463acb0c4b25f36bf0c437` passed Actions run
  `32175903779`, but it was not deployed. Independent review found that its
  first diagnostic resolver did not reject a symlinked run cache, bounded
  lines but not bytes, let an oversized optional diagnostic abort core
  collection, preferred an empty command log over useful stderr, and allowed
  mutable non-terminal diagnostics.
- The resolver now requires canonical owned run and cache directories, a
  recorded terminal failure, and the final complete Nextflow work-directory
  marker. It rejects a truncated later marker and derives a fixed relative
  cache member before collection.
- Remote and locally decoded log payloads are capped at 2 MiB. A readable,
  non-empty `.command.log` is preferred, then `.command.err`. Optional task
  files have a separate 2 MiB cap; oversized, unreadable, unsafe, or
  total-budget-exceeding files are omitted without blocking core artifacts and
  produce a deterministic omission TSV.
- Nine focused dispatcher compatibility/security tests and two focused client
  tests pass, including cache-symlink escape, active/truncated markers,
  multi-megabyte one-line logs, stderr fallback, and oversized diagnostic
  collection.
- One complete `pixi run --locked check` passes Ruff format/lint, `ty`, 476
  unit tests, 67 contract tests, 64 integration tests, schemas, public-panel
  validation, documentation links, actionlint, Nextflow syntax and full
  stub/resume coverage, and all Bash wrapper checks.

### Next exact starting point

Commit and push this review correction, watch one CI run, rebuild the local
controller, deploy the reviewed dispatcher, and prove `logs` plus `collect` on
the retained failed Marmic run without raw SSH. Only then cherry-pick the
focused writable-stub commit and stage one replacement Marmic smoke.
## 2026-08-18T19:07:25Z - Read-only M6 stub copies made portable

### Observed failure and focused correction

- The Marmic source archive correctly hardens fixture directories and files.
  Plain recursive-copy stubs preserved those modes in task outputs, leaving
  Nextflow unable to clean or stage out the copied directory tree.
- Added one test-only fixture-copy helper. It requires a new destination,
  copies hidden and nested content, and makes destination directories and files
  owner-writable. Source-archive hardening removes executable bits, so every
  stub invokes the readable helper through `/bin/bash`. Its exit trap also
  repairs a partially copied destination before Nextflow cleanup.
- Routed all 20 M6 directory-copy stub blocks, comprising 21 conditional copy
  sites, through the helper. Scientific commands, fixtures, process inputs and
  outputs, cache identities, and normal execution paths are unchanged.

### Focused evidence

- A mode-0400 helper and hardened fixture regression preserves exact file
  digests and empty/hidden directory structure, verifies owner-write and
  traversal permissions, and removes the resulting tree successfully. A forced
  partial-copy failure proves the exit trap repairs the tree without hiding the
  original failure, and a wiring regression rejects direct recursive copies;
  all three tests pass.
- One focused M6 stub run completed all 25 tasks with no failure, and every
  published result directory and file was owner-writable. Bash syntax, Ruff
  format/lint, Nextflow syntax, and `git diff --check` pass. No complete suite
  or remote operation was run.

### Next exact starting point

Integrate the focused commit, push it once, and use its single CI run as the
batch gate. After green CI, deploy the reviewed tools and submit one fresh
Marmic M6 smoke; retain and classify the failed permission run separately.

## 2026-08-18T20:11:39Z - Wrapper-only diagnosis proven and stub fix integrated

### Immutable and local evidence

- Actions run `32177984113`, job `95844195308`, passed hardened diagnostic
  commit `d0ac6dc586a9defa024e5cb97172b96ccc0d868f` in 6m0s. The installed
  controller checksum is
  `d03420d2200cdf4353e9cc0f373270867e049789244f97fbae14607a07d88d1a`,
  and checksum-gated recovery deployed dispatcher
  `2b0601371ed8f230dd0b86096c4a73c72be03a5269b96b64c84844ec135683cb`.
- The reviewed `logs` operation on retained failed Slurm job `629472` returned
  the exact `.command.log` and its scratch permission-denied lines. `collect`
  added all seven fixed Nextflow task files while preserving failure signature
  `0d7564d00d12009af1c5c1b6e96dcc007f02f9916ef84c20e07f2bd7259dfded`.
  No SSH or arbitrary path input was used for this proof.
- Integrated the isolated writable-stub slice. All 21 M6 fixture-copy sites
  invoke the mode-0400-readable helper via `/bin/bash`; the helper preserves
  content, repairs owner permissions on success or partial failure, and retains
  the original failing exit status.
- Three focused helper/wiring regressions and a direct 25-task M6 stub pass.
  One complete `pixi run --locked check` passes Ruff format/lint, `ty`, 476
  unit tests, 67 contract tests, 67 integration tests, schemas, public-panel
  validation, documentation links, actionlint, Nextflow syntax and complete
  stub/resume coverage, and all Bash wrapper checks.

### Next exact starting point

Push the integrated writable-stub commit once and watch one CI run. After green
CI, stage that exact SHA through the reviewed Marmic source-archive boundary,
verify the fixed Marmic policy and run-owned cache, submit exactly one
replacement M6 Nextflow smoke, and rebind the existing heartbeat rather than
creating another.

## 2026-08-18T20:24:35Z - Writable-stub Marmic replacement is running

### Immutable execution evidence

- Actions run `32181016092`, job `95853786465`, passed writable-stub commit
  `d579f4130d0e20bd60c961ce30a4a7285e5cf663` in 5m58s under Pixi
  0.76.2.
- Checksum-gated deployment rebound the unchanged hardened dispatcher, job
  wrapper, and recovery checksums to that exact source. Source-archive staging
  completed with nf-helper
  `82431e4c56cb4cd2ef4ea67321fd01fad7ba65cb`, site `marmic`, the fixed Marmic
  policy, and the run-owned Apptainer cache.
- Submitted exactly one replacement:
  `gtd-m6-nextflow-smoke-20260818T201947Z-d579f4130d0e-acc965e0`, Slurm
  `629490`. Its first structured state is `RUNNING`, terminal false.
- Rebound the existing `continue-prokaryotic-control-roadmap` 30-minute
  heartbeat in place. It uses wrapper-only status/logs/collect and never falls
  back to raw SSH. The failed job `629472` remains retained and excluded from
  monitoring, resume, cache reuse, and cleanup.

### Next exact starting point

While non-terminal, issue one reviewed-wrapper status per heartbeat and make no
run change. At terminal, collect bounded logs and artifacts, verify the full
Marmic R0A orchestration contract, and classify before source edits. If it
passes, continue the R1--R3 foundations; do not stage M6 science yet.

## 2026-08-18T21:30:21Z - Authoritative schemas are the public export

### R1 schema-parity correction

- Reproduced `PIPE-P2-03`: all seven contract kinds with tracked authoritative
  JSON Schemas exported independently regenerated Pydantic schemas. The public
  `pipeline-config` export accepted `reference_backend: null` while the runtime
  tracked schema rejected it.
- `contract_json_schema()` now returns the same tracked or packaged
  authoritative object used by runtime validation whenever a schema filename
  is declared. Contract kinds without a tracked schema retain the generated
  Draft 2020-12 export.
- Seven byte-structure parity cases, the known null mutation, all 23 generated
  schema-validity cases, and two CLI schema tests pass: 33 focused tests total.
  Targeted Ruff format/lint, `ty`, and `git diff --check` pass.

### Next exact starting point

Commit this isolated slice without pushing. Integrate it with the other R1
contract slices only after the active Marmic smoke is terminally classified,
then run one complete locked gate for the combined R1 boundary.
## 2026-08-18T22:32:56Z - M6 storeDir replaced by standard resume caching

### Terminal evidence and architecture correction

- The third Marmic run, Slurm `629503`, failed with signature
  `647db6e89242fcdd5e04127089fa690bf58f4dd884dd67d42de772b81275534b`.
  Its collected runner proves `NXF_SCRATCH=''`; the task/helper and generated
  copy exited zero, yet Nextflow still declared the directory moved through
  `storeDir` missing. This isolates the failure to Marmic directory-output
  `storeDir` registration rather than source modes or scratch.
- Removed `storeDir` and the `m6_discovery_store` parameter. The smoke now uses
  one standard Nextflow execution/work/cache for operational first pass,
  operational `-resume`, and leakage `-resume`.
- Moved only the catalogue/MMseqs2/Foldseek processes into a dedicated
  truthless-cache module with explicit staged content files and `cache 'deep'`.
  Track salt forces every other task to remain track-specific. Separate real
  operational/leakage runs intentionally recompute discovery rather than share
  mutable cross-run state.

### Focused evidence

- A real focused sequence completes 25 operational tasks, caches all 25 on
  operational resume, then caches exactly six truthless leakage tasks (two
  import, two PDB, two Foldseek) while completing 19 track-specific tasks.
- Focused unit/contract checks pass 41 cases, dispatcher/cache checks pass 10,
  and writable-copy checks pass 3. Nextflow syntax, Bash syntax, Ruff
  format/lint, `ty`, and `git diff --check` pass.

### Next exact starting point

Commit this isolated cache-topology correction without pushing. Integrate it
onto current main after preserving the third-run journal, run one complete
locked gate and CI, deploy reviewed tools, then submit exactly one fixed Marmic
replay. Rebind the existing heartbeat only after submission.

## 2026-08-18T20:29:31Z - Development paused after second Marmic store failure

### Terminal evidence

- Replacement run `gtd-m6-nextflow-smoke-20260818T201947Z-d579f4130d0e-acc965e0`,
  Slurm `629490`, terminated `FAILED`, `test_failure`, with signature
  `b6eb59532b30f4baf428cbfbcc9dc46c04aa31c3c992155458c15920543f03e5`.
- The writable helper executed with exit zero and the previous scratch
  permission-denied diagnostics are absent, but Nextflow still reported the
  store-backed `m6_catalogue_bundle` output missing. This disproves copied mode
  bits as the complete root cause and narrows the remaining defect to Marmic
  scratch plus `storeDir` output registration/copy-back.
- Wrapper-only `logs` and `collect` completed. Collection retained all seven
  fixed task diagnostics; no raw SSH was used. Do not resume or reuse either
  failed run/cache.

### Pause state and next exact starting point

- The existing `continue-prokaryotic-control-roadmap` heartbeat is `PAUSED`.
  Slurm job `629490` is already terminal; no job was cancelled or cleaned.
- Both parallel R1 worktrees stopped cleanly before edits or tests.
- On explicit resume, first read the collected `.command.run`, `.command.sh`,
  `.command.log`, and store evidence for job `629490` locally. Add one focused
  regression for Marmic `scratch + stageOutMode=copy + storeDir`, then choose
  the smallest configuration or process-boundary correction. Do not submit a
  third run until that regression and one integration gate pass.

## 2026-08-18T21:12:32Z - Marmic permanent-store tasks bypass scratch copy-back

### Diagnosis and focused correction

- The collected second-run task shows the fixture helper and generated scratch
  unstage command both exited zero with empty command/error logs. Nextflow
  copied the declared directory directly to the run-owned `storeDir`, then the
  driver reported that same required directory missing. The prior permission
  failure was therefore secondary rather than the remaining cause.
- A minimal Nextflow 26.04.6 directory-output reproducer succeeds on local
  APFS with `scratch + stageOutMode=copy + storeDir`; the remaining failure is
  specific to Marmic's compute-node scratch to shared-NFS permanent-store
  visibility boundary. Official Nextflow semantics define scratch copy-back
  and `storeDir` as distinct output locations; the permanent store should not
  require a second scratch publication boundary.
- Added one red/green repository-policy regression that enumerates every M6
  process using `storeDir` and requires exactly the catalogue, MMseqs2, and
  Foldseek tasks to have Marmic `withName` selectors setting `scratch=false`.
  All other Marmic tasks retain node-local scratch.
- `nextflow config -profile marmic -flat` resolves the three selectors to
  `scratch=false` while the profile default remains `/scratch/$USER`.
- One complete `pixi run --locked check` passes Ruff format/lint, `ty`, 476
  unit tests, 68 contract tests, 67 integration tests, schemas, public-panel
  validation, documentation links, actionlint, Nextflow syntax and complete
  stub/resume coverage, and all Bash wrapper checks.

### Next exact starting point

Commit and push this site-specific permanent-store boundary, watch one CI run,
deploy/rebind the reviewed tools, and stage exactly one new Marmic smoke from
the pushed SHA. Resume and rebind the existing heartbeat only after submission;
never reuse either failed run or cache.

## 2026-08-18T21:28:30Z - Contract wire types and finite metrics fail closed

### Discoveries and correction

- Draft 2020-12 treats an integral JSON number such as `1.0` as an integer, so
  authoritative schema validation alone cannot enforce the repository's exact
  integer wire type. Pydantic strict JSON mode rejects that value together with
  string integers and booleans while still decoding ISO timestamps,
  string-backed enums, and paths.
- Contract JSON mode is now always strict and all contract models reject
  non-finite floats. The central JSON reader rejects the non-standard `NaN`,
  `Infinity`, and `-Infinity` tokens; the YAML pair normaliser rejects `.nan`,
  `.inf`, and `-.inf` at their document paths.
- `load_contract` retains authoritative schema validation and then constructs
  the model through the same strict JSON-mode boundary. Programmatic Python
  construction remains compatible with explicitly typed values.

### Focused evidence and remaining boundary

- The focused contract suite passes 69 tests, including valid JSON, YAML, TSV,
  datetime, enum, path, manifest, result, and JSONL examples plus coercion and
  non-finite mutations. Ruff formatting, Ruff lint, `ty`, and
  `git diff --check` pass.
- Every typed `ContractModel.model_validate_json` entry point inherits the new
  boundary. Raw dictionary readers based on ordinary `json.loads` or
  `yaml.safe_load` remain outside it; notably the M6 protocol, execution,
  runner, evaluation, collection, and scientific helper loaders. Migrating
  those untyped documents requires a separate reviewed slice.
- Duplicate scientific IDs, TSV width/header semantics, schema export, runtime
  caps, HPC configuration, and scientific policy were not changed.

### Next exact starting point

Integrate this focused strict-wire commit, then inventory raw JSON/YAML
dictionary loaders separately before claiming repository-wide entry-point
parity.
## 2026-08-18T21:44:46Z - Unsupported downstream caps removed from v1 contract

### Contract correction and focused evidence

- Removed `max_refinement_finalists`, `max_sequence_map_finalists`, and
  `max_concurrent_mr_jobs` from the typed pipeline configuration, authoritative
  JSON Schema, example, and generated M6 configuration. These settings had no
  runtime consumer; refinement and sequence assessment retain every explicitly
  approved finalist, while executor/site configuration owns concurrency.
- Added a three-field mutation regression requiring each removed name to fail
  as an unknown `search_limits` property. No provider cap, runtime workflow,
  retain-all policy, site configuration, or frozen scientific criterion changed.
- Sixty-two focused contract, retain-all, sequence-checkpoint, and M6 tests
  pass. Schema validation, targeted Ruff format/lint, targeted `ty`, and
  `git diff --check` pass. The combined repository-policy test could not read
  the uninitialised nf-helper submodule in this isolated worktree; its tracked
  scheduler assertions and files were not changed.

### Next exact starting point

Integrate this contract-only commit with the other R1 slices, run the complete
locked batch gate once, and keep provider-plan caps plus unsupported toggles in
their separately scoped remediation. Do not infer remote or M6 acceptance from
this local contract correction.
## 2026-08-18T21:45:14Z - Declaration-only pipeline toggles removed

### Discovery and correction

- Confirmed that `matthews.reference_backend`, both `review.require_*`
  checkpoint flags, and `retention.retain_all_normalised_results` had no
  runtime branch or configurable effect. Their presence falsely implied that
  required checkpoints and normalised-result retention could be disabled.
- Removed exactly those four fields from the typed pipeline configuration,
  authoritative schema, public example, M6-generated configuration, and test
  fixture. The M6 verifier now relies on the mandatory retain-all candidate
  policy plus retained logs rather than an inert normalised-result flag.
- The MR-seed and sequence checkpoints remain mandatory workflow stages, and
  normalised results remain unconditionally retained. Provider settings,
  runtime caps, scientific policy, and workflow modules were not changed.

### Focused evidence

- Four mutation tests prove the removed names fail as unknown fields. Contract
  and repository-schema tests pass 59 cases; mandatory MR/sequence checkpoint
  tests pass 18 cases; and the two focused M6 retain-all qualification tests
  pass.
- Ruff formatting, Ruff lint, `ty`, and `git diff --check` pass. No complete
  suite, remote operation, scientific execution, or threshold change occurred.

### Next exact starting point

Integrate this focused dead-toggle commit, then continue reviewing the
remaining declared caps separately without changing checkpoint or retention
semantics.

## 2026-08-18T22:08:16Z - Core R1 contract slices pass one combined gate

### Integrated contract boundary

- Integrated strict JSON wire types and finite metrics, line-aware Matthews
  input identity/coverage validation, authoritative public schema export,
  exact TSV shape/error handling, removal of three inert downstream caps, and
  removal of four declaration-only toggles.
- The cap/toggle removals preserve every mandatory checkpoint, retain-all
  result behavior, and scheduler-owned concurrency. Provider-plan caps remain
  an explicit R2 slice rather than being silently accepted here.
- The combined focused scientific/configuration suite passes 155 tests.
- One complete `pixi run --locked check` passes Ruff format/lint, `ty`, 488
  unit tests, 106 contract tests, 67 integration tests, schemas, public-panel
  validation, documentation links, actionlint, Nextflow syntax and complete
  stub/resume coverage, and all Bash wrapper checks.

### Remaining R1 parity boundary

Typed `ContractModel` JSON/JSONL and central JSON/YAML/TSV contract loading are
covered. Raw dictionary loaders in temporary M6 protocol/execution/evaluation
helpers remain outside this boundary; inventory and migrate or explicitly
delete them with the R4 temporary slice before claiming every repository entry
point passes one mutation corpus.

### Next exact starting point

Integrate these local commits onto current main after preserving the active-run
journal. Push once and watch one CI run for the combined R1 batch. Then close
the remaining raw-loader parity slice without mixing in R2 provider behavior.
## 2026-08-18T21:23:22Z - Permanent-store Marmic replay is running

### Immutable execution evidence

- Actions run `32186626570`, job `95871628833`, passed commit
  `b847873ba387508de6c692b6fd5b29f2baa4aa13` in 6m35s under Pixi 0.76.2.
- Checksum-gated deployment rebound the unchanged reviewed tools to that
  source. Source-archive staging completed with the fixed Marmic policy,
  nf-helper `82431e4c56cb4cd2ef4ea67321fd01fad7ba65cb`, and run-owned
  Apptainer cache.
- Submitted exactly one replay:
  `gtd-m6-nextflow-smoke-20260818T212114Z-b847873ba387-343ceb8d`, Slurm
  `629503`. Its first structured state is `RUNNING`, terminal false.
- The existing heartbeat is rebound and `ACTIVE`; it monitors only this run
  through status/logs/collect. Both earlier failed runs and caches remain
  retained but excluded from monitoring, resume, reuse, and cleanup.

### Next exact starting point

While non-terminal, leave the run untouched and continue independent R1
contract work in isolated worktrees. At terminal, collect and classify through
the wrapper before any run-related source change. Do not stage M6 science.

## 2026-08-18T22:10:14Z - Third Marmic run isolates the storeDir defect

### Terminal evidence

- Run `gtd-m6-nextflow-smoke-20260818T212114Z-b847873ba387-343ceb8d`,
  Slurm `629503`, terminated `FAILED`, `test_failure`, with signature
  `647db6e89242fcdd5e04127089fa690bf58f4dd884dd67d42de772b81275534b`.
  Wrapper-only logs and collection retained the seven fixed task diagnostics.
- The collected generated runner proves the Marmic `withName` selector applied:
  `NXF_SCRATCH=''`. The task and writable helper exited zero with empty logs,
  but Nextflow still copied the directory from the ordinary shared work
  directory into `storeDir` and immediately reported it missing. This rules out
  source permissions and scratch as the remaining cause and isolates Marmic
  directory-output `storeDir` registration/visibility.
- The heartbeat is paused on this already-terminal run. All three failed runs
  and caches remain retained but excluded from resume, reuse, and cleanup.

### Parallel R1 state and next exact starting point

- The six core R1 contract/configuration corrections are integrated on main
  and passed their combined complete locked gate before integration. The
  active-run journal was restored after the cherry-pick sequence.
- A separate `m6-shared-resume-cache` worktree is replacing `storeDir` with one
  standard shared Nextflow work/cache: operational resume must be 25/25 cached,
  while leakage resume may reuse exactly six truthless discovery tasks and
  must execute 19 track-specific tasks.
- Do not stage another Marmic run until that topology has focused evidence,
  one complete integration gate, one CI run, and reviewed tool deployment.

## 2026-08-18T22:55:33Z - R1 and standard M6 resume cache pass combined gate

### Integrated evidence

- Actions run `32191546405`, job `95886758470`, passed the combined R1
  contract/configuration batch at `72b3a14a39e3b1b4e5cfd89c5c5a8163b89c8f2d`
  in 5m49s.
- Integrated removal of M6 `storeDir` and its unused parameter. Explicit
  content files plus `cache 'deep'` bind the three truthless processes; track
  salt prevents every other process from reusing across operational/leakage.
  Separate real scientific tracks recompute discovery.
- The focused three-pass graph proves 25 newly completed operational tasks,
  25 cached operational-resume tasks, and exactly six truthless cached plus 19
  newly completed leakage tasks.
- The complete combined gate passes Ruff format/lint, `ty`, 488 unit tests,
  106 contract tests, 68 integration tests, schemas, public-panel validation,
  documentation links, actionlint, Nextflow syntax, and all Bash wrapper
  checks. Its first full stub sweep found one stale textual `storeDir` reuse
  assertion; removing that obsolete assertion leaves the trace-based topology
  checks authoritative, and the complete stub/resume sweep then passes.

### Next exact starting point

Commit the stale-assertion cleanup with this evidence, push once, and watch one
CI run. After green CI, deploy reviewed tools and submit exactly one Marmic
shared-resume smoke. Rebind and resume the existing heartbeat only after
submission; never reuse the three failed runs or caches.

## 2026-08-18T23:08:58Z - Standard resume-cache Marmic smoke is running

### Immutable execution evidence

- Actions run `32195014221`, job `95897118858`, passed source
  `e33082c37093f7f0fe92ab118f1e3a7d10f3e527` in 6m38s under Pixi 0.76.2.
- Installed controller checksum
  `ba5754386e2b6e9cc46ca7f0aa720cd3207dc1fe9c80357a8c42715c5b0f2f46`
  and deployed dispatcher/job-wrapper checksums
  `d7d29d77eb258f6235a1a1e2a3b65864d915b6888b1279aa6e018e2d9aead1d2` /
  `ac7ee72d9866c2b277e53203bf0d8c877b8db17f4d7ab6e7f5ff2bc606e4cddc`.
- Source-archive staging completed with site `marmic`, the fixed policy,
  nf-helper `82431e4c56cb4cd2ef4ea67321fd01fad7ba65cb`, and run-owned Apptainer
  cache. Submitted exactly one run:
  `gtd-m6-nextflow-smoke-20260818T230434Z-e33082c37093-9ffca874`, Slurm
  `629533`; first structured state `RUNNING`, terminal false.
- Rebound and resumed the existing heartbeat. It monitors only this run through
  wrapper status/logs/collect and enforces the 25 completed / 25 cached / six
  truthless cached plus 19 track-specific completed topology.

### Next exact starting point

While non-terminal, leave the run untouched and continue the isolated R1 raw
loader parity inventory. At terminal, collect and classify before any
run-related source edit. Do not stage M6 science.

## 2026-08-18T23:45:13Z - Marmic smoke exposes arrival-order cache instability

### Terminal evidence and classification

- Run `gtd-m6-nextflow-smoke-20260818T230434Z-e33082c37093-9ffca874`,
  Slurm `629533`, terminated `FAILED`, `test_failure`, at source
  `e33082c37093f7f0fe92ab118f1e3a7d10f3e527`. Wrapper-only collection
  retained the three traces, scientific contract evidence, resource evidence,
  digest manifests, and synthetic operational outputs.
- The fresh operational pass completed all 25 tasks. Its operational resume
  cached 14 tasks but reran both catalogue-partition tasks and their nine
  downstream active-case tasks. The two partition task hashes changed while
  all import and database-search hashes remained stable.
- Leakage resume behaved as designed: exactly the two catalogue imports, two
  PDB searches, and two Foldseek searches were cached; all 19 track-specific
  tasks were recomputed. The permanent-store failure is therefore closed.
- Classification is a deterministic workflow defect, not infrastructure or
  scientific failure: arrival order from the three collected catalogue/search
  channels leaked into the partition-task input hash.

### Focused correction and evidence

- Catalogue, PDB-batch, and Foldseek-batch tuples are now sorted by their
  immutable identifiers before paths are passed to downstream value channels.
  A repository-policy regression requires all three canonical sorts.
- The focused contract regression, Nextflow syntax check, and diff check pass.
  A targeted three-pass M6 stub completes 25 fresh operational tasks, caches
  all 25 on operational resume, then caches exactly six truthless discovery
  tasks and recomputes 19 leakage tasks.
- One complete locked gate passes Ruff format/lint, `ty`, 488 unit tests, 106
  contract tests, 68 integration tests, schemas, public-panel and documentation
  checks, actionlint, the full Nextflow syntax/stub-resume sweep, and all Bash
  wrapper syntax checks.

### Next exact starting point

Review and commit only the workflow, regression, and this journal evidence;
push once, watch one CI run, deploy checksum-reviewed tools, and submit exactly
one fresh Marmic replacement smoke. Never resume, clean, or reuse run `629533`
or its cache.

## 2026-08-18T23:24:55Z - Strict raw-document loader foundation added

### Focused boundary

- Added shared JSON text/path and YAML path loaders that preserve duplicate
  mapping pairs until path-aware validation and reject JSON `NaN`/`Infinity`
  plus YAML non-finite values at their exact document pointers.
- Central typed contract loading now delegates to the same raw-document
  primitives; valid booleans, integers, finite floats, arrays, and mappings are
  unchanged.
- Six raw JSON/YAML mutation routes plus valid round trips pass within the full
  98-test typed-contract file. Ruff import/format/lint, `ty`, and
  `git diff --check` pass.

### Remaining work and next exact starting point

This commit intentionally adds the reusable boundary only. Inventory and
migrate genuine M6 operator/evidence document entry points separately; leave
external-tool log parsing and canonical in-memory serialization unchanged.
Do not claim repository-wide raw-loader parity from this foundation alone.

## 2026-08-18T23:32:05Z - Bounded M6 authority loaders use strict raw documents

### Focused migration and evidence

- Migrated the frozen M6 protocol and execution-policy YAML, preparation and
  runner manifests, evaluation evidence, collection manifest/private truth,
  scientific summary/JSONL evidence, runner verification JSON, and model-policy
  JSON object loaders to the shared strict raw-document boundary. Existing
  typed model validation and `PublicControlError` domain boundaries remain.
- Added a 24-case mutation/equivalence corpus covering duplicate mapping keys
  and non-finite values for all eleven migrated loader families. The frozen
  protocol, both site policies, and frozen scientific fixtures remain
  semantically unchanged.
- Eighty focused M6 benchmark, identity, family, edge, and raw-loader tests
  pass. Targeted Ruff formatting/lint, `ty`, and `git diff --check` pass. No
  full suite, remote execution, cache, protocol criterion, or scientific
  threshold changed.

### Deliberately remaining boundary

- Leave `m6_collection.py` JSONL aggregation, all `m6_nextflow.py` raw
  task/evidence reads, and the raw JSON observations in `m6_edge.py` for a
  separately bounded migration. Typed `ContractModel.model_validate_json`
  readers already enforce strict wire input and were not rewritten.
- Non-M6 runtime JSON/YAML inventory entries and external-service/tool output
  parsers were inspected but remain outside this M6 authority slice.

### Next exact starting point

Integrate this commit after its strict-loader foundation. Then migrate the
remaining M6 edge/Nextflow/collection JSONL reads in one bounded task without
changing aggregation, scientific models, or frozen acceptance criteria.

## 2026-08-19T00:16:26Z - Remaining M6 raw readers use the strict boundary

### Bounded correction

- Migrated M6 collection JSONL aggregation, edge-observation manifests, and
  Nextflow task/evidence JSON and JSONL reads to the shared duplicate-key and
  non-finite-number rejecting loaders. No external-tool output parser or
  canonical serializer changed.
- Internal count/rank fields now require real JSON integers and reject booleans,
  strings, and values below their declared minimum rather than coercing them
  with `int(...)`.
- Extended the mutation corpus to four remaining M6 loader families:
  collection JSONL, edge JSON, Nextflow JSON, and Nextflow JSONL.

### Focused evidence and remaining boundary

- The combined focused corpus passes 187 M6, edge, raw-loader, and typed-contract
  tests. Targeted Ruff format/lint, `ty`, and `git diff --check` pass.
- This closes the identified M6 raw authority/evidence readers. Non-M6 runtime
  JSON/YAML inventory entries and external-service/tool output parsers remain a
  separately reviewed R1 inventory; do not claim repository-wide entry-point
  parity yet.

### Next exact starting point

Review and commit this final M6 reader slice without pushing or running a full
suite. Integrate the three ordered raw-loader commits onto current main while
preserving the active-run journal, then run focused integration checks before
the next coherent full gate.

## 2026-08-18T23:32:44Z - Immutable provider-plan contract established

### Contract and resolver boundary

- Added strict content-addressed provider-entry and aggregate provider-plan
  contracts, an authoritative tracked schema, canonical default example, and a
  deterministic CLI resolver from the pipeline configuration plus database
  manifest. Enabled routes bind ready database resource identities; disabled
  routes bind no resources and resolve their effective hit cap to zero.
- Provider caps resolve once in the plan. PDB and Foldseek retain their
  configured cap, AFDB exact is bounded to one, enabled zero/oversized caps
  fail, and enabled ESM Atlas fails before output because no adapter or approved
  compute-network route exists.
- The CLI writes one canonical `provider_plan.json` plus four independently
  checksummed provider-entry files. Entry and plan validators reject content,
  checksum-inventory, or ID tampering. No Nextflow route, provider adapter,
  cache key, runtime parameter, or M6 code changed in this slice.

### Focused evidence and next action

- Forty-eight provider-plan and contract cases pass, including enable/disable,
  configured/effective caps, database binding, ESM fail-closed behaviour,
  byte determinism, CLI output, default-example equality, and tamper rejection.
  Repository schema validation, targeted Ruff format/lint, targeted `ty`, and
  `git diff --check` pass.
- Integrate this resolver contract before implementing the separate typed-empty
  bundle and Nextflow routing slices. Run the complete locked gate only at the
  coherent R2 batch boundary; do not infer remote-provider or M6 evidence from
  this local plan-only correction.

## 2026-08-19T00:07:10Z - Deterministic-resume Marmic replay is running

### Immutable execution evidence

- Committed the canonical channel-order correction as
  `8326afb668054a481eac03b74f71857cd8daf72b` and pushed it once to `main`.
- Actions run `32199203030`, job `95909221455`, passed that exact commit in
  6m28s under Pixi 0.76.2.
- The rebuilt controller is byte-identical to the installed reviewed controller
  at SHA-256
  `ba5754386e2b6e9cc46ca7f0aa720cd3207dc1fe9c80357a8c42715c5b0f2f46`.
  Deployed dispatcher/job-wrapper/recovery checksums remain
  `d7d29d77eb258f6235a1a1e2a3b65864d915b6888b1279aa6e018e2d9aead1d2` /
  `ac7ee72d9866c2b277e53203bf0d8c877b8db17f4d7ab6e7f5ff2bc606e4cddc` /
  `5334a95d54a5c990c975b1db6814e77435652618181c11070584e379a35a4ab6`.
- Staged exactly one fresh Marmic source archive with nf-helper
  `82431e4c56cb4cd2ef4ea67321fd01fad7ba65cb` and submitted run
  `gtd-m6-nextflow-smoke-20260819T000318Z-8326afb66805-b63c878f`, Slurm
  `629614`. Its first structured state is `RUNNING`, terminal false.
- The existing 30-minute heartbeat is rebound and active for only this run.
  Failed run `629533` and every earlier failed run/cache remain retained but
  excluded from monitoring, resume, reuse, and cleanup.

### Next exact starting point

While non-terminal, leave run `629614` untouched and continue the isolated R1
raw-loader parity slice with focused checks only. At terminal, use separate
reviewed-wrapper status, bounded logs, and collect operations; classify all
retained evidence before run-related source edits. Do not stage M6 science.

## 2026-08-19T00:32:57Z - Raw-loader and provider-plan batch passes integration gate

### Integrated foundation evidence

- Integrated the strict raw-document loader foundation, all identified M6 raw
  authority/evidence readers, and the immutable provider-plan contract as four
  focused commits after the deterministic-resume smoke source.
- The focused integrated corpus passes 203 M6, edge, raw-loader,
  provider-plan, and typed-contract tests. Schema export/runtime validation,
  targeted Ruff, targeted `ty`, and `git diff --check` pass.
- One complete locked gate passes Ruff format/lint, `ty`, 544 unit tests, 115
  contract tests, 68 integration tests, schemas, public-panel and documentation
  checks, actionlint, the full Nextflow syntax/stub-resume sweep, and all Bash
  wrapper syntax checks.
- No provider route, external request, cache key, M6 acceptance criterion, or
  active Marmic run changed. Run `629614` remains owned by source `8326afb` and
  is monitored only at the fixed heartbeat cadence.

### Remaining boundaries and next exact starting point

- R1 still requires the separately inventoried non-M6 runtime JSON/YAML readers
  to migrate or be explicitly classified as external-tool/service parsers.
- R2 provider-plan routing, typed empty/no-model bundles, network-site refusal,
  complete content identities, and classified retries remain separate slices.
- Amend the unpushed provider-plan commit with this journal evidence, push the
  four-commit batch once, and watch exactly one CI run. Continue focused R1/R2
  work while the independent Marmic smoke remains non-terminal; do not stage
  M6 science.

## 2026-08-19T00:44:22Z - Scientific and operator raw loaders are strict

### Bounded R1 migration

- Migrated the remaining non-M6 scientific/operator document readers for MR,
  additional-copy staging, refinement staging, candidate funnels, public
  controls/panels, review checkpoints, structure-search qualification, and
  repository schema checks to the shared duplicate-key and non-finite-number
  rejecting JSON/YAML boundary.
- Domain-specific errors now preserve the exact input path and JSON pointer
  from the strict loader. Existing typed models, symlink checks, scientific
  semantics, serializers, and external-tool parsing remain unchanged.
- Added 34 mutation routes covering every migrated JSON/YAML entry point.
  The mutation tests and all existing touched-adapter suites pass 243 tests.
  Targeted Ruff format/lint, targeted `ty`, and `git diff --check` pass.

### Remaining boundary and next exact starting point

- Remaining direct JSON decoders are confined to database/cache/network code,
  AFDB HTTP response parsing, and fixed HPC controller/run-state code. Classify
  external response bodies separately from repository-owned manifests before
  migrating them; do not fold those operational boundaries into this commit.
- Review and commit this scientific/operator slice without pushing or running a
  full suite. Continue with a separately bounded HPC-owned manifest/state slice
  while CI for `f879a9a` and Marmic smoke `629614` remain independent.

## 2026-08-19T00:48:48Z - HPC-owned JSON state uses the strict boundary

### Bounded R1 migration

- Migrated fixed P0 input specifications, local HPC configuration/run records,
  collected review JSON/JSONL, inspectable result records, optional failure
  signatures, and the fixed M4 import evidence loader to the shared strict JSON
  boundary. Dispatcher protocol, transport commands, remote scripts, limits,
  and state transitions did not change.
- Duplicate keys and non-finite numbers now fail with their exact path/pointer.
  Optional failure-signature construction deliberately fails closed to no
  signature when its diagnostic job-result document is malformed.
- Sixteen focused mutation cases and all existing touched HPC model/client/CLI
  suites pass 94 tests. Targeted Ruff format/lint, targeted `ty`, and
  `git diff --check` pass. No remote operation or full suite ran.

### Remaining boundary and next exact starting point

- Direct JSON decoding is now confined to database/cache/network modules and
  the AFDB HTTP response parser. Separate repository-owned database manifests
  and sidecars from external HTTP response bodies before migration.
- Review and commit this HPC-owned state slice separately. Then migrate the
  repository-owned database metadata/cache documents with focused cache and
  database tests; keep external response parsing as an explicit final class.

## 2026-08-19T00:57:41Z - Database and external JSON boundaries are strict

### Final direct-decoder migration

- Migrated database resource sidecars/manifests, source bundles, resumable
  download state, coordinate-cache layouts/metadata/indexes, resource
  inventories, the ESM Atlas probe response, and AFDB metadata responses to the
  shared duplicate-key and non-finite-number rejecting JSON grammar.
- Repository-owned file loaders retain path-aware `DatabaseError` diagnostics.
  External ESM Atlas/AFDB responses retain their separate parse-failure
  semantics and raw evidence; no request, endpoint, cap, cache identity, or
  provider policy changed.
- Twelve focused mutation routes and all existing touched database,
  cache/network, source-bundle, storage, and AFDB suites pass 113 tests.
  Targeted Ruff format/lint, targeted `ty`, and `git diff --check` pass.

### R1 parser boundary and next exact starting point

- No direct `json.loads`, `json.load`, or `yaml.safe_load` call remains outside
  the central `schemas/io.py` implementation; all repository entry points now
  pass through that strict document boundary, while canonical serialization
  stays unchanged.
- Review and commit this final direct-decoder slice without a full suite or
  push. Integrate commits `85484ae`, `f7fdb5a`, and this commit onto main while
  preserving the terminal Marmic/roadmap evidence. Run one complete locked gate
  for the combined R1 boundary, push once, and watch one CI run.

## 2026-08-19T00:56:15Z - Marmic standard-resume smoke passes all R0 gates

### Terminal collected evidence

- Run `gtd-m6-nextflow-smoke-20260819T000318Z-8326afb66805-b63c878f`,
  Slurm `629614`, completed successfully on immutable source
  `8326afb668054a481eac03b74f71857cd8daf72b`, nf-helper
  `82431e4c56cb4cd2ef4ea67321fd01fad7ba65cb`, Pixi 0.76.2, lock SHA-256
  `a31c520126e559154433546f45b92d2617bc622f89ffd6b0422c0579c0dda66b`,
  and Marmic policy SHA-256
  `696f9e7d1153af664e6cb5cc818cd618287f80d759dc9dda15b2c7819b466623`.
- The first operational trace contains exactly 25 `COMPLETED` tasks and 25
  distinct native child IDs. Operational resume contains exactly 25 `CACHED`
  tasks with byte-identical ten-file digest manifests. Leakage resume contains
  exactly six cached truthless tasks--two catalogue imports, two PDB searches,
  and two Foldseek searches--plus 19 completed track-specific tasks.
- The four search children have distinct native IDs and each requested 32 CPUs,
  16 GB, and 24 hours. Per-job bounds pass; observed peak concurrency is one,
  so no aggregate queue/rate-limit enforcement claim is made.
- Collected v2 evidence contains both the active `M6C001` and typed-empty
  `M6C057` cases with checksum-bound identity decisions and edge-observation
  lists. All seven final qualification checksum entries verify, the exact ten
  allow-listed scientific outputs are present, and terminal state is
  `COMPLETED`/exit zero/`success` with no failure signature.
- Static-typing-preview and redundant-`first` warnings remain retained. The run
  is a two-case stub and explicitly `acceptance_evidence=false`.

### Classification and next exact starting point

- R0 and the Marmic migration are accepted as orchestration evidence. R0A's
  corrected evaluator/fan-out contracts remain accepted from the prior
  evidence-complete Viper smoke. No operational/leakage M6 science was run and
  Gate 1 remains blocked behind R1--R4.
- Never query, resume, recollect, clean, or reuse run `629614` or its cache.
  Rebind the existing heartbeat from run monitoring to the R1--R3 development
  loop. Integrate the focused raw-loader slices, then continue the remaining R2
  foundations; do not stage M6 science.

## 2026-08-19T01:09:49Z - R1 strict contract foundation passes final gate

### Integrated R1 evidence

- Actions run `32201700388`, job `95916697573`, passed the preceding
  raw-loader/provider-plan batch at `f879a9a0a4a13a1c6fd726c8a66d50bf5b026654`
  in 6m53s under Pixi 0.76.2.
- Integrated three further focused commits covering every remaining
  scientific/operator, HPC-owned, database/cache, and external-response JSON or
  YAML entry point. Outside the central `schemas/io.py` parser implementation,
  `src/` contains no direct `json.loads`, `json.load`, or `yaml.safe_load` call.
- The integrated focused mutation/contract corpus passes 162 tests and schema
  validation. One complete locked gate passes Ruff format/lint, `ty`, 606 unit
  tests, 115 contract tests, 68 integration tests, schemas, public-panel and
  documentation checks, actionlint, the full Nextflow syntax/stub-resume sweep,
  and all Bash wrapper syntax checks.
- Together with the already integrated strict scalar/finite models, duplicate
  scientific-ID diagnostics, authoritative schema export, TSV taxonomy, and
  removed/bound configuration caps, this closes R1's source/runtime gate. No
  scientific policy, threshold, provider request, or M6 criterion changed.

### Next exact starting point

Amend the unpushed final R1 commit with this journal/roadmap evidence, review
the complete diff/status, push the three-commit batch once, and watch exactly
one CI run. Then continue R2 provider-plan routing and typed empty/no-model
bundles with focused tests; do not stage M6 science.

## 2026-08-19T01:31:02Z - Direct typed JSON closes the final R1 parser gap

### Observed gap and correction

- Final review found that raw path/text readers used the central duplicate-key
  parser, but direct `ContractModel.model_validate_json` calls still delegated
  JSON tokenisation to Pydantic. Strict scalar/non-finite validation was active,
  but duplicate mapping keys could retain the last value.
- `ContractModel.model_validate_json` now decodes UTF-8 and passes the document
  through the same path-aware duplicate/non-finite parser, then reserializes
  finite unambiguous JSON before Pydantic's strict JSON-mode validation. This
  preserves supported datetime, enum, and path decoding without coercing
  booleans or numbers.
- A direct `SequenceGroupRecord` JSONL duplicate-key regression fails at
  `SequenceGroupRecord:/source_record_count`. Existing direct non-finite tests
  now assert the shared raw-parser diagnostic.

### Final evidence and next exact starting point

- The focused typed-contract file passes 101 tests. One complete locked gate
  passes Ruff format/lint, `ty`, 606 unit tests, 116 contract tests, 68
  integration tests, schemas, public-panel and documentation checks,
  actionlint, the full Nextflow syntax/stub-resume sweep, and all Bash wrapper
  syntax checks.
- R1 is now complete for raw path/text and direct typed JSON/JSONL entry points.
  Commit this correction with the updated roadmap, push once after the already
  running prior CI concludes, and watch exactly one new CI run. Then resume R2
  provider-plan routing; do not stage M6 science.

## 2026-08-19T01:37:21Z - Disabled provider routes emit typed total bundles

### First R2 routing slice

- Added a deterministic disabled-provider adapter and CLI consuming one
  checksum-bound disabled `ProviderPlanEntry` plus the complete sequence-group
  catalogue. It executes no provider software and makes no network request.
- Every sequence group receives an explicit `skipped_policy` /
  `not_interpretable` result. Search results, empty structural hits, empty
  coordinate sources, raw reason/log files, and one checksum-bound manifest are
  always emitted, so downstream channels remain total. This state is distinct
  from an executed scientific no-hit.
- Enabled, tampered, duplicate-sequence, and empty-sequence inputs fail before
  output creation. Repeated runs are byte-identical.

### Focused evidence and next exact starting point

- Twenty-two provider-plan, disabled-bundle, tamper, determinism, and CLI tests
  pass. Targeted Ruff format/lint, targeted `ty`, and `git diff --check` pass.
  No full suite, provider request, Nextflow route, or remote operation ran.
- Commit this Python/CLI contract slice. Next, pass provider entries into each
  enabled adapter so effective caps/resources are verified there, then route
  enabled versus disabled entries in Nextflow and prove exact process counts.

## 2026-08-19T01:40:11Z - Enabled routes authenticate aggregate provider plans

### Second R2 routing slice

- Added one shared enabled-route verifier that loads the aggregate provider
  plan, provider entry, and database manifest through authoritative contracts.
  It requires the expected provider and adapter, an enabled route, exact entry
  file checksum/inventory equality, the aggregate database-manifest checksum,
  and unchanged ready resource IDs/manifests.
- Disabled entries, entry-byte drift, database-manifest drift, and adapter
  version drift fail before provider execution.

### Focused evidence and next exact starting point

- Twenty-seven provider-plan, route-authentication, disabled-bundle, CLI,
  determinism, and tamper cases pass. Targeted `ty` and `git diff --check`
  pass; the only lint finding was one line-length correction made before this
  hand-off. No full suite, provider request, Nextflow route, or remote action
  ran.
- Commit this route-verification slice. Then add optional plan/entry inputs to
  the three existing search adapters for the normal workflow, resolve hit caps
  from the authenticated entry, and retain the frozen legacy/M6 callers until
  their separately versioned route is changed.

## 2026-08-19T01:48:31Z - Enabled adapters bind provider-plan identities

### Third R2 routing slice

- Added optional aggregate-plan and entry inputs to PDB MMseqs2, ProstT5/
  Foldseek, and exact AFDB requests. When present, each adapter authenticates
  the complete route before provider execution. Supplying only one route file
  fails closed; legacy/frozen callers remain readable until their separately
  versioned workflow route is changed.
- PDB and Foldseek ignore caller hit-cap values on the planned route and use
  the authenticated entry's effective cap. Plan and entry checksums enter
  cache identities and output manifests; AFDB authenticates the enabled route
  and retains its fixed one-model policy.
- Bumped adapter versions to `pdb-sequence-mmseqs-v3`,
  `prostt5-foldseek-pdb-v5`, and `afdb-exact-v2`; regenerated the canonical
  provider-plan example and updated checksum-bound stubs.

### Focused evidence and next exact starting point

- Forty-nine provider-plan, route-binding, disabled-bundle, PDB/Foldseek/AFDB,
  qualification, fixture-integrity, and CLI tests pass. Targeted Ruff
  format/lint, targeted `ty`, and `git diff --check` pass. No real provider,
  Nextflow, full-suite, or remote operation ran.
- Commit this adapter slice. Next add the provider-plan resolver and disabled
  bundle processes to `PDB_SEQUENCE_DISCOVERY`, route each provider on its
  typed entry, expose the ESM disabled bundle, and prove enabled/disabled
  process cardinality plus cached resume in the focused Nextflow stub.

## 2026-08-19T02:08:33Z - Provider plan is authoritative in Nextflow discovery

### Fourth R2 routing slice

- Added fixed Nextflow processes for provider-plan resolution, typed disabled
  bundles, and deterministic PDB/Foldseek hit aggregation. The discovery graph
  reads each typed plan entry, runs only enabled adapters, and emits a total
  bundle for every disabled route including ESM Atlas.
- Removed duplicate root/Nextflow PDB and Foldseek hit-cap parameters; their
  values now come only from the authenticated provider entries. Existing
  e-value, coverage, length, query-count, GPU, and AFDB request controls remain
  explicit.
- Added a typed merge adapter so both PDB sequence and ProstT5/Foldseek hits
  reach coordinate registration. It does not cross-rank or filter providers;
  it validates provider ownership, rejects duplicate hit IDs, sorts
  deterministically, and records both input checksums.

### Focused local evidence

- Fifty-five provider-plan/bundle/adapter/merge/qualification tests pass.
  Nextflow syntax, schema validation, targeted Ruff format/lint, targeted `ty`,
  and `git diff --check` pass.
- Default discovery runs exactly six processes: resolver, three enabled
  adapters, disabled ESM, and hit merge; resume is 6/6 cached. An all-disabled
  fixture runs resolver, four disabled bundles, and hit merge; resume is also
  6/6 cached, with every result `skipped_policy`/`not_interpretable`.
- Integrated `main.nf --analysis_stage first_copy` completes 17 processes and
  resumes 17/17 cached with merged hits feeding coordinate registration. One
  initial focused run exposed and then fixed a same-basename staging collision
  by assigning provider-specific staged filenames.

### Next exact starting point

Commit this routing slice without pushing or running a full suite. Integrate
the four ordered R2 commits onto current main after the final R1 CI is green,
run one complete locked gate, push once, and watch one CI run. Then continue R2
with canonical network-site refusal and classified retry policy; do not stage
M6 science.

## 2026-08-19T02:25:35Z - R2 provider routing passes complete integration gate

### Integrated evidence

- Actions run `32205271905`, job `95927183890`, passed the final R1 direct-JSON
  correction at `8bab00e89c1aa3e844d086d53937422f4d437ac4` in 6m5s under
  Pixi 0.76.2.
- Integrated four R2 commits establishing typed disabled bundles, aggregate
  plan/entry/database authentication for enabled routes, plan-derived PDB and
  Foldseek caps, versioned plan-bound adapter identities, Nextflow enabled/
  disabled routing, and deterministic PDB/Foldseek hit aggregation.
- Focused evidence covers default routing, every-provider-disabled routing,
  both 6/6 cached resumes, and integrated first-copy execution with 17/17
  cached resume. One observed same-basename staging collision was reproduced
  and fixed with provider-specific staged filenames.
- One complete locked gate passes Ruff format/lint, `ty`, 630 unit tests, 116
  contract tests, 68 integration tests, schemas, public-panel and documentation
  checks, actionlint, the full Nextflow syntax/stub-resume sweep including both
  provider route matrices, and all Bash wrapper syntax checks.

### R2 pause boundary and next exact starting point

- R2 remains in progress: complete raw-input/cache identities, canonical
  network-site refusal, classified retries, and remaining complete tuple/
  channel fan-out still require their named slices. R3 is explicitly paused by
  the user and must not start without a new instruction.
- Amend the unpushed routing commit with this evidence and roadmap state, review
  status/diff, push the four-commit R2 batch once, and watch one CI run. The
  heartbeat may inspect a newly active authorised Marmic run and fix observed
  R2 defects, but it must not re-query terminal run `629614`, start R3, or stage
  M6 science.

## 2026-08-19T02:33:53Z - R2 provider-routing checkpoint is paused

### Immutable CI evidence

- Actions run `32208595324`, job `95936568909`, passed source
  `14c9d5e70e59b1215368dfe5ec15fb29cccc1819` in 6m21s under Pixi
  0.76.2. The exact pushed four-commit provider-routing batch is therefore green
  locally and in CI.
- Main is otherwise clean. There is no active Marmic/Viper job; terminal smoke
  `629614` remains collected and excluded from further query, resume, reuse, or
  cleanup.

### Pause boundary and next exact starting point

- Pause at R2. Remaining R2 work is complete raw-input/cache identity,
  canonical network-site refusal, classified retry policy, and remaining
  complete tuple/channel fan-out. Do not start any of those as a new slice
  until the user resumes development; only fix an evidence-backed bug in the
  completed R2 checkpoint or a newly authorised Marmic test.
- R3, R4, M6 science, joint-copy, heteromer, and unknown-crystal work remain
  prohibited. The existing heartbeat is paused after this hand-off.

## 2026-08-19T10:53:48Z - Programme pivots to a prototype-first heteromer path

### User-approved scope change

- The user approved publishing v0.1 despite its known incompleteness and
  explicitly authorised bounded two-component `nA + mB` development before
  corrected M6/R2--R4 hardening.
- Rewrote `AGENTS.md`, the active v0.2 roadmap, and the full-program roadmap so
  the next scientific target is a minimal fixed-A/one-B 6RTZ control, followed
  by end-to-end 6RTZ, explicit `nA + mB`, minimal catalogue partner search, and
  a small control slice.
- The historical single-component roadmap now carries a supersession banner;
  historical M0--M6 evidence and the 7L6G three-of-six limitation remain
  unchanged. The documentation index identifies the active versus historical
  plans.
- Unfinished adverse-review, R2--R4, M6, localisation, unknown-crystal, and
  advanced-composition work is retained as post-prototype debt. A deferred item
  moves forward only when a known heteromer control demonstrates a blocking or
  scientifically answer-changing defect.

### Next exact starting point

Prepare and publish an explicitly incomplete archival v0.1 release: finalise
version metadata, dated changelog, and release notes; run focused documentation/
version checks plus one release boundary gate; commit, push, tag, and publish
the source release. Then begin v0.2 P1 without resuming the former R3/M6
hardening sequence.

## 2026-08-19T11:06:26Z - Archival v0.1.0 release candidate passes gate

### Release preparation and evidence

- Set Python, Pixi, and Nextflow release metadata to `0.1.0`; updated active
  version assertions and the stub software manifest. `pixi.lock` remained
  unchanged at SHA-256
  `a31c520126e559154433546f45b92d2617bc622f89ffd6b0422c0579c0dda66b`.
- Added dated changelog and release notes that explicitly label v0.1.0 as an
  incomplete archival research snapshot with M6 held, no heteromer support,
  the 7L6G three-of-six limitation, sequential copy placement, and deferred
  crystallographic/robustness debt.
- Focused version/CLI/integration checks pass 13 tests; CLI reports `0.1.0`;
  schema and documentation checks pass.
- One complete release-boundary gate passes Ruff format/lint, `ty`, 630 unit
  tests, 116 contract tests, 68 integration tests, schemas, public-panel and
  documentation checks, actionlint, full Nextflow syntax/stub-resume coverage,
  and Bash wrapper syntax.

### Next exact starting point

Review and commit the authority/roadmap/release diff, push once, and watch one
CI run. After green CI, create and push annotated tag `v0.1.0`, publish the
GitHub release from `docs/releases/v0.1.0.md`, and verify the remote tag/release.
Do not start v0.2 implementation before the archival tag is immutable.

## 2026-08-19T12:28:47Z - Incomplete archival v0.1.0 is published

### Immutable release evidence

- Release commit `cab4cb7628faa26b18349e5440ebb8bb29fb7780` passed Actions
  run `32246051614`, job `96046684140`, in 7m26s under Pixi 0.76.2.
- Annotated tag `v0.1.0` points to that exact commit and was pushed to the
  private remote.
- GitHub release `v0.1.0 — archival incomplete research prototype` was
  published at
  `https://github.com/asuq/nf-genome_to_diffraction/releases/tag/v0.1.0`.
  It is neither a draft nor a prerelease; its text explicitly records the M6
  hold, missing heteromer support, 7L6G three-of-six result, sequential copy
  placement, and deferred hardening.
- The release tag remains immutable. These post-release hand-off edits are not
  part of v0.1.0 and remain uncommitted for the first v0.2 milestone.

### Next exact starting point

Start v0.2 P1 only when requested: bump development metadata to `0.2.0.dev0`
and implement the minimal fixed-A/one-B Phaser adapter for a known 6RTZ control.
Use focused tests and real Phenix early; do not resume R3/M6 hardening first.

## 2026-08-19T13:23:02Z - v0.2 development line is open

### Completed boundary

- Preserved the immutable archival `v0.1.0` tag at
  `cab4cb7628faa26b18349e5440ebb8bb29fb7780` and changed only the active
  development line.
- Set the Python project, Pixi workspace, Nextflow manifest, and runtime package
  version to `0.2.0.dev0`; updated the direct CLI/package assertions and marked
  roadmap P0 complete.
- Five focused package/CLI/integration tests pass. The documentation link check
  passes, and resolved Nextflow configuration reports
  `manifest.version = '0.2.0.dev0'`. A full repository gate was intentionally
  not run for this metadata-only milestone.

### Next exact starting point

Begin P1 with the smallest fixed-A/one-B Phaser adapter and focused
command/parser/failure tests. Do not resume broad R2--R4 or M6 hardening unless
the known 6RTZ control exposes a specific blocker.

## 2026-08-22T14:38:49Z - P1 fixed-A/one-B adapter is locally green

### Completed implementation

- Added one deliberately bounded `1A + 1B` adapter and CLI action. It verifies
  the two exact-sequence groups, fixed A coordinate, B search model, MTZ
  preflight, and Phenix manifest; fixes A with `solution_at_origin = True`; and
  searches exactly one B ensemble.
- Added a typed partner-search result that keeps explicit no-solution, tool
  failure, and parse failure separate. A failed search never proves B absent,
  and packing/component markers remain search evidence rather than biological
  proof.
- The adapter records the combined solution files, B-specific TFZ, and
  `incremental_llg = LLG(A+B) - LLG(A)`. Primary/fallback classification uses
  that increment, not total LLG dominated by A: strict `>100`/`>10`, then
  strict `>50`/`>5`.
- Reused the existing tested Phaser completed-output and final-coordinate
  metric parsers instead of adding a second interpretation path. General
  `nA + mB`, Nextflow orchestration, catalogue partner selection, and unrelated
  hardening remain outside this slice.

### Local evidence and open gate

- 154 focused partner, first-copy, add-copy, CLI, and typed-contract tests pass.
  Targeted Ruff format/lint, targeted `ty`, documentation links, and
  `git diff --check` pass.
- No full repository gate was run; this is an adapter milestone rather than an
  end-to-end or release boundary.
- P1 remains unaccepted until the same adapter runs against real installed
  Phenix using checksum-reviewed 6RTZ A-parent, HisH B-model, sequence,
  preflight, and parent-LLG inputs.

### Next exact starting point

Prepare the smallest fixed Marmic 6RTZ adapter-isolation profile, validate its
local fake lifecycle, then push the immutable source only with explicit user
authority and run exactly one real Phenix job through the reviewed wrapper.
Classify that result before adding end-to-end Nextflow or general `nA + mB`.

## 2026-08-22T15:18:19Z - Fixed 6RTZ public inputs prepare locally

### Public-source evidence and implementation

- Downloaded only the two public RCSB 6RTZ files already frozen in the tracked
  protocol. Their observed SHA-256 values and byte sizes exactly match the
  frozen coordinate and structure-factor identities.
- Verified that entity 1 maps to chain A and the frozen 253-aa HisF sequence,
  while entity 2 maps to chain B and the frozen 201-aa HisH sequence. The
  coordinate polymers contain 252 and 200 observed residues, respectively,
  with the frozen full sequences retained for composition.
- Added one fixed input preparer. It converts the deposited reflections to MTZ,
  writes polymer-only A/B PDBs and exact sequence groups, and emits only the
  A-first-copy model/hypothesis plus B-partner inputs needed by P1.
- The preparer ran successfully on the exact public files. Independent MTZ
  preflight selected `F(+),SIGF(+),F(-),SIGF(-)`, `FreeR_flag`, space group
  `P 32 2 1`, and a high-resolution limit of approximately 2.77 A with the
  expected review warning because local Xtriage was intentionally skipped.

### Local evidence and next exact starting point

- Eleven focused preparer/partner tests pass; targeted Ruff and `ty` checks
  pass. The public-source preparation and preflight were real local operations,
  but no local Phenix installation was claimed or used.
- Add only the fixed `heteromer-smoke` managed-wrapper profile needed to stage
  these public sources and execute A-first-copy followed by fixed-A/one-B on
  Marmic. Keep it sequential, single-job, and non-Nextflow for adapter
  isolation. Then request explicit push authority before remote staging.

## 2026-08-22T15:30:41Z - Fixed Marmic heteromer smoke is locally ready

### Closed local profile

- Added one path-closed `heteromer-smoke` profile across the local controller,
  remote dispatcher, job body, resource mapping, bounded collection, and run-ID
  contract. It accepts only a pushed revision and an owned run ID; no arbitrary
  case, path, Phaser flag, or command is exposed.
- Login staging invokes the fixed public preparer in download mode, so only the
  two protocol-frozen 6RTZ RCSB objects are fetched and verified before compute.
- One sequential Marmic job requests 8 CPUs, 16 GB, and 24 hours. It verifies
  Phenix, runs real Xtriage, places exact HisF as the one-copy A parent, then
  fixes that checksum-bound result and searches exact HisH as B. This adapter
  isolation deliberately adds no Nextflow entry point.
- The profile writes a compact gate summary plus exact input, preflight,
  parent, partner, command, log, coordinate, MTZ, and checksum artefacts. A
  primary or fallback score cohort is accepted only with a packed output and
  explicit fixed-A/B placement markers.

### Evidence and next exact starting point

- The complete fake Marmic stage, 8-CPU/16-GB/24-hour submit, sequential job,
  result gate, and bounded collect lifecycle passes. The broader focused set is
  130 tests green; targeted Ruff, `ty`, Bash syntax, and wrapper checks pass.
- The actual preparer download path also completed against RCSB and reproduced
  both frozen SHA-256 values. No real Phenix execution has occurred yet.
- Review and commit this profile slice. The local branch is then four coherent
  v0.2 commits ahead of `origin/main`; request explicit authority before one
  push, CI, wrapper deployment, or Marmic submission.

## 2026-08-22T15:42:38Z - P1 source is green; Marmic transfer is unavailable

### Immutable source and CI evidence

- With explicit user authority, pushed the four v0.2 commits through
  `b45416a40bbe05575fccba7e7906decacac0d1b3`; local `main` and `origin/main`
  agree at that exact source.
- GitHub Actions run `32582065724`, job `97052827065`, passed the complete
  locked foundation gate in 7m28s under Pixi 0.76.2.
- The reviewed deployment inputs are dispatcher SHA-256
  `132c9c0ac7da6da28bc23613256e11dc83b0ee68ff40002705730a41cc46ae7c`,
  job-wrapper SHA-256
  `4847e0b77540e053c6d9cf288848f04f8d6f79dcb806bd7e81c49d315482929f`,
  and recovery SHA-256
  `5334a95d54a5c990c975b1db6814e77435652618181c11070584e379a35a4ab6`.

### External blocker and exact restart

- The checksum-bound `deploy-tools` operation was attempted twice through the
  normal managed wrapper and once with explicit external-network permission.
  Every attempt ended before dispatcher execution with `Connection closed by
  UNKNOWN port 65535`, classified as `transfer_failure`.
- No remote tool deployment was confirmed, no run directory was staged, and no
  Slurm job was submitted. Do not infer a software defect, create a replacement
  run, or use raw SSH from this evidence.
- When the Marmic SSH endpoint is reachable, retry only `deploy-tools` for exact
  pushed source `b45416a40bbe05575fccba7e7906decacac0d1b3`. After checksum
  confirmation, stage and submit exactly one `heteromer-smoke`, then monitor,
  collect, and classify that owned run before any P2/P3 work.

## 2026-08-22T16:47:48Z - Marmic transport restored; home quota blocks all writes

### Classification

- The first resumed deployment accidentally used the current default
  Viper-specific local configuration and reproduced the earlier connection
  closure. Read-only local configuration inspection identified the existing
  Marmic-specific configuration; no remote mutation occurred in that attempt.
- Using the explicit Marmic configuration restored transport and reached the
  site. The checksum-gated recovery then failed before deployment because it
  could not create its temporary directory: `Disk quota exceeded`.
- One subsequent read-only managed readiness operation reached the existing
  dispatcher but it could not create the zero-length owned `.discard` file for
  the same quota reason. This confirms a Marmic home-filesystem/quota blocker,
  not a source, scientific, CI, scheduler, or network defect.
- No tool deployment was confirmed, no run directory was staged, and no Slurm
  job was submitted. No source change or remote cleanup is justified by this
  evidence.

### Exact restart

Free a small amount of the Marmic home quota outside this workflow. Then use the
explicit Marmic wrapper configuration to deploy exact pushed source
`b45416a40bbe05575fccba7e7906decacac0d1b3`; after checksum confirmation, stage
and submit exactly one `heteromer-smoke`. Do not use the default Viper
configuration, raw SSH fallback, or unreviewed remote deletion.

## 2026-08-22T17:04:03Z - Cleanup exposed missing configuration-parent bootstrap

### Observed evidence and smallest correction

- The installed local controller was stale and did not recognise
  `heteromer-smoke`; the deterministic current-source controller was therefore
  built at SHA-256
  `47837da784f2c033564fe045d0491279d5af29c0fb8bce2173a12fe93bf1ecec`
  and used directly without replacing the user-owned installed binary.
- With quota available, exact source `b45416a40bbe05575fccba7e7906decacac0d1b3`
  and its reviewed dispatcher/job-wrapper checksums deployed successfully via
  checksum-gated recovery.
- Managed readiness then showed the fixed P0/Phenix configuration absent. The
  preserved checksum-confirmed local candidate could not be restored because
  storage cleanup had removed the fixed `_config` parent directory and the
  create-only operation assumed that parent already existed.
- Corrected only that observed bootstrap defect: `p0-configure` now creates its
  one fixed owned parent directory with mode `0700` when absent, then applies
  the existing canonical-path, ownership, containment, payload, checksum, and
  atomic-install checks unchanged.
- The missing-parent regression and the complete fake `heteromer-smoke`
  lifecycle both pass. Targeted Ruff, `ty`, Bash syntax, and diff checks pass.

### Next exact starting point

Commit and push this one correction, watch exactly one CI run, deploy the exact
successor tools through the explicit Marmic configuration, restore the
checksum-confirmed P0/Phenix paths, require readiness, and then stage and submit
exactly one `heteromer-smoke`.

## 2026-08-22T17:18:01Z - Heteromer smoke no longer depends on obsolete P0 inputs

### Evidence-backed scope reduction

- Source `4dd67d9524703d32a8090517a4caabaa1919da7b` passed Actions run
  `32586642486`, job `97063896607`, in 7m36s and deployed successfully through
  checksum-gated recovery. The successor dispatcher SHA-256 is
  `dc60443f435edbdc428521a8c68cf1c5a776b9eade77f16e18bdc93cba3f539c`;
  the job-wrapper and recovery identities remain unchanged.
- Recreated the fixed configuration parent, but the preserved seven-line P0
  candidate correctly failed readiness because cleanup removed historical P0
  inputs. Attempting to rebuild that bundle stopped locally because its private
  pipeline configuration contains declaration-only fields removed by the
  current strict schema. No invalid bundle was uploaded.
- The heteromer control needs none of the old catalogue, unknown MTZ, pipeline
  config, or database state. Requiring complete P0 readiness was therefore an
  unnecessary dependency, not a reason to resurrect obsolete inputs.
- Narrowed staging to bind only the preserved private Phenix-manifest path and
  the independently frozen Phenix SHA-256 from the fixed local P0 identity
  specification. The CLI still exposes no path or checksum argument: the
  controller resolves both fixed local records internally, and the dispatcher
  verifies the remote regular file and checksum before recording it for the
  job.
- The focused controller-binding regression and complete fake Marmic
  `heteromer-smoke` lifecycle pass; targeted Ruff, `ty`, Bash syntax, and diff
  checks pass.

### Next exact starting point

Commit/push this dependency reduction, watch one CI run, deploy the matching
tools, and stage exactly one `heteromer-smoke` through the explicit Marmic
configuration. Submit only that owned staged run, then monitor, collect, and
classify before any further feature work.

## 2026-08-22T17:33:04Z - First real heteromer smoke reaches legacy Phenix boundary

### Immutable run and terminal classification

- Source `d53e17d274cdac0a78dc44aae1fbd7637fc0fab6` passed Actions run
  `32587350629`, job `97065649788`, in 5m35s and deployed with dispatcher,
  job-wrapper, and recovery SHA-256 values
  `a333050b7a6840f2996f01212a3d37d5e5f04bdb00913ee6d60f5cb1a2623081`,
  `8908dfca9c6e15330e6ae5defcdaffc6eb28f646c5f84e008535077473c5adc6`,
  and `5334a95d54a5c990c975b1db6814e77435652618181c11070584e379a35a4ab6`.
- Staged the one owned run
  `gtd-heteromer-smoke-20260822T172504Z-d53e17d274cd-20eced0a` through the
  checksum-gated source-archive fallback and submitted Slurm job `632765` with
  the fixed 8-CPU/16-GB/24-hour profile.
- The job terminated `FAILED`, exit 1, classified `environment_failure`.
  Bounded logs and collection show every prepared 6RTZ input passed its staged
  checksum. Execution stopped before Xtriage at Phenix-manifest loading because
  the preserved Marmic manifest predates executable hashing and lacks
  `executable_sha256` for all seven required commands. Collected failure
  signature is
  `06f6f220eb9c9abfb800822e3cfb74632cb6cf9cd1ce00febab6d3aa737a7674`.
- This is a manifest-compatibility/configuration defect, not a scientific
  no-hit, Phaser failure, scheduler failure, or damaged input. Do not resume,
  clean, or reinterpret run `632765`.

### Smallest correction and next exact starting point

- Added a non-destructive `phenix refresh-manifest` operation. It requires the
  legacy manifest to remain verified, verifies its recorded `phenix_env.sh`
  checksum, re-probes the same installed build, hashes every resolved required
  executable, and writes a strict run-owned successor; the site manifest and
  licensed installation remain unchanged.
- The heteromer job now refreshes first and uses only that run-owned successor.
  The refreshed manifest is included in bounded collection and final checksums.
- Focused refresh, environment-drift, partner, and complete fake Marmic
  lifecycle tests pass; Ruff, `ty`, Bash syntax, and diff checks pass.
- Commit/push this correction, watch one CI run, deploy matching tools, and
  stage/submit exactly one fresh `heteromer-smoke`. Collect/classify it before
  any end-to-end or `nA + mB` work.

## 2026-08-22T17:49:58Z - Real 6RTZ fixed-A/one-B gate passes

### Immutable execution and collected evidence

- Source `092a898d426d585c30973f50b652d315a12e216a` passed Actions run
  `32588181601`, job `97067630752`, in 7m23s. Matching deployed dispatcher,
  job-wrapper, and recovery SHA-256 values were
  `73572eb97beffe27d42c0093f10400ef09fc73a789ac707597ebb6f5de9cac20`,
  `23a0de5aa83222f627f7a2a1701634a0eeba1ef299ceb9dd7e4507713e626bec`,
  and `5334a95d54a5c990c975b1db6814e77435652618181c11070584e379a35a4ab6`.
- Staged run `gtd-heteromer-smoke-20260822T174312Z-092a898d426d-083c796f`
  through the checksum-gated source-archive fallback and submitted Slurm job
  `632767` with 8 CPUs, 16 GB, and a 24-hour limit. It completed with exit 0,
  scheduler `COMPLETED`, and `failure_class=success`.
- The run-owned refreshed Phenix 2.1-6048 manifest validates and contains
  SHA-256 identities for all seven required executables. Real Xtriage passed
  the derived 6RTZ MTZ in space group `P 32 2 1` at 2.771 A with the selected
  `F(+),SIGF(+),F(-),SIGF(-)` observations and no warning codes.
- Exact HisF first-copy completed packed with one placed copy, LLG 1566.207,
  and TFZ 42.2. The fixed-A/HisH search completed packed with combined LLG
  6620.861, incremental LLG 5054.654, B-specific TFZ 71.2, and the primary
  score cohort. The combined PDB contains exactly one `fixed_parent` and one
  `search_partner` placement marker.
- Every entry in `heteromer-smoke-checksums.sha256` verifies locally. The
  collected typed results, commands, PHIL, raw logs, PDBs, MTZs, preflight,
  summary, and refreshed manifest all agree; `gate_passed=true` and no failure
  signature was emitted.

### Milestone decision and next exact starting point

- Accept P1 (minimal fixed-A/one-B adapter) and P2 (6RTZ adapter-isolation
  smoke). This is a known exact-model positive control, not evidence for
  genome-wide partner identification or unknown-crystal performance.
- Begin P3 only: obtain A through the existing normal component workflow,
  retain an explicit composition review decision, then search B without manual
  file substitution inside the scheduled task. Preserve run `632767`; do not
  clean it, rerun the isolated gate, or start general `nA + mB` first.

## 2026-08-22T18:05:56Z - P3 approved-seed bridge is locally wired

### Completed local vertical slice

- Added a narrow approved-partner bridge that consumes the existing
  `stage-approved-seeds` output and MR review package. It requires exactly one
  approved one-copy A row, rechecks the stage/validation checksums, review-owned
  coordinate/result assets, packing, placed count, and parent LLG, then binds
  the fixed B model from the complete checksum-bearing 6RTZ preparation.
- Added `analysis_stage=heteromer` to the existing `main.nf` entry point rather
  than creating another root workflow. It reuses discovery, model preparation,
  diverse first-copy MR, review-package generation, and explicit MR approval,
  then runs one internal approved-partner process. Same-component additional
  copy and T12 branches remain unchanged.
- The control preparation is staged as a directory, not a lone manifest, so
  the referenced B model is present and checksum-verifiable in the process
  work directory.
- Focused bridge tests reject changed parent evidence and verify the exact
  A-LLG/B-model hand-off. The direct `analysis_stage=heteromer` Nextflow stub
  reaches all 19 expected processes and publishes the approved stage plus
  partner result. Targeted Ruff, `ty`, schema, Nextflow syntax, and diff checks
  pass; the full all-entrypoint stub was not rerun locally.

### Next exact starting point

Review and commit this local P3 bridge without pushing unless separately
authorised. P3 remains open until a real normal-workflow 6RTZ run obtains A,
crosses an explicit composition decision, and searches B with no manual file
substitution. Do not start general `nA + mB` first.

## 2026-08-22T18:57:21Z - P3 real checkpoint successor is ready

### Green integration boundary

- The user confirmed continuing `git push origin main` authority. Pushed P3
  bridge source `8b728c5f994b4bbec1dc6c0383981b4d8826a550`; Actions run
  `32591430241`, job `97075780779`, passed in 7m28s under Pixi 0.76.2.
- Kept the same fixed `heteromer-smoke` profile rather than adding another
  profile or root Nextflow entry point. The accepted adapter-isolation evidence
  remains immutable; a fresh successor now exercises the component checkpoint.
- Added fixed control review support around the real A result: one typed source
  record, one physically plausible Matthews row, a one-hypothesis funnel
  manifest, and current strict pipeline config feed the ordinary MR review
  builder. A predeclared control policy selects only the inspectable frozen
  HisF sequence in an explicit decision TSV, then the existing approval
  validator/stager produces the approved A state consumed by the P3 bridge.
- The parent result now retains its workflow-compatible
  `first_copy_phaser_<hypothesis>` directory identity while fixed-name evidence
  copies remain collectable. The B search is invoked only through
  `mr approved-partner`, not direct argument substitution.
- Focused preparation/review tests and the complete fake Marmic stage, job,
  checkpoint, partner gate, and bounded collection pass. Targeted Ruff, `ty`,
  Bash syntax, and diff checks pass.

### Next exact starting point

Commit/push this control-checkpoint successor, watch one CI run, deploy matching
tools, and stage/submit exactly one fresh `heteromer-smoke`. Collect and verify
the review package, decision, approved stage, parent/partner metrics, and
checksums before accepting P3 or beginning explicit `nA + mB`.

## 2026-08-22T19:32:12Z - P3 accepted; P4 joint-copy slice is locally green

### Immutable P3 evidence

- Source `a486ce5093b18f8fde7029d9d3a286c61beb9e76` passed Actions run
  `32592306850`, job `97077913763`, in 6m26s. Marmic run
  `gtd-heteromer-smoke-20260822T190514Z-a486ce5093b1-6f99f217`, Slurm `632797`,
  completed with exit 0 and `failure_class=success`.
- The collected normal MR review package contained one inspectable HisF seed;
  the predeclared decision approved only that seed, and the checksum-bound
  normal-workflow approved stage supplied the parent to the partner bridge.
  No direct parent-file substitution bypassed the checkpoint.
- The parent retained one packed copy at LLG 1566.207 and TFZ 42.2. HisH search
  retained one fixed-parent and one search-partner marker, combined LLG
  6620.861, incremental LLG 5054.654, B TFZ 71.2, and the primary cohort. All
  eleven final checksum entries pass. P3 and programme Gate C are accepted.

### P4 local slice

- Generalised only the existing first-component and fixed-parent adapters to
  explicit positive copy counts. A hypothesis may retain the legacy one-copy
  search or request all declared A copies jointly; the partner command writes
  explicit A/B composition counts and jointly searches the requested B copies.
- Added the frozen 3U7Q `2A + 2B` preparer and extended the same fixed
  `heteromer-smoke` profile rather than adding a profile or root workflow.
  Real public input preparation passed locally. The deposited NifD entity is a
  one-residue Q440E construct relative to `WP_012698832.1`; this relationship is
  now explicit in the preparation manifest, while NifK is sequence exact.
- Focused copy-count, preparer, CLI/client, Bash-syntax, and complete fake
  Marmic lifecycle tests pass. The fake lifecycle retains both the accepted
  6RTZ checkpoint result and the new two-A/two-B result.
- The named P4 `pixi run --locked check` gate passes: 651 unit, 116 contract,
  and 70 integration tests, plus schemas, public panel, docs, action lint,
  Nextflow syntax/full stub-resume, and all wrapper syntax checks.

### Next exact starting point

Run the named P4 locked gate, inspect the complete diff, commit and push one
coherent joint-copy milestone, watch exactly one CI run, deploy matching tools,
and stage exactly one evolved `heteromer-smoke` on Marmic. Collect and classify
both controls before starting P5 catalogue partner enumeration.

## 2026-08-22T20:34:00Z - P4 reaches joint B search; 16 GB is insufficient

### Terminal evidence and classification

- Source `00b29ccd66618553bfbdc8156aa12c7669de5177` passed Actions run
  `32594507579`, job `97083257467`, in 7m22s. Matching tools were deployed with
  dispatcher and job-wrapper SHA-256 values
  `71a935c065fdbebd25d966843c8a36f12c2d1bfd4c433774e49ee8e3123cc2ca`
  and `e5ff5a05191afef2160cc25016ad86e2296fdeb29cee68fa71998a4b9554c8a1`.
- Marmic run `gtd-heteromer-smoke-20260822T195026Z-00b29ccd6661-d2a3877c`,
  Slurm `632812`, completed terminal `OUT_OF_MEMORY`; retained failure signature
  is `c22e70e9c300f0a0f21efb4dab69fea4ce70c71648f61871a987bcc1b2dec548`.
  Preserve it; do not resume, clean, or reinterpret it.
- The unchanged 6RTZ checkpoint path passed. Real 3U7Q Xtriage passed at 1.000 A
  in `P 1 21 1`; the joint A command requested two copies and retained exactly
  two packed placements with LLG 17887.289 and TFZ 127.4. The fixed-A/joint-B
  command correctly declared `2A + 2B`, but Slurm recorded a cgroup OOM and
  Phaser exited `-9` before a B solution. All eighteen retained checksums pass.
- This is a fixed-profile capacity defect, not a scientific no-hit or adapter
  parse failure. Increase only `heteromer-smoke` memory from 16 to 32 GB. Also
  correct the first-copy start log to report the actual joint search count; it
  had logged one while the retained command correctly searched two.
- The first resource-fix CI run `32597071536` failed only because `caplog`
  depended on global logger state left by earlier unit tests; stderr confirmed
  the corrected value was two. Replaced that order-dependent assertion with a
  direct logger-call capture. The focused regression and the complete 651-test
  unit suite pass.

### Next exact starting point

Run the focused fake Marmic lifecycle, first-copy logger test, wrapper syntax,
and diff checks; commit/push this narrow correction, watch one CI run, deploy
matching tools, and stage one fresh 32 GB successor. Do not start P5 until it is
terminal, collected, and classified.

## 2026-08-22T21:42:12Z - 3U7Q 2A+2B completes; exponent parser causes false gate

### Terminal evidence and classification

- Source `3245ee42d2c5564a68f0a4f6c587625d9a54bb86` passed corrective Actions
  run `32597225648`, job `97090002745`, in 6m59s. Matching Marmic dispatcher,
  job-wrapper, and recovery SHA-256 values were
  `2cb33092f0af64fcf8e29620f751d68bb0e54cbe9e9b99a65b4c1f7bfd70e9b0`,
  `e5ff5a05191afef2160cc25016ad86e2296fdeb29cee68fa71998a4b9554c8a1`,
  and `5334a95d54a5c990c975b1db6814e77435652618181c11070584e379a35a4ab6`.
- Marmic run `gtd-heteromer-smoke-20260822T204506Z-3245ee42d2c5-4e566dc9`,
  Slurm `632825`, completed both Phenix searches under 32 GB but ended exit 4
  because the fixed scientific gate consumed a misparsed metric. Preserve the
  run; do not resume, clean, or reinterpret its normalised result.
- The 6RTZ checkpoint regression passed unchanged. 3U7Q Xtriage passed at
  1.000 A in `P 1 21 1`; the parent jointly placed two A copies at LLG
  17887.289 and TFZ 127.4. Joint partner MR then completed successfully with
  one fixed-parent marker, exactly two B markers, packing, and TFZ 371.4.
- Phaser wrote combined PDB LLG `2.47e+05`. `_PDB_LLG` matched only the decimal
  prefix and normalised it as `2.47`, creating incremental LLG `-17884.819` and
  a false `below_threshold` cohort. The native log independently reports final
  LLG about 246594 and explicitly says the partner placement will be correct.
  All eighteen retained checksums pass.

### Smallest correction and next exact starting point

- Extend only the PDB LLG numeric token to accept an optional exponent. A
  focused regression parses `2.47e+05` as 247000; replay against the collected
  real PDB returns LLG 247000, TFZ 371.4, three total placement markers, and
  PAK 0. All 34 focused first-copy/partner tests plus Ruff and `ty` pass.
- Commit/push the parser correction, watch one CI run, deploy matching tools,
  and stage exactly one fresh 32 GB successor. After submission, restore a
  30-minute thread heartbeat rather than continuous polling. Do not start P5
  until the parser-fixed run is terminal, collected, and classified.

## 2026-08-22T22:58:00Z - P4 explicit 2A+2B gate accepted

### Immutable acceptance evidence

- Source `437dad7de44a8d67b1b618f2cad36c82b02870ca` passed Actions run
  `32600401614`, job `97097697201`, in 7m34s. The deployed Marmic dispatcher,
  job-wrapper, and recovery identities remained
  `2cb33092f0af64fcf8e29620f751d68bb0e54cbe9e9b99a65b4c1f7bfd70e9b0`,
  `e5ff5a05191afef2160cc25016ad86e2296fdeb29cee68fa71998a4b9554c8a1`,
  and `5334a95d54a5c990c975b1db6814e77435652618181c11070584e379a35a4ab6`.
- Marmic run `gtd-heteromer-smoke-20260822T215112Z-437dad7de44a-1ac7eb95`,
  Slurm `632835`, completed with scheduler `COMPLETED`, exit 0, and
  `failure_class=success` under the fixed 8-CPU/32-GB/24-hour profile.
- The 6RTZ normal-workflow checkpoint regression remained green: parent LLG
  1566.207, partner incremental LLG 5054.654, B TFZ 71.2, one fixed-parent and
  one searched-partner marker, packing, and primary cohort.
- 3U7Q Xtriage passed at 1.000 A in `P 1 21 1`. Joint A MR retained exactly two
  packed placements at LLG 17887.289 and TFZ 127.4. Fixed-A/joint-B MR retained
  exactly two B placements, combined LLG 247000, incremental LLG 229112.711,
  B TFZ 371.4, packing, and primary cohort. The PDB contains one fixed-parent
  and exactly two search-partner remarks.
- All 18 final checksum entries verify locally. The run-owned Phenix 2.1-6048
  manifest is verified and contains SHA-256 identities for all seven required
  executables. The P4 heartbeat was deleted after terminal collection.

### Milestone decision and next exact starting point

- Accept P4 explicit positive `nA + mB` support and the 3U7Q `2A + 2B` control.
  This remains a known exact/construct-model positive control, not proof of
  genome-wide partner identification.
- Commit and push this evidence update. Begin P5 with one focused deterministic
  catalogue-selection contract and test: order supplied B candidates by
  existing SDS/native/composition/model evidence, cap the first wave at 25,
  and retain tested/untested counts and reasons. Do not add localisation tools,
  unknown crystals, a new root workflow, or a new HPC profile first.

## 2026-08-22T23:16:01Z - P5 deterministic catalogue selector is locally green

### Smallest completed slice

- Added one typed `ranking partner-plan` operation. It consumes an explicit
  parent sequence/copy count, requested B copy count, supplied catalogue
  sequence groups, existing Matthews/SDS rows, MTZ preflight/config, and one
  aggregate checksum-bound model registry. It performs no Phaser work and
  makes no identity claim.
- Every non-A sequence group is retained. Searchable rows are ordered by SDS
  label (`strong`, `compatible`, missing-neutral, `weak`), combined physical
  status/Matthews prior, then model identity, retained fraction, coordinate
  error, structural class, and immutable IDs. Native-PAGE evidence is explicitly
  `unavailable` and neutral in this first slice.
- The first wave is fixed at 25. Selected, cap-deferred, model-less, mass-less,
  and physically impossible rows are distinct statuses; selected/deferred and
  unsearchable counts are validated against the complete retained candidate
  table. Only physical impossibility, unusable mass, or no MR model prevents an
  attempt.
- Three focused tests pass: 28-candidate ordering/cap/counts plus byte-identical
  repeat, changed-model checksum rejection, and the fixed CLI surface. The 21
  partner/ranking tests, schema check, targeted Ruff, `ty`, and diff checks pass.

### Next exact starting point

Review and commit/push this selector slice, watch one CI run, then connect only
the selected rows to independent fixed-A/joint-B Nextflow items using the
existing adapter. Retain all result states and plan counts. Qualify P5 on the
fixed 6RTZ full catalogue before beginning the P6 control slice; do not add a
  root workflow/profile or localisation integration.

## 2026-08-22T23:46:41Z - P5 selected B rows fan out and aggregate locally

### Completed integration slice

- Generalised the approved-parent reader to complete positive A copy counts and
  added one planned-partner driver. It verifies the approved stage/review,
  selected candidate status, plan and plan-file identities, candidate/model
  checksum, parent composition, and model sequence identity before delegating
  to the accepted fixed-A/joint-B adapter. P1--P4 calls retain null selection
  provenance; planned results carry plan ID, plan SHA-256, and candidate ID in
  their result and search identity.
- Added one internal partner-search workflow to the existing
  `analysis_stage=heteromer`. The planner derives A from the approved stage,
  writes selected IDs as a plain newline boundary, and Nextflow fans those IDs
  into independent `process_mr` items. No Python/Bash scientific loop, new root
  workflow, analysis stage, or HPC profile was added.
- Added a typed partner-attempt summary. It requires the selected candidate set
  to equal the result candidate set exactly, counts hit/no-hit/tool/parse
  outcomes, retains deferred/unsearchable plan counts, and explicitly states
  that a failed partner search does not prove biological absence.
- Forty-three focused planner/approved-driver/partner tests pass, including
  changed model, changed review, plan provenance, and incomplete result
  inventory failures. Targeted Ruff, `ty`, and Nextflow syntax pass. A direct
  heteromer stub executed 22 processes including plan, one selected partner,
  and summary; the unchanged replay cached all 22 processes.

### Next exact starting point

Run the focused checks and inspect the complete diff, then commit/push this P5
integration slice and watch one CI run. Next build the fixed 6RTZ full-catalogue
control using the frozen 1,846-protein Thermotoga catalogue, require HisH in the
selected wave, and execute/count every selected attempt before accepting P5.
  Do not add localisation tools, unknown crystals, or a new workflow/profile.

## 2026-08-23T00:18:27Z - Fixed 1846-protein P5 control is locally ready

### Real local control evidence

- The protocol's dynamic NCBI Datasets ZIP endpoint no longer reproduced the
  frozen bundle byte checksum and was correctly rejected. Replaced that fragile
  route only for this fixed control with the assembly-versioned static NCBI FTP
  `protein.faa.gz`; the decompressed FASTA still must match the protocol's exact
  size and SHA-256, so source identity is unchanged.
- The real Thermotoga FASTA matches the frozen 729424-byte identity and contains
  exactly 1846 unique protein records, including checksum-matched HisF and HisH.
  Catalogue import produced 1846 source records and 1846 exact sequence groups;
  two sub-30-aa records retain catalogue review flags and one exact group is
  explicitly `unsearchable_catalogue_ineligible` because Matthews correctly
  omitted it.
- The fixed catalogue control publishes a path-closed catalogue manifest,
  strict control config, preparation manifest, and one-model exact HisH
  registry. Real local Matthews enumeration retained 7380 rows for 1845 eligible
  groups. The approved-parent plan retained 1845 non-A candidates, selected
  exactly HisH as the sole searchable row, deferred none, and recorded 1844
  unsearchable rows; the combined HisF+HisH composition is plausible.

### Existing-profile extension and checks

- Extended only `heteromer-smoke`: login staging downloads/verifies the static
  FASTA, imports the catalogue, and checksum-binds its outputs. After the green
  6RTZ and 3U7Q gates, the existing job enumerates full-catalogue Matthews,
  plans one HisH attempt, runs it through the planned-partner driver, requires
  a complete attempt summary, and adds all P5 evidence to final checksums and
  bounded collection.
- The complete fake Marmic lifecycle passes the new staging, 1845-candidate
  plan, selected attempt, summary, gate, and collection assertions. The final
  touched/integration set passed 84 tests; repository-wide Ruff formatting/lint and `ty`,
  Bash wrapper syntax, Nextflow syntax, and diff checks pass.

### Next exact starting point

Review/commit/push this fixed P5 control, watch one CI run, deploy matching
tools, and stage exactly one fresh `heteromer-smoke`. Submit only that owned
run, then use a 30-minute thread heartbeat for wrapper-only status checks.
Collect/classify before accepting P5 or starting P6.

## 2026-08-23T01:38:15Z - P5 full-catalogue partner search accepted

### Immutable Marmic evidence

- The owned `heteromer-smoke` completed successfully from source
  `19e837dcab8401a254195cca2ecb5964397ac56a` under Pixi 0.76.2 with the pinned
  nf-helper commit. Bounded wrapper collection retained the terminal state,
  scientific records, commands, logs, and qualification summaries.
- The fixed Thermotoga catalogue imported 1846 source proteins as 1846 exact
  sequence groups. The plan retained 1845 non-A candidates, selected exactly
  one checksum-bound HisH sequence/model, deferred none, and kept 1844 typed
  unsearchable rows.
- The selected planned attempt completed with one packed B placement, partner
  TFZ 71.2, incremental LLG 5054.654, and complete plan/candidate/result
  provenance. The attempt summary retained its sole selected result.
- The 6RTZ `1A+1B` and 3U7Q `2A+2B` controls remained green. All 26 listed
  checksums and the SHA-256 identities of all seven required Phenix executables
  verified. P5 is accepted; the completed-run heartbeat was removed.

### Next exact starting point

Commit and push this evidence update, then begin P6 with the smallest focused
typed controls: missing B, wrong B, homomer non-regression, and the 9ECN
`unsupported_component_count` boundary. Reuse the existing accepted positive
controls and workflow/profile; do not implement three-component reconstruction,
localisation filtering, unknown crystals, or deferred hardening.

## 2026-08-23T02:20:00Z - P6 control slice is locally green

### Smallest completed slice

- Added one fixed P6 preparation/assessment module rather than a new workflow
  root or profile. It reuses the accepted 6RTZ and 3U7Q bundles to create a
  parent-only model registry for missing B, one checksum-bound 3U7Q-B wrong
  model against fixed 6RTZ-A, and the protocol-bound 9ECN three-component
  boundary.
- Missing B now survives the workflow as an empty selected channel and produces
  a complete zero-attempt summary. Against the retained real 1846-protein P5
  catalogue, all 1845 non-A rows were retained as unsearchable, with zero
  selected searches and a valid zero-result summary.
- The P6 assessor requires both accepted positive placements, completed
  missing/wrong controls without any complete-composition claim, a packed
  current-source first-copy result as the homomer-route non-regression, and
  explicit 9ECN `unsupported_component_count` while retaining possible partial
  A+B evidence. Tool or parse failures cannot pass the wrong-B control.
- The existing `heteromer-smoke` now stages only these fixed inputs, runs one
  additional wrong-B Phaser attempt, writes one six-case report, and retains
  its commands, results, report, and checksums. Twenty-nine focused unit tests,
  the fake Marmic lifecycle, Ruff, `ty`, Bash syntax, Nextflow syntax, and diff
  checks pass. The complete repository gate remains deferred to the v0.2
  release boundary.

### Next exact starting point

Review and commit/push the P6 slice, watch one CI run, deploy matching tools,
and stage exactly one fresh existing `heteromer-smoke`. After submission, use a
30-minute heartbeat for wrapper-only status. Collect and classify all six case
outcomes before accepting P6 or beginning the v0.2 release boundary.

## 2026-08-23T07:00:00Z - P6 diagnostic run passes but exposes claim-gate defects

### Terminal real-Phenix evidence

- Marmic `heteromer-smoke` run
  `gtd-heteromer-smoke-20260823T055337Z-8ade88261939-90c2832b`, Slurm `632965`,
  completed from source `8ade882619395b916f5261f904b4e4f84b8a8ad3` with exit
  zero under Pixi 0.76.2 and the pinned nf-helper revision. Bounded wrapper
  collection retained the fixed controls, P6 plans/results, logs, manifests,
  and qualification records.
- The accepted positive regressions remained stable. The full missing-B plan
  retained 1845 non-A candidates, selected zero attempts, and emitted a
  complete zero-result summary.
- The deliberately wrong 3U7Q-B model nevertheless produced a packed 6RTZ
  placement with incremental LLG 327.049 and TFZ 5.1 in the fallback cohort.
  This is valid search evidence and strong direct evidence that packing and MR
  scores cannot establish partner identity or a complete composition.

### Classification and next exact starting point

- Treat this run as diagnostic, not final P6 acceptance. The current report
  hard-codes no-claim and 9ECN boundary statements, under-binds fixed control
  identities, permits a vacuous missing catalogue in unit coverage, bypasses
  the real empty-partner Nextflow channel, and incompletely checksums P6 inputs
  and optional outputs.
- Correct those five acceptance boundaries in one focused slice, run touched
  Python/Nextflow/fake-Marmic checks, then commit/push/CI/deploy and replay the
  same fixed profile once. Do not reinterpret or clean Slurm `632965`.

## 2026-08-23T08:30:00Z - Corrected P6-v2 acceptance gates are locally green

### Completed correction

- The P6 preparation now binds the frozen protocol, exact 6RTZ and 3U7Q source
  preparations, parent hypotheses/models, component sequence relationships,
  MTZ/model identities, and the full 1846-sequence catalogue. The missing-B
  universe is exactly catalogue-minus-6RTZ-A: 1845 unique sequence groups with
  recomputed candidate IDs, zero selected attempts, and exact plan/summary
  checksum and count equality.
- Both positive controls are tied to their retained fixed-A parent hypothesis,
  placed count, packing, coordinate SHA-256, and LLG. Wrong B must reuse the
  exact 6RTZ parent/MTZ while carrying the checksum-bound 3U7Q-B model; a packed
  wrong hit remains typed `search_evidence_only` and is never composition-claim
  eligible.
- P6 writes one protocol-backed component-scope decision and six typed
  composition assessments. The 9ECN outcome is derived from observed three
  versus supported two components rather than copied into the summary.
- The actual partner-search Nextflow workflow now exercises an empty selected
  channel: one 1845-row plan, zero partner processes, one zero-result summary,
  and byte-identical cached resume. Staging, final checksums, and bounded
  collection cover the dynamic parent-only model, scope/assessment records,
  missing plan inventory, mandatory wrong-search evidence, and conditional
  solution PDB/MTZ.

### Focused evidence and next exact starting point

- Eleven P6 scientific tests, three fake Marmic lifecycles, 29 related partner
  tests, the focused empty-partner Nextflow stub, Ruff, `ty`, format, wrapper
  syntax, documentation, and diff checks pass. Independent review found two
  further release blockers; parent-solution and exact catalogue-universe
  bindings were added and their mutation regressions pass.
- Review the final diff, commit/push once, watch one CI run, deploy matching
  reviewed tools, and stage one fresh `heteromer-smoke`. Accept P6 only after
  terminal collection validates the P6-v2 report and every retained checksum.

## 2026-08-23 - Phase III development branch opened in parallel

### Branch boundary and authorised scope

- The user authorised Phase III source development on `dev/phase3` while the
  corrected v0.2 P6 Marmic replay continues from immutable `main`. The Phase III
  branch was created from `24f733c`; the active P6 run, release worktree, and
  retained evidence remain untouched.
- Phase III supports arbitrary ordered component records but fixed execution is
  bounded to six distinct components, three parent states per depth, 25
  attempts per depth, and 100 additional-component attempts per crystal.
  Depth three requires 9ECN validation; depths four through six remain
  provisional and cannot support a complete-composition claim.
- No Phase III HPC, M6, localisation, or unknown-crystal run starts before the
  relevant contracts/fixed profiles pass and v0.2 is preserved as an immutable
  release.

### Parallel starting slices

- Added the dependency-ordered Phase III roadmap and unified finding ledger.
- Started independent focused work on schema-v2 composition contracts and
  complete three-crystal Nextflow fan-out. Both use branches/worktrees derived
  from `dev/phase3`; neither may push or touch the v0.2 release line.
- Added the first local Phase III vertical slice: a schema-v2 JSON/TSV gel
  evidence manifest for SDS/native-PAGE observations with explicit mass,
  absolute uncertainty, method, condition, band role, replicate, source, and
  notes. Empty evidence is explicitly neutral, duplicate observation IDs fail,
  and every observation must reference a supplied crystal.
- Eleven focused gel-contract tests, the authoritative schema check, targeted
  Ruff, targeted `ty`, documentation links, and diff checks pass. Localisation
  adapters and ranking consumption remain deliberately separate slices.
- Closed the local `PIPE-P2-01` boundary: a zero-exit `phenix.refine` run is no
  longer publishable when final Rwork or Rfree cannot be parsed, and completed
  refinement contracts require both final values. The typed outcome is
  `failed_parse`; existing model/map files are not promoted as completed
  scientific evidence. Seven focused completion/status tests pass.
- Closed the local `PIPE-P2-02` boundary: an unknown or inconsistent catalogue
  identity in successful `phenix.sequence_from_map` output now emits a typed
  candidate-level `failed_parse` result rather than raising out of the process.
  The raw log remains retained and independent finalist processes can continue.
- Closed the local `PIPE-P1-09` stale-output boundary for T12. Every candidate
  now owns a new or empty output directory; a symlink, non-directory, or any
  pre-existing file fails before external execution, so a zero-output current
  attempt cannot publish a prior attempt's model, MTZ, or maps.

### Next exact starting point

Review and integrate each focused branch only after its regressions pass. Keep
the documentation changes uncommitted until combined with the first coherent
Phase III code slice. Continue wrapper-only P6 polling through its existing
heartbeat; do not duplicate the Marmic run or monitoring loop.

## 2026-08-23T15:30:00Z - Phase III composition-v2 contract slice is focused-green

### Completed contract foundation

- Added an opt-in `genome_to_diffraction.schemas.v2` namespace without changing
  the existing v1 P6 records. The six Phase III public records describe arbitrary
  ordered component lists, component-specific placement evidence, retained
  composition states, bounded expansion plans, scope decisions, and scientific
  assessments.
- Every v2 record is frozen and content-addressed over its complete canonical
  payload. Packing remains search evidence until identity and review support are
  present; claim eligibility is derived separately, and component depths beyond
  the validated depth remain provisional.
- Focused mutation coverage verifies content identities, ordering, evidence
  promotions, sequence-group uniqueness, deterministic plan inventories and
  budgets, provisional-depth claim refusal, final-review requirements, and
  continued v1 readability. The focused 18-test contract/package/ID slice, Ruff,
  and `ty` pass.

### Next exact starting point

Integrate this contract-only commit into `dev/phase3` after review. Build the
planner and Nextflow fan-out against these records in a separate slice; do not add
search execution, localisation, unknown-crystal profiles, or reinterpret v1 data
while integrating the contracts.

## 2026-08-23T15:30:00Z - Phase III per-crystal fan-out foundation is isolated

### Completed focused slice

- Extended the existing checksum-verifying crystal dispatcher with an explicit
  manifest-owned crystal ID. Omitting that ID preserves the v0.2 one-crystal
  contract; a multi-crystal manifest remains invalid on the legacy path.
- Added a Phase III workflow boundary that expands the validated manifest and
  uses Cartesian combination with the singleton catalogue and provider bundles.
  Each scheduled item therefore carries its crystal manifest, preflight,
  catalogue preparation, and provider preparation together instead of
  consuming shared preparation alongside only the first crystal.
- A focused stub prepares the two shared bundles once, dispatches three exact
  crystal identities, and proves that all three downstream items can read both
  shared bundles. The first run completes eight expected tasks; cached resume
  retains the same three distinct dispatch hashes and byte-identical evidence.
  The focused dispatcher unit tests, Ruff checks, and Nextflow syntax check pass.

### Next exact starting point

Integrate this boundary into the Phase III application workflow after the v0.2
release transition. Keep the existing v0.2 single-crystal entry point unchanged;
do not add unknown-screen profiles or general composition contracts in this
slice.

## 2026-08-23T16:20:00Z - Phase III shared-depth expansion planner is focused-green

### Completed focused slice

- Added a typed deterministic planner for one additional-component depth. It
  accepts one to three ranked packed parents, excludes sequence groups already
  represented by each parent, retains parent-specific physical eligibility for
  explicit copy hypotheses 1--4, and treats missing localisation, gel, Matthews,
  model-quality, and structural-diversity evidence as neutral scheduling
  evidence.
- Searchable hypotheses are allocated in deterministic diagonal rounds across
  candidate and copy-count positions, with parent rank round-robin at each
  position. One shared cap of 25 attempts applies across the complete parent
  beam, and the remaining global cap of 100 attempts is enforced independently.
  Selected, per-depth-deferred, globally deferred, reviewer-deferred, no-model,
  model-identity-unsearchable, and physically impossible outcomes remain typed.
- Corrected a contract gap discovered during implementation: the original
  singular-parent expansion plan could not itself prove a shared depth budget.
  Added an explicitly parent-bound depth-plan contract with parent summaries,
  parent-bound candidates, allocation ranks, and aggregate inventory/budget
  validation. The singular-parent v2 record remains readable but is not the
  authoritative Phase III scheduling boundary.
- The planner performs no search or support assessment. Selection reasons state
  explicitly that scheduling is not scientific support; LLG, TFZ, and packing
  are not planner inputs and cannot promote an identity or composition claim.

### Focused evidence and next exact starting point

- Six planner regressions cover deterministic evidence ordering, represented-
  group exclusion, three-parent/candidate/copy fairness, distinct depth/global
  budget dispositions, evidence mutation, missing-evidence neutrality, and the
  zero-physical-hypothesis path. Shared-budget and parent-binding mutations fail
  contract validation. The combined planner/contract slice passes 16 tests;
  package/typed-contract compatibility adds 115 passing tests. Targeted Ruff,
  `ty`, and the authoritative schema check pass.
- Integrate this commit after the composition-v2 contract commit. Use the new
  shared depth plan as the only scheduling authority when wiring Nextflow; do
  not reinterpret the singular-parent record as granting 25 attempts per
  parent. Phaser, Nextflow, localisation, unknown profiles, and scientific
  assessment remain intentionally outside this slice.

## 2026-08-23 - Phase III offline localisation contracts are focused-green

### Completed focused slice

- Added a checksum- and version-bound standalone PSORTb 3.0.6 adapter for one
  sequence group using the officially documented archaeal terse command. The
  attempt retains its input FASTA, version probe, resolved command, stdout,
  stderr, and typed result without public sequence submission.
- Normalised archaeal PSORTb results as membrane, surface, extracellular,
  soluble, or unknown. Tool and parser failures remain typed failed outcomes;
  incompatible informative observations resolve to conflicting rather than to
  an exclusion.
- Added a user-image and one-FASTA DeepTMHMM 1.0 runtime/input contract. The
  official documentation does not specify a stable local image entrypoint,
  arguments, or output wire format, so executable invocation remains explicitly
  blocked with an empty command. The image is checksum-bound, never
  redistributed, and no result is fabricated.
- Twenty focused command, parser, stub, failure, mutation, provenance, input,
  and outcome-resolution tests pass. Targeted Ruff, formatting, `ty`,
  documentation, and staged-diff checks pass.

### Next exact starting point

Inspect the user-provided DeepTMHMM image before defining any executable command
or raw-output parser. Integrate this contract slice into `dev/phase3` after
review; keep Nextflow fan-out, catalogue-wide localisation, first-wave policy,
and candidate ranking in later focused slices.
