# Phase III component candidate generation

## Scientific boundary

`build_component_expansion_inputs` is the deterministic join between the
complete protein catalogue and the schema-v2 B--F composition planner. It emits
one retained row for every catalogue sequence group not already represented in
each packed parent. It does not run a structural search, Phaser, refinement,
localisation tool, or remote service, and it cannot promote identity or
composition support.

The join consumes the checksum-verified all-eligible model registry, never the
bounded A execution shortlist. A sequence group with no eligible model remains
in the inventory with a typed non-coordinate placeholder; registry binding later
resolves all four copy hypotheses to `no_eligible_model`. The placeholder cannot
be executed and is not model evidence.

## Exact inputs and output

One generation call requires:

- one to three unbound `ParentExpansionInput` records for packed states at the
  same crystal, diffraction dataset, and component depth;
- the complete, duplicate-free `SequenceGroupRecord` catalogue, which must
  match both the localisation policy and all-model registry exactly;
- one `CatalogueLocalisationWavePolicy`, its exact `ActiveWaveCompletion`, and
  the `LocalisationReopenPlan` derived from that same pair;
- one typed schema-v2 `GelEvidenceManifest`, which may be empty;
- one `ParentMatthewsContext` per parent with ASU volume, broad solvent bounds,
  source-evidence checksum, and the fixed transparent prior backend;
- optional parent/model-specific `ParentModelRankingEvidence` with separate
  model-quality and structural-diversity levels, policy version, and source
  checksum; and
- the local `all_model_registry.json`, including its checksum-bound records,
  compatibility manifest, and model files.

The output `ComponentExpansionInputInventory` carries the complete derived rows,
four `TotalCompositionCopyEvidence` records per row, every source identity, the
exact catalogue-group list and each parent's represented/candidate partition,
catalogue/parent/row/model/wave/copy counts, and the literal selection boundary
`scheduling_prior_only_no_identity_or_composition_support`. `inventory_id` is
the content-addressed cache key. `ComponentExpansionInputGeneration.candidates`
is the exact ordered tuple accepted by `CompositionExpansionRequest`;
`as_request()` constructs the default bounded unbound request for subsequent
registry verification and planning.

## Evidence interpretation and deterministic order

For each parent, already represented exact sequence-equivalence groups are
counted and omitted from expansion. Every other catalogue group is retained.
Candidate ranks use the declared lexicographic order:

1. localisation wave;
2. SDS-PAGE monomer-mass evidence;
3. native-PAGE total-composition evidence;
4. total-composition Matthews evidence;
5. model quality;
6. structural diversity;
7. best retained Matthews prior; and
8. exact sequence-group ID.

Soluble localisation is supporting. Explicit membrane, surface, extracellular,
or transmembrane localisation is conflicting for ranking and is held from the
first wave, but the row is retained. Unknown, conflicting, and failed
localisation is neutral and first-wave eligible. An excluded group becomes wave
eligible only when the supplied completion covers every first-wave group with
no failure or omission and records zero packed groups. Reopening changes only
`localisation_wave_eligible`; it does not rewrite the localisation evidence
level or create a reviewer decision.

SDS-PAGE compares the sequence-derived monomer-mass interval with each typed
observation interval. Native PAGE compares every physically eligible
parent-plus-candidate-copy total-mass interval. A dominant reducing SDS band or
dominant native band is supporting, another interval overlap is compatible,
and typed evidence with no overlap is conflicting. An empty manifest or
unavailable mass is neutral. Gel evidence affects rank only and never physical
eligibility or oligomeric interpretation.

For each candidate, copies 1--4 use
`parent physical mass + candidate sequence mass * copy count`. The recorded ASU
volume gives Matthews-coefficient and solvent-fraction bounds. `plausible` and
`review` copies remain physically eligible; only `impossible` is excluded. A low
prior alone never excludes a copy. Exact, bounded, and unavailable sequence
masses remain distinct. Mass-unavailable groups retain four explicit unassessed
copy records and zero eligible copies rather than receiving a fabricated mass.
The planner reports these as `unsearchable_physical_evidence`; it may use
`excluded_physical_impossible` only for a completed physical assessment.

Model selection considers every eligible registry model. Explicit quality and
diversity levels precede retained fraction, estimated coordinate error, quality
flags, provider, variant, accession, and model ID. Missing quality/diversity
evidence is neutral. This ordering selects one exact model request per
parent/group while retaining valid models that were outside any A shortlist.

## Failure semantics, status, and tests

Catalogue/localisation/registry coverage mismatch, stale sequence identity,
missing or duplicate parent Matthews contexts, model-evidence checksum mismatch,
non-contiguous parents, a forged or mismatched reopen decision, and any registry
or model checksum failure raise `CandidateGenerationError` before a planner
request is emitted. Missing gel, model-ranking, model, or usable mass evidence
is a typed scientific state and not an execution failure.

The current v1 `ActiveWaveCompletion` and `LocalisationReopenPlan` records are
catalogue-wide and do not themselves carry crystal, parent-beam, or depth
fields. This generator binds their exact content IDs into a crystal/parent/depth
inventory and rejects an internally mismatched pair. Before live application
wiring, the upstream result checksums must also be bound to that execution
item; this contract-only slice does not claim that live source qualification.

`tests/unit/test_component_candidate_generation.py` proves input-order-invariant
ranking, exact retained counts, four copy records per row, distinct parent copy
eligibility, bounded and unavailable mass retention, a B model outside the
25-model A set, quality/diversity model selection, excluded-row retention,
neutral unknown/conflicting/failed localisation, neutral missing gel, exact
zero-pack reopen gating, registry-bound planner compatibility, and no support
promotion. It also proves that missing physical evidence cannot be relabelled
as physical impossibility. The broader composition contract, planner, registry,
execution-input, and selected-attempt suites protect compatibility. No Nextflow,
Phaser, unknown-crystal profile, remote sequence submission, or HPC run is part
of this slice.
