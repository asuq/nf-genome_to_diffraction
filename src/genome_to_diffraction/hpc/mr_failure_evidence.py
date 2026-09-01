"""Build bounded, checksum-authenticated diagnostics for a failed MR screen.

This internal repository tool reads one owned Nextflow log and its run-local
work tree after controller failure. It copies only scoped first-copy task
evidence into a new immutable diagnostic package. The package is never a cache
authority and never promotes a scientific hit or no-hit.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import canonical_json_text, content_id
from genome_to_diffraction.schemas.results import MrHypothesis, NormalisedMrResult
from genome_to_diffraction.time import utc_now_iso

_ADAPTER_VERSION = "failed-first-copy-child-evidence-v1"
_RUN_ID = re.compile(
    r"^gtd-unknown-screen-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}-[0-9a-f]{8}$"
)
_SUBMITTED = re.compile(
    r"\[SLURM\] submitted process .*RUN_PHASE3_FIRST_COPY_PHASER "
    r"\(phase3-first-copy:([^:()]+):(mrhyp_[0-9a-f]{64})\) > "
    r"jobId: ([0-9]+); workDir: ([^\s;]+)"
)
_COMPLETED = re.compile(
    r"Task completed > TaskHandler\[jobId: ([0-9]+); .*"
    r"RUN_PHASE3_FIRST_COPY_PHASER "
    r"\(phase3-first-copy:([^:()]+):(mrhyp_[0-9a-f]{64})\); "
    r"status: COMPLETED; exit: ([^;]+); .*started: ([^;]+); exited: ([^;]+);"
)
_COMMAND_FILES = (
    ".command.sh",
    ".command.run",
    ".command.log",
    ".command.out",
    ".command.err",
    ".command.trace",
    ".exitcode",
)
_MAX_HYPOTHESES = 75
_MAX_ATTEMPTS = 150
_MAX_FILES = 5000
_MAX_FILE_BYTES = 128 * 1024 * 1024
_MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
_SBATCH_CPUS = re.compile(r"^#SBATCH -c ([0-9]+)$", re.MULTILINE)
_SBATCH_TIME = re.compile(r"^#SBATCH -t ([0-9:-]+)$", re.MULTILINE)
_SBATCH_MEMORY = re.compile(r"^#SBATCH --mem ([0-9]+[KMGTP]?)$", re.MULTILINE)


class MrFailureEvidenceError(ValueError):
    """Failed-screen evidence is unsafe, inconsistent, or over its bounds."""


@dataclass(frozen=True, slots=True)
class _Attempt:
    """One scheduler submission observed in the controller log."""

    crystal_id: str
    hypothesis_id: str
    job_id: str
    work_directory: Path
    submission_index: int


@dataclass(frozen=True, slots=True)
class _Completion:
    """One terminal task observation from Nextflow."""

    crystal_id: str
    hypothesis_id: str
    exit_code: str
    started: str
    exited: str


@dataclass(slots=True)
class _PackageState:
    """Mutable bounded package inventory during atomic construction."""

    root: Path
    total_bytes: int = 0
    files: list[dict[str, object]] | None = None
    omissions: list[dict[str, object]] | None = None

    def __post_init__(self) -> None:
        self.files = []
        self.omissions = []


def _safe_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise MrFailureEvidenceError(f"unsafe diagnostic relative path: {value!r}")
    return path


def _inside(path: Path, root: Path, *, label: str) -> Path:
    if path.is_symlink():
        raise MrFailureEvidenceError(f"{label} must not be a symlink")
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as error:
        raise MrFailureEvidenceError(f"{label} escapes its owned root") from error
    return resolved


def _copy_file(
    state: _PackageState,
    source: Path,
    relative: str,
    *,
    role: str,
) -> None:
    destination_relative = _safe_relative(relative)
    if source.is_symlink() or not source.is_file():
        assert state.omissions is not None
        state.omissions.append(
            {
                "relative_path": destination_relative.as_posix(),
                "role": role,
                "reason": "missing_or_unsafe",
            }
        )
        return
    size = source.stat().st_size
    if size > _MAX_FILE_BYTES:
        assert state.omissions is not None
        state.omissions.append(
            {
                "relative_path": destination_relative.as_posix(),
                "role": role,
                "reason": "file_exceeds_bound",
                "size_bytes": size,
            }
        )
        return
    if state.total_bytes + size > _MAX_TOTAL_BYTES:
        raise MrFailureEvidenceError("failed-child evidence exceeds total byte bound")
    assert state.files is not None
    if len(state.files) >= _MAX_FILES:
        raise MrFailureEvidenceError("failed-child evidence exceeds file-count bound")
    destination = state.root.joinpath(*destination_relative.parts)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    if sha256_file(destination, progress=False) != sha256_file(source, progress=False):
        raise MrFailureEvidenceError("copied failed-child evidence checksum differs")
    state.total_bytes += size
    state.files.append(
        {
            "relative_path": destination_relative.as_posix(),
            "role": role,
            "size_bytes": size,
            "sha256": sha256_file(destination, progress=False),
        }
    )


def _parse_log(text: str) -> tuple[tuple[_Attempt, ...], dict[str, _Completion]]:
    attempts: list[_Attempt] = []
    jobs: set[str] = set()
    for index, match in enumerate(_SUBMITTED.finditer(text), start=1):
        crystal_id, hypothesis_id, job_id, work_directory = match.groups()
        if job_id in jobs:
            raise MrFailureEvidenceError(f"duplicate submitted child job ID: {job_id}")
        jobs.add(job_id)
        attempts.append(
            _Attempt(
                crystal_id=crystal_id,
                hypothesis_id=hypothesis_id,
                job_id=job_id,
                work_directory=Path(work_directory),
                submission_index=index,
            )
        )
    if len(attempts) > _MAX_ATTEMPTS:
        raise MrFailureEvidenceError("submitted MR attempts exceed the fixed bound")

    completions: dict[str, _Completion] = {}
    for match in _COMPLETED.finditer(text):
        job_id, crystal_id, hypothesis_id, exit_code, started, exited = match.groups()
        completion = _Completion(
            crystal_id=crystal_id,
            hypothesis_id=hypothesis_id,
            exit_code=exit_code,
            started=started,
            exited=exited,
        )
        previous = completions.setdefault(job_id, completion)
        if previous != completion:
            raise MrFailureEvidenceError(
                f"child job has contradictory completion evidence: {job_id}"
            )
    return tuple(attempts), completions


def _hypotheses(
    work_root: Path,
) -> tuple[dict[str, MrHypothesis], dict[str, Path]]:
    records: dict[str, MrHypothesis] = {}
    raw_lines: dict[str, Path] = {}
    paths = sorted(work_root.glob("*/*/diverse_first_copy_funnel/mr_hypotheses.jsonl"))
    for path in paths:
        resolved = _inside(path, work_root, label="funnel hypothesis inventory")
        for line_number, line in enumerate(
            resolved.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            try:
                hypothesis = MrHypothesis.model_validate_json(line)
            except ValueError as error:
                raise MrFailureEvidenceError(
                    f"invalid funnel hypothesis at line {line_number}"
                ) from error
            if hypothesis.hypothesis_id in records:
                raise MrFailureEvidenceError(
                    f"duplicate funnel hypothesis: {hypothesis.hypothesis_id}"
                )
            records[hypothesis.hypothesis_id] = hypothesis
            raw_lines[hypothesis.hypothesis_id] = resolved
    if len(records) > _MAX_HYPOTHESES:
        raise MrFailureEvidenceError("funnel hypothesis count exceeds 75")
    return records, raw_lines


def _copy_hypothesis_evidence(
    state: _PackageState,
    work_root: Path,
    hypothesis: MrHypothesis,
    source_inventory: Path,
) -> None:
    relative_root = f"hypotheses/{hypothesis.hypothesis_id}"
    atomic_write_text(
        state.root / relative_root / "mr_hypothesis.json",
        f"{canonical_json_text(hypothesis)}\n",
    )
    hypothesis_path = state.root / relative_root / "mr_hypothesis.json"
    hypothesis_size = hypothesis_path.stat().st_size
    if state.total_bytes + hypothesis_size > _MAX_TOTAL_BYTES:
        raise MrFailureEvidenceError("failed-child evidence exceeds total byte bound")
    assert state.files is not None
    if len(state.files) >= _MAX_FILES:
        raise MrFailureEvidenceError("failed-child evidence exceeds file-count bound")
    state.total_bytes += hypothesis_size
    state.files.append(
        {
            "relative_path": f"{relative_root}/mr_hypothesis.json",
            "role": "mr_hypothesis",
            "size_bytes": hypothesis_size,
            "sha256": sha256_file(hypothesis_path, progress=False),
        }
    )
    plan = (
        source_inventory.parent / "resource_plans" / f"{hypothesis.hypothesis_id}.json"
    )
    if plan.exists() or plan.is_symlink():
        _inside(plan, work_root, label="MR resource plan")
        _copy_file(
            state,
            plan,
            f"{relative_root}/mr_resource_plan.json",
            role="mr_resource_plan",
        )


def _copy_attempt_evidence(
    state: _PackageState,
    work_root: Path,
    attempt: _Attempt,
    attempt_number: int,
) -> None:
    work = _inside(attempt.work_directory, work_root, label="MR task work directory")
    relative_root = f"children/{attempt.hypothesis_id}/attempt-{attempt_number:02d}"
    for name in _COMMAND_FILES:
        path = work / name
        if path.exists() or path.is_symlink():
            _copy_file(
                state,
                path,
                f"{relative_root}/command/{name.removeprefix('.')}",
                role=f"nextflow_{name.removeprefix('.')}",
            )
    result_root = work / (
        f"phase3_first_copy_{attempt.crystal_id}_{attempt.hypothesis_id}"
    )
    if result_root.is_dir() and not result_root.is_symlink():
        for path in sorted(result_root.rglob("*")):
            if path.is_symlink():
                assert state.omissions is not None
                state.omissions.append(
                    {
                        "relative_path": f"{relative_root}/result/{path.name}",
                        "role": "mr_result_asset",
                        "reason": "symlink_rejected",
                    }
                )
                continue
            if not path.is_file():
                continue
            relative = path.relative_to(result_root).as_posix()
            _copy_file(
                state,
                path,
                f"{relative_root}/result/{relative}",
                role="mr_result_asset",
            )


def _allocated_resources(work: Path) -> dict[str, object] | None:
    command_run = work / ".command.run"
    if command_run.is_symlink() or not command_run.is_file():
        return None
    try:
        text = command_run.read_text(encoding="utf-8")
    except OSError, UnicodeError:
        return None
    cpus = _SBATCH_CPUS.search(text)
    time = _SBATCH_TIME.search(text)
    memory = _SBATCH_MEMORY.search(text)
    if cpus is None or time is None or memory is None:
        return None
    return {
        "cpus": int(cpus.group(1)),
        "time_limit": time.group(1),
        "memory_limit": memory.group(1),
    }


def _normalised_result_state(work: Path, attempt: _Attempt) -> dict[str, object]:
    path = (
        work
        / f"phase3_first_copy_{attempt.crystal_id}_{attempt.hypothesis_id}"
        / "normalised_mr_result.json"
    )
    if path.is_symlink() or not path.is_file():
        return {"state": "absent", "execution_status": None}
    try:
        result = NormalisedMrResult.model_validate_json(
            path.read_text(encoding="utf-8")
        )
    except OSError, UnicodeError, ValueError:
        return {"state": "invalid", "execution_status": None}
    if result.hypothesis_id != attempt.hypothesis_id:
        return {"state": "cross_hypothesis", "execution_status": None}
    return {"state": "valid", "execution_status": result.execution_status.value}


def build_failed_mr_evidence(
    *,
    run_id: str,
    nextflow_log: Path,
    work_root: Path,
    output_directory: Path,
) -> Path:
    """Create one immutable failed-screen child-evidence package."""

    if _RUN_ID.fullmatch(run_id) is None:
        raise MrFailureEvidenceError("invalid unknown-screen run ID")
    if output_directory.exists():
        raise MrFailureEvidenceError("failed-child output already exists")
    log = nextflow_log.resolve(strict=True)
    work = work_root.resolve(strict=True)
    if log.is_symlink() or work_root.is_symlink() or not work.is_dir():
        raise MrFailureEvidenceError("failed-child input root is unsafe")
    text = log.read_text(encoding="utf-8")
    attempts, completions = _parse_log(text)
    hypotheses, source_inventories = _hypotheses(work)
    attempts_by_job = {attempt.job_id: attempt for attempt in attempts}
    orphan_completions = set(completions) - set(attempts_by_job)
    if orphan_completions:
        raise MrFailureEvidenceError(
            "completed MR child jobs are absent from the submission inventory: "
            + ", ".join(sorted(orphan_completions))
        )
    for job_id, completion in completions.items():
        attempt = attempts_by_job[job_id]
        if (
            completion.crystal_id != attempt.crystal_id
            or completion.hypothesis_id != attempt.hypothesis_id
        ):
            raise MrFailureEvidenceError(
                f"child completion identity differs from its submission: {job_id}"
            )
    if attempts and not hypotheses:
        raise MrFailureEvidenceError(
            "submitted MR tasks have no recoverable funnel inventory"
        )
    submitted_ids = {attempt.hypothesis_id for attempt in attempts}
    unknown_submissions = submitted_ids - set(hypotheses)
    if unknown_submissions and hypotheses:
        raise MrFailureEvidenceError(
            "submitted tasks are absent from the funnel inventory: "
            + ", ".join(sorted(unknown_submissions))
        )

    output_directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        dir=output_directory.parent,
        prefix=f".{output_directory.name}.",
    ) as temporary:
        staging = Path(temporary) / output_directory.name
        staging.mkdir()
        state = _PackageState(staging)
        for hypothesis_id in sorted(hypotheses):
            _copy_hypothesis_evidence(
                state,
                work,
                hypotheses[hypothesis_id],
                source_inventories[hypothesis_id],
            )

        attempts_by_hypothesis: dict[str, list[_Attempt]] = {}
        for attempt in attempts:
            attempts_by_hypothesis.setdefault(attempt.hypothesis_id, []).append(attempt)
        for hypothesis_id in attempts_by_hypothesis:
            attempts_by_hypothesis[hypothesis_id].sort(
                key=lambda item: item.submission_index
            )
        for hypothesis_id in sorted(attempts_by_hypothesis):
            for attempt_number, attempt in enumerate(
                attempts_by_hypothesis[hypothesis_id], start=1
            ):
                _copy_attempt_evidence(
                    state,
                    work,
                    attempt,
                    attempt_number,
                )

        child_records: list[dict[str, object]] = []
        for hypothesis_id in sorted(set(hypotheses) | submitted_ids):
            hypothesis = hypotheses.get(hypothesis_id)
            hypothesis_attempts = attempts_by_hypothesis.get(hypothesis_id, [])
            attempt_records: list[dict[str, object]] = []
            for attempt_number, attempt in enumerate(hypothesis_attempts, start=1):
                completion = completions.get(attempt.job_id)
                attempt_work = _inside(
                    attempt.work_directory,
                    work,
                    label="MR task work directory",
                )
                attempt_records.append(
                    {
                        "attempt": attempt_number,
                        "native_job_id": attempt.job_id,
                        "state": "completed"
                        if completion is not None
                        else "unfinished_at_controller_abort",
                        "exit_code": completion.exit_code if completion else None,
                        "started": completion.started if completion else None,
                        "exited": completion.exited if completion else None,
                        "allocated_resources": _allocated_resources(attempt_work),
                        "normalised_result": _normalised_result_state(
                            attempt_work,
                            attempt,
                        ),
                    }
                )
            child_records.append(
                {
                    "crystal_id": hypothesis.crystal_id
                    if hypothesis is not None
                    else hypothesis_attempts[0].crystal_id,
                    "hypothesis_id": hypothesis_id,
                    "expected_copy_count": hypothesis.copy_count_expected
                    if hypothesis is not None
                    else None,
                    "searched_copy_count": hypothesis.copy_number_to_search
                    if hypothesis is not None
                    else None,
                    "state": "unsubmitted"
                    if not hypothesis_attempts
                    else "completed"
                    if all(record["state"] == "completed" for record in attempt_records)
                    else "unfinished_at_controller_abort",
                    "attempts": attempt_records,
                }
            )

        assert state.files is not None
        assert state.omissions is not None
        completed_attempts = sum(
            job_id in completions for job_id in {attempt.job_id for attempt in attempts}
        )
        manifest_identity = {
            "run_id": run_id,
            "nextflow_log_sha256": sha256_file(log, progress=False),
            "hypothesis_ids": sorted(set(hypotheses) | submitted_ids),
            "submitted_native_job_ids": [attempt.job_id for attempt in attempts],
            "file_sha256s": [
                item["sha256"]
                for item in sorted(
                    state.files, key=lambda row: str(row["relative_path"])
                )
            ],
        }
        manifest = {
            "schema_version": "1.0",
            "adapter_version": _ADAPTER_VERSION,
            "evidence_id": content_id("mrfailure_", manifest_identity),
            "created_at": utc_now_iso(),
            "run_id": run_id,
            "profile": "unknown-screen",
            "scientific_evidence_accepted": False,
            "cache_reusable": False,
            "nextflow_log_sha256": manifest_identity["nextflow_log_sha256"],
            "funnel_hypothesis_count": len(hypotheses),
            "submitted_attempt_count": len(attempts),
            "completed_attempt_count": completed_attempts,
            "unfinished_attempt_count": len(attempts) - completed_attempts,
            "unsubmitted_hypothesis_count": len(set(hypotheses) - submitted_ids),
            "children": child_records,
            "files": sorted(state.files, key=lambda row: str(row["relative_path"])),
            "omissions": sorted(
                state.omissions,
                key=lambda row: (str(row["relative_path"]), str(row["role"])),
            ),
            "retained_total_bytes": state.total_bytes,
        }
        manifest_path = staging / "manifest.json"
        atomic_write_json(manifest_path, manifest)
        checksummed = sorted(
            path
            for path in staging.rglob("*")
            if path.is_file() and path.name not in {"checksums.sha256", "file-count"}
        )
        if len(checksummed) > _MAX_FILES:
            raise MrFailureEvidenceError(
                "failed-child evidence exceeds file-count bound"
            )
        checksum_lines = "".join(
            f"{sha256_file(path, progress=False)}  "
            f"{path.relative_to(staging).as_posix()}\n"
            for path in checksummed
        )
        atomic_write_text(staging / "checksums.sha256", checksum_lines)
        atomic_write_text(staging / "file-count", f"{len(checksummed)}\n")
        package_total = 0
        for path in staging.rglob("*"):
            if not path.is_file():
                continue
            size = path.stat().st_size
            if size > _MAX_FILE_BYTES:
                raise MrFailureEvidenceError(
                    "failed-child package control file exceeds per-file bound"
                )
            package_total += size
        if package_total > _MAX_TOTAL_BYTES:
            raise MrFailureEvidenceError(
                "failed-child package exceeds total byte bound"
            )
        staging.rename(output_directory)
    return output_directory / "manifest.json"


def main() -> int:
    """Internal fixed-argument command for the reviewed job wrapper."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--nextflow-log", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = build_failed_mr_evidence(
            run_id=args.run_id,
            nextflow_log=args.nextflow_log,
            work_root=args.work_root,
            output_directory=args.outdir,
        )
    except (
        MrFailureEvidenceError,
        OSError,
        UnicodeError,
        json.JSONDecodeError,
    ) as error:
        print(f"failed MR evidence collection refused: {error}", file=sys.stderr)
        return 1
    print(manifest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
