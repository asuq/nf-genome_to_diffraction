# Phase III multi-crystal first-copy application

## Purpose and activation

The historical application selects exactly one manifest-owned crystal before
first-copy molecular replacement. Explicit Phase III mode activates the
multi-crystal path only when `analysis_stage=first_copy` and
`phase3_joint_first_copy=true`; historical single-crystal, heteromer-control,
approved-seed, and refinement execution remain unchanged.

## Inputs and execution boundaries

One previously validated crystal manifest, preflight inventory, catalogue,
provider registration, predicted and experimental model preparations, Matthews
records, pipeline configuration, and verified Phenix manifest are shared.
`CRYSTAL_FANOUT_WORKFLOW` emits one manifest-owned, checksum-verified MTZ item
per crystal; catalogue and provider preparation remain single shared tasks.

`BUILD_DIVERSE_FIRST_COPY_FUNNEL` emits its crystal identity with the existing
funnel and publishes Phase III outputs under a crystal-qualified directory.
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
catalogue, one shared provider, three dispatch tasks, three funnels, three
first-copy tasks, and three separate unapproved review packages; every task
and published output must remain unchanged on cached resume. The same gate
checks that the ordinary `main.nf` application selects the explicit Phase III
branch instead of the legacy one-crystal selector.

This local qualification uses synthetic fixtures only. Fixed unknown profiles,
staged crystallographic review enforcement, real provider/Phenix execution,
malformed-sibling isolation, and downstream multi-crystal review continuation
remain separate Phase III gates.
