"""Tests for the bounded, inspectable exact-predicted-model funnel."""

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.ranking import (
    ExactPredictedFunnelRequest,
    FunnelInputError,
    build_exact_predicted_funnel,
)
from genome_to_diffraction.schemas.results import (
    CoordinateSourceRecord,
    MatthewsHypothesis,
    PhysicalStatus,
)

REPOSITORY = Path(__file__).resolve().parents[2]
STUBS = REPOSITORY / "tests/fixtures/stubs"
SEQUENCE_GROUP_ID = (
    "seq_f50b9a1db8767fb7cdc8b89cf1a78c9fac1e0e2d5bb5367aeec14709396d5c5e"
)
COORDINATE_ID = "coord_" + "b" * 64


def _coordinate(path: Path) -> None:
    record = CoordinateSourceRecord(
        schema_version="1.0",
        coordinate_id=COORDINATE_ID,
        provider="afdb",
        provider_accession="AF-STUB-F1",
        retrieval_date=datetime(2026, 8, 11, tzinfo=UTC),
        source_release="v6",
        coordinate_path="coordinates/stub.cif",
        coordinate_sha256="b" * 64,
        source_sequence_sha256=SEQUENCE_GROUP_ID.removeprefix("seq_"),
        confidence_summary={"mean_plddt": 93.8},
        license_or_provenance="AlphaFold DB stub provenance",
    )
    path.write_text(f"{canonical_json_text(record)}\n", encoding="utf-8")


def _matthews(
    *,
    copy_count: int,
    rank: int,
    physical_status: PhysicalStatus,
    retained: bool = True,
) -> MatthewsHypothesis:
    return MatthewsHypothesis(
        schema_version="1.0",
        hypothesis_id=f"matthews_{copy_count}",
        crystal_id="test_crystal_01",
        sequence_group_id=SEQUENCE_GROUP_ID,
        copy_count=copy_count,
        sequence_mass_da=436.4375,
        total_mass_da=436.4375 * copy_count,
        v_asu_a3=250_000,
        matthews_coefficient=250_000 / (436.4375 * copy_count),
        solvent_fraction=0.50,
        matthews_prior=1.0 - rank / 10,
        prior_backend="test-prior",
        rank_within_candidate=rank,
        retained=retained,
        physical_status=physical_status,
        sds_page_prior_label="unavailable",
    )


def _request(
    tmp_path: Path, *, first_copy_cap: int = 200
) -> ExactPredictedFunnelRequest:
    model_preparation = tmp_path / "model preparation with spaces"
    shutil.copytree(STUBS / "predicted_model_preparation", model_preparation)
    coordinates = tmp_path / "coordinate sources.jsonl"
    _coordinate(coordinates)
    matthews = tmp_path / "Matthews hypotheses.jsonl"
    rows = (
        _matthews(copy_count=1, rank=1, physical_status=PhysicalStatus.PLAUSIBLE),
        _matthews(copy_count=2, rank=2, physical_status=PhysicalStatus.IMPOSSIBLE),
        _matthews(copy_count=3, rank=3, physical_status=PhysicalStatus.REVIEW),
        _matthews(
            copy_count=4,
            rank=4,
            physical_status=PhysicalStatus.PLAUSIBLE,
            retained=False,
        ),
    )
    matthews.write_text(
        "".join(f"{canonical_json_text(row)}\n" for row in rows),
        encoding="utf-8",
    )
    config = tmp_path / "config.yaml"
    config_text = (REPOSITORY / "examples/config.yaml").read_text(encoding="utf-8")
    config.write_text(
        config_text.replace(
            "max_first_copy_jobs: 200", f"max_first_copy_jobs: {first_copy_cap}"
        ),
        encoding="utf-8",
    )
    return ExactPredictedFunnelRequest(
        coordinate_sources_jsonl=coordinates,
        processed_models_jsonl=model_preparation / "processed_models.jsonl",
        model_preparation_manifest=(
            model_preparation / "model_preparation_manifest.json"
        ),
        sequence_groups_jsonl=STUBS / "sequence_groups.jsonl",
        matthews_hypotheses_jsonl=matthews,
        mtz_preflight_jsonl=STUBS / "mtz_preflight.jsonl",
        pipeline_config=config,
        output_directory=tmp_path / "funnel output",
        crystal_ids=("test_crystal_01",),
        progress=False,
    )


def test_funnel_excludes_impossible_rows_and_preserves_features(tmp_path: Path) -> None:
    result = build_exact_predicted_funnel(_request(tmp_path))

    assert [item.copy_count_expected for item in result.hypotheses] == [1, 3]
    assert all(item.copy_number_to_search == 1 for item in result.hypotheses)
    assert all(item.status == "queued" for item in result.hypotheses)
    first = result.hypotheses[0]
    assert first.priority_features["exact_sequence_mapping"] is True
    assert first.priority_features["coordinate_provider"] == "afdb"
    assert first.priority_features["model_retained_fraction"] == 1.0
    assert first.priority_features["matthews_physical_status"] == "plausible"
    manifest = json.loads(result.manifest_json.read_text(encoding="utf-8"))
    assert manifest["candidate_count_before_global_cap"] == 2
    assert manifest["selected_hypothesis_count"] == 2
    assert manifest["per_model_copy_cap"] == 3
    assert "matthews_prior" in manifest["ordering_features"]
    assert result.hypotheses_tsv.read_text(encoding="utf-8").count("\n") == 3
    records = sorted((result.manifest_json.parent / "hypotheses").glob("*.jsonl"))
    assert {record.stem for record in records} == {
        item.hypothesis_id for item in result.hypotheses
    }
    assert all(
        record.read_text(encoding="utf-8").count("\n") == 1 for record in records
    )


def test_funnel_applies_global_first_copy_cap_deterministically(tmp_path: Path) -> None:
    result = build_exact_predicted_funnel(_request(tmp_path, first_copy_cap=1))

    assert len(result.hypotheses) == 1
    assert result.hypotheses[0].copy_count_expected == 1
    manifest = json.loads(result.manifest_json.read_text(encoding="utf-8"))
    assert manifest["global_cap"] == 1
    assert manifest["excluded_by_global_cap_count"] == 1


def test_funnel_fails_before_publication_on_model_checksum_change(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    model = request.model_preparation_manifest.parent / "models/stub.cif"
    model.write_text("changed\n", encoding="utf-8")

    with pytest.raises(FunnelInputError, match="checksum mismatch"):
        build_exact_predicted_funnel(request)
    assert not request.output_directory.exists()


def test_funnel_rejects_path_traversal_in_preparation_manifest(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    document = json.loads(
        request.model_preparation_manifest.read_text(encoding="utf-8")
    )
    document["entries"][0]["model_path"] = "../escaped.cif"
    request.model_preparation_manifest.write_text(
        json.dumps(document), encoding="utf-8"
    )

    with pytest.raises(FunnelInputError, match="unsafe processed-model path"):
        build_exact_predicted_funnel(request)
