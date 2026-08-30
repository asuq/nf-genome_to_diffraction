"""Build and validate the fixed private Phase III pass-2 input archive.

The local mode-0600 spec points to one prepared run-owned directory. The
builder rejects symlinks, path escapes, undeclared fields, an incomplete frozen
crystal panel, stale closure evidence, cross-parent assessments, execution
identities that differ from the staged commit/tree, and a ledger that differs
from that exact source before creating a deterministic archive. The extracted
validator repeats every byte, contract, closure, parent, and source check. No
scheduler or external scientific tool is invoked.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from pydantic import ValidationError

from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.execution.finding_closure import (
    PhaseIIIFindingClosureEvidenceFiles,
    validate_phase3_finding_closure,
)
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.localisation import (
    BatchLocalisationReopenPlan,
    BatchLocalisationReopenStatus,
)
from genome_to_diffraction.schemas.io import ContractLoadError, load_json_document
from genome_to_diffraction.schemas.results import MrHypothesis
from genome_to_diffraction.schemas.v2 import (
    CompositionState,
    PhaseIIIExecutionIdentity,
    UnknownPass1CrystalAssessment,
    UnknownPass1ScientificStatus,
)
from genome_to_diffraction.status import InputContractError

PASS2_SPEC_RELATIVE = Path(".untracked/phase3-unknown-pass2/pass2-inputs.json")
PASS2_SOURCE_MANIFEST = "phase3_pass2_source.json"
PASS2_INPUT_MANIFEST = "phase3_pass2_input_manifest.json"
_ADAPTER = "phase3-pass2-input-bundle-v2"
_MAX_SPEC_BYTES = 16 * 1024
_MAX_FILE_COUNT = 50_000
_MAX_ARCHIVE_BYTES = 8 * 1024 * 1024 * 1024
_CHECKSUM = re.compile(r"^[a-f0-9]{64}$")
_CRYSTALS = {
    "AD4QS1P4G2_18",
    "CD4QS2P2G1_15",
    "CD6QS2P2G1_5",
}
_SPEC_KEYS = {"schema_version", "input_root", "source_manifest_sha256"}
_GLOBAL_KEYS = {
    "schema_version",
    "finding_closure",
    "finding_ledger",
    "adverse_review_evidence",
    "integration_gate_evidence",
    "known_control_evidence",
    "m6_evidence",
    "unknown_pass1_evidence",
    "exact_source_ci_evidence",
    "items",
}
_ITEM_KEYS = {
    "crystal_id",
    "mode",
    "pass1_assessment",
    "no_a_expansion_plan",
    "parent_states",
    "sequence_groups",
    "localisation_policy",
    "active_wave_completion",
    "localisation_reopen_plan",
    "gel_evidence",
    "preflight",
    "model_registry",
    "model_ranking_evidence",
    "diffraction_selection",
    "free_r_identity",
    "fixed_coordinate_root",
    "execution_identity",
    "mtz",
    "phenix_manifest",
    "source_records",
    "matthews",
    "pipeline_config",
}
_DIRECTORY_KEYS = {"fixed_coordinate_root", "no_a_expansion_plan"}


class UnknownPass2InputError(InputContractError):
    """The fixed pass-2 private input authority is unsafe or incomplete."""


@dataclass(frozen=True, slots=True)
class UnknownPass2InputBundle:
    """One deterministic closure-gated pass-2 input archive."""

    input_id: str
    archive_path: Path
    archive_sha256: str
    archive_size_bytes: int
    file_count: int
    crystal_ids: tuple[str, ...]
    source_commit: str
    source_tree: str
    parent_run_id: str
    finding_ledger_sha256: str
    execution_identity_id: str
    finding_closure_id: str


def _owned_spec(path: Path) -> dict[str, object]:
    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_uid != os.getuid()
        or path.stat().st_mode & 0o777 != 0o600
        or not 1 <= path.stat().st_size <= _MAX_SPEC_BYTES
    ):
        raise UnknownPass2InputError("pass-2 spec must be an owned mode-0600 file")
    try:
        document = load_json_document(path)
    except ContractLoadError as error:
        raise UnknownPass2InputError("pass-2 spec is malformed") from error
    if (
        not isinstance(document, dict)
        or set(document) != _SPEC_KEYS
        or document.get("schema_version") != "1.0"
        or not isinstance(document.get("input_root"), str)
        or not str(document["input_root"]).startswith("/")
        or not isinstance(document.get("source_manifest_sha256"), str)
        or _CHECKSUM.fullmatch(str(document["source_manifest_sha256"])) is None
    ):
        raise UnknownPass2InputError("pass-2 spec fields are invalid")
    return document


def _root(path: Path) -> Path:
    if path.is_symlink():
        raise UnknownPass2InputError("pass-2 input root must not be a symlink")
    try:
        root = path.resolve(strict=True)
    except OSError as error:
        raise UnknownPass2InputError("pass-2 input root is absent") from error
    if not root.is_dir():
        raise UnknownPass2InputError("pass-2 input root must be a directory")
    return root


def _relative(value: object, *, label: str) -> PurePosixPath:
    if not isinstance(value, str):
        raise UnknownPass2InputError(f"{label} path is invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise UnknownPass2InputError(f"{label} path is unsafe")
    return path


def _path(root: Path, relative: PurePosixPath, *, directory: bool = False) -> Path:
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise UnknownPass2InputError("pass-2 input path contains a symlink")
    try:
        resolved = current.resolve(strict=True)
    except OSError as error:
        raise UnknownPass2InputError("pass-2 input path is absent") from error
    if (
        not resolved.is_relative_to(root)
        or (directory and not resolved.is_dir())
        or (not directory and not resolved.is_file())
    ):
        raise UnknownPass2InputError("pass-2 input path has the wrong type")
    return resolved


def _source_manifest(root: Path, expected_sha256: str) -> dict[str, object]:
    path = _path(root, PurePosixPath(PASS2_SOURCE_MANIFEST))
    if sha256_file(path) != expected_sha256:
        raise UnknownPass2InputError("pass-2 source manifest checksum differs")
    try:
        document = load_json_document(path)
    except ContractLoadError as error:
        raise UnknownPass2InputError("pass-2 source manifest is malformed") from error
    if (
        not isinstance(document, dict)
        or set(document) != _GLOBAL_KEYS
        or document.get("schema_version") != "1.0"
        or not isinstance(document.get("items"), list)
        or not 1 <= len(document["items"]) <= len(_CRYSTALS)
    ):
        raise UnknownPass2InputError("pass-2 source manifest fields are invalid")
    return document


def _inventory(root: Path) -> tuple[tuple[str, Path, str, int], ...]:
    rows = []
    total = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise UnknownPass2InputError("pass-2 input tree contains a symlink")
        if not path.is_file() or path.name == PASS2_INPUT_MANIFEST:
            continue
        relative = path.relative_to(root).as_posix()
        size = path.stat().st_size
        total += size
        rows.append((relative, path, sha256_file(path), size))
    if not 1 <= len(rows) <= _MAX_FILE_COUNT or total > _MAX_ARCHIVE_BYTES:
        raise UnknownPass2InputError("pass-2 input tree exceeds its fixed bounds")
    return tuple(rows)


def _validate_source(
    root: Path,
    source: dict[str, object],
    *,
    expected_source_commit: str,
    expected_source_tree: str,
    expected_parent_run_id: str,
    expected_finding_ledger_sha256: str,
) -> tuple[tuple[str, ...], PhaseIIIExecutionIdentity, str]:
    global_paths = {
        key: _path(root, _relative(source[key], label=key))
        for key in _GLOBAL_KEYS - {"schema_version", "items"}
    }
    identities: list[PhaseIIIExecutionIdentity] = []
    crystal_ids: list[str] = []
    raw_items = source.get("items")
    if not isinstance(raw_items, list):
        raise UnknownPass2InputError("pass-2 crystal items are invalid")
    for raw in raw_items:
        if not isinstance(raw, dict) or set(raw) != _ITEM_KEYS:
            raise UnknownPass2InputError("pass-2 crystal item fields are invalid")
        crystal_id = raw.get("crystal_id")
        if not isinstance(crystal_id, str) or crystal_id not in _CRYSTALS:
            raise UnknownPass2InputError("pass-2 crystal identity is invalid")
        crystal_ids.append(crystal_id)
        mode = raw.get("mode")
        if mode not in {"composition_beam", "no_a_expansion"}:
            raise UnknownPass2InputError("pass-2 item mode is invalid")
        paths = {}
        for key in _ITEM_KEYS - {"crystal_id", "mode"}:
            value = raw[key]
            if key == "no_a_expansion_plan" and value is None:
                continue
            paths[key] = _path(
                root,
                _relative(value, label=f"{crystal_id} {key}"),
                directory=key in _DIRECTORY_KEYS,
            )
        try:
            identity = PhaseIIIExecutionIdentity.model_validate_json(
                paths["execution_identity"].read_bytes()
            )
            assessment = UnknownPass1CrystalAssessment.model_validate_json(
                paths["pass1_assessment"].read_bytes()
            )
            states = tuple(
                CompositionState.model_validate_json(line)
                for line in paths["parent_states"].read_text().splitlines()
                if line.strip()
            )
        except (OSError, UnicodeError, ValidationError, ValueError) as error:
            raise UnknownPass2InputError(
                f"pass-2 execution/state contract differs for {crystal_id}"
            ) from error
        adapters = dict(identity.adapter_versions)
        required_adapters = {
            "phase3_all_model_registry": "all-eligible-model-registry-v3",
            "phase3_component_coordinates": (
                "phaser-component-coordinate-inventory-v2"
            ),
            "phase3_composition_attempt": ("phase3-composition-attempt-execution-v1"),
            "phase3_composition_beam": "phase3-composition-beam-depth-v1",
            "phase3_composition_depth": "phase3-composition-depth-input-v1",
            "phase3_no_a_expansion": "phase3-no-a-expansion-v2",
            "phase3_pass2_a_seed": "phase3-pass2-a-seed-v1",
        }
        if any(
            adapters.get(name) != version for name, version in required_adapters.items()
        ):
            raise UnknownPass2InputError(
                f"pass-2 execution adapters differ for {crystal_id}"
            )
        if (
            assessment.crystal_id != crystal_id
            or assessment.execution_identity_id != identity.execution_identity_id
            or assessment.owned_parent_run_id != expected_parent_run_id
        ):
            raise UnknownPass2InputError(f"pass-2 assessment differs for {crystal_id}")
        credible = assessment.scientific_status in {
            UnknownPass1ScientificStatus.CREDIBLE_SINGLE_COMPONENT_SOLUTION,
            UnknownPass1ScientificStatus.CREDIBLE_PARTIAL_OR_RESIDUAL,
        }
        if mode == "composition_beam" and (
            not credible or "no_a_expansion_plan" in paths or not 1 <= len(states) <= 3
        ):
            raise UnknownPass2InputError(
                f"pass-2 composition parent authority differs for {crystal_id}"
            )
        if mode == "no_a_expansion" and (credible or states):
            raise UnknownPass2InputError(
                f"pass-2 no-A authority differs for {crystal_id}"
            )
        if any(
            state.crystal_id != crystal_id
            or state.depth != 1
            or state.support_state.value
            not in {
                "packed",
                "refined",
                "review_supported",
                "composition_supported",
            }
            for state in states
        ):
            raise UnknownPass2InputError(
                f"pass-2 parent beam is invalid for {crystal_id}"
            )
        if mode == "no_a_expansion":
            plan_root = paths.get("no_a_expansion_plan")
            if plan_root is None:
                raise UnknownPass2InputError(
                    f"pass-2 no-A plan is absent for {crystal_id}"
                )
            try:
                plan = BatchLocalisationReopenPlan.model_validate_json(
                    (plan_root / "localisation_reopen_plan.json").read_bytes()
                )
                hypotheses = tuple(
                    MrHypothesis.model_validate_json(line)
                    for line in (plan_root / "reopened_hypotheses.jsonl")
                    .read_text()
                    .splitlines()
                    if line.strip()
                )
            except (OSError, UnicodeError, ValidationError, ValueError) as error:
                raise UnknownPass2InputError(
                    f"pass-2 no-A plan is invalid for {crystal_id}"
                ) from error
            if (
                plan.status is not BatchLocalisationReopenStatus.READY
                or plan.reopened_hypothesis_count != len(hypotheses)
                or tuple(item.hypothesis_id for item in hypotheses)
                != plan.reopened_hypothesis_ids
                or any(item.crystal_id != crystal_id for item in hypotheses)
            ):
                raise UnknownPass2InputError(
                    f"pass-2 no-A inventory differs for {crystal_id}"
                )
        mtz_sha256 = sha256_file(paths["mtz"])
        mtz_artifacts = tuple(
            artifact
            for artifact in identity.crystal_artifacts
            if artifact.owner_id == crystal_id and artifact.role == "mtz"
        )
        if (
            len(mtz_artifacts) != 1
            or mtz_artifacts[0].sha256 != mtz_sha256
            or mtz_artifacts[0].size_bytes != paths["mtz"].stat().st_size
            or any(state.diffraction_sha256 != mtz_sha256 for state in states)
        ):
            raise UnknownPass2InputError(
                f"pass-2 MTZ/execution authority differs for {crystal_id}"
            )
        identities.append(identity)
    if tuple(sorted(crystal_ids)) != tuple(sorted(_CRYSTALS)):
        raise UnknownPass2InputError(
            "pass-2 source must contain the exact three-crystal panel"
        )
    execution_ids = {item.execution_identity_id for item in identities}
    if len(execution_ids) != 1:
        raise UnknownPass2InputError("pass-2 crystal items use different executions")
    first = identities[0]
    if (
        first.source_commit != expected_source_commit
        or first.source_tree != expected_source_tree
    ):
        raise UnknownPass2InputError(
            "pass-2 execution identity differs from the staged source"
        )
    if any(
        item.source_commit != expected_source_commit
        or item.source_tree != expected_source_tree
        for item in identities
    ):
        raise UnknownPass2InputError("pass-2 crystal items use another staged source")
    if (
        sha256_file(global_paths["finding_ledger"], progress=False)
        != expected_finding_ledger_sha256
    ):
        raise UnknownPass2InputError(
            "pass-2 finding ledger differs from the exact staged source"
        )
    closure = validate_phase3_finding_closure(
        global_paths["finding_closure"],
        global_paths["finding_ledger"],
        expected_source_commit=first.source_commit,
        expected_source_tree=first.source_tree,
        evidence_files=PhaseIIIFindingClosureEvidenceFiles(
            adverse_review=global_paths["adverse_review_evidence"],
            integration_gate=global_paths["integration_gate_evidence"],
            known_control_evidence=global_paths["known_control_evidence"],
            m6_evidence=global_paths["m6_evidence"],
            unknown_pass1_evidence=global_paths["unknown_pass1_evidence"],
            exact_source_ci_evidence=global_paths["exact_source_ci_evidence"],
        ),
    )
    return tuple(sorted(crystal_ids)), first, closure.closure_id


def _add_file(archive: tarfile.TarFile, name: str, source: Path) -> None:
    info = archive.gettarinfo(str(source), arcname=name)
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    info.mtime = 0
    info.mode = 0o600
    with source.open("rb") as stream:
        archive.addfile(info, stream)


def build_unknown_pass2_input_bundle(
    *,
    repository: Path,
    archive_path: Path,
    expected_source_commit: str,
    expected_source_tree: str,
    expected_parent_run_id: str,
    expected_finding_ledger_sha256: str,
) -> UnknownPass2InputBundle:
    """Validate the private source tree and create one deterministic tar archive."""

    spec = _owned_spec(repository / PASS2_SPEC_RELATIVE)
    root = _root(Path(str(spec["input_root"])))
    source = _source_manifest(root, str(spec["source_manifest_sha256"]))
    crystal_ids, identity, closure_id = _validate_source(
        root,
        source,
        expected_source_commit=expected_source_commit,
        expected_source_tree=expected_source_tree,
        expected_parent_run_id=expected_parent_run_id,
        expected_finding_ledger_sha256=expected_finding_ledger_sha256,
    )
    rows = _inventory(root)
    file_records = [
        {"relative_path": relative, "sha256": digest, "size_bytes": size}
        for relative, _, digest, size in rows
    ]
    identity_payload = {
        "adapter_version": _ADAPTER,
        "source_commit": expected_source_commit,
        "source_tree": expected_source_tree,
        "parent_run_id": expected_parent_run_id,
        "finding_ledger_sha256": expected_finding_ledger_sha256,
        "execution_identity_id": identity.execution_identity_id,
        "finding_closure_id": closure_id,
        "crystal_ids": list(crystal_ids),
        "source": source,
        "files": file_records,
    }
    input_id = content_id("phase3pass2inputs_", identity_payload)
    manifest = {
        "schema_version": "1.0",
        "input_id": input_id,
        **identity_payload,
    }
    if archive_path.exists() or archive_path.is_symlink():
        raise UnknownPass2InputError("pass-2 archive output must be absent")
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="nf-gtd-pass2-inputs-", dir="/tmp") as tmp:
        manifest_path = Path(tmp) / PASS2_INPUT_MANIFEST
        atomic_write_json(manifest_path, manifest)
        with tarfile.open(archive_path, mode="w") as archive:
            for relative, path, _, _ in rows:
                _add_file(archive, relative, path)
            _add_file(archive, PASS2_INPUT_MANIFEST, manifest_path)
    if archive_path.stat().st_size > _MAX_ARCHIVE_BYTES:
        raise UnknownPass2InputError("pass-2 archive exceeds its fixed bound")
    return UnknownPass2InputBundle(
        input_id=input_id,
        archive_path=archive_path,
        archive_sha256=sha256_file(archive_path),
        archive_size_bytes=archive_path.stat().st_size,
        file_count=len(rows) + 1,
        crystal_ids=crystal_ids,
        source_commit=expected_source_commit,
        source_tree=expected_source_tree,
        parent_run_id=expected_parent_run_id,
        finding_ledger_sha256=expected_finding_ledger_sha256,
        execution_identity_id=identity.execution_identity_id,
        finding_closure_id=closure_id,
    )


def validate_unknown_pass2_input_tree(
    root: Path,
    *,
    expected_input_id: str,
    expected_source_commit: str,
    expected_source_tree: str,
    expected_parent_run_id: str,
    expected_finding_ledger_sha256: str,
) -> UnknownPass2InputBundle:
    """Revalidate an extracted pass-2 archive and its complete file inventory."""

    checked_root = _root(root)
    manifest_path = _path(checked_root, PurePosixPath(PASS2_INPUT_MANIFEST))
    try:
        manifest = load_json_document(manifest_path)
    except ContractLoadError as error:
        raise UnknownPass2InputError("pass-2 input manifest is malformed") from error
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != "1.0"
        or manifest.get("adapter_version") != _ADAPTER
        or manifest.get("input_id") != expected_input_id
        or manifest.get("source_commit") != expected_source_commit
        or manifest.get("source_tree") != expected_source_tree
        or manifest.get("parent_run_id") != expected_parent_run_id
        or manifest.get("finding_ledger_sha256") != expected_finding_ledger_sha256
        or not isinstance(manifest.get("source"), dict)
        or not isinstance(manifest.get("files"), list)
    ):
        raise UnknownPass2InputError("pass-2 input manifest fields differ")
    declared = {}
    for raw in manifest["files"]:
        if not isinstance(raw, dict) or set(raw) != {
            "relative_path",
            "sha256",
            "size_bytes",
        }:
            raise UnknownPass2InputError("pass-2 file inventory is malformed")
        relative = _relative(raw["relative_path"], label="pass-2 file")
        path = _path(checked_root, relative)
        digest = raw["sha256"]
        size = raw["size_bytes"]
        if (
            not isinstance(digest, str)
            or _CHECKSUM.fullmatch(digest) is None
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
            or path.stat().st_size != size
            or sha256_file(path) != digest
            or relative.as_posix() in declared
        ):
            raise UnknownPass2InputError("pass-2 file inventory differs")
        declared[relative.as_posix()] = path
    actual = {
        path.relative_to(checked_root).as_posix()
        for path in checked_root.rglob("*")
        if path.is_file() and path != manifest_path
    }
    if actual != set(declared):
        raise UnknownPass2InputError("pass-2 extracted inventory is incomplete")
    crystal_ids, identity, closure_id = _validate_source(
        checked_root,
        manifest["source"],
        expected_source_commit=expected_source_commit,
        expected_source_tree=expected_source_tree,
        expected_parent_run_id=expected_parent_run_id,
        expected_finding_ledger_sha256=expected_finding_ledger_sha256,
    )
    rebuilt = content_id(
        "phase3pass2inputs_",
        {
            "adapter_version": _ADAPTER,
            "source_commit": expected_source_commit,
            "source_tree": expected_source_tree,
            "parent_run_id": expected_parent_run_id,
            "finding_ledger_sha256": expected_finding_ledger_sha256,
            "execution_identity_id": identity.execution_identity_id,
            "finding_closure_id": closure_id,
            "crystal_ids": list(crystal_ids),
            "source": manifest["source"],
            "files": manifest["files"],
        },
    )
    if rebuilt != expected_input_id:
        raise UnknownPass2InputError("pass-2 input identity cannot be re-derived")
    return UnknownPass2InputBundle(
        input_id=expected_input_id,
        archive_path=checked_root,
        archive_sha256="0" * 64,
        archive_size_bytes=0,
        file_count=len(declared) + 1,
        crystal_ids=crystal_ids,
        source_commit=expected_source_commit,
        source_tree=expected_source_tree,
        parent_run_id=expected_parent_run_id,
        finding_ledger_sha256=expected_finding_ledger_sha256,
        execution_identity_id=identity.execution_identity_id,
        finding_closure_id=closure_id,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--expected-input-id", required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-source-tree", required=True)
    parser.add_argument("--expected-parent-run-id", required=True)
    parser.add_argument("--expected-finding-ledger-sha256", required=True)
    parser.add_argument("--write-checksums", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        output = validate_unknown_pass2_input_tree(
            args.root,
            expected_input_id=args.expected_input_id,
            expected_source_commit=args.expected_source_commit,
            expected_source_tree=args.expected_source_tree,
            expected_parent_run_id=args.expected_parent_run_id,
            expected_finding_ledger_sha256=(args.expected_finding_ledger_sha256),
        )
    except (OSError, UnknownPass2InputError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    if args.write_checksums is not None:
        manifest_path = args.root / PASS2_INPUT_MANIFEST
        manifest = load_json_document(manifest_path)
        if not isinstance(manifest, dict) or not isinstance(
            manifest.get("files"), list
        ):
            print("pass-2 input manifest inventory is unavailable", file=sys.stderr)
            return 2
        rows = [
            f"{item['sha256']}  {item['relative_path']}\n"
            for item in manifest["files"]
            if isinstance(item, dict)
        ]
        rows.append(f"{sha256_file(manifest_path)}  {PASS2_INPUT_MANIFEST}\n")
        atomic_write_text(args.write_checksums, "".join(sorted(rows)))
    print(output.input_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
