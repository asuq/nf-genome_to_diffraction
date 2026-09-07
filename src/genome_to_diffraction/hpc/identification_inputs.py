"""Bounded, source-bound inputs for the explicitly selected identification screen.

This internal profile does not change the released hypothesis funnel. Its plan
accounts for every sequence in each supplied mass interval, including missing
models and work explicitly reserved to another run. All independent preparation
and MR computations are Nextflow tasks. Archive validation precedes extraction.
"""

import hashlib
import math
import os
import re
import tarfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

import gemmi
from pydantic import Field

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.matthews.enumerate import dynamic_copy_counts, prior_score
from genome_to_diffraction.schemas.base import ContractModel, Sha256Hex
from genome_to_diffraction.schemas.io import load_json_document, parse_json_document
from genome_to_diffraction.schemas.results import (
    SequenceGroupRecord,
    SourceProteinRecord,
    StructuralSearchHit,
)
from genome_to_diffraction.status import InputContractError

SPEC_RELATIVE = Path(".untracked/identification-marmic/input-root.json")
MANIFEST_NAME = "identification_input_manifest.json"
MAX_ARCHIVE_BYTES = 1024 * 1024 * 1024
MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_FILES = 12000
MAX_CASES = 5000
SAFE_NAME = r"[A-Za-z0-9][A-Za-z0-9_.-]*"
MEMBER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./-]*$")


class IdentificationInputError(InputContractError):
    """Identification input identity, completeness or confinement is invalid."""


class CrystalInput(ContractModel):
    """Explicit original diffraction identity and optional experimental prior."""

    crystal_id: str = Field(pattern=f"^{SAFE_NAME}$")
    mtz: str
    mtz_sha256: Sha256Hex
    observation_labels: str
    free_r_test_value: int
    space_group: str
    asu_volume_a3: float = Field(gt=0)
    resolution_high_a: float = Field(gt=0)
    reflection_count: int = Field(gt=0)
    symmetry_multiplicity: int = Field(gt=0)
    minimum_mass_da: float = Field(gt=0)
    maximum_mass_da: float = Field(gt=0)


class IdentificationCase(ContractModel):
    """One protein hypothesis, or an explicit non-executed inventory row."""

    case_id: str = Field(pattern=r"^identcase_[a-f0-9]{64}$")
    crystal_id: str = Field(pattern=f"^{SAFE_NAME}$")
    sequence_group_id: str = Field(pattern=r"^seq_[a-f0-9]{64}$")
    accessions: tuple[str, ...] = Field(min_length=1)
    product: str
    mass_da: float = Field(gt=0)
    status: Literal["ready", "model_unavailable", "existing_work"]
    reason: str
    evidence_reference: str | None = None
    hit: StructuralSearchHit | None = None
    coordinate_file: str | None = None
    coordinate_sha256: Sha256Hex | None = None
    component_copies: int = Field(gt=0)
    search_copies: Literal[1] = 1
    copy_priors: tuple[dict[str, float | int], ...] = Field(min_length=1)


class IdentificationPlan(ContractModel):
    """Complete catalogue accounting without a globally truncated model pool."""

    schema_version: Literal["1.0"] = "1.0"
    adapter_version: Literal["identification-screen-v1"] = "identification-screen-v1"
    run_mode: Literal["smoke", "screen"] = "screen"
    discovery_package_id: str
    sequence_groups_sha256: Sha256Hex
    source_records_sha256: Sha256Hex
    crystals: tuple[CrystalInput, ...] = Field(min_length=1, max_length=3)
    cases: tuple[IdentificationCase, ...] = Field(min_length=1, max_length=MAX_CASES)


def execution_cases(plan: IdentificationPlan) -> tuple[IdentificationCase, ...]:
    """Run all ready cases, or one deterministic representative per crystal."""

    ready = tuple(
        sorted(
            (c for c in plan.cases if c.status == "ready"),
            key=lambda c: (c.crystal_id, c.case_id),
        )
    )
    if plan.run_mode == "screen":
        return ready
    selected = {}
    for case in ready:
        selected.setdefault(case.crystal_id, case)
    return tuple(selected.values())


@dataclass(frozen=True, slots=True)
class IdentificationInputBundle:
    """One validated tar stream for a single immutable source commit."""

    input_id: str
    archive_path: Path
    archive_sha256: str
    archive_size_bytes: int
    file_count: int


