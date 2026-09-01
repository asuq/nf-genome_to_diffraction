"""Qualify the fail-closed network boundary used by scheduled Phase III tasks."""

from __future__ import annotations

import argparse
import errno
import hashlib
import os
import re
import socket
import sys
from collections.abc import Sequence
from pathlib import Path

from genome_to_diffraction.checksums import atomic_write_json
from genome_to_diffraction.schemas.io import ContractLoadError, load_json_document

ADAPTER_VERSION = "phase3-worker-network-probe-v1"
TEST_ADDRESS = ("192.0.2.1", 443)
DENIED_ERRNOS = frozenset({errno.ENETDOWN, errno.ENETUNREACH, errno.EHOSTUNREACH})
JOB_ID_PATTERN = re.compile(r"^[0-9]+$")
NETNS_PATTERN = re.compile(r"^net:\[[0-9]+\]$")
RUN_ID_PATTERN = re.compile(
    r"^gtd-phase3-network-probe-[0-9]{8}T[0-9]{6}Z-"
    r"[0-9a-f]{12}-[0-9a-f]{8}$"
)
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")


class NetworkProbeError(ValueError):
    """The worker or collected probe evidence violates the fixed contract."""


def _required_match(value: str, pattern: re.Pattern[str], label: str) -> str:
    if pattern.fullmatch(value) is None:
        raise NetworkProbeError(f"{label} is invalid")
    return value


def run_probe(
    *,
    role: str,
    outer_job_id: str,
    outer_network_namespace: str,
    output: Path,
) -> dict[str, object]:
    """Attempt one fixed external socket from an isolated scheduled task."""

    if role not in {"child_slurm", "controller_local"}:
        raise NetworkProbeError("role must be child_slurm or controller_local")
    _required_match(outer_job_id, JOB_ID_PATTERN, "outer Slurm job ID")
    _required_match(
        outer_network_namespace,
        NETNS_PATTERN,
        "outer network namespace",
    )
    worker_job_id = os.environ.get("SLURM_JOB_ID", "")
    _required_match(worker_job_id, JOB_ID_PATTERN, "worker Slurm job ID")
    if os.environ.get("GTD_COMPUTE_NETWORK_ACCESS") != "false":
        raise NetworkProbeError("compute-network denial marker is absent")

    worker_network_namespace = os.readlink("/proc/self/ns/net")
    _required_match(
        worker_network_namespace,
        NETNS_PATTERN,
        "worker network namespace",
    )
    if worker_network_namespace == outer_network_namespace:
        raise NetworkProbeError("worker retained the outer network namespace")
    if role == "child_slurm" and worker_job_id == outer_job_id:
        raise NetworkProbeError("child probe did not receive an independent Slurm job")
    if role == "controller_local" and worker_job_id != outer_job_id:
        raise NetworkProbeError("controller-local probe changed the outer Slurm job")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.settimeout(2.0)
        denied_errno = connection.connect_ex(TEST_ADDRESS)
    if denied_errno not in DENIED_ERRNOS:
        raise NetworkProbeError(
            "external socket was not denied by the empty network namespace: "
            f"errno={denied_errno}"
        )

    record: dict[str, object] = {
        "schema_version": "1.0",
        "adapter_version": ADAPTER_VERSION,
        "scientific_execution_performed": False,
        "role": role,
        "outer_slurm_job_id": outer_job_id,
        "worker_slurm_job_id": worker_job_id,
        "outer_network_namespace": outer_network_namespace,
        "worker_network_namespace": worker_network_namespace,
        "compute_network_access": False,
        "test_address": f"{TEST_ADDRESS[0]}:{TEST_ADDRESS[1]}",
        "socket_denied": True,
        "socket_errno": denied_errno,
        "socket_errno_name": errno.errorcode[denied_errno],
    }
    atomic_write_json(output, record)
    return record


def _load_probe(path: Path) -> dict[str, object]:
    try:
        value = load_json_document(path)
    except ContractLoadError as error:
        raise NetworkProbeError(
            f"cannot load probe report {path.name}: {error}"
        ) from error
    if not isinstance(value, dict):
        raise NetworkProbeError(f"probe report {path.name} must be a JSON object")
    expected = {
        "schema_version": "1.0",
        "adapter_version": ADAPTER_VERSION,
        "scientific_execution_performed": False,
        "compute_network_access": False,
        "socket_denied": True,
        "test_address": f"{TEST_ADDRESS[0]}:{TEST_ADDRESS[1]}",
    }
    for key, expected_value in expected.items():
        if value.get(key) != expected_value:
            raise NetworkProbeError(f"probe report {path.name} has invalid {key}")
    denied_errno = value.get("socket_errno")
    if not isinstance(denied_errno, int) or denied_errno not in DENIED_ERRNOS:
        raise NetworkProbeError(f"probe report {path.name} has invalid socket_errno")
    if value.get("socket_errno_name") != errno.errorcode[denied_errno]:
        raise NetworkProbeError(
            f"probe report {path.name} has inconsistent socket errno name"
        )
    for key, pattern in (
        ("outer_slurm_job_id", JOB_ID_PATTERN),
        ("worker_slurm_job_id", JOB_ID_PATTERN),
        ("outer_network_namespace", NETNS_PATTERN),
        ("worker_network_namespace", NETNS_PATTERN),
    ):
        field = value.get(key)
        if not isinstance(field, str):
            raise NetworkProbeError(f"probe report {path.name} omits {key}")
        _required_match(field, pattern, key)
    if value["outer_network_namespace"] == value["worker_network_namespace"]:
        raise NetworkProbeError(
            f"probe report {path.name} retained the outer network namespace"
        )
    return value


