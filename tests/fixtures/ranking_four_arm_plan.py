"""Fixed five-case RF task planning, preserving original M6 track provenance.

The complete truth-isolated runner is verified by both production track
planners. Their task files stay immutable; separate reference-labelled channel
tables schedule only the declared five cases and their unique full catalogues.
No scientific tool, scheduler, truth join or human approval runs here. This is
not a completed M6 track or native acceptance evidence. The content identity
binds source, original inputs and every output file; changed, missing, foreign
or escaped assets fail validation. Tests use the actual production runner and
planners with synthetic inputs. Native staging must independently anchor these
inputs, source and the saved manifest digest before any task runs.
"""

import csv
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from tests.fixtures.ranking_four_arm_advancement import (
    REFERENCE_CASE_IDS,
    _source_sha256,
)

from genome_to_diffraction.benchmarks.m6_advancement import _owned
from genome_to_diffraction.benchmarks.m6_nextflow import (
    M6CaseTask,
    M6CatalogueTask,
    M6TrackPlanRequest,
    _load_case_task,
    _load_catalogue_task,
    _load_inventory,
    _object_by_role,
    plan_m6_nextflow_track,
)
from genome_to_diffraction.benchmarks.m6_scientific import (
    M6ScientificTrack,
    m6_track_case_ids,
)
from genome_to_diffraction.benchmarks.m6_verification import _object_path
from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.schemas.base import ContractModel, Sha256Hex

_MANIFEST = "reference_plan.json"
_TRACKS: tuple[M6ScientificTrack, ...] = ("operational", "leakage")


@dataclass(frozen=True)
class ReferencePlanInputs:
    """Original, independently qualified truthless runner and runtime inputs."""

    runner_root: Path
    database_manifest: Path
    software_lock: Path

    def checksums(self) -> dict[str, str]:
        """Bind original inputs without introducing labels into the task graph."""

        return {
            "runner_manifest": sha256_file(self.runner_root / "runner_manifest.json"),
            "database_manifest": sha256_file(self.database_manifest),
            "software_lock": sha256_file(self.software_lock),
        }


class ReferenceCasePlanRow(ContractModel):
    """Original production task and its immutable relative directory."""

    task: M6CaseTask
    task_directory: str


class ReferenceCataloguePlanRow(ContractModel):
    """One unchanged full-catalogue import, shared only by identical keys."""

    task: M6CatalogueTask
    task_directory: str


class ReferenceTaskPlan(ContractModel):
    """Reference subset scheduling, explicitly distinct from M6 acceptance."""

    schema_version: Literal["1.0"] = "1.0"
    adapter_version: Literal["rf-five-case-plan-v1"] = "rf-five-case-plan-v1"
    execution_authority_kind: Literal["truth_blind_rf_reference"] = (
        "truth_blind_rf_reference"
    )
    benchmark_acceptance_claim: Literal[False] = False
    human_approval_granted: Literal[False] = False
    plan_id: str
    source_sha256: dict[str, Sha256Hex]
    input_sha256: dict[str, Sha256Hex]
    output_sha256: dict[str, Sha256Hex]
    cases: tuple[ReferenceCasePlanRow, ...]
    catalogues: tuple[ReferenceCataloguePlanRow, ...]


def _inventory(root: Path, manifest_name: str | None) -> dict[str, str]:
    paths: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("reference plan contains a symlink")
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            if relative != manifest_name:
                paths[relative] = sha256_file(_owned(root, relative))
    return paths


def _rows(
    inputs: ReferencePlanInputs, root: Path
) -> tuple[tuple[ReferenceCasePlanRow, ...], tuple[ReferenceCataloguePlanRow, ...]]:
    inventory = _load_inventory(inputs.runner_root)
    original_cases = {case.case_id: case for case in inventory.cases}
    tracks = {
        case_id: track for track in _TRACKS for case_id in m6_track_case_ids(track)
    }
    cases: list[ReferenceCasePlanRow] = []
    catalogues: dict[str, ReferenceCataloguePlanRow] = {}
    for case_id in REFERENCE_CASE_IDS:
        original = original_cases[case_id]
        track = tracks[case_id]
        prefix = f"production_plans/{track}"
        case_directory = f"{prefix}/case_tasks/{case_id}"
        case_root, task = _load_case_task(
            _owned(root, f"{case_directory}/task.json").parent
        )
        if task.case_id != case_id or task.track != track:
            raise ValueError("reference task changed its original case or track")
        roles = _object_by_role(inputs.runner_root, original)
        for role, filename in (
            ("reflections", "reflections.mtz"),
            ("analysis_config", "analysis_config.json"),
            ("model_policy", "model_policy.json"),
            ("fault_control", "fault_control.json"),
        ):
            if (
                role in roles
                and sha256_file(case_root / filename) != roles[role][1].sha256
            ):
                raise ValueError("reference case differs from its original runner")
        catalogue_directory = f"{prefix}/catalogue_tasks/{task.catalogue_key}"
        _, catalogue = _load_catalogue_task(
            _owned(root, f"{catalogue_directory}/task.json").parent
        )
        if (
            catalogue.catalogue_key != task.catalogue_key
            or catalogue.catalogue_sha256 != roles["catalogue"][1].sha256
            or catalogue.analysis_config_sha256 != task.analysis_config_sha256
            or catalogue.software_lock_sha256 != sha256_file(inputs.software_lock)
        ):
            raise ValueError("reference catalogue changed its original binding")
        old = catalogues.get(task.catalogue_key)
        if old is not None and old.task != catalogue:
            raise ValueError("reference tracks disagree about a shared catalogue")
        if old is None:
            catalogues[task.catalogue_key] = ReferenceCataloguePlanRow(
                task=catalogue, task_directory=catalogue_directory
            )
        cases.append(ReferenceCasePlanRow(task=task, task_directory=case_directory))
    return tuple(cases), tuple(catalogues[key] for key in sorted(catalogues))


