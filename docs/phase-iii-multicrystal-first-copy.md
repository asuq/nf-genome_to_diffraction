# Phase III multi-crystal first-copy application

## Purpose and activation

Current application execution uses `phase3_application.nf` with the required
typed operation `phase3_operation=first_copy`. That root always uses reviewed
joint multi-crystal search and exposes no legacy single-crystal selector or
joint-mode switch. Archival single-crystal, heteromer-control, approved-seed,
and refinement execution remains isolated under `main.nf`.

Reviewed unknown applications additionally provide both
`phase3_crystallographic_review_stage`, `phase3_execution_identity`, and the
complete checksum-pinned localisation/gel bundle.
Supplying incomplete or continuation-only authority with the first-copy
operation fails before scheduling. These are internal Nextflow inputs for a
future fixed, reviewed operator profile; no arbitrary HPC path, crystal
selector, or user approval is exposed by this slice.

## Inputs and execution boundaries

One previously validated crystal manifest, preflight inventory, catalogue,
provider registration, predicted and experimental model preparations, Matthews
records, pipeline configuration, localisation/gel authority, and verified
Phenix manifest are shared.
`CRYSTAL_FANOUT_WORKFLOW` emits one manifest-owned, checksum-verified MTZ item
per crystal; catalogue and provider preparation remain single shared tasks.

When the reviewed inputs are present,
`VALIDATE_PHASE3_CRYSTALLOGRAPHIC_REVIEWS` reuses the existing registry-owned
three-crystal stage index and strict two-file stage validator. It checks the
exact execution identity, canonical `proceed|hold` decisions, crystal coverage,
package bindings, and every manifest MTZ checksum before publishing one
crystal-local decision bundle. `hold` is retained by
`RETAIN_PHASE3_CRYSTALLOGRAPHIC_HOLD`; it never reaches candidate ranking,
Phaser, or an invented MR-seed checkpoint. Only `proceed` items enter the
existing scientific workflow, and their own decision bundle remains in each
child task/cache identity.

`BUILD_PHASE3_DIVERSE_FIRST_COPY_FUNNEL` emits its crystal identity with the
Phase III evidence-bound funnel and publishes outputs under a
crystal-qualified directory. It independently validates complete catalogue
coverage, binds the localisation policy and per-group evidence into hypothesis
identities, ranks active before neutral groups, and retains first-wave
exclusions without scheduling them.
Joint search retains the existing copy-count and maximum-25-hypothesis policy.
Every `RUN_PHASE3_FIRST_COPY_PHASER` item includes its own crystal ID, exact
MTZ, selected hypothesis, complete model registry, preflight records, shared
catalogue/provider, and Phenix installation identity. The existing
`genome-to-diffraction mr first-copy` adapter constructs the external command;
Nextflow's complete-item hash is the cache key.

`BUILD_PHASE3_MR_SEED_REVIEW` groups only the corresponding crystal's results,
retains a typed empty/no-model branch, and invokes the existing
`genome-to-diffraction review build-mr-seed` adapter. Each crystal receives its
own independent review package and an empty approval template. No decision,
identity claim, composition claim, or unknown-dataset permission is fabricated.

## Failures and qualification

Malformed dispatch, inconsistent funnel/hypothesis inputs, and a changed
declared attempt cap fail before scientific promotion. A no-hypothesis branch
still produces its own review checkpoint. The dedicated
`pixi run --locked phase3-multicrystal-stub` gate requires exactly one shared
catalogue, one shared provider, three dispatch tasks, three evidence-bound
funnels, three
first-copy tasks, and three separate unapproved review packages; every task
and published output must remain unchanged on cached resume. The same gate
checks that `phase3_application.nf` selects only the canonical Phase III branch
and never schedules the legacy one-crystal selector.

The same gate runs an actual independently staged three-crystal reviewed
fixture: one validation task, three dispatches, two proceeding funnels/Phaser
tasks/MR-seed packages, one held output, and no scientific task for the held
crystal. Every reviewed task and output remains byte-identical on cached resume.
Focused mutations reject missing crystals, changed frozen MTZ bytes, and
altered canonical decisions before any reviewed output is published.

This local qualification uses synthetic fixtures only. Fixed unknown profiles,
real provider/Phenix execution, malformed-sibling isolation, and downstream
multi-crystal review continuation remain separate Phase III gates.
