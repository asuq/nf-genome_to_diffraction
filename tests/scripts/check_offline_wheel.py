"""Build and verify the project wheel without network or build isolation."""

from __future__ import annotations

import argparse
import configparser
import importlib.metadata
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from dataclasses import dataclass
from email.parser import BytesParser
from pathlib import Path, PurePosixPath

_DISTRIBUTION = "nf-genome-to-diffraction"
_PACKAGE = "genome_to_diffraction"
_ENTRY_POINTS = {
    "genome-to-diffraction": "genome_to_diffraction.cli:main",
}
_REQUIRED_CODE = (
    "genome_to_diffraction/__init__.py",
    "genome_to_diffraction/cli.py",
)
_REQUIRED_RESOURCES = {
    "genome_to_diffraction/matthews/data/protein_mattprob_2013.json.gz": (
        "src/genome_to_diffraction/matthews/data/protein_mattprob_2013.json.gz"
    ),
}
_INTERNAL_HPC_PREFIX = "genome_to_diffraction/hpc/"
_NEXTFLOW_VERSION = re.compile(r"^\s*version\s*=\s*'([^']+)'\s*$", re.MULTILINE)
_SOURCE_VERSION = re.compile(r'^__version__\s*=\s*"([^"]+)"\s*$', re.MULTILINE)
_HATCHLING_PIN = re.compile(r"^hatchling==([^;\s]+)$")

_ENTRY_POINT_RUNNER = """
import importlib.metadata
import sys

distribution_name, entry_point_name, *arguments = sys.argv[1:]
matches = [
    item for item in importlib.metadata.distribution(distribution_name).entry_points
    if item.group == "console_scripts" and item.name == entry_point_name
]
if len(matches) != 1:
    raise RuntimeError(f"expected one entry point {entry_point_name!r}")
sys.argv = [entry_point_name, *arguments]
result = matches[0].load()()
raise SystemExit(0 if result is None else int(result))
"""

_INSTALLED_PROBE = """
import importlib.metadata
import json
from pathlib import Path
import genome_to_diffraction

print(json.dumps({
    "distribution": importlib.metadata.version("nf-genome-to-diffraction"),
    "module_file": str(Path(genome_to_diffraction.__file__).resolve()),
    "package": genome_to_diffraction.__version__,
}, sort_keys=True))
"""


class WheelGateError(ValueError):
    """Raised when the offline distribution boundary is incomplete."""


@dataclass(frozen=True)
class DistributionSpec:
    """Release metadata required to inspect one wheel."""

    version: str
    build_backend_version: str
    entry_points: dict[str, str]


def require_version_parity(versions: dict[str, str]) -> str:
    """Return the common release version or reject divergent surfaces."""

    if not versions:
        raise WheelGateError("no release-version surfaces were supplied")
    if len(set(versions.values())) != 1:
        rendered = ", ".join(
            f"{name}={value}" for name, value in sorted(versions.items())
        )
        raise WheelGateError(f"release-version mismatch: {rendered}")
    return next(iter(versions.values()))


def _one_match(pattern: re.Pattern[str], path: Path, label: str) -> str:
    matches = pattern.findall(path.read_text(encoding="utf-8"))
    if len(matches) != 1:
        raise WheelGateError(f"expected one {label} in {path}, found {len(matches)}")
    return matches[0]


def load_distribution_spec(repository: Path) -> tuple[DistributionSpec, dict[str, str]]:
    """Load exact build, entry-point, and release metadata."""

    pyproject = tomllib.loads(
        (repository / "pyproject.toml").read_text(encoding="utf-8")
    )
    pixi = tomllib.loads((repository / "pixi.toml").read_text(encoding="utf-8"))
    build = pyproject["build-system"]
    requirements = build.get("requires")
    if build.get("build-backend") != "hatchling.build":
        raise WheelGateError("build backend must be exactly hatchling.build")
    if not isinstance(requirements, list) or len(requirements) != 1:
        raise WheelGateError("build-system.requires must contain one exact pin")
    backend = _HATCHLING_PIN.fullmatch(str(requirements[0]))
    if backend is None:
        raise WheelGateError("build-system.requires must pin hatchling with ==")

    project = pyproject["project"]
    entry_points = project.get("scripts")
    if entry_points != _ENTRY_POINTS:
        raise WheelGateError("pyproject has unexpected console entry points")
    version = str(project["version"])
    versions = {
        "package_source": _one_match(
            _SOURCE_VERSION,
            repository / "src" / _PACKAGE / "__init__.py",
            "literal package version",
        ),
        "pixi": str(pixi["workspace"]["version"]),
        "pyproject": version,
        "nextflow": _one_match(
            _NEXTFLOW_VERSION,
            repository / "nextflow.config",
            "Nextflow manifest version",
        ),
    }
    require_version_parity(versions)
    return DistributionSpec(version, backend.group(1), dict(entry_points)), versions


