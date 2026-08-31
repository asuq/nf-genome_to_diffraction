# v0.3 cleanup and documentation atlas plan

## Binding design decisions

- Build a multi-page static atlas committed with deterministic source and HTML.
- Surface one canonical `documentation.html` home with an upper-right Scientist
  / Developer view toggle and node-specific integrated documentation panel.
- Keep Validation & Evidence cross-cutting and converge both views at shared
  canonical workflow-stage and subsystem pages.
- Give every substantive active module a page; retain a complete searchable
  inventory for all functions, classes, Nextflow workflows/processes, CLI
  commands, schemas, reviewed wrapper operations, and important Bash functions.
- Use curated call diagrams for public and scientifically, operationally, or
  traceability-critical paths. Function sections show signatures, callers and
  callees, tests, failures, source links, and small critical excerpts.
- Generate structural facts from source while maintaining scientific narrative,
  subsystem boundaries, maturity, and diagrams as reviewed metadata.
- Give schemas and external tools first-class contract/boundary pages.
- Include only curated sanitised evidence. Private unknown-crystal reports remain
  outside the committed atlas.
- Use English, classic technical styling, light/dark themes, global search, and
  repository-relative offline links.
- Develop `current/`, then freeze deterministic release snapshots.
- Make freshness, links, schemas, examples, inventory, wheel contents, and
  structural cleanliness release-blocking.

## Clean-break target

- Public Nextflow entrypoints: `main.nf` and `prepare_databases.nf`.
- Internal validation entrypoint: role-named `validation.nf` under a dedicated
  top-level `validation/` tree.
- Public installed CLI: `genome-to-diffraction` only.
- Keep the reviewed HPC client as a Pixi-invoked internal repository tool and
  exclude it from the wheel.
- Support only the CLI and versioned file contracts as public interfaces.
- Remove milestone/gate identifiers from active executable names and schemas.
  Keep established domain acronyms. Preserve old identifiers only in immutable
  history and explicitly required historical evidence readers.
- Use role-based robustness/leakage validation terminology in the active interface.
- Remove obsolete entrypoints, adapters, aliases, tests, fixtures, and duplicate
  documentation without compatibility shims.
- Retain active-contract tests plus isolated tests for required historical
  evidence readers.
- Curate historical documents and rotate the development journal by release.

## Sequence

1. Generate the complete current executable inventory in a separate worktree.
2. Build the atlas generator, canonical viewer home, shared subsystem pages, module
   pages, contract pages, boundary indexes, and deterministic checks.
3. Secure unknown-pass-1 evidence and mandatory review from the active scientific
   source before moving executable code.
4. Use the inventory to execute the role-based clean break in focused reviewable
   migrations.
5. Regenerate the final atlas from the cleaned source and curate critical call,
   workflow, data-flow, and validation diagrams with Archify.
6. Close remaining Phase III findings, robustness/leakage validation, deeper analysis, reports,
   packaging, and release gates.
7. Freeze the accepted atlas and release evidence as the v0.3.0 snapshot.

## Current inventory baseline

The first deterministic extraction from pre-cleanup source found 152 application
Python modules, 2,241 Python symbols, 141 test modules, 73 Nextflow files with
118 declarations, six reviewed shell files with 108 functions, nine JSON
schemas, and 1,098 active milestone/gate-name occurrences. These counts are
diagnostic cleanup inputs, not release acceptance.
