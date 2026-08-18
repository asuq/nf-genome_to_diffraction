"""Regression tests for writable M6 stub fixture outputs."""

import hashlib
import os
import shutil
import stat
import subprocess
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
COPY_HELPER = REPOSITORY / "tests/scripts/copy_stub_fixture.sh"
M6_MODULES = (
    REPOSITORY / "modules/local/m6_nextflow_tasks.nf",
    REPOSITORY / "modules/local/m6_truthless_cache_tasks.nf",
)


def _file_digests(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _directory_names(root: Path) -> set[str]:
    return {str(path.relative_to(root)) for path in root.rglob("*") if path.is_dir()}


def test_copy_stub_fixture_repairs_hardened_modes_and_allows_cleanup(
    tmp_path: Path,
) -> None:
    source = tmp_path / "read-only fixture"
    nested = source / "nested"
    empty = source / ".empty"
    nested.mkdir(parents=True)
    empty.mkdir()
    (source / ".hidden").write_bytes(b"hidden\n")
    (nested / "data.json").write_bytes(b'{"value": 1}\n')
    executable = nested / "fixture-tool"
    executable.write_bytes(b"#!/usr/bin/env bash\nexit 0\n")

    os.chmod(source / ".hidden", 0o400)
    os.chmod(nested / "data.json", 0o400)
    os.chmod(executable, 0o500)
    os.chmod(nested, 0o500)
    os.chmod(empty, 0o500)
    os.chmod(source, 0o500)
    expected_files = _file_digests(source)
    expected_directories = _directory_names(source)
    output = tmp_path / "copied output"
    hardened_helper = tmp_path / "copy_stub_fixture.sh"
    shutil.copy2(COPY_HELPER, hardened_helper)
    hardened_helper.chmod(0o400)

    try:
        result = subprocess.run(
            ["/bin/bash", str(hardened_helper), str(source), str(output)],
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr
        assert _file_digests(output) == expected_files
        assert _directory_names(output) == expected_directories
        for directory in (
            output,
            *(path for path in output.rglob("*") if path.is_dir()),
        ):
            mode = stat.S_IMODE(directory.stat().st_mode)
            assert mode & stat.S_IWUSR
            assert mode & stat.S_IXUSR
        for file_path in (path for path in output.rglob("*") if path.is_file()):
            assert stat.S_IMODE(file_path.stat().st_mode) & stat.S_IWUSR
        assert stat.S_IMODE((output / "nested/fixture-tool").stat().st_mode) & (
            stat.S_IXUSR
        )
        assert not stat.S_IMODE((source / "nested/data.json").stat().st_mode) & (
            stat.S_IWUSR
        )

        shutil.rmtree(output)
        assert not output.exists()
    finally:
        for path in (source, *source.rglob("*")):
            os.chmod(path, 0o700 if path.is_dir() else 0o600)


def test_every_m6_directory_copy_stub_uses_the_writable_copy_helper() -> None:
    modules = tuple(path.read_text(encoding="utf-8") for path in M6_MODULES)
    stub_blocks = tuple(
        block for module in modules for block in module.split("\n    stub:\n")[1:]
    )

    assert len(stub_blocks) == 20
    assert all("cp -R" not in module for module in modules)
    assert (
        sum(module.count("tests/scripts/copy_stub_fixture.sh") for module in modules)
        == 21
    )
    hardened_invocation = "/bin/bash '${projectDir}/tests/scripts/copy_stub_fixture.sh'"
    assert sum(module.count(hardened_invocation) for module in modules) == 21
    for block in stub_blocks:
        stub = block.split("\n}\n", maxsplit=1)[0]
        assert "tests/scripts/copy_stub_fixture.sh" in stub


def test_copy_failure_repairs_partial_output_for_nextflow_cleanup(
    tmp_path: Path,
) -> None:
    source = tmp_path / "fixture"
    source.mkdir()
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_cp = fake_bin / "cp"
    fake_cp.write_text(
        "#!/usr/bin/env bash\n"
        "set -eu\n"
        'destination="${3%/}"\n'
        'mkdir "$destination/partial"\n'
        'touch "$destination/partial/file"\n'
        'chmod 0400 "$destination/partial/file"\n'
        'chmod 0500 "$destination/partial"\n'
        "exit 7\n",
        encoding="utf-8",
    )
    fake_cp.chmod(0o700)
    output = tmp_path / "partial output"
    environment = dict(os.environ)
    environment["PATH"] = f"{fake_bin}:{environment['PATH']}"

    result = subprocess.run(
        ["/bin/bash", str(COPY_HELPER), str(source), str(output)],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.returncode == 7
    assert stat.S_IMODE((output / "partial").stat().st_mode) & stat.S_IWUSR
    assert stat.S_IMODE((output / "partial/file").stat().st_mode) & stat.S_IWUSR
    shutil.rmtree(output)
    assert not output.exists()
