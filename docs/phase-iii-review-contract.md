# Phase III file-based review contract

## Scope

The schema-v2 `phase3-review-decisions` contract records the four human
checkpoints required by the unknown-crystal workflow without prompting inside a
scheduled task. One decision file covers exactly one checkpoint and one review
package. It binds `owned_parent_run_id`, `review_package_id`, the package-manifest
SHA-256, and every crystal/item decision into `decision_file_id`.

The identifier is derived from RFC-8785 canonical typed content. It is not the
byte checksum of the entered TSV. The local staging adapter independently
verifies the caller-supplied owned parent run/profile/phase, exact package
manifest, target membership, transported decision-file checksum, canonical
content identifier, and whether every decision timestamp is not older than the
package.

Historical `review-decisions` schema-v1 files and their `mr_seed` and
`sequence_candidate` semantics are unchanged.

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

This slice defines no Nextflow process, profile, remote staging operation, or
review-package generator.

## Local staging boundary

`stage_phase3_review_decisions` accepts one caller-verified
`OwnedPhaseIIIParentRun`, the expected checkpoint, a strict schema-v2 review
package manifest, a JSON or TSV decision file, and an independently confirmed
SHA-256 for the exact decision-file bytes. The package manifest must bind:

- `review_package_id` and checkpoint;
- `owned_parent_run_id`, `parent_profile`, and `parent_phase`;
- timezone-aware `created_at`; and
- the complete permitted `(crystal_id, item_id)` target set.

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
files are not copied. The caller remains responsible for deriving the owned
parent reference from its trusted local run registry. This local slice does not
authenticate a remote run, generate review packages, or add a Nextflow/HPC
profile.
