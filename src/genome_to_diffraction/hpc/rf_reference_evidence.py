"""Authenticate actual Phenix invocation/exit pairs for the fixed RF profile.

Inputs are an original JSON-formatted task stderr log and exact command
expectations derived from already authenticated native receipts. The output
preserves argument arrays, original working directories and numeric tool exits;
an exit is never guessed from a typed MR/refinement status. Full task-log bytes
remain separately hash-bound by the reference checkpoint. This reader does not
run tools, schedule science, assign acceptance or read truth-side labels.

Only the current captured-Phenix logger format is supported. Incomplete,
overlapping, reordered, duplicated or foreign commands fail. Non-tool stderr
is retained in the original log and counted explicitly, not treated as tool
evidence. There is no cache or fallback parser. Python 3.14 is sufficient.

The same fixed-profile boundary checks owned trace/task paths and freezes their
regular outputs plus seven original task logs, within 128 MiB/file and 12 GiB
total limits. Declared catalogue/batch inputs bind their original planned tasks;
indexed partition inputs map to the complete unique original search producer
union. Both mappings remain unchanged on resume and collection; generated output
symlinks remain invalid. The read-only module CLI accepts only --run-root and
lists the unchanged native/published/input-copy paths authorised by terminal first/
resume records. Failed runs without first verification yield no dynamic assets;
the dispatcher separately retains fixed diagnostics. Missing, foreign, changed,
unbounded or incompletely resumed evidence fails, rather than acquiring an
acceptance claim. Unit and dispatcher tests cover numeric command exits, path
substitution, payload mutation, exact inventories and diagnostic-only failures.
"""

import argparse
import csv
import os
import re
import stat
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.execution_evidence import validate_login_result_binding
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.schemas.io import load_json_document, parse_json_document

_START = "executing captured Phenix command"
_FINISH = "captured Phenix command finished"
_MAX_FILE_BYTES = 128 * 1024 * 1024
_MAX_TOTAL_BYTES = 12 * 1024 * 1024 * 1024
_TASK_LOGS = frozenset(
    {
        ".command.sh",
        ".command.run",
        ".command.out",
        ".command.err",
        ".command.log",
        ".command.trace",
        ".exitcode",
    }
)
REFERENCE_INPUT_COPIES = {
    "runner_manifest": "runner_manifest.json",
    "database_manifest": "database_manifest.json",
    "phenix_manifest": "phenix_manifest.json",
    "software_lock": "pixi.lock",
    "execution_policy": "execution_policy.yaml",
    "protocol": "protocol.yaml",
    "controller_identity": "controller.json",
    "run_manifest": "run_manifest.json",
    "phenix_verification_log": "phenix_verification.log",
}


def _owned_path(root: Path, path: Path, *, directory: bool) -> Path:
    if not root.is_absolute() or not path.is_absolute() or ".." in path.parts:
        raise ValueError("reference native path is not absolute and traversal-free")
    # Raven's reviewed /ptmp mount alias may already have been canonicalised by
    # a scientific adapter. Accept the same owned run, never a different root.
    anchor = root if path.is_relative_to(root) else root.resolve(strict=True)
    relative = path.relative_to(anchor)
    current = anchor
    for part in ("", *relative.parts):
        if part:
            current /= part
        details = current.lstat()
        if stat.S_ISLNK(details.st_mode) or details.st_uid != os.getuid():
            raise ValueError("reference native path has a substituted or foreign owner")
        want_directory = current != path or directory
        if not (stat.S_ISDIR if want_directory else stat.S_ISREG)(details.st_mode):
            raise ValueError("reference native path has an invalid file type")
    if not path.resolve(strict=True).is_relative_to(root.resolve(strict=True)):
        raise ValueError("reference native path escapes its owned run")
    return path


def reference_owned_regular_file(root: Path, path: Path) -> Path:
    """Bound a regular file before reading it; permit only the site's outer alias."""

    _owned_path(root, path, directory=False)
    if path.stat().st_size > _MAX_FILE_BYTES:
        raise ValueError("reference native file exceeds the collection per-file limit")
    return path


