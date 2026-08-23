# Phase III unknown-pass terminal status contract

Status: local schema-v2 foundation; workflow and report wiring remain pending.

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

Focused mutation and mixed-panel coverage is in
`tests/unit/test_unknown_pass1_assessment_v2.py`. Live unknown workflow wiring,
review-package generation, provider composition, and report publication remain
separate milestones.
