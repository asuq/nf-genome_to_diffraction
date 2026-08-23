# Phase III file-based review contract

## Scope

The schema-v2 `phase3-review-decisions` contract records the four human
checkpoints required by the unknown-crystal workflow without prompting inside a
scheduled task. One decision file covers exactly one checkpoint and one review
package. It binds `owned_parent_run_id`, `review_package_id`, the package-manifest
SHA-256, and every crystal/item decision into `decision_file_id`.

The identifier is derived from RFC-8785 canonical typed content. It is not the
byte checksum of the entered TSV. A future staging adapter must independently
verify parent-run ownership, the package manifest and assets, target membership,
the transported decision-file checksum, and whether the decision timestamp is
not older than the package. Those checks are deliberately not claimed here.

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
