# Phase III all-eligible model registry

## Purpose and boundary

The all-eligible registry is the immutable model universe for later B--F
composition planning. It is deliberately separate from the bounded A-search
execution list: changing a first-copy cap may change scheduled A hypotheses but
must not remove a valid model from this registry or change its identity.

The registry does not rank candidates, calculate composition plausibility, run
Phaser, infer identity, or make a scientific claim. It consumes only validated
catalogue sequence groups and prepared model/source records. Crystal-specific
Matthews evidence, localisation evidence, diffraction data, and execution caps
are not registry inputs.

## Inputs and outputs

Each model input binds one `ProcessedModelRecord` to its
`CoordinateSourceRecord`, catalogue `SequenceGroupRecord`, checksum-verified
model file, retained fraction, and, for PDB-derived models, the exact
`CoordinateHitMappingRecord`. Predicted AFDB and ESM Atlas models require exact
source-sequence mapping. Unsupported providers or inconsistent mappings fail
before publication.

The output directory contains:

- `all_model_registry.json`: schema-v2 inventories and the `allmodelreg_...`
  content identity;
- `processed_models.jsonl`: every eligible record in canonical deterministic
  order;
- `model_preparation_manifest.json`: a deterministic schema-v1 compatibility
  manifest for existing Phaser and partner-planning readers; and
- `models/<digest-prefix>/<sha256>.pdb`: deduplicated content-addressed model
  bytes.

Every catalogue sequence group has one inventory. An empty inventory is a valid
scientific state with reason `no_eligible_model`. Lookup additionally returns
typed `sequence_group_not_registered`, `provider_unavailable`, and
`variant_unavailable` outcomes. These outcomes do not fabricate a model and are
not execution failures.

## Identity, failure semantics, and tests

The registry identity covers deterministic sequence inventories and the
checksums of the complete processed-model records, coordinate-source records,
optional PDB mappings, copied model bytes, canonical JSONL, and compatibility
manifest. Input permutation is normalised. Source or model mutation changes the
identity; A-search cap mutation cannot because caps are absent from the payload.

No external command or runtime version is required. Duplicate identities,
invalid records, unsupported mappings/providers, unsafe paths, and checksum
mismatches raise `AllEligibleModelRegistryError`. The loader revalidates the
content identity and all retained records and files before enabling lookup.

Focused coverage in `tests/unit/test_all_eligible_model_registry.py` proves
ordering, mutation, checksum, typed absence, and lookup behaviour. The diverse
funnel regression in `tests/unit/test_ranking_funnel.py` proves that changing
the A execution cap changes scheduled hypotheses while leaving the registry ID
and bytes unchanged.
