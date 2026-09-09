# Instructions for Codex and Development Agents

This file applies to the entire repository unless a deeper `AGENTS.md` explicitly narrows a rule.

## 1. Source-of-truth order

1. This `AGENTS.md`.
2. JSON Schemas under `schemas/`.
3. Example files under `examples/`.
4. The approved developer handoff retained outside this Git repository.

The tracked `docs/` tree contains operational runbooks and verified test reports.
It summarises implementation and observations but does not supersede the schemas,
examples, or retained handoff. Before making a specification-level or
scientific-policy change, consult the retained handoff and obtain explicit user
approval.

When documents conflict, use the earlier item in this order. Do not silently reconcile contradictions by inventing new policy.

## 2. Scope that must not change without explicit user approval

The user approved bounded two-component heteromer development on 2026-08-19.
The v0.2 release line may implement `ASU = nA + mB` for exactly two protein
components. Start with an explicit known `1A + 1B` control, fix the placed A
solution, and search for B.

On 2026-08-23 the user separately authorised Phase III development on the
`dev/phase3` branch while v0.2 release validation continues on `main`. Phase III
may represent arbitrary ordered protein-component lists, but fixed application
execution is bounded to six distinct components, three retained parent states
per depth, 25 attempts per depth, and 100 additional-component attempts per
crystal. Depth three must be validated with 9ECN. Depths four through six remain
provisional and cannot support a complete-composition claim. AF3 complex logic
and unbounded assembly inference remain out of scope.

On 2026-09-01, after `v0.2.0` was released and before any external use, the
user directed that the complete Phase III line be merged into `main` and that
all subsequent development continue there. `dev/phase3` is now a historical
integration branch, not an active source authority.

On 2026-08-31 the user approved a candidate-confidence-first clean break for
the unknown-crystal screen. Matthews retains the complete configured expected
copy range, while every initial MR hypothesis searches exactly one copy. The
active workflow must not impose a special four-copy or joint-copy admission
limit. Only an explicitly approved one-copy A seed may add copies, one at a
time, toward its retained expectation. Complete candidate assessment for all
three frozen crystals now precedes the remaining M6, closure, pass-2, atlas,
package, and v0.3.0 release programme. The canonical execution order is
`docs/v0.3-roadmap.md`.

On 2026-09-04 the user increased only the A-seed continuation limit from three
to five corrected-review-priority states per crystal for the next qualified
round. The three-parent composition beam, 25-attempt depth budget, and
100-additional-component budget are unchanged. This policy change requires a
new exact-source discovery/screen chain before the five-state decisions can be
consumed. For this round the user explicitly accepts Phaser's coupled two-copy
tNCS states for AD4; this does not convert them into strict one-copy evidence or
an identity claim.

On 2026-09-07 the user authorised a separate case-specific
`identification-screen` profile on Marmic, including implementation, testing,
push and deployment on `main`. It accounts for every catalogue sequence in each
supplied apparent-mass interval, not the earlier global 25-model pool. Explicit
existing-work reservations avoid duplicate tests, and unavailable models remain
visible non-executed records. The existing initial-copy, resource, tNCS,
catalogue-identity and human-review safeguards still apply. This is not approval
of the proposed full-expected-copy search or the deferred general mass-blind
generator redesign. Do not request the supervisor's solved identity as a
prerequisite for independent identification.

The user subsequently imposed a temporary five-job total limit on this Marmic
identification programme because other large jobs are active. Count one
controller and at most four preparation/MR children shared across the executor,
including submitted/pending work. Do not modify other user jobs, restart the
already compliant three-case smoke, or lift the cap without explicit direction.
This overrides the no-concurrency-cap policy only for this identification run
programme; scientific task budgets and other workflow defaults are unchanged.

The user then approved migration of this identification programme to MPCDF
Raven using the maintained nf-helper profile. Keep all project-managed tools,
inputs, work, results, temporary files and caches under `/ptmp`. Raven must not
inherit the temporary five-job cap: use its site profile and scheduler limits
(the inspected account permits eight running and 300 submitted jobs). Its
24-hour per-job limit is mandatory and resolved task allocations must be
recorded accurately. Bootstrap and verify Raven before retiring only the owned
Marmic run; preserve its evidence and avoid concurrent duplicate candidates.
Initial-copy, catalogue, scientific and human-review policy remains unchanged.
One-off raw SSH/bootstrap commands may be requested for explicit approval during
this migration; do not grant persistent broad SSH or scheduler permission.