def reference_trace_tasks(run_root: Path, trace: Path) -> tuple[dict[str, str], ...]:
    """Read exact native task identities only after validating every task directory.

    Workflow completeness and scientific results are checked separately. This
    boundary requires actual numeric executor IDs, successful task exits and
    original first/resume statuses; it never equates those with a tool hit.
    """

    reference_owned_regular_file(run_root, trace)
    if trace not in {
        run_root
        / "artifacts/qualification"
        / f"rf-reference-{phase}-pipeline-info"
        / "trace.tsv"
        for phase in ("first", "resume")
    }:
        raise ValueError("reference native trace is not a fixed first/resume snapshot")
    before = sha256_file(trace)
    required = {
        "task_id",
        "hash",
        "native_id",
        "process",
        "tag",
        "status",
        "exit",
        "workdir",
    }
    rows: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    seen_directories: set[Path] = set()
    with trace.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fields = reader.fieldnames
        if (
            fields is None
            or len(fields) != len(set(fields))
            or not required.issubset(fields)
        ):
            raise ValueError("reference native trace fields are missing or duplicated")
        for raw in reader:
            if None in raw or any(type(value) is not str for value in raw.values()):
                raise ValueError("reference native trace contains a malformed row")
            row = dict(raw)
            work = Path(row["workdir"])
            cache = run_root / "cache/rf-reference/work"
            _owned_path(run_root, work, directory=True)
            relative = work.relative_to(cache).as_posix()
            if (
                re.fullmatch(r"[0-9a-f]{2}/[0-9a-f]{30}", relative) is None
                or re.fullmatch(r"[0-9a-f]{2}/[0-9a-f]{6,30}", row["hash"]) is None
                or not relative.startswith(row["hash"])
                or not re.fullmatch(r"[1-9][0-9]*", row["task_id"])
                or not re.fullmatch(r"[1-9][0-9]*", row["native_id"])
                or row["task_id"] in seen_ids
                or work in seen_directories
                or not row["process"].startswith("RF_REFERENCE_WORKFLOW:")
                or row["status"] not in {"COMPLETED", "CACHED"}
                or row["exit"] != "0"
            ):
                raise ValueError(
                    "reference native task identity or completion is invalid"
                )
            seen_ids.add(row["task_id"])
            seen_directories.add(work)
            rows.append(row)
    if not rows or sha256_file(trace) != before:
        raise ValueError("reference native trace is empty or changed during reading")
    return tuple(rows)


def _staged_link_target(path: Path) -> Path:
    details = path.lstat()
    if not stat.S_ISLNK(details.st_mode) or details.st_uid != os.getuid():
        raise ValueError("reference declared input is not an owned staging link")
    return path.resolve(strict=True)


