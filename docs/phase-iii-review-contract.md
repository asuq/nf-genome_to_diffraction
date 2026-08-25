# Phase III file-based review contract

## Scope

The schema-v2 review-package and `phase3-review-decisions` contracts record the
evidence boundary and the four human checkpoints required by the unknown-crystal
workflow without prompting inside a scheduled task. One decision file covers
exactly one checkpoint and one review package. It binds `owned_parent_run_id`,
`review_package_id`, the package-manifest SHA-256, and every crystal/item decision
into `decision_file_id`.

The identifier is derived from RFC-8785 canonical typed content. It is not the
byte checksum of the entered TSV. The local staging adapter independently
verifies the caller-supplied owned parent run/profile/phase, exact package
manifest, target membership, transported decision-file checksum, canonical
content identifier, and whether every decision timestamp is not older than the
package.

`phase3-review-package-v1` preserves existing `crystallographic` and `a_seed`
packages without changing their content identifiers. The same generator emits
`phase3-review-package-v2` for `composition` and `sequence` checkpoints, using
each checkpoint's existing restricted decision vocabulary. Historical
`review-decisions` schema-v1 files and their `mr_seed` and `sequence_candidate`
semantics are unchanged.

## Review-package generator

`build_phase3_review_package` accepts exactly one checkpoint, one crystal, one
owned parent run/profile/phase, one full `phase3exec_` execution identity, a
complete non-empty target-item set, and an explicit evidence allow-list. Evidence
sources have a unique logical role and a canonical path relative to one input
root. Absolute paths, parent traversal, non-portable path segments, duplicate
roles or paths, symlinks below the root, missing files, and non-regular files fail
before publication.

The output is an existing empty, non-symlink directory. The generator builds and
validates a private sibling directory, then replaces the empty destination in one
atomic rename. It never merges with or overwrites a non-empty package. Each source
file is streamed into the private package and checksummed, then checksummed again
at its source; mutation during the snapshot fails and leaves the destination
empty.

Every successful package contains exactly:

- `phase3_review_package_manifest.json`;
- `review_targets.tsv`; and
- the explicitly allowed files below `evidence/`, retaining their safe relative
  input paths.

The generated table contains one canonically ordered row for every target and the
checkpoint-specific decision vocabulary. Its decision fields are blank. It is an
inspection worksheet, not a valid `phase3-review-decisions` file by itself; the
operator decision adapter also requires the package ID and an independently
calculated manifest-file SHA-256.

The path-free manifest records `phase3-review-package-v1` for existing
crystallographic/A-seed checkpoints or `phase3-review-package-v2` for
composition/sequence checkpoints, together with the exact parent and execution
identities, checkpoint, crystal, creation time, all permitted targets, every
evidence role/relative path/SHA-256/size, and the generated table's
SHA-256/size/row coverage. `package_content_sha256` is the RFC-8785 digest of the
complete evidence/table inventory. `review_package_id` is derived from the full
canonical manifest except for that identifier, so any parent, execution, target,
file, ordering, or timestamp change invalidates it. Package validation refuses
unlisted or missing files, symlinks, checksum/size drift, and incomplete or
reordered table targets.

Only relative paths appear in generated metadata. Evidence payloads are copied
byte-for-byte rather than rewritten; callers must select already review-safe
artefacts and must not allow an artefact containing private paths or credentials
into the explicit evidence allow-list.

## Trusted local owned-run registry

`register_phase3_owned_run` is the local trust boundary used before decision
staging. The caller supplies one verified `completed_success` parent run, its
exact schema-v2 execution identity, one or more already generated review
packages, and an existing empty directory under caller-selected ignored storage.
The adapter does not inspect a directory name to infer ownership.

For every package it verifies the content-derived manifest, complete existing
file allow-list, parent run/profile/phase, execution identity, crystal,
checkpoint, creation chronology, and that the execution identity contains that
crystal's MTZ. It snapshots the package into a private directory, independently
revalidates source and copy, then atomically publishes one path-free
`phase3_owned_run_registry.json`, the canonical execution identity, and the
content-addressed package directories. The run record stores each package ID,
manifest checksum, and package-content digest; the package manifest remains the
authoritative per-file checksum and size allow-list.

Registries containing only historical crystallographic/A-seed packages retain
`phase3-owned-run-registry-v1` and their existing content identifiers. A registry
containing a composition or sequence package instead records
`phase3-owned-run-registry-v2`; a v1 registry cannot silently admit either newer
checkpoint. Package generation, registration, or staging never promotes a
composition claim or an exact sequence/locus assignment without independently
verified review evidence.

`resolve_phase3_owned_review_package` accepts only the registry directory plus
an exact run/crystal/checkpoint key. It first revalidates the canonical run and
execution records, exact top-level/package set, every package byte, and every
ownership binding. Only then does it return runtime-only paths and the existing
`OwnedPhaseIIIParentRun` needed by `stage_phase3_review_decisions`. Absolute
paths are never serialised. Missing, duplicate, stale, cross-run,
cross-crystal/checkpoint, mutated, symlinked, or unexpected package state fails
closed.

The registry is deliberately local and single-run. It does not authenticate a
remote scheduler, discover run directories, add an HPC profile, or define
unknown-screen execution.

