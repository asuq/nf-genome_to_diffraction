"""Collect a checksum-closed three-crystal Phase III pass-1 terminal panel."""

import html
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import gemmi
from pydantic import ValidationError

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.ids import canonical_json_bytes
from genome_to_diffraction.review import (
    PhaseIIIReviewPackageError,
    validate_phase3_review_package,
)
from genome_to_diffraction.schemas.base import ContractModel
from genome_to_diffraction.schemas.results import (
    BriefRefinementResult,
    CopyCountAssessment,
    NormalisedMrResult,
    SequenceMapResult,
)
from genome_to_diffraction.schemas.v2 import (
    PhaseIIIReviewCheckpoint,
    PhaseIIIReviewDecisionFile,
    UnknownPass1CollectedFile,
    UnknownPass1CollectedFileKind,
    UnknownPass1CrossChecksumManifest,
    UnknownPass1CrystalAssessment,
    UnknownPass1CrystalChecksumManifest,
    UnknownPass1FinalMetricsEvidence,
    UnknownPass1PanelSummary,
    UnknownPass1ScientificStatus,
    UnknownPass1TerminalEvidence,
)
from genome_to_diffraction.schemas.v2.review import validate_phase3_review_relative_path
from genome_to_diffraction.status import ExecutionStatus, InputContractError

_ADAPTER = "unknown-pass1-local-collector-v2"
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
                solution.refined_coordinate_sha256,
                solution.refined_mtz_sha256,
                solution.review_map_sha256,
                solution.refinement_evidence_sha256,
                solution.sequence_evidence_sha256,
                solution.parsed_final_metrics_evidence_sha256,
            )
            if value is not None
        )
    return digests


def _validate_review_sources(
    assessment: UnknownPass1CrystalAssessment,
    sources: list[tuple[UnknownPass1EvidenceSource, Path]],
) -> dict[PhaseIIIReviewCheckpoint, set[str]]:
    paths_by_digest: dict[str, list[Path]] = {}
    declared_paths: set[Path] = set()
    for declared, path in sources:
        paths_by_digest.setdefault(declared.sha256, []).append(path)
        declared_paths.add(path)

    screen_parent: str | None = None
    package_digests: dict[PhaseIIIReviewCheckpoint, set[str]] = {}
    for evidence in assessment.review_evidence:
        package_paths = paths_by_digest.get(
            evidence.review_package_manifest_sha256,
            [],
        )
        decision_paths = paths_by_digest.get(evidence.decision_file_sha256, [])
        if len(package_paths) != 1 or len(decision_paths) != 1:
            raise UnknownPass1CollectionError(
                "review package or decision source is ambiguous"
            )
        package_path = package_paths[0]
        try:
            package = validate_phase3_review_package(package_path.parent)
            decision_file = PhaseIIIReviewDecisionFile.model_validate_json(
                decision_paths[0].read_bytes()
            )
        except (
            OSError,
            PhaseIIIReviewPackageError,
            ValidationError,
            ValueError,
        ) as error:
            raise UnknownPass1CollectionError(
                "review package or decision is not authentic schema-v2 evidence"
            ) from error

        if (
            package_path.name != "phase3_review_package_manifest.json"
            or package.review_package_id != evidence.review_package_id
            or package.checkpoint is not evidence.checkpoint
            or package.crystal_id != assessment.crystal_id
            or package.crystal_id != evidence.package_crystal_id
            or package.execution_identity_id != assessment.execution_identity_id
            or decision_file.decision_file_id != evidence.decision_file_id
            or decision_file.checkpoint is not package.checkpoint
            or decision_file.owned_parent_run_id != package.owned_parent_run_id
            or decision_file.review_package_id != package.review_package_id
            or decision_file.review_package_manifest_sha256
            != evidence.review_package_manifest_sha256
        ):
            raise UnknownPass1CollectionError(
                "review package or decision ownership differs from its assessment"
            )

        final_checkpoint = package.checkpoint in {
            PhaseIIIReviewCheckpoint.SEQUENCE,
            PhaseIIIReviewCheckpoint.COMPOSITION,
        }
        if final_checkpoint:
            if (
                package.owned_parent_run_id != assessment.owned_parent_run_id
                or package.parent_profile != "unknown-single-component"
            ):
                raise UnknownPass1CollectionError(
                    "review package has an unowned final-checkpoint parent"
                )
        elif (
            package.parent_profile != "unknown-screen"
            or package.owned_parent_run_id == assessment.owned_parent_run_id
            or (
                screen_parent is not None
                and package.owned_parent_run_id != screen_parent
            )
        ):
            raise UnknownPass1CollectionError(
                "review package has an inconsistent completed-screen parent"
            )
        else:
            screen_parent = package.owned_parent_run_id

        targets = tuple(
            target
            for target in package.permitted_targets
            if target.crystal_id == assessment.crystal_id
            and target.item_id == evidence.package_item_id
        )
        decisions = tuple(
            item
            for item in decision_file.decisions
            if item.crystal_id == evidence.decision_crystal_id
            and item.item_id == evidence.decision_item_id
        )
        if (
            len(targets) != 1
            or len(decisions) != 1
            or evidence.package_item_id != evidence.decision_item_id
            or decisions[0].decision is not evidence.decision
        ):
            raise UnknownPass1CollectionError(
                "review package target differs from its independent human decision"
            )

        for artifact in (*package.evidence_inventory, *package.review_tables):
            if package_path.parent / artifact.relative_path not in declared_paths:
                raise UnknownPass1CollectionError(
                    "review package contains undeclared evidence"
                )
            package_digests.setdefault(package.checkpoint, set()).add(
                artifact.sha256
            )
    return package_digests