def safe_member(root: Path, name: str) -> Path:
    """Resolve an existing regular, non-symlink file below an explicit root."""

    relative = PurePosixPath(name)
    if (
        not MEMBER_RE.fullmatch(name)
        or relative.is_absolute()
        or any(part in {"", ".", ".."} for part in relative.parts)
        or relative.as_posix() != name
    ):
        raise IdentificationInputError("unsafe identification member name")
    candidate = root / name
    if (
        candidate.is_symlink()
        or not candidate.is_file()
        or not candidate.resolve().is_relative_to(root.resolve())
        or root.is_symlink()
        or any(
            (root / Path(*relative.parts[:i])).is_symlink()
            for i in range(1, len(relative.parts))
        )
    ):
        raise IdentificationInputError(f"unsafe or absent identification file: {name}")
    if not 0 < candidate.stat().st_size <= MAX_FILE_BYTES:
        raise IdentificationInputError(
            f"identification file size outside bound: {name}"
        )
    return candidate


def read_groups(path: Path) -> dict[str, SequenceGroupRecord]:
    """Load canonical sequence identities without duplicate or empty records."""

    rows = [
        SequenceGroupRecord.model_validate_json(line)
        for line in path.read_text().splitlines()
    ]
    groups = {r.sequence_group_id: r for r in rows}
    if not rows or len(rows) != len(groups):
        raise IdentificationInputError("empty or duplicated catalogue sequence groups")
    return groups


def expected_case_id(crystal: CrystalInput, group_id: str) -> str:
    """Identify a candidate independently of ranking, scheduler or result."""

    return content_id(
        "identcase_",
        {
            "crystal_id": crystal.crystal_id,
            "mtz_sha256": crystal.mtz_sha256,
            "sequence_group_id": group_id,
        },
    )


def copy_priors(
    crystal: CrystalInput, mass: float
) -> tuple[int, tuple[dict[str, float | int], ...]]:
    """Reuse the existing complete Matthews range and prior, searching one copy."""

    counts, warnings = dynamic_copy_counts(
        v_asu_a3=crystal.asu_volume_a3,
        mass_lower_da=mass,
        mass_upper_da=mass,
        minimum_solvent_fraction=0.10,
        maximum_solvent_fraction=0.90,
    )
    if warnings or not counts:
        raise IdentificationInputError("candidate has no valid complete Matthews range")
    priors: list[dict[str, float | int]] = []
    for count in counts:
        vm = crystal.asu_volume_a3 / (mass * count)
        solvent = 1 - 1.23 / vm
        priors.append(
            {
                "copies": count,
                "vm": vm,
                "solvent_fraction": solvent,
                "prior": prior_score(
                    solvent,
                    resolution_high_a=crystal.resolution_high_a,
                    copy_count=count,
                ),
            }
        )
    best = max(priors, key=lambda row: (row["prior"], -row["copies"]))
    return int(best["copies"]), tuple(priors)


