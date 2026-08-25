"""Tests for the cap-independent Phase III processed-model universe."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from genome_to_diffraction.ids import sequence_digest
from genome_to_diffraction.model_registry import (
    AllEligibleModelRegistryError,
    ModelUnavailableReason,
    ValidatedProcessedModelInput,
    build_all_eligible_model_registry,
    load_all_eligible_model_registry,
)
from genome_to_diffraction.schemas.results import (
    CoordinateSourceRecord,
    ProcessedModelRecord,
    SequenceGroupRecord,
)

REPOSITORY = Path(__file__).resolve().parents[2]
STUB_PREPARATION = REPOSITORY / "tests/fixtures/stubs/predicted_model_preparation"


def _group(sequence: str) -> SequenceGroupRecord:
    digest = sequence_digest(sequence)
    return SequenceGroupRecord(
        schema_version="1.0",
        sequence_group_id=f"seq_{digest}",
        sha256=digest,
        sequence=sequence,
        length_aa=len(sequence),
        molecular_mass_da=436.4375,
        mass_method="synthetic registry test mass",
        residue_policy="standard_exact",
        source_record_count=1,
    )


def _coordinate(group: SequenceGroupRecord, accession: str) -> CoordinateSourceRecord:
    return CoordinateSourceRecord(
        schema_version="1.0",
        coordinate_id=f"coord_{group.sha256}",
        provider="afdb",
        provider_accession=accession,
        retrieval_date=datetime(2026, 8, 23, tzinfo=UTC),
        source_release="v6",
        coordinate_path=f"coordinates/{group.sha256}.cif",
        coordinate_sha256=group.sha256,
        source_sequence_sha256=group.sha256,
        confidence_summary={"mean_plddt": 90.0},
        license_or_provenance="synthetic AlphaFold DB registry fixture",
    )


def _template_model() -> ProcessedModelRecord:
    return ProcessedModelRecord.model_validate_json(
        (STUB_PREPARATION / "processed_models.jsonl").read_text(encoding="utf-8")
    )


def _model_input(
    *,
    model: ProcessedModelRecord,
    coordinate: CoordinateSourceRecord,
    group: SequenceGroupRecord,
) -> ValidatedProcessedModelInput:
    return ValidatedProcessedModelInput(
        model=model,
        coordinate=coordinate,
        sequence_group=group,
        model_path=STUB_PREPARATION / "models/stub.pdb",
        retained_fraction=1.0,
    )


def _two_group_inputs() -> tuple[
    tuple[ValidatedProcessedModelInput, ...],
    tuple[SequenceGroupRecord, ...],
]:
    group_a = _group("ACDE")
    group_b = _group("FGHI")
    coordinate_a = _coordinate(group_a, "AF-A-F1")
    coordinate_b = _coordinate(group_b, "AF-B-F1")
    template = _template_model()
    model_a = template.model_copy(
        update={
            "model_id": f"model_{1:064x}",
            "coordinate_id": coordinate_a.coordinate_id,
            "full_candidate_sequence_group_id": group_a.sequence_group_id,
        }
    )
    model_b = template.model_copy(
        update={
            "model_id": f"model_{2:064x}",
            "coordinate_id": coordinate_b.coordinate_id,
            "full_candidate_sequence_group_id": group_b.sequence_group_id,
        }
    )
    return (
        (
            _model_input(model=model_a, coordinate=coordinate_a, group=group_a),
            _model_input(model=model_b, coordinate=coordinate_b, group=group_b),
        ),
        (group_a, group_b),
    )


def test_b_model_outside_twenty_five_item_a_shortlist_remains_searchable(
    tmp_path: Path,
) -> None:
    group_a = _group("ACDE")
    group_b = _group("FGHI")
    group_without_model = _group("KLMN")
    coordinate_a = _coordinate(group_a, "AF-A-F1")
    coordinate_b = _coordinate(group_b, "AF-B-F1")
    template = _template_model()
    inputs = tuple(
        _model_input(
            model=template.model_copy(
                update={
                    "model_id": f"model_{index:064x}",
                    "coordinate_id": coordinate_a.coordinate_id,
                    "full_candidate_sequence_group_id": group_a.sequence_group_id,
                }
            ),
            coordinate=coordinate_a,
            group=group_a,
        )
        for index in range(1, 26)
    )
    b_model = template.model_copy(
        update={
            "model_id": f"model_{26:064x}",
            "coordinate_id": coordinate_b.coordinate_id,
            "full_candidate_sequence_group_id": group_b.sequence_group_id,
        }
    )
    b_input = _model_input(
        model=b_model,
        coordinate=coordinate_b,
        group=group_b,
    )
    a_search_shortlist = tuple(item.model.model_id for item in inputs)

    output = build_all_eligible_model_registry(
        models=(*inputs, b_input),
        sequence_groups=(group_a, group_b, group_without_model),
        output_directory=tmp_path / "all models",
    )
    registry = load_all_eligible_model_registry(output.registry_json)
    b_lookup = registry.lookup(group_b.sequence_group_id)

    assert len(a_search_shortlist) == 25
    assert b_model.model_id not in a_search_shortlist
    assert output.registry.model_count == 26
    assert b_lookup.available
    assert [item.model_id for item in b_lookup.models] == [b_model.model_id]
    assert b_lookup.unavailable_reason is None
    missing_lookup = registry.lookup(group_without_model.sequence_group_id)
    assert missing_lookup.unavailable_reason is (
        ModelUnavailableReason.NO_ELIGIBLE_MODEL
    )


def test_registry_order_and_identity_ignore_input_permutation(tmp_path: Path) -> None:
    inputs, groups = _two_group_inputs()
    first = build_all_eligible_model_registry(
        models=inputs,
        sequence_groups=groups,
        output_directory=tmp_path / "first",
    )
    second = build_all_eligible_model_registry(
        models=tuple(reversed(inputs)),
        sequence_groups=tuple(reversed(groups)),
        output_directory=tmp_path / "second",
    )

    assert first.registry.registry_id == second.registry.registry_id
    assert first.registry_json.read_bytes() == second.registry_json.read_bytes()
    assert first.processed_models_jsonl.read_bytes() == (
        second.processed_models_jsonl.read_bytes()
    )


def test_registry_publishes_only_canonical_schema_v2_authority(tmp_path: Path) -> None:
    inputs, groups = _two_group_inputs()

    output = build_all_eligible_model_registry(
        models=inputs,
        sequence_groups=groups,
        output_directory=tmp_path / "registry",
    )

    assert output.registry.schema_version == "2.0"
    assert {path.name for path in output.registry_directory.iterdir()} == {
        "all_model_registry.json",
        "processed_models.jsonl",
        "models",
    }
    assert not (output.registry_directory / "model_preparation_manifest.json").exists()


def test_source_and_model_mutations_change_registry_identity(tmp_path: Path) -> None:
    inputs, groups = _two_group_inputs()
    baseline = build_all_eligible_model_registry(
        models=inputs,
        sequence_groups=groups,
        output_directory=tmp_path / "baseline",
    )
    source_mutation = inputs[0].coordinate.model_copy(update={"source_release": "v7"})
    changed_source_inputs = (
        _model_input(
            model=inputs[0].model,
            coordinate=source_mutation,
            group=inputs[0].sequence_group,
        ),
        inputs[1],
    )
    changed_source = build_all_eligible_model_registry(
        models=changed_source_inputs,
        sequence_groups=groups,
        output_directory=tmp_path / "changed source",
    )
    model_mutation = inputs[0].model.model_copy(
        update={"estimated_coordinate_error": 0.42}
    )
    changed_model_inputs = (
        _model_input(
            model=model_mutation,
            coordinate=inputs[0].coordinate,
            group=inputs[0].sequence_group,
        ),
        inputs[1],
    )
    changed_model = build_all_eligible_model_registry(
        models=changed_model_inputs,
        sequence_groups=groups,
        output_directory=tmp_path / "changed model",
    )

    assert baseline.registry.registry_id != changed_source.registry.registry_id
    assert baseline.registry.registry_id != changed_model.registry.registry_id


def test_lookup_returns_typed_provider_variant_and_unknown_reasons(
    tmp_path: Path,
) -> None:
    inputs, groups = _two_group_inputs()
    output = build_all_eligible_model_registry(
        models=inputs,
        sequence_groups=groups,
        output_directory=tmp_path / "registry",
    )
    registry = load_all_eligible_model_registry(output.registry_json)

    assert (
        registry.lookup(groups[0].sequence_group_id, provider="pdb").unavailable_reason
        is ModelUnavailableReason.PROVIDER_UNAVAILABLE
    )
    assert (
        registry.lookup(
            groups[0].sequence_group_id, variant_type="experimental_full"
        ).unavailable_reason
        is ModelUnavailableReason.VARIANT_UNAVAILABLE
    )
    assert registry.lookup(f"seq_{'f' * 64}").unavailable_reason is (
        ModelUnavailableReason.SEQUENCE_GROUP_NOT_REGISTERED
    )


def test_checksum_mismatch_fails_before_registry_publication(tmp_path: Path) -> None:
    inputs, groups = _two_group_inputs()
    changed_model = tmp_path / "changed.pdb"
    changed_model.write_text("changed\n", encoding="utf-8")
    invalid = ValidatedProcessedModelInput(
        model=inputs[0].model,
        coordinate=inputs[0].coordinate,
        sequence_group=inputs[0].sequence_group,
        model_path=changed_model,
        retained_fraction=1.0,
    )
    output = tmp_path / "registry"

    with pytest.raises(AllEligibleModelRegistryError, match="checksum mismatch"):
        build_all_eligible_model_registry(
            models=(invalid, inputs[1]),
            sequence_groups=groups,
            output_directory=output,
        )

    assert not output.exists()
