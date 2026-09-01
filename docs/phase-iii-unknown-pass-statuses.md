# Phase III unknown-pass terminal status contract

Status: local schema-v2 assessment and checksum-closed collector foundation;
live workflow wiring remains pending.

## Purpose and boundary

`UnknownPass1CrystalAssessment` content-binds one crystal's terminal execution
evidence, optional solution evidence, and exact human-review package/decision
identities. It runs no provider, Phaser, refinement, map, report, Nextflow, or
remote-service command. Its cache key is the full canonical `assessment_id`.

The scientific endpoint vocabulary is exactly:

- `credible_single_component_solution`;
- `credible_partial_or_residual`;
- `candidate_shortlist_no_credible_mr_solution`;
- `no_supported_catalogue_candidate`;
- `mtz_or_symmetry_review_required`;
- `execution_failure`; and
- `insufficient_evidence`.

Scientific no-hit is a successful terminal analysis:
`completed_no_hit` becomes `no_supported_catalogue_candidate` after an exact
crystallographic `proceed` decision. A classified tool, parser, input-contract,
or infrastructure failure becomes `execution_failure`; it is not rewritten as
a scientific no-hit.

## Promotion and failure semantics

A credible single-component or partial/residual endpoint requires all of the
following to match the assessment crystal and retained state:

- one crystallographic review package/decision with `proceed`;
- one A-seed review package/decision with `approve`;
- one composition review package/decision with `approve` for no detected
  residual content or `retain_partial` for present/suspected residual content;
- supported requested/observed copies with equal non-zero counts and exact
  evidence checksum;
- packing, combined coordinates, completed refinement, refined MTZ, and their
  evidence checksums; and
- parsed final Rwork and Rfree with their source checksum.

The contract retains package-side and decision-side checkpoint, crystal, and
item identities separately. Missing, ambiguous, contradictory, or cross-crystal
evidence becomes `insufficient_evidence`; an exact crystallographic `hold`
becomes `mtz_or_symmetry_review_required`. Sequence/locus promotion is outside
this pass-1 composition-status contract and still requires its separate review
checkpoint.

`UnknownPass1PanelSummary` embeds exactly three complete assessments from one
owned execution. Its `panel_id` binds every assessment and exact terminal status.
The panel has only `terminal_complete`, never a panel-wide scientific status, so
a credible sibling cannot promote a no-hit, held, or failed crystal.

## Local collection boundary

`collect_unknown_pass1_panel` accepts exactly the three fixed operator-crystal
assessment records and an explicit per-crystal command/result/evidence
allow-list. It reloads each assessment through strict JSON-mode validation,
re-derives its content identifier and scientific status, requires one shared
owned-run and execution identity, and requires every checksum referenced by the
assessment to occur in that crystal's allow-list.

Only checksum- and size-matched regular non-symlink files below the input root
are copied. Missing, duplicate, cross-crystal, unsafe, mutated, or symlinked
evidence and a non-empty output directory fail before publication. A successful
collection contains canonical assessments JSONL, the panel summary, one
per-crystal checksum manifest, one cross-crystal checksum manifest, the exact
copied allow-list, and a static HTML table. The HTML explicitly states that the
unknowns are exploratory rather than validation and mirrors each typed endpoint
without adding an identity or composition claim.

Assessment mutation and mixed-panel coverage is in
`tests/unit/test_unknown_pass1_assessment_v2.py`. Collector coverage in
`tests/unit/test_unknown_pass1_collection.py` includes credible/no-hit/failure
and uncertain mixed panels, missing and cross-crystal evidence, checksum drift,
unsafe paths, symlinks, non-empty output, and byte-identical input permutation.
Live unknown workflow wiring, review-package generation, provider composition,
and remote collection remain separate milestones.
