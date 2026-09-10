"""Read-only metadata inspection of the fixed Raven project setup.

The existing locked Python runs this committed, standard-library-only program.
It verifies the login host, runtime source/lock and saved Phenix-manifest binding,
then lists at most 128 immediate entries in each fixed manifest/resource directory.
It never installs, submits, follows inventory symlinks or reads biological data.
The timestamped JSON is inspection evidence, not native M6 qualification or a
selected database binding. There is no reusable scientific cache.
"""

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import socket
import stat
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

MAX_METADATA_BYTES = 8 * 1024**2
MAX_DIRECTORY_ENTRIES = 128
MANIFEST_DIRECTORIES = (
    "software/manifests",
    "manifests",
    "databases",
    "resources",
    "_config",
)


def _owned_directory(path: Path) -> None:
    record = path.lstat()
    if not stat.S_ISDIR(record.st_mode) or record.st_uid != os.getuid():
        raise ValueError(f"Raven directory is not owned and regular: {path}")


def _metadata_sha256(path: Path) -> str:
    record = path.lstat()
    if (
        not stat.S_ISREG(record.st_mode)
        or record.st_uid != os.getuid()
        or not 0 < record.st_size <= MAX_METADATA_BYTES
    ):
        raise ValueError(f"Raven metadata file is absent, unsafe or oversized: {path}")
    payload = path.read_bytes()
    if len(payload) != record.st_size:
        raise ValueError(f"Raven metadata changed during inspection: {path}")
    return hashlib.sha256(payload).hexdigest()


def _directory_inventory(root: Path, relative: str) -> dict[str, object]:
    path = root / relative
    try:
        record = path.lstat()
    except FileNotFoundError:
        return {"relative_path": relative, "state": "absent", "entries": []}
    if stat.S_ISLNK(record.st_mode):
        return {
            "relative_path": relative,
            "state": "symlink_not_followed",
            "entries": [],
        }
    _owned_directory(path)
    paths: list[Path] = []
    for item in path.iterdir():
        paths.append(item)
        if len(paths) > MAX_DIRECTORY_ENTRIES:
            raise ValueError(
                f"Raven manifest directory exceeds the inspection bound: {relative}"
            )
    entries: list[dict[str, object]] = []
    for item in sorted(paths):
        item_stat = item.lstat()
        kind = (
            "file"
            if stat.S_ISREG(item_stat.st_mode)
            else "directory"
            if stat.S_ISDIR(item_stat.st_mode)
            else "symlink"
            if stat.S_ISLNK(item_stat.st_mode)
            else "other"
        )
        entries.append(
            {"name": item.name, "kind": kind, "size_bytes": item_stat.st_size}
        )
    return {"relative_path": relative, "state": "inspected", "entries": entries}


def inspect_project(
    root: Path,
    runtime_source_commit: str,
    expected_lock_sha256: str,
    expected_phenix_sha256: str,
) -> dict[str, object]:
    """Verify saved bindings and inventory only the fixed immediate directories."""

    if re.fullmatch(r"[a-f0-9]{40}", runtime_source_commit) is None or any(
        re.fullmatch(r"[a-f0-9]{64}", value) is None
        for value in (expected_lock_sha256, expected_phenix_sha256)
    ):
        raise ValueError("Raven readiness requires exact source and metadata digests")
    host = socket.gethostname().split(".")[0]
    if host not in {
        f"raven{i:02d}{suffix}" for i in range(1, 5) for suffix in ("", "i")
    }:
        raise ValueError("Raven readiness requires an explicit Raven login node")
    if sys.version_info[:2] != (3, 14):
        raise ValueError("Raven readiness requires the existing Python 3.14 runtime")
    _owned_directory(root)
    runtime_root = root / "sources" / runtime_source_commit
    _owned_directory(runtime_root)
    if not runtime_root.resolve().is_relative_to(root.resolve()):
        raise ValueError("Raven runtime source escaped the fixed project root")
    runtime_python = runtime_root / ".pixi/envs/hpc/bin/python"
    if (
        not runtime_python.resolve(strict=True).is_relative_to(root.resolve())
        or Path(sys.executable).resolve() != runtime_python.resolve()
    ):
        raise ValueError("Raven readiness did not use the bound existing Python")
    environment = os.environ.copy()
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    git = subprocess.run(
        [
            "git",
            "-c",
            "core.fsmonitor=false",
            "-C",
            str(runtime_root),
            "rev-parse",
            "HEAD",
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
        env=environment,
    )
    if git.stdout.strip() != runtime_source_commit:
        raise ValueError("Raven runtime source commit changed")
    lock_sha256 = _metadata_sha256(runtime_root / "pixi.lock")
    if lock_sha256 != expected_lock_sha256:
        raise ValueError("Raven existing environment lock differs from the test source")
    phenix = root / "software/manifests/phenix-2.1-6048-raven.json"
    phenix_sha256 = _metadata_sha256(phenix)
    if phenix_sha256 != expected_phenix_sha256:
        raise ValueError("Raven saved Phenix manifest binding changed")
    return {
        "schema_version": "1.0",
        "operation": "readiness",
        "site_id": "raven",
        "observed_at": datetime.now(UTC).isoformat(),
        "login_host": host,
        "root": str(root),
        "runtime_source_commit": runtime_source_commit,
        "pixi_lock_sha256": lock_sha256,
        "phenix_manifest_sha256": phenix_sha256,
        "python_version": sys.version.split()[0],
        "package_versions": {
            name: importlib.metadata.version(name) for name in ("gemmi", "pydantic")
        },
        "runtime_bindings_verified": True,
        "database_binding_verified": False,
        "native_qualification_verified": False,
        "manifest_directories": [
            _directory_inventory(root, name) for name in MANIFEST_DIRECTORIES
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--runtime-source-commit", required=True)
    parser.add_argument("--pixi-lock-sha256", required=True)
    parser.add_argument("--phenix-manifest-sha256", required=True)
    args = parser.parse_args()
    username = os.environ.get("USER", "")
    if (
        re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", username) is None
        or args.root != Path("/ptmp") / username / "nf-genome_to_diffraction"
    ):
        raise ValueError("Raven readiness root differs from the authenticated account")
    print(
        json.dumps(
            inspect_project(
                args.root,
                args.runtime_source_commit,
                args.pixi_lock_sha256,
                args.phenix_manifest_sha256,
            ),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
