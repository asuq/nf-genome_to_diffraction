"""Tests for the fixed full-catalogue 6RTZ partner control."""

import json
from pathlib import Path

import pytest

from genome_to_diffraction.benchmarks import (
    HeteromerCatalogueControlRequest,
    prepare_6rtz_partner_catalogue_control,
)
from genome_to_diffraction.benchmarks import heteromer_catalogue_control as control
from genome_to_diffraction.benchmarks import heteromer_control as fixed
from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.schemas.results import ProcessedModelRecord

REPOSITORY = Path(__file__).resolve().parents[2]
PROTOCOL = REPOSITORY / "benchmarks/m6/protocol.yaml"
PARENT_SEQUENCE = (
    "MLAKRIIACLDVKDGRVVKGTNFENLRDSGDPVELGKFYSEIGIDELVFLDITASVEKRKTMLELVEKVA"
    "EQIDIPFTVGGGIHDFETASELILRGADKVSINTAAVENPSLITQIAQTFGSQAVVVAIDAKRVDGEFM"
    "VFTYSGKKNTGILLRDWVVEVEKRGAGEILLTSIDRDGTKSGYDTEMIRFVRPLTTLPIIASGGAGKMEH"
    "FLEAFLAGADAALAASVFHFREIDVRELKEYLKKHGVNVRLEGL"
)
PARTNER_SEQUENCE = (
    "MRIGIISVGPGNIMNLYRGVKRASENFEDVSIELVESPRNDLYDLLFIPGVGHFGEGMRRLRENDLIDFV"
    "RKHVEDERYVVGVCLGMQLLFEESEEAPGVKGLSLIEGNVVKLRSRRLPHMGWNEVIFKDTFPNGYYYF"
    "VHTYRAVCEEEHVLGTTEYDGEIFPSAVRKGRILGFQFHPEKSSKIGRKLLEKVIECSLSRR"
)


def _proteome_payload() -> bytes:
    records = [
        f">WP_004080486.1\n{PARENT_SEQUENCE}\n",
        f">WP_004080484.1\n{PARTNER_SEQUENCE}\n",
    ]
    alphabet = "ACDEFGHIKLMNPQRSTVWY"
    for index in range(1844):
        suffix = "".join(
            alphabet[(index // (len(alphabet) ** power)) % len(alphabet)]
            for power in range(4)
        )
        records.append(f">DUMMY_{index:04d}\nM{suffix}{'A' * 25}\n")
    return "".join(records).encode("ascii")


def _fixed_preparation(tmp_path: Path) -> Path:
    root = tmp_path / "fixed"
    models = root / "models"
    models.mkdir(parents=True)
    partner_model = models / "component_B.pdb"
    partner_model.write_text("REMARK fixed HisH\nATOM\n", encoding="ascii")
    parent = fixed._sequence_group(PARENT_SEQUENCE)
    partner = fixed._sequence_group(PARTNER_SEQUENCE)
    groups = root / "sequence_groups.jsonl"
    groups.write_text(
        f"{canonical_json_text(parent)}\n{canonical_json_text(partner)}\n",
        encoding="utf-8",
    )
    preparation = root / "preparation_manifest.json"
    preparation.write_text(
        json.dumps(
            {
                "crystal_id": "6RTZ",
                "parent_sequence_group_id": parent.sequence_group_id,
                "partner_sequence_group_id": partner.sequence_group_id,
                "files": {
                    "sequence_groups": {
                        "path": groups.relative_to(root).as_posix(),
                        "sha256": sha256_file(groups),
                    },
                    "partner_model": {
                        "path": partner_model.relative_to(root).as_posix(),
                        "sha256": sha256_file(partner_model),
                    },
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return preparation


def test_verify_proteome_requires_exact_bytes(tmp_path: Path) -> None:
    payload = b">protein\nMAAA\n"
    proteome = tmp_path / "protein.faa"
    proteome.write_bytes(payload)

    output = control._verify_proteome(
        proteome,
        sha256=sha256_file(proteome),
        size_bytes=len(payload),
    )

    assert output.read_bytes() == payload


def test_preparer_retains_full_catalogue_and_one_hish_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _proteome_payload()
    proteome = tmp_path / "synthetic-proteome.faa"
    proteome.write_bytes(payload)
    monkeypatch.setattr(control, "_verify_proteome", lambda path, **_: path)

    result = prepare_6rtz_partner_catalogue_control(
        HeteromerCatalogueControlRequest(
            protocol=PROTOCOL,
            control_preparation_manifest=_fixed_preparation(tmp_path),
            output_directory=tmp_path / "prepared",
            proteome_faa=proteome,
        )
    )

    assert result.protein_record_count == 1846
    assert result.catalogue_manifest.is_file()
    model = ProcessedModelRecord.model_validate_json(
        (result.partner_model_registry / "processed_models.jsonl").read_text(
            encoding="utf-8"
        )
    )
    assert model.full_candidate_sequence_group_id == result.partner_sequence_group_id
    assert model.processing_parameters["sequence_identity"] == 1.0
    manifest = json.loads(result.preparation_manifest.read_text(encoding="utf-8"))
    assert manifest["protein_record_count"] == 1846
    assert manifest["files"]["proteome_faa"]["sha256"] == sha256_file(
        result.proteome_faa
    )
