"""Prepare and assess the fixed P6 heteromer control slice.

The preparation helper reuses the accepted 6RTZ and 3U7Q control bundles.  It
creates a parent-only model registry for the missing-B plan, a checksum-bound
6RTZ-A/3U7Q-B wrong-partner bundle, and an explicit 9ECN
``unsupported_component_count`` record.  It performs no Phaser work.

The assessor consumes the retained P3--P6 records and writes one compact JSON
report.  Partner hits remain search evidence: neither packing nor a wrong-model
placement becomes a complete biological-composition claim.  Inputs and outputs
are checksum-addressed; malformed or inconsistent controls fail loudly.
"""

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from genome_to_diffraction.benchmarks.heteromer_control import (
    HeteromerControlPreparationError,
    _prepared_file,
)
from genome_to_diffraction.benchmarks.m6_protocol import load_m6_protocol
from genome_to_diffraction.checksums import (
    atomic_write_bytes,
    atomic_write_json,
    sha256_file,
)
from genome_to_diffraction.ids import canonical_json_text, content_id
from genome_to_diffraction.schemas.io import load_json_document
from genome_to_diffraction.schemas.results import (
    NormalisedMrResult,
    PartnerAttemptSummary,
    PartnerSearchPlan,
    PartnerSearchResult,
    ProcessedModelRecord,
    SequenceGroupRecord,
)
from genome_to_diffraction.status import ExecutionStatus

_ADAPTER_VERSION = "heteromer-p6-control-slice-v1"


@dataclass(frozen=True)
class HeteromerSlicePreparationRequest:
    """Frozen protocol and accepted 6RTZ/3U7Q preparation manifests."""

    protocol: Path
    control_6rtz_preparation: Path
    control_3u7q_preparation: Path
    output_directory: Path


@dataclass(frozen=True)
class HeteromerSlicePreparationResult:
    """Paths used by the missing-B, wrong-B, and 9ECN controls."""

    preparation_manifest: Path
    missing_partner_model_registry: Path
    wrong_partner_sequence_groups: Path
    wrong_partner_model: Path


@dataclass(frozen=True)
class HeteromerSliceAssessmentRequest:
    """All retained records required for the six fixed P6 cases."""

    preparation_manifest: Path
    positive_6rtz_result: Path
    positive_3u7q_result: Path
    missing_partner_plan: Path
    missing_partner_summary: Path
    wrong_partner_result: Path
    homomer_result: Path
    output_json: Path


@dataclass(frozen=True)
class HeteromerSliceAssessmentResult:
    """The accepted/rejected P6 report and its content identity."""

    report_json: Path
    report_id: str
    gate_passed: bool


def _document(path: Path, *, label: str) -> dict[str, Any]:
    value = load_json_document(path.resolve(strict=True))
    if not isinstance(value, dict):
        raise HeteromerControlPreparationError(f"{label} is not a JSON object")
    return value


def _model[T: BaseModel](path: Path, model: type[T], *, label: str) -> T:
    try:
        return model.model_validate_json(path.resolve(strict=True).read_text())
    except (OSError, ValidationError) as error:
        raise HeteromerControlPreparationError(f"invalid {label}") from error


def _groups(path: Path) -> dict[str, SequenceGroupRecord]:
    records: dict[str, SequenceGroupRecord] = {}
    with path.resolve(strict=True).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = SequenceGroupRecord.model_validate_json(line)
            except ValidationError as error:
                raise HeteromerControlPreparationError(
                    f"invalid sequence group at line {line_number}"
                ) from error
            if record.sequence_group_id in records:
                raise HeteromerControlPreparationError("duplicate sequence group")
            records[record.sequence_group_id] = record
    return records