def _staged_file_inputs(
    run_root: Path, tasks: tuple[dict[str, str], ...]
) -> dict[str, str]:
    """Bind the three current tuple-path input layouts to original plan outputs."""

    bindings = {}
    for (
        process,
        directory,
        filenames,
        producer,
        producer_output,
        task_directory,
        tag,
    ) in (
        (
            "M6_IMPORT_CATALOGUE",
            "catalogue_task",
            ("analysis_config.json", "catalogue.faa", "task.json"),
            "RF_PLAN",
            "reference_plan/bundle",
            "catalogue_tasks",
            "m6-import:",
        ),
        (
            "M6_SEARCH_PDB",
            "batch_task",
            ("sequence_groups.jsonl", "task.json"),
            "M6_BUILD_SEARCH_BATCHES",
            "m6_batch_plan",
            "pdb_sequence_batches",
            "m6-pdb:",
        ),
        (
            "M6_SEARCH_FOLDSEEK",
            "batch_task",
            ("sequence_groups.jsonl", "task.json"),
            "M6_BUILD_SEARCH_BATCHES",
            "m6_batch_plan",
            "prostt5_foldseek_batches",
            "m6-foldseek:",
        ),
    ):
        consumers = tuple(
            row for row in tasks if row["process"] == f"RF_REFERENCE_WORKFLOW:{process}"
        )
        if not consumers:
            continue
        originals = tuple(
            row
            for row in tasks
            if row["process"] == f"RF_REFERENCE_WORKFLOW:{producer}"
        )
        if len(originals) != 1:
            raise ValueError(
                "reference declared inputs lack their unique original planner"
            )
        source = _owned_path(
            run_root, Path(originals[0]["workdir"]) / producer_output, directory=True
        ).resolve(strict=True)
        for task in consumers:
            parent = _owned_path(
                run_root, Path(task["workdir"]) / directory, directory=True
            )
            if {path.name for path in parent.iterdir()} != set(filenames):
                raise ValueError("reference declared input file inventory differs")
            if not task["tag"].startswith(tag) or not task["tag"][len(tag) :]:
                raise ValueError("reference declared input task tag differs")
            task_id = task["tag"][len(tag) :]
            original_parents = set()
            for filename in filenames:
                link = parent / filename
                target = _staged_link_target(link)
                reference_owned_regular_file(run_root, target)
                if target.name != filename or not target.is_relative_to(source):
                    raise ValueError(
                        "reference declared input belongs to another producer"
                    )
                relative = target.parent.relative_to(source).parts
                valid = relative == (task_directory, task_id)
                if process == "M6_IMPORT_CATALOGUE":
                    valid = (
                        len(relative) == 4
                        and relative[0] == "production_plans"
                        and relative[2:] == (task_directory, task_id)
                    )
                if not valid:
                    raise ValueError(
                        "reference declared input belongs to another planned task"
                    )
                original_parents.add(target.parent)
                bindings[link.relative_to(run_root).as_posix()] = target.relative_to(
                    run_root.resolve(strict=True)
                ).as_posix()
            if len(original_parents) != 1:
                raise ValueError(
                    "reference declared inputs mix original task directories"
                )
    return bindings


def reference_staged_search_inputs(
    run_root: Path, tasks: tuple[dict[str, str], ...]
) -> dict[str, str]:
    """Bind declared catalogue, batch and indexed partition inputs to producers.

    Only the current tuple-path and indexed input layouts are excluded from
    generated output traversal. Every indexed parent is owned and contains exactly
    one correctly named link, and resolves to a distinct original traced producer
    output. The returned input-to-producer map must remain identical on resume.
    This authenticates filesystem inputs, not native execution or science.
    """

    partitions = tuple(
        _owned_path(run_root, Path(task["workdir"]), directory=True)
        for task in tasks
        if task["process"] == "RF_REFERENCE_WORKFLOW:M6_PARTITION_DISCOVERY"
    )
    bindings = _staged_file_inputs(run_root, tasks)
    if not partitions:
        return dict(sorted(bindings.items()))
    for provider, process, basename in (
        ("pdb", "M6_SEARCH_PDB", "m6_pdb_bundle"),
        ("foldseek", "M6_SEARCH_FOLDSEEK", "m6_foldseek_bundle"),
    ):
        producers = tuple(
            _owned_path(run_root, Path(task["workdir"]) / basename, directory=True)
            for task in tasks
            if task["process"] == f"RF_REFERENCE_WORKFLOW:{process}"
        )
        targets = {
            path.resolve(strict=True): path.relative_to(run_root).as_posix()
            for path in producers
        }
        if not targets or len(targets) != len(producers):
            raise ValueError(
                "reference staged search producer union is absent or repeated"
            )
        prefix = f"{provider}-batch"
        expected_names = {
            f"{prefix}{index:02d}" for index in range(1, len(producers) + 1)
        }
        for work in partitions:
            parents = tuple(
                path for path in work.iterdir() if path.name.startswith(prefix)
            )
            if {path.name for path in parents} != expected_names:
                raise ValueError(
                    "reference indexed search input parents are incomplete or foreign"
                )
            seen = set()
            for parent in sorted(parents):
                _owned_path(run_root, parent, directory=True)
                link = parent / basename
                if tuple(parent.iterdir()) != (link,):
                    raise ValueError(
                        "reference indexed search input directory has foreign contents"
                    )
                target = _staged_link_target(link)
                if target not in targets or target in seen:
                    raise ValueError(
                        "reference indexed search input has a foreign "
                        "or repeated producer"
                    )
                seen.add(target)
                bindings[link.relative_to(run_root).as_posix()] = targets[target]
            if seen != set(targets):
                raise ValueError(
                    "reference indexed search inputs omit original producers"
                )
    return dict(sorted(bindings.items()))


