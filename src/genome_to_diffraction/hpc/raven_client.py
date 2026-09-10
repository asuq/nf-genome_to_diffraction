"""Local fixed-command transport for owned Raven identification controllers."""

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tarfile
from pathlib import Path, PurePosixPath
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.hpc.client import (
    SubprocessGitRepository,
    _extract_approved_archive,
)
from genome_to_diffraction.hpc.raven_identification import (
    MAX_COLLECT_BYTES,
    RUN_PATTERN,
    RavenLaunch,
)


class RavenClientConfig(BaseModel):
    """One explicit Raven account and local state directory, not run ownership."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"]
    ssh_alias: Literal["raven"]
    remote_root: Path
    local_state_root: Path

    @model_validator(mode="after")
    def _fixed_paths(self) -> Self:
        if (
            re.fullmatch(
                r"/ptmp/[A-Za-z0-9][A-Za-z0-9._-]*/nf-genome_to_diffraction",
                str(self.remote_root),
            )
            is None
            or not self.local_state_root.is_absolute()
        ):
            raise ValueError("Raven client paths are outside the fixed site contract")
        return self


def inspect_readiness(
    config: RavenClientConfig,
    revision: str,
    runtime_source_commit: str,
    phenix_manifest_sha256: str,
) -> dict[str, object]:
    """Run only the committed read-only inspector in the existing Raven runtime."""

    if (
        re.fullmatch(r"[a-f0-9]{40}", runtime_source_commit) is None
        or re.fullmatch(r"[a-f0-9]{64}", phenix_manifest_sha256) is None
    ):
        raise ValueError("Raven readiness requires exact runtime and Phenix bindings")
    repository = Path(__file__).resolve().parents[3]
    git = SubprocessGitRepository(repository)
    git.ensure_clean()
    commit = git.resolve_commit(revision)
    git.ensure_reachable_from_origin_main(commit)
    script = git.read_file_at_commit(
        commit, PurePosixPath("src/genome_to_diffraction/hpc/raven_readiness.py")
    )
    if len(script) > 65536:
        raise ValueError("Raven readiness program exceeds its command-size bound")
    lock_sha256 = hashlib.sha256(
        git.read_file_at_commit(commit, PurePosixPath("pixi.lock"))
    ).hexdigest()
    python = (
        config.remote_root
        / "sources"
        / runtime_source_commit
        / ".pixi/envs/hpc/bin/python"
    )
    remote = [
        "env",
        "PYTHONDONTWRITEBYTECODE=1",
        str(python),
        "-c",
        script.decode("utf-8"),
        "--root",
        str(config.remote_root),
        "--runtime-source-commit",
        runtime_source_commit,
        "--pixi-lock-sha256",
        lock_sha256,
        "--phenix-manifest-sha256",
        phenix_manifest_sha256,
    ]
    result = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=15",
            config.ssh_alias,
            shlex.join(remote),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if result.returncode:
        raise RuntimeError(f"Raven readiness failed: {result.stderr[-2000:]}")
    if len(result.stdout.encode("utf-8")) > 2 * 1024**2:
        raise ValueError("Raven readiness response exceeds its output bound")
    payload = json.loads(result.stdout)
    expected = {
        "schema_version": "1.0",
        "operation": "readiness",
        "site_id": "raven",
        "root": str(config.remote_root),
        "runtime_source_commit": runtime_source_commit,
        "pixi_lock_sha256": lock_sha256,
        "phenix_manifest_sha256": phenix_manifest_sha256,
    }
    if (
        not isinstance(payload, dict)
        or any(payload.get(key) != value for key, value in expected.items())
        or (
            payload.get("runtime_bindings_verified") is not True
            or payload.get("database_binding_verified") is not False
            or payload.get("native_qualification_verified") is not False
        )
    ):
        raise ValueError(
            "Raven readiness returned inconsistent scope or runtime evidence"
        )
    return {
        **payload,
        "inspection_source_commit": commit,
        "inspection_script_sha256": hashlib.sha256(script).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "operation",
        choices=("start", "status", "logs", "collect", "cancel", "readiness"),
    )
    parser.add_argument("--run-id")
    parser.add_argument("--tail", type=int, default=200)
    parser.add_argument("--revision")
    parser.add_argument("--runtime-source-commit")
    parser.add_argument("--phenix-manifest-sha256")
    args = parser.parse_args()
    if (
        args.config.is_symlink()
        or args.config.stat().st_uid != os.getuid()
        or args.config.stat().st_mode & 0o777 != 0o600
    ):
        raise ValueError("Raven client configuration must be an owned mode-0600 file")
    config = RavenClientConfig.model_validate_json(args.config.read_text())
    if not 1 <= args.tail <= 2000:
        raise ValueError("Raven log tail is outside its fixed bound")
    if args.operation == "readiness":
        if args.run_id is not None or not all(
            (args.revision, args.runtime_source_commit, args.phenix_manifest_sha256)
        ):
            parser.error(
                "readiness requires revision/runtime/Phenix bindings and no run ID"
            )
        print(
            json.dumps(
                inspect_readiness(
                    config,
                    args.revision,
                    args.runtime_source_commit,
                    args.phenix_manifest_sha256,
                ),
                sort_keys=True,
            )
        )
        return 0
    if (
        args.run_id is None
        or re.fullmatch(RUN_PATTERN, args.run_id) is None
        or any((args.revision, args.runtime_source_commit, args.phenix_manifest_sha256))
    ):
        parser.error(
            "owned run operations require one valid run ID and no readiness bindings"
        )
    local_run = config.local_state_root / args.run_id
    record_path = local_run / "run.json"
    if (
        local_run.is_symlink()
        or not local_run.resolve().is_relative_to(config.local_state_root.resolve())
        or record_path.is_symlink()
        or not record_path.is_file()
        or record_path.stat().st_uid != os.getuid()
        or record_path.stat().st_size > 65536
    ):
        raise ValueError("local Raven ownership record is absent or unsafe")
    spec = RavenLaunch.model_validate_json(record_path.read_text())
    if (
        spec.run_id != args.run_id
        or spec.source_root != config.remote_root / "sources" / spec.source_commit
    ):
        raise ValueError("local Raven run and source ownership differ")
    remote_run = config.remote_root / "runs" / spec.run_id
    remote_command = [
        "bash",
        "-l",
        str(spec.source_root / "bootstrap/nf-gtd-raven-dispatch"),
        args.operation,
        "--run-dir",
        str(remote_run),
        "--owner",
        spec.owner_id,
    ]
    if args.operation == "logs":
        remote_command.extend(("--tail", str(args.tail)))
    command = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=15",
        config.ssh_alias,
        shlex.join(remote_command),
    ]
    if args.operation != "collect":
        result = subprocess.run(command, check=False, capture_output=True, timeout=120)
        if result.returncode:
            sys.stderr.buffer.write(result.stderr)
            return result.returncode
        payload = json.loads(result.stdout)
        expected = {
            "run_id": spec.run_id,
            "site_id": "raven",
            "profile": "identification-screen",
            "owner_id": spec.owner_id,
            "source_commit": spec.source_commit,
            "input_id": spec.input_id,
        }
        if any(payload.get(key) != value for key, value in expected.items()):
            raise ValueError(
                "remote Raven response belongs to another run/site/source/input"
            )
        print(json.dumps(payload, sort_keys=True))
        return 0
    archive_path = local_run / "collection.tar.gz"
    with archive_path.open("xb") as output:
        result = subprocess.run(
            command, check=False, stdout=output, stderr=subprocess.PIPE, timeout=3600
        )
    if result.returncode:
        sys.stderr.buffer.write(result.stderr)
        return result.returncode
    if archive_path.stat().st_size > MAX_COLLECT_BYTES:
        raise ValueError("Raven collection exceeds the local byte bound")
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        names = [m.name for m in members]
        if len(names) != len(set(names)) or len(names) > 30000:
            raise ValueError(
                "Raven collection duplicates or exceeds its file inventory"
            )
        launch = archive.getmember("launch.json")
        if not launch.isfile() or launch.size > 65536:
            raise ValueError("Raven collection lacks bounded source ownership")
        handle = archive.extractfile(launch)
        if handle is None or RavenLaunch.model_validate_json(handle.read()) != spec:
            raise ValueError("Raven collection source/input/owner differs")
    destination = local_run / "collected"
    if destination.exists():
        raise ValueError("Raven collection destination already exists")
    names = _extract_approved_archive(archive_path, destination, progress=False)
    print(
        json.dumps(
            {
                "run_id": spec.run_id,
                "site_id": "raven",
                "operation": "collect",
                "archive_sha256": sha256_file(archive_path),
                "file_count": len(names),
                "collected_root": str(destination),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
