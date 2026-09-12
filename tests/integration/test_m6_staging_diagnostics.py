"""Read-only fixed M6 attachment observations, not staging/scientific acceptance."""

import base64
import json
from pathlib import Path

import pytest

from tests.integration.test_hpc_remote_dispatcher import (
    M6_INPUTS_RUN_ID,
    M6_NATIVE_CONTROL_RUN_ID,
    OWNER_ID,
    _decode_protocol,
    _prepare_m6_import_diagnostics,
    _run,
)

COMMON_STATES = (
    "site-id",
    "controller-kind",
    "m6-runner-archive-sha256",
    "m6-runner-manifest-sha256",
    "m6-runner-case-count",
    "m6-runner-object-count",
    "m6-track",
)
SCIENTIFIC_STATES = (
    "m6-execution-purpose",
    "database-manifest",
    "database-manifest-sha256",
    "phenix-manifest",
    "phenix-manifest-sha256",
)
EVENTS = (
    "stage_started",
    "stage_source_archive_verified",
    "stage_hpc_environment_ready",
    "stage_completed",
    "m6_runner_ready",
)
TIME_FIELDS = (
    "stage_started_at",
    "source_archive_verified_at",
    "environment_ready_at",
    "base_stage_completed_at",
    "runner_ready_at",
)


def _logs(
    dispatcher: Path,
    environment: dict[str, str],
    root: Path,
    *,
    run_id: str = M6_NATIVE_CONTROL_RUN_ID,
    success: bool = True,
) -> dict[str, str]:
    return _decode_protocol(
        _run(
            [str(dispatcher), "logs", run_id, OWNER_ID, "1"],
            cwd=root,
            environment=environment,
            success=success,
        ).stdout
    )


def _summary(response: dict[str, str]) -> dict[str, str]:
    payload = base64.b64decode(response["content_base64"], validate=True).decode(
        "ascii"
    )
    assert len(payload.splitlines()) == 1
    assert len(payload.encode("ascii")) <= 2 * 1024 * 1024
    fields = dict(field.split("=", 1) for field in payload.strip().split())
    assert set(fields) == {
        "staging_phase",
        "temporary_runner_archive",
        "observed_bytes",
        "missing_state_files",
        "empty_state_files",
        "runner_manifest_state",
        "event_journal",
        *TIME_FIELDS,
    }
    return fields


def _snapshot(run: Path) -> dict[str, tuple[bytes, int, int]]:
    return {
        path.relative_to(run).as_posix(): (
            path.read_bytes(),
            path.stat().st_ino,
            path.stat().st_mtime_ns,
        )
        for path in run.rglob("*")
        if path.is_file()
    }


def test_staged_base_does_not_claim_attached_runner_or_expose_state_contents(
    tmp_path: Path,
) -> None:
    dispatcher, environment, run = _prepare_m6_import_diagnostics(tmp_path)
    (run / "state/phase").write_text("staged\n", encoding="ascii")
    (run / "state/site-id").write_text("DO_NOT_EMIT_STATE_CONTENT\n", encoding="ascii")
    (run / "state/m6-track").write_bytes(b"")
    (run / "events.jsonl").write_text(
        '{"event":"stage_started","timestamp":"2026-09-12T07:00:00Z"}\n'
        '{"event":"stage_hpc_environment_ready","timestamp":"2026-09-12T07:15:00Z"}\n'
        '{"event":"stage_completed","timestamp":"2026-09-12T07:15:01Z"}\n',
        encoding="ascii",
    )
    before = _snapshot(run)
    response = _logs(dispatcher, environment, tmp_path)
    observed = _summary(response)
    assert observed["staging_phase"] == "staged"
    assert set(observed["missing_state_files"].split(",")) == (
        set(COMMON_STATES + SCIENTIFIC_STATES) - {"site-id", "m6-track"}
    )
    assert observed["empty_state_files"] == "m6-track"
    assert observed["runner_manifest_state"] == "absent"
    assert observed["stage_started_at"] == "2026-09-12T07:00:00Z"
    assert observed["environment_ready_at"] == "2026-09-12T07:15:00Z"
    assert observed["base_stage_completed_at"] == "2026-09-12T07:15:01Z"
    assert observed["source_archive_verified_at"] == "unavailable"
    assert observed["runner_ready_at"] == "unavailable"
    assert "DO_NOT_EMIT_STATE_CONTENT" not in str(response)
    assert OWNER_ID not in str(response)
    assert before == _snapshot(run)
    assert not (run / "state/job-id").exists()