def _tables(
    cases: tuple[ReferenceCasePlanRow, ...],
    catalogues: tuple[ReferenceCataloguePlanRow, ...],
) -> dict[str, str]:
    case_table = io.StringIO(newline="")
    writer = csv.writer(case_table, delimiter="\t", lineterminator="\n")
    writer.writerow(("case_id", "catalogue_key", "task_directory"))
    writer.writerows(
        (row.task.case_id, row.task.catalogue_key, row.task_directory) for row in cases
    )
    catalogue_table = io.StringIO(newline="")
    writer = csv.writer(catalogue_table, delimiter="\t", lineterminator="\n")
    writer.writerow(("catalogue_key", "import_cache_key", "task_directory"))
    writer.writerows(
        (row.task.catalogue_key, row.task.import_cache_key, row.task_directory)
        for row in catalogues
    )
    return {
        "reference_case_tasks.tsv": case_table.getvalue(),
        "reference_catalogue_tasks.tsv": catalogue_table.getvalue(),
    }


def _identity(manifest: ReferenceTaskPlan) -> str:
    return content_id("rfplan_", manifest.model_dump(mode="json", exclude={"plan_id"}))


def plan_reference_nextflow(inputs: ReferencePlanInputs, output: Path) -> Path:
    """Verify complete inputs and emit only the frozen five-case channel subset."""

    if output.exists() or output.is_symlink():
        raise ValueError("reference plan output must not already exist")
    before = inputs.checksums()
    source = _source_sha256()
    root = output.resolve()
    for track in _TRACKS:
        plan_m6_nextflow_track(
            M6TrackPlanRequest(
                runner_root=inputs.runner_root,
                database_manifest=inputs.database_manifest,
                software_lock=inputs.software_lock,
                track=track,
                output_directory=root / "production_plans" / track,
            )
        )
    cases, catalogues = _rows(inputs, root)
    for filename, table in _tables(cases, catalogues).items():
        (root / filename).write_text(table, encoding="ascii")
    manifest = ReferenceTaskPlan(
        plan_id="pending",
        source_sha256=source,
        input_sha256=before,
        output_sha256=_inventory(root, _MANIFEST),
        cases=cases,
        catalogues=catalogues,
    )
    if before != inputs.checksums() or source != _source_sha256():
        raise ValueError("reference plan inputs or source changed during planning")
    manifest = manifest.model_copy(update={"plan_id": _identity(manifest)})
    path = root / _MANIFEST
    atomic_write_json(path, manifest.model_dump(mode="json"))
    validate_reference_plan(path, inputs)
    return path


def validate_reference_plan(
    path: Path, inputs: ReferencePlanInputs
) -> ReferenceTaskPlan:
    """Authenticate exact scope, inputs, source and the complete output inventory."""

    root = path.resolve(strict=True).parent
    if path.is_symlink() or path.name != _MANIFEST:
        raise ValueError("reference plan requires its owned canonical manifest")
    manifest = ReferenceTaskPlan.model_validate_json(path.read_bytes())
    if (
        manifest.plan_id != _identity(manifest)
        or manifest.source_sha256 != _source_sha256()
        or manifest.input_sha256 != inputs.checksums()
        or manifest.output_sha256 != _inventory(root, _MANIFEST)
    ):
        raise ValueError("reference plan identity, source, inputs or outputs changed")
    # Check all runner objects, including unselected cases, without copying them.
    inventory = _load_inventory(inputs.runner_root)
    runner = inputs.runner_root.resolve(strict=True)
    expected_files = {
        "runner_manifest.json",
        *(f"objects/{key}" for key in inventory.objects),
    }
    actual_files = {
        file.relative_to(runner).as_posix()
        for file in runner.rglob("*")
        if file.is_file() or file.is_symlink()
    }
    if actual_files != expected_files or (runner / "runner_manifest.json").is_symlink():
        raise ValueError(
            "reference original runner contains missing or foreign objects"
        )
    checked: set[str] = set()
    for case in inventory.cases:
        for spec in case.objects:
            if spec.object not in checked:
                _object_path(runner, spec)
                checked.add(spec.object)
    cases, catalogues = _rows(inputs, root)
    if manifest.cases != cases or manifest.catalogues != catalogues:
        raise ValueError("reference plan differs from the fixed original task subset")
    for filename, expected in _tables(cases, catalogues).items():
        if _owned(root, filename).read_text(encoding="ascii") != expected:
            raise ValueError(
                "reference channel table differs from its exact task subset"
            )
    return manifest
