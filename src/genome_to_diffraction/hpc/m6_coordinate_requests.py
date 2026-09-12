"""Freeze the failed fixed M6 control's truthless coordinate request inventory.

Inputs are a bounded, owned producer archive and the prior terminal collection.
The output preserves original producer bytes and derives the same eligible and
three-hit-per-group requests used by the offline coordinate adapter. No network,
cache publication, MR admission, or scientific status change occurs here. Invalid
paths, checksums, producer joins, or incomplete cases fail before publication.
The snapshot identity hashes every collected input and derived request file.
"""

import csv
import io
import re
import shlex
import tarfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import Field

from genome_to_diffraction.benchmarks.m6_nextflow import (
    M6BundleManifest,
    M6CaseTask,
    _load_catalogue_bundle,
    _write_eligible_inputs,
)
from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.hpc.models import (
    MAX_REVIEW_ARTIFACT_ARCHIVE_BYTES,
    MAX_REVIEW_ARTIFACT_FILE_BYTES,
    MAX_REVIEW_ARTIFACT_TOTAL_BYTES,
    ValidationError,
)
from genome_to_diffraction.ids import canonical_json_text, content_id
from genome_to_diffraction.schemas.base import ContractModel, Sha256Hex
from genome_to_diffraction.schemas.io import load_json_document
from genome_to_diffraction.schemas.results import (
    EligibilityStatus,
    SequenceGroupRecord,
    StructuralSearchHit,
)
from genome_to_diffraction.structure_search.pdb_coordinates import (
    PdbCoordinateRegistrationRequest,
    _read_jsonl,
    _select_hits,
    _validate_hit,
)

CASES = ("M6C001", "M6C025")
TRACE = "artifacts/m6-nextflow-results/pipeline_info/trace.tsv"
RUNNER = "artifacts/m6-runner-inputs/runner_manifest.json"
COLLECTION = "coordinate_request_collection.json"
CORE_FILES = frozenset(
    {
        "manifest.json",
        "state/phase",
        "state/failure-class",
        "state/job-id",
        "state/job-result.json",
        "state/controller-kind",
        "state/m6-execution-purpose",
        "state/m6-track",
        "state/m6-runner-manifest-sha256",
        RUNNER,
        TRACE,
    }
)
CATALOGUE_FILES = (
    "bundle_manifest.json",
    "catalogue_task.json",
    "catalogue/sequence_groups.jsonl",
    "catalogue/source_records.jsonl",
    "catalogue/catalogue_import_manifest.json",
)
POLICY_FILES = (
    "bundle_manifest.json",
    "case_task.json",
    "policy/accepted_structural_hits.jsonl",
)


class _FileRecord(ContractModel):
    sha256: Sha256Hex
    size_bytes: int = Field(ge=0, le=MAX_REVIEW_ARTIFACT_FILE_BYTES)


class _Collection(ContractModel):
    schema_version: Literal["1.0"]
    adapter_version: Literal["m6-coordinate-request-collection-v1"]
    run_id: str
    remote_run_root: str
    files: dict[str, _FileRecord]


def extract_request_archive(archive: Path, destination: Path) -> _Collection:
    """Extract only regular, canonical, non-duplicate files to new staging."""

    if archive.stat().st_size > MAX_REVIEW_ARTIFACT_ARCHIVE_BYTES:
        raise ValidationError("coordinate request archive exceeds the byte limit")
    destination.mkdir(exist_ok=False)
    names: set[str] = set()
    total = 0
    with tarfile.open(archive, mode="r|gz") as handle:
        for member in handle:
            relative = PurePosixPath(member.name)
            total += member.size
            if (
                not member.isfile()
                or relative.is_absolute()
                or ".." in relative.parts
                or relative.as_posix() != member.name
                or member.name in names
                or len(names) >= 64
                or member.size < 0
                or member.size > MAX_REVIEW_ARTIFACT_FILE_BYTES
                or total > MAX_REVIEW_ARTIFACT_TOTAL_BYTES
            ):
                raise ValidationError("unsafe or oversized coordinate request member")
            names.add(member.name)
            source = handle.extractfile(member)
            if source is None:
                raise ValidationError("unreadable coordinate request member")
            target = destination.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as output:
                while data := source.read(1024 * 1024):
                    output.write(data)
    collection = _Collection.model_validate(
        load_json_document(destination / COLLECTION)
    )
    if names != set(collection.files) | {COLLECTION}:
        raise ValidationError("coordinate request archive inventory is incomplete")
    for name, expected in collection.files.items():
        path = destination / name
        if (
            path.stat().st_size != expected.size_bytes
            or sha256_file(path) != expected.sha256
        ):
            raise ValidationError("coordinate request archive checksum changed")
    return collection


