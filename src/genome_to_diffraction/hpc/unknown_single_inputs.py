"""Build the fixed private A-seed decision archive for continuation staging."""

import argparse
import os
import re
import shutil
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.execution import stage_unknown_pass1_selected_a_seeds
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.review.owned_run import (
    OwnedPhaseIIIReviewPackageSource,
    register_phase3_owned_run,
)
from genome_to_diffraction.review.phase3_package import (
    validate_phase3_review_package,
)
from genome_to_diffraction.review.phase3_stage import OwnedPhaseIIIParentRun
from genome_to_diffraction.schemas.io import (
    ContractError,
    ContractLoadError,
    load_contract,
    load_json_document,
)
from genome_to_diffraction.schemas.v2 import (
    PhaseIIIReviewCheckpoint,
    PhaseIIIReviewDecisionFile,
)
from genome_to_diffraction.status import InputContractError

UNKNOWN_SINGLE_SPEC_RELATIVE = Path(
    ".untracked/phase3-unknown-pass1/unknown-single-component-inputs.json"
)
UNKNOWN_SINGLE_MANIFEST_NAME = "unknown_single_component_input_manifest.json"
_SPEC_KEYS = frozenset({"schema_version", "decisions"})
_DECISION_KEYS = frozenset({"crystal_id", "path", "sha256"})
_MAX_SPEC_BYTES = 32 * 1024
_MAX_DECISION_BYTES = 128 * 1024
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_CHECKSUM = re.compile(r"^[a-f0-9]{64}$")


class UnknownSingleComponentInputError(InputContractError):
    """The fixed A-seed decision inputs are unsafe or incomplete."""


@dataclass(frozen=True, slots=True)
class UnknownSingleComponentInputBundle:
    """One deterministic decision archive bound to its screen parent."""

    input_id: str
    parent_run_id: str
    crystal_ids: tuple[str, ...]
    archive_path: Path
    archive_sha256: str
    archive_size_bytes: int
    decision_count: int


def _owned_spec(path: Path) -> dict[str, object]:
    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_uid != os.getuid()
        or path.stat().st_mode & 0o777 != 0o600
    ):
        raise UnknownSingleComponentInputError(
            "unknown-single-component spec must be an owned mode-0600 file"
        )
    if path.stat().st_size < 1 or path.stat().st_size > _MAX_SPEC_BYTES:
        raise UnknownSingleComponentInputError(
            "unknown-single-component spec size is outside the fixed bound"
        )
    try:
        document = load_json_document(path)
    except ContractLoadError as error:
        raise UnknownSingleComponentInputError(
            "unknown-single-component spec is malformed"
        ) from error
    if (
        not isinstance(document, dict)
        or set(document) != _SPEC_KEYS
        or document.get("schema_version") != "1.0"
    ):
        raise UnknownSingleComponentInputError(
            "unknown-single-component spec differs from its fixed fields"
        )
    return document


def _decision_path(value: object, *, crystal_id: str) -> Path:
    if not isinstance(value, str) or not value.startswith("/"):
        raise UnknownSingleComponentInputError(
            f"decision path for {crystal_id} must be absolute"
        )
    path = Path(value)
    if path.is_symlink():
        raise UnknownSingleComponentInputError(
            f"decision path for {crystal_id} must not be a symlink"
        )
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise UnknownSingleComponentInputError(
            f"decision path for {crystal_id} is absent"
        ) from error
    if not resolved.is_file() or resolved.stat().st_size > _MAX_DECISION_BYTES:
        raise UnknownSingleComponentInputError(
            f"decision file for {crystal_id} is invalid"
        )
    return resolved


def _load_decision(
    path: Path,
    *,
    crystal_id: str,
    parent_run_id: str,
) -> PhaseIIIReviewDecisionFile:
    try:
        decision = load_contract(
            path,
            "phase3-review-decisions",
            progress=False,
        )
    except ContractError as error:
        raise UnknownSingleComponentInputError(
            f"A-seed decision for {crystal_id} violates its contract"
        ) from error
    if not isinstance(decision, PhaseIIIReviewDecisionFile):
        raise AssertionError("decision loader returned another contract")
    if (
        decision.checkpoint is not PhaseIIIReviewCheckpoint.A_SEED
        or decision.owned_parent_run_id != parent_run_id
        or {item.crystal_id for item in decision.decisions} != {crystal_id}
    ):
        raise UnknownSingleComponentInputError(
            f"A-seed decision for {crystal_id} belongs to another authority"
        )
    return decision


def _add_file(archive: tarfile.TarFile, name: str, source: Path) -> None:
    info = archive.gettarinfo(str(source), arcname=name)
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    info.mode = 0o600
    with source.open("rb") as handle:
        archive.addfile(info, handle)


