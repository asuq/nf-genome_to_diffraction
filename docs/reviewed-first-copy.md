# Reviewer-selected first-copy alternatives

## Scientific scope

RF-G2 permits a reviewer to select exact model-backed alternatives after a
completed A-search result is rejected or left unresolved (`reject` or `defer`).
Packing is not a prerequisite or a veto: a packed but rejected result can
trigger this route. Failed or incomplete tasks remain incomplete evidence and
cannot supply its negative scientific trigger.

Selections can include cap-deferred candidates, zero empirical copy-frequency
states and non-retained members of the complete physical Matthews range.
An out-of-window solvent fraction remains reviewable, not physically impossible.
Each selected hypothesis still searches **one** copy; its expected copy count
sets the sequence-derived composition. No selection approves an A seed.

This is separate from automatic complete-zero-pack localisation reopening.
It does not broaden that trigger or restart an operator-cancelled programme.

## Inputs and authority

The runtime `reviewed-first-copy-selection` contract is
`schemas/v2/reconsideration.py:ReviewedFirstCopySelection`. Construct a selection
with its `from_content` method so the content ID is derived, never guessed.
The selection records:

- exact source commit/tree, crystal and owned parent registry;
- parent A-package ID and manifest checksum, parent decisions checksum and
  parent funnel manifest checksum;
- sorted rejected/deferred solution IDs;
- sorted unique `(sequence_group_id, model_id, matthews_hypothesis_id)` targets;
- reviewer, timestamp, reason and an explicit budget of at most 25 attempts.

Use the original coordinate sources, processed-model batches, preparation
manifests, coordinate mappings, sequence groups, source records, full Matthews
rows, preflight, configuration and localisation bundle. They must match the
owned parent byte-for-byte; the prepared all-model universe is also checked.
No missing model or invalid physical state is fabricated into an executable one.

Pass the normal Phase III `ranking diverse-first-copy-funnel` inputs, including
`--require-localisation-policy`, plus all five authority options:

```text
--review-selection /absolute/review/selection.json
--confirmed-review-selection-sha256 INDEPENDENTLY_CONFIRMED_SHA256
--owned-parent-registry /absolute/parent/owned_registry
--parent-funnel /absolute/parent/funnel
--parent-a-decisions /absolute/review/parent_decisions.json
```

The selection checksum must be independently confirmed after review. Omitting
part of this authority set, selecting stale/foreign/duplicate targets, exceeding
the configured or explicit budget, or implicitly rescheduling an already
attempted hypothesis fails. No truncation, implicit evidence reuse or failed-cache
reuse occurs. A later review cycle carries the earlier scheduled inventory
forward and cannot forget previous attempts.

## Execution and outputs

The funnel emits `reviewed-first-copy-funnel-v1`: the existing model registry,
aggregate and individual hypothesis/resource files, selected authority and
conservation counts. These distinguish total model-backed physical hypotheses,
previously scheduled, available deferred, selected and remaining deferred states,
with parent completed/incomplete/selected-packed counts. New attempts initially
remain `not_executed`, with no A approval.

Independently confirm that funnel's manifest checksum, then use the dedicated
typed Nextflow entry point with the site's existing executor configuration:

```bash
pixi run --locked nextflow run reviewed_first_copy.nf \
  --funnel /absolute/reviewed/funnel \
  --confirmed_funnel_sha256 INDEPENDENTLY_CONFIRMED_FUNNEL_SHA256 \
  --sequence_groups /absolute/catalogue/sequence_groups.jsonl \
  --source_records /absolute/catalogue/source_records.jsonl \
  --matthews /absolute/matthews/hypotheses.jsonl \
  --preflight /absolute/preflight/mtz_preflight.jsonl \
  --pipeline_config /absolute/config.yaml \
  --crystal_directory /absolute/dispatched/crystal \
  --execution_identity /absolute/parent/phase3_execution_identity.json \
  --phenix_manifest /absolute/software/phenix.json \
  --owned_run_id DISTINCT_REVIEWED_RUN_ID \
  --outdir /absolute/reviewed/results
```

The crystal directory contains the unchanged `input.mtz` and
`phase3_diffraction_selection.json`. The gate checks source input digests,
selected hypothesis/resource inventories and individual files, registry/model
bytes, crystal/diffraction binding and the parent's declared Phenix tool digests
and versions. Its deep-cached dispatch is emitted only after validation. The
existing MR adapter then verifies the licensed runtime before executing it.
Nextflow 26.04.6 and the locked Python 3.14 environment are required; no Phenix
installation or download is performed by this entry point.

The route uses the existing `RUN_PHASE3_FIRST_COPY_PHASER`,
`BUILD_PHASE3_MR_SEED_REVIEW` and `BUILD_PHASE3_OWNED_A_REVIEW_PACKAGE` processes.
Each selected hypothesis is an independent task. Review reports retain completed
hits/no-hits separately from failed or incomplete results and label adapter
attempt counts explicitly; they do not equate a result record with native success.
The owned A checkpoint requires a new human decision before any copy completion.

Remote execution still requires its separately approved clean immutable source
and reviewed HPC profile. This entry point alone does not grant remote authority.

## Qualification

The focused synthetic test uses the actual Matthews enumerator, production
funnel, first-copy adapter and review builder: an unobserved 67-copy expectation
outside the retained top three remains a one-copy search after rejection or
deferral of a packed result. The runtime is deliberately fake, not native evidence.
Drift, duplicate/budget, failed-parent and incomplete-result cases fail or remain
incomplete as appropriate. A real Nextflow stub runs the non-stubbed gate,
schedules one MR task and the two existing review tasks; a bad confirmation
schedules no MR. The owned package in stub mode is explicitly non-scientific.

Native known-control qualification and the full RF integration milestone remain
required before the release gates can close. Tests are
`test_reviewed_first_copy_selection.py`, `test_reviewed_first_copy_nextflow.py`
and the repository task-contract checks.