def _members(archive: zipfile.ZipFile) -> set[str]:
    names: set[str] = set()
    for member in archive.infolist():
        path = PurePosixPath(member.filename)
        if path.is_absolute() or ".." in path.parts:
            raise WheelGateError(f"unsafe wheel member: {member.filename}")
        if member.filename in names:
            raise WheelGateError(f"duplicate wheel member: {member.filename}")
        names.add(member.filename)
    return names


def _wheel_entry_points(payload: bytes) -> dict[str, str]:
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(payload.decode("utf-8"))
    if not parser.has_section("console_scripts"):
        return {}
    return dict(parser.items("console_scripts"))


def inspect_wheel(wheel: Path, repository: Path, spec: DistributionSpec) -> str:
    """Verify code, schemas, metadata, and entry points in one wheel."""

    with zipfile.ZipFile(wheel) as archive:
        names = _members(archive)
        metadata_files = sorted(
            name for name in names if name.endswith(".dist-info/METADATA")
        )
        if len(metadata_files) != 1:
            raise WheelGateError(
                f"expected one wheel METADATA file, found {len(metadata_files)}"
            )
        dist_info = metadata_files[0].removesuffix("/METADATA")
        required_metadata = {
            metadata_files[0],
            f"{dist_info}/WHEEL",
            f"{dist_info}/entry_points.txt",
        }
        missing_metadata = sorted(required_metadata - names)
        if missing_metadata:
            raise WheelGateError(
                f"wheel is missing metadata: {', '.join(missing_metadata)}"
            )

        metadata = BytesParser().parsebytes(archive.read(metadata_files[0]))
        if metadata.get("Name", "").casefold() != _DISTRIBUTION.casefold():
            raise WheelGateError("wheel distribution name does not match pyproject")
        wheel_version = metadata.get("Version", "")
        require_version_parity(
            {"pyproject": spec.version, "wheel_metadata": wheel_version}
        )
        wheel_metadata = archive.read(f"{dist_info}/WHEEL").decode("utf-8")
        if "Root-Is-Purelib: true" not in wheel_metadata:
            raise WheelGateError("wheel must be a purelib distribution")
        wheel_entry_points = _wheel_entry_points(
            archive.read(f"{dist_info}/entry_points.txt")
        )
        if wheel_entry_points != spec.entry_points:
            raise WheelGateError("wheel console entry points do not match pyproject")

        missing_code = sorted(set(_REQUIRED_CODE) - names)
        if missing_code:
            raise WheelGateError(
                f"wheel is missing package code: {', '.join(missing_code)}"
            )
        missing_resources = sorted(set(_REQUIRED_RESOURCES) - names)
        if missing_resources:
            raise WheelGateError(
                "wheel is missing required scientific resources: "
                f"{', '.join(missing_resources)}"
            )
        for name, source in _REQUIRED_RESOURCES.items():
            if archive.read(name) != (repository / source).read_bytes():
                raise WheelGateError(
                    f"packaged scientific resource differs from source: {name}"
                )
        internal_hpc_members = sorted(
            name for name in names if name.startswith(_INTERNAL_HPC_PREFIX)
        )
        if internal_hpc_members:
            raise WheelGateError(
                "wheel contains the internal HPC client: "
                f"{', '.join(internal_hpc_members)}"
            )
        schemas = {
            f"{_PACKAGE}/_schemas/{path.name}": path
            for path in (repository / "schemas").glob("*.schema.json")
        }
        if not schemas:
            raise WheelGateError("repository has no packaged JSON Schemas")
        missing_schemas = sorted(set(schemas) - names)
        if missing_schemas:
            raise WheelGateError(
                f"wheel is missing packaged schemas: {', '.join(missing_schemas)}"
            )
        for name, path in schemas.items():
            if archive.read(name) != path.read_bytes():
                raise WheelGateError(f"packaged schema differs from source: {name}")
    return wheel_version