def build_unknown_single_component_input_bundle(
    *,
    repository: Path,
    parent_run_id: str,
    archive_path: Path,
) -> UnknownSingleComponentInputBundle:
    """Validate checksum-confirmed A decisions and write a deterministic tar."""

    spec = _owned_spec(repository / UNKNOWN_SINGLE_SPEC_RELATIVE)
    raw_decisions = spec.get("decisions")
    if not isinstance(raw_decisions, list) or not 1 <= len(raw_decisions) <= 3:
        raise UnknownSingleComponentInputError(
            "unknown-single-component requires one to three decision files"
        )
    records: list[dict[str, object]] = []
    members: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for raw in raw_decisions:
        if not isinstance(raw, dict) or set(raw) != _DECISION_KEYS:
            raise UnknownSingleComponentInputError(
                "unknown-single-component decision spec is malformed"
            )
        crystal_id = raw.get("crystal_id")
        expected_sha256 = raw.get("sha256")
        if (
            not isinstance(crystal_id, str)
            or _IDENTIFIER.fullmatch(crystal_id) is None
            or crystal_id in seen
            or not isinstance(expected_sha256, str)
            or _CHECKSUM.fullmatch(expected_sha256) is None
        ):
            raise UnknownSingleComponentInputError(
                "unknown-single-component decision identity is invalid"
            )
        path = _decision_path(raw.get("path"), crystal_id=crystal_id)
        actual_sha256 = sha256_file(path, progress=False)
        if actual_sha256 != expected_sha256:
            raise UnknownSingleComponentInputError(
                f"A-seed decision checksum differs for {crystal_id}"
            )
        decision = _load_decision(
            path,
            crystal_id=crystal_id,
            parent_run_id=parent_run_id,
        )
        seen.add(crystal_id)
        relative = f"decisions/{crystal_id}.tsv"
        members.append((relative, path))
        records.append(
            {
                "crystal_id": crystal_id,
                "relative_path": relative,
                "sha256": actual_sha256,
                "size_bytes": path.stat().st_size,
                "decision_file_id": decision.decision_file_id,
                "decision_count": len(decision.decisions),
            }
        )
    records.sort(key=lambda item: str(item["crystal_id"]))
    members.sort(key=lambda item: item[0])
    identity = {
        "adapter_version": "unknown-single-component-input-bundle-v1",
        "parent_run_id": parent_run_id,
        "decisions": records,
    }
    input_id = content_id("unknownsingleinputs_", identity)
    manifest = {"schema_version": "1.0", "input_id": input_id, **identity}
    if archive_path.exists() or archive_path.is_symlink():
        raise UnknownSingleComponentInputError(
            "unknown-single-component archive output must be absent"
        )
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="nf-gtd-unknown-single-inputs-",
        dir="/tmp",
    ) as temporary:
        manifest_path = Path(temporary) / UNKNOWN_SINGLE_MANIFEST_NAME
        atomic_write_json(manifest_path, manifest)
        with tarfile.open(archive_path, mode="w") as archive:
            for name, path in members:
                _add_file(archive, name, path)
            _add_file(archive, UNKNOWN_SINGLE_MANIFEST_NAME, manifest_path)
    return UnknownSingleComponentInputBundle(
        input_id=input_id,
        parent_run_id=parent_run_id,
        crystal_ids=tuple(str(item["crystal_id"]) for item in records),
        archive_path=archive_path,
        archive_sha256=sha256_file(archive_path, progress=False),
        archive_size_bytes=archive_path.stat().st_size,
        decision_count=len(records),
    )