def reference_native_file_inventory(
    run_root: Path, tasks: tuple[dict[str, str], ...]
) -> dict[str, dict[str, str | int]]:
    """Freeze trace-owned generated files and seven logs within collection limits.

    Top-level input-stage links and authenticated indexed partition inputs are
    excluded; their original producer bytes remain inventoried at the producer.
    Generated descendants must be regular, owned and symlink-free. All sizes are
    checked before hashing any payload. The caller authenticates these exact
    tasks and original scientific input receipts.
    """

    staged_parents = {
        (run_root / relative).parent
        for relative in reference_staged_search_inputs(run_root, tasks)
    }
    candidates: dict[str, tuple[Path, int]] = {}
    total = 0
    for task in tasks:
        work = _owned_path(run_root, Path(task["workdir"]), directory=True)
        if not work.is_relative_to(run_root / "cache/rf-reference/work"):
            raise ValueError("reference native task belongs to another cache")
        pending = [work]
        logs: set[str] = set()
        while pending:
            directory = pending.pop()
            for path in sorted(directory.iterdir()):
                details = path.lstat()
                if directory == work:
                    if path.name in _TASK_LOGS:
                        logs.add(path.name)
                    elif (
                        path in staged_parents
                        or path.name.startswith(".")
                        or stat.S_ISLNK(details.st_mode)
                    ):
                        continue
                if stat.S_ISDIR(details.st_mode):
                    pending.append(_owned_path(run_root, path, directory=True))
                    continue
                reference_owned_regular_file(run_root, path)
                relative = path.relative_to(run_root).as_posix()
                if relative in candidates:
                    raise ValueError("reference native inventory repeats a task file")
                candidates[relative] = (path, details.st_size)
                total += details.st_size
                if total > _MAX_TOTAL_BYTES:
                    raise ValueError(
                        "reference native inventory exceeds the total limit"
                    )
        if logs != _TASK_LOGS:
            raise ValueError("reference native inventory lacks original task logs")
    if not candidates:
        raise ValueError("reference native inventory is empty")
    result = {}
    for relative, (path, size) in sorted(candidates.items()):
        digest = sha256_file(reference_owned_regular_file(run_root, path))
        if path.stat().st_size != size:
            raise ValueError("reference native payload size changed while hashing")
        result[relative] = {"sha256": digest, "size_bytes": size}
    return result


@dataclass(frozen=True)
class ReferenceNativeCommand:
    """One exact command from an authenticated original native command record."""

    arguments: tuple[str, ...]
    working_directory: Path


@dataclass(frozen=True)
class ReferenceNativeInvocation:
    """An actual paired invocation and numeric exit, not scientific success."""

    command: ReferenceNativeCommand
    exit_status: int
    start_line: int
    finish_line: int


@dataclass(frozen=True)
class ReferenceNativeTaskLog:
    """Complete-log digest plus extracted native execution evidence."""

    log_sha256: str
    invocations: tuple[ReferenceNativeInvocation, ...]
    other_stderr_lines: int