def _object(path: Path) -> dict[str, object]:
    value = load_json_document(path)
    if not isinstance(value, dict):
        raise ValidationError("coordinate producer JSON must be an object")
    return value


def _task(
    rows: list[dict[str, str]],
    remote_root: PurePosixPath,
    process: str,
    tag: str,
    status: str,
) -> str:
    selected = [
        row
        for row in rows
        if row["process"] == f"M6_VALIDATION_WORKFLOW:{process}" and row["tag"] == tag
    ]
    if len(selected) != 1:
        raise ValidationError("coordinate producer trace identity is ambiguous")
    row = selected[0]
    relative = PurePosixPath(row["workdir"]).relative_to(remote_root).as_posix()
    if (
        re.fullmatch(
            r"cache/m6-nextflow-operational/work/[0-9a-f]{2}/[0-9a-f]{30}", relative
        )
        is None
        or row["hash"]
        != "/".join((relative.split("/")[-2], relative.split("/")[-1][:6]))
        or row["status"] != status
        or row["attempt"] != "1"
        or row["exit"] != ("0" if status == "COMPLETED" else "1")
    ):
        raise ValidationError("coordinate producer trace path or outcome changed")
    return relative


def _check_command(path: Path, expected: dict[str, str]) -> Path:
    """Check the recorded argv without executing or trusting it as a path source."""

    words = shlex.split(path.read_text(encoding="utf-8"), comments=True)
    prefix = [
        "genome-to-diffraction",
        "--no-progress",
        "--log-format",
        "json",
        "benchmark",
        "stage-m6-coordinates",
    ]
    arguments = words[len(prefix) :]
    if words[: len(prefix)] != prefix or len(arguments) != 10:
        raise ValidationError("recorded coordinate command is not the fixed adapter")
    options = dict(zip(arguments[::2], arguments[1::2], strict=True))
    if len(options) != 5 or any(
        options.get(key) != value for key, value in expected.items()
    ):
        raise ValidationError("recorded coordinate command producer join changed")
    if set(options) != set(expected) | {"--database-manifest"}:
        raise ValidationError("recorded coordinate command options changed")
    if not PurePosixPath(options["--database-manifest"]).is_absolute():
        raise ValidationError("recorded coordinate database path is not absolute")
    return Path(options["--database-manifest"])


def _derive_requests(
    catalogue: Path,
    policy: Path,
    output: Path,
    database: Path,
) -> tuple[dict[str, object], set[str]]:
    """Use the original eligible-input and registration selectors, without I/O to DB."""

    output.mkdir(parents=True)
    groups_path, _, hits_path = _write_eligible_inputs(catalogue, policy, output)
    groups = _read_jsonl(
        groups_path,
        SequenceGroupRecord,
        label="eligible groups",
        identifier=lambda item: item.sequence_group_id,
        progress=False,
        allow_empty=True,
    )
    hits = _read_jsonl(
        hits_path,
        StructuralSearchHit,
        label="eligible hits",
        identifier=lambda item: item.hit_id,
        progress=False,
        allow_empty=True,
    )
    group_index = {group.sequence_group_id: group for group in groups}
    selected_hits = tuple(
        hit for hit in hits if hit.eligibility_status is EligibilityStatus.SELECTED
    )
    for hit in selected_hits:
        _validate_hit(hit, group_index)
    mapping_bound = sum(
        min(3, count)
        for count in Counter(hit.sequence_group_id for hit in hits).values()
    )
    selected = (
        _select_hits(
            selected_hits,
            PdbCoordinateRegistrationRequest(
                structural_hits_jsonl=hits_path,
                sequence_groups_jsonl=groups_path,
                database_manifest=database,
                output_directory=output,
                maximum_hits_per_sequence_group=3,
                maximum_mappings=mapping_bound,
                allow_network_acquisition=False,
                progress=False,
            ),
        )
        if hits
        else ()
    )
    expected_count = sum(
        min(3, count)
        for count in Counter(hit.sequence_group_id for hit in selected_hits).values()
    )
    if len(selected) != expected_count:
        raise ValidationError("coordinate request selection lost eligible mappings")
    selected_path = output / "selected_structural_hits.jsonl"
    atomic_write_text(
        selected_path, "".join(f"{canonical_json_text(hit)}\n" for hit in selected)
    )
    entries = {str(hit.pdb_id).upper() for hit in selected}
    return {
        "eligible_group_count": len(groups),
        "accepted_hit_count": len(hits),
        "registration_mapping_bound": mapping_bound,
        "requested_mapping_count": len(selected),
        "pdb_ids": sorted(entries),
        "selected_hits_sha256": sha256_file(selected_path),
    }, entries


