"""Tests for deterministic PDB-provider hit aggregation."""

import json
from pathlib import Path

import pytest

from genome_to_diffraction.cli import main
from genome_to_diffraction.schemas.io import load_json_document
from genome_to_diffraction.structure_search.provider_hits import (
    ProviderHitMergeError,
    ProviderHitMergeRequest,
    merge_pdb_provider_hits,
)

REPOSITORY = Path(__file__).resolve().parents[2]
PDB_HITS = REPOSITORY / "tests/fixtures/stubs/structure_search/structural_hits.jsonl"
FOLDSEEK_HITS = (
    REPOSITORY / "tests/fixtures/stubs/prostt5_foldseek_search/structural_hits.jsonl"
)


def _merge(tmp_path: Path, *, name: str = "merged"):
    return merge_pdb_provider_hits(
        ProviderHitMergeRequest(PDB_HITS, FOLDSEEK_HITS, tmp_path / name)
    )


def test_provider_hit_merge_retains_both_provider_universes(tmp_path: Path) -> None:
    output = _merge(tmp_path)

    assert {item.provider for item in output.hits} == {
        "pdb_sequence_mmseqs",
        "foldseek_prostt5_pdb",
    }
    assert len(output.hits) == 2
    manifest = load_json_document(output.manifest_json)
    assert isinstance(manifest, dict)
    assert manifest["hit_count"] == 2
    assert manifest["hit_ids"] == [item.hit_id for item in output.hits]


def test_provider_hit_merge_is_byte_deterministic(tmp_path: Path) -> None:
    first = _merge(tmp_path, name="first")
    second = _merge(tmp_path, name="second")

    assert first.hits_jsonl.read_bytes() == second.hits_jsonl.read_bytes()
    assert first.manifest_json.read_bytes() == second.manifest_json.read_bytes()


def test_provider_hit_merge_accepts_two_typed_empty_inputs(tmp_path: Path) -> None:
    pdb = tmp_path / "pdb.jsonl"
    foldseek = tmp_path / "foldseek.jsonl"
    pdb.write_text("", encoding="utf-8")
    foldseek.write_text("", encoding="utf-8")

    output = merge_pdb_provider_hits(
        ProviderHitMergeRequest(pdb, foldseek, tmp_path / "empty")
    )

    assert output.hits == ()
    assert output.hits_jsonl.read_text(encoding="utf-8") == ""


def test_provider_hit_merge_rejects_wrong_bundle_provider(tmp_path: Path) -> None:
    with pytest.raises(ProviderHitMergeError, match="differs from its bundle"):
        merge_pdb_provider_hits(
            ProviderHitMergeRequest(PDB_HITS, PDB_HITS, tmp_path / "invalid")
        )


def test_provider_hit_merge_rejects_duplicate_hit_ids(tmp_path: Path) -> None:
    pdb_document = json.loads(PDB_HITS.read_text(encoding="utf-8"))
    foldseek_document = json.loads(FOLDSEEK_HITS.read_text(encoding="utf-8"))
    foldseek_document["hit_id"] = pdb_document["hit_id"]
    foldseek = tmp_path / "foldseek.jsonl"
    foldseek.write_text(json.dumps(foldseek_document) + "\n", encoding="utf-8")

    with pytest.raises(ProviderHitMergeError, match="duplicate hit IDs"):
        merge_pdb_provider_hits(
            ProviderHitMergeRequest(PDB_HITS, foldseek, tmp_path / "duplicate")
        )


def test_provider_hit_merge_cli_writes_manifest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "cli"

    assert (
        main(
            [
                "structure-search",
                "merge-pdb-provider-hits",
                "--pdb-sequence-hits",
                str(PDB_HITS),
                "--foldseek-hits",
                str(FOLDSEEK_HITS),
                "--outdir",
                str(output),
            ]
        )
        == 0
    )

    assert "Merged 2 PDB provider hits" in capsys.readouterr().out
    assert (output / "provider_hit_merge_manifest.json").is_file()