def validate_plan(
    root: Path, *, allowed_mtz_root: Path | None = None
) -> IdentificationPlan:
    """Require exact interval coverage, catalogue mapping, models and diffraction."""

    plan = IdentificationPlan.model_validate_json(
        safe_member(root, "plan.json").read_text()
    )
    group_path = safe_member(root, "sequence_groups.jsonl")
    sources = safe_member(root, "source_records.jsonl")
    if (
        sha256_file(group_path) != plan.sequence_groups_sha256
        or sha256_file(sources) != plan.source_records_sha256
    ):
        raise IdentificationInputError("catalogue bytes differ from the plan")
    groups = read_groups(group_path)
    if any(group.molecular_mass_da is None for group in groups.values()):
        raise IdentificationInputError(
            "unknown catalogue mass requires an explicit scope disposition"
        )
    source_rows = [
        SourceProteinRecord.model_validate_json(line)
        for line in sources.read_text().splitlines()
    ]
    if not source_rows or len({r.source_record_id for r in source_rows}) != len(
        source_rows
    ):
        raise IdentificationInputError("source catalogue is empty or duplicated")
    if (
        len({r.catalogue_id for r in source_rows}) != 1
        or len({r.source_annotation_provider for r in source_rows}) != 1
    ):
        raise IdentificationInputError(
            "identification requires one consistent catalogue and annotation source"
        )
    accessions: dict[str, set[str]] = {}
    source_counts = Counter(source.sequence_group_id for source in source_rows)
    if any(
        source_counts[group.sequence_group_id] != group.source_record_count
        for group in groups.values()
    ):
        raise IdentificationInputError(
            "sequence-group source-record counts differ from the catalogue"
        )
    for source in source_rows:
        if source.sequence_group_id not in groups:
            raise IdentificationInputError("source catalogue has an unknown sequence")
        accessions.setdefault(source.sequence_group_id, set()).add(
            source.original_protein_id
        )
    crystals = {c.crystal_id: c for c in plan.crystals}
    if len(crystals) != len(plan.crystals):
        raise IdentificationInputError("duplicate crystal scope")
    expected = set()
    for crystal in plan.crystals:
        if crystal.minimum_mass_da > crystal.maximum_mass_da:
            raise IdentificationInputError("reversed candidate mass interval")
        for group in groups.values():
            if (
                group.molecular_mass_da is not None
                and crystal.minimum_mass_da
                <= group.molecular_mass_da
                <= crystal.maximum_mass_da
            ):
                expected.add((crystal.crystal_id, group.sequence_group_id))
        if allowed_mtz_root is not None:
            mtz_path = Path(crystal.mtz)
            if (
                mtz_path.is_symlink()
                or not mtz_path.is_file()
                or not mtz_path.resolve().is_relative_to(allowed_mtz_root.resolve())
            ):
                raise IdentificationInputError(
                    "diffraction path escapes the approved root"
                )
            if sha256_file(mtz_path) != crystal.mtz_sha256:
                raise IdentificationInputError("original diffraction bytes changed")
            mtz = gemmi.read_mtz_file(str(mtz_path))
            if (
                mtz.spacegroup is None
                or mtz.spacegroup.hm != crystal.space_group
                or mtz.nreflections != crystal.reflection_count
                or any(
                    label not in mtz.column_labels()
                    for label in crystal.observation_labels.split(",")
                )
            ):
                raise IdentificationInputError(
                    "diffraction metadata differs from the plan"
                )
            multiplicity = len(mtz.spacegroup.operations())
            if (
                multiplicity != crystal.symmetry_multiplicity
                or not math.isclose(
                    mtz.cell.volume / multiplicity, crystal.asu_volume_a3, rel_tol=1e-9
                )
                or not math.isclose(
                    mtz.resolution_high(), crystal.resolution_high_a, rel_tol=1e-7
                )
            ):
                raise IdentificationInputError(
                    "diffraction volume, symmetry or resolution differs"
                )
    actual = {(c.crystal_id, c.sequence_group_id) for c in plan.cases}
    if actual != expected or len(actual) != len(plan.cases):
        raise IdentificationInputError(
            "candidate inventory omits or duplicates interval members"
        )
    for case in plan.cases:
        crystal = crystals[case.crystal_id]
        group = groups[case.sequence_group_id]
        if set(case.accessions) != accessions.get(case.sequence_group_id) or len(
            case.accessions
        ) != len(set(case.accessions)):
            raise IdentificationInputError(
                "candidate accession mapping differs from the catalogue"
            )
        if (
            case.case_id != expected_case_id(crystal, group.sequence_group_id)
            or case.mass_da != group.molecular_mass_da
        ):
            raise IdentificationInputError(
                "candidate identity or sequence mass differs"
            )
        copies, priors = copy_priors(crystal, case.mass_da)
        # Preserve exact staged bytes, but allow only round-off when an ARM
        # planner and an x86 worker independently evaluate the pinned NumPy KDE.
        priors_agree = len(case.copy_priors) == len(priors) and all(
            set(observed) == set(expected)
            and observed["copies"] == expected["copies"]
            and all(
                math.isclose(
                    float(observed[key]),
                    float(expected[key]),
                    rel_tol=1e-12,
                    abs_tol=1e-15,
                )
                for key in ("vm", "solvent_fraction", "prior")
            )
            for observed, expected in zip(case.copy_priors, priors, strict=False)
        )
        if case.component_copies != copies or not priors_agree:
            raise IdentificationInputError("candidate Matthews plan differs")
        if not case.reason.strip():
            raise IdentificationInputError("candidate disposition requires a reason")
        if case.status == "existing_work" and not case.evidence_reference:
            raise IdentificationInputError(
                "existing work must name its explicit evidence"
            )
        if case.status == "ready":
            if (
                case.hit is None
                or case.hit.sequence_identity is None
                or case.coordinate_file is None
                or case.coordinate_sha256 is None
                or case.hit.sequence_group_id != case.sequence_group_id
                or case.hit.eligibility_status != "selected"
            ):
                raise IdentificationInputError(
                    "ready candidate lacks eligible model identity"
                )
            coordinate = safe_member(root, case.coordinate_file)
            if sha256_file(coordinate) != case.coordinate_sha256:
                raise IdentificationInputError("coordinate checksum differs")
    return plan


