"""Collect a checksum-closed three-crystal Phase III pass-1 terminal panel."""

import html
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from pydantic import ValidationError

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.ids import canonical_json_bytes
from genome_to_diffraction.schemas.v2 import (
    UnknownPass1CollectedFile,
    UnknownPass1CollectedFileKind,
    UnknownPass1CrossChecksumManifest,
    UnknownPass1CrystalAssessment,
    UnknownPass1CrystalChecksumManifest,
    UnknownPass1PanelSummary,
)
from genome_to_diffraction.schemas.v2.review import validate_phase3_review_relative_path
from genome_to_diffraction.status import InputContractError

_ADAPTER = "unknown-pass1-local-collector-v1"
_ASSESSMENTS = "unknown-pass1-assessments.jsonl"
_PANEL = "unknown-pass1-panel-summary.json"
_REPORT = "unknown-pass1-report.html"
_CROSS = "cross-crystal-checksum-manifest.json"
_CRYSTAL_MANIFEST = "checksum-manifest.json"
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_INPUT_KINDS = frozenset(
    {
        UnknownPass1CollectedFileKind.COMMAND,
        UnknownPass1CollectedFileKind.RESULT,
        UnknownPass1CollectedFileKind.EVIDENCE,
    }
)

PHASE3_UNKNOWN_CRYSTAL_IDS = (
    "AD4QS1P4G2_18",
    "CD4QS2P2G1_15",
    "CD6QS2P2G1_5",
)


class UnknownPass1CollectionError(InputContractError):
    """The terminal panel cannot be collected without weakening its contract."""


@dataclass(frozen=True, slots=True)
class UnknownPass1AssessmentSource:
    crystal_id: str
    relative_path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class UnknownPass1EvidenceSource:
    crystal_id: str
    kind: UnknownPass1CollectedFileKind
    role: str
    relative_path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class UnknownPass1CollectionRequest:
    input_root: Path
    assessment_sources: tuple[UnknownPass1AssessmentSource, ...]
    evidence_allow_list: tuple[UnknownPass1EvidenceSource, ...]
    output_directory: Path


def _line(value: object) -> bytes:
    return canonical_json_bytes(value) + b"\n"


def _root(path: Path, *, label: str, empty: bool = False) -> Path:
    if path.is_symlink():
        raise UnknownPass1CollectionError(f"{label} cannot be a symlink")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise UnknownPass1CollectionError(f"{label} is absent") from error
    if not resolved.is_dir() or (empty and any(resolved.iterdir())):
        requirement = "an empty directory" if empty else "a directory"
        raise UnknownPass1CollectionError(f"{label} must be {requirement}")
    return resolved


def _source(
    root: Path,
    *,
    relative_path: str,
    sha256: str,
    size_bytes: int,
) -> Path:
    if (
        not isinstance(size_bytes, int)
        or isinstance(size_bytes, bool)
        or size_bytes < 0
        or not isinstance(sha256, str)
        or _SHA256.fullmatch(sha256) is None
    ):
        raise UnknownPass1CollectionError("source checksum declaration is invalid")
    try:
        validate_phase3_review_relative_path(relative_path)
    except ValueError as error:
        raise UnknownPass1CollectionError("source path is unsafe") from error
    path = root
    for part in PurePosixPath(relative_path).parts:
        path /= part
        if path.is_symlink():
            raise UnknownPass1CollectionError("source path contains a symlink")
    try:
        path = path.resolve(strict=True)
    except OSError as error:
        raise UnknownPass1CollectionError("allow-listed source is absent") from error
    if not path.is_relative_to(root) or not path.is_file():
        raise UnknownPass1CollectionError("source is not a regular input file")
    if path.stat().st_size != size_bytes or sha256_file(path) != sha256:
        raise UnknownPass1CollectionError(
            "source differs from its checksum declaration"
        )
    return path


def _load_assessment(path: Path) -> UnknownPass1CrystalAssessment:
    try:
        item = UnknownPass1CrystalAssessment.model_validate_json(path.read_bytes())
    except (OSError, ValidationError, ValueError) as error:
        raise UnknownPass1CollectionError("assessment violates schema-v2") from error
    rebuilt = UnknownPass1CrystalAssessment.from_evidence(
        owned_parent_run_id=item.owned_parent_run_id,
        execution_identity_id=item.execution_identity_id,
        crystal_id=item.crystal_id,
        crystallographic_review_item_id=item.crystallographic_review_item_id,
        execution_status=item.execution_status,
        terminal_evidence_sha256=item.terminal_evidence_sha256,
        candidate_shortlist_present=item.candidate_shortlist_present,
        solution_evidence=item.solution_evidence,
        review_evidence=item.review_evidence,
    )
    if rebuilt != item:
        raise UnknownPass1CollectionError(
            "assessment identity/status cannot be re-derived"
        )
    return item


