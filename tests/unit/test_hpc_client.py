"""Tests for local ownership, transitions, collection, and feedback limits."""

import base64
import hashlib
import io
import json
import subprocess
import tarfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import pytest

from genome_to_diffraction.hpc.client import (
    DATABASE_STAGE_TIMEOUT_SECONDS,
    P0_STAGE_TIMEOUT_SECONDS,
    SSH_COLLECTION_TIMEOUT_SECONDS,
    SSH_CONNECT_TIMEOUT_SECONDS,
    SSH_OPERATION_TIMEOUT_SECONDS,
    HpcController,
    SshTransport,
)
from genome_to_diffraction.hpc.models import (
    ConfigurationError,
    FailureClass,
    HpcConfig,
    RemoteOperationError,
    ValidationError,
)

COMMIT = "1" * 40
REPOSITORY = Path(__file__).resolve().parents[2]


@dataclass
class FakeGit:
    dirty: bool = False
    repository: Path | None = None

    def ensure_clean(self) -> None:
        if self.dirty:
            raise ValidationError("dirty")

    def resolve_commit(self, revision: str) -> str:
        if revision not in {"HEAD", COMMIT}:
            raise ValidationError("revision")
        return COMMIT

    def read_file_at_commit(self, commit: str, path: PurePosixPath) -> bytes:
        if commit != COMMIT or self.repository is None:
            raise ValidationError("commit file")
        return self.repository.joinpath(*path.parts).read_bytes()


@dataclass
class FakeTransport:
    archive: bytes = b""
    status_responses: list[dict[str, str]] = field(default_factory=list)
    calls: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)
    p0_archive: bytes = b""

    def run(self, operation: str, arguments: Sequence[str]) -> dict[str, str]:
        self.calls.append((operation, tuple(arguments)))
        if operation == "status" and self.status_responses:
            return self.status_responses.pop(0)
        if operation == "logs":
            return {
                "run_id": arguments[0],
                "content_base64": base64.b64encode(b"line one\nline two\n").decode(),
            }
        return {
            "run_id": arguments[0] if arguments else "",
            "remote_operation": operation,
        }

    def collect(self, run_id: str, owner_id: str) -> bytes:
        self.calls.append(("collect", (run_id, owner_id)))
        return self.archive

    def p0_inputs_stage(
        self,
        source_id: str,
        archive_sha256: str,
        archive_size_bytes: int,
        database_manifest_sha256: str,
        phenix_manifest_sha256: str,
        archive_path: Path,
    ) -> dict[str, str]:
        self.calls.append(
            (
                "p0-inputs-stage",
                (
                    source_id,
                    archive_sha256,
                    str(archive_size_bytes),
                    database_manifest_sha256,
                    phenix_manifest_sha256,
                ),
            )
        )
        self.p0_archive = archive_path.read_bytes()
        destination = f"/approved/root/_p0_inputs/p0i_{source_id}"
        paths = (
            "/approved\n"
            f"{destination}/manifests/catalogues.json\n"
            f"{destination}/manifests/crystals.json\n"
            f"{destination}/manifests/config.yaml\n"
            "/approved/databases\n"
            "/approved/database-manifest.json\n"
            "/approved/phenix-manifest.json\n"
        ).encode("ascii")
        return {
            "p0_input_id": f"p0i_{source_id}",
            "archive_sha256": archive_sha256,
            "archive_size_bytes": str(archive_size_bytes),
            "p0_config_sha256": hashlib.sha256(paths).hexdigest(),
            "p0_paths_base64": base64.b64encode(paths).decode("ascii"),
        }


def _config(repository: Path) -> HpcConfig:
    return HpcConfig(
        repository=repository,
        ssh_alias="marmic",
        remote_dispatcher="/approved/root/_tooling/nf-gtd-hpc-remote",
        local_state_root=repository / ".untracked" / "hpc-test",
        poll_seconds=1,
        queue_timeout_seconds=1,
        execution_timeout_seconds=1,
        database_execution_timeout_seconds=2,
    )


