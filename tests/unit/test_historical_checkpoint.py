"""Historical checkpoint evidence remains immutable, readable, and confined."""

import json
from pathlib import Path

import pytest

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.review.historical_checkpoint import (
    HistoricalCheckpointError,
    verify_historical_checkpoint,
)


def _write_checkpoint(root: Path) -> Path:
    asset = root / "assets" / "sol_test" / "brief_refine_001.pdb"
    asset.parent.mkdir(parents=True)
    asset.write_text("historical retained coordinates\n", encoding="utf-8")
    output = root / "sequence_approval_candidates.tsv"
    output.write_text("sequence_group_id\nseq_test\n", encoding="utf-8")
    manifest = {
        "schema_version": "1.0",
        "run_id": "gtd-t12-test",
        "package_id": "seqreview_test",
        "finalist_count": 1,
        "outputs": {output.name: sha256_file(output)},
        "identity": {
            "assets": {asset.relative_to(root).as_posix(): sha256_file(asset)}
        },
        "crystal_context": {"crystal_id": "crystal_test"},
    }
    (root / "sequence_checkpoint_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    return root


def test_historical_checkpoint_verification_never_writes_scientific_claims(
    tmp_path: Path,
) -> None:
    checkpoint = _write_checkpoint(tmp_path / "checkpoint")
    before = {
        path.relative_to(checkpoint).as_posix(): sha256_file(path)
        for path in checkpoint.rglob("*")
        if path.is_file()
    }

    manifest, manifest_path = verify_historical_checkpoint(checkpoint)

    assert manifest.run_id == "gtd-t12-test"
    assert manifest.package_id == "seqreview_test"
    assert manifest.crystal_context["crystal_id"] == "crystal_test"
    assert manifest_path == checkpoint / "sequence_checkpoint_manifest.json"
    after = {
        path.relative_to(checkpoint).as_posix(): sha256_file(path)
        for path in checkpoint.rglob("*")
        if path.is_file()
    }
    assert after == before
    assert not (checkpoint / "scientific_status.json").exists()
    assert not (checkpoint / "crystal_report.html").exists()


@pytest.mark.parametrize("relative", ["../outside.tsv", "assets/../../outside.tsv"])
def test_historical_checkpoint_rejects_parent_traversal(
    tmp_path: Path, relative: str
) -> None:
    checkpoint = _write_checkpoint(tmp_path / "checkpoint")
    outside = tmp_path / "outside.tsv"
    outside.write_text("unowned scientific evidence\n", encoding="utf-8")
    manifest_path = checkpoint / "sequence_checkpoint_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["outputs"][relative] = sha256_file(outside)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(HistoricalCheckpointError, match="checkpoint path"):
        verify_historical_checkpoint(checkpoint)


def test_historical_checkpoint_rejects_intermediate_symlink(tmp_path: Path) -> None:
    checkpoint = _write_checkpoint(tmp_path / "checkpoint")
    outside = tmp_path / "outside"
    outside.mkdir()
    stolen = outside / "stolen.tsv"
    stolen.write_text("unowned scientific evidence\n", encoding="utf-8")
    (checkpoint / "assets" / "redirect").symlink_to(outside, target_is_directory=True)
    manifest_path = checkpoint / "sequence_checkpoint_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["outputs"]["assets/redirect/stolen.tsv"] = sha256_file(stolen)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(HistoricalCheckpointError, match="symlink"):
        verify_historical_checkpoint(checkpoint)