## Unknown-screen crystallographic staging bridge

`stage_unknown_pass1_crystallographic_reviews` is the only local bridge from an
owned-run registry into the unknown-pass-1 screen builder. The caller supplies
one exact owned run ID and exactly three crystal-bound decision files with
independently confirmed checksums. The checkpoint is fixed to
`crystallographic`; no package path is accepted.

The bridge sorts the crystal IDs, resolves and fully revalidates each package
through `resolve_phase3_owned_review_package`, and passes only the resolved
canonical manifest and parent record to `PhaseIIIReviewStageRequest`. It stages
into a private sibling directory, revalidates the registry after all three
stages, and atomically publishes `stages/` plus the content-addressed,
path-free `unknown_pass1_review_stage_index.json`. The index binds the owned-run
registry and execution identities, exact parent run/profile/phase, and three
existing `UnknownPass1ReviewBinding` records in deterministic crystal order.

The unknown-screen builder accepts only that index path. It rejects extra,
missing, symlinked, renamed, mutated, cross-parent, or cross-execution stage
state before creating crystal or hypothesis items. Crystal-named storage is
only an indexed lookup key; ownership is never inferred from the directory
name.

## Unknown-screen A-seed staging bridge

`stage_unknown_pass1_selected_a_seeds` accepts one exact owned `unknown-screen`
parent run, an ASCII operator TSV, and the independently confirmed SHA-256 of
that TSV. The checkpoint is fixed to `a_seed`; the single crystal is inferred
from validated decision rows rather than accepted as a caller-selected value.
Its review package is resolved only through the checksum-closed owned-run
registry. An arbitrary package path cannot bypass ownership validation.

The existing review stager retains `approve`, `reject`, and `defer` outcomes,
rejects more than three approved A states per crystal, and publishes only its
canonical decision JSON plus stage manifest. Wrong parent/profile/checkpoint,
mutated package evidence, and mismatched independent checksums fail before
publication. The local CLI is `review stage-owned-a-seeds`; a remote fixed
profile and actual downstream same-component execution remain separate gates.

## Checkpoints and values

| `checkpoint` | Allowed `decision` values | Retained-state rule |
| --- | --- | --- |
| `crystallographic` | `proceed`, `hold` | No retained-state cap |
| `a_seed` | `approve`, `reject`, `defer` | At most three `approve` rows per crystal |
| `composition` | `approve`, `reject`, `defer`, `retain_partial` | At most three combined `approve` and `retain_partial` rows per crystal |
| `sequence` | `approve`, `retain_alternative`, `no_assignment` | No additional finalist cap is introduced by this contract |

Duplicate `(crystal_id, item_id)` targets fail, including two rows that try to
replace an earlier decision. Rejection, hold, deferral, partial retention,
alternative retention, and no assignment are valid scientific outcomes. They
are not execution failures.

## Operator TSV

The required columns are:

```text
checkpoint
owned_parent_run_id
review_package_id
review_package_manifest_sha256
crystal_id
item_id
decision
reviewer
reviewed_at
reason
```

An optional `comment` column may retain additional context. `reviewed_at` must
be timezone-aware and is normalised to UTC. `reason` is mandatory for every
decision so holds, negative outcomes, and promotions remain auditable. The four
package-level fields repeat on every TSV row and must be identical. The adapter
derives the canonical `decision_file_id`; JSON input must carry and validate the
same identifier.

This slice defines no Nextflow process, fixed HPC profile, remote staging
operation, or automatic scientific promotion.

## Local staging boundary

`stage_phase3_review_decisions` accepts one caller-verified
`OwnedPhaseIIIParentRun`, the expected checkpoint, a strict schema-v2 review
package manifest, a JSON or TSV decision file, and an independently confirmed
SHA-256 for the exact decision-file bytes. The package manifest must bind:

- content-derived `review_package_id`, `package_content_sha256`, and checkpoint;
- `owned_parent_run_id`, `parent_profile`, and `parent_phase`;
- one full Phase III execution identity and exactly one crystal;
- timezone-aware `created_at`;
- the complete permitted `(crystal_id, item_id)` target set;
- the explicit evidence checksum/size allow-list; and
- the generated review-table checksum and complete target coverage.

The stager fails with `PhaseIIIReviewStageError`, a typed input-contract error,
when any parent/package/checkpoint binding differs, the package-manifest SHA does
not match the decision file, the transported decision checksum differs from its
confirmation, a canonical decision identifier is stale, a target is absent, or
a review predates package creation. Loading the decision through the authoritative
schema-v2 contract also re-enforces duplicate refusal and checkpoint-specific
caps.

All validation finishes before publication. The output path must not already
exist. A successful stage contains exactly:

- `phase3_review_decision.json`, the deterministic typed JSON representation; and
- `phase3_review_stage_manifest.json`, which records the deterministic stage ID,
  parent/package bindings, source and canonical checksums, package creation time,
  decision count, and the two-file allow-list.

The source TSV/JSON, review package, package assets, and arbitrary neighbouring
files are not copied. Direct staging retains a caller-owned parent for focused
tests and other checkpoints; the unknown-pass-1 path instead uses the registry
bridge above. This local slice does not authenticate a remote run or add a
Nextflow/HPC profile.