def _exact_model(
    *,
    group: SequenceGroupRecord,
    source: Path,
    source_pdb_id: str,
    source_chain: str,
    registry: Path,
    flag: str,
) -> tuple[ProcessedModelRecord, Path, Path]:
    if group.molecular_mass_da is None:
        raise HeteromerControlPreparationError("control sequence lacks molecular mass")
    digest = sha256_file(source)
    model_path = registry / "models" / f"{digest}.pdb"
    atomic_write_bytes(model_path, source.read_bytes())
    mapping_id = content_id(
        "coordmap_",
        {
            "pdb_id": source_pdb_id,
            "chain": source_chain,
            "sequence_sha256": group.sha256,
        },
    )
    coordinate_id = content_id(
        "coord_", {"mapping_id": mapping_id, "model_sha256": digest}
    )
    record = ProcessedModelRecord(
        schema_version="1.0",
        model_id=content_id(
            "model_", {"coordinate_id": coordinate_id, "model_sha256": digest}
        ),
        coordinate_id=coordinate_id,
        variant_type="experimental_cleaned_source_chain",
        residue_ranges=(f"{source_chain}:polymer",),
        processing_tool="gemmi",
        processing_version="control-prepared",
        processing_parameters={
            "adapter_version": _ADAPTER_VERSION,
            "mapping_id": mapping_id,
            "sequence_identity": 1.0,
            "source_pdb_id": source_pdb_id,
            "source_chain": source_chain,
        },
        model_mass_da=group.molecular_mass_da,
        full_candidate_sequence_group_id=group.sequence_group_id,
        model_sha256=digest,
        quality_flags=(flag,),
    )
    processed = registry / "processed_models.jsonl"
    atomic_write_bytes(processed, f"{record.model_dump_json()}\n".encode())
    manifest = registry / "model_preparation_manifest.json"
    atomic_write_json(
        manifest,
        {
            "schema_version": "1.0",
            "adapter_version": _ADAPTER_VERSION,
            "processed_model_count": 1,
            "entries": [
                {
                    "model_id": record.model_id,
                    "model_path": model_path.relative_to(registry).as_posix(),
                    "model_sha256": digest,
                    "retained_fraction": 1.0,
                }
            ],
        },
    )
    return record, model_path, manifest


def prepare_heteromer_control_slice(
    request: HeteromerSlicePreparationRequest,
) -> HeteromerSlicePreparationResult:
    """Create the fixed missing/wrong/unsupported P6 control inputs."""

    output = request.output_directory.absolute()
    if output.exists() and any(output.iterdir()):
        raise HeteromerControlPreparationError(
            f"P6 control output is not empty: {output}"
        )
    control_6_path = request.control_6rtz_preparation.resolve(strict=True)
    control_3_path = request.control_3u7q_preparation.resolve(strict=True)
    control_6 = _document(control_6_path, label="6RTZ preparation")
    control_3 = _document(control_3_path, label="3U7Q preparation")
    if control_6.get("crystal_id") != "6RTZ" or control_3.get("crystal_id") != "3U7Q":
        raise HeteromerControlPreparationError(
            "P6 control preparation identity differs"
        )
    files_6 = control_6.get("files")
    files_3 = control_3.get("files")
    parent_id = control_6.get("parent_sequence_group_id")
    wrong_id = control_3.get("partner_sequence_group_id")
    wrong_identity = control_3.get("partner_model_identity_fraction")
    if not isinstance(parent_id, str) or not isinstance(wrong_id, str):
        raise HeteromerControlPreparationError("P6 control sequence IDs are absent")
    if (
        isinstance(wrong_identity, bool)
        or not isinstance(wrong_identity, int | float)
        or not math.isfinite(float(wrong_identity))
        or not 0 < float(wrong_identity) <= 1
    ):
        raise HeteromerControlPreparationError("P6 wrong-model identity is invalid")
    groups_6 = _groups(
        _prepared_file(control_6_path.parent, files_6, "sequence_groups")
    )
    groups_3 = _groups(
        _prepared_file(control_3_path.parent, files_3, "sequence_groups")
    )
    parent_group = groups_6.get(parent_id)
    wrong_group = groups_3.get(wrong_id)
    if parent_group is None or wrong_group is None or parent_id == wrong_id:
        raise HeteromerControlPreparationError("P6 control sequence mapping differs")
    parent_source = _prepared_file(control_6_path.parent, files_6, "parent_model")
    wrong_source = _prepared_file(control_3_path.parent, files_3, "partner_model")

    missing_registry = output / "missing_partner_model_registry"
    parent_model, parent_model_path, parent_model_manifest = _exact_model(
        group=parent_group,
        source=parent_source,
        source_pdb_id="6RTZ",
        source_chain="A",
        registry=missing_registry,
        flag="fixed_p6_parent_only_missing_partner_control",
    )
    wrong_root = output / "wrong_partner"
    wrong_groups = wrong_root / "sequence_groups.jsonl"
    atomic_write_bytes(
        wrong_groups,
        (
            f"{canonical_json_text(parent_group)}\n{canonical_json_text(wrong_group)}\n"
        ).encode(),
    )
    wrong_model = wrong_root / "model.pdb"
    atomic_write_bytes(wrong_model, wrong_source.read_bytes())

    protocol = load_m6_protocol(request.protocol)
    controls_9ecn = [
        item for item in protocol.assumption_controls if item.target_key == "A04"
    ]
    if len(controls_9ecn) != 1 or controls_9ecn[0].source.pdb_id != "9ECN":
        raise HeteromerControlPreparationError("fixed 9ECN control is absent")
    control_9ecn = controls_9ecn[0]
    if control_9ecn.asu_distinct_protein_species != 3:
        raise HeteromerControlPreparationError("9ECN component count changed")

    preparation = output / "preparation_manifest.json"
    recorded = {
        "missing_processed_models": missing_registry / "processed_models.jsonl",
        "missing_model_manifest": parent_model_manifest,
        "missing_parent_model": parent_model_path,
        "wrong_sequence_groups": wrong_groups,
        "wrong_partner_model": wrong_model,
    }
    atomic_write_json(
        preparation,
        {
            "schema_version": "1.0",
            "adapter_version": _ADAPTER_VERSION,
            "missing_partner": {
                "parent_sequence_group_id": parent_id,
                "selected_attempt_count_expected": 0,
                "complete_composition_claimed": False,
            },
            "wrong_partner": {
                "parent_sequence_group_id": parent_id,
                "partner_sequence_group_id": wrong_id,
                "partner_model_identity_fraction": float(wrong_identity),
                "complete_composition_claimed": False,
            },
            "homomer_non_regression": {
                "route": "first_copy",
                "complete_composition_claimed": False,
            },
            "unsupported_component_control": {
                "target_key": "A04",
                "pdb_id": "9ECN",
                "observed_component_count": 3,
                "supported_component_count": 2,
                "status": "unsupported_component_count",
                "retain_partial_a_b_evidence": True,
                "complete_composition_claimed": False,
            },
            "parent_model_id": parent_model.model_id,
            "files": {
                role: {
                    "path": path.relative_to(output).as_posix(),
                    "sha256": sha256_file(path),
                    "size_bytes": path.stat().st_size,
                }
                for role, path in recorded.items()
            },
        },
    )
    return HeteromerSlicePreparationResult(
        preparation_manifest=preparation,
        missing_partner_model_registry=missing_registry,
        wrong_partner_sequence_groups=wrong_groups,
        wrong_partner_model=wrong_model,
    )