def summarise_probes(
    *,
    child_report: Path,
    controller_report: Path,
    run_id: str,
    site_id: str,
    source_commit: str,
    nf_helper_commit: str,
    output: Path,
) -> dict[str, object]:
    """Validate both task classes and write one immutable qualification summary."""

    _required_match(run_id, RUN_ID_PATTERN, "run ID")
    if site_id not in {"marmic", "viper-cpu"}:
        raise NetworkProbeError("site ID is invalid")
    _required_match(source_commit, COMMIT_PATTERN, "source commit")
    _required_match(nf_helper_commit, COMMIT_PATTERN, "nf-helper commit")
    child = _load_probe(child_report)
    controller = _load_probe(controller_report)
    if child.get("role") != "child_slurm":
        raise NetworkProbeError("child report has the wrong role")
    if controller.get("role") != "controller_local":
        raise NetworkProbeError("controller report has the wrong role")
    common = ("outer_slurm_job_id", "outer_network_namespace", "test_address")
    if any(child[key] != controller[key] for key in common):
        raise NetworkProbeError("probe reports do not share one outer execution")
    if child["worker_slurm_job_id"] == child["outer_slurm_job_id"]:
        raise NetworkProbeError("child report does not prove Slurm fan-out")
    if controller["worker_slurm_job_id"] != controller["outer_slurm_job_id"]:
        raise NetworkProbeError("controller report does not prove local execution")
    if child["worker_network_namespace"] == controller["worker_network_namespace"]:
        raise NetworkProbeError("probe tasks unexpectedly share one worker namespace")

    summary: dict[str, object] = {
        "schema_version": "1.0",
        "adapter_version": ADAPTER_VERSION,
        "run_id": run_id,
        "site_id": site_id,
        "source_commit": source_commit,
        "nf_helper_commit": nf_helper_commit,
        "scientific_execution_performed": False,
        "gate_passed": True,
        "outer_slurm_job_id": child["outer_slurm_job_id"],
        "outer_network_namespace": child["outer_network_namespace"],
        "qualified_task_classes": ["child_slurm", "controller_local"],
        "socket_denial": "empty_linux_network_namespace",
        "reports": [
            {
                "role": child["role"],
                "path": child_report.name,
                "sha256": hashlib.sha256(child_report.read_bytes()).hexdigest(),
            },
            {
                "role": controller["role"],
                "path": controller_report.name,
                "sha256": hashlib.sha256(controller_report.read_bytes()).hexdigest(),
            },
        ],
    }
    atomic_write_json(output, summary)
    return summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    probe = commands.add_parser("probe")
    probe.add_argument(
        "--role", choices=("child_slurm", "controller_local"), required=True
    )
    probe.add_argument("--outer-job-id", required=True)
    probe.add_argument("--outer-network-namespace", required=True)
    probe.add_argument("--output", type=Path, required=True)
    summarise = commands.add_parser("summarise")
    summarise.add_argument("--child-report", type=Path, required=True)
    summarise.add_argument("--controller-report", type=Path, required=True)
    summarise.add_argument("--run-id", required=True)
    summarise.add_argument("--site-id", choices=("marmic", "viper-cpu"), required=True)
    summarise.add_argument("--source-commit", required=True)
    summarise.add_argument("--nf-helper-commit", required=True)
    summarise.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one fixed worker probe or validate the two-task qualification."""

    arguments = _build_parser().parse_args(argv)
    try:
        if arguments.operation == "probe":
            run_probe(
                role=arguments.role,
                outer_job_id=arguments.outer_job_id,
                outer_network_namespace=arguments.outer_network_namespace,
                output=arguments.output,
            )
        else:
            summarise_probes(
                child_report=arguments.child_report,
                controller_report=arguments.controller_report,
                run_id=arguments.run_id,
                site_id=arguments.site_id,
                source_commit=arguments.source_commit,
                nf_helper_commit=arguments.nf_helper_commit,
                output=arguments.output,
            )
    except (NetworkProbeError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
