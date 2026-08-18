"""Focused Matthews JSONL identity and coverage contract tests."""

import hashlib
import json
from pathlib import Path

import pytest

from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.matthews.enumerate import (
    MatthewsInputError,
    MatthewsRequest,
    enumerate_matthews,
)
from genome_to_diffraction.schemas.results import (
    MtzPreflightRecord,
    PreflightDecision,
    SequenceGroupRecord,
    SourceProteinRecord,
)
from genome_to_diffraction.status import ExecutionStatus

REPOSITORY = Path(__file__).resolve().parents[2]


def _preflight(*, asu_volume_a3: float = 250_000) -> MtzPreflightRecord:
    return MtzPreflightRecord(
        schema_version="1.0",
        preflight_id=f"preflight_{int(asu_volume_a3)}",
        crystal_id="crystal_a",
        mtz_sha256="0" * 64,
        selected_observation_labels="I,SIGI",
        selected_observation_type="intensity",
        free_flag_labels="FreeR_flag",
        free_flag_status="present",
        unit_cell=(100, 100, 100, 90, 90, 90),
        space_group="P 21 21 21",
        general_position_multiplicity=4,
        cell_volume_a3=asu_volume_a3 * 4,
        asu_volume_a3=asu_volume_a3,
        resolution_low_a=20,
        resolution_high_a=2,
        reflection_count=1000,
        decision=PreflightDecision.PASS,
        execution_status=ExecutionStatus.COMPLETED_SUCCESS,
    )


def _group(sequence: str, *, source_record_count: int) -> SequenceGroupRecord:
    digest = hashlib.sha256(sequence.encode("ascii")).hexdigest()
    return SequenceGroupRecord(
        schema_version="1.0",
        sequence_group_id=f"seq_{digest}",
        sha256=digest,
        sequence=sequence,
        length_aa=len(sequence),
        molecular_mass_da=float(len(sequence) * 100),
        mass_method="synthetic",
        residue_policy="test",
        source_record_count=source_record_count,
    )


def _source(source_id: str, group: SequenceGroupRecord) -> SourceProteinRecord:
    return SourceProteinRecord(
        schema_version="1.0",
        source_record_id=source_id,
        catalogue_id="catalogue_a",
        original_protein_id=source_id,
        original_header=source_id,
        sequence_group_id=group.sequence_group_id,
        source_annotation_provider="synthetic",
    )


def _write_jsonl(path: Path, records: tuple[object, ...]) -> None:
    path.write_text(
        "".join(f"{canonical_json_text(record)}\n" for record in records),
        encoding="utf-8",
    )