def command_record_expectations(
    path: Path, *, work_directory: Path
) -> tuple[ReferenceNativeCommand, ...]:
    """Read only current Phaser/T12 command records after scientific validation."""

    reference_owned_regular_file(work_directory, path)
    root = work_directory.resolve(strict=True)
    original = path.resolve(strict=True)
    if not original.is_relative_to(root):
        raise ValueError("reference native command record escapes its task")
    raw = load_json_document(original)
    if not isinstance(raw, Mapping):
        raise ValueError("reference native command record is not an object")
    if path.name == "phaser_command.json":
        values = (raw.get("arguments"),)
    elif path.name == "t12_command.json":
        values = (raw.get("refine_arguments"),)
        if raw.get("sequence_arguments") is not None:
            values += (raw["sequence_arguments"],)
    else:
        raise ValueError("reference native command record has an unreviewed name")
    commands = []
    for arguments in values:
        if (
            not isinstance(arguments, list)
            or not arguments
            or any(type(value) is not str or not value for value in arguments)
            or arguments[0]
            not in {"phenix.phaser", "phenix.refine", "phenix.sequence_from_map"}
        ):
            raise ValueError("reference native command arguments are invalid")
        commands.append(ReferenceNativeCommand(tuple(arguments), original.parent))
    return tuple(commands)


def read_reference_native_task_log(
    path: Path,
    *,
    work_directory: Path,
    expected: tuple[ReferenceNativeCommand, ...],
) -> ReferenceNativeTaskLog:
    """Require exact ordered native command/exit pairs from original task stderr."""

    if path.name != ".command.err":
        raise ValueError("reference native stderr is absent or substituted")
    reference_owned_regular_file(work_directory, path)
    work = work_directory.resolve(strict=True)
    if path.resolve(strict=True).parent != work:
        raise ValueError("reference native stderr belongs to another task")
    before = sha256_file(path)
    invocations = []
    active: tuple[ReferenceNativeCommand, int] | None = None
    other_lines = 0
    for number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.startswith("{"):
            other_lines += 1
            continue
        raw = parse_json_document(line, label=f"{path}:{number}")
        if not isinstance(raw, dict):
            raise ValueError("reference JSON task log is not an object")
        if raw.get("logger") != "genome_to_diffraction.phenix" or raw.get(
            "message"
        ) not in {_START, _FINISH}:
            other_lines += 1
            continue
        if raw["message"] == _START:
            arguments = raw.get("arguments")
            command = raw.get("command")
            directory = raw.get("working_directory")
            if (
                active is not None
                or not isinstance(arguments, list)
                or any(type(value) is not str for value in arguments)
                or type(command) is not str
                or type(directory) is not str
                or not Path(directory).is_absolute()
                or ".." in Path(directory).parts
                or not Path(directory).resolve(strict=True).is_relative_to(work)
            ):
                raise ValueError("reference native invocation is malformed or overlaps")
            active = (
                ReferenceNativeCommand((command, *arguments), Path(directory)),
                number,
            )
        else:
            if (
                active is None
                or raw.get("command") != active[0].arguments[0]
                or type(raw.get("exit_status")) is not int
            ):
                raise ValueError("reference native numeric exit lacks its invocation")
            invocations.append(
                ReferenceNativeInvocation(
                    active[0], raw["exit_status"], active[1], number
                )
            )
            active = None
    if active is not None or tuple(item.command for item in invocations) != expected:
        raise ValueError("reference native commands are incomplete or differ")
    if sha256_file(path) != before:
        raise ValueError("reference native stderr changed while being authenticated")
    return ReferenceNativeTaskLog(before, tuple(invocations), other_lines)


def _object(root: Path, path: Path) -> dict[str, object]:
    value = load_json_document(reference_owned_regular_file(root, path))
    if not isinstance(value, dict):
        raise ValueError("reference collection record must be a JSON object")
    return value


