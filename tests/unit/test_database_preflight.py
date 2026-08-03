"""Unit tests for the fixed large-database compute-node preflight."""

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from genome_to_diffraction.databases.common import DatabaseError
from genome_to_diffraction.databases.preflight import (
    FOLDSEEK_PDB_ARCHIVE_URL,
    FOLDSEEK_PDB_VERSION_URL,
    FOLDSEEK_PROSTT5_ARCHIVE_URL,
    PDB_COORDINATE_SMOKE_URL,
    PDB_SEQUENCE_URL,
    DatabasePreflightRequest,
    _probe_public_routes,
    preflight_database_administration,
)


def _request(tmp_path: Path) -> DatabasePreflightRequest:
    database_root = tmp_path / "database root"
    scratch_root = tmp_path / "scratch root"
    database_root.mkdir()
    scratch_root.mkdir()
    return DatabasePreflightRequest(
        database_root=database_root,
        scratch_root=scratch_root,
        report_path=tmp_path / "preflight report.json",
        storage_limit_bytes=2_000,
        minimum_free_bytes=100,
        required_database_capacity_bytes=1_000,
        minimum_scratch_free_bytes=500,
        probe_timeout_seconds=5,
        progress=False,
    )


def _mock_successful_system(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "genome_to_diffraction.databases.preflight._device_id",
        lambda path: 1 if path.name == "database root" else 2,
    )
    monkeypatch.setattr(
        "genome_to_diffraction.databases.preflight.tree_size", lambda _: 100
    )
    monkeypatch.setattr(
        "genome_to_diffraction.databases.preflight.shutil.disk_usage",
        lambda path: SimpleNamespace(
            total=4_000,
            used=1_000,
            free=3_000 if path.name == "database root" else 2_000,
        ),
    )
    monkeypatch.setattr(
        "genome_to_diffraction.databases.preflight.tool_version",
        lambda executable: (
            "foldseek 10.941cd33" if executable == "foldseek" else "mmseqs 18.8cc5c"
        ),
    )
    monkeypatch.setattr(
        "genome_to_diffraction.databases.preflight._probe_public_routes",
        lambda *_args, **_kwargs: (
            "aria2 version 1.37.0",
            [
                {
                    "name": "fixed",
                    "url": FOLDSEEK_PDB_VERSION_URL,
                    "probe": "aria2c --dry-run=true",
                    "status": "reachable",
                }
            ],
        ),
    )


def test_preflight_records_distinct_scratch_capacity_tools_and_routes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path)
    _mock_successful_system(monkeypatch)

    report = preflight_database_administration(request)

    assert report["status"] == "passed"
    assert report["database_device"] == 1
    assert report["scratch_device"] == 2
    assert report["database_available_build_bytes"] == 1_900
    assert report["large_payload_started"] is False
    persisted = json.loads(request.report_path.read_text(encoding="utf-8"))
    assert persisted == report


def test_preflight_fails_before_network_when_scratch_shares_filesystem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path)
    monkeypatch.setattr(
        "genome_to_diffraction.databases.preflight._device_id", lambda _: 1
    )

    with pytest.raises(DatabaseError, match="filesystem distinct"):
        preflight_database_administration(request)

    report = json.loads(request.report_path.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["large_payload_started"] is False


def test_preflight_fails_when_explicit_capacity_requirement_is_not_met(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path)
    _mock_successful_system(monkeypatch)
    monkeypatch.setattr(
        "genome_to_diffraction.databases.preflight.tree_size", lambda _: 1_500
    )

    with pytest.raises(DatabaseError, match="explicitly required build capacity"):
        preflight_database_administration(request)

    report = json.loads(request.report_path.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["large_payload_started"] is False


def test_route_probe_uses_pinned_aria2_dry_run_and_only_fixed_urls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_directory = tmp_path / "bin"
    bin_directory.mkdir()
    calls = tmp_path / "calls.txt"
    aria2c = bin_directory / "aria2c"
    aria2c.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'printf \'%s\\t\' "$@" >> "$PROBE_CALLS"\n'
        "printf '\\n' >> \"$PROBE_CALLS\"\n",
        encoding="utf-8",
    )
    aria2c.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_directory}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("PROBE_CALLS", str(calls))
    monkeypatch.setattr(
        "genome_to_diffraction.databases.preflight.tool_version",
        lambda _: "aria2 version 1.37.0",
    )
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    version, probes = _probe_public_routes(
        scratch,
        timeout_seconds=5,
        progress=False,
    )

    assert version == "aria2 version 1.37.0"
    assert [probe["url"] for probe in probes] == [
        FOLDSEEK_PDB_ARCHIVE_URL,
        FOLDSEEK_PDB_VERSION_URL,
        FOLDSEEK_PROSTT5_ARCHIVE_URL,
        PDB_SEQUENCE_URL,
        PDB_COORDINATE_SMOKE_URL,
    ]
    call_lines = calls.read_text(encoding="utf-8").splitlines()
    assert len(call_lines) == 5
    assert all("--dry-run=true" in line for line in call_lines)