def validate_bound_input_root(
    root: Path, *, expected_input_id: str, source_commit: str, allowed_mtz_root: Path
) -> IdentificationPlan:
    """Recheck the staged content identity before any candidate tasks are emitted."""

    manifest = load_json_document(safe_member(root, MANIFEST_NAME))
    if not isinstance(manifest, dict) or set(manifest) != {
        "input_id",
        "schema_version",
        "source_commit",
        "files",
    }:
        raise IdentificationInputError("invalid staged identification manifest")
    payload = {k: v for k, v in manifest.items() if k != "input_id"}
    if (
        manifest["input_id"] != expected_input_id
        or content_id("identificationinputs_", payload) != expected_input_id
        or manifest["source_commit"] != source_commit
    ):
        raise IdentificationInputError(
            "staged identification source or content changed"
        )
    rows = manifest["files"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_FILES:
        raise IdentificationInputError("staged file inventory is invalid")
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("relative_path"), str):
            raise IdentificationInputError("staged file record is invalid")
        path = safe_member(root, row["relative_path"])
        if sha256_file(path) != row.get("sha256") or path.stat().st_size != row.get(
            "size_bytes"
        ):
            raise IdentificationInputError("staged input file changed before execution")
    return validate_plan(root, allowed_mtz_root=allowed_mtz_root)


def build_identification_input_bundle(
    *, repository: Path, archive_path: Path, source_commit: str
) -> IdentificationInputBundle:
    """Build one bounded archive from the explicit private input-root spec."""

    spec_path = repository / SPEC_RELATIVE
    if (
        spec_path.is_symlink()
        or not spec_path.is_file()
        or spec_path.stat().st_uid != os.getuid()
        or spec_path.stat().st_size > 32768
        or spec_path.stat().st_mode & 0o777 != 0o600
    ):
        raise IdentificationInputError("identification input spec must be mode 0600")
    spec = load_json_document(spec_path)
    if (
        not isinstance(spec, dict)
        or set(spec) != {"schema_version", "input_root"}
        or spec["schema_version"] != "1.0"
        or not isinstance(spec["input_root"], str)
    ):
        raise IdentificationInputError("invalid identification input-root spec")
    root = Path(spec["input_root"])
    return build_identification_archive(
        root=root, archive_path=archive_path, source_commit=source_commit
    )


def build_identification_archive(
    *, root: Path, archive_path: Path, source_commit: str
) -> IdentificationInputBundle:
    """Build the shared archive format from an explicitly selected input root."""

    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise IdentificationInputError(
            "identification input root is not a regular absolute directory"
        )
    plan = validate_plan(root)
    names = {"plan.json", "sequence_groups.jsonl", "source_records.jsonl"}
    names.update(
        c.coordinate_file
        for c in plan.cases
        if c.status == "ready" and c.coordinate_file is not None
    )
    files = [
        {
            "relative_path": name,
            "sha256": sha256_file(safe_member(root, name)),
            "size_bytes": safe_member(root, name).stat().st_size,
        }
        for name in sorted(names)
    ]
    if (
        len(files) > MAX_FILES
        or sum(int(row["size_bytes"]) for row in files)
        > MAX_ARCHIVE_BYTES - 16 * 1024 * 1024
    ):
        raise IdentificationInputError(
            "identification archive exceeds its fixed bounds"
        )
    if re.fullmatch(r"[a-f0-9]{40}", source_commit) is None:
        raise IdentificationInputError("invalid identification source commit")
    payload = {"schema_version": "1.0", "source_commit": source_commit, "files": files}
    input_id = content_id("identificationinputs_", payload)
    manifest = {"input_id": input_id, **payload}
    manifest_path = archive_path.with_suffix(".manifest.json")
    atomic_write_json(manifest_path, manifest)
    with tarfile.open(archive_path, "x") as archive:
        for name, path in [
            (MANIFEST_NAME, manifest_path),
            *((name, safe_member(root, name)) for name in sorted(names)),
        ]:
            info = tarfile.TarInfo(name)
            info.size = path.stat().st_size
            info.mode = 0o444
            with path.open("rb") as handle:
                archive.addfile(info, handle)
    return IdentificationInputBundle(
        input_id,
        archive_path,
        sha256_file(archive_path),
        archive_path.stat().st_size,
        len(files) + 1,
    )