def _verification_record(run: Path, phase: str) -> dict[str, object]:
    path = run / "artifacts/qualification" / f"rf-reference-{phase}-verification.json"
    record = _object(run, path)
    expected = {
        "schema_version": "1.0",
        "adapter_version": "rf-native-verification-v1",
        "phase": phase,
        "native_acceptance_claim": False,
        "benchmark_acceptance_claim": False,
        "human_approval_granted": False,
        "truth_compared": False,
    }
    if (
        set(record)
        != {
            *expected,
            "first_verification_sha256",
            "invariant",
            "trace_sha256",
            "child_checkpoint_sha256",
            "resource_evidence_sha256",
            "verification_id",
        }
        or any(
            type(record.get(key)) is not type(value) or record[key] != value
            for key, value in expected.items()
        )
        or record["verification_id"]
        != content_id(
            "rfnative_",
            {key: value for key, value in record.items() if key != "verification_id"},
        )
    ):
        raise ValueError(
            "reference collection has an invalid native verification record"
        )
    for key, name in (
        ("trace_sha256", f"rf-reference-{phase}-pipeline-info/trace.tsv"),
        ("child_checkpoint_sha256", f"rf-reference-{phase}-child-outputs.json"),
        ("resource_evidence_sha256", f"rf-reference-{phase}-resource-evidence.json"),
    ):
        original = reference_owned_regular_file(run, path.parent / name)
        if sha256_file(original) != record[key]:
            raise ValueError("reference collection phase evidence changed")
    return record


