# Documentation

This directory contains tracked operational documentation and verified test
reports. The JSON Schemas, examples, `AGENTS.md`, and separately retained handoff
remain authoritative for scientific policy and interface contracts.

## Available documents

- [Full-program roadmap](full-program-roadmap.md): programme phases from the
  active single-component prototype through heteromer search, advanced
  crystallographic/assembly support, calibrated automation, and the final
  internal research platform.
- [Single-component prototype roadmap](single-component-prototype-roadmap.md):
  detailed current maturity and authorised milestones from real-site
  qualification through structural discovery, MR, sequence narrowing, pilot
  calibration, independent validation, and the first internal release.
- [Viper-CPU runbook](viper-cpu-runbook.md): active site cut-over, secure
  bootstrap, cross-site M4 continuation, database track, and rollback.
- [M0 qualification status](m0-qualification.md): gate dashboard, frozen
  biological/MTZ evidence, preparatory Gemmi findings, fixed P0 boundary, and
  the operator-held evidence still required before structural discovery.
- [Structural-search interface](structural-search.md): active M1 provider
  contract, local PDB and exact AFDB commands and Nextflow entry point, outputs,
  cache identity, statuses, and failure semantics.
- [P1 direct-PDB qualification](p1-direct-pdb-qualification.md): immutable
  Marmic run provenance, catalogue/search counts, exact 8OOX-family retention,
  cached resume, resource observations, and remaining M1 scope.
- [P1 ProstT5/Foldseek qualification](p1-prostt5-qualification.md): immutable
  first real failure evidence, bounded-log correction, large-node resources,
  deterministic real pilot slice, and the still-open full-catalogue boundary.
- [P1 exact AFDB qualification](p1-afdb-exact-qualification.md): live public
  accession/API/mmCIF sequence equality, the exact pilot-derived
  `WP_042685700.1` mapping, coordinate checksums, and cache provenance.
- [M2 predicted-model preparation](m2-predicted-model-preparation.md): immutable
  predicted-coordinate mapping, fixed Phenix confidence processing, output
  identity, the real pilot qualification, and the still-open M2 boundaries.
- [M2 experimental PDB model preparation](m2-experimental-model-preparation.md):
  registered hit-to-coordinate inputs, the deterministic cleaned source-chain
  variant, identity/failure/cache semantics, tests, and the real qualification
  still required.
- [M3 first-copy Phaser boundary](m3-first-copy-phaser.md): exact and
  multi-source funnels, homologue-aware Phaser identity, final-packing parser,
  strict provisional score gate, typed fan-out, cache identity, and open P2
  work.
- [T12 brief refinement and sequence narrowing](t12-brief-refinement.md): fixed
  one-cycle refinement, stable map parameters, complete-catalogue scoring,
  typed failure/cache semantics, and Viper resource policy.
- [Development loop journal](development-loop-journal.md): the mandatory
  read-first hand-off record of discoveries, accomplishments, immutable
  evidence, unresolved work, and the next exact starting point.
- [Public methanogen and methanotroph control panel](public-control-panel.md):
  ten frozen X-ray structures, catalogue-to-construct mappings, reproducible
  source/MTZ preparation, runnable-control order, and one deliberate heteromer
  assumption violation.
- [Initial Marmic prototype report](prototype-test-report-2026-08-02.md): inputs,
  execution history, annotation findings, crystallographic preflight, Matthews
  counts, validation evidence, and limitations from the first real Task 05 run.
- [Marmic prototype runbook](marmic-prototype-runbook.md): historical project
  layout, pinned Pixi setup, manifest checks, Slurm launch, resume, output
  verification, logging, and scratch guidance.
- [Local-Marmic feedback loop](hpc-feedback-loop.md): immutable-revision
  foundation smoke plus fixed P0/P1 testing, installation, command interface,
  result records, failure classes, approval boundaries, and concurrency limits.
- [Local settings and rollback](local-settings-and-rollback.md): exact
  user-controlled files, recoverable disable/removal steps, restoration checks,
  and the boundary between local and Marmic state.

Generated results, logs, work directories, environments, biological inputs, and
licensed software are deliberately not tracked.