@pytest.mark.parametrize("empty", (False, True))
def test_fixed_manifest_and_all_state_presence_are_not_content_validation(
    tmp_path: Path,
    empty: bool,
) -> None:
    dispatcher, environment, run = _prepare_m6_import_diagnostics(tmp_path)
    for name in COMMON_STATES + SCIENTIFIC_STATES:
        (run / "state" / name).write_text("UNVALIDATED_CONTENT\n", encoding="ascii")
    inputs = run / "artifacts/m6-runner-inputs"
    inputs.mkdir(parents=True)
    (inputs / "runner_manifest.json").write_bytes(
        b"" if empty else b"not a valid manifest"
    )
    observed = _summary(_logs(dispatcher, environment, tmp_path))
    assert observed["missing_state_files"] == "none"
    assert observed["empty_state_files"] == "none"
    assert observed["runner_manifest_state"] == ("empty" if empty else "present")
    assert all(observed[name] == "unavailable" for name in TIME_FIELDS)
    assert "UNVALIDATED_CONTENT" not in str(observed)


def test_input_qualification_does_not_invent_scientific_purpose_requirements(
    tmp_path: Path,
) -> None:
    dispatcher, environment, run = _prepare_m6_import_diagnostics(tmp_path)
    target = run.with_name(M6_INPUTS_RUN_ID)
    run.rename(target)
    (target / "state/profile").write_text("m6-inputs\n", encoding="ascii")
    observed = _summary(
        _logs(dispatcher, environment, tmp_path, run_id=M6_INPUTS_RUN_ID)
    )
    assert observed["missing_state_files"].split(",") == list(COMMON_STATES)


@pytest.mark.parametrize("empty", (False, True))
def test_event_journal_observations_are_distinct_and_only_show_fixed_timestamps(
    tmp_path: Path,
    empty: bool,
) -> None:
    dispatcher, environment, run = _prepare_m6_import_diagnostics(tmp_path)
    rows = [
        {"event": event, "timestamp": f"2026-09-12T07:00:0{index}Z"}
        for index, event in enumerate(EVENTS)
    ]
    rows.append({"event": "not_a_selected_stage", "timestamp": "2026-09-12T08:00:00Z"})
    payload = (
        ""
        if empty
        else "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows)
    )
    (run / "events.jsonl").write_text(payload, encoding="ascii")
    before = _snapshot(run)
    observed = _summary(_logs(dispatcher, environment, tmp_path))
    assert observed["event_journal"] == ("empty" if empty else "present")
    for index, name in enumerate(TIME_FIELDS):
        assert observed[name] == (
            "unavailable" if empty else f"2026-09-12T07:00:0{index}Z"
        )
    assert "not_a_selected_stage" not in str(observed)
    assert before == _snapshot(run)


@pytest.mark.parametrize(
    "corruption", ("malformed", "duplicate", "nul", "extra_field", "oversized")
)
def test_unsafe_event_evidence_fails_without_returning_partial_diagnostics(
    tmp_path: Path,
    corruption: str,
) -> None:
    dispatcher, environment, run = _prepare_m6_import_diagnostics(tmp_path)
    row = b'{"event":"stage_started","timestamp":"2026-09-12T07:00:00Z"}\n'
    payload = {
        "malformed": row + b'{"event":"TRUNCATED_SECRET',
        "duplicate": row + row,
        "nul": row.replace(b"stage_started", b"stage_\0started"),
        "extra_field": row.replace(b"}", b',"unexpected":"SECRET"}'),
        "oversized": b"x" * (2 * 1024 * 1024 + 1),
    }[corruption]
    (run / "events.jsonl").write_bytes(payload)
    before = _snapshot(run)
    response = _logs(dispatcher, environment, tmp_path, success=False)
    assert response["failure_class"] == "wrapper_failure"
    assert "event journal" in response["message"]
    assert "content_base64" not in response
    assert "SECRET" not in str(response)
    assert before == _snapshot(run)


@pytest.mark.parametrize(
    "relative",
    (
        "state/m6-track",
        "events.jsonl",
        "artifacts",
        "artifacts/m6-runner-inputs",
        "artifacts/m6-runner-inputs/runner_manifest.json",
    ),
)
def test_new_diagnostic_paths_refuse_symlinks_before_reading_payloads(
    tmp_path: Path,
    relative: str,
) -> None:
    dispatcher, environment, run = _prepare_m6_import_diagnostics(tmp_path)
    outside = tmp_path / "outside-secret"
    outside.write_text("UNRELATED_SECRET\n", encoding="ascii")
    selected = run / relative
    selected.parent.mkdir(parents=True, exist_ok=True)
    selected.symlink_to(outside)
    response = _logs(dispatcher, environment, tmp_path, success=False)
    assert response["failure_class"] == "wrapper_failure"
    assert "unsafe M6 staging" in response["message"]
    assert "content_base64" not in response
    assert "UNRELATED_SECRET" not in str(response)
