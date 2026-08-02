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

The first prototype identifies candidates under the model `ASU = nA`, where one protein species may occur in one or more copies. Do not implement heteromer reconstruction yet.

The pipeline narrows candidates. It is not required to force one exact sequence or one unique locus. Exact duplicate protein sequences form one sequence-equivalence group linked to every compatible locus.

The protein catalogue is imported and trusted. Genetic-code inference, taxonomy assignment, and gene prediction are out of scope.

Use one annotation source per catalogue. Do not merge Prokka, RefSeq, PGAP, GenBank, Bakta, or other annotations in one run.

## 3. Mandatory scientific safeguards

- Keep the identity universe, model universe, and evidence universe distinct.
- External PDB, AlphaFold DB, and ESM Atlas hits may provide coordinates or family evidence, but may not become reportable identities unless mapped to a supplied catalogue sequence.
- Treat SDS–PAGE molecular weight as an apparent monomer/polypeptide-mass prior only. Never use it as ASU total mass or oligomeric-state evidence.
- Use sequence-derived mass for Matthews calculations.
- Retain multiple plausible ASU copy counts; default to the top three per candidate or candidate group.
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

- Use current Nextflow DSL2 with syntax parser v2 and typed workflow interfaces.
- Use Python 3.14 and modern typing. No backward-compatibility shims are required.
- Use Pixi and commit `pixi.lock`.
- Keep Nextflow responsible for deterministic execution, scheduling, retries, caching, and publication.
- Keep scientific ranking, state transitions, manifests, and report assembly in Python.
- Keep Bash wrappers thin and limited to environment setup plus one external-tool invocation.
- Introduce Rust only after profiling identifies a material Python bottleneck. Prefer a standalone CLI over a Python extension.
- Human checkpoints must be file-based. Never prompt interactively inside a scheduled Nextflow process.
- Candidate-specific scientific failures should emit normalised status records and allow the run to continue. Infrastructure or contract failures should fail clearly.
- Use immutable, content-addressed identifiers for sequences, models, databases, diffraction datasets, and hypotheses.

## 8. Testing policy

Every process adapter requires:

- a unit or contract test for command construction;
- a parser test with a frozen representative output fixture;
- a failure-path test;
- a stub mode suitable for `nextflow -stub-run` where practical.

Do not claim a Phenix integration is complete without testing it against a real installed Phenix runtime.

The first three MTZ datasets are feasibility tests, not a general validation set. At least one should be a known positive control consistent with `ASU = nA` if available.

## 9. Development sequencing

The current milestone is Task 00 / Epic 0 only. Follow later milestones in the
approved external handoff. Do not start heteromer logic, AF3 complex logic, or
local ESM Atlas deployment before the monomer/domain prototype satisfies its
acceptance criteria.

## 10. Documentation expectations

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