def _archive(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as tar:
        for name, payload in files.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
    return output.getvalue()


def _controller(tmp_path: Path, transport: FakeTransport) -> HpcController:
    (tmp_path / "pixi.lock").write_text("locked\n", encoding="utf-8")
    bootstrap = tmp_path / "bootstrap"
    bootstrap.mkdir(exist_ok=True)
    for name in ("nf-gtd-hpc-remote", "nf-gtd-hpc-smoke-job"):
        tool = bootstrap / name
        tool.write_text(f"#!/usr/bin/env bash\n# {name}\n", encoding="utf-8")
        tool.chmod(0o755)
    return HpcController(
        _config(tmp_path),
        transport=transport,
        git=FakeGit(repository=tmp_path),
        progress=False,
    )


def _write_fixed_p0_inputs(repository: Path) -> str:
    qualification = repository / ".untracked" / "m0-qualification"
    manifests = qualification / "manifests"
    manifests.mkdir(parents=True)
    data = repository.parent / "data"
    genome = data / "genome"
    crystals = data / "crystals"
    genome.mkdir(parents=True)
    crystals.mkdir()
    source_files = {
        ("proteome_faa", "GCF_000711905.1"): genome / "protein.faa",
        ("genome_fasta", "GCF_000711905.1"): genome / "genome.fna",
        ("annotation_gff", "GCF_000711905.1"): genome / "genomic.gff",
        ("annotation_gbff", "GCF_000711905.1"): genome / "genomic.gbff",
        ("mtz", "AD4QS1P4G2_18"): crystals / "AD4QS1P4G2_18.mtz",
        ("mtz", "CD4QS2P2G1_15"): crystals / "CD4QS2P2G1_15.mtz",
        ("mtz", "CD6QS2P2G1_5"): crystals / "CD6QS2P2G1_5.mtz",
    }
    for (role, logical_id), path in source_files.items():
        path.write_bytes(f"{role}:{logical_id}\n".encode("ascii"))

    catalogue = {
        "schema_version": "1.0",
        "catalogues": [
            {
                "catalogue_id": "methermicoccus_refseq",
                "proteome_faa": str(source_files[("proteome_faa", "GCF_000711905.1")]),
                "annotation_provider": "NCBI RefSeq PGAP",
                "annotation_version": "test",
                "assembly_accession": "GCF_000711905.1",
                "genome_fasta": str(source_files[("genome_fasta", "GCF_000711905.1")]),
                "annotation_gff": str(
                    source_files[("annotation_gff", "GCF_000711905.1")]
                ),
                "annotation_gbff": str(
                    source_files[("annotation_gbff", "GCF_000711905.1")]
                ),
                "protein_locus_map": None,
                "translation_table": 11,
                "is_contaminant_catalogue": False,
            }
        ],
    }
    (manifests / "catalogues.json").write_text(
        json.dumps(catalogue) + "\n", encoding="utf-8"
    )
    crystal_manifest = {
        "schema_version": "1.0",
        "crystals": [
            {
                "crystal_id": crystal_id,
                "mtz": str(source_files[("mtz", crystal_id)]),
                "catalogue_id": "methermicoccus_refseq",
                "allow_remote_sequence_submission": False,
            }
            for crystal_id in (
                "AD4QS1P4G2_18",
                "CD4QS2P2G1_15",
                "CD6QS2P2G1_5",
            )
        ],
    }
    (manifests / "crystals.json").write_text(
        json.dumps(crystal_manifest) + "\n", encoding="utf-8"
    )
    (manifests / "config.yaml").write_bytes(
        (REPOSITORY / "examples" / "config.yaml").read_bytes()
    )

    rows = ["role\tlogical_id\tsize_bytes\tsha256\tpath"]
    for (role, logical_id), path in source_files.items():
        payload = path.read_bytes()
        rows.append(
            f"{role}\t{logical_id}\t{len(payload)}\t"
            f"{hashlib.sha256(payload).hexdigest()}\t{path}"
        )
    (qualification / "input-inventory.tsv").write_text(
        "\n".join(rows) + "\n", encoding="utf-8"
    )
    spec = {
        "schema_version": "1.0",
        "database_manifest_sha256": "2" * 64,
        "phenix_manifest_sha256": "3" * 64,
    }
    spec_path = qualification / "p0-inputs.json"
    spec_path.write_text(json.dumps(spec, sort_keys=True) + "\n", encoding="utf-8")
    return hashlib.sha256(spec_path.read_bytes()).hexdigest()


def test_ssh_transport_is_noninteractive_and_has_hard_timeouts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[tuple[str, ...]] = []
    timeouts: list[int] = []

    def timeout_run(
        command: Sequence[str], **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        timeout = kwargs.get("timeout")
        assert isinstance(timeout, int)
        commands.append(tuple(command))
        timeouts.append(timeout)
        raise subprocess.TimeoutExpired(command, timeout)

    monkeypatch.setattr("genome_to_diffraction.hpc.client.subprocess.run", timeout_run)
    transport = SshTransport(_config(tmp_path))

    with pytest.raises(RemoteOperationError, match="transport timeout") as operation:
        transport.run("readiness", ["p0"])
    with pytest.raises(RemoteOperationError, match="transport timeout") as p0_staging:
        transport.run(
            "stage",
            [
                "gtd-p0-20260802T120000Z-0123456789ab-01234567",
                "1" * 40,
                "2" * 64,
                "3" * 32,
                "1",
                "p0",
            ],
        )
    with pytest.raises(RemoteOperationError, match="transport timeout") as staging:
        transport.run("database-stage", ["1" * 40])
    with pytest.raises(RemoteOperationError, match="transport timeout") as collection:
        transport.collect("gtd-p0-20260802T120000Z-0123456789ab-01234567", "1" * 32)

    assert operation.value.failure_class is FailureClass.TRANSFER_FAILURE
    assert p0_staging.value.failure_class is FailureClass.TRANSFER_FAILURE
    assert staging.value.failure_class is FailureClass.TRANSFER_FAILURE
    assert collection.value.failure_class is FailureClass.TRANSFER_FAILURE
    assert timeouts == [
        SSH_OPERATION_TIMEOUT_SECONDS,
        P0_STAGE_TIMEOUT_SECONDS,
        DATABASE_STAGE_TIMEOUT_SECONDS,
        SSH_COLLECTION_TIMEOUT_SECONDS,
    ]
    assert all(command[0] == "ssh" for command in commands)
    assert all("BatchMode=yes" in command for command in commands)
    assert all(
        f"ConnectTimeout={SSH_CONNECT_TIMEOUT_SECONDS}" in command
        for command in commands
    )
    assert all("ConnectionAttempts=1" in command for command in commands)
    assert all("ServerAliveInterval=15" in command for command in commands)
    assert all("ServerAliveCountMax=2" in command for command in commands)


def test_deploy_tools_sends_only_commit_and_verified_checksums(tmp_path: Path) -> None:
    transport = FakeTransport()
    controller = _controller(tmp_path, transport)

    result = controller.deploy_tools("HEAD")

    assert result["operation"] == "deploy-tools"
    operation, arguments = transport.calls[-1]
    assert operation == "deploy-tools"
    assert arguments[0] == COMMIT
    assert len(arguments) == 3
    assert all(len(value) == 64 for value in arguments[1:])


def test_deploy_tools_refuses_dirty_or_mismatched_worktree(tmp_path: Path) -> None:
    transport = FakeTransport()
    controller = _controller(tmp_path, transport)
    controller.git = FakeGit(dirty=True, repository=tmp_path)
    with pytest.raises(ValidationError, match="dirty"):
        controller.deploy_tools("HEAD")

    controller.git = FakeGit(repository=tmp_path)
    (tmp_path / "bootstrap" / "nf-gtd-hpc-smoke-job").write_text(
        "changed\n", encoding="utf-8"
    )
    committed = b"#!/usr/bin/env bash\n# nf-gtd-hpc-smoke-job\n"

    class MismatchedGit(FakeGit):
        def read_file_at_commit(self, commit: str, path: PurePosixPath) -> bytes:
            if path.name == "nf-gtd-hpc-smoke-job":
                return committed
            return super().read_file_at_commit(commit, path)

    controller.git = MismatchedGit(repository=tmp_path)
    with pytest.raises(ValidationError, match="worktree content differs"):
        controller.deploy_tools("HEAD")
    assert transport.calls == []


def test_all_owned_operations_use_the_recorded_capability(tmp_path: Path) -> None:
    transport = FakeTransport(
        status_responses=[
            {
                "run_id": "placeholder",
                "scheduler_state": "COMPLETED",
                "terminal": "true",
                "failure_class": "success",
            }
        ]
    )
    controller = _controller(tmp_path, transport)

    staged = controller.stage("smoke", "HEAD")
    run_id = str(staged["run_id"])
    assert controller.submit("smoke", run_id)["operation"] == "submit"
    assert controller.status(run_id)["operation"] == "status"
    assert controller.logs(run_id, 200)["log"] == "line one\nline two\n"
    assert controller.cancel(run_id)["operation"] == "cancel"
    assert controller.clean(run_id, run_id)["operation"] == "clean"

    owner_values = {
        arguments[1]
        for operation, arguments in transport.calls
        if operation in {"submit", "status", "logs", "cancel", "clean"}
    }
    assert len(owner_values) == 1


@pytest.mark.parametrize("profile", ["p0", "p1", "p2", "p2-diverse"])
def test_scientific_profile_has_a_closed_run_id_and_remote_argument(
    tmp_path: Path, profile: str
) -> None:
    transport = FakeTransport()
    controller = _controller(tmp_path, transport)

    staged = controller.stage(profile, "HEAD")

    run_id = str(staged["run_id"])
    assert run_id.startswith(f"gtd-{profile}-")
    operation, arguments = transport.calls[-1]
    assert operation == "stage"
    assert arguments[-1] == profile
    assert controller.submit(profile, run_id)["operation"] == "submit"
    with pytest.raises(ValidationError, match="does not match"):
        controller.submit("smoke", run_id)


@pytest.mark.parametrize("profile", ["p0", "p1", "p2", "p2-diverse"])
def test_scientific_readiness_accepts_no_path_or_run_authority(
    tmp_path: Path, profile: str
) -> None:
    transport = FakeTransport()
    controller = _controller(tmp_path, transport)

    result = controller.readiness(profile)

    assert result["operation"] == "readiness"
    assert result["profile"] == profile
    assert transport.calls == [("readiness", (profile,))]
    with pytest.raises(ValidationError, match="only for p0, p1, p2"):
        controller.readiness("smoke")
    with pytest.raises(ValidationError):
        controller.readiness("p0;touch-bad")


def test_p0_configuration_is_checksum_confirmed_and_strictly_validated(
    tmp_path: Path,
) -> None:
    transport = FakeTransport()
    controller = _controller(tmp_path, transport)
    paths_file = tmp_path / "p0.paths"
    payload = "\n".join(f"/approved/site/path-{index}" for index in range(7)) + "\n"
    paths_file.write_text(payload, encoding="ascii")
    paths_file.chmod(0o600)
    checksum = hashlib.sha256(payload.encode("ascii")).hexdigest()

    with pytest.raises(ValidationError, match="exactly equal"):
        controller.p0_configure(paths_file, "0" * 64)
    result = controller.p0_configure(paths_file, checksum)

    assert result["operation"] == "p0-configure"
    operation, arguments = transport.calls[-1]
    assert operation == "p0-configure"
    assert arguments[0] == checksum
    assert base64.b64decode(arguments[1]).decode("ascii") == payload

    paths_file.write_text(
        payload.replace("path-3", "path-3;touch-bad"), encoding="ascii"
    )
    with pytest.raises(ConfigurationError, match="conservative absolute"):
        controller.p0_configure(paths_file, checksum)


def test_p0_input_staging_is_frozen_rewritten_and_checksum_gated(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "nf-genome_to_diffraction"
    repository.mkdir()
    confirmation = _write_fixed_p0_inputs(repository)
    transport = FakeTransport()
    controller = _controller(repository, transport)

    with pytest.raises(ValidationError, match="exactly equal"):
        controller.p0_inputs_stage("0" * 64)
    result = controller.p0_inputs_stage(confirmation)

    assert result["operation"] == "p0-inputs-stage"
    assert result["scientific_input_count"] == 7
    assert result["p0_input_id"] == f"p0i_{transport.calls[-1][1][0]}"
    assert (
        hashlib.sha256(transport.p0_archive).hexdigest() == (result["archive_sha256"])
    )
    paths_file = Path(str(result["local_paths_file"]))
    assert paths_file.stat().st_mode & 0o777 == 0o600
    assert (
        hashlib.sha256(paths_file.read_bytes()).hexdigest()
        == (result["p0_config_sha256"])
    )
    with tarfile.open(fileobj=io.BytesIO(transport.p0_archive), mode="r:gz") as archive:
        names = sorted(archive.getnames())
        assert len(names) == 12
        assert names == [
            "bundle.json",
            "inputs/AD4QS1P4G2_18.mtz",
            "inputs/CD4QS2P2G1_15.mtz",
            "inputs/CD6QS2P2G1_5.mtz",
            "inputs/annotation.gbff",
            "inputs/annotation.gff",
            "inputs/genome.fna",
            "inputs/proteome.faa",
            "inventory.tsv",
            "manifests/catalogues.json",
            "manifests/config.yaml",
            "manifests/crystals.json",
        ]
        rewritten = archive.extractfile("manifests/catalogues.json")
        assert rewritten is not None
        rewritten_text = rewritten.read().decode("ascii")
    assert str(repository.parent / "data") not in rewritten_text
    assert "/approved/root/_p0_inputs/p0i_" in rewritten_text

    repeated = controller.p0_inputs_stage(confirmation)
    assert repeated["p0_input_id"] == result["p0_input_id"]
    assert repeated["archive_sha256"] == result["archive_sha256"]

    paths_file.chmod(0o644)
    with pytest.raises(ValidationError, match="unsafe identity"):
        controller.p0_inputs_stage(confirmation)
    paths_file.chmod(0o600)

    protein = repository.parent / "data" / "genome" / "protein.faa"
    protein.write_text("changed\n", encoding="ascii")
    with pytest.raises(ValidationError, match="size differs"):
        controller.p0_inputs_stage(confirmation)


def test_p0_input_staging_rejects_files_not_owned_by_the_invoking_user(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "nf-genome_to_diffraction"
    repository.mkdir()
    confirmation = _write_fixed_p0_inputs(repository)
    controller = _controller(repository, FakeTransport())
    monkeypatch.setattr(
        "genome_to_diffraction.hpc.p0_inputs.os.getuid",
        lambda: repository.stat().st_uid + 1,
    )

    with pytest.raises(ValidationError, match="owned regular file"):
        controller.p0_inputs_stage(confirmation)


def test_database_start_has_a_separate_local_authority_boundary(
    tmp_path: Path,
) -> None:
    transport = FakeTransport()
    controller = _controller(tmp_path, transport)

    readiness = controller.database_readiness()
    staged = controller.database_stage("HEAD")
    run_id = str(staged["run_id"])
    submitted = controller.database_submit(run_id)

    assert readiness["profile"] == "database"
    assert run_id.startswith("gtd-database-")
    assert submitted["operation"] == "database-submit"
    assert [operation for operation, _ in transport.calls] == [
        "database-readiness",
        "database-stage",
        "database-submit",
    ]
    assert transport.calls[0][1] == ()
    assert transport.calls[1][1][-1] == transport.calls[2][1][1]

    with pytest.raises(ValidationError, match="separate database-stage"):
        controller.stage("database", "HEAD")
    with pytest.raises(ValidationError, match="separate database-submit"):
        controller.submit("database", run_id)

    smoke_run = str(controller.stage("smoke", "HEAD")["run_id"])
    with pytest.raises(ValidationError, match="requires a database run"):
        controller.database_submit(smoke_run)


def test_database_failed_staging_archive_requires_collected_owned_evidence(
    tmp_path: Path,
) -> None:
    job_result = json.dumps(
        {
            "failure_class": "software_failure",
            "exit_code": 1,
            "scheduler_state": "FAILED",
        }
    ).encode()
    transport = FakeTransport(archive=_archive({"state/job-result.json": job_result}))
    controller = _controller(tmp_path, transport)
    run_id = str(controller.database_stage("HEAD")["run_id"])

    with pytest.raises(ValidationError, match="collect the terminal database run"):
        controller.database_archive_failed(run_id, run_id)
    controller.collect(run_id)
    with pytest.raises(ValidationError, match="exactly equal"):
        controller.database_archive_failed(run_id, "wrong")

    result = controller.database_archive_failed(run_id, run_id)

    assert result["operation"] == "database-archive-failed"
    assert transport.calls[-1][0] == "database-archive-failed"
    assert transport.calls[-1][1][0] == run_id
    assert transport.calls[-1][1][2] == run_id

    cancelled_transport = FakeTransport(archive=_archive({"manifest.json": b"{}\n"}))
    cancelled_root = tmp_path / "cancelled"
    cancelled_root.mkdir()
    cancelled_controller = _controller(cancelled_root, cancelled_transport)
    cancelled_run = str(cancelled_controller.database_stage("HEAD")["run_id"])
    cancelled_controller.collect(cancelled_run)
    assert (
        cancelled_controller.database_archive_failed(cancelled_run, cancelled_run)[
            "operation"
        ]
        == "database-archive-failed"
    )


def test_stage_refuses_dirty_or_injected_revisions(tmp_path: Path) -> None:
    (tmp_path / "pixi.lock").write_text("locked\n", encoding="utf-8")
    transport = FakeTransport()
    dirty = HpcController(
        _config(tmp_path),
        transport=transport,
        git=FakeGit(dirty=True, repository=tmp_path),
        progress=False,
    )
    with pytest.raises(ValidationError, match="dirty"):
        dirty.stage("smoke", "HEAD")

    clean = HpcController(
        _config(tmp_path),
        transport=transport,
        git=FakeGit(repository=tmp_path),
        progress=False,
    )
    with pytest.raises(ValidationError):
        clean.stage("smoke", "HEAD; touch bad")
    assert transport.calls == []


def test_wait_reports_bounded_queue_timeout_without_cancelling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = FakeTransport(
        status_responses=[
            {"scheduler_state": "PENDING", "terminal": "false"},
        ]
    )
    controller = _controller(tmp_path, transport)
    run_id = str(controller.stage("smoke", "HEAD")["run_id"])
    monkeypatch.setattr("genome_to_diffraction.hpc.client.time.sleep", lambda _: None)

    result = controller.wait(run_id)

    assert result["failure_class"] == FailureClass.QUEUE_TIMEOUT
    assert all(operation != "cancel" for operation, _ in transport.calls)


def test_collection_extracts_regular_whitelisted_payload_safely(tmp_path: Path) -> None:
    job_result = json.dumps(
        {
            "failure_class": "test_failure",
            "exit_code": 1,
            "scheduler_state": "FAILED",
        }
    ).encode()
    transport = FakeTransport(
        archive=_archive(
            {
                "manifest.json": b"{}\n",
                "state/job-result.json": job_result,
                "logs/smoke.log": b"failed\n",
            }
        )
    )
    controller = _controller(tmp_path, transport)
    run_id = str(controller.stage("smoke", "HEAD")["run_id"])

    result = controller.collect(run_id)

    assert result["failure_signature"] is not None
    assert (Path(str(result["destination"])) / "logs" / "smoke.log").read_text() == (
        "failed\n"
    )


def test_collection_rejects_path_traversal(tmp_path: Path) -> None:
    transport = FakeTransport(archive=_archive({"../outside": b"bad"}))
    controller = _controller(tmp_path, transport)
    run_id = str(controller.stage("smoke", "HEAD")["run_id"])

    with pytest.raises(RemoteOperationError, match="unsafe archive member"):
        controller.collect(run_id)
    assert not (tmp_path / "outside").exists()


def test_collection_rejects_symlinked_parent(tmp_path: Path) -> None:
    transport = FakeTransport(archive=_archive({"logs/smoke.log": b"bad"}))
    controller = _controller(tmp_path, transport)
    run_id = str(controller.stage("smoke", "HEAD")["run_id"])
    destination = tmp_path / ".untracked" / "hpc-test" / run_id / "collected"
    outside = tmp_path / "outside"
    outside.mkdir()
    destination.mkdir(parents=True)
    (destination / "logs").symlink_to(outside, target_is_directory=True)

    with pytest.raises(RemoteOperationError, match="escaped collection root"):
        controller.collect(run_id)
    assert list(outside.iterdir()) == []


def test_same_failure_twice_stops_the_feedback_chain(tmp_path: Path) -> None:
    job_result = json.dumps(
        {
            "failure_class": "test_failure",
            "exit_code": 1,
            "scheduler_state": "FAILED",
        }
    ).encode()
    transport = FakeTransport(archive=_archive({"state/job-result.json": job_result}))
    controller = _controller(tmp_path, transport)
    first = str(controller.stage("smoke", "HEAD")["run_id"])
    controller.collect(first)
    second = str(controller.stage("smoke", "HEAD", parent_run_id=first)["run_id"])
    controller.collect(second)

    with pytest.raises(ValidationError, match="occurred twice"):
        controller.stage("smoke", "HEAD", parent_run_id=second)


def test_distinct_application_diagnostics_do_not_collide(tmp_path: Path) -> None:
    job_result = json.dumps(
        {
            "failure_class": "environment_failure",
            "exit_code": 1,
            "scheduler_state": "FAILED",
            "application_log": "logs/smoke.log",
        }
    ).encode()
    transport = FakeTransport()
    controller = _controller(tmp_path, transport)
    first = str(controller.stage("smoke", "HEAD")["run_id"])
    transport.archive = _archive(
        {
            "state/job-result.json": job_result,
            "logs/smoke.log": b"package resolution failed\n",
        }
    )
    first_result = controller.collect(first)
    second = str(controller.stage("smoke", "HEAD", parent_run_id=first)["run_id"])
    transport.archive = _archive(
        {
            "state/job-result.json": job_result,
            "logs/smoke.log": b"phenix.xtriage probe timed out\n",
        }
    )
    second_result = controller.collect(second)

    assert first_result["failure_signature"] != second_result["failure_signature"]
    third = controller.stage("smoke", "HEAD", parent_run_id=second)
    assert third["iteration"] == 3


def test_unowned_run_cannot_be_cancelled(tmp_path: Path) -> None:
    transport = FakeTransport()
    controller = _controller(tmp_path, transport)
    run_id = "gtd-smoke-20260802T120000Z-0123456789ab-01234567"
    with pytest.raises(ValidationError, match="not found"):
        controller.cancel(run_id)
    assert transport.calls == []
