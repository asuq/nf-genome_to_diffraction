"""Verify one extracted truth-isolated M6 runner bundle.

This runner-side step has no access to the truth protocol.  It validates the
opaque 63-case manifest, content-addressed object inventory, FASTA/MTZ/JSON
media contracts, candidate-retention policy, and observation-column states.
It emits one bounded qualification record and never invokes a network service
or a scientific external executable.  Missing, changed, malformed, symlinked,
or unreferenced objects fail the whole qualification.

The runner-manifest checksum is the cache key.  Focused unit tests cover a
valid bundle plus checksum and policy failure paths; Viper execution validates
the real Pixi/Gemmi environment and the staged 63-case archive.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Self

import gemmi
from Bio import SeqIO
from pydantic import Field, model_validator

from genome_to_diffraction.benchmarks.public_control import PublicControlError
from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.diffraction.preflight import select_observations
from genome_to_diffraction.ids import canonical_sequence
from genome_to_diffraction.schemas.base import (
    ContractModel,
    OperatorIdentifier,
    PositiveInt,
    Sha256Hex,
)
from genome_to_diffraction.schemas.io import load_json_document
from genome_to_diffraction.schemas.manifests import PipelineConfig
from genome_to_diffraction.time import utc_now_iso

_LOCUS_ID_RE = re.compile(r"^loc_[0-9a-f]{64}$")
_REQUIRED_ROLES = {
    "catalogue",
    "reflections",
    "analysis_config",
    "model_policy",
}


class M6RunnerObjectSpec(ContractModel):
    """One content-addressed object referenced by an opaque case."""

    role: Literal[
        "catalogue",
        "reflections",
        "analysis_config",
        "model_policy",
        "fault_control",
    ]
    object: Sha256Hex
    sha256: Sha256Hex
    size_bytes: PositiveInt
    media_type: Literal[
        "application/json",
        "application/x-mtz",
        "text/plain",
        "text/x-fasta",
    ]

    @model_validator(mode="after")
    def _validate_address(self) -> Self:
        if self.object != self.sha256:
            raise ValueError("runner object name must equal its SHA-256")
        return self


class M6RunnerCaseSpec(ContractModel):
    """One opaque M6 runner case and its role-specific objects."""

    case_id: str = Field(pattern=r"^M6C[0-9]{3}$")
    objects: tuple[M6RunnerObjectSpec, ...] = Field(min_length=4, max_length=5)

    @model_validator(mode="after")
    def _validate_roles(self) -> Self:
        roles = [item.role for item in self.objects]
        if len(roles) != len(set(roles)):
            raise ValueError("runner case object roles must be unique")
        if not set(roles) >= _REQUIRED_ROLES:
            raise ValueError("runner case lacks a required input role")
        return self


class M6RunnerInventorySpec(ContractModel):
    """The complete opaque runner manifest contract."""

    schema_version: Literal["1.0"]
    protocol_id: OperatorIdentifier
    case_count: Literal[63]
    object_count: PositiveInt
    objects: dict[Sha256Hex, dict[str, object]]
    cases: tuple[M6RunnerCaseSpec, ...] = Field(min_length=63, max_length=63)

    @model_validator(mode="after")
    def _validate_inventory(self) -> Self:
        case_ids = [case.case_id for case in self.cases]
        expected = [f"M6C{index:03d}" for index in range(1, 64)]
        if case_ids != expected:
            raise ValueError("runner case IDs must be the complete ordered matrix")
        referenced = {item.object for case in self.cases for item in case.objects}
        if set(self.objects) != referenced or self.object_count != len(referenced):
            raise ValueError("runner object inventory differs from case references")
        for digest, record in self.objects.items():
            if not isinstance(record, dict):
                raise ValueError("runner object inventory record must be an object")
            if record.get("sha256") != digest:
                raise ValueError("runner inventory object checksum differs from key")
        return self


@dataclass(frozen=True)
class M6RunnerVerificationRequest:
    """One extracted opaque runner root and qualification output path."""

    runner_root: Path
    output: Path


@dataclass(frozen=True)
class M6RunnerVerificationResult:
    """Stable identifiers and counts for one successful qualification."""

    qualification: Path
    qualification_sha256: str
    runner_manifest_sha256: str
    case_count: int
    object_count: int


def _load_manifest(path: Path) -> M6RunnerInventorySpec:
    try:
        payload = load_json_document(path)
        return M6RunnerInventorySpec.model_validate(payload)
    except (OSError, ValueError) as error:
        raise PublicControlError(f"invalid M6 runner manifest: {error}") from error


def _verify_json(path: Path) -> dict[str, object]:
    try:
        payload = load_json_document(path)
    except (OSError, ValueError) as error:
        raise PublicControlError(
            f"invalid M6 JSON object {path.name}: {error}"
        ) from error
    if not isinstance(payload, dict):
        raise PublicControlError(f"M6 JSON object is not a mapping: {path.name}")
    return payload


def _verify_catalogue(path: Path) -> int:
    try:
        records = tuple(SeqIO.parse(path, "fasta"))
    except (OSError, ValueError) as error:
        raise PublicControlError(
            f"invalid M6 FASTA object {path.name}: {error}"
        ) from error
    if not records:
        raise PublicControlError(f"M6 FASTA object is empty: {path.name}")
    identifiers = [record.id for record in records]
    if len(identifiers) != len(set(identifiers)):
        raise PublicControlError(f"M6 FASTA object has duplicate loci: {path.name}")
    if any(_LOCUS_ID_RE.fullmatch(identifier) is None for identifier in identifiers):
        raise PublicControlError(
            f"M6 FASTA object exposes a non-opaque locus: {path.name}"
        )
    for record in records:
        try:
            canonical_sequence(str(record.seq))
        except ValueError as error:
            raise PublicControlError(
                f"M6 FASTA object has an invalid protein sequence: {path.name}"
            ) from error
    return len(records)


def _verify_reflections(path: Path) -> dict[str, object]:
    try:
        mtz = gemmi.read_mtz_file(str(path))
        selected, _, warnings = select_observations(mtz, None)
    except (OSError, RuntimeError, ValueError) as error:
        raise PublicControlError(
            f"invalid M6 MTZ object {path.name}: {error}"
        ) from error
    return {
        "selected_observation_labels": (
            None if selected is None else selected.rendered
        ),
        "selected_observation_type": (
            None if selected is None else selected.observation_type
        ),
        "warning_codes": list(warnings),
        "reflection_count": mtz.nreflections,
        "column_count": len(mtz.columns),
    }


def _object_path(root: Path, spec: M6RunnerObjectSpec) -> Path:
    path = root / "objects" / spec.object
    if path.is_symlink():
        raise PublicControlError(f"M6 runner object is a symlink: {spec.object}")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise PublicControlError(
            f"M6 runner object is missing: {spec.object}"
        ) from error
    if not resolved.is_file() or resolved.parent != (root / "objects").resolve():
        raise PublicControlError(f"M6 runner object path is unsafe: {spec.object}")
    if resolved.stat().st_size != spec.size_bytes:
        raise PublicControlError(f"M6 runner object size changed: {spec.object}")
    if sha256_file(resolved) != spec.sha256:
        raise PublicControlError(f"M6 runner object checksum changed: {spec.object}")
    return resolved


def verify_m6_runner_bundle(
    request: M6RunnerVerificationRequest,
) -> M6RunnerVerificationResult:
    """Validate one extracted opaque bundle and emit bounded qualification."""

    root = request.runner_root.resolve(strict=True)
    if request.output.resolve().is_relative_to(root):
        raise PublicControlError("M6 qualification output must remain outside runner")
    manifest_path = root / "runner_manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise PublicControlError("M6 runner manifest is missing or unsafe")
    manifest = _load_manifest(manifest_path)
    expected_files = {
        Path("runner_manifest.json"),
        *(Path("objects") / digest for digest in manifest.objects),
    }
    actual_files = {
        path.relative_to(root)
        for path in root.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    if actual_files != expected_files:
        raise PublicControlError("M6 runner contains missing or unreferenced objects")

    verified: dict[str, Path] = {}
    for case in manifest.cases:
        for spec in case.objects:
            if spec.object not in verified:
                verified[spec.object] = _object_path(root, spec)

    case_records: list[dict[str, object]] = []
    all_retained = True
    score_policy_valid = True
    for case in manifest.cases:
        by_role = {item.role: item for item in case.objects}
        catalogue_count = _verify_catalogue(verified[by_role["catalogue"].object])
        reflections = _verify_reflections(verified[by_role["reflections"].object])
        config_payload = _verify_json(verified[by_role["analysis_config"].object])
        try:
            config = PipelineConfig.model_validate(config_payload)
        except ValueError as error:
            raise PublicControlError(
                f"invalid M6 analysis configuration for {case.case_id}"
            ) from error
        policy = _verify_json(verified[by_role["model_policy"].object])
        if "fault_control" in by_role:
            _verify_json(verified[by_role["fault_control"].object])
        retained = (
            policy.get("candidate_policy") == "retain_all"
            and config.retention.retain_all_logs
        )
        score_ok = policy.get("score_policy") == "llg_tfz_annotations_only"
        all_retained = all_retained and retained
        score_policy_valid = score_policy_valid and score_ok
        case_records.append(
            {
                "case_id": case.case_id,
                "roles": sorted(by_role),
                "catalogue_sequence_count": catalogue_count,
                "candidate_policy": policy.get("candidate_policy"),
                "score_policy": policy.get("score_policy"),
                "model_policy_mode": policy.get("mode"),
                **reflections,
            }
        )
    if not all_retained:
        raise PublicControlError("M6 runner does not retain every candidate")
    if not score_policy_valid:
        raise PublicControlError("M6 runner applies an unapproved score policy")

    request.output.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(
        request.output,
        {
            "schema_version": "1.0",
            "adapter_version": "m6-runner-input-qualification-v1",
            "generated_at": utc_now_iso(),
            "protocol_id": manifest.protocol_id,
            "runner_manifest_sha256": sha256_file(manifest_path),
            "case_count": manifest.case_count,
            "object_count": manifest.object_count,
            "verified_object_count": len(verified),
            "all_candidates_retained": all_retained,
            "score_policy": "LLG/TFZ_are_ranking_annotations_only",
            "case_records": case_records,
        },
    )
    return M6RunnerVerificationResult(
        qualification=request.output.resolve(strict=True),
        qualification_sha256=sha256_file(request.output),
        runner_manifest_sha256=sha256_file(manifest_path),
        case_count=manifest.case_count,
        object_count=manifest.object_count,
    )