def reference_collection_files(run: Path) -> tuple[str, ...]:
    """Enumerate only unchanged frozen native assets of an owned terminal RF run.

    Before the first verifier exists, only the dispatcher's fixed diagnostic
    logs/raw trace may be collected. A successful terminal run must have both
    phase verifications. This is bounded byte transport, never reinterpreted as
    scientific acceptance or a truth comparison. No payload is modified.
    """

    manifest = _object(run, run / "manifest.json")
    if manifest.get("profile") != "rf-reference" or manifest.get("run_id") != run.name:
        raise ValueError("reference collection belongs to another run/profile")
    qualification = run / "artifacts/qualification"
    first_path = qualification / "rf-reference-first-verification.json"
    terminal_path = run / "state/controller-result.json"
    if not terminal_path.exists() and not terminal_path.is_symlink():
        phase = (
            reference_owned_regular_file(run, run / "state/phase").read_text().strip()
        )
        if phase != "stage_failed" or first_path.exists() or first_path.is_symlink():
            raise ValueError(
                "reference collection requires terminal controller evidence"
            )
        return ()
    terminal = _object(run, terminal_path)
    identity = _object(run, run / "state/controller.json")
    owner = (
        reference_owned_regular_file(run, run / "state/owner-id").read_text().strip()
    )
    commit = reference_owned_regular_file(run, run / "state/commit").read_text().strip()
    if (
        manifest.get("commit") != commit
        or manifest.get("site_id") != "raven"
        or manifest.get("controller_kind") != "login_process"
        or manifest.get("source_snapshot_status") != "immutable"
    ):
        raise ValueError("reference collection immutable source/site binding differs")
    validate_login_result_binding(
        identity,
        terminal,
        run_id=run.name,
        owner_id=owner,
        profile="rf-reference",
        source_commit=commit,
    )
    state, exit_code = terminal.get("controller_state"), terminal.get("exit_code")
    if (
        state not in {"COMPLETED", "FAILED", "CANCELLED"}
        or type(exit_code) is not int
        or exit_code < 0
        or (state == "COMPLETED") != (exit_code == 0)
        or (state == "COMPLETED") != (terminal.get("failure_class") == "success")
    ):
        raise ValueError("reference collection has inconsistent terminal status")
    if not first_path.exists() and not first_path.is_symlink():
        if state == "COMPLETED":
            raise ValueError("successful reference collection lacks first verification")
        return ()
    first = _verification_record(run, "first")
    invariant = first["invariant"]
    if not isinstance(invariant, dict) or (
        invariant.get("run_id") != run.name
        or invariant.get("profile") != "rf-reference"
        or invariant.get("reference_scope") != "rf-fixed-five-v1"
        or invariant.get("source_commit") != commit
        or invariant.get("controller_identity") != identity
        or first["first_verification_sha256"] is not None
    ):
        raise ValueError("reference collection has foreign frozen native evidence")
    resume_path = qualification / "rf-reference-resume-verification.json"
    if resume_path.exists() or resume_path.is_symlink():
        resume = _verification_record(run, "resume")
        if (
            resume["first_verification_sha256"] != sha256_file(first_path)
            or resume["invariant"] != invariant
        ):
            raise ValueError(
                "reference collection resume differs from its frozen first pass"
            )
    elif state == "COMPLETED":
        raise ValueError(
            "successful reference collection lacks cached resume verification"
        )
    first_trace = qualification / "rf-reference-first-pipeline-info/trace.tsv"
    tasks = reference_trace_tasks(run, first_trace)
    if reference_staged_search_inputs(run, tasks) != invariant.get(
        "staged_search_inputs"
    ):
        raise ValueError("reference collection indexed search inputs changed")
    if reference_native_file_inventory(run, tasks) != invariant.get("native_files"):
        raise ValueError("reference collection native task bytes changed")
    result_root = run / "artifacts/rf-reference-results/reference_run/bundle"
    result_path = result_root / "reference_run.json"
    result = _object(run, result_path)
    result_outputs = result.get("output_sha256")
    if not isinstance(result_outputs, dict) or sha256_file(
        result_path
    ) != invariant.get("reference_result_sha256"):
        raise ValueError("reference collection result binding changed")
    input_digests = invariant.get("input_sha256")
    if not isinstance(input_digests, dict) or set(input_digests) != set(
        REFERENCE_INPUT_COPIES
    ):
        raise ValueError("reference collection original input bindings are incomplete")
    prefixes = {
        "native_files": Path("cache/rf-reference/work"),
        "published_files": result_root.relative_to(run),
        "input_copies": Path("artifacts/qualification/rf-reference-inputs"),
    }
    names: set[str] = set()
    total = 0
    for role, prefix in prefixes.items():
        files = invariant.get(role)
        if not isinstance(files, dict) or not files:
            raise ValueError(
                "reference collection lacks its full frozen file inventory"
            )
        if role == "input_copies" and set(files) != {
            (prefix / name).as_posix() for name in REFERENCE_INPUT_COPIES.values()
        }:
            raise ValueError("reference collection input-copy inventory differs")
        if role == "published_files" and set(files) != {
            (prefix / name).as_posix()
            for name in ("reference_run.json", *result_outputs)
        }:
            raise ValueError("reference collection published inventory differs")
        for relative, binding in files.items():
            if (
                not isinstance(relative, str)
                or not relative
                or any(ord(char) < 32 or ord(char) > 126 for char in relative)
                or not Path(relative).is_relative_to(prefix)
                or relative in names
                or not isinstance(binding, dict)
                or set(binding) != {"sha256", "size_bytes"}
                or type(binding["size_bytes"]) is not int
                or binding["size_bytes"] < 0
            ):
                raise ValueError("reference collection has an invalid frozen file path")
            if role == "input_copies":
                input_role = next(
                    key
                    for key, name in REFERENCE_INPUT_COPIES.items()
                    if name == Path(relative).name
                )
                if binding["sha256"] != input_digests[input_role]:
                    raise ValueError(
                        "reference collection copy changed its original binding"
                    )
            elif role == "published_files":
                published_relative = Path(relative).relative_to(prefix).as_posix()
                expected = (
                    invariant["reference_result_sha256"]
                    if published_relative == "reference_run.json"
                    else result_outputs[published_relative]
                )
                if binding["sha256"] != expected:
                    raise ValueError(
                        "reference collection published checksum binding differs"
                    )
            path = reference_owned_regular_file(run, run / relative)
            size = path.stat().st_size
            total += size
            if (
                total > _MAX_TOTAL_BYTES
                or size != binding["size_bytes"]
                or sha256_file(path) != binding["sha256"]
            ):
                raise ValueError(
                    "reference collection payload changed or exceeds limits"
                )
            names.add(relative)
    return tuple(sorted(names))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List only owned frozen RF collection files"
    )
    parser.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()
    for relative in reference_collection_files(args.run_root):
        print(relative)
    return 0


if __name__ == "__main__":
    sys.exit(main())