def validate_unknown_single_component_input_tree(
    root: Path,
    *,
    expected_input_id: str,
    expected_parent_run_id: str,
) -> tuple[str, ...]:
    """Authenticate one extracted A-seed decision archive."""

    if root.is_symlink():
        raise UnknownSingleComponentInputError(
            "unknown-single-component input tree must not be a symlink"
        )
    try:
        resolved = root.resolve(strict=True)
    except OSError as error:
        raise UnknownSingleComponentInputError(
            "unknown-single-component input tree is absent"
        ) from error
    manifest_path = resolved / UNKNOWN_SINGLE_MANIFEST_NAME
    try:
        manifest = load_json_document(manifest_path)
    except ContractLoadError as error:
        raise UnknownSingleComponentInputError(
            "unknown-single-component input manifest is malformed"
        ) from error
    if not isinstance(manifest, dict) or set(manifest) != {
        "schema_version",
        "input_id",
        "adapter_version",
        "parent_run_id",
        "decisions",
    }:
        raise UnknownSingleComponentInputError(
            "unknown-single-component input manifest fields differ"
        )
    identity = {
        "adapter_version": manifest.get("adapter_version"),
        "parent_run_id": manifest.get("parent_run_id"),
        "decisions": manifest.get("decisions"),
    }
    if (
        manifest.get("schema_version") != "1.0"
        or manifest.get("input_id") != expected_input_id
        or manifest.get("parent_run_id") != expected_parent_run_id
        or content_id("unknownsingleinputs_", identity) != expected_input_id
        or not isinstance(manifest.get("decisions"), list)
    ):
        raise UnknownSingleComponentInputError(
            "unknown-single-component input manifest identity differs"
        )
    decisions = manifest["decisions"]
    expected_names = {UNKNOWN_SINGLE_MANIFEST_NAME}
    crystal_ids: list[str] = []
    for record in decisions:
        if not isinstance(record, dict):
            raise UnknownSingleComponentInputError(
                "unknown-single-component decision inventory is malformed"
            )
        crystal_id = record.get("crystal_id")
        relative = record.get("relative_path")
        digest = record.get("sha256")
        size = record.get("size_bytes")
        if (
            not isinstance(crystal_id, str)
            or not isinstance(relative, str)
            or relative != f"decisions/{crystal_id}.tsv"
            or not isinstance(digest, str)
            or _CHECKSUM.fullmatch(digest) is None
            or not isinstance(size, int)
            or size < 1
            or relative in expected_names
        ):
            raise UnknownSingleComponentInputError(
                "unknown-single-component decision inventory is unsafe"
            )
        path = resolved / relative
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size != size
            or sha256_file(path, progress=False) != digest
        ):
            raise UnknownSingleComponentInputError(
                "unknown-single-component decision file changed"
            )
        decision = _load_decision(
            path,
            crystal_id=crystal_id,
            parent_run_id=expected_parent_run_id,
        )
        if decision.decision_file_id != record.get("decision_file_id"):
            raise UnknownSingleComponentInputError(
                "unknown-single-component decision identity changed"
            )
        expected_names.add(relative)
        crystal_ids.append(crystal_id)
    actual_names = {
        path.relative_to(resolved).as_posix()
        for path in resolved.rglob("*")
        if path.is_file()
    }
    if actual_names != expected_names or tuple(crystal_ids) != tuple(
        sorted(set(crystal_ids))
    ):
        raise UnknownSingleComponentInputError(
            "unknown-single-component input tree is incomplete or duplicated"
        )
    return tuple(crystal_ids)


