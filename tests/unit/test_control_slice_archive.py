"""Tests for the fixed Viper control-slice archive boundary."""

import hashlib
import json
import tarfile
from pathlib import Path

import pytest

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.hpc.control_slice import _write_bundle_archive
from genome_to_diffraction.hpc.models import ValidationError


def test_control_slice_archive_records_bounded_checksum_inventory(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first asset.txt"
    second = tmp_path / "second.txt"
    first.write_text("alpha\n", encoding="ascii")
    second.write_text("beta\n", encoding="ascii")
    destination = tmp_path / "slice.tar.gz"

    archive_sha256, archive_size, manifest_sha256 = _write_bundle_archive(
        destination,
        members={
            "controls/PDB_1JCF/input.mtz": first,
            "controls/PDB_3W45/input.mtz": second,
        },
        manifest_payload={
            "schema_version": "1.0",
            "adapter_version": "public-homomer-smoke-import-v1",
            "case_ids": ["POS_1JCF", "POS_3W45"],
        },
        progress=False,
    )

    assert archive_sha256 == sha256_file(destination)
    assert archive_size == destination.stat().st_size
    with tarfile.open(destination, "r:gz") as archive:
        assert sorted(archive.getnames()) == [
            "control_slice_import_manifest.json",
            "controls/PDB_1JCF/input.mtz",
            "controls/PDB_3W45/input.mtz",
        ]
        manifest_handle = archive.extractfile("control_slice_import_manifest.json")
        assert manifest_handle is not None
        manifest_bytes = manifest_handle.read()
        manifest = json.loads(manifest_bytes)
    assert manifest_sha256 == hashlib.sha256(manifest_bytes).hexdigest()
    assert manifest["inventory"] == {
        "controls/PDB_1JCF/input.mtz": {
            "sha256": sha256_file(first),
            "size_bytes": first.stat().st_size,
        },
        "controls/PDB_3W45/input.mtz": {
            "sha256": sha256_file(second),
            "size_bytes": second.stat().st_size,
        },
    }


def test_control_slice_archive_rejects_unsafe_member_path(tmp_path: Path) -> None:
    source = tmp_path / "asset.txt"
    source.write_text("asset\n", encoding="ascii")

    with pytest.raises(ValidationError, match="member path is unsafe"):
        _write_bundle_archive(
            tmp_path / "slice.tar.gz",
            members={"../escaped.txt": source},
            manifest_payload={"schema_version": "1.0"},
            progress=False,
        )


def test_control_slice_archive_rejects_symlink_asset(tmp_path: Path) -> None:
    source = tmp_path / "asset.txt"
    source.write_text("asset\n", encoding="ascii")
    link = tmp_path / "asset-link.txt"
    link.symlink_to(source)

    with pytest.raises(ValidationError, match="regular non-symlink"):
        _write_bundle_archive(
            tmp_path / "slice.tar.gz",
            members={"controls/asset.txt": link},
            manifest_payload={"schema_version": "1.0"},
            progress=False,
        )