On 2026-09-08 the user approved BR01 for v0.4: valid retained MR placements
receive target-aware preparation and one fixed diagnostic phenix.refine
macrocycle before final score-based candidate filtering and A-seed review.
Keep eligibility distinct from score filtering, preserve Free-R and incomplete
ASU/tNCS caveats, and reuse the shared refinement adapter and saved MR evidence.
Explicit A approval remains required before copy completion and deeper
follow-up. This is future v0.4 scope only; it does not change v0.3 execution,
approve current seeds, or authorise new scientific jobs. Implementation and
acceptance criteria are in docs/v0.3-v0.4-development-plan.md (BR01/WP3).

The user also assigned AF01 and AF02 to the v0.4 plan. AFDB Foldseek is a
fallback after suitable experimental-template routes, ideally using an
AlphaFold-predicted monomer of the original catalogue sequence as its query.
Development of the new original-sequence prediction/fallback component is
deferred until suitable GPU access is available. Preserve pLDDT/PAE and genuine
coordinate-based TM-score provenance; do not invent TM-scores for ProstT5-only
queries. Independently, the end-of-screening exact-sequence AlphaFold-model MR
check applies to retained finalists, including those first screened with PDB
models, not every screened candidate. These requirements do not authorise AF3
complex/stoichiometry inference or automatically approve any candidate.

Separately, the user requested an immediate Raven initial-MR screen with the
already retrieved exact-sequence AFDB models for the unknown crystals. This
does not require new GPU folding. Qualify predicted-model preparation and its
integration in the current identification profile before execution; preserve
the completed PDB screen, initial-copy/tNCS policy and human-review gates. Do
not claim that the deferred AFDB Foldseek fallback or automatic finalist check
has been implemented by running this bounded supplied-model cohort.
The user subsequently approved the narrow integration, focused testing,
commit/push/deployment, and a three-crystal smoke followed by the remaining
exact-model cohort. This approval does not change the deferred v0.4 scope or
the A-review boundary.

On 2026-09-09 the user cancelled the expanded identification programme,
including further AlphaFold/AFDB work, and explicitly accepted all three
candidate assessments as complete after supervisor confirmation that each
rank-one candidate was correct. Preserve that external confirmation separately
from computed MR, refinement and sequence evidence; do not invent unperformed
analyses or decision artefacts. Do not launch the remaining supplied-model
cohort or re-open the accepted assessments as a prerequisite for development.
The user directed work to RF-G1 through RF-G4 and then continuation through the
remaining planned v0.3 programme. The documented ranking-gate plan is the next
scientific scope; broader v0.4/GPU work remains deferred. Preserve cancelled-run
evidence, and stop only at genuinely required human decisions or new external
authority. This is not automatic permission to publish a release.

On 2026-09-10 the user explicitly approved a code-only push to the existing
private remote for CI after the local gate passes, followed by RF/M6 known-
control qualification through the reviewed Marmic workflow. Preserve exact-
source, frozen-input, truth-isolation and fixed-profile requirements. This does
not restart the cancelled crystal/AFDB investigation, approve human scientific
decisions, extend M6 to Raven, or authorise release publication.

The user then explicitly approved refreshing the M6 benchmark references in
place; preserving a separate original protocol is not required. Keep the same
case identities, acceptance thresholds and leakage rules, and rederive the
snapshot checksums, target-family bindings and M5 independence checks together.
Save downloaded sources, prepared benchmark inputs, truth-side evidence and
runner archives persistently under repository `.untracked/`, not `/tmp`.
Requalify the refreshed inputs before native execution; the former missing-
August-snapshot hold no longer blocks this approved refresh.

The user subsequently directed continued work through the release of v0.4,
including during their absence, and explicitly prohibited subagents. Worktrees
are permitted when useful. Complete the canonical v0.3 qualification and release
sequence, then the approved v0.4 WP0-WP5 programme, including BR01, AF01 and AF02.
This supersedes the earlier general deferral of v0.4 development, not the need
for suitable GPU resources, explicit scientific decisions, supported fixed-HPC
profiles or command permissions. The release request authorises publication
only after all corresponding acceptance gates genuinely pass. Do not restart
the cancelled operator-crystal identification/AFDB investigation or fabricate
human approvals to advance unattended work.

The pipeline narrows candidates. It is not required to force one exact sequence or one unique locus. Exact duplicate protein sequences form one sequence-equivalence group linked to every compatible locus.

The protein catalogue is imported and trusted. Genetic-code inference, taxonomy assignment, and gene prediction are out of scope.

