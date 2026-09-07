"""Raven controller ownership checks without launching remote scientific work."""

import json
from pathlib import Path

import pytest

from genome_to_diffraction.hpc import raven_identification as raven


def _spec() -> raven.RavenLaunch:
    root = Path("/ptmp/test_user/nf-genome_to_diffraction")
    return raven.RavenLaunch(
        schema_version="1.0",
        run_id=f"gtd-identification-screen-20260907T000000Z-{'a' * 12}-01234567",
        owner_id="b" * 32,
        site_id="raven",
        account="test_cpu",
        source_commit="a" * 40,
        source_root=root / "sources" / ("a" * 40),
        input_root=root / "inputs/smoke",
        input_id="identificationinputs_" + "c" * 64,
        phenix_manifest=root / "software/phenix.json",
        phenix_manifest_sha256="d" * 64,
        mtz_root=root / "inputs/mtz",
        run_mode="smoke",
    )


def test_raven_status_rejects_other_owner_and_reused_pid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = _spec()
    process = {"pid": 123, "start_ticks": "456", "boot_id": "test-boot"}
    (tmp_path / "controller.json").write_text(
        json.dumps(
            {
                "run_id": spec.run_id,
                "owner_id": spec.owner_id,
                "process": process,
            }
        )
    )
    state = {
        "state": "RUNNING",
        "run_id": spec.run_id,
        "owner_id": spec.owner_id,
        "source_commit": spec.source_commit,
        "input_id": spec.input_id,
        "identity_accepted": False,
    }
    (tmp_path / "state.json").write_text(json.dumps(state))
    monkeypatch.setattr(raven, "_process_identity", lambda pid: process)
    result = raven._status(tmp_path, spec)
    assert result["state"] == "RUNNING" and not result["terminal"]
    assert result["controller_kind"] == "login_process"
    monkeypatch.setattr(
        raven, "_process_identity", lambda pid: {**process, "start_ticks": "999"}
    )
    assert raven._status(tmp_path, spec)["state"] == "FAILED"
    state.update(state="COMPLETED", owner_id="e" * 32)
    (tmp_path / "state.json").write_text(json.dumps(state))
    with pytest.raises(ValueError, match="another source/input/owner"):
        raven._status(tmp_path, spec)


def test_raven_duplicate_start_never_spawns_a_second_controller(tmp_path: Path) -> None:
    (tmp_path / "controller.json").write_text("{}")
    with pytest.raises(ValueError, match="already been started"):
        raven._start(tmp_path, _spec())


def test_raven_command_keeps_shared_graph_and_ptmp_work_without_marmic_cap() -> None:
    spec = _spec()
    run = Path("/ptmp/test_user/nf-genome_to_diffraction/runs") / spec.run_id
    command = raven.nextflow_command(run, spec)
    assert command[command.index("-profile") + 1] == "raven"
    assert command[command.index("-work-dir") + 1] == str(
        run / "cache/identification/work"
    )
    assert command[command.index("run") + 1] == str(
        spec.source_root / "qualification.nf"
    )
    assert "-qs" not in command and "-resume" not in command


def test_raven_rejects_foreign_host_and_non_ptmp_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(raven.socket, "gethostname", lambda: "not-raven")
    with pytest.raises(ValueError, match="explicit Raven login"):
        raven._load(tmp_path, "b" * 32)
    monkeypatch.setattr(raven.socket, "gethostname", lambda: "raven03")
    with pytest.raises(ValueError, match="owned /ptmp"):
        raven._load(tmp_path, "b" * 32)