def _evidence_hashes(item: UnknownPass1CrystalAssessment) -> set[str]:
    digests = {item.terminal_evidence_sha256}
    for review in item.review_evidence:
        digests.update(
            (review.review_package_manifest_sha256, review.decision_file_sha256)
        )
    if item.solution_evidence is not None:
        solution = item.solution_evidence
        digests.update(
            value
            for value in (
                solution.copy_support_evidence_sha256,
                solution.packing_evidence_sha256,
                solution.combined_coordinate_sha256,
                solution.refined_mtz_sha256,
                solution.refinement_evidence_sha256,
                solution.parsed_final_metrics_evidence_sha256,
            )
            if value is not None
        )
    return digests


def _file(
    root: Path,
    relative_path: str,
    kind: UnknownPass1CollectedFileKind,
    role: str,
) -> UnknownPass1CollectedFile:
    path = root / relative_path
    return UnknownPass1CollectedFile(
        kind=kind,
        role=role,
        relative_path=relative_path,
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
    )


def _html(panel: UnknownPass1PanelSummary) -> bytes:
    rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(item.crystal_id)}</td>"
        f"<td>{html.escape(item.execution_status.value)}</td>"
        f"<td>{html.escape(item.scientific_status.value)}</td>"
        '<td><a href="crystals/'
        f'{html.escape(item.crystal_id)}/assessment.json">record</a></td>'
        "</tr>"
        for item in panel.assessments
    )
    return (
        '<!doctype html>\n<html lang="en"><meta charset="utf-8">'
        "<title>Phase III unknown pass 1</title><body>\n"
        "<h1>Phase III unknown-pass-1 terminal assessments</h1>\n"
        "<p><strong>Exploratory application; not validation.</strong> This report "
        "mirrors each assessment and makes no additional identity or composition "
        "claim.</p>\n"
        "<table><tr><th>Crystal</th><th>Execution</th><th>Scientific status</th>"
        f"<th>Record</th></tr>\n{rows}\n</table>\n</body></html>\n"
    ).encode()