Use one annotation source per catalogue. Do not merge Prokka, RefSeq, PGAP, GenBank, Bakta, or other annotations in one run.

## 3. Mandatory scientific safeguards

- Keep the identity universe, model universe, and evidence universe distinct.
- External PDB, AlphaFold DB, and ESM Atlas hits may provide coordinates or family evidence, but may not become reportable identities unless mapped to a supplied catalogue sequence.
- Treat SDS–PAGE molecular weight as an apparent monomer/polypeptide-mass prior only. Never use it as ASU total mass or oligomeric-state evidence.
- Use sequence-derived mass for Matthews calculations.
- Retain multiple plausible ASU copy counts through the configured Matthews
  range. Do not impose a separate static copy-count ceiling. Bound execution by
  ranked hypothesis budgets, search one copy in the initial screen, and add
  further copies sequentially only after review. Never treat copy rank as
  evidence of the true copy count.
- Matthews probability is a prior, not proof. Never reject a candidate solely because its Matthews probability is low unless the hypothesis is physically impossible.
- Scientific no-hit outcomes are valid completed analyses. Separate execution failure from scientific status.
- Do not use `R_free` as a high-throughput screening objective across large candidate sets.
- Do not force an exact paralogue or locus when the map cannot discriminate it.
- Preserve raw metrics. Do not collapse all evidence into one unexplained scalar score.

## 4. Remote-service policy

Public ESM Atlas requests are disabled by default. The user must explicitly set `allow_remote_sequence_submission=true` for a crystal or run.

Every remote response must be cached by sequence digest, provider, endpoint version or identifying metadata, query parameters, request date, and response checksum.

Do not assume compute nodes have internet access. Remote-provider tasks require a dedicated Nextflow label/profile.

Do not use the public ESM Atlas folding endpoint for whole-proteome prediction. The prototype uses Atlas sequence search and fetches selected Atlas structures; local ProstT5/Foldseek is the scalable whole-catalogue route.

## 5. Phenix policy

Phenix is an external licensed runtime. It is not installed by Pixi and must not be redistributed in a public container or repository.

The repository must include a bootstrap installer script, but that script must require a user-provided installer file and checksum. It must not automatically download Phenix.

Source `phenix_env.sh` only inside a dedicated subprocess wrapper. Never source it globally before invoking Pixi-managed Python because Phenix modifies `PATH` and exposes its own Python runtime.

The main scientific workflow must verify the Phenix installation manifest but must not install or upgrade Phenix.

## 6. Database policy

Database preparation is a separate Nextflow entry point. Normal analysis runs must not silently download or rebuild large databases.

Every database/cache object must record a release or snapshot identifier, preparation tool version, parameters, path, and checksum or manifest checksum.

Use local PDB and ProstT5 resources for the prototype. Use the public ESM Atlas API only when explicitly enabled. Local `ESMAtlas30` is deferred until evidence justifies the storage cost.

## 7. Engineering policy

- Follow KISS, DRY, YAGNI mindset
- Optimise the active v0.2 work for the smallest end-to-end scientific path that
  runs. Do not add a general schema, adapter, driver, retry framework, provider
  abstraction, or validation matrix unless the current heteromer vertical
  slice requires it.
- Use current Nextflow DSL2 with syntax parser v2 and typed workflow interfaces.
- Use Python 3.14 and modern typing. No backward-compatibility shims are required.
- Use Pixi and commit `pixi.lock`.
- Keep Nextflow responsible for deterministic execution, scheduling, retries, caching, and publication.
- Keep scientific ranking, state transitions, manifests, and report assembly in Python.
- Independent catalogues, samples, candidates, hypotheses, seeds, and finalists
  must be emitted as Nextflow channel items. Nextflow and the configured HPC
  executor own their scheduling and concurrency; Python and Bash must not run a
  multi-sample scientific loop, thread pool, process pool, or nested scheduler.
- A scientifically dependent chain may remain sequential inside one task only
  when the next operation requires the preceding result, such as iterative
  same-component copy placement. Independent chains must still fan out through
  Nextflow.
- Choose channel-item granularity from the external tool's efficient batch
  boundary. For database-backed batch tools such as MMseqs2 and Foldseek,
  deduplicate queries and use deterministic query/residue-bounded batches;
  never create one database-loading process per sample merely because samples
  are independent.
- A change to a shared-store task's inputs, parameters, tool binding, or output
  semantics must change its content key or adapter version and its cache-
  invalidation contract test. Never rely on a source commit alone to make a
  cross-track scientific cache safe.