def _positive_gate(result: PartnerSearchResult) -> bool:
    return (
        result.execution_status is ExecutionStatus.COMPLETED_HIT
        and result.partner_placement_count == result.requested_partner_copy_count
        and result.partner_placement_observed
        and result.top_solution_packed
        and result.score_cohort in {"primary", "fallback"}
    )


def assess_heteromer_control_slice(
    request: HeteromerSliceAssessmentRequest,
) -> HeteromerSliceAssessmentResult:
    """Validate the six P6 controls and write one bounded release-gate report."""

    preparation = _document(request.preparation_manifest, label="P6 preparation")
    if preparation.get("adapter_version") != _ADAPTER_VERSION:
        raise HeteromerControlPreparationError("P6 preparation adapter differs")
    positive_6 = _model(
        request.positive_6rtz_result, PartnerSearchResult, label="6RTZ result"
    )
    positive_3 = _model(
        request.positive_3u7q_result, PartnerSearchResult, label="3U7Q result"
    )
    missing_plan = _model(
        request.missing_partner_plan, PartnerSearchPlan, label="missing-B plan"
    )
    missing_summary = _model(
        request.missing_partner_summary,
        PartnerAttemptSummary,
        label="missing-B summary",
    )
    wrong = _model(
        request.wrong_partner_result, PartnerSearchResult, label="wrong-B result"
    )
    homomer = _model(request.homomer_result, NormalisedMrResult, label="homomer result")
    missing_definition = preparation.get("missing_partner")
    wrong_definition = preparation.get("wrong_partner")
    unsupported = preparation.get("unsupported_component_control")
    if not all(
        isinstance(value, dict)
        for value in (missing_definition, wrong_definition, unsupported)
    ):
        raise HeteromerControlPreparationError("P6 preparation cases are incomplete")
    assert isinstance(missing_definition, dict)
    assert isinstance(wrong_definition, dict)
    assert isinstance(unsupported, dict)

    missing_gate = (
        missing_plan.parent_sequence_group_id
        == missing_definition.get("parent_sequence_group_id")
        and missing_plan.selected_attempt_count == 0
        and missing_plan.searchable_candidate_count == 0
        and missing_plan.unsearchable_candidate_count == missing_plan.candidate_count
        and missing_summary.plan_id == missing_plan.plan_id
        and missing_summary.selected_attempt_count == 0
        and missing_summary.result_count == 0
        and missing_summary.all_selected_attempts_retained
    )
    wrong_gate = (
        wrong.parent_sequence_group_id
        == wrong_definition.get("parent_sequence_group_id")
        and wrong.partner_sequence_group_id
        == wrong_definition.get("partner_sequence_group_id")
        and wrong.execution_status
        in {
            ExecutionStatus.COMPLETED_HIT,
            ExecutionStatus.COMPLETED_NO_HIT,
        }
        and wrong.parent_retained
        and not wrong.failed_search_proves_partner_absence
    )
    packing = homomer.packing_summary.get("top_solution_packed")
    homomer_gate = (
        homomer.execution_status is ExecutionStatus.COMPLETED_HIT
        and homomer.placed_copy_count >= 1
        and packing is True
    )
    unsupported_gate = (
        unsupported.get("pdb_id") == "9ECN"
        and unsupported.get("observed_component_count") == 3
        and unsupported.get("supported_component_count") == 2
        and unsupported.get("status") == "unsupported_component_count"
        and unsupported.get("retain_partial_a_b_evidence") is True
        and unsupported.get("complete_composition_claimed") is False
    )
    cases = {
        "6RTZ_positive_1A_1B": {
            "gate_passed": _positive_gate(positive_6),
            "execution_status": positive_6.execution_status.value,
            "partner_placement_count": positive_6.partner_placement_count,
        },
        "3U7Q_positive_2A_2B": {
            "gate_passed": _positive_gate(positive_3),
            "execution_status": positive_3.execution_status.value,
            "partner_placement_count": positive_3.partner_placement_count,
        },
        "missing_B": {
            "gate_passed": missing_gate,
            "selected_attempt_count": missing_plan.selected_attempt_count,
            "complete_composition_claimed": False,
        },
        "wrong_B": {
            "gate_passed": wrong_gate,
            "execution_status": wrong.execution_status.value,
            "search_evidence_retained": True,
            "complete_composition_claimed": False,
        },
        "homomer_non_regression": {
            "gate_passed": homomer_gate,
            "execution_status": homomer.execution_status.value,
            "route": "first_copy",
        },
        "9ECN_three_component_boundary": {
            "gate_passed": unsupported_gate,
            "status": "unsupported_component_count",
            "retain_partial_a_b_evidence": True,
            "complete_composition_claimed": False,
        },
    }
    gate_passed = all(bool(case["gate_passed"]) for case in cases.values())
    identity = {
        "adapter_version": _ADAPTER_VERSION,
        "preparation_sha256": sha256_file(request.preparation_manifest),
        "positive_6rtz_sha256": sha256_file(request.positive_6rtz_result),
        "positive_3u7q_sha256": sha256_file(request.positive_3u7q_result),
        "missing_plan_sha256": sha256_file(request.missing_partner_plan),
        "missing_summary_sha256": sha256_file(request.missing_partner_summary),
        "wrong_result_sha256": sha256_file(request.wrong_partner_result),
        "homomer_result_sha256": sha256_file(request.homomer_result),
    }
    report_id = content_id("heteromerslice_", identity)
    report = {
        "schema_version": "1.0",
        "report_id": report_id,
        "adapter_version": _ADAPTER_VERSION,
        "gate_passed": gate_passed,
        "cases": cases,
        "evidence_sha256": identity,
        "limitations": [
            "packing_and_MR_scores_are_search_evidence_not_composition_proof",
            "exactly_two_components_supported",
            "three_component_reconstruction_not_attempted",
        ],
    }
    output = request.output_json.absolute()
    if output.exists():
        raise HeteromerControlPreparationError(f"P6 report already exists: {output}")
    atomic_write_json(output, report)
    return HeteromerSliceAssessmentResult(
        report_json=output, report_id=report_id, gate_passed=gate_passed
    )
