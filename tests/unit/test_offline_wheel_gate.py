"""Focused regressions for the locked offline wheel gate."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from tests.scripts.check_offline_wheel import (
    DistributionSpec,
    WheelGateError,
    inspect_wheel,
    require_version_parity,
)


def _write_repository(repository: Path) -> None:
    package = repository / "src" / "genome_to_diffraction"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text('__version__ = "0.2.0"\n')
    schemas = repository / "schemas"
    schemas.mkdir()
    (schemas / "example.schema.json").write_text('{"schema_version":"2.0"}\n')


def _write_wheel(
    wheel: Path,
    repository: Path,
    *,
    include_schema: bool = True,
    include_internal_hpc: bool = False,
    entry_points: str | None = None,
    version: str = "0.2.0",
) -> None:
    dist_info = "nf_genome_to_diffraction-0.2.0.dist-info"
    default_entry_points = (
        "[console_scripts]\ngenome-to-diffraction = genome_to_diffraction.cli:main\n"
    )
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            "genome_to_diffraction/__init__.py",
            (repository / "src/genome_to_diffraction/__init__.py").read_bytes(),
        )
        archive.writestr("genome_to_diffraction/cli.py", "")
        if include_internal_hpc:
            archive.writestr("genome_to_diffraction/hpc/cli.py", "")
        if include_schema:
            archive.writestr(
                "genome_to_diffraction/_schemas/example.schema.json",
                (repository / "schemas/example.schema.json").read_bytes(),
            )
        archive.writestr(
            f"{dist_info}/METADATA",
            "Metadata-Version: 2.4\n"
            "Name: nf-genome-to-diffraction\n"
            f"Version: {version}\n",
        )
        archive.writestr(
            f"{dist_info}/WHEEL",
            "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        archive.writestr(
            f"{dist_info}/entry_points.txt",
            default_entry_points if entry_points is None else entry_points,
        )


@pytest.fixture
def distribution_spec() -> DistributionSpec:
    return DistributionSpec(
        version="0.2.0",
        build_backend_version="1.32.0",
        entry_points={
            "genome-to-diffraction": "genome_to_diffraction.cli:main",
        },
    )


def test_wheel_rejects_missing_packaged_schema(
    tmp_path: Path,
    distribution_spec: DistributionSpec,
) -> None:
    _write_repository(tmp_path)
    wheel = tmp_path / "missing_schema.whl"
    _write_wheel(wheel, tmp_path, include_schema=False)

    with pytest.raises(WheelGateError, match="missing packaged schemas"):
        inspect_wheel(wheel, tmp_path, distribution_spec)


def test_wheel_rejects_missing_console_entry_point(
    tmp_path: Path,
    distribution_spec: DistributionSpec,
) -> None:
    _write_repository(tmp_path)
    wheel = tmp_path / "missing_entry_point.whl"
    _write_wheel(
        wheel,
        tmp_path,
        entry_points=("[console_scripts]\n"),
    )

    with pytest.raises(WheelGateError, match="console entry points"):
        inspect_wheel(wheel, tmp_path, distribution_spec)


def test_wheel_rejects_internal_hpc_client(
    tmp_path: Path,
    distribution_spec: DistributionSpec,
) -> None:
    _write_repository(tmp_path)
    wheel = tmp_path / "internal_hpc_client.whl"
    _write_wheel(wheel, tmp_path, include_internal_hpc=True)

    with pytest.raises(WheelGateError, match="internal HPC client"):
        inspect_wheel(wheel, tmp_path, distribution_spec)


def test_wheel_rejects_release_version_mismatch(
    tmp_path: Path,
    distribution_spec: DistributionSpec,
) -> None:
    _write_repository(tmp_path)
    wheel = tmp_path / "version_mismatch.whl"
    _write_wheel(wheel, tmp_path, version="0.2.1")

    with pytest.raises(WheelGateError, match="release-version mismatch"):
        inspect_wheel(wheel, tmp_path, distribution_spec)


def test_release_version_surfaces_must_be_nonempty_and_equal() -> None:
    assert require_version_parity({"package": "0.2.0", "pixi": "0.2.0"}) == ("0.2.0")
    with pytest.raises(WheelGateError, match="no release-version surfaces"):
        require_version_parity({})