- Keep Bash wrappers thin and limited to environment setup plus one external-tool invocation.
- Introduce Rust only after profiling identifies a material Python bottleneck. Prefer a standalone CLI over a Python extension.
- Human checkpoints must be file-based. Never prompt interactively inside a scheduled Nextflow process.
- Candidate-specific scientific failures should emit normalised status records and allow the run to continue. Infrastructure or contract failures should fail clearly.
- Use immutable, content-addressed identifiers for sequences, models, databases, diffraction datasets, and hypotheses.

## 8. HPC testing authority

- The local Git repository is the only source of truth. Never edit, commit, or
  push source on the HPC.
- Test only clean immutable commits that are available from the private Git
  remote. Use one isolated remote checkout per run.
- Routine remote operations must go through the reviewed repository-specific
  wrapper. Do not grant persistent approval to raw SSH, transfer, or scheduler
  commands.
- Version 1 may automate only the fixed smoke profile. Integration requires a
  separately reviewed profile; full and benchmark runs require explicit
  approval.
- Cancel only the scheduler job recorded for the owned run. Remote cleanup
  always requires explicit approval and exact run-ID confirmation.
- Retrieve and classify logs before proposing source changes. Do not change
  source in response to an infrastructure failure without evidence of a
  software cause.

## 8.1 Command approval discipline

- Use only command forms already covered by the user's persistent approvals.
  If a required command is outside those approvals, stop and ask the user
  instead of requesting or assuming a new command approval.
- Issue exactly one shell command per tool call. Do not combine commands with
  pipes, `&&`, `||`, semicolons, command substitution, subshells, or multi-line
  command sequences.

## 9. Testing policy

Every process adapter requires:

- a unit or contract test for command construction;
- a parser test with a frozen representative output fixture;
- a failure-path test;
- a stub mode suitable for `nextflow -stub-run` where practical.

For the prototype-first v0.2 path, use focused tests while iterating. Run the
complete locked repository gate only at a named end-to-end milestone or release
boundary, not after every edit.

After an observed failure has one focused regression test and the required
repository gate passes, prioritise the next real-data prototype run over
polishing synthetic tests. Add further test cases only when they protect a
distinct scientific invariant, safety boundary, or demonstrated failure mode;
do not delay real-data feedback in pursuit of perfect test coverage.

Do not claim a Phenix integration is complete without testing it against a real installed Phenix runtime.

The three frozen operator MTZ datasets are unknown-composition feasibility
inputs, not validation data. They may run only after the Phase III execution,
crystallographic, provider, and review-checkpoint foundations pass. They must
not calibrate scientific heuristics or support a validation claim.
M6 remains an independently reviewable robustness benchmark, but it no longer
gates experimental heteromer implementation.

## 10. Development sequencing

M0–M5 are accepted. Preserve the explicit limitation that 7L6G supports three
rather than its declared six copies; do not rerun, relabel, fabricate, or hide
it. The user authorised an archival v0.1 release even though M6 is held and the
software is incomplete. Label that release honestly; do not claim production or
M6 scientific acceptance.

After preserving v0.1, the smallest bounded two-component path was completed
and published as experimental `v0.2.0` from exact-source Marmic-qualified
commit `68d216f`. Preserve that tag, release notes, P6 evidence, and scientific
limitations as immutable read-only history.

Phase III is now the active development programme on `main`. Do not reinterpret,
mutate, or reuse a v0.2
Marmic run as Phase III evidence. Do not launch Phase III controls, M6 reruns,
localisation, or unknown-crystal analysis until the corresponding Phase III
contracts and fixed profiles have passed their local integration gates.

Complete the candidate-confidence critical path in `docs/v0.3-roadmap.md`
before advancing M6, final finding closure, unknown pass 2, or release work.
Each frozen crystal may terminate as exact, equivalent, family-level,
unresolved, or no-supported-candidate; forcing an answer is never a completion
criterion.

At the start of each new development loop, read the newest entry in
`docs/development-loop-journal.md` before changing code or running a new remote
profile. Before every session close or hand-off, append a concise dated entry
covering discoveries, accomplishments, immutable evidence, unresolved work, and
the exact next starting point. Do not include private paths, inputs, credentials,
or generated scientific data in this tracked journal.

## 11. Documentation expectations

Every new module must document:

- scientific purpose;
- exact inputs and outputs;
- external command and version requirements;
- failure semantics;
- status values;
- cache key;
- test coverage.

Reconcile specification-level changes with the retained external handoff before
implementation. Keep tracked reports free of private inputs, credentials,
machine-specific user paths, and generated pipeline outputs.