def _scientific_source(
    sources: list[tuple[UnknownPass1EvidenceSource, Path]],
    *,
    digest: str | None,
    role: str,
) -> Path:
    matches = tuple(
        path
        for declared, path in sources
        if declared.kind is UnknownPass1CollectedFileKind.RESULT
        and declared.role == role
        and declared.sha256 == digest
    )
    if len(matches) != 1:
        raise UnknownPass1CollectionError(
            f"owned scientific {role} evidence is missing or ambiguous"
        )
    return matches[0]


def _scientific_contract[Record: ContractModel](
    sources: list[tuple[UnknownPass1EvidenceSource, Path]],
    *,
    digest: str | None,
    role: str,
    schema: type[Record],
) -> Record:
    path = _scientific_source(sources, digest=digest, role=role)
    try:
        return schema.model_validate_json(path.read_bytes())
    except (OSError, ValidationError, ValueError) as error:
        raise UnknownPass1CollectionError(
            f"owned scientific {role} evidence violates its authoritative contract"
        ) from error


def _validate_scientific_assets(
    *,
    combined: Path,
    refined: Path,
    mtz_path: Path,
    map_path: Path,
) -> None:
    try:
        for path in (combined, refined):
            structure = gemmi.read_structure(str(path))
            atom_count = sum(
                len(residue)
                for model in structure
                for chain in model
                for residue in chain
            )
            if atom_count < 1:
                raise ValueError("coordinates contain no atoms")
        mtz = gemmi.read_mtz_file(str(mtz_path))
        columns = {column.label: column.type for column in mtz.columns}
        required_columns = {
            "2FOFCWT": "F",
            "PH2FOFCWT": "P",
            "FOFCWT": "F",
            "PHFOFCWT": "P",
        }
        if mtz.nreflections < 1 or any(
            columns.get(label) != kind for label, kind in required_columns.items()
        ):
            raise ValueError("refined MTZ lacks reflections or review-map coefficients")
        review_map = gemmi.read_ccp4_map(str(map_path))
        if min(review_map.grid.nu, review_map.grid.nv, review_map.grid.nw) < 1:
            raise ValueError("review map grid is empty")
    except (OSError, RuntimeError, ValueError) as error:
        raise UnknownPass1CollectionError(
            "owned scientific coordinate, MTZ, or review-map evidence is invalid"
        ) from error