def _offline_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_NO_INDEX": "1",
            "PYTHONNOUSERSITE": "1",
            "UV_OFFLINE": "1",
        }
    )
    environment.pop("PYTHONPATH", None)
    return environment


def _run(command: list[str], cwd: Path, environment: dict[str, str]) -> str:
    return subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _install_and_probe(
    wheel: Path, workspace: Path, spec: DistributionSpec
) -> dict[str, str]:
    environment = _offline_environment()
    venv = workspace / "venv"
    _run(
        [
            sys.executable,
            "-m",
            "venv",
            "--without-pip",
            "--system-site-packages",
            str(venv),
        ],
        workspace,
        environment,
    )
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    purelib = Path(
        _run(
            [
                str(python),
                "-c",
                "import sysconfig; print(sysconfig.get_paths()['purelib'])",
            ],
            workspace,
            environment,
        ).strip()
    )
    with zipfile.ZipFile(wheel) as archive:
        _members(archive)
        archive.extractall(purelib)

    probe = json.loads(
        _run([str(python), "-c", _INSTALLED_PROBE], workspace, environment)
    )
    module_file = Path(str(probe["module_file"]))
    if not module_file.is_relative_to(purelib.resolve()):
        raise WheelGateError(f"wheel import escaped isolated install: {module_file}")
    installed_versions = {
        "installed_distribution": str(probe["distribution"]),
        "installed_package": str(probe["package"]),
        "pyproject": spec.version,
    }
    require_version_parity(installed_versions)

    for name in sorted(spec.entry_points):
        output = _run(
            [
                str(python),
                "-c",
                _ENTRY_POINT_RUNNER,
                _DISTRIBUTION,
                name,
                "--help",
            ],
            workspace,
            environment,
        )
        if "usage:" not in output.casefold():
            raise WheelGateError(f"entry point {name} emitted no help usage")
    cli_version = _run(
        [
            str(python),
            "-c",
            _ENTRY_POINT_RUNNER,
            _DISTRIBUTION,
            "genome-to-diffraction",
            "--version",
        ],
        workspace,
        environment,
    ).strip()
    require_version_parity({"installed_cli": cli_version, "pyproject": spec.version})
    installed_versions["installed_cli"] = cli_version
    return installed_versions


def run_gate(repository: Path) -> dict[str, object]:
    """Execute the complete locked-runtime offline wheel gate."""

    repository = repository.resolve()
    spec, versions = load_distribution_spec(repository)
    try:
        backend_version = importlib.metadata.version("hatchling")
    except importlib.metadata.PackageNotFoundError as error:
        raise WheelGateError("Hatchling is absent from the locked runtime") from error
    require_version_parity(
        {"build_system": spec.build_backend_version, "runtime": backend_version}
    )

    environment = _offline_environment()
    with tempfile.TemporaryDirectory(prefix="nf-gtd-offline-wheel-") as temporary:
        workspace = Path(temporary)
        dist = workspace / "dist"
        dist.mkdir()
        _run(
            [
                sys.executable,
                "-m",
                "hatchling",
                "build",
                "--target",
                "wheel",
                "--directory",
                str(dist),
            ],
            repository,
            environment,
        )
        wheels = sorted(dist.glob("*.whl"))
        if len(wheels) != 1:
            raise WheelGateError(f"expected one built wheel, found {len(wheels)}")
        wheel_version = inspect_wheel(wheels[0], repository, spec)
        installed_versions = _install_and_probe(wheels[0], workspace, spec)

    version = require_version_parity(
        {**versions, "wheel_metadata": wheel_version, **installed_versions}
    )
    return {
        "build_backend": f"hatchling=={backend_version}",
        "entry_points": sorted(spec.entry_points),
        "offline_build": True,
        "schema_count": len(list((repository / "schemas").glob("*.schema.json"))),
        "version": version,
    }


def main() -> int:
    """Run the gate and emit one deterministic summary."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        result = run_gate(args.repository)
    except (OSError, subprocess.CalledProcessError, WheelGateError) as error:
        print(f"offline wheel gate failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