def _request(
    root: Path,
    *,
    preflights: tuple[MtzPreflightRecord, ...],
    groups: tuple[SequenceGroupRecord, ...],
    sources: tuple[SourceProteinRecord, ...],
) -> MatthewsRequest:
    root.mkdir(parents=True, exist_ok=True)
    crystals = root / "crystals.json"
    crystals.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "crystals": [
                    {
                        "crystal_id": "crystal_a",
                        "mtz": "synthetic.mtz",
                        "catalogue_id": "catalogue_a",
                        "allow_remote_sequence_submission": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    config = root / "config.yaml"
    config.write_text(
        (REPOSITORY / "examples/config.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    preflight_path = root / "preflight.jsonl"
    group_path = root / "groups.jsonl"
    source_path = root / "sources.jsonl"
    _write_jsonl(preflight_path, preflights)
    _write_jsonl(group_path, groups)
    _write_jsonl(source_path, sources)
    return MatthewsRequest(
        crystal_manifest=crystals,
        pipeline_config=config,
        preflight_jsonl=preflight_path,
        sequence_groups_jsonl=group_path,
        source_records_jsonl=source_path,
        output_directory=root / "output",
        progress=False,
    )


def _assert_duplicate_rejected(
    tmp_path: Path,
    *,
    preflights: tuple[MtzPreflightRecord, ...],
    groups: tuple[SequenceGroupRecord, ...],
    sources: tuple[SourceProteinRecord, ...],
    expected: str,
) -> None:
    request = _request(
        tmp_path,
        preflights=preflights,
        groups=groups,
        sources=sources,
    )
    with pytest.raises(MatthewsInputError) as captured:
        enumerate_matthews(request)
    assert str(captured.value) == expected


@pytest.mark.parametrize("conflicting", (False, True))
def test_duplicate_preflight_crystal_id_is_order_independently_rejected(
    tmp_path: Path, conflicting: bool
) -> None:
    group = _group("A" * 100, source_record_count=1)
    first = _preflight()
    second = _preflight(asu_volume_a3=500_000) if conflicting else first
    for order, records in enumerate(((first, second), (second, first)), start=1):
        _assert_duplicate_rejected(
            tmp_path / str(order),
            preflights=records,
            groups=(group,),
            sources=(_source("source_a", group),),
            expected=(
                "duplicate MtzPreflightRecord.crystal_id 'crystal_a' at lines 1 and 2"
            ),
        )


def test_duplicate_error_reports_physical_jsonl_line_numbers(tmp_path: Path) -> None:
    group = _group("A" * 100, source_record_count=1)
    request = _request(
        tmp_path,
        preflights=(_preflight(), _preflight(asu_volume_a3=500_000)),
        groups=(group,),
        sources=(_source("source_a", group),),
    )
    records = request.preflight_jsonl.read_text(encoding="utf-8").splitlines()
    request.preflight_jsonl.write_text(
        f"\n{records[0]}\n\n{records[1]}\n", encoding="utf-8"
    )

    with pytest.raises(MatthewsInputError) as captured:
        enumerate_matthews(request)
    assert str(captured.value).endswith("'crystal_a' at lines 2 and 4")


@pytest.mark.parametrize("conflicting", (False, True))
def test_duplicate_sequence_group_id_is_order_independently_rejected(
    tmp_path: Path, conflicting: bool
) -> None:
    first = _group("A" * 100, source_record_count=1)
    second = (
        first.model_copy(update={"molecular_mass_da": 20_000.0})
        if conflicting
        else first
    )
    for order, records in enumerate(((first, second), (second, first)), start=1):
        _assert_duplicate_rejected(
            tmp_path / str(order),
            preflights=(_preflight(),),
            groups=records,
            sources=(_source("source_a", first),),
            expected=(
                f"duplicate SequenceGroupRecord.sequence_group_id "
                f"'{first.sequence_group_id}' at lines 1 and 2"
            ),
        )


@pytest.mark.parametrize("conflicting", (False, True))
def test_duplicate_source_id_is_order_independently_rejected(
    tmp_path: Path, conflicting: bool
) -> None:
    group = _group("A" * 100, source_record_count=1)
    first = _source("source_a", group)
    second = (
        first.model_copy(update={"original_protein_id": "conflicting_protein"})
        if conflicting
        else first
    )
    for order, records in enumerate(((first, second), (second, first)), start=1):
        _assert_duplicate_rejected(
            tmp_path / str(order),
            preflights=(_preflight(),),
            groups=(group,),
            sources=records,
            expected=(
                "duplicate SourceProteinRecord.source_record_id 'source_a' "
                "at lines 1 and 2"
            ),
        )


def test_exact_coverage_preserves_distinct_loci_in_one_sequence_group(
    tmp_path: Path,
) -> None:
    duplicated_locus_group = _group("A" * 100, source_record_count=2)
    other_group = _group("C" * 100, source_record_count=1)
    result = enumerate_matthews(
        _request(
            tmp_path,
            preflights=(_preflight(),),
            groups=(duplicated_locus_group, other_group),
            sources=(
                _source("locus_a", duplicated_locus_group),
                _source("locus_b", duplicated_locus_group),
                _source("locus_c", other_group),
            ),
        )
    )

    hypothesis_keys = {
        (row.sequence_group_id, row.copy_count) for row in result.hypotheses
    }
    assert len(hypothesis_keys) == len(result.hypotheses)
    assert {row.sequence_group_id for row in result.hypotheses} == {
        duplicated_locus_group.sequence_group_id,
        other_group.sequence_group_id,
    }


@pytest.mark.parametrize(
    "coverage_error",
    ("unexpected_preflight", "unreferenced_group", "source_count"),
)
def test_matthews_jsonl_requires_exact_record_coverage(
    tmp_path: Path, coverage_error: str
) -> None:
    group = _group(
        "A" * 100, source_record_count=2 if coverage_error == "source_count" else 1
    )
    preflights = (_preflight(),)
    groups = (group,)
    if coverage_error == "unexpected_preflight":
        preflights += (
            _preflight().model_copy(
                update={"crystal_id": "unexpected", "preflight_id": "unexpected"}
            ),
        )
    if coverage_error == "unreferenced_group":
        groups += (_group("C" * 100, source_record_count=1),)
    with pytest.raises(MatthewsInputError, match=r"coverage|source_record_count"):
        enumerate_matthews(
            _request(
                tmp_path,
                preflights=preflights,
                groups=groups,
                sources=(_source("source_a", group),),
            )
        )
