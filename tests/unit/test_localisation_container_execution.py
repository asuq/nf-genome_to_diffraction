"""Tests for inspected network-none localisation container evidence."""

import json
import subprocess
from pathlib import Path

import pytest

from genome_to_diffraction.localisation.container_execution import (
    DEEPTMHMM_IMAGE_REFERENCE,
    PSORTB_IMAGE_REFERENCE,
    LocalisationContainerCaptureRequest,
    LocalisationContainerExecutionError,
    capture_localisation_container_execution,
    validate_localisation_container_execution,
)


def _container(tool: str) -> dict[str, object]:
    image = PSORTB_IMAGE_REFERENCE if tool == "psortb" else DEEPTMHMM_IMAGE_REFERENCE
    command = (
        ("/usr/local/bin/psort", "-a", "-o", "terse", "-i", "/input.faa")
        if tool == "psortb"
        else ("python3", "predict.py", "--fasta", "/input.faa")
    )
    index = 1 if tool == "psortb" else 2
    return {
        "Id": f"{index:064x}",
        "Image": f"sha256:{index + 10:064x}",
        "Path": command[0],
        "Args": list(command[1:]),
        "Config": {
            "Image": image,
            "WorkingDir": "/tmp/results" if tool == "psortb" else "/openprotein",
        },
        "HostConfig": {"NetworkMode": "none"},
        "State": {"Status": "exited", "Running": False, "ExitCode": 0},
    }


def test_capture_replays_real_docker_inspection_and_copied_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fasta = tmp_path / "catalogue.faa"
    psortb = tmp_path / "psortb.tsv"
    deep = tmp_path / "deeptmhmm.3line"
    fasta.write_text(">protein\nMPEPTIDE\n", encoding="ascii")
    psortb.write_text(
        "SeqID\tLocalization\tScore\nprotein\tCytoplasmic\t9.5\n",
        encoding="ascii",
    )
    deep.write_text(
        ">protein | GLOB\nMPEPTIDE\nIIIIIIII\n",
        encoding="ascii",
    )
    calls: list[tuple[str, ...]] = []

    def fake_run(
        arguments: list[str],
        *,
        check: bool,
        capture_output: bool,
        timeout: int,
    ) -> subprocess.CompletedProcess[bytes]:
        del check, capture_output, timeout
        calls.append(tuple(arguments))
        if arguments[1:3] == ["version", "--format"]:
            return subprocess.CompletedProcess(arguments, 0, b"29.6.2\n", b"")
        if arguments[1:3] == ["container", "inspect"]:
            tool = "psortb" if arguments[3] == "psortb-test" else "deeptmhmm"
            return subprocess.CompletedProcess(
                arguments,
                0,
                json.dumps([_container(tool)]).encode(),
                b"",
            )
        if arguments[1:3] == ["image", "inspect"]:
            reference = arguments[3]
            digest = reference.rsplit("sha256:", maxsplit=1)[1]
            tool = "psortb" if "psortb" in reference else "deeptmhmm"
            index = 1 if tool == "psortb" else 2
            document = [
                {
                    "Id": f"sha256:{index + 10:064x}",
                    "Os": "linux",
                    "Architecture": "amd64",
                    "RepoDigests": [
                        f"{reference.split('@', maxsplit=1)[0]}@sha256:{digest}"
                    ],
                }
            ]
            return subprocess.CompletedProcess(
                arguments,
                0,
                json.dumps(document).encode(),
                b"",
            )
        if arguments[1] == "logs":
            return subprocess.CompletedProcess(
                arguments,
                0,
                f"terminal {arguments[2]}\n".encode(),
                b"",
            )
        if arguments[1] == "cp":
            source, destination = arguments[2:]
            target = Path(destination)
            if source.endswith(":/input.faa"):
                target.write_bytes(fasta.read_bytes())
            elif source.startswith("psortb-test:"):
                target.write_bytes(psortb.read_bytes())
            else:
                target.write_bytes(deep.read_bytes())
            return subprocess.CompletedProcess(arguments, 0, b"", b"")
        raise AssertionError(f"unexpected Docker invocation: {arguments}")

    monkeypatch.setattr(
        "genome_to_diffraction.localisation.container_execution.subprocess.run",
        fake_run,
    )
    output = tmp_path / "execution"

    manifest_path = capture_localisation_container_execution(
        LocalisationContainerCaptureRequest(
            catalogue_fasta=fasta,
            psortb_container="psortb-test",
            psortb_output_container_path="/tmp/results/psortb.tsv",
            psortb_output=psortb,
            deeptmhmm_container="deeptmhmm-test",
            deeptmhmm_output_container_path=("/openprotein/predicted_topologies.3line"),
            deeptmhmm_output=deep,
            output_directory=output,
        )
    )

    manifest = validate_localisation_container_execution(output)
    assert manifest_path.is_file()
    assert manifest.psortb.network_mode == "none"
    assert manifest.deeptmhmm.network_mode == "none"
    assert manifest.psortb.exit_code == 0
    assert manifest.deeptmhmm.exit_code == 0
    assert sum(call[1] == "cp" for call in calls) == 4


def test_container_execution_rejects_changed_inspection_bytes(tmp_path: Path) -> None:
    from tests.support.unknown_pass1_fixture import (
        materialise_localisation_container_execution_fixture,
    )

    fasta = tmp_path / "catalogue.faa"
    psortb = tmp_path / "psortb.tsv"
    deep = tmp_path / "deep.3line"
    fasta.write_text(">p\nMPEPTIDE\n", encoding="ascii")
    psortb.write_text("header\nrow\n", encoding="ascii")
    deep.write_text(">p | GLOB\nMPEPTIDE\nIIIIIIII\n", encoding="ascii")
    bundle = materialise_localisation_container_execution_fixture(
        tmp_path / "fixture",
        catalogue_fasta=fasta,
        psortb_output=psortb,
        deeptmhmm_output=deep,
    )
    manifest = bundle / "localisation_container_execution.json"
    document = json.loads(manifest.read_text(encoding="utf-8"))
    document["psortb"]["network_mode"] = "bridge"
    manifest.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(
        LocalisationContainerExecutionError, match="manifest is invalid"
    ):
        validate_localisation_container_execution(bundle)
