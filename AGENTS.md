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
The active v0.2 prototype may implement `ASU = nA + mB` for exactly two protein
components. Start with an explicit known `1A + 1B` control, fix the placed A
solution, and search for B. Three-or-more-component reconstruction, AF3 complex
logic, and general assembly inference remain out of scope.

The pipeline narrows candidates. It is not required to force one exact sequence or one unique locus. Exact duplicate protein sequences form one sequence-equivalence group linked to every compatible locus.

The protein catalogue is imported and trusted. Genetic-code inference, taxonomy assignment, and gene prediction are out of scope.

Use one annotation source per catalogue. Do not merge Prokka, RefSeq, PGAP, GenBank, Bakta, or other annotations in one run.

## 3. Mandatory scientific safeguards

- Keep the identity universe, model universe, and evidence universe distinct.
- External PDB, AlphaFold DB, and ESM Atlas hits may provide coordinates or family evidence, but may not become reportable identities unless mapped to a supplied catalogue sequence.
- Treat SDS–PAGE molecular weight as an apparent monomer/polypeptide-mass prior only. Never use it as ASU total mass or oligomeric-state evidence.
- Use sequence-derived mass for Matthews calculations.
- Retain multiple plausible ASU copy counts. The current pilot cap is the top
  four per candidate or candidate group because that is the smallest
  predeclared cap that retains the known two-copy 8OOX control; keep the cap
  configurable and do not treat rank as evidence of the true copy count.
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
inputs, not validation data. Defer them until the known heteromer control works;
they must not calibrate scientific heuristics or support a validation claim.
M6 remains an independently reviewable robustness benchmark, but it no longer
gates experimental heteromer implementation.

## 10. Development sequencing

M0–M5 are accepted. Preserve the explicit limitation that 7L6G supports three
rather than its declared six copies; do not rerun, relabel, fabricate, or hide
it. The user authorised an archival v0.1 release even though M6 is held and the
software is incomplete. Label that release honestly; do not claim production or
M6 scientific acceptance.

After preserving v0.1, implement the smallest heteromer path before additional
hardening: known fixed-A/one-B placement on 6RTZ, end-to-end 6RTZ, then explicit
`nA + mB` and a small positive/negative control slice. Fix only defects that
block or scientifically invalidate that path. Unfinished R2–R4 hardening, M6,
localisation filtering, unknown operator crystals, and broader validation move
to the post-prototype backlog. Do not start R3 as an independent hardening
programme unless the user explicitly resumes it or a required heteromer result
demonstrates that a specific R3 defect is blocking execution.

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