def collect_unknown_pass1_panel(
    request: UnknownPass1CollectionRequest,
) -> UnknownPass1CrossChecksumManifest:
    """Collect exactly three independently revalidated terminal assessments."""

    input_root = _root(request.input_root, label="input root")
    output = _root(request.output_directory, label="output", empty=True)
    if output == input_root or output.is_relative_to(input_root):
        raise UnknownPass1CollectionError("output must remain outside the input root")
    if len(request.assessment_sources) != 3:
        raise UnknownPass1CollectionError("exactly three assessments are required")
    crystals = tuple(sorted(source.crystal_id for source in request.assessment_sources))
    if crystals != PHASE3_UNKNOWN_CRYSTAL_IDS:
        raise UnknownPass1CollectionError(
            "the fixed three unknown crystals are required"
        )

    used_paths: set[Path] = set()
    assessments: dict[str, UnknownPass1CrystalAssessment] = {}
    for declared in request.assessment_sources:
        path = _source(
            input_root,
            relative_path=declared.relative_path,
            sha256=declared.sha256,
            size_bytes=declared.size_bytes,
        )
        if path in used_paths:
            raise UnknownPass1CollectionError("assessment source is duplicated")
        used_paths.add(path)
        item = _load_assessment(path)
        if item.crystal_id != declared.crystal_id:
            raise UnknownPass1CollectionError("assessment crystal identity differs")
        assessments[declared.crystal_id] = item

    evidence: dict[str, list[tuple[UnknownPass1EvidenceSource, Path]]] = {
        crystal: [] for crystal in crystals
    }
    used_digests: set[str] = set()
    for declared in request.evidence_allow_list:
        if declared.crystal_id not in evidence or declared.kind not in _INPUT_KINDS:
            raise UnknownPass1CollectionError("evidence crystal or kind is invalid")
        if _IDENTIFIER.fullmatch(declared.role) is None:
            raise UnknownPass1CollectionError("evidence role is invalid")
        path = _source(
            input_root,
            relative_path=declared.relative_path,
            sha256=declared.sha256,
            size_bytes=declared.size_bytes,
        )
        if path in used_paths or declared.sha256 in used_digests:
            raise UnknownPass1CollectionError("duplicate or cross-crystal evidence")
        used_paths.add(path)
        used_digests.add(declared.sha256)
        evidence[declared.crystal_id].append((declared, path))
    for crystal, sources in evidence.items():
        roles = [declared.role for declared, _ in sources]
        relative_paths = [declared.relative_path for declared, _ in sources]
        if len(roles) != len(set(roles)) or len(relative_paths) != len(
            set(relative_paths)
        ):
            raise UnknownPass1CollectionError("per-crystal evidence is duplicated")
        available = {declared.sha256 for declared, _ in sources}
        if _evidence_hashes(assessments[crystal]) - available:
            raise UnknownPass1CollectionError(
                "assessment-referenced evidence is missing"
            )

    panel = UnknownPass1PanelSummary.from_assessments(
        (
            assessments[crystals[0]],
            assessments[crystals[1]],
            assessments[crystals[2]],
        )
    )
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        manifests = []
        cross_files = []
        for item in panel.assessments:
            base = f"crystals/{item.crystal_id}"
            assessment_relative = f"{base}/assessment.json"
            assessment_path = staging / assessment_relative
            assessment_path.parent.mkdir(parents=True)
            assessment_path.write_bytes(_line(item))
            files = [
                _file(
                    staging,
                    assessment_relative,
                    UnknownPass1CollectedFileKind.ASSESSMENT,
                    "assessment_record",
                )
            ]
            ordered_sources = sorted(
                evidence[item.crystal_id],
                key=lambda pair: (pair[0].kind.value, pair[0].role),
            )
            for declared, source_path in ordered_sources:
                relative = (
                    f"{base}/artifacts/{declared.kind.value}/{declared.role}/"
                    f"{PurePosixPath(declared.relative_path).name}"
                )
                destination = staging / relative
                destination.parent.mkdir(parents=True)
                shutil.copyfile(source_path, destination)
                if sha256_file(source_path) != declared.sha256 or (
                    sha256_file(destination) != declared.sha256
                ):
                    raise UnknownPass1CollectionError(
                        "evidence changed during collection"
                    )
                files.append(_file(staging, relative, declared.kind, declared.role))
            files_tuple = tuple(
                sorted(files, key=lambda value: (value.kind.value, value.role))
            )
            manifest = UnknownPass1CrystalChecksumManifest.from_content(
                adapter_version=_ADAPTER,
                owned_parent_run_id=panel.owned_parent_run_id,
                execution_identity_id=panel.execution_identity_id,
                crystal_id=item.crystal_id,
                assessment_id=item.assessment_id,
                execution_status=item.execution_status,
                scientific_status=item.scientific_status,
                files=files_tuple,
            )
            manifest_relative = f"{base}/{_CRYSTAL_MANIFEST}"
            (staging / manifest_relative).write_bytes(_line(manifest))
            manifests.append(manifest)
            cross_files.extend(files_tuple)
            cross_files.append(
                _file(
                    staging,
                    manifest_relative,
                    UnknownPass1CollectedFileKind.CRYSTAL_MANIFEST,
                    f"{item.crystal_id}_checksum_manifest",
                )
            )

        (staging / _ASSESSMENTS).write_bytes(
            b"".join(_line(item) for item in panel.assessments)
        )
        (staging / _PANEL).write_bytes(_line(panel))
        (staging / _REPORT).write_bytes(_html(panel))
        cross_files.extend(
            (
                _file(
                    staging,
                    _ASSESSMENTS,
                    UnknownPass1CollectedFileKind.ASSESSMENT_INVENTORY,
                    "canonical_assessments",
                ),
                _file(
                    staging,
                    _PANEL,
                    UnknownPass1CollectedFileKind.PANEL_SUMMARY,
                    "panel_summary",
                ),
                _file(
                    staging,
                    _REPORT,
                    UnknownPass1CollectedFileKind.HTML_REPORT,
                    "portable_html_report",
                ),
            )
        )
        cross = UnknownPass1CrossChecksumManifest.from_content(
            adapter_version=_ADAPTER,
            owned_parent_run_id=panel.owned_parent_run_id,
            execution_identity_id=panel.execution_identity_id,
            panel_id=panel.panel_id,
            crystal_manifest_ids=tuple(
                sorted(manifest.crystal_manifest_id for manifest in manifests)
            ),
            files=tuple(sorted(cross_files, key=lambda value: value.relative_path)),
            interpretation_boundary="exploratory_non_validation_assessment_mirror_only",
        )
        (staging / _CROSS).write_bytes(_line(cross))
        output.rmdir()
        os.replace(staging, output)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    return cross