def stage_unknown_single_component_handoff(
    *,
    parent_run_root: Path,
    child_run_root: Path,
    input_root: Path,
    child_run_id: str,
    expected_input_id: str,
) -> Path:
    """Build the owned registry, canonical A stages, and continuation routes."""

    parent = parent_run_root.resolve(strict=True)
    child = child_run_root.resolve(strict=True)
    parent_run_id = parent.name
    crystal_ids = validate_unknown_single_component_input_tree(
        input_root,
        expected_input_id=expected_input_id,
        expected_parent_run_id=parent_run_id,
    )
    try:
        result = load_json_document(parent / "state/job-result.json")
    except ContractLoadError as error:
        raise UnknownSingleComponentInputError(
            "unknown-screen parent terminal result is malformed"
        ) from error
    if (
        not isinstance(result, dict)
        or result.get("run_id") != parent_run_id
        or result.get("profile") != "unknown-screen"
        or result.get("scheduler_state") != "COMPLETED"
        or result.get("failure_class") != "success"
        or result.get("exit_code") != 0
        or not isinstance(result.get("completed_at"), str)
    ):
        raise UnknownSingleComponentInputError(
            "unknown-screen parent lacks successful terminal evidence"
        )
    try:
        completed_at = datetime.fromisoformat(
            str(result["completed_at"]).replace("Z", "+00:00")
        )
    except ValueError as error:
        raise UnknownSingleComponentInputError(
            "unknown-screen parent completion time is invalid"
        ) from error
    execution_identity = (
        parent / "artifacts/unknown-screen/inputs/phase3_execution_identity.json"
    )
    package_root = parent / "artifacts/unknown-screen/results"
    sources: list[OwnedPhaseIIIReviewPackageSource] = []
    for package in sorted(package_root.glob("phase3_owned_a_review_*")):
        manifest = validate_phase3_review_package(package)
        if manifest.checkpoint is not PhaseIIIReviewCheckpoint.A_SEED:
            raise UnknownSingleComponentInputError(
                "unknown-screen retained a non-A package in its A inventory"
            )
        sources.append(
            OwnedPhaseIIIReviewPackageSource(
                crystal_id=manifest.crystal_id,
                checkpoint=manifest.checkpoint,
                package_directory=package,
            )
        )
    if not sources or not set(crystal_ids).issubset(
        {source.crystal_id for source in sources}
    ):
        raise UnknownSingleComponentInputError(
            "unknown-screen parent lacks a decided A package"
        )
    output = child / "artifacts/unknown-single-component"
    if output.exists() or output.is_symlink():
        raise UnknownSingleComponentInputError(
            "unknown-single-component handoff output already exists"
        )
    output.mkdir(parents=True)
    registry = output / "owned_run_registry"
    registry.mkdir()
    registered = register_phase3_owned_run(
        parent=OwnedPhaseIIIParentRun(
            run_id=parent_run_id,
            profile="unknown-screen",
            phase="phase3-pass1",
        ),
        completed_at=completed_at,
        execution_identity=execution_identity,
        packages=tuple(sources),
        output_directory=registry,
    )
    stages = output / "a_seed_stages"
    hypotheses_root = output / "hypotheses"
    stages.mkdir()
    hypotheses_root.mkdir()
    routes: list[dict[str, str]] = []
    stage_records: list[dict[str, str]] = []
    for crystal_id in crystal_ids:
        decision = input_root / f"decisions/{crystal_id}.tsv"
        stage = stage_unknown_pass1_selected_a_seeds(
            owned_run_registry=registry,
            owned_run_id=parent_run_id,
            decisions=decision,
            confirmed_decisions_sha256=sha256_file(decision, progress=False),
            output_directory=stages / crystal_id,
            progress=False,
        )
        hypotheses_source = (
            package_root
            / "phase3"
            / crystal_id
            / "diverse_first_copy_funnel"
            / "mr_hypotheses.jsonl"
        )
        if hypotheses_source.is_symlink() or not hypotheses_source.is_file():
            raise UnknownSingleComponentInputError(
                f"unknown-screen hypotheses are absent for {crystal_id}"
            )
        hypotheses = hypotheses_root / f"{crystal_id}.jsonl"
        shutil.copy2(hypotheses_source, hypotheses)
        routes.append(
            {
                "crystal_id": crystal_id,
                "review_stage": f"a_seed_stages/{crystal_id}",
                "hypotheses": f"hypotheses/{crystal_id}.jsonl",
            }
        )
        stage_records.append(
            {
                "crystal_id": crystal_id,
                "stage_id": stage.stage_id,
                "stage_manifest_sha256": sha256_file(
                    stage.stage_manifest,
                    progress=False,
                ),
            }
        )
    reviewed_manifest = output / "reviewed_crystals.json"
    atomic_write_json(
        reviewed_manifest,
        {"schema_version": "1.0", "crystals": routes},
    )
    atomic_write_json(
        output / "unknown_single_component_stage_manifest.json",
        {
            "schema_version": "1.0",
            "adapter_version": "unknown-single-component-stage-v1",
            "child_run_id": child_run_id,
            "parent_run_id": parent_run_id,
            "input_id": expected_input_id,
            "owned_run_registry_id": registered.owned_run_registry_id,
            "execution_identity_id": registered.execution_identity_id,
            "crystal_ids": list(crystal_ids),
            "stages": stage_records,
            "reviewed_crystals_sha256": sha256_file(
                reviewed_manifest,
                progress=False,
            ),
        },
    )
    return output


def main() -> int:
    """Validate or materialise one remote continuation handoff."""

    parser = argparse.ArgumentParser()
    actions = parser.add_subparsers(dest="action", required=True)
    validate = actions.add_parser("validate")
    validate.add_argument("--input-root", type=Path, required=True)
    validate.add_argument("--expected-input-id", required=True)
    validate.add_argument("--expected-parent-run-id", required=True)
    stage = actions.add_parser("stage-handoff")
    stage.add_argument("--parent-run-root", type=Path, required=True)
    stage.add_argument("--child-run-root", type=Path, required=True)
    stage.add_argument("--input-root", type=Path, required=True)
    stage.add_argument("--child-run-id", required=True)
    stage.add_argument("--expected-input-id", required=True)
    args = parser.parse_args()
    if args.action == "validate":
        validate_unknown_single_component_input_tree(
            args.input_root,
            expected_input_id=args.expected_input_id,
            expected_parent_run_id=args.expected_parent_run_id,
        )
    else:
        stage_unknown_single_component_handoff(
            parent_run_root=args.parent_run_root,
            child_run_root=args.child_run_root,
            input_root=args.input_root,
            child_run_id=args.child_run_id,
            expected_input_id=args.expected_input_id,
        )
    return 0


__all__ = [
    "UNKNOWN_SINGLE_MANIFEST_NAME",
    "UNKNOWN_SINGLE_SPEC_RELATIVE",
    "UnknownSingleComponentInputBundle",
    "UnknownSingleComponentInputError",
    "build_unknown_single_component_input_bundle",
    "stage_unknown_single_component_handoff",
    "validate_unknown_single_component_input_tree",
]


if __name__ == "__main__":
    sys.exit(main())
