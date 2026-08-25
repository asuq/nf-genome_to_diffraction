"""Focused regressions for the fixed Phase III worker-network probe."""

from __future__ import annotations

from pathlib import Path

import pytest

from genome_to_diffraction.execution import network_probe


class _Socket:
    def __init__(self, result: int) -> None:
        self.result = result

    def __enter__(self) -> _Socket:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def settimeout(self, timeout: float) -> None:
        assert timeout == 2.0

    def connect_ex(self, address: tuple[str, int]) -> int:
        assert address == network_probe.TEST_ADDRESS
        return self.result


def _set_probe_environment(
    monkeypatch: pytest.MonkeyPatch,
    *,
    job_id: str,
    network_namespace: str,
    socket_result: int = network_probe.errno.ENETUNREACH,
) -> None:
    monkeypatch.setenv("SLURM_JOB_ID", job_id)
    monkeypatch.setenv("GTD_COMPUTE_NETWORK_ACCESS", "false")
    monkeypatch.setattr(network_probe.os, "readlink", lambda _path: network_namespace)
    monkeypatch.setattr(
        network_probe.socket,
        "socket",
        lambda *_args: _Socket(socket_result),
    )


def test_worker_probe_requires_a_distinct_namespace_and_denied_socket(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "child.json"
    _set_probe_environment(
        monkeypatch,
        job_id="700002",
        network_namespace="net:[4026533002]",
    )

    result = network_probe.run_probe(
        role="child_slurm",
        outer_job_id="700001",
        outer_network_namespace="net:[4026533001]",
        output=output,
    )

    assert result["socket_denied"] is True
    assert result["worker_slurm_job_id"] == "700002"
    assert output.is_file()


@pytest.mark.parametrize(
    ("job_id", "namespace", "socket_result", "message"),
    (
        ("700001", "net:[4026533001]", network_probe.errno.ENETUNREACH, "retained"),
        ("700002", "net:[4026533002]", 0, "was not denied"),
    ),
)
def test_worker_probe_fails_without_real_network_isolation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    job_id: str,
    namespace: str,
    socket_result: int,
    message: str,
) -> None:
    output = tmp_path / "probe.json"
    _set_probe_environment(
        monkeypatch,
        job_id=job_id,
        network_namespace=namespace,
        socket_result=socket_result,
    )

    with pytest.raises(network_probe.NetworkProbeError, match=message):
        network_probe.run_probe(
            role="child_slurm",
            outer_job_id="700001",
            outer_network_namespace="net:[4026533001]",
            output=output,
        )

    assert not output.exists()


def test_probe_summary_requires_one_child_and_one_controller_task(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    child = tmp_path / "phase3-network-probe-child.json"
    controller = tmp_path / "phase3-network-probe-controller.json"
    _set_probe_environment(
        monkeypatch,
        job_id="700002",
        network_namespace="net:[4026533002]",
    )
    network_probe.run_probe(
        role="child_slurm",
        outer_job_id="700001",
        outer_network_namespace="net:[4026533001]",
        output=child,
    )
    _set_probe_environment(
        monkeypatch,
        job_id="700001",
        network_namespace="net:[4026533003]",
    )
    network_probe.run_probe(
        role="controller_local",
        outer_job_id="700001",
        outer_network_namespace="net:[4026533001]",
        output=controller,
    )

    summary = network_probe.summarise_probes(
        child_report=child,
        controller_report=controller,
        run_id=("gtd-phase3-network-probe-20260825T120000Z-0123456789ab-01234567"),
        site_id="marmic",
        source_commit="0" * 40,
        nf_helper_commit="1" * 40,
        output=tmp_path / "summary.json",
    )

    assert summary["gate_passed"] is True
    assert summary["qualified_task_classes"] == ["child_slurm", "controller_local"]