def unpack_identification_archive(
    archive_path: Path,
    root: Path,
    *,
    expected_input_id: str,
    source_commit: str,
    allowed_mtz_root: Path,
) -> IdentificationPlan:
    """Reject links, traversal, duplicates and oversized members before any write."""

    if root.exists() or archive_path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise IdentificationInputError(
            "input destination exists or archive exceeds bound"
        )
    with tarfile.open(archive_path, "r:") as archive:
        members = archive.getmembers()
        names = [m.name for m in members]
        if (
            len(names) != len(set(names))
            or not 1 <= len(names) <= MAX_FILES
            or sum(m.size for m in members) > MAX_ARCHIVE_BYTES
        ):
            raise IdentificationInputError(
                "invalid archive cardinality or expanded size"
            )
        for member in members:
            relative = PurePosixPath(member.name)
            if (
                not member.isfile()
                or not 0 < member.size <= MAX_FILE_BYTES
                or not MEMBER_RE.fullmatch(member.name)
                or relative.is_absolute()
                or ".." in relative.parts
                or relative.as_posix() != member.name
            ):
                raise IdentificationInputError("unsafe archive member")
        if MANIFEST_NAME not in names:
            raise IdentificationInputError("input archive manifest absent")
        manifest_file = archive.extractfile(MANIFEST_NAME)
        if manifest_file is None:
            raise IdentificationInputError("input archive manifest absent")
        manifest = parse_json_document(
            manifest_file.read().decode("utf-8"), label=MANIFEST_NAME
        )
        if not isinstance(manifest, dict) or set(manifest) != {
            "input_id",
            "schema_version",
            "source_commit",
            "files",
        }:
            raise IdentificationInputError("invalid input archive manifest")
        payload = {k: v for k, v in manifest.items() if k != "input_id"}
        if (
            manifest["schema_version"] != "1.0"
            or manifest["input_id"] != expected_input_id
            or content_id("identificationinputs_", payload) != expected_input_id
            or manifest["source_commit"] != source_commit
        ):
            raise IdentificationInputError("input archive ownership differs")
        file_rows = manifest["files"]
        if not isinstance(file_rows, list) or any(
            not isinstance(r, dict)
            or set(r) != {"relative_path", "sha256", "size_bytes"}
            or not isinstance(r["relative_path"], str)
            or not isinstance(r["sha256"], str)
            or re.fullmatch(r"[a-f0-9]{64}", r["sha256"]) is None
            or type(r["size_bytes"]) is not int
            for r in file_rows
        ):
            raise IdentificationInputError("invalid input file inventory")
        expected = {r["relative_path"]: r for r in file_rows}
        if len(expected) != len(file_rows) or set(names) != {MANIFEST_NAME, *expected}:
            raise IdentificationInputError("archive has missing or unlisted files")
        for member in members:
            if member.name == MANIFEST_NAME:
                continue
            handle = archive.extractfile(member)
            if handle is None:
                raise IdentificationInputError("archive file is unreadable")
            digest = hashlib.sha256()
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
            if (
                digest.hexdigest() != expected[member.name]["sha256"]
                or member.size != expected[member.name]["size_bytes"]
            ):
                raise IdentificationInputError("archive file checksum or size differs")
        root.mkdir()
        archive.extractall(root, filter="data")
    return validate_plan(root, allowed_mtz_root=allowed_mtz_root)
