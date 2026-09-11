"""Read-only login-controller evidence shared by analysis and internal HPC code.

Inputs are saved process identities and terminal records, never executable
commands. Validators return the unchanged identity or raise ExecutionEvidenceError
for malformed or inconsistent ownership, source, process, log or timestamp data.
No state is inferred from the operating system, no scientific status is assigned,
and no external tools or cache are used. Python 3.14 is sufficient. Common-client,
M6 collection, process-supervisor and offline-wheel tests cover this boundary.
The public scientific wheel must not import the internal HPC implementation.
"""

import re
from collections.abc import Mapping
from datetime import datetime

RAVEN_LOGIN_PROFILES = frozenset(
    {
        "m6-nextflow-smoke",
        "m6-native-control",
        "m6-operational",
        "m6-leakage",
        "rf-reference",
    }
)


class ExecutionEvidenceError(ValueError):
    """Saved controller evidence violates its fixed identity contract."""


def validate_process_identity(value: object) -> Mapping[str, object]:
    """Validate Raven host/boot/PID/start ticks without inferring live state."""

    if not isinstance(value, Mapping) or set(value) != {
        "host",
        "pid",
        "start_ticks",
        "boot_id",
    }:
        raise ExecutionEvidenceError("controller process identity is incomplete")
    pid = value["pid"]
    host, ticks, boot = value["host"], value["start_ticks"], value["boot_id"]
    if (
        type(pid) is not int
        or pid <= 0
        or not isinstance(host, str)
        or re.fullmatch(r"raven0[1-4]i?", host) is None
        or not isinstance(ticks, str)
        or re.fullmatch(r"[1-9][0-9]*", ticks) is None
        or not isinstance(boot, str)
        or re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", boot) is None
    ):
        raise ExecutionEvidenceError("controller process identity is invalid")
    return value


def validate_login_result_binding(
    identity: Mapping[str, object],
    result: Mapping[str, object],
    *,
    run_id: str,
    owner_id: str,
    profile: str,
    source_commit: str,
) -> None:
    """Bind collected login completion to its original owned launch identity."""

    if profile not in RAVEN_LOGIN_PROFILES:
        raise ExecutionEvidenceError("controller profile is not a login process")
    if (
        re.fullmatch(r"[0-9a-f]{32}", owner_id) is None
        or re.fullmatch(r"[0-9a-f]{40}", source_commit) is None
        or re.fullmatch(
            rf"gtd-{profile}-[0-9]{{8}}T[0-9]{{6}}Z-"
            rf"{source_commit[:12]}-[0-9a-f]{{8}}",
            run_id,
        )
        is None
    ):
        raise ExecutionEvidenceError("controller owner or source identity is invalid")
    expected_identity = {
        "schema_version": "1.0",
        "run_id": run_id,
        "owner_id": owner_id,
        "site_id": "raven",
        "profile": profile,
        "source_commit": source_commit,
        "controller_kind": "login_process",
    }
    for key, expected in expected_identity.items():
        if identity.get(key) != expected:
            raise ExecutionEvidenceError(f"controller identity {key} differs")
    process = validate_process_identity(identity.get("process"))
    if any(field in result for field in ("job_id", "scheduler_state")):
        raise ExecutionEvidenceError("login result contains scheduler evidence")
    expected_result = {
        **expected_identity,
        "process": process,
        "started_at": identity.get("started_at"),
        "standard_output": "logs/controller.log",
        "standard_error": "logs/controller.log",
        "application_log": f"logs/{profile}.log",
    }
    for key, expected in expected_result.items():
        if result.get(key) != expected:
            raise ExecutionEvidenceError(f"controller result {key} differs")
    timestamps = []
    for key in ("started_at", "completed_at"):
        value = result.get(key)
        if not isinstance(value, str):
            raise ExecutionEvidenceError(f"controller result {key} is absent")
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as error:
            raise ExecutionEvidenceError(
                f"controller result {key} is invalid"
            ) from error
        if parsed.tzinfo is None:
            raise ExecutionEvidenceError(f"controller result {key} has no timezone")
        timestamps.append(parsed)
    if timestamps[1] < timestamps[0]:
        raise ExecutionEvidenceError("controller completed before it started")
