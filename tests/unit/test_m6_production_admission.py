"""M6 must expose the full safe model inventory to production admission."""

import json
from pathlib import Path

import pytest

from genome_to_diffraction.benchmarks.m6_nextflow import _write_eligible_inputs
from genome_to_diffraction.benchmarks.m6_registration import (
    register_m6_models,
    registration_batches,
)
from genome_to_diffraction.benchmarks.public_control import PublicControlError
from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.schemas.results import (
    CoordinateHitMappingRecord,
    CoordinateSourceRecord,
    StructuralSearchHit,
)
from genome_to_diffraction.structure_search import PdbCoordinateRegistrationRequest
from tests.unit.test_m6_benchmark import _policy_group, _policy_hit


def _hits(count: int) -> tuple[StructuralSearchHit, ...]:
    group = _policy_group("ACDE")
    return tuple(
        _policy_hit(
            group,
            hit_id=f"hit_{index:05d}",
            provider="pdb_sequence_mmseqs",
            provider_rank=index + 1,
            pdb_id="1ABC",
            target_sha256="a" * 64,
            identity=0.5,
            coverage=1.0,
        )
        for index in range(count)
    )


def test_eligible_inputs_ignore_provider_top_25(tmp_path: Path) -> None:
    groups = tuple(_policy_group("A" * length) for length in range(4, 35))
    catalogue = tmp_path / "catalogue"
    (catalogue / "catalogue").mkdir(parents=True)
    policy = tmp_path / "policy"
    (policy / "policy").mkdir(parents=True)
    (catalogue / "catalogue/sequence_groups.jsonl").write_text(
        "".join(f"{canonical_json_text(group)}\n" for group in groups), encoding="utf-8"
    )
    (catalogue / "catalogue/source_records.jsonl").write_text("", encoding="utf-8")
    hits = tuple(
        _policy_hit(
            group,
            hit_id=f"hit_{index}",
            provider="pdb_sequence_mmseqs",
            pdb_id="1ABC",
            target_sha256="a" * 64,
            identity=0.5,
            coverage=1.0,
        )
        for index, group in enumerate(groups)
    )
    (policy / "policy/accepted_structural_hits.jsonl").write_text(
        "".join(f"{canonical_json_text(hit)}\n" for hit in hits), encoding="utf-8"
    )
    output = tmp_path / "output"
    output.mkdir()
    group_path, _, hit_path = _write_eligible_inputs(catalogue, policy, output)
    assert len(group_path.read_text().splitlines()) == 31
    assert len(hit_path.read_text().splitlines()) == 31


def test_registration_batches_retain_every_hit_deterministically() -> None:
    hits = _hits(1007)
    batches = registration_batches(tuple(reversed(hits)))
    assert tuple(len(batch) for batch in batches) == (1000, 7)
    assert tuple(hit.hit_id for batch in batches for hit in batch) == tuple(
        hit.hit_id for hit in hits
    )
    with pytest.raises(PublicControlError, match="duplicate"):
        registration_batches((hits[0], hits[0]))


@pytest.mark.parametrize("omit_mapping", [False, True])
def test_complete_registration_checks_mapping_conservation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, omit_mapping: bool
) -> None:
    hits = _hits(1001)
    observed_batches: list[int] = []

    def register(request: PdbCoordinateRegistrationRequest) -> None:
        batch = [
            json.loads(line)
            for line in request.structural_hits_jsonl.read_text().splitlines()
        ]
        observed_batches.append(len(batch))
        assert request.maximum_mappings == len(batch)
        assert request.maximum_hits_per_sequence_group == len(batch)
        assert set(request.hit_ids) == {row["hit_id"] for row in batch}
        assert request.allow_network_acquisition is False
        output = request.output_directory
        output.mkdir()
        coordinate = output / "object.pdb"
        coordinate.write_text("coordinate fixture\n", encoding="utf-8")
        source = CoordinateSourceRecord(
            schema_version="1.0",
            coordinate_id="coord_one",
            provider="pdb",
            provider_accession="1ABC:1:A",
            retrieval_date="2026-08-01T00:00:00Z",
            source_release="test",
            coordinate_path="object.pdb",
            coordinate_sha256=sha256_file(coordinate),
            source_sequence_sha256="a" * 64,
            license_or_provenance="Synthetic registration test",
        )
        (output / "coordinate_sources.jsonl").write_text(
            f"{canonical_json_text(source)}\n"
        )
        mappings = [
            CoordinateHitMappingRecord(
                schema_version="1.0",
                mapping_id=f"mapping_{row['hit_id']}",
                hit_id=row["hit_id"],
                coordinate_id="coord_one",
                sequence_group_id=row["sequence_group_id"],
                candidate_sequence_sha256=_policy_group("ACDE").sha256,
                pdb_id="1ABC",
                identifier_namespace="legacy_seqres_suffix",
                seqres_token="A",
                entity_id="1",
                label_asym_ids=("A",),
                source_sequence_sha256="a" * 64,
                source_sequence_length=4,
                query_start=1,
                query_end=4,
                target_start=1,
                target_end=4,
                aligned_length=4,
                query_coverage=1.0,
                target_coverage=1.0,
                sequence_identity=0.5,
                exact_sequence_match=False,
            )
            for row in batch
        ]
        if omit_mapping:
            mappings.pop()
        (output / "coordinate_hit_mappings.jsonl").write_text(
            "".join(f"{canonical_json_text(mapping)}\n" for mapping in mappings)
        )
        (output / "registration_manifest.json").write_text("{}\n")

    monkeypatch.setattr(
        "genome_to_diffraction.benchmarks.m6_registration.register_pdb_coordinates",
        register,
    )
    if omit_mapping:
        with pytest.raises(PublicControlError, match="omitted"):
            register_m6_models(
                hits=hits,
                sequence_groups=tmp_path / "groups",
                database_manifest=tmp_path / "database",
                output_directory=tmp_path / "registry",
            )
        return
    register_m6_models(
        hits=hits,
        sequence_groups=tmp_path / "groups",
        database_manifest=tmp_path / "database",
        output_directory=tmp_path / "registry",
    )
    assert observed_batches == [1000, 1]
    manifest = json.loads(
        (tmp_path / "registry/registration_manifest.json").read_text()
    )
    assert manifest["selected_mapping_count"] == 1001
    assert manifest["coordinate_source_count"] == 1
    source = json.loads((tmp_path / "registry/coordinate_sources.jsonl").read_text())
    assert (tmp_path / "registry" / source["coordinate_path"]).is_file()
