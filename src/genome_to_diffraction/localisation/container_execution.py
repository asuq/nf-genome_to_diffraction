"""Capture and authenticate fixed offline localisation container executions.

The capture command invokes only the local Docker CLI. It records the raw
container and image inspection JSON, exact effective command, network mode,
terminal exit status, input FASTA, output, and container-log checksums for the
fixed PSORTb and DeepTMHMM images. The resulting portable directory is consumed
by the batch importer; caller-authored version/network strings are not accepted.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Literal, Self

from pydantic import Field, ValidationError, model_validator

from genome_to_diffraction.checksums import (
    atomic_write_bytes,
    atomic_write_json,
    sha256_file,
)
from genome_to_diffraction.schemas.base import NonEmptyString, Sha256Hex
from genome_to_diffraction.schemas.v2.composition import _ContentAddressedContract
from genome_to_diffraction.status import InputContractError

LOCALISATION_BATCH_ADAPTER_VERSION = "container-localisation-batch-v3-inspected"
PSORTB_IMAGE_REFERENCE = (
    "docker.io/brinkmanlab/psortb_commandline@"
    "sha256:5fd2243b7ed4470e2d5ad521c6f32fcd254d1579600bb1537cbe6322a2181040"
)
PSORTB_IMAGE_MANIFEST_SHA256 = (
    "5fd2243b7ed4470e2d5ad521c6f32fcd254d1579600bb1537cbe6322a2181040"
)
DEEPTMHMM_IMAGE_REFERENCE = (
    "docker.io/deeptmhmm/deeptmhmm@"
    "sha256:e527883fd2114007c6208c3d764fece40016cc95e209eab93016644c3e7ccb16"
)
DEEPTMHMM_IMAGE_MANIFEST_SHA256 = (
    "e527883fd2114007c6208c3d764fece40016cc95e209eab93016644c3e7ccb16"
)
_MANIFEST_NAME = "localisation_container_execution.json"
_PSORTB_LOG_NAME = "psortb-container.log"
_DEEPTMHMM_LOG_NAME = "deeptmhmm-container.log"


class LocalisationContainerExecutionError(InputContractError):
    """Container execution evidence is absent, unsafe, or inconsistent."""


class LocalisationContainerToolExecution(_ContentAddressedContract):
    """Raw Docker evidence for one fixed terminal tool invocation."""

    _identity_field: ClassVar[str] = "execution_id"
    _identity_prefix: ClassVar[str] = "localcontainerexec_"

    schema_version: Literal["2.0"]
    execution_id: NonEmptyString
    tool: Literal["psortb", "deeptmhmm"]
    tool_version: NonEmptyString
    container_id: Sha256Hex
    image_reference: NonEmptyString
    image_manifest_sha256: Sha256Hex
    image_id: NonEmptyString
    platform: Literal["linux/amd64"]
    docker_engine_version: NonEmptyString
    container_inspect_json: NonEmptyString
    container_inspect_sha256: Sha256Hex
    image_inspect_json: NonEmptyString
    image_inspect_sha256: Sha256Hex
    effective_command: tuple[NonEmptyString, ...] = Field(min_length=2)
    working_directory: NonEmptyString
    network_mode: Literal["none"]
    terminal_status: Literal["exited"]
    exit_code: Literal[0]
    input_container_path: Literal["/input.faa"]
    input_fasta_sha256: Sha256Hex
    input_fasta_size_bytes: int = Field(gt=0)
    output_container_path: NonEmptyString
    raw_output_sha256: Sha256Hex
    raw_output_size_bytes: int = Field(gt=0)
    log_path: Literal["psortb-container.log", "deeptmhmm-container.log"]
    log_sha256: Sha256Hex
    log_size_bytes: int = Field(ge=0)
    explicit_failed_source_ids: tuple[NonEmptyString, ...] = ()
    provenance_source: Literal["docker_cli_inspect_copy_logs_v1"] = (
        "docker_cli_inspect_copy_logs_v1"
    )

    @model_validator(mode="after")
    def _validate_inspection(self) -> Self:
        if (
            hashlib.sha256(self.container_inspect_json.encode("utf-8")).hexdigest()
            != self.container_inspect_sha256
            or hashlib.sha256(self.image_inspect_json.encode("utf-8")).hexdigest()
            != self.image_inspect_sha256
        ):
            raise ValueError("container inspection bytes changed")
        try:
            container_docs = json.loads(self.container_inspect_json)
            image_docs = json.loads(self.image_inspect_json)
        except json.JSONDecodeError as error:
            raise ValueError("container inspection JSON is invalid") from error
        if (
            not isinstance(container_docs, list)
            or len(container_docs) != 1
            or not isinstance(container_docs[0], dict)
            or not isinstance(image_docs, list)
            or len(image_docs) != 1
            or not isinstance(image_docs[0], dict)
        ):
            raise ValueError("container inspection cardinality differs")
        container = container_docs[0]
        image = image_docs[0]
        state = container.get("State")
        config = container.get("Config")
        host = container.get("HostConfig")
        if not all(isinstance(item, dict) for item in (state, config, host)):
            raise ValueError("container inspection fields are absent")
        assert isinstance(state, dict)
        assert isinstance(config, dict)
        assert isinstance(host, dict)
        identifier = container.get("Id")
        image_id = container.get("Image")
        path = container.get("Path")
        arguments = container.get("Args")
        command = (
            tuple([path, *arguments])
            if isinstance(path, str)
            and isinstance(arguments, list)
            and all(isinstance(value, str) for value in arguments)
            else ()
        )
        repo_digests = image.get("RepoDigests")
        expected_reference, expected_digest, expected_version = _fixed_tool(self.tool)
        if (
            identifier != self.container_id
            or image_id != self.image_id
            or config.get("Image")
            not in {expected_reference, expected_reference.removeprefix("docker.io/")}
            or host.get("NetworkMode") != "none"
            or state.get("Status") != "exited"
            or state.get("Running") is not False
            or state.get("ExitCode") != 0
            or command != self.effective_command
            or config.get("WorkingDir") != self.working_directory
            or self.image_reference != expected_reference
            or self.image_manifest_sha256 != expected_digest
            or self.tool_version != expected_version
            or image.get("Os") != "linux"
            or image.get("Architecture") != "amd64"
            or not isinstance(repo_digests, list)
            or not any(
                isinstance(value, str) and value.endswith(f"@sha256:{expected_digest}")
                for value in repo_digests
            )
        ):
            raise ValueError("container execution differs from the fixed runtime")
        if self.tool == "psortb":
            if (
                self.effective_command[1:]
                != (
                    "-a",
                    "-o",
                    "terse",
                    "-i",
                    "/input.faa",
                )
                or self.log_path != _PSORTB_LOG_NAME
            ):
                raise ValueError("PSORTb effective command differs")
        elif (
            self.effective_command
            not in {
                ("python3", "predict.py", "--fasta", "/input.faa"),
                ("/usr/local/bin/python3", "predict.py", "--fasta", "/input.faa"),
            }
            or self.working_directory != "/openprotein"
            or self.log_path != _DEEPTMHMM_LOG_NAME
        ):
            raise ValueError("DeepTMHMM effective command differs")
        if (
            tuple(sorted(set(self.explicit_failed_source_ids)))
            != self.explicit_failed_source_ids
        ):
            raise ValueError("explicit failed source IDs are not canonical")
        return self


class LocalisationBatchExecutionManifest(_ContentAddressedContract):
    """Both successful fixed container executions over one exact FASTA."""

    _identity_field: ClassVar[str] = "manifest_id"
    _identity_prefix: ClassVar[str] = "localcontainermanifest_"

    schema_version: Literal["2.0"]
    adapter_version: Literal["container-localisation-batch-v3-inspected"] = (
        LOCALISATION_BATCH_ADAPTER_VERSION
    )
    manifest_id: NonEmptyString
    source_fasta_sha256: Sha256Hex
    source_fasta_size_bytes: int = Field(gt=0)
    psortb: LocalisationContainerToolExecution
    deeptmhmm: LocalisationContainerToolExecution

    @model_validator(mode="after")
    def _validate_pair(self) -> Self:
        if (
            self.psortb.tool != "psortb"
            or self.deeptmhmm.tool != "deeptmhmm"
            or self.psortb.input_fasta_sha256 != self.source_fasta_sha256
            or self.deeptmhmm.input_fasta_sha256 != self.source_fasta_sha256
            or self.psortb.input_fasta_size_bytes != self.source_fasta_size_bytes
            or self.deeptmhmm.input_fasta_size_bytes != self.source_fasta_size_bytes
            or self.psortb.docker_engine_version != self.deeptmhmm.docker_engine_version
        ):
            raise ValueError("localisation container executions use different inputs")
        return self


@dataclass(frozen=True, slots=True)
class LocalisationContainerCaptureRequest:
    """Local Docker objects and copied outputs to authenticate."""

    catalogue_fasta: Path
    psortb_container: str
    psortb_output_container_path: str
    psortb_output: Path
    deeptmhmm_container: str
    deeptmhmm_output_container_path: str
    deeptmhmm_output: Path
    output_directory: Path


def _fixed_tool(tool: str) -> tuple[str, str, str]:
    if tool == "psortb":
        return PSORTB_IMAGE_REFERENCE, PSORTB_IMAGE_MANIFEST_SHA256, "3.0.6"
    return DEEPTMHMM_IMAGE_REFERENCE, DEEPTMHMM_IMAGE_MANIFEST_SHA256, "1.0"


def _docker(*arguments: str) -> bytes:
    try:
        completed = subprocess.run(
            ["docker", *arguments],
            check=False,
            capture_output=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise LocalisationContainerExecutionError(
            "Docker evidence command failed"
        ) from error
    if completed.returncode != 0:
        raise LocalisationContainerExecutionError(
            "Docker evidence command returned nonzero"
        )
    return completed.stdout


def _docker_logs(container_name: str) -> bytes:
    try:
        completed = subprocess.run(
            ["docker", "logs", container_name],
            check=False,
            capture_output=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise LocalisationContainerExecutionError(
            "Docker log capture failed"
        ) from error
    if completed.returncode != 0:
        raise LocalisationContainerExecutionError("Docker log capture returned nonzero")
    return completed.stdout + completed.stderr


def _capture_tool(
    *,
    tool: Literal["psortb", "deeptmhmm"],
    container_name: str,
    output_container_path: str,
    host_fasta: Path,
    host_output: Path,
    docker_version: str,
    output_directory: Path,
) -> LocalisationContainerToolExecution:
    container_inspect = _docker("container", "inspect", container_name).decode("utf-8")
    try:
        container = json.loads(container_inspect)[0]
        image_reference = container["Config"]["Image"]
        image_id = container["Image"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
        raise LocalisationContainerExecutionError(
            "Docker container inspection is incomplete"
        ) from error
    image_inspect = _docker("image", "inspect", image_reference).decode("utf-8")
    log_bytes = _docker_logs(container_name)
    log_name = _PSORTB_LOG_NAME if tool == "psortb" else _DEEPTMHMM_LOG_NAME
    atomic_write_bytes(output_directory / log_name, log_bytes)
    with tempfile.TemporaryDirectory(
        prefix="nf-gtd-localisation-capture-", dir="/tmp"
    ) as temporary:
        copied_input = Path(temporary) / "input.faa"
        copied_output = Path(temporary) / "output.raw"
        _docker("cp", f"{container_name}:/input.faa", str(copied_input))
        _docker("cp", f"{container_name}:{output_container_path}", str(copied_output))
        if copied_input.read_bytes() != host_fasta.read_bytes():
            raise LocalisationContainerExecutionError(
                f"{tool} container input differs from catalogue FASTA"
            )
        if copied_output.read_bytes() != host_output.read_bytes():
            raise LocalisationContainerExecutionError(
                f"{tool} container output differs from retained raw output"
            )
    container_doc = json.loads(container_inspect)[0]
    path = container_doc.get("Path")
    arguments = container_doc.get("Args")
    if (
        not isinstance(path, str)
        or not isinstance(arguments, list)
        or not all(isinstance(value, str) for value in arguments)
    ):
        raise LocalisationContainerExecutionError("Docker effective command is invalid")
    expected_reference, expected_digest, tool_version = _fixed_tool(tool)
    values = {
        "schema_version": "2.0",
        "tool": tool,
        "tool_version": tool_version,
        "container_id": container_doc.get("Id"),
        "image_reference": expected_reference,
        "image_manifest_sha256": expected_digest,
        "image_id": image_id,
        "platform": "linux/amd64",
        "docker_engine_version": docker_version,
        "container_inspect_json": container_inspect,
        "container_inspect_sha256": hashlib.sha256(
            container_inspect.encode("utf-8")
        ).hexdigest(),
        "image_inspect_json": image_inspect,
        "image_inspect_sha256": hashlib.sha256(
            image_inspect.encode("utf-8")
        ).hexdigest(),
        "effective_command": (path, *arguments),
        "working_directory": container_doc.get("Config", {}).get("WorkingDir"),
        "network_mode": container_doc.get("HostConfig", {}).get("NetworkMode"),
        "terminal_status": container_doc.get("State", {}).get("Status"),
        "exit_code": container_doc.get("State", {}).get("ExitCode"),
        "input_container_path": "/input.faa",
        "input_fasta_sha256": sha256_file(host_fasta, progress=False),
        "input_fasta_size_bytes": host_fasta.stat().st_size,
        "output_container_path": output_container_path,
        "raw_output_sha256": sha256_file(host_output, progress=False),
        "raw_output_size_bytes": host_output.stat().st_size,
        "log_path": log_name,
        "log_sha256": hashlib.sha256(log_bytes).hexdigest(),
        "log_size_bytes": len(log_bytes),
        "explicit_failed_source_ids": (),
        "provenance_source": "docker_cli_inspect_copy_logs_v1",
    }
    return LocalisationContainerToolExecution.from_content(**values)


def capture_localisation_container_execution(
    request: LocalisationContainerCaptureRequest,
) -> Path:
    """Capture two terminal network-none containers into a portable bundle."""

    output = request.output_directory.absolute()
    if output.exists() or output.is_symlink():
        raise LocalisationContainerExecutionError("execution output already exists")
    fasta = request.catalogue_fasta.resolve(strict=True)
    psortb_output = request.psortb_output.resolve(strict=True)
    deep_output = request.deeptmhmm_output.resolve(strict=True)
    if not all(path.is_file() for path in (fasta, psortb_output, deep_output)):
        raise LocalisationContainerExecutionError("capture inputs must be files")
    docker_version = (
        _docker("version", "--format", "{{.Server.Version}}").decode("utf-8").strip()
    )
    if not docker_version:
        raise LocalisationContainerExecutionError("Docker version is empty")
    output.mkdir(parents=True)
    psortb = _capture_tool(
        tool="psortb",
        container_name=request.psortb_container,
        output_container_path=request.psortb_output_container_path,
        host_fasta=fasta,
        host_output=psortb_output,
        docker_version=docker_version,
        output_directory=output,
    )
    deeptmhmm = _capture_tool(
        tool="deeptmhmm",
        container_name=request.deeptmhmm_container,
        output_container_path=request.deeptmhmm_output_container_path,
        host_fasta=fasta,
        host_output=deep_output,
        docker_version=docker_version,
        output_directory=output,
    )
    manifest = LocalisationBatchExecutionManifest.from_content(
        source_fasta_sha256=sha256_file(fasta, progress=False),
        source_fasta_size_bytes=fasta.stat().st_size,
        psortb=psortb,
        deeptmhmm=deeptmhmm,
    )
    path = output / _MANIFEST_NAME
    atomic_write_json(path, manifest.model_dump(mode="json"))
    validate_localisation_container_execution(output)
    return path


def validate_localisation_container_execution(
    directory: Path,
) -> LocalisationBatchExecutionManifest:
    """Revalidate the exact portable inspect/log bundle."""

    if directory.is_symlink():
        raise LocalisationContainerExecutionError(
            "container execution bundle must not be a symlink"
        )
    try:
        root = directory.resolve(strict=True)
    except OSError as error:
        raise LocalisationContainerExecutionError(
            "container execution bundle is absent"
        ) from error
    expected = {_MANIFEST_NAME, _PSORTB_LOG_NAME, _DEEPTMHMM_LOG_NAME}
    observed = {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    }
    if (
        not root.is_dir()
        or root.is_symlink()
        or observed != expected
        or any(path.is_symlink() for path in root.rglob("*"))
    ):
        raise LocalisationContainerExecutionError(
            "container execution bundle layout differs"
        )
    try:
        manifest = LocalisationBatchExecutionManifest.model_validate_json(
            (root / _MANIFEST_NAME).read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, ValidationError, ValueError) as error:
        raise LocalisationContainerExecutionError(
            "container execution manifest is invalid"
        ) from error
    for record in (manifest.psortb, manifest.deeptmhmm):
        log = root / record.log_path
        if (
            log.stat().st_size != record.log_size_bytes
            or sha256_file(log, progress=False) != record.log_sha256
        ):
            raise LocalisationContainerExecutionError("container log checksum differs")
    return manifest


__all__ = [
    "DEEPTMHMM_IMAGE_MANIFEST_SHA256",
    "DEEPTMHMM_IMAGE_REFERENCE",
    "LOCALISATION_BATCH_ADAPTER_VERSION",
    "PSORTB_IMAGE_MANIFEST_SHA256",
    "PSORTB_IMAGE_REFERENCE",
    "LocalisationBatchExecutionManifest",
    "LocalisationContainerCaptureRequest",
    "LocalisationContainerExecutionError",
    "LocalisationContainerToolExecution",
    "capture_localisation_container_execution",
    "validate_localisation_container_execution",
]