def freeze_request_inventory(
    root: Path,
    *,
    collection: _Collection,
    prior: Path,
    remote_root: PurePosixPath,
    run_id: str,
    source_commit: str,
) -> dict[str, object]:
    """Validate the complete producer joins and derive canonical offline requests."""

    if collection.run_id != run_id or collection.remote_run_root != str(remote_root):
        raise ValidationError("coordinate collection belongs to another owned run")
    for name in ("manifest.json", "state/job-result.json", TRACE, RUNNER):
        old = prior / name
        if old.is_symlink() or old.resolve(strict=True) != prior.resolve() / name:
            raise ValidationError("prior terminal evidence is not link-free")
        if old.read_bytes() != (root / name).read_bytes():
            raise ValidationError(
                "coordinate collection differs from prior terminal evidence"
            )
    manifest = _object(root / "manifest.json")
    if manifest.get("commit") != source_commit:
        raise ValidationError("coordinate producer source commit changed")
    if (
        root / "state/m6-execution-purpose"
    ).read_text().strip() != "native_control" or (
        root / "state/m6-track"
    ).read_text().strip() != "operational":
        raise ValidationError(
            "coordinate collection is not the native operational control"
        )
    rows = list(csv.DictReader(io.StringIO((root / TRACE).read_text()), delimiter="\t"))
    process_counts = Counter(row["process"] for row in rows)
    for process, count in (
        ("M6_PLAN_TRACK", 1),
        ("M6_IMPORT_CATALOGUE", 2),
        ("M6_PARTITION_DISCOVERY", 2),
        ("M6_APPLY_POLICY", 2),
        ("M6_STAGE_COORDINATES", 2),
    ):
        if process_counts[f"M6_VALIDATION_WORKFLOW:{process}"] != count:
            raise ValidationError("coordinate producer trace inventory is incomplete")
    expected = set(CORE_FILES)
    plan = (
        _task(rows, remote_root, "M6_PLAN_TRACK", "m6-plan:operational", "COMPLETED")
        + "/m6_track_plan"
    )
    expected.update(
        f"{plan}/{name}"
        for name in ("track_plan.json", "case_tasks.tsv", "catalogue_tasks.tsv")
    )
    plan_record = _object(root / plan / "track_plan.json")
    if plan_record.get("benchmark_acceptance_claim") is not False or any(
        plan_record.get(key) != value
        for key, value in {
            "schema_version": "1.0",
            "adapter_version": "m6-native-control-plan-v1",
            "execution_purpose": "native_control",
            "track": "operational",
            "benchmark_acceptance_claim": False,
            "case_ids": list(CASES),
            "case_task_count": 2,
            "catalogue_task_count": 2,
            "input_sha256": {
                "runner_manifest": sha256_file(root / RUNNER),
                "database_manifest": manifest["database_manifest_sha256"],
                "software_lock": manifest["pixi_lock_sha256"],
            },
            "outputs": {
                "catalogue_tasks": sha256_file(root / plan / "catalogue_tasks.tsv"),
                "case_tasks": sha256_file(root / plan / "case_tasks.tsv"),
            },
        }.items()
    ):
        raise ValidationError(
            "coordinate request plan is not the frozen native control"
        )
    if (root / "state/m6-runner-manifest-sha256").read_text().strip() != sha256_file(
        root / RUNNER
    ):
        raise ValidationError("coordinate request runner binding changed")
    case_reports = {}
    all_entries: set[str] = set()
    case_table = []
    catalogue_table = []
    for case_id in CASES:
        case_relative = f"{plan}/case_tasks/{case_id}/task.json"
        expected.add(case_relative)
        case = M6CaseTask.model_validate_json((root / case_relative).read_bytes())
        if (
            case.case_id != case_id
            or case.track != "operational"
            or case.fault_control_sha256 is not None
        ):
            raise ValidationError("coordinate case identity or fault policy changed")
        key = case.catalogue_key
        catalogue = (
            _task(
                rows,
                remote_root,
                "M6_IMPORT_CATALOGUE",
                f"m6-import:{key}",
                "COMPLETED",
            )
            + "/m6_catalogue_bundle"
        )
        policy = (
            _task(
                rows,
                remote_root,
                "M6_APPLY_POLICY",
                f"m6-policy:{case_id}",
                "COMPLETED",
            )
            + "/m6_policy_bundle"
        )
        partition = (
            _task(
                rows,
                remote_root,
                "M6_PARTITION_DISCOVERY",
                f"m6-partition:{key}",
                "COMPLETED",
            )
            + "/m6_discovery_partition"
        )
        failed = _task(
            rows,
            remote_root,
            "M6_STAGE_COORDINATES",
            f"m6-coordinate-stage:{case_id}",
            "FAILED",
        )
        expected.update(f"{catalogue}/{name}" for name in CATALOGUE_FILES)
        expected.update(f"{policy}/{name}" for name in POLICY_FILES)
        expected.update(
            f"{partition}/{provider}/bundle_manifest.json"
            for provider in ("pdb_bundle", "foldseek_bundle")
        )
        expected.add(f"{failed}/.command.sh")
        database = _check_command(
            root / failed / ".command.sh",
            {
                "--task": str(remote_root / plan / "case_tasks" / case_id),
                "--catalogue-bundle": str(remote_root / catalogue),
                "--policy-bundle": str(remote_root / policy),
                "--outdir": "m6_coordinate_stage",
            },
        )
        catalogue_root, catalogue_task = _load_catalogue_bundle(root / catalogue)
        cat_manifest = M6BundleManifest.model_validate_json(
            (catalogue_root / "bundle_manifest.json").read_bytes()
        )
        policy_manifest = M6BundleManifest.model_validate_json(
            (root / policy / "bundle_manifest.json").read_bytes()
        )
        if (
            catalogue_task.catalogue_key != key
            or catalogue_task.analysis_config_sha256 != case.analysis_config_sha256
            or catalogue_task.software_lock_sha256 != manifest["pixi_lock_sha256"]
            or cat_manifest.task_kind != "catalogue_import"
            or cat_manifest.adapter_version != "m6-nextflow-catalogue-v1"
            or cat_manifest.input_sha256.get("task")
            != sha256_file(catalogue_root / "catalogue_task.json")
            or cat_manifest.input_sha256.get("software_lock")
            != manifest["pixi_lock_sha256"]
            or policy_manifest.task_id != case_id
            or policy_manifest.input_sha256.get("case_task")
            != sha256_file(root / case_relative)
            or (root / policy / "case_task.json").read_bytes()
            != (root / case_relative).read_bytes()
            or policy_manifest.input_sha256.get("catalogue_bundle")
            != sha256_file(catalogue_root / "bundle_manifest.json")
            or policy_manifest.input_sha256.get("database_manifest")
            != manifest["database_manifest_sha256"]
        ):
            raise ValidationError("coordinate catalogue/policy/source join changed")
        for provider in ("pdb_bundle", "foldseek_bundle"):
            path = root / partition / provider / "bundle_manifest.json"
            producer = M6BundleManifest.model_validate_json(path.read_bytes())
            if (
                policy_manifest.input_sha256.get(provider) != sha256_file(path)
                or producer.task_id != key
                or producer.task_kind != provider
                or producer.adapter_version != "m6-nextflow-discovery-partition-v1"
                or producer.input_sha256.get("catalogue_bundle")
                != sha256_file(catalogue_root / "bundle_manifest.json")
            ):
                raise ValidationError("coordinate search producer join changed")
        case_table.append(
            {
                "case_id": case_id,
                "catalogue_key": key,
                "task_directory": f"case_tasks/{case_id}",
            }
        )
        catalogue_table.append(
            {
                "catalogue_key": key,
                "import_cache_key": catalogue_task.import_cache_key,
                "task_directory": f"catalogue_tasks/{key}",
            }
        )
        report, entries = _derive_requests(
            catalogue_root, root / policy, root / "requests" / case_id, database
        )
        all_entries.update(entries)
        case_reports[case_id] = {"catalogue_key": key, **report}
    for name, expected_rows in (
        ("case_tasks", case_table),
        (
            "catalogue_tasks",
            sorted(catalogue_table, key=lambda item: item["catalogue_key"]),
        ),
    ):
        with (root / plan / f"{name}.tsv").open() as handle:
            actual_rows = list(csv.DictReader(handle, delimiter="\t"))
        if actual_rows != expected_rows:
            raise ValidationError("coordinate plan table/producer join changed")
    if expected != set(collection.files):
        raise ValidationError(
            "coordinate request collection has missing or unexpected producer files"
        )
    files = {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
    inventory = {
        "schema_version": "1.0",
        "adapter_version": "m6-coordinate-requests-v1",
        "run_id": run_id,
        "producer_commit": source_commit,
        "database_manifest_sha256": manifest["database_manifest_sha256"],
        "cases": case_reports,
        "distinct_pdb_count": len(all_entries),
        "pdb_ids": sorted(all_entries),
        "input_and_request_sha256": files,
        "network_acquisition_performed": False,
        "cache_import_performed": False,
    }
    inventory["inventory_id"] = content_id("m6coords_", inventory)
    atomic_write_json(root / "request_inventory.json", inventory)
    return inventory
