"""Read-only Raven setup binding, bounded inventories and source-bound transport."""

import hashlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from genome_to_diffraction.hpc import raven_client, raven_readiness

COMMIT = "a" * 40
LOCK = b"unchanged locked environment\n"
PHENIX = b'{"phenix_version":"2.1-6048"}\n'


def _runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "project"
    runtime = root / "sources" / COMMIT
    binary = runtime / ".pixi/envs/hpc/bin/python"
    binary.parent.mkdir(parents=True)
    binary.write_text("existing Python executable")
    (runtime / "pixi.lock").write_bytes(LOCK)
    manifests = root / "software/manifests"
    manifests.mkdir(parents=True)
    (manifests / "phenix-2.1-6048-raven.json").write_bytes(PHENIX)
    monkeypatch.setattr(raven_readiness.socket, "gethostname", lambda: "raven03i")
    monkeypatch.setattr(raven_readiness.sys, "executable", str(binary))

    def git_probe(command, **kwargs):
        assert command == [
            "git",
            "-c",
            "core.fsmonitor=false",
            "-C",
            str(runtime),
            "rev-parse",
            "HEAD",
        ]
        assert kwargs["env"]["GIT_OPTIONAL_LOCKS"] == "0"
        return subprocess.CompletedProcess(command, 0, f"{COMMIT}\n", "")

    monkeypatch.setattr(raven_readiness.subprocess, "run", git_probe)
    return root


def _inspect(root: Path) -> dict[str, object]:
    return raven_readiness.inspect_project(
        root,
        COMMIT,
        hashlib.sha256(LOCK).hexdigest(),
        hashlib.sha256(PHENIX).hexdigest(),
    )


def test_raven_readiness_is_read_only_and_does_not_qualify_native_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _runtime(tmp_path, monkeypatch)
    databases = root / "databases"
    databases.mkdir()
    (databases / "database_manifest.json").write_text("not read as a database binding")
    (databases / "outside-link").symlink_to(tmp_path / "absent-secret")
    before = {str(path): path.lstat().st_mtime_ns for path in root.rglob("*")}

    result = _inspect(root)

    assert result["runtime_bindings_verified"] is True
    assert result["database_binding_verified"] is False
    assert result["native_qualification_verified"] is False
    inventories = result["manifest_directories"]
    assert isinstance(inventories, list)
    database = next(row for row in inventories if row["relative_path"] == "databases")
    assert database["state"] == "inspected"
    assert {row["kind"] for row in database["entries"]} == {"file", "symlink"}
    assert "not read as a database binding" not in json.dumps(result)
    assert {str(path): path.lstat().st_mtime_ns for path in root.rglob("*")} == before


@pytest.mark.parametrize("mutation", ("host", "lock", "phenix", "runtime_escape"))
def test_raven_readiness_rejects_changed_bindings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    root = _runtime(tmp_path, monkeypatch)
    if mutation == "host":
        monkeypatch.setattr(raven_readiness.socket, "gethostname", lambda: "other-site")
    elif mutation == "lock":
        (root / "sources" / COMMIT / "pixi.lock").write_text("changed")
    elif mutation == "phenix":
        (root / "software/manifests/phenix-2.1-6048-raven.json").write_text("changed")
    else:
        binary = root / "sources" / COMMIT / ".pixi/envs/hpc/bin/python"
        binary.unlink()
        outside = tmp_path / "outside-python"
        outside.write_text("not the qualified environment")
        binary.symlink_to(outside)
    with pytest.raises(ValueError):
        _inspect(root)


def test_raven_readiness_bounds_directory_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _runtime(tmp_path, monkeypatch)
    databases = root / "databases"
    databases.mkdir()
    for index in range(raven_readiness.MAX_DIRECTORY_ENTRIES + 1):
        (databases / str(index)).touch()
    with pytest.raises(ValueError, match="inspection bound"):
        _inspect(root)


def test_raven_readiness_does_not_follow_manifest_directory_symlinks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _runtime(tmp_path, monkeypatch)
    (root / "databases").symlink_to(tmp_path / "not-inspected")
    result = _inspect(root)
    inventories = result["manifest_directories"]
    assert isinstance(inventories, list)
    assert {
        "relative_path": "databases",
        "state": "symlink_not_followed",
        "entries": [],
    } in inventories


@pytest.mark.parametrize("changed_response", (False, True))
def test_raven_client_readiness_uses_only_committed_inspector_and_saved_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed_response: bool
) -> None:
    script = b"committed read-only inspection program"
    calls = []
    git = SimpleNamespace(
        ensure_clean=lambda: calls.append("clean"),
        resolve_commit=lambda revision: COMMIT,
        ensure_reachable_from_origin_main=lambda commit: calls.append(commit),
        read_file_at_commit=lambda commit, path: (
            LOCK if str(path) == "pixi.lock" else script
        ),
    )
    monkeypatch.setattr(raven_client, "SubprocessGitRepository", lambda repository: git)
    config = raven_client.RavenClientConfig(
        schema_version="1.0",
        ssh_alias="raven",
        remote_root=Path("/ptmp/test_user/nf-genome_to_diffraction"),
        local_state_root=tmp_path,
    )

    def run(command, **kwargs):
        calls.append(command)
        assert command[:6] == [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=15",
            "raven",
        ]
        assert "committed read-only inspection program" in command[6]
        assert (
            str(config.remote_root / "sources" / COMMIT / ".pixi/envs/hpc/bin/python")
            in command[6]
        )
        assert kwargs["timeout"] == 120
        payload = {
            "schema_version": "1.0",
            "operation": "readiness",
            "site_id": "raven",
            "root": str(config.remote_root),
            "runtime_source_commit": COMMIT,
            "pixi_lock_sha256": hashlib.sha256(LOCK).hexdigest(),
            "phenix_manifest_sha256": hashlib.sha256(PHENIX).hexdigest(),
            "runtime_bindings_verified": True,
            "database_binding_verified": False,
            "native_qualification_verified": changed_response,
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    monkeypatch.setattr(raven_client.subprocess, "run", run)
    if changed_response:
        with pytest.raises(ValueError, match="inconsistent scope"):
            raven_client.inspect_readiness(
                config, "HEAD", COMMIT, hashlib.sha256(PHENIX).hexdigest()
            )
    else:
        result = raven_client.inspect_readiness(
            config, "HEAD", COMMIT, hashlib.sha256(PHENIX).hexdigest()
        )
        assert result["inspection_source_commit"] == COMMIT
        assert result["inspection_script_sha256"] == hashlib.sha256(script).hexdigest()
    assert calls[:2] == ["clean", COMMIT]
