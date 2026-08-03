"""Tests for scoped database storage accounting and process-group shutdown."""

import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

import genome_to_diffraction.databases.common as common_module
from genome_to_diffraction.databases.common import (
    DatabaseError,
    ScratchLimitError,
    StorageLimitError,
    StorageWatchdogError,
    run_command,
    tree_size,
)


def _run(
    root: Path,
    write_root: Path,
    code: str,
    *,
    limit: int = 10_000_000,
    interval: float = 0.02,
    arguments: tuple[str, ...] = (),
) -> None:
    run_command(
        [sys.executable, "-c", code, *arguments],
        log_path=root / "logs" / "command.log",
        storage_root=root,
        write_roots=(write_root,),
        storage_limit_bytes=limit,
        minimum_free_bytes=0,
        progress=False,
        watchdog_interval_seconds=interval,
    )


def test_tree_size_ignores_symlinks_and_counts_regular_files(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "one").write_bytes(b"123")
    (tmp_path / "two").write_bytes(b"4567")
    (tmp_path / "link").symlink_to(nested / "one")
    assert tree_size(tmp_path) == 7


def test_watchdog_scans_only_active_roots_between_reconciliations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_root = tmp_path / "active"
    write_root.mkdir()
    original = common_module.tree_size
    calls: list[Path] = []

    def record(root: Path) -> int:
        calls.append(root)
        return original(root)

    monkeypatch.setattr(common_module, "tree_size", record)
    _run(
        tmp_path,
        write_root,
        "import time; time.sleep(0.12)",
    )

    assert calls.count(tmp_path) == 2
    assert calls.count(write_root.resolve()) >= 2


def test_watchdog_stops_process_group_at_storage_limit(tmp_path: Path) -> None:
    write_root = tmp_path / "active"
    write_root.mkdir()
    writer = (
        "import pathlib,sys,time\n"
        "p=pathlib.Path(sys.argv[1])\n"
        "for _ in range(40):\n"
        "    with p.open('ab') as handle: handle.write(b'x'*256)\n"
        "    time.sleep(0.03)\n"
    )
    with pytest.raises(StorageLimitError, match="project cap or free-space"):
        _run(
            tmp_path,
            write_root,
            writer,
            limit=1024,
            arguments=(str(write_root / "growing.bin"),),
        )

    size_after = (write_root / "growing.bin").stat().st_size
    time.sleep(0.15)
    assert (write_root / "growing.bin").stat().st_size == size_after


def test_watchdog_scan_error_has_distinct_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_root = tmp_path / "active"
    write_root.mkdir()
    original = common_module.tree_size
    calls = 0

    def fail_during_watch(root: Path) -> int:
        nonlocal calls
        calls += 1
        if calls >= 3 and root == write_root.resolve():
            raise OSError("injected NFS scan failure")
        return original(root)

    monkeypatch.setattr(common_module, "tree_size", fail_during_watch)
    with pytest.raises(StorageWatchdogError, match="injected NFS scan failure"):
        _run(tmp_path, write_root, "import time; time.sleep(2)")


def test_process_group_includes_child_writer(tmp_path: Path) -> None:
    write_root = tmp_path / "active"
    write_root.mkdir()
    child_code = (
        "import pathlib,sys,time\n"
        "p=pathlib.Path(sys.argv[1])\n"
        "for _ in range(80):\n"
        "    with p.open('ab') as handle: handle.write(b'x'*256)\n"
        "    time.sleep(0.03)\n"
    )
    parent_code = (
        "import subprocess,sys,time; "
        "subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2]]); "
        "time.sleep(5)"
    )
    output = write_root / "child.bin"
    with pytest.raises(StorageLimitError):
        _run(
            tmp_path,
            write_root,
            parent_code,
            limit=1024,
            arguments=(child_code, str(output)),
        )
    size_after = output.stat().st_size
    time.sleep(0.15)
    assert output.stat().st_size == size_after


def test_write_root_symlink_is_rejected(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(real, target_is_directory=True)
    with pytest.raises(DatabaseError, match="write root is unsafe"):
        _run(tmp_path, linked, "raise AssertionError('must not execute')")


def test_free_space_headroom_is_checked_before_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_root = tmp_path / "active"
    write_root.mkdir()

    @dataclass(frozen=True)
    class Usage:
        total: int
        used: int
        free: int

    monkeypatch.setattr(
        "genome_to_diffraction.databases.common.shutil.disk_usage",
        lambda _: Usage(100, 100, 0),
    )
    with pytest.raises(StorageLimitError, match="free bytes"):
        run_command(
            [sys.executable, "-c", "raise AssertionError('must not execute')"],
            log_path=tmp_path / "logs" / "headroom.log",
            storage_root=tmp_path,
            write_roots=(write_root,),
            storage_limit_bytes=10_000,
            minimum_free_bytes=1,
            progress=False,
        )


def test_scratch_headroom_is_checked_before_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = tmp_path / "storage"
    scratch = tmp_path / "scratch"
    active = storage / "active"
    active.mkdir(parents=True)
    scratch.mkdir()
    marker = tmp_path / "must-not-run"

    @dataclass(frozen=True)
    class Usage:
        total: int
        used: int
        free: int

    monkeypatch.setattr(
        common_module,
        "_device_id",
        lambda path: 2 if path == scratch else 1,
    )
    monkeypatch.setattr(
        "genome_to_diffraction.databases.common.shutil.disk_usage",
        lambda path: Usage(100, 100, 0) if path == scratch else Usage(100, 0, 100),
    )
    with pytest.raises(ScratchLimitError, match="database scratch has 0 free bytes"):
        run_command(
            [
                sys.executable,
                "-c",
                "import pathlib,sys; pathlib.Path(sys.argv[1]).touch()",
                str(marker),
            ],
            log_path=storage / "logs" / "scratch-headroom.log",
            storage_root=storage,
            write_roots=(active,),
            storage_limit_bytes=10_000,
            minimum_free_bytes=0,
            progress=False,
            scratch_roots=(scratch,),
            minimum_scratch_free_bytes=1,
        )
    assert not marker.exists()


def test_scratch_watchdog_stops_process_when_headroom_drops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = tmp_path / "storage"
    scratch = tmp_path / "scratch"
    active = storage / "active"
    active.mkdir(parents=True)
    scratch.mkdir()
    scratch_checks = 0

    @dataclass(frozen=True)
    class Usage:
        total: int
        used: int
        free: int

    monkeypatch.setattr(
        common_module,
        "_device_id",
        lambda path: 2 if path == scratch else 1,
    )

    def disk_usage(path: Path) -> Usage:
        nonlocal scratch_checks
        if path == scratch:
            scratch_checks += 1
            return Usage(100, 100, 0) if scratch_checks >= 2 else Usage(100, 0, 100)
        return Usage(100, 0, 100)

    monkeypatch.setattr(
        "genome_to_diffraction.databases.common.shutil.disk_usage", disk_usage
    )
    with pytest.raises(ScratchLimitError, match="scratch free-space headroom"):
        run_command(
            [sys.executable, "-c", "import time; time.sleep(2)"],
            log_path=storage / "logs" / "scratch-watchdog.log",
            storage_root=storage,
            write_roots=(active,),
            storage_limit_bytes=10_000,
            minimum_free_bytes=0,
            progress=False,
            scratch_roots=(scratch,),
            minimum_scratch_free_bytes=1,
            watchdog_interval_seconds=0.02,
        )
