"""Execute the fixed public 9ECN ``2A+2B+2C`` Phase III control.

This is one scientifically dependent chain inside one fixed control task. It
runs joint two-copy McrA, fixes that parent while placing two McrB copies,
derives exact component-only A/B coordinates, then fixes both independent
uncertainty models while placing two McrG copies. The same A+B parent is then
challenged with the frozen wrong-B control model as a deliberately wrong C.
No step consults unknown datasets or changes thresholds.

The final report applies frozen public-control truth only after execution. The
generic multi-fixed result remains ``search_evidence_only`` and cannot create an
identity or composition claim by itself. Every command, result, coordinate
inventory, runtime, and summary file is checksum-retained. Missing copies,
packing, model provenance, component markers, or atom recombination fails the
control gate.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from genome_to_diffraction.checksums import (
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.diffraction import (
    PreflightRequest,
    build_diffraction_selection,
    preflight_crystals,
)
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.mr import (
    CandidateSearchComponent,
    ExpectedPhaserComponent,
    FixedSearchComponent,
    MultiFixedSearchManifest,
    PartnerSearchRequest,
    PhaserPerPlacementRequest,
    PhaserRunRequest,
    collect_phaser_per_placement_outputs,
    run_first_copy_phaser,
    run_multi_fixed_search,
    run_partner_search,
)
from genome_to_diffraction.schemas.manifests import CrystalManifest
from genome_to_diffraction.schemas.results import (
    MtzPreflightRecord,
    SequenceGroupRecord,
)
from genome_to_diffraction.schemas.v2 import (
    ComponentIdentitySupport,
    ComponentPlacement,
    ComponentScopeDecision,
    ComponentScopeStatus,
    ComponentSpec,
    CompositionAssessment,
    CompositionClaimBoundary,
    CompositionScientificStatus,
    CompositionState,
    CompositionStopReason,
    CompositionSupportState,
    ResidualContentState,
)
from genome_to_diffraction.status import ExecutionStatus, InputContractError

_ADAPTER_VERSION = "9ecn-phase3-depth-three-control-v3-wrong-c-assessment"
_DIGEST = re.compile(r"^[a-f0-9]{64}$")


class Phase3ControlExecutionError(InputContractError):
    """The fixed 9ECN execution or its evidence is incomplete."""


@dataclass(frozen=True, slots=True)
class Phase3ControlExecutionRequest:
    """Exact prepared inputs and installed runtime for the fixed control."""

    preparation_directory: Path
    phenix_manifest: Path
    wrong_c_sequence_groups_jsonl: Path
    wrong_c_sequence_group_id: str
    wrong_c_model: Path
    wrong_c_control_manifest: Path
    expected_wrong_c_model_sha256: str
    wrong_c_model_identity_fraction: float
    output_directory: Path
    threads: int = 1
    timeout_seconds: float | None = None
    progress: bool = True


@dataclass(frozen=True, slots=True)
class Phase3ControlExecutionResult:
    """Accepted report and checksum manifest paths."""

    report: Path
    checksums: Path
    placement_inventory: Path


def _load(path: Path) -> dict[str, object]:
    try:
        document = json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise Phase3ControlExecutionError(f"invalid fixed 9ECN JSON: {path}") from error
    if not isinstance(document, dict):
        raise Phase3ControlExecutionError(f"fixed 9ECN JSON is not an object: {path}")
    return document


def _file(root: Path, record: object, *, role: str) -> Path:
    if not isinstance(record, dict):
        raise Phase3ControlExecutionError(f"9ECN {role} file record is absent")
    relative = record.get("path")
    digest = record.get("sha256")
    size = record.get("size_bytes")
    if (
        not isinstance(relative, str)
        or not isinstance(digest, str)
        or _DIGEST.fullmatch(digest) is None
        or not isinstance(size, int)
        or isinstance(size, bool)
    ):
        raise Phase3ControlExecutionError(f"9ECN {role} file record is malformed")
    path = (root / relative).resolve(strict=True)
    if (
        root not in path.parents
        or path.is_symlink()
        or not path.is_file()
        or path.stat().st_size != size
        or sha256_file(path, progress=False) != digest
    ):
        raise Phase3ControlExecutionError(f"9ECN {role} file identity differs")
    return path


def _component_rows(document: dict[str, object]) -> dict[str, dict[str, object]]:
    rows = document.get("components")
    if not isinstance(rows, list):
        raise Phase3ControlExecutionError("9ECN preparation lacks components")
    by_label = {
        row.get("label"): row
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("label"), str)
    }
    if tuple(sorted(by_label)) != ("A", "B", "C"):
        raise Phase3ControlExecutionError("9ECN preparation is not exact A+B+C")
    for label, row in by_label.items():
        if (
            row.get("requested_copy_count") != 2
            or not isinstance(row.get("sequence_group_id"), str)
            or not isinstance(row.get("model_id"), str)
            or not isinstance(row.get("model_sha256"), str)
            or _DIGEST.fullmatch(str(row["model_sha256"])) is None
            or not isinstance(row.get("catalogue_sequence_sha256"), str)
            or _DIGEST.fullmatch(str(row["catalogue_sequence_sha256"])) is None
        ):
            raise Phase3ControlExecutionError(
                f"9ECN component {label} identity is incomplete"
            )
    return by_label


def _parent_values(
    result_path: Path, command_path: Path
) -> tuple[float, Path, str, float, str]:
    result = _load(result_path)
    command = _load(command_path)
    llg = result.get("llg")
    relative = result.get("solution_coordinate_path")
    digest = result.get("solution_coordinate_sha256")
    identity = command.get("model_identity_percent")
    uncertainty = command.get("model_uncertainty_source")
    if (
        result.get("execution_status") != "completed_hit"
        or result.get("placed_copy_count") != 2
        or isinstance(llg, bool)
        or not isinstance(llg, int | float)
        or not math.isfinite(float(llg))
        or not isinstance(relative, str)
        or not isinstance(digest, str)
        or _DIGEST.fullmatch(digest) is None
        or isinstance(identity, bool)
        or not isinstance(identity, int | float)
        or not 0 < float(identity) <= 100
        or not isinstance(uncertainty, str)
        or not uncertainty.strip()
    ):
        raise Phase3ControlExecutionError("9ECN A parent lacks exact packed provenance")
    coordinate = (result_path.parent / relative).resolve(strict=True)
    if sha256_file(coordinate, progress=False) != digest:
        raise Phase3ControlExecutionError("9ECN A parent coordinate changed")
    return float(llg), coordinate, digest, float(identity) / 100, uncertainty


def _component_group(inventory: dict[str, object], label: str) -> dict[str, object]:
    groups = inventory.get("component_groups")
    matches = (
        [
            row
            for row in groups
            if isinstance(row, dict) and row.get("component_label") == label
        ]
        if isinstance(groups, list)
        else []
    )
    if len(matches) != 1:
        raise Phase3ControlExecutionError(f"9ECN inventory lacks component {label}")
    row = matches[0]
    if row.get("expected_copy_count") != 2 or row.get("observed_copy_count") != 2:
        raise Phase3ControlExecutionError(f"9ECN component {label} copy count differs")
    return row


def _sequence_group_index(path: Path) -> dict[str, SequenceGroupRecord]:
    records: dict[str, SequenceGroupRecord] = {}
    try:
        lines = path.resolve(strict=True).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise Phase3ControlExecutionError(
            "cannot read control sequence groups"
        ) from error
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = SequenceGroupRecord.model_validate_json(line)
        except ValueError as error:
            raise Phase3ControlExecutionError(
                f"invalid control sequence group at line {line_number}"
            ) from error
        if record.sequence_group_id in records:
            raise Phase3ControlExecutionError("duplicate control sequence group")
        records[record.sequence_group_id] = record
    if not records:
        raise Phase3ControlExecutionError("control sequence groups are empty")
    return records


def _diffraction_selection(
    crystal_manifest: Path,
    preflight_jsonl: Path,
):
    try:
        crystals = CrystalManifest.model_validate_json(crystal_manifest.read_bytes())
        rows = tuple(
            MtzPreflightRecord.model_validate_json(line)
            for line in preflight_jsonl.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    except (OSError, UnicodeError, ValueError) as error:
        raise Phase3ControlExecutionError(
            "9ECN diffraction selection evidence is invalid"
        ) from error
    crystal_matches = tuple(
        item for item in crystals.crystals if item.crystal_id == "9ECN"
    )
    preflight_matches = tuple(item for item in rows if item.crystal_id == "9ECN")
    if len(crystal_matches) != 1 or len(preflight_matches) != 1:
        raise Phase3ControlExecutionError("9ECN lacks one exact diffraction selection")
    return build_diffraction_selection(
        crystal=crystal_matches[0],
        preflight=preflight_matches[0],
        crystal_manifest_sha256=sha256_file(crystal_manifest, progress=False),
    )


def _validate_wrong_c_control(
    *,
    manifest_path: Path,
    sequence_groups: Path,
    sequence_group_id: str,
    model: Path,
    model_sha256: str,
    positive_model_sha256s: frozenset[str],
) -> None:
    manifest = _load(manifest_path)
    wrong = manifest.get("wrong_partner")
    positive = manifest.get("positive_controls")
    files = manifest.get("files")
    positive_3u7q = positive.get("3U7Q") if isinstance(positive, dict) else None
    wrong_model_record = (
        files.get("wrong_partner_model") if isinstance(files, dict) else None
    )
    wrong_groups_record = (
        files.get("wrong_sequence_groups") if isinstance(files, dict) else None
    )
    if (
        manifest.get("adapter_version") != "heteromer-p6-control-slice-v2"
        or not isinstance(wrong, dict)
        or not isinstance(positive_3u7q, dict)
        or wrong.get("partner_sequence_group_id") != sequence_group_id
        or wrong.get("partner_model_sha256") != model_sha256
        or positive_3u7q.get("partner_sequence_group_id") != sequence_group_id
        or positive_3u7q.get("partner_model_sha256") != model_sha256
        or model_sha256 in positive_model_sha256s
    ):
        raise Phase3ControlExecutionError(
            "wrong-C frozen negative-control identity differs"
        )
    root = manifest_path.resolve(strict=True).parent
    retained_model = _file(root, wrong_model_record, role="wrong-C model")
    retained_groups = _file(root, wrong_groups_record, role="wrong-C groups")
    if retained_model != model.resolve(
        strict=True
    ) or retained_groups != sequence_groups.resolve(strict=True):
        raise Phase3ControlExecutionError(
            "wrong-C files differ from frozen negative-control manifest"
        )


def run_9ecn_phase3_control(
    request: Phase3ControlExecutionRequest,
) -> Phase3ControlExecutionResult:
    """Run and validate the fixed depth-three control."""

    if request.threads < 1 or (
        request.timeout_seconds is not None and request.timeout_seconds <= 0
    ):
        raise ValueError("threads and optional timeout must be positive")
    if (
        _DIGEST.fullmatch(request.expected_wrong_c_model_sha256) is None
        or not 0 < request.wrong_c_model_identity_fraction <= 1
    ):
        raise ValueError("wrong-C checksum and identity must be valid")
    prepared = request.preparation_directory.resolve(strict=True)
    manifest_path = prepared / "preparation_manifest.json"
    preparation = _load(manifest_path)
    if (
        preparation.get("adapter_version") != "9ecn-fixed-two-a-two-b-two-c-inputs-v1"
        or preparation.get("crystal_id") != "9ECN"
        or preparation.get("composition") != {"A": 2, "B": 2, "C": 2}
    ):
        raise Phase3ControlExecutionError("prepared input is not fixed 9ECN 2A+2B+2C")
    components = _component_rows(preparation)
    files = preparation.get("files")
    if not isinstance(files, dict):
        raise Phase3ControlExecutionError("9ECN preparation file inventory is absent")
    crystal_manifest = _file(prepared, files.get("crystal_manifest"), role="crystals")
    sequence_groups = _file(prepared, files.get("sequence_groups"), role="sequences")
    processed_models = _file(prepared, files.get("processed_models"), role="models")
    model_manifest = _file(
        prepared,
        files.get("model_preparation_manifest"),
        role="model manifest",
    )
    hypotheses = _file(prepared, files.get("hypotheses"), role="hypotheses")
    mtz = _file(prepared, files.get("mtz"), role="MTZ")
    models = {
        label: _file(
            prepared, files.get(f"component_{label}_model"), role=f"model {label}"
        )
        for label in ("A", "B", "C")
    }
    if any(
        sha256_file(models[label], progress=False)
        != str(components[label]["model_sha256"])
        for label in ("A", "B", "C")
    ):
        raise Phase3ControlExecutionError("9ECN component model identity differs")
    control_groups = _sequence_group_index(sequence_groups)
    wrong_groups = _sequence_group_index(request.wrong_c_sequence_groups_jsonl)
    wrong_group = wrong_groups.get(request.wrong_c_sequence_group_id)
    component_group_ids = {
        str(components[label]["sequence_group_id"]) for label in ("A", "B", "C")
    }
    if (
        set(control_groups) != component_group_ids
        or wrong_group is None
        or wrong_group.sequence_group_id in component_group_ids
    ):
        raise Phase3ControlExecutionError("wrong-C sequence identity is not distinct")
    wrong_model = request.wrong_c_model.resolve(strict=True)
    if (
        sha256_file(wrong_model, progress=False)
        != request.expected_wrong_c_model_sha256
    ):
        raise Phase3ControlExecutionError("wrong-C model identity differs")
    _validate_wrong_c_control(
        manifest_path=request.wrong_c_control_manifest,
        sequence_groups=request.wrong_c_sequence_groups_jsonl,
        sequence_group_id=wrong_group.sequence_group_id,
        model=wrong_model,
        model_sha256=request.expected_wrong_c_model_sha256,
        positive_model_sha256s=frozenset(
            str(components[label]["model_sha256"]) for label in ("A", "B", "C")
        ),
    )
    output = request.output_directory.absolute()
    if output.exists() and any(output.iterdir()):
        raise Phase3ControlExecutionError("9ECN execution output is not empty")
    output.mkdir(parents=True, exist_ok=True)
    provenance = output / "provenance"
    provenance.mkdir()
    preparation_snapshot = provenance / "preparation_manifest.json"
    phenix_snapshot = provenance / "phenix_manifest.json"
    atomic_write_bytes(preparation_snapshot, manifest_path.read_bytes())
    atomic_write_bytes(
        phenix_snapshot,
        request.phenix_manifest.resolve(strict=True).read_bytes(),
    )
    preflight = preflight_crystals(
        PreflightRequest(
            crystal_manifest=crystal_manifest,
            output_directory=output / "preflight",
            phenix_manifest=request.phenix_manifest,
            progress=request.progress,
            xtriage_timeout_seconds=None,
        )
    )
    diffraction_selection = _diffraction_selection(
        crystal_manifest,
        preflight.jsonl_path,
    )
    parent = run_first_copy_phaser(
        PhaserRunRequest(
            hypotheses_jsonl=hypotheses,
            hypothesis_id=str(preparation["parent_hypothesis_id"]),
            sequence_groups_jsonl=sequence_groups,
            processed_models_jsonl=processed_models,
            model_preparation_manifest=model_manifest,
            preflight_jsonl=preflight.jsonl_path,
            mtz=mtz,
            phenix_manifest=request.phenix_manifest,
            output_directory=output / "parent_A",
            threads=request.threads,
            timeout_seconds=request.timeout_seconds,
            progress=request.progress,
        )
    )
    parent_llg, parent_coordinate, parent_sha, parent_identity, parent_uncertainty = (
        _parent_values(parent.result_json, parent.command_json)
    )
    component_a = components["A"]
    component_b = components["B"]
    component_c = components["C"]
    partner = run_partner_search(
        PartnerSearchRequest(
            crystal_id="9ECN",
            parent_solution_id=f"joint_{preparation['parent_hypothesis_id']}",
            parent_sequence_group_id=str(component_a["sequence_group_id"]),
            partner_sequence_group_id=str(component_b["sequence_group_id"]),
            sequence_groups_jsonl=sequence_groups,
            parent_coordinate=parent_coordinate,
            expected_parent_coordinate_sha256=parent_sha,
            parent_llg=parent_llg,
            parent_model_identity_fraction=parent_identity,
            parent_model_uncertainty_source=parent_uncertainty,
            parent_copy_count=2,
            partner_model=models["B"],
            expected_partner_model_sha256=str(component_b["model_sha256"]),
            partner_model_identity_fraction=1.0,
            partner_copy_count=2,
            preflight_jsonl=preflight.jsonl_path,
            mtz=mtz,
            phenix_manifest=request.phenix_manifest,
            output_directory=output / "partner_B",
            diffraction_selection=diffraction_selection,
            threads=request.threads,
            timeout_seconds=request.timeout_seconds,
            progress=request.progress,
        )
    )
    if partner.result.execution_status is not ExecutionStatus.COMPLETED_HIT:
        raise Phase3ControlExecutionError("9ECN did not recover fixed-A/search-B")
    if (
        partner.result.combined_solution_id is None
        or partner.result.combined_llg is None
    ):
        raise Phase3ControlExecutionError("9ECN A+B parent lacks its exact identity")
    ab_inventory = collect_phaser_per_placement_outputs(
        PhaserPerPlacementRequest(
            crystal_id="9ECN",
            search_id=partner.result.search_id,
            phaser_version=partner.result.tool_version,
            output_directory=output / "partner_B",
            command_record=partner.command_json,
            result_record=partner.result_json,
            expected_components=(
                ExpectedPhaserComponent("A", "fixed_parent", 2),
                ExpectedPhaserComponent("B", "search_partner", 2),
            ),
            component_models=(("A", models["A"]), ("B", models["B"])),
        )
    )
    ab_document = _load(ab_inventory.inventory_json)
    fixed_rows = {label: _component_group(ab_document, label) for label in ("A", "B")}
    partner_command = _load(partner.command_json)
    b_identity = partner_command.get("partner_model_identity_fraction")
    if isinstance(b_identity, bool) or not isinstance(b_identity, int | float):
        raise Phase3ControlExecutionError("9ECN B uncertainty is absent")
    fixed_components = tuple(
        FixedSearchComponent(
            schema_version="2.0",
            label=label,
            sequence_group_id=str(components[label]["sequence_group_id"]),
            model_id=str(components[label]["model_id"]),
            model_sha256=str(components[label]["model_sha256"]),
            coordinate_path=str(
                output / "partner_B" / str(fixed_rows[label]["coordinate_path"])
            ),
            coordinate_sha256=str(fixed_rows[label]["coordinate_sha256"]),
            requested_copy_count=2,
            observed_copy_count=2,
            phaser_identity_fraction=(
                parent_identity if label == "A" else float(b_identity)
            ),
            model_uncertainty_source=(
                parent_uncertainty
                if label == "A"
                else "exact catalogue-aligned experimental control model"
            ),
            model_uncertainty_evidence_sha256=str(
                components[label]["catalogue_sequence_sha256"]
            ),
        )
        for label in ("A", "B")
    )
    expansion_manifest = output / "component_C_input.json"
    atomic_write_json(
        expansion_manifest,
        MultiFixedSearchManifest(
            schema_version="2.0",
            adapter_version="multi-fixed-component-search-input-v2",
            crystal_id="9ECN",
            diffraction_selection=diffraction_selection,
            parent_solution_id=partner.result.combined_solution_id,
            parent_combined_llg=partner.result.combined_llg,
            fixed_components=fixed_components,
            candidate=CandidateSearchComponent(
                schema_version="2.0",
                label="C",
                sequence_group_id=str(component_c["sequence_group_id"]),
                model_id=str(component_c["model_id"]),
                model_sha256=str(component_c["model_sha256"]),
                model_path=str(models["C"]),
                requested_copy_count=2,
                phaser_identity_fraction=1.0,
                model_uncertainty_source=(
                    "exact catalogue-aligned experimental control model"
                ),
                model_uncertainty_evidence_sha256=str(
                    component_c["catalogue_sequence_sha256"]
                ),
            ),
        ).model_dump(mode="json"),
    )
    component_c_result = run_multi_fixed_search(
        manifest_path=expansion_manifest,
        sequence_groups_jsonl=sequence_groups,
        preflight_jsonl=preflight.jsonl_path,
        mtz_path=mtz,
        phenix_manifest=request.phenix_manifest,
        output_directory=output / "component_C",
        threads=request.threads,
        timeout_seconds=request.timeout_seconds,
    )
    result_path = output / "component_C/component_search_result.json"
    if component_c_result.execution_status is not ExecutionStatus.COMPLETED_HIT:
        raise Phase3ControlExecutionError("9ECN did not recover component C")
    c_inventory = collect_phaser_per_placement_outputs(
        PhaserPerPlacementRequest(
            crystal_id="9ECN",
            search_id=component_c_result.search_id,
            phaser_version=component_c_result.tool_version,
            output_directory=output / "component_C",
            command_record=output / "component_C/phaser_command.json",
            result_record=result_path,
            expected_components=(
                ExpectedPhaserComponent("A", "fixed_A", 2),
                ExpectedPhaserComponent("B", "fixed_B", 2),
                ExpectedPhaserComponent("C", "search_C", 2),
            ),
            component_models=(
                ("A", models["A"]),
                ("B", models["B"]),
                ("C", models["C"]),
            ),
        )
    )
    inventory = _load(c_inventory.inventory_json)
    groups = {label: _component_group(inventory, label) for label in ("A", "B", "C")}
    gate = (
        component_c_result.top_solution_packed
        and component_c_result.fixed_components_observed
        and component_c_result.candidate_placement_observed
        and inventory.get("recombination_status")
        == "verified_exact_combined_atom_partition"
        and inventory.get("combined_atom_count")
        == inventory.get("recombined_atom_count")
        and all(row.get("observed_copy_count") == 2 for row in groups.values())
    )
    if not gate:
        raise Phase3ControlExecutionError("9ECN depth-three placement gate failed")
    wrong_sequence_groups = output / "wrong_C_sequence_groups.jsonl"
    atomic_write_text(
        wrong_sequence_groups,
        "".join(
            f"{canonical_json_text(group)}\n"
            for group in sorted(
                (
                    control_groups[str(component_a["sequence_group_id"])],
                    control_groups[str(component_b["sequence_group_id"])],
                    wrong_group,
                ),
                key=lambda item: item.sequence_group_id,
            )
        ),
    )
    wrong_manifest = output / "wrong_C_input.json"
    atomic_write_json(
        wrong_manifest,
        MultiFixedSearchManifest(
            schema_version="2.0",
            adapter_version="multi-fixed-component-search-input-v2",
            crystal_id="9ECN",
            diffraction_selection=diffraction_selection,
            parent_solution_id=partner.result.combined_solution_id,
            parent_combined_llg=partner.result.combined_llg,
            fixed_components=fixed_components,
            candidate=CandidateSearchComponent(
                schema_version="2.0",
                label="C",
                sequence_group_id=wrong_group.sequence_group_id,
                model_id=f"wrong_c_{request.expected_wrong_c_model_sha256}",
                model_sha256=request.expected_wrong_c_model_sha256,
                model_path=str(wrong_model),
                requested_copy_count=2,
                phaser_identity_fraction=request.wrong_c_model_identity_fraction,
                model_uncertainty_source="frozen distinct public-control wrong model",
                model_uncertainty_evidence_sha256=wrong_group.sha256,
            ),
        ).model_dump(mode="json"),
    )
    wrong_c_result = run_multi_fixed_search(
        manifest_path=wrong_manifest,
        sequence_groups_jsonl=wrong_sequence_groups,
        preflight_jsonl=preflight.jsonl_path,
        mtz_path=mtz,
        phenix_manifest=request.phenix_manifest,
        output_directory=output / "wrong_C",
        threads=request.threads,
        timeout_seconds=request.timeout_seconds,
    )
    if wrong_c_result.execution_status not in {
        ExecutionStatus.COMPLETED_HIT,
        ExecutionStatus.COMPLETED_NO_HIT,
    }:
        raise Phase3ControlExecutionError("wrong-C search did not complete")
    if (
        wrong_c_result.scientific_status != "search_evidence_only"
        or wrong_c_result.exact_identity_claimed
        or wrong_c_result.complete_composition_claimed
    ):
        raise Phase3ControlExecutionError("wrong-C search promoted a scientific claim")
    parent_document = _load(parent.result_json)
    parent_tfz = parent_document.get("tfz")
    if isinstance(parent_tfz, bool) or not isinstance(parent_tfz, int | float):
        raise Phase3ControlExecutionError("9ECN A parent TFZ is absent")
    component_specs = {
        label: ComponentSpec.from_content(
            label=label,
            sequence_group_id=str(components[label]["sequence_group_id"]),
            sequence_sha256=control_groups[
                str(components[label]["sequence_group_id"])
            ].sha256,
            model_id=str(components[label]["model_id"]),
            model_sha256=str(components[label]["model_sha256"]),
            requested_copy_count=2,
            sequence_mass_da=control_groups[
                str(components[label]["sequence_group_id"])
            ].molecular_mass_da,
            mass_evidence_sha256=control_groups[
                str(components[label]["sequence_group_id"])
            ].sha256,
            model_evidence_sha256=str(components[label]["catalogue_sequence_sha256"]),
        )
        for label in ("A", "B")
    }
    parent_placements = {
        "A": ComponentPlacement.from_content(
            component_spec_id=component_specs["A"].component_spec_id,
            component_label="A",
            sequence_group_id=component_specs["A"].sequence_group_id,
            model_id=component_specs["A"].model_id,
            model_sha256=component_specs["A"].model_sha256,
            requested_copy_count=2,
            observed_copy_count=2,
            execution_status=ExecutionStatus.COMPLETED_HIT,
            component_tfz=float(parent_tfz),
            incremental_llg=parent_llg,
            packing_passed=True,
            coordinate_sha256=str(fixed_rows["A"]["coordinate_sha256"]),
            identity_support=ComponentIdentitySupport.UNRESOLVED,
        ),
        "B": ComponentPlacement.from_content(
            component_spec_id=component_specs["B"].component_spec_id,
            component_label="B",
            sequence_group_id=component_specs["B"].sequence_group_id,
            model_id=component_specs["B"].model_id,
            model_sha256=component_specs["B"].model_sha256,
            requested_copy_count=2,
            observed_copy_count=2,
            execution_status=ExecutionStatus.COMPLETED_HIT,
            component_tfz=partner.result.partner_tfz,
            incremental_llg=partner.result.incremental_llg,
            packing_passed=partner.result.top_solution_packed,
            coordinate_sha256=str(fixed_rows["B"]["coordinate_sha256"]),
            identity_support=ComponentIdentitySupport.UNRESOLVED,
        ),
    }
    if (
        partner.result.combined_coordinate_sha256 is None
        or partner.result.output_mtz_sha256 is None
    ):
        raise Phase3ControlExecutionError("9ECN A+B parent assets are absent")
    parent_mass = sum(
        component.sequence_mass_da * component.requested_copy_count
        for component in component_specs.values()
        if component.sequence_mass_da is not None
    )
    a_mass = component_specs["A"].sequence_mass_da
    parent_mtz_sha256 = parent_document.get("output_mtz_sha256")
    if a_mass is None or not isinstance(parent_mtz_sha256, str):
        raise Phase3ControlExecutionError("9ECN A state mass or MTZ is absent")
    a_state = CompositionState.from_content(
        crystal_id="9ECN",
        diffraction_dataset_id=diffraction_selection.diffraction_dataset_id,
        diffraction_sha256=diffraction_selection.mtz_sha256,
        parent_state_id=None,
        depth=1,
        components=(component_specs["A"],),
        placements=(parent_placements["A"],),
        combined_coordinate_sha256=parent_sha,
        combined_mtz_sha256=parent_mtz_sha256,
        physical_mass_lower_da=a_mass * 2,
        physical_mass_upper_da=a_mass * 2,
        support_state=CompositionSupportState.PACKED,
    )
    parent_state = CompositionState.from_content(
        crystal_id="9ECN",
        diffraction_dataset_id=diffraction_selection.diffraction_dataset_id,
        diffraction_sha256=diffraction_selection.mtz_sha256,
        parent_state_id=a_state.state_id,
        depth=2,
        components=(component_specs["A"], component_specs["B"]),
        placements=(parent_placements["A"], parent_placements["B"]),
        combined_coordinate_sha256=partner.result.combined_coordinate_sha256,
        combined_mtz_sha256=partner.result.output_mtz_sha256,
        physical_mass_lower_da=parent_mass,
        physical_mass_upper_da=parent_mass,
        support_state=CompositionSupportState.PACKED,
    )
    assessment_state = parent_state
    wrong_inventory_sha256: str | None = None
    if wrong_c_result.execution_status is ExecutionStatus.COMPLETED_HIT:
        wrong_inventory_output = collect_phaser_per_placement_outputs(
            PhaserPerPlacementRequest(
                crystal_id="9ECN",
                search_id=wrong_c_result.search_id,
                phaser_version=wrong_c_result.tool_version,
                output_directory=output / "wrong_C",
                command_record=output / "wrong_C/phaser_command.json",
                result_record=output / "wrong_C/component_search_result.json",
                expected_components=(
                    ExpectedPhaserComponent("A", "fixed_A", 2),
                    ExpectedPhaserComponent("B", "fixed_B", 2),
                    ExpectedPhaserComponent("C", "search_C", 2),
                ),
                component_models=(
                    ("A", models["A"]),
                    ("B", models["B"]),
                    ("C", wrong_model),
                ),
            )
        )
        wrong_inventory = _load(wrong_inventory_output.inventory_json)
        wrong_group_coordinates = _component_group(wrong_inventory, "C")
        wrong_observed_copies = wrong_group_coordinates.get("observed_copy_count")
        if isinstance(wrong_observed_copies, bool) or not isinstance(
            wrong_observed_copies,
            int,
        ):
            raise Phase3ControlExecutionError("wrong-C observed copy count is invalid")
        wrong_inventory_sha256 = sha256_file(
            wrong_inventory_output.inventory_json,
            progress=False,
        )
        wrong_spec = ComponentSpec.from_content(
            label="C",
            sequence_group_id=wrong_group.sequence_group_id,
            sequence_sha256=wrong_group.sha256,
            model_id=f"wrong_c_{request.expected_wrong_c_model_sha256}",
            model_sha256=request.expected_wrong_c_model_sha256,
            requested_copy_count=2,
            sequence_mass_da=wrong_group.molecular_mass_da,
            mass_evidence_sha256=wrong_group.sha256,
            model_evidence_sha256=wrong_group.sha256,
        )
        if (
            wrong_c_result.candidate_tfz is None
            or wrong_c_result.incremental_llg is None
            or wrong_c_result.combined_coordinate_sha256 is None
            or wrong_c_result.output_mtz_sha256 is None
        ):
            raise Phase3ControlExecutionError("wrong-C hit lacks terminal evidence")
        wrong_placement = ComponentPlacement.from_content(
            component_spec_id=wrong_spec.component_spec_id,
            component_label="C",
            sequence_group_id=wrong_spec.sequence_group_id,
            model_id=wrong_spec.model_id,
            model_sha256=wrong_spec.model_sha256,
            requested_copy_count=2,
            observed_copy_count=wrong_observed_copies,
            execution_status=ExecutionStatus.COMPLETED_HIT,
            component_tfz=wrong_c_result.candidate_tfz,
            incremental_llg=wrong_c_result.incremental_llg,
            packing_passed=wrong_c_result.top_solution_packed,
            coordinate_sha256=str(wrong_group_coordinates["coordinate_sha256"]),
            identity_support=ComponentIdentitySupport.UNRESOLVED,
        )
        wrong_mass = wrong_group.molecular_mass_da
        if wrong_mass is None:
            raise Phase3ControlExecutionError("wrong-C sequence mass is absent")
        wrong_support = (
            CompositionSupportState.PACKED
            if wrong_c_result.top_solution_packed
            and wrong_placement.observed_copy_count == 2
            else CompositionSupportState.SEARCH_EVIDENCE_ONLY
        )
        assessment_state = CompositionState.from_content(
            crystal_id="9ECN",
            diffraction_dataset_id=diffraction_selection.diffraction_dataset_id,
            diffraction_sha256=diffraction_selection.mtz_sha256,
            parent_state_id=parent_state.state_id,
            depth=3,
            components=(*parent_state.components, wrong_spec),
            placements=(*parent_state.placements, wrong_placement),
            combined_coordinate_sha256=(wrong_c_result.combined_coordinate_sha256),
            combined_mtz_sha256=wrong_c_result.output_mtz_sha256,
            physical_mass_lower_da=parent_mass + wrong_mass * 2,
            physical_mass_upper_da=parent_mass + wrong_mass * 2,
            support_state=wrong_support,
            warnings=("frozen_wrong_component_negative_control",),
        )
    retained_packed = int(
        assessment_state.support_state is CompositionSupportState.PACKED
        and assessment_state.depth == 3
    )
    stop_reason = (
        CompositionStopReason.NO_PHYSICALLY_POSSIBLE_REMAINING_COMPONENT
        if retained_packed
        else CompositionStopReason.NO_RETAINED_PACKED_STATE
    )
    scope = ComponentScopeDecision.from_content(
        crystal_id="9ECN",
        state_id=assessment_state.state_id,
        search_depth_reached=assessment_state.depth,
        maximum_search_depth=6,
        validated_component_depth=3,
        total_additional_attempt_budget=100,
        total_additional_attempts_used=1,
        remaining_physical_hypothesis_count=0,
        retained_packed_state_count=retained_packed,
        state_support_state=assessment_state.support_state,
        stop_reason=stop_reason,
        residual_content_state=ResidualContentState.UNRESOLVED,
        scope_status=ComponentScopeStatus.WITHIN_VALIDATED_COMPONENT_DEPTH,
        claim_boundary=CompositionClaimBoundary.PARTIAL_OR_RESIDUAL_ONLY,
        complete_composition_claim_eligible=False,
        warnings=("frozen_wrong_component_negative_control",),
    )
    assessment_evidence = {
        "negative_control_manifest": sha256_file(
            request.wrong_c_control_manifest,
            progress=False,
        ),
        "wrong_c_result": sha256_file(
            output / "wrong_C/component_search_result.json",
            progress=False,
        ),
    }
    if wrong_inventory_sha256 is not None:
        assessment_evidence["wrong_c_placement_inventory"] = wrong_inventory_sha256
    wrong_assessment = CompositionAssessment.from_content(
        crystal_id="9ECN",
        state_id=assessment_state.state_id,
        scope_decision=scope,
        execution_status=wrong_c_result.execution_status,
        state_support_state=assessment_state.support_state,
        scientific_status=CompositionScientificStatus.SEARCH_EVIDENCE_ONLY,
        complete_composition_claim_eligible=False,
        complete_composition_claimed=False,
        evidence_sha256=assessment_evidence,
        warnings=("frozen_wrong_component_negative_control",),
    )
    wrong_assessment_path = output / "wrong_C/composition_assessment.json"
    atomic_write_json(wrong_assessment_path, wrong_assessment.model_dump(mode="json"))
    report = output / "phase3-9ecn-control-summary.json"
    atomic_write_json(
        report,
        {
            "schema_version": "1.0",
            "adapter_version": _ADAPTER_VERSION,
            "control": "9ECN_McrA_McrB_McrG_2A_2B_2C",
            "gate_passed": True,
            "known_control_status": "known_control_recovered",
            "generic_scientific_status": component_c_result.scientific_status,
            "exact_identity_claimed_by_search": False,
            "complete_composition_claimed_by_search": False,
            "wrong_c_claim_boundary_passed": True,
            "wrong_c_execution_status": wrong_c_result.execution_status,
            "wrong_c_top_solution_packed": wrong_c_result.top_solution_packed,
            "wrong_c_candidate_tfz": wrong_c_result.candidate_tfz,
            "wrong_c_incremental_llg": wrong_c_result.incremental_llg,
            "wrong_c_exact_identity_claimed": False,
            "wrong_c_complete_composition_claimed": False,
            "wrong_c_assessment_id": wrong_assessment.assessment_id,
            "wrong_c_scientific_status": wrong_assessment.scientific_status,
            "wrong_c_assessment_claim_eligible": (
                wrong_assessment.complete_composition_claim_eligible
            ),
            "wrong_c_assessment_claimed": wrong_assessment.complete_composition_claimed,
            "component_copy_counts": {
                label: groups[label]["observed_copy_count"] for label in ("A", "B", "C")
            },
            "candidate_tfz": component_c_result.candidate_tfz,
            "incremental_llg": component_c_result.incremental_llg,
            "combined_atom_count": inventory.get("combined_atom_count"),
            "preparation_manifest_sha256": sha256_file(
                preparation_snapshot,
                progress=False,
            ),
            "phenix_manifest_sha256": sha256_file(
                phenix_snapshot,
                progress=False,
            ),
            "placement_inventory": "component_C/phaser_per_placement_inventory.json",
            "result": "component_C/component_search_result.json",
            "wrong_c_result": "wrong_C/component_search_result.json",
            "wrong_c_assessment": "wrong_C/composition_assessment.json",
        },
    )
    for path in output.rglob("*"):
        if path.is_symlink():
            raise Phase3ControlExecutionError(
                f"9ECN execution created a symlink: {path.relative_to(output)}"
            )
    retained = tuple(
        sorted(
            (path for path in output.rglob("*") if path.is_file()),
            key=lambda path: path.relative_to(output).as_posix(),
        )
    )
    checksums = output / "phase3-9ecn-control-checksums.sha256"
    checksum_lines: list[str] = []
    for path in retained:
        relative = path.relative_to(output)
        checksum_lines.append(f"{sha256_file(path, progress=False)}  {relative}\n")
    atomic_write_text(checksums, "".join(checksum_lines))
    return Phase3ControlExecutionResult(report, checksums, c_inventory.inventory_json)


__all__ = [
    "Phase3ControlExecutionError",
    "Phase3ControlExecutionRequest",
    "Phase3ControlExecutionResult",
    "run_9ecn_phase3_control",
]