def _validate_scientific_sources(
    assessment: UnknownPass1CrystalAssessment,
    sources: list[tuple[UnknownPass1EvidenceSource, Path]],
    package_digests: dict[PhaseIIIReviewCheckpoint, set[str]],
) -> None:
    terminal = _scientific_contract(
        sources,
        digest=assessment.terminal_evidence_sha256,
        role="terminal_result",
        schema=UnknownPass1TerminalEvidence,
    )
    solution = assessment.solution_evidence
    if (
        terminal.owned_parent_run_id != assessment.owned_parent_run_id
        or terminal.execution_identity_id != assessment.execution_identity_id
        or terminal.crystal_id != assessment.crystal_id
        or terminal.execution_status is not assessment.execution_status
        or terminal.candidate_shortlist_present
        is not assessment.candidate_shortlist_present
        or terminal.state_id != (solution.state_id if solution is not None else None)
        or terminal.sequence_group_id
        != (solution.sequence_group_id if solution is not None else None)
    ):
        raise UnknownPass1CollectionError(
            "owned terminal scientific evidence differs from its assessment"
        )

    if assessment.scientific_status not in {
        UnknownPass1ScientificStatus.CREDIBLE_SINGLE_COMPONENT_SOLUTION,
        UnknownPass1ScientificStatus.CREDIBLE_PARTIAL_OR_RESIDUAL,
    }:
        return
    if solution is None:
        raise UnknownPass1CollectionError("credible scientific solution is missing")
    required_checkpoints = {
        PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
        PhaseIIIReviewCheckpoint.A_SEED,
        PhaseIIIReviewCheckpoint.SEQUENCE,
        PhaseIIIReviewCheckpoint.COMPOSITION,
    }
    if not required_checkpoints.issubset(package_digests):
        raise UnknownPass1CollectionError(
            "credible solution lacks every specialised review package"
        )
    packaged_science = set().union(
        package_digests[PhaseIIIReviewCheckpoint.A_SEED],
        package_digests[PhaseIIIReviewCheckpoint.SEQUENCE],
        package_digests[PhaseIIIReviewCheckpoint.COMPOSITION],
    )
    required_packaged_science = {
        value
        for value in (
            solution.copy_support_evidence_sha256,
            solution.packing_evidence_sha256,
            solution.combined_coordinate_sha256,
            solution.refined_coordinate_sha256,
            solution.refined_mtz_sha256,
            solution.review_map_sha256,
            solution.refinement_evidence_sha256,
            solution.sequence_evidence_sha256,
        )
        if value is not None
    }
    if not required_packaged_science.issubset(packaged_science):
        raise UnknownPass1CollectionError(
            "credible scientific evidence is absent from its owned review packages"
        )

    copies = _scientific_contract(
        sources,
        digest=solution.copy_support_evidence_sha256,
        role="copy_support",
        schema=CopyCountAssessment,
    )
    packing = _scientific_contract(
        sources,
        digest=solution.packing_evidence_sha256,
        role="packing",
        schema=NormalisedMrResult,
    )
    refinement = _scientific_contract(
        sources,
        digest=solution.refinement_evidence_sha256,
        role="refinement",
        schema=BriefRefinementResult,
    )
    sequence = _scientific_contract(
        sources,
        digest=solution.sequence_evidence_sha256,
        role="sequence_map",
        schema=SequenceMapResult,
    )
    metrics = _scientific_contract(
        sources,
        digest=solution.parsed_final_metrics_evidence_sha256,
        role="final_metrics",
        schema=UnknownPass1FinalMetricsEvidence,
    )

    if (
        copies.seed_solution_id != solution.state_id
        or copies.sequence_group_id != solution.sequence_group_id
        or copies.expected_copy_count != solution.requested_copy_count
        or copies.best_supported_copy_count != solution.observed_copy_count
        or not copies.reached_expected_copy_count
        or copies.final_execution_status is not ExecutionStatus.COMPLETED_HIT
        or not copies.final_top_solution_packed
        or copies.final_placement_count != solution.observed_copy_count
        or not solution.copy_counts_supported
    ):
        raise UnknownPass1CollectionError(
            "scientific copy support differs from the owned crystal state"
        )

    packed_count = packing.packing_summary.get("packed_solution_count")
    if (
        packing.hypothesis_id != copies.hypothesis_id
        or packing.execution_status is not ExecutionStatus.COMPLETED_HIT
        or packing.placed_copy_count != solution.observed_copy_count
        or packing.packing_summary.get("top_solution_packed") is not True
        or isinstance(packed_count, bool)
        or not isinstance(packed_count, int)
        or packed_count < 1
        or packing.solution_coordinate_sha256 != solution.combined_coordinate_sha256
        or not solution.packing_passed
    ):
        raise UnknownPass1CollectionError(
            "scientific Phaser evidence does not establish observed packed copies"
        )

    if (
        refinement.seed_solution_id != solution.state_id
        or refinement.sequence_group_id != solution.sequence_group_id
        or refinement.input_copy_count != solution.observed_copy_count
        or refinement.execution_status
        not in {ExecutionStatus.COMPLETED_SUCCESS, ExecutionStatus.COMPLETED_WARNING}
        or refinement.refined_model_sha256 != solution.refined_coordinate_sha256
        or refinement.refined_mtz_sha256 != solution.refined_mtz_sha256
        or refinement.map_sha256 != solution.review_map_sha256
        or refinement.final_r_work != solution.final_r_work
        or refinement.final_r_free != solution.final_r_free
        or not solution.refinement_completed
    ):
        raise UnknownPass1CollectionError(
            "scientific refinement evidence differs from the owned crystal state"
        )

    if (
        sequence.seed_solution_id != solution.state_id
        or sequence.refinement_id != refinement.refinement_id
        or sequence.execution_status is not ExecutionStatus.COMPLETED_HIT
        or not any(
            candidate.sequence_group_id == solution.sequence_group_id
            and candidate.refinement_id == refinement.refinement_id
            for candidate in sequence.candidates
        )
    ):
        raise UnknownPass1CollectionError(
            "scientific sequence-map evidence does not support the approved group"
        )

    if (
        metrics.owned_parent_run_id != assessment.owned_parent_run_id
        or metrics.execution_identity_id != assessment.execution_identity_id
        or metrics.crystal_id != assessment.crystal_id
        or metrics.state_id != solution.state_id
        or metrics.sequence_group_id != solution.sequence_group_id
        or metrics.refinement_id != refinement.refinement_id
        or metrics.final_r_work != refinement.final_r_work
        or metrics.final_r_free != refinement.final_r_free
        or metrics.residual_content_state is not solution.residual_content_state
    ):
        raise UnknownPass1CollectionError(
            "scientific final metrics or residual evidence lacks exact ownership"
        )

    _validate_scientific_assets(
        combined=_scientific_source(
            sources,
            digest=solution.combined_coordinate_sha256,
            role="combined_coordinate",
        ),
        refined=_scientific_source(
            sources,
            digest=solution.refined_coordinate_sha256,
            role="refined_coordinate",
        ),
        mtz_path=_scientific_source(
            sources,
            digest=solution.refined_mtz_sha256,
            role="refined_mtz",
        ),
        map_path=_scientific_source(
            sources,
            digest=solution.review_map_sha256,
            role="review_map",
        ),
    )


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
        if path in used_paths:
            raise UnknownPass1CollectionError("evidence source path is duplicated")
        used_paths.add(path)
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
        package_digests = _validate_review_sources(assessments[crystal], sources)
        _validate_scientific_sources(
            assessments[crystal],
            sources,
            package_digests,
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
