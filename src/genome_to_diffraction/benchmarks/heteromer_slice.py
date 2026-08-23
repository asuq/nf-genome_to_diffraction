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

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ValidationError

from genome_to_diffraction.benchmarks.heteromer_control import (
    HeteromerControlPreparationError,
    _prepared_file,
)
from genome_to_diffraction.benchmarks.m6_protocol import (
    M6AssumptionControlSpec,
    load_m6_protocol,
)
from genome_to_diffraction.checksums import (
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import canonical_json_text, content_id
from genome_to_diffraction.schemas.io import load_json_document
from genome_to_diffraction.schemas.results import (
    ComponentScopeDecision,
    ComponentScopeStatus,
    CompositionAssessment,
    CompositionAssessmentCaseKind,
    CompositionAssessmentStatus,
    MrHypothesis,
    NormalisedMrResult,
    PartnerAttemptSummary,
    PartnerSearchPlan,
    PartnerSearchResult,
    ProcessedModelRecord,
    SequenceGroupRecord,
)
from genome_to_diffraction.status import ExecutionStatus

_ADAPTER_VERSION = "heteromer-p6-control-slice-v2"
_EXPECTED_CATALOGUE_SEQUENCE_GROUP_COUNT = 1846
_EXPECTED_MISSING_CANDIDATE_COUNT = 1845
_SUPPORTED_DISTINCT_COMPONENT_COUNT = 2
_CONTROL_EXPECTATIONS: dict[str, dict[str, object]] = {
    "6RTZ": {
        "control_key": "A01",
        "adapter_version": "6rtz-fixed-a-one-b-inputs-v1",
        "parent_chain": "A",
        "composition": {"A": 1, "B": 1},
    },
    "3U7Q": {
        "control_key": "A03",
        "adapter_version": "3u7q-fixed-two-a-two-b-inputs-v1",
        "parent_chain": "A",
        "composition": {"A": 2, "B": 2},
    },
}


@dataclass(frozen=True)
class HeteromerSlicePreparationRequest:
    """Frozen protocol and accepted 6RTZ/3U7Q preparation manifests."""

    protocol: Path
    control_6rtz_preparation: Path
    control_3u7q_preparation: Path
    catalogue_sequence_groups: Path
    output_directory: Path


@dataclass(frozen=True)
class HeteromerSlicePreparationResult:
    """Paths used by the missing-B, wrong-B, and 9ECN controls."""

    preparation_manifest: Path
    missing_partner_model_registry: Path
    wrong_partner_sequence_groups: Path
    wrong_partner_model: Path
    component_scope_decision: Path


@dataclass(frozen=True)
class HeteromerSliceAssessmentRequest:
    """All retained records required for the six fixed P6 cases."""

    preparation_manifest: Path
    catalogue_sequence_groups: Path
    positive_6rtz_result: Path
    positive_3u7q_result: Path
    positive_3u7q_parent_result: Path
    missing_partner_plan: Path
    missing_partner_summary: Path
    wrong_partner_result: Path
    homomer_result: Path
    output_json: Path


@dataclass(frozen=True)
class HeteromerSliceAssessmentResult:
    """The accepted/rejected P6 report and its content identity."""

    report_json: Path
    composition_assessments_jsonl: Path
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


def _candidate_universe_sha256(sequence_group_ids: set[str]) -> str:
    payload = "".join(
        f"{sequence_group_id}\n" for sequence_group_id in sorted(sequence_group_ids)
    )
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def _expected_partner_candidate_id(
    plan: PartnerSearchPlan,
    candidate_sequence_group_id: str,
    model_id: str | None,
) -> str:
    return content_id(
        "partnercand_",
        {
            "adapter_version": plan.adapter_version,
            "crystal_id": plan.crystal_id,
            "parent_sequence_group_id": plan.parent_sequence_group_id,
            "parent_copy_count": plan.parent_copy_count,
            "partner_sequence_group_id": candidate_sequence_group_id,
            "partner_copy_count": plan.partner_copy_count,
            "parent_state_sha256": plan.parent_state_sha256,
            "model_id": model_id,
        },
    )


def _prepared_entry(
    preparation_path: Path,
    files: object,
    role: str,
) -> Path:
    """Resolve one checksum- and size-bound source-preparation file."""

    path = _prepared_file(preparation_path.parent, files, role)
    if not isinstance(files, dict):
        raise HeteromerControlPreparationError("control preparation files are invalid")
    entry = files.get(role)
    if not isinstance(entry, dict):
        raise HeteromerControlPreparationError(
            f"control preparation file entry is invalid: {role}"
        )
    size_bytes = entry.get("size_bytes")
    if (
        isinstance(size_bytes, bool)
        or not isinstance(size_bytes, int)
        or size_bytes < 1
        or path.stat().st_size != size_bytes
    ):
        raise HeteromerControlPreparationError(
            f"control preparation file size differs: {role}"
        )
    return path


def _single_jsonl_model[T: BaseModel](path: Path, model: type[T], *, label: str) -> T:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    if len(lines) != 1:
        raise HeteromerControlPreparationError(f"{label} must contain one record")
    try:
        return model.model_validate_json(lines[0])
    except ValidationError as error:
        raise HeteromerControlPreparationError(f"invalid {label}") from error


def _protocol_control(
    controls: tuple[M6AssumptionControlSpec, ...],
    *,
    target_key: str,
    crystal_id: str,
) -> M6AssumptionControlSpec:
    matches = [
        control
        for control in controls
        if control.target_key == target_key and control.source.pdb_id == crystal_id
    ]
    if len(matches) != 1:
        raise HeteromerControlPreparationError(
            f"fixed {crystal_id} protocol control is absent"
        )
    return matches[0]


def _control_binding(
    preparation_path: Path,
    preparation: dict[str, Any],
    protocol_control: M6AssumptionControlSpec,
) -> dict[str, object]:
    """Validate and retain exact identity/model evidence for one positive control."""

    crystal_id = protocol_control.source.pdb_id
    expected = _CONTROL_EXPECTATIONS[crystal_id]
    composition = cast(dict[str, int], expected["composition"])
    if (
        preparation.get("schema_version") != "1.0"
        or preparation.get("adapter_version") != expected["adapter_version"]
        or preparation.get("control_key") != expected["control_key"]
        or preparation.get("crystal_id") != crystal_id
        or preparation.get("composition") != composition
        or preparation.get("source")
        != {
            "coordinates_sha256": protocol_control.source.coordinates.sha256,
            "structure_factors_sha256": (
                protocol_control.source.structure_factors.sha256
            ),
        }
    ):
        raise HeteromerControlPreparationError(
            f"fixed {crystal_id} preparation identity differs"
        )
    parent_id = preparation.get("parent_sequence_group_id")
    partner_id = preparation.get("partner_sequence_group_id")
    preparation_id = preparation.get("preparation_id")
    parent_hypothesis_id = preparation.get("parent_hypothesis_id")
    if not all(
        isinstance(value, str)
        for value in (parent_id, partner_id, preparation_id, parent_hypothesis_id)
    ):
        raise HeteromerControlPreparationError(
            f"fixed {crystal_id} preparation identifiers are absent"
        )
    assert isinstance(parent_id, str)
    assert isinstance(partner_id, str)
    assert isinstance(preparation_id, str)
    assert isinstance(parent_hypothesis_id, str)
    if parent_id == partner_id:
        raise HeteromerControlPreparationError(
            f"fixed {crystal_id} component identities are not distinct"
        )

    files = preparation.get("files")
    expected_roles = {
        "crystal_manifest",
        "sequence_groups",
        "processed_models",
        "model_preparation_manifest",
        "hypotheses",
        "mtz",
        "parent_model",
        "partner_model",
    }
    if not isinstance(files, dict) or set(files) != expected_roles:
        raise HeteromerControlPreparationError(
            f"fixed {crystal_id} preparation file inventory differs"
        )
    paths = {
        role: _prepared_entry(preparation_path, files, role)
        for role in sorted(expected_roles)
    }
    file_digests = {role: sha256_file(path) for role, path in paths.items()}
    expected_preparation_id = content_id(
        "heteromerprep_",
        {
            "adapter_version": expected["adapter_version"],
            "source_coordinates_sha256": protocol_control.source.coordinates.sha256,
            "source_structure_factors_sha256": (
                protocol_control.source.structure_factors.sha256
            ),
            "files": file_digests,
        },
    )
    if preparation_id != expected_preparation_id:
        raise HeteromerControlPreparationError(
            f"fixed {crystal_id} preparation content identity differs"
        )

    groups = _groups(paths["sequence_groups"])
    if set(groups) != {parent_id, partner_id}:
        raise HeteromerControlPreparationError(
            f"fixed {crystal_id} sequence-group inventory differs"
        )
    relationships = preparation.get("sequence_relationships")
    if not isinstance(relationships, list) or len(relationships) != 2:
        raise HeteromerControlPreparationError(
            f"fixed {crystal_id} sequence relationships differ"
        )
    for entity_id, (group_id, protein) in enumerate(
        zip((parent_id, partner_id), protocol_control.proteins, strict=True),
        start=1,
    ):
        relationship = relationships[entity_id - 1]
        if not isinstance(relationship, dict):
            raise HeteromerControlPreparationError(
                f"fixed {crystal_id} sequence relationship is invalid"
            )
        group = groups[group_id]
        source_sha256 = relationship.get("source_construct_sequence_sha256")
        if (
            relationship.get("entity_id") != entity_id
            or relationship.get("catalogue_protein_id") != protein.protein_id
            or relationship.get("catalogue_sequence_sha256") != protein.sequence_sha256
            or source_sha256 != group.sha256
            or relationship.get("exact_catalogue_sequence")
            is not (source_sha256 == protein.sequence_sha256)
        ):
            raise HeteromerControlPreparationError(
                f"fixed {crystal_id} sequence relationship differs"
            )

    parent_model = _single_jsonl_model(
        paths["processed_models"],
        ProcessedModelRecord,
        label=f"{crystal_id} processed parent model",
    )
    if (
        parent_model.full_candidate_sequence_group_id != parent_id
        or parent_model.model_sha256 != file_digests["parent_model"]
        or parent_model.processing_parameters.get("source_pdb_id") != crystal_id
        or parent_model.processing_parameters.get("source_chain")
        != expected["parent_chain"]
    ):
        raise HeteromerControlPreparationError(
            f"fixed {crystal_id} parent model identity differs"
        )
    model_manifest = _document(
        paths["model_preparation_manifest"],
        label=f"{crystal_id} model preparation manifest",
    )
    entries = model_manifest.get("entries")
    if (
        model_manifest.get("adapter_version") != expected["adapter_version"]
        or not isinstance(entries, list)
        or len(entries) != 1
        or not isinstance(entries[0], dict)
        or entries[0].get("model_id") != parent_model.model_id
        or entries[0].get("model_path") != "models/component_A.pdb"
        or entries[0].get("model_sha256") != parent_model.model_sha256
    ):
        raise HeteromerControlPreparationError(
            f"fixed {crystal_id} model preparation manifest differs"
        )
    hypothesis = _single_jsonl_model(
        paths["hypotheses"], MrHypothesis, label=f"{crystal_id} parent hypothesis"
    )
    parent_copies = composition["A"]
    if (
        hypothesis.hypothesis_id != parent_hypothesis_id
        or hypothesis.crystal_id != crystal_id
        or hypothesis.sequence_group_id != parent_id
        or hypothesis.model_id != parent_model.model_id
        or hypothesis.copy_count_expected != parent_copies
        or hypothesis.copy_number_to_search != parent_copies
    ):
        raise HeteromerControlPreparationError(
            f"fixed {crystal_id} parent hypothesis differs"
        )
    model_identity = preparation.get("partner_model_identity_fraction")
    if (
        isinstance(model_identity, bool)
        or not isinstance(model_identity, int | float)
        or not math.isclose(float(model_identity), 1.0)
    ):
        raise HeteromerControlPreparationError(
            f"fixed {crystal_id} partner model is not exact"
        )

    return {
        "control_key": expected["control_key"],
        "crystal_id": crystal_id,
        "composition": composition,
        "parent_sequence_group_id": parent_id,
        "partner_sequence_group_id": partner_id,
        "parent_hypothesis_id": parent_hypothesis_id,
        "parent_model_id": parent_model.model_id,
        "parent_model_sha256": file_digests["parent_model"],
        "partner_model_sha256": file_digests["partner_model"],
        "mtz_sha256": file_digests["mtz"],
        "processed_models_sha256": file_digests["processed_models"],
        "model_preparation_manifest_sha256": file_digests["model_preparation_manifest"],
        "source_coordinates_sha256": protocol_control.source.coordinates.sha256,
        "source_structure_factors_sha256": (
            protocol_control.source.structure_factors.sha256
        ),
        "source_preparation_id": preparation_id,
        "source_preparation_manifest_sha256": sha256_file(preparation_path),
    }


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
    protocol_path = request.protocol.resolve(strict=True)
    protocol = load_m6_protocol(protocol_path)
    control_6 = _document(control_6_path, label="6RTZ preparation")
    control_3 = _document(control_3_path, label="3U7Q preparation")
    protocol_6 = _protocol_control(
        protocol.assumption_controls, target_key="A01", crystal_id="6RTZ"
    )
    protocol_3 = _protocol_control(
        protocol.assumption_controls, target_key="A03", crystal_id="3U7Q"
    )
    binding_6 = _control_binding(control_6_path, control_6, protocol_6)
    binding_3 = _control_binding(control_3_path, control_3, protocol_3)
    parent_id = cast(str, binding_6["parent_sequence_group_id"])
    expected_partner_id = cast(str, binding_6["partner_sequence_group_id"])
    wrong_id = cast(str, binding_3["partner_sequence_group_id"])
    if wrong_id in {parent_id, expected_partner_id}:
        raise HeteromerControlPreparationError("P6 wrong partner is not distinct")
    catalogue_path = request.catalogue_sequence_groups.resolve(strict=True)
    catalogue_groups = _groups(catalogue_path)
    candidate_universe = set(catalogue_groups) - {parent_id}
    if (
        len(catalogue_groups) != _EXPECTED_CATALOGUE_SEQUENCE_GROUP_COUNT
        or parent_id not in catalogue_groups
        or expected_partner_id not in catalogue_groups
        or len(candidate_universe) != _EXPECTED_MISSING_CANDIDATE_COUNT
    ):
        raise HeteromerControlPreparationError(
            "fixed Thermotoga catalogue sequence-group universe differs"
        )
    candidate_universe_sha256 = _candidate_universe_sha256(candidate_universe)
    files_6 = cast(dict[str, object], control_6["files"])
    files_3 = cast(dict[str, object], control_3["files"])
    groups_6 = _groups(_prepared_entry(control_6_path, files_6, "sequence_groups"))
    groups_3 = _groups(_prepared_entry(control_3_path, files_3, "sequence_groups"))
    parent_group = groups_6.get(parent_id)
    wrong_group = groups_3.get(wrong_id)
    if parent_group is None or wrong_group is None:
        raise HeteromerControlPreparationError("P6 control sequence mapping differs")
    parent_source = _prepared_entry(control_6_path, files_6, "parent_model")
    wrong_source = _prepared_entry(control_3_path, files_3, "partner_model")

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

    control_9ecn = _protocol_control(
        protocol.assumption_controls, target_key="A04", crystal_id="9ECN"
    )
    observed_components = control_9ecn.asu_distinct_protein_species
    scope_status = (
        ComponentScopeStatus.WITHIN_SUPPORTED_COMPONENT_COUNT
        if observed_components <= _SUPPORTED_DISTINCT_COMPONENT_COUNT
        else ComponentScopeStatus.UNSUPPORTED_COMPONENT_COUNT
    )
    scope_identity = {
        "target_key": control_9ecn.target_key,
        "crystal_id": control_9ecn.source.pdb_id,
        "protocol_id": protocol.protocol_id,
        "protocol_sha256": sha256_file(protocol_path),
        "observed_distinct_component_count": observed_components,
        "supported_distinct_component_count": _SUPPORTED_DISTINCT_COMPONENT_COUNT,
    }
    scope_decision = ComponentScopeDecision(
        schema_version="1.0",
        decision_id=content_id("componentscope_", scope_identity),
        **scope_identity,
        status=scope_status,
        retain_partial_a_b_evidence=(
            observed_components > _SUPPORTED_DISTINCT_COMPONENT_COUNT
            and _SUPPORTED_DISTINCT_COMPONENT_COUNT >= 2
        ),
        complete_composition_claim_eligible=(
            scope_status is ComponentScopeStatus.WITHIN_SUPPORTED_COMPONENT_COUNT
        ),
    )
    scope_decision_path = output / "component_scope_decision.json"
    atomic_write_json(scope_decision_path, scope_decision.model_dump(mode="json"))

    preparation = output / "preparation_manifest.json"
    recorded = {
        "missing_processed_models": missing_registry / "processed_models.jsonl",
        "missing_model_manifest": parent_model_manifest,
        "missing_parent_model": parent_model_path,
        "wrong_sequence_groups": wrong_groups,
        "wrong_partner_model": wrong_model,
        "component_scope_decision": scope_decision_path,
    }
    atomic_write_json(
        preparation,
        {
            "schema_version": "1.0",
            "adapter_version": _ADAPTER_VERSION,
            "protocol": {
                "protocol_id": protocol.protocol_id,
                "sha256": sha256_file(protocol_path),
            },
            "source_preparations": {
                crystal_id: {
                    "preparation_id": binding["source_preparation_id"],
                    "manifest_sha256": binding["source_preparation_manifest_sha256"],
                }
                for crystal_id, binding in (
                    ("6RTZ", binding_6),
                    ("3U7Q", binding_3),
                )
            },
            "positive_controls": {
                "6RTZ": binding_6,
                "3U7Q": binding_3,
            },
            "catalogue_sequence_groups": {
                "sha256": sha256_file(catalogue_path),
                "sequence_group_count": len(catalogue_groups),
                "candidate_sequence_group_count": len(candidate_universe),
                "candidate_universe_sha256": candidate_universe_sha256,
            },
            "missing_partner": {
                "parent_sequence_group_id": parent_id,
                "parent_copy_count": 1,
                "partner_copy_count": 1,
                "expected_candidate_count": _EXPECTED_MISSING_CANDIDATE_COUNT,
                "candidate_universe_sha256": candidate_universe_sha256,
                "selected_attempt_count_expected": 0,
            },
            "wrong_partner": {
                "crystal_id": "6RTZ",
                "parent_sequence_group_id": parent_id,
                "parent_copy_count": 1,
                "expected_partner_sequence_group_id": expected_partner_id,
                "partner_sequence_group_id": wrong_id,
                "partner_copy_count": 1,
                "partner_model_sha256": sha256_file(wrong_model),
                "mtz_sha256": binding_6["mtz_sha256"],
            },
            "homomer_non_regression": {
                "route": "first_copy",
                "parent_hypothesis_id": binding_6["parent_hypothesis_id"],
            },
            "unsupported_component_control": {
                "target_key": control_9ecn.target_key,
                "pdb_id": control_9ecn.source.pdb_id,
                "scope_decision_id": scope_decision.decision_id,
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
        component_scope_decision=scope_decision_path,
    )


def _parent_result_gate(
    result: NormalisedMrResult,
    expected: dict[str, object],
) -> bool:
    composition = expected.get("composition")
    return (
        isinstance(composition, dict)
        and result.hypothesis_id == expected.get("parent_hypothesis_id")
        and result.execution_status is ExecutionStatus.COMPLETED_HIT
        and result.placed_copy_count == composition.get("A")
        and result.packing_summary.get("top_solution_packed") is True
        and result.solution_coordinate_sha256 is not None
        and result.llg is not None
    )


def _positive_identity_gate(
    result: PartnerSearchResult,
    expected: dict[str, object],
    parent_result: NormalisedMrResult,
) -> bool:
    composition = expected.get("composition")
    return (
        isinstance(composition, dict)
        and _parent_result_gate(parent_result, expected)
        and result.crystal_id == expected.get("crystal_id")
        and result.parent_sequence_group_id == expected.get("parent_sequence_group_id")
        and result.partner_sequence_group_id
        == expected.get("partner_sequence_group_id")
        and result.parent_copy_count == composition.get("A")
        and result.requested_partner_copy_count == composition.get("B")
        and result.partner_model_sha256 == expected.get("partner_model_sha256")
        and result.mtz_sha256 == expected.get("mtz_sha256")
        and result.parent_coordinate_sha256 == parent_result.solution_coordinate_sha256
        and parent_result.llg is not None
        and math.isclose(
            result.parent_llg,
            parent_result.llg,
            rel_tol=1e-10,
            abs_tol=1e-8,
        )
    )


def _positive_gate(
    result: PartnerSearchResult,
    expected: dict[str, object],
    parent_result: NormalisedMrResult,
) -> bool:
    return (
        _positive_identity_gate(result, expected, parent_result)
        and result.execution_status is ExecutionStatus.COMPLETED_HIT
        and result.partner_placement_count == result.requested_partner_copy_count
        and result.partner_placement_observed
        and result.top_solution_packed
        and result.score_cohort in {"primary", "fallback"}
    )


def _composition_assessment(
    *,
    case_id: str,
    crystal_id: str,
    case_kind: CompositionAssessmentCaseKind,
    execution_status: ExecutionStatus,
    placement_observed: bool,
    exact_identity_supported: bool,
    scope_status: ComponentScopeStatus,
    scope_decision_id: str | None,
    scientific_status: CompositionAssessmentStatus,
    complete_composition_claim_eligible: bool,
    evidence_sha256: dict[str, str],
) -> CompositionAssessment:
    identity = {
        "case_id": case_id,
        "crystal_id": crystal_id,
        "case_kind": case_kind.value,
        "execution_status": execution_status.value,
        "placement_observed": placement_observed,
        "exact_identity_supported": exact_identity_supported,
        "scope_status": scope_status.value,
        "scope_decision_id": scope_decision_id,
        "scientific_status": scientific_status.value,
        "complete_composition_claim_eligible": (complete_composition_claim_eligible),
        "evidence_sha256": evidence_sha256,
    }
    return CompositionAssessment(
        schema_version="1.0",
        assessment_id=content_id("compositionassessment_", identity),
        case_id=case_id,
        crystal_id=crystal_id,
        case_kind=case_kind,
        execution_status=execution_status,
        placement_observed=placement_observed,
        exact_identity_supported=exact_identity_supported,
        scope_status=scope_status,
        scope_decision_id=scope_decision_id,
        scientific_status=scientific_status,
        complete_composition_claim_eligible=(complete_composition_claim_eligible),
        evidence_sha256=evidence_sha256,
    )


def assess_heteromer_control_slice(
    request: HeteromerSliceAssessmentRequest,
) -> HeteromerSliceAssessmentResult:
    """Validate the six P6 controls and write one bounded release-gate report."""

    preparation = _document(request.preparation_manifest, label="P6 preparation")
    if (
        preparation.get("schema_version") != "1.0"
        or preparation.get("adapter_version") != _ADAPTER_VERSION
    ):
        raise HeteromerControlPreparationError("P6 preparation adapter differs")
    positive_6 = _model(
        request.positive_6rtz_result, PartnerSearchResult, label="6RTZ result"
    )
    positive_3 = _model(
        request.positive_3u7q_result, PartnerSearchResult, label="3U7Q result"
    )
    positive_3_parent = _model(
        request.positive_3u7q_parent_result,
        NormalisedMrResult,
        label="3U7Q parent result",
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
    homomer_definition = preparation.get("homomer_non_regression")
    positive_definitions = preparation.get("positive_controls")
    protocol_definition = preparation.get("protocol")
    source_preparations = preparation.get("source_preparations")
    catalogue_definition = preparation.get("catalogue_sequence_groups")
    if not all(
        isinstance(value, dict)
        for value in (
            missing_definition,
            wrong_definition,
            unsupported,
            homomer_definition,
            positive_definitions,
            protocol_definition,
            source_preparations,
            catalogue_definition,
        )
    ):
        raise HeteromerControlPreparationError("P6 preparation cases are incomplete")
    assert isinstance(missing_definition, dict)
    assert isinstance(wrong_definition, dict)
    assert isinstance(unsupported, dict)
    assert isinstance(homomer_definition, dict)
    assert isinstance(positive_definitions, dict)
    assert isinstance(protocol_definition, dict)
    assert isinstance(source_preparations, dict)
    assert isinstance(catalogue_definition, dict)
    if set(positive_definitions) != {"6RTZ", "3U7Q"} or set(source_preparations) != {
        "6RTZ",
        "3U7Q",
    }:
        raise HeteromerControlPreparationError("P6 positive control inventory differs")
    positive_6_definition = positive_definitions.get("6RTZ")
    positive_3_definition = positive_definitions.get("3U7Q")
    if not isinstance(positive_6_definition, dict) or not isinstance(
        positive_3_definition, dict
    ):
        raise HeteromerControlPreparationError("P6 positive bindings are invalid")
    for crystal_id, definition in (
        ("6RTZ", positive_6_definition),
        ("3U7Q", positive_3_definition),
    ):
        expected = _CONTROL_EXPECTATIONS[crystal_id]
        source = source_preparations[crystal_id]
        if (
            not isinstance(source, dict)
            or definition.get("control_key") != expected["control_key"]
            or definition.get("crystal_id") != crystal_id
            or definition.get("composition") != expected["composition"]
            or source.get("preparation_id") != definition.get("source_preparation_id")
            or source.get("manifest_sha256")
            != definition.get("source_preparation_manifest_sha256")
        ):
            raise HeteromerControlPreparationError(
                f"P6 {crystal_id} source preparation binding differs"
            )

    catalogue_path = request.catalogue_sequence_groups.resolve(strict=True)
    catalogue_groups = _groups(catalogue_path)
    catalogue_parent_id = positive_6_definition.get("parent_sequence_group_id")
    if not isinstance(catalogue_parent_id, str):
        raise HeteromerControlPreparationError("P6 catalogue parent identity is absent")
    candidate_universe = set(catalogue_groups) - {catalogue_parent_id}
    candidate_universe_sha256 = _candidate_universe_sha256(candidate_universe)
    if (
        sha256_file(catalogue_path) != catalogue_definition.get("sha256")
        or len(catalogue_groups) != _EXPECTED_CATALOGUE_SEQUENCE_GROUP_COUNT
        or catalogue_definition.get("sequence_group_count") != len(catalogue_groups)
        or catalogue_parent_id not in catalogue_groups
        or positive_6_definition.get("partner_sequence_group_id")
        not in catalogue_groups
        or len(candidate_universe) != _EXPECTED_MISSING_CANDIDATE_COUNT
        or catalogue_definition.get("candidate_sequence_group_count")
        != len(candidate_universe)
        or catalogue_definition.get("candidate_universe_sha256")
        != candidate_universe_sha256
        or missing_definition.get("candidate_universe_sha256")
        != candidate_universe_sha256
    ):
        raise HeteromerControlPreparationError(
            "P6 Thermotoga catalogue sequence-group binding differs"
        )

    files = preparation.get("files")
    scope_path = _prepared_entry(
        request.preparation_manifest.resolve(strict=True),
        files,
        "component_scope_decision",
    )
    wrong_model_path = _prepared_entry(
        request.preparation_manifest.resolve(strict=True),
        files,
        "wrong_partner_model",
    )
    scope = _model(
        scope_path, ComponentScopeDecision, label="9ECN component scope decision"
    )
    scope_identity = {
        "target_key": scope.target_key,
        "crystal_id": scope.crystal_id,
        "protocol_id": scope.protocol_id,
        "protocol_sha256": scope.protocol_sha256,
        "observed_distinct_component_count": (scope.observed_distinct_component_count),
        "supported_distinct_component_count": (
            scope.supported_distinct_component_count
        ),
    }
    unsupported_gate = (
        scope.decision_id == content_id("componentscope_", scope_identity)
        and scope.target_key == "A04"
        and scope.crystal_id == "9ECN"
        and scope.protocol_id == protocol_definition.get("protocol_id")
        and scope.protocol_sha256 == protocol_definition.get("sha256")
        and scope.observed_distinct_component_count == 3
        and scope.supported_distinct_component_count
        == _SUPPORTED_DISTINCT_COMPONENT_COUNT
        and scope.status is ComponentScopeStatus.UNSUPPORTED_COMPONENT_COUNT
        and scope.retain_partial_a_b_evidence
        and not scope.complete_composition_claim_eligible
        and unsupported.get("target_key") == scope.target_key
        and unsupported.get("pdb_id") == scope.crystal_id
        and unsupported.get("scope_decision_id") == scope.decision_id
    )

    plan_sha256 = sha256_file(request.missing_partner_plan)
    candidate_ids = [candidate.candidate_id for candidate in missing_plan.candidates]
    sequence_ids = [
        candidate.sequence_group_id for candidate in missing_plan.candidates
    ]
    recomputed_candidate_ids = [
        _expected_partner_candidate_id(
            missing_plan,
            candidate.sequence_group_id,
            candidate.model_id,
        )
        for candidate in missing_plan.candidates
    ]
    expected_missing_count = missing_definition.get("expected_candidate_count")
    missing_gate = (
        expected_missing_count == _EXPECTED_MISSING_CANDIDATE_COUNT
        and missing_plan.adapter_version == "catalogue-partner-plan-v1"
        and missing_plan.crystal_id == "6RTZ"
        and missing_plan.parent_sequence_group_id
        == missing_definition.get("parent_sequence_group_id")
        and missing_plan.parent_copy_count
        == missing_definition.get("parent_copy_count")
        and missing_plan.partner_copy_count
        == missing_definition.get("partner_copy_count")
        and missing_plan.candidate_count == _EXPECTED_MISSING_CANDIDATE_COUNT
        and len(set(candidate_ids)) == _EXPECTED_MISSING_CANDIDATE_COUNT
        and len(set(sequence_ids)) == _EXPECTED_MISSING_CANDIDATE_COUNT
        and set(sequence_ids) == candidate_universe
        and _candidate_universe_sha256(set(sequence_ids)) == candidate_universe_sha256
        and candidate_ids == recomputed_candidate_ids
        and all(candidate.model_id is None for candidate in missing_plan.candidates)
        and missing_plan.selected_attempt_count == 0
        and missing_plan.searchable_candidate_count == 0
        and missing_plan.deferred_cap_count == 0
        and missing_plan.unsearchable_candidate_count
        == _EXPECTED_MISSING_CANDIDATE_COUNT
        and missing_summary.plan_id == missing_plan.plan_id
        and missing_summary.plan_sha256 == plan_sha256
        and missing_summary.candidate_count == missing_plan.candidate_count
        and missing_summary.selected_attempt_count == 0
        and missing_summary.result_count == 0
        and missing_summary.completed_hit_count == 0
        and missing_summary.completed_no_hit_count == 0
        and missing_summary.failed_tool_execution_count == 0
        and missing_summary.failed_parse_count == 0
        and missing_summary.deferred_cap_count == missing_plan.deferred_cap_count
        and missing_summary.unsearchable_candidate_count
        == missing_plan.unsearchable_candidate_count
        and not missing_summary.selected_candidate_ids
        and not missing_summary.result_candidate_ids
        and not missing_summary.result_search_ids
        and missing_summary.all_selected_attempts_retained
    )
    wrong_gate = (
        wrong.crystal_id == wrong_definition.get("crystal_id")
        and wrong.parent_sequence_group_id
        == wrong_definition.get("parent_sequence_group_id")
        and wrong.parent_copy_count == wrong_definition.get("parent_copy_count")
        and wrong.partner_sequence_group_id
        == wrong_definition.get("partner_sequence_group_id")
        and wrong.partner_sequence_group_id
        != wrong_definition.get("expected_partner_sequence_group_id")
        and wrong.requested_partner_copy_count
        == wrong_definition.get("partner_copy_count")
        and wrong.partner_model_sha256 == wrong_definition.get("partner_model_sha256")
        and wrong.partner_model_sha256 == sha256_file(wrong_model_path)
        and wrong.mtz_sha256 == wrong_definition.get("mtz_sha256")
        and wrong.parent_coordinate_sha256 == positive_6.parent_coordinate_sha256
        and math.isclose(
            wrong.parent_llg,
            positive_6.parent_llg,
            rel_tol=1e-10,
            abs_tol=1e-8,
        )
        and wrong.execution_status
        in {
            ExecutionStatus.COMPLETED_HIT,
            ExecutionStatus.COMPLETED_NO_HIT,
        }
        and wrong.parent_retained
        and not wrong.failed_search_proves_partner_absence
    )
    homomer_gate = homomer_definition.get(
        "parent_hypothesis_id"
    ) == positive_6_definition.get("parent_hypothesis_id") and _parent_result_gate(
        homomer, positive_6_definition
    )

    positive_6_gate = _positive_gate(positive_6, positive_6_definition, homomer)
    positive_3_gate = _positive_gate(
        positive_3, positive_3_definition, positive_3_parent
    )
    within_scope = ComponentScopeStatus.WITHIN_SUPPORTED_COMPONENT_COUNT
    evidence = {
        "preparation": sha256_file(request.preparation_manifest),
        "positive_6rtz": sha256_file(request.positive_6rtz_result),
        "positive_3u7q": sha256_file(request.positive_3u7q_result),
        "positive_3u7q_parent": sha256_file(request.positive_3u7q_parent_result),
        "catalogue_sequence_groups": sha256_file(catalogue_path),
        "missing_plan": plan_sha256,
        "missing_summary": sha256_file(request.missing_partner_summary),
        "wrong_result": sha256_file(request.wrong_partner_result),
        "homomer_result": sha256_file(request.homomer_result),
        "component_scope_decision": sha256_file(scope_path),
        "protocol": scope.protocol_sha256,
        "source_preparation_6rtz": cast(
            str, source_preparations["6RTZ"]["manifest_sha256"]
        ),
        "source_preparation_3u7q": cast(
            str, source_preparations["3U7Q"]["manifest_sha256"]
        ),
    }
    assessments = (
        _composition_assessment(
            case_id="6RTZ_positive_1A_1B",
            crystal_id="6RTZ",
            case_kind=CompositionAssessmentCaseKind.KNOWN_POSITIVE_CONTROL,
            execution_status=positive_6.execution_status,
            placement_observed=positive_6_gate,
            exact_identity_supported=_positive_identity_gate(
                positive_6, positive_6_definition, homomer
            ),
            scope_status=within_scope,
            scope_decision_id=None,
            scientific_status=(
                CompositionAssessmentStatus.KNOWN_CONTROL_RECOVERED
                if positive_6_gate
                else CompositionAssessmentStatus.SEARCH_EVIDENCE_ONLY
            ),
            complete_composition_claim_eligible=positive_6_gate,
            evidence_sha256={
                "result": evidence["positive_6rtz"],
                "parent_result": evidence["homomer_result"],
                "source_preparation": evidence["source_preparation_6rtz"],
            },
        ),
        _composition_assessment(
            case_id="3U7Q_positive_2A_2B",
            crystal_id="3U7Q",
            case_kind=CompositionAssessmentCaseKind.KNOWN_POSITIVE_CONTROL,
            execution_status=positive_3.execution_status,
            placement_observed=positive_3_gate,
            exact_identity_supported=_positive_identity_gate(
                positive_3, positive_3_definition, positive_3_parent
            ),
            scope_status=within_scope,
            scope_decision_id=None,
            scientific_status=(
                CompositionAssessmentStatus.KNOWN_CONTROL_RECOVERED
                if positive_3_gate
                else CompositionAssessmentStatus.SEARCH_EVIDENCE_ONLY
            ),
            complete_composition_claim_eligible=positive_3_gate,
            evidence_sha256={
                "result": evidence["positive_3u7q"],
                "parent_result": evidence["positive_3u7q_parent"],
                "source_preparation": evidence["source_preparation_3u7q"],
            },
        ),
        _composition_assessment(
            case_id="missing_B",
            crystal_id="6RTZ",
            case_kind=CompositionAssessmentCaseKind.MISSING_PARTNER_CONTROL,
            execution_status=ExecutionStatus.COMPLETED_SUCCESS,
            placement_observed=False,
            exact_identity_supported=False,
            scope_status=within_scope,
            scope_decision_id=None,
            scientific_status=CompositionAssessmentStatus.NO_PARTNER_ATTEMPTED,
            complete_composition_claim_eligible=False,
            evidence_sha256={
                "plan": evidence["missing_plan"],
                "summary": evidence["missing_summary"],
                "catalogue_sequence_groups": evidence["catalogue_sequence_groups"],
            },
        ),
        _composition_assessment(
            case_id="wrong_B",
            crystal_id="6RTZ",
            case_kind=CompositionAssessmentCaseKind.WRONG_PARTNER_CONTROL,
            execution_status=wrong.execution_status,
            placement_observed=(
                wrong.execution_status is ExecutionStatus.COMPLETED_HIT
                and wrong.partner_placement_observed
                and wrong.top_solution_packed
            ),
            exact_identity_supported=False,
            scope_status=within_scope,
            scope_decision_id=None,
            scientific_status=CompositionAssessmentStatus.SEARCH_EVIDENCE_ONLY,
            complete_composition_claim_eligible=False,
            evidence_sha256={"result": evidence["wrong_result"]},
        ),
        _composition_assessment(
            case_id="homomer_non_regression",
            crystal_id="6RTZ",
            case_kind=CompositionAssessmentCaseKind.HOMOMER_NON_REGRESSION,
            execution_status=homomer.execution_status,
            placement_observed=homomer_gate,
            exact_identity_supported=homomer_gate,
            scope_status=within_scope,
            scope_decision_id=None,
            scientific_status=CompositionAssessmentStatus.ROUTE_NON_REGRESSION,
            complete_composition_claim_eligible=False,
            evidence_sha256={"result": evidence["homomer_result"]},
        ),
        _composition_assessment(
            case_id="9ECN_three_component_boundary",
            crystal_id=scope.crystal_id,
            case_kind=CompositionAssessmentCaseKind.COMPONENT_SCOPE_BOUNDARY,
            execution_status=ExecutionStatus.COMPLETED_SUCCESS,
            placement_observed=False,
            exact_identity_supported=False,
            scope_status=scope.status,
            scope_decision_id=scope.decision_id,
            scientific_status=CompositionAssessmentStatus(scope.status.value),
            complete_composition_claim_eligible=(
                scope.complete_composition_claim_eligible
            ),
            evidence_sha256={
                "scope_decision": evidence["component_scope_decision"],
                "protocol": evidence["protocol"],
            },
        ),
    )
    assessments_by_case = {item.case_id: item for item in assessments}
    cases = {
        "6RTZ_positive_1A_1B": {
            "gate_passed": positive_6_gate,
            "execution_status": positive_6.execution_status.value,
            "partner_placement_count": positive_6.partner_placement_count,
            "assessment": assessments_by_case["6RTZ_positive_1A_1B"].model_dump(
                mode="json"
            ),
        },
        "3U7Q_positive_2A_2B": {
            "gate_passed": positive_3_gate,
            "execution_status": positive_3.execution_status.value,
            "partner_placement_count": positive_3.partner_placement_count,
            "assessment": assessments_by_case["3U7Q_positive_2A_2B"].model_dump(
                mode="json"
            ),
        },
        "missing_B": {
            "gate_passed": missing_gate,
            "selected_attempt_count": missing_plan.selected_attempt_count,
            "candidate_count": missing_plan.candidate_count,
            "complete_composition_claim_eligible": assessments_by_case[
                "missing_B"
            ].complete_composition_claim_eligible,
            "complete_composition_claimed": assessments_by_case[
                "missing_B"
            ].complete_composition_claimed,
            "assessment": assessments_by_case["missing_B"].model_dump(mode="json"),
        },
        "wrong_B": {
            "gate_passed": wrong_gate,
            "execution_status": wrong.execution_status.value,
            "search_evidence_retained": True,
            "complete_composition_claim_eligible": assessments_by_case[
                "wrong_B"
            ].complete_composition_claim_eligible,
            "complete_composition_claimed": assessments_by_case[
                "wrong_B"
            ].complete_composition_claimed,
            "assessment": assessments_by_case["wrong_B"].model_dump(mode="json"),
        },
        "homomer_non_regression": {
            "gate_passed": homomer_gate,
            "execution_status": homomer.execution_status.value,
            "route": "first_copy",
            "assessment": assessments_by_case["homomer_non_regression"].model_dump(
                mode="json"
            ),
        },
        "9ECN_three_component_boundary": {
            "gate_passed": unsupported_gate,
            "status": assessments_by_case[
                "9ECN_three_component_boundary"
            ].scientific_status.value,
            "retain_partial_a_b_evidence": scope.retain_partial_a_b_evidence,
            "complete_composition_claim_eligible": assessments_by_case[
                "9ECN_three_component_boundary"
            ].complete_composition_claim_eligible,
            "complete_composition_claimed": assessments_by_case[
                "9ECN_three_component_boundary"
            ].complete_composition_claimed,
            "assessment": assessments_by_case[
                "9ECN_three_component_boundary"
            ].model_dump(mode="json"),
        },
    }
    gate_passed = all(bool(case["gate_passed"]) for case in cases.values())
    output = request.output_json.absolute()
    assessments_path = output.with_name("heteromer-composition-assessments.jsonl")
    if output.exists() or assessments_path.exists():
        raise HeteromerControlPreparationError(
            f"P6 report output already exists: {output.parent}"
        )
    atomic_write_text(
        assessments_path,
        "".join(f"{canonical_json_text(item)}\n" for item in assessments),
    )
    evidence["composition_assessments"] = sha256_file(assessments_path)
    report_id = content_id(
        "heteromerslice_",
        {"adapter_version": _ADAPTER_VERSION, "evidence_sha256": evidence},
    )
    report = {
        "schema_version": "1.0",
        "report_id": report_id,
        "adapter_version": _ADAPTER_VERSION,
        "gate_passed": gate_passed,
        "cases": cases,
        "composition_assessments": {
            "path": assessments_path.name,
            "sha256": evidence["composition_assessments"],
            "record_count": len(assessments),
        },
        "evidence_sha256": evidence,
        "limitations": [
            "packing_and_MR_scores_are_search_evidence_not_composition_proof",
            "exactly_two_components_supported",
            "three_component_reconstruction_not_attempted",
        ],
    }
    atomic_write_json(output, report)
    return HeteromerSliceAssessmentResult(
        report_json=output,
        composition_assessments_jsonl=assessments_path,
        report_id=report_id,
        gate_passed=gate_passed,
    )
