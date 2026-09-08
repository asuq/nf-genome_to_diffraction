"""Local fixed-command transport for owned Raven identification controllers."""

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tarfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.hpc.client import _extract_approved_archive
from genome_to_diffraction.hpc.raven_identification import (
    MAX_COLLECT_BYTES,
    RUN_PATTERN,
    launch_profile,
    parse_launch,
)


class RavenClientConfig(BaseModel):
    """One explicit Raven account and local state directory, not run ownership."""

    model_config = ConfigDict(extra="forbid")
    schema_version: str
    ssh_alias: str
    remote_root: Path
    local_state_root: Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "operation", choices=("start", "status", "logs", "collect", "cancel")
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--tail", type=int, default=200)
    args = parser.parse_args()
    if (
        args.config.is_symlink()
        or args.config.stat().st_uid != os.getuid()
        or args.config.stat().st_mode & 0o777 != 0o600
    ):
        raise ValueError("Raven client configuration must be an owned mode-0600 file")
    config = RavenClientConfig.model_validate_json(args.config.read_text())
    if (
        config.schema_version != "1.0"
        or config.ssh_alias != "raven"
        or re.fullmatch(
            r"/ptmp/[A-Za-z0-9._-]+/nf-genome_to_diffraction", str(config.remote_root)
        )
        is None
        or not config.local_state_root.is_absolute()
        or re.fullmatch(RUN_PATTERN, args.run_id) is None
        or not 1 <= args.tail <= 2000
    ):
        raise ValueError("invalid fixed Raven configuration or run identifier")
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
    spec = parse_launch(record_path.read_text())
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
            "profile": launch_profile(spec),
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
        if handle is None or parse_launch(handle.read()) != spec:
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
