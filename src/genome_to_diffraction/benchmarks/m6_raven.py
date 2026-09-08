"""Read terminal Raven M6 records without the internal HPC controller package.

These bounded file checks serve the installed truth-side collector as well as
the source-only leakage controller. They bind source, owner, inputs and every
qualification checksum; they invoke no external command and assess no identity.
Native qualification still requires the complete shared M6 evidence validators.
"""

import json
import os
from pathlib import Path

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.ids import canonical_digest
from genome_to_diffraction.schemas.raven import RavenQualificationLaunch


def _completed_status(root: Path, spec: RavenQualificationLaunch) -> dict:
    records = {}
    for name in ("controller.json", "state.json"):
        path = root / name
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_uid != os.getuid()
            or path.stat().st_size > 65536
        ):
            raise ValueError("Raven terminal record is absent or unsafe")
        value = json.loads(path.read_text())
        if not isinstance(value, dict) or any(
            value.get(key) != expected
            for key, expected in {
                "owner_id": spec.owner_id,
                "run_id": spec.run_id,
            }.items()
        ):
            raise ValueError("Raven terminal run ownership differs")
        records[name] = value
    state = records["state.json"]
    if (
        state.get("source_commit") != spec.source_commit
        or state.get("input_id") != spec.input_id
        or state.get("state") != "COMPLETED"
        or type(state.get("exit_code")) is not int
        or state["exit_code"] != 0
    ):
        raise ValueError("Raven M6 controller is not completed for its bound source")
    process = records["controller.json"].get("process")
    if not isinstance(process, dict) or (
        type(process.get("pid")) is not int
        or process["pid"] < 1
        or not isinstance(process.get("start_ticks"), str)
        or not process["start_ticks"].isdigit()
        or not isinstance(process.get("boot_id"), str)
        or not process["boot_id"]
    ):
        raise ValueError("Raven M6 controller lacks its process identity")
    return state


_PRECHECK_PATHS = (
    "launch.json",
    "state.json",
    "qualification/m6-scientific-summary.json",
    "qualification/m6-scientific-checksums.sha256",
)


def operational_precheck(root: Path) -> str:
    """Hash the completed login-run authority consumed by its leakage child."""

    files = {}
    for name in _PRECHECK_PATHS:
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("Raven M6 operational precheck is incomplete")
        files[name] = sha256_file(path)
    return canonical_digest(files)


def collection_manifest(root: Path) -> dict[str, object]:
    """Verify a terminal Raven record, then project its observed provenance."""

    spec = RavenQualificationLaunch.model_validate_json(
        (root / "launch.json").read_text()
    )
    status = _completed_status(root, spec)
    if spec.stage not in {"m6-operational", "m6-leakage"} or (
        status["state"] != "COMPLETED" or status.get("exit_code") != 0
    ):
        raise ValueError("Raven M6 collection lacks a completed owned controller")
    qualification = root / "qualification"
    declared = set()
    checksum_path = qualification / "m6-scientific-checksums.sha256"
    for line in checksum_path.read_text().splitlines():
        digest, relative = line.split("  ", 1)
        path = Path(relative)
        if (
            path.is_absolute()
            or ".." in path.parts
            or str(path) != relative
            or relative in declared
            or (qualification / path).is_symlink()
            or sha256_file(qualification / path) != digest
        ):
            raise ValueError("Raven M6 collected qualification checksum changed")
        declared.add(relative)
    actual = {
        p.relative_to(qualification).as_posix()
        for p in qualification.rglob("*")
        if p.is_file() and p != checksum_path
    }
    if not declared or actual != declared:
        raise ValueError("Raven M6 qualification snapshot is incomplete")
    parameters = json.loads(
        (root / "qualification/m6-input-provenance.json").read_text()
    )
    if (
        parameters.get("run_id") != spec.run_id
        or parameters.get("input_id") != spec.input_id
        or parameters.get("runner_archive_sha256") != spec.runner_archive_sha256
        or parameters.get("software_lock_sha256") != spec.pixi_lock_sha256
    ):
        raise ValueError("Raven M6 collected inputs differ from their launch")
    summary = json.loads((qualification / "m6-scientific-summary.json").read_text())
    inputs = summary.get("input_sha256")
    if not isinstance(inputs, dict) or any(
        inputs.get(key) != value
        for key, value in {
            "phenix_manifest": spec.phenix_manifest_sha256,
            "database_manifest": parameters["database_manifest_sha256"],
            "runner_manifest": parameters["runner_manifest_sha256"],
        }.items()
    ):
        raise ValueError("Raven M6 scientific inputs differ from their launch")
    return {
        "run_id": spec.run_id,
        "site_id": "raven",
        "profile": spec.stage,
        "controller_kind": "login_process",
        "commit": spec.source_commit,
        "nf_helper_commit": spec.nf_helper_commit,
        "pixi_version": spec.pixi_version,
        "pixi_lock_sha256": spec.pixi_lock_sha256,
        "database_manifest_sha256": parameters["database_manifest_sha256"],
        "runner_archive_sha256": spec.runner_archive_sha256,
        "runner_manifest_sha256": parameters["runner_manifest_sha256"],
        "operational_parent_run_id": (
            spec.operational_parent_run.name if spec.operational_parent_run else None
        ),
        "operational_precheck_sha256": spec.operational_precheck_sha256,
    }
