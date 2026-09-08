"""Validate reviewed JSON authority before exercising the existing no-A graph."""

import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.hpc.raven_controls import PATH_FIELDS
from genome_to_diffraction.localisation import plan_batch_localisation_reopen
from genome_to_diffraction.schemas.v2.execution import ExecutionArtifactIdentity
from genome_to_diffraction.status import ExecutionStatus
from tests.unit.test_localisation_reopen import _case, _reviewed_request
from tests.unit.test_phase3_execution_identity import _identity

REPOSITORY = Path(__file__).resolve().parents[2]
FIXTURE = REPOSITORY / "tests/fixtures/stubs/phase3_composition_beam"


def run_reviewed_reopening_stub(root: Path) -> None:
    """Require one reviewer-selected hypothesis and cache-identical replay."""

    root.mkdir()
    source = root / "review_authority"
    source.mkdir()
    request, selected_id = _case(
        source,
        status=ExecutionStatus.COMPLETED_HIT,
        packed=True,
        crystal_id="stub_no_a_crystal",
    )
    reviewed = _reviewed_request(request, (selected_id,))
    plan = plan_batch_localisation_reopen(reviewed)
    if plan.plan.reopened_hypothesis_count != 1:
        raise RuntimeError("reviewed reopening did not retain the exact selection")
    fixture = root / "fixture"
    shutil.copytree(FIXTURE, fixture)
    shutil.copytree(plan.plan_json.parent, fixture / "no_a", dirs_exist_ok=True)
    output = root / "results"
    output.mkdir()
    environment = dict(os.environ)
    environment["NXF_HOME"] = str(root / "nxf-home")
    environment["NXF_CACHE_DIR"] = str(root / "nxf-cache")
    command = [
        "nextflow",
        "-C",
        str(FIXTURE / "nextflow.config"),
        "run",
        str(FIXTURE / "main.nf"),
        "-stub-run",
        "--fixture_root",
        str(fixture),
        "--outdir",
        str(output),
        "--cache_root",
        str(root / "cache"),
    ]
    for resume in (False, True):
        completed = subprocess.run(
            [*command[:5], *(["-resume"] if resume else []), *command[5:]],
            cwd=REPOSITORY,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "reviewed reopening stub failed:\n"
                f"{completed.stdout}\n{completed.stderr}"
            )
        with (output / "pipeline_info/trace.tsv").open(newline="") as stream:
            attempts = tuple(
                row
                for row in csv.DictReader(stream, delimiter="\t")
                if row["process"].split(":")[-1] == "RUN_PHASE3_NO_A_FIRST_COPY"
            )
        expected_status = "CACHED" if resume else "COMPLETED"
        if len(attempts) != 1 or attempts[0]["status"] != expected_status:
            raise RuntimeError(
                "reviewed reopening scheduled an unexpected native attempt set"
            )
        hypothesis_id = plan.plan.reopened_hypothesis_ids[0]
        if hypothesis_id not in attempts[0]["tag"]:
            raise RuntimeError(
                "Nextflow did not execute the reviewer-selected hypothesis"
            )
        if not (output / "phase3_owned_a_review_stub_no_a_crystal").is_dir():
            raise RuntimeError(
                "reviewed reopening did not reach its next owned A checkpoint"
            )
    _run_known_control_route(root / "known-control")


def _run_known_control_route(root: Path) -> None:
    """Validate real reviewed authority through the production qualification entry."""

    root.mkdir()
    mtz = root / "input.mtz"
    mtz.write_bytes(b"synthetic diffraction for a metadata-only stub")
    identity = _identity(
        {
            "crystal_artifacts": (
                ExecutionArtifactIdentity.from_content(
                    scope="crystal",
                    owner_id="9ECN",
                    role="mtz",
                    sha256=sha256_file(mtz),
                    size_bytes=mtz.stat().st_size,
                ),
            )
        }
    )
    atomic_write_json(
        root / "execution_identity.json", identity.model_dump(mode="json")
    )
    request, selected = _case(
        root, status=ExecutionStatus.COMPLETED_HIT, packed=True, crystal_id="9ECN"
    )
    reviewed = _reviewed_request(
        request,
        (selected,),
        execution_identity_id=identity.execution_identity_id,
    )
    plan = plan_batch_localisation_reopen(reviewed)
    paths = {}
    for name in PATH_FIELDS:
        if name == "no_a_expansion_plan":
            path = plan.plan_json.parent
        elif name == "execution_identity":
            path = root / "execution_identity.json"
        elif name == "mtz":
            path = mtz
        else:
            path = root / f"{name}.json"
            path.write_text("{}\n")
        paths[name] = path.relative_to(root).as_posix()
    manifest = root / "known-control.json"
    atomic_write_json(
        manifest,
        {
            "schema_version": "1.0",
            "crystal_id": "9ECN",
            "parent_run_id": "test_parent",
            "paths": paths,
        },
    )
    execution = root.parent / "known-control-execution"
    execution.mkdir()
    output = execution / "results"
    environment = dict(os.environ)
    environment["NXF_HOME"] = str(execution / "nxf-home")
    environment["NXF_CACHE_DIR"] = str(execution / "nxf-cache")
    command = [
        "nextflow",
        "-C",
        str(FIXTURE / "nextflow.config"),
        "run",
        str(REPOSITORY / "qualification.nf"),
        "-stub-run",
        "--qualification_stage",
        "known_control_reopening",
        "--known_control_inputs",
        str(manifest),
        "--source_commit",
        identity.source_commit,
        "--phenix_manifest",
        str(root / paths["phenix_manifest"]),
        "--outdir",
        str(output),
        "--cache_root",
        str(execution / "cache"),
    ]
    for resume in (False, True):
        result = subprocess.run(
            [*command, *(["-resume"] if resume else [])],
            cwd=REPOSITORY,
            env=environment,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise RuntimeError(
                f"known-control qualification failed:\n{result.stdout}\n{result.stderr}"
            )
        with (output / "pipeline_info/trace.tsv").open(newline="") as stream:
            rows = tuple(csv.DictReader(stream, delimiter="\t"))
        if len(rows) != 4 or any(
            row["status"] != ("CACHED" if resume else "COMPLETED") for row in rows
        ):
            raise RuntimeError(
                "known-control dispatch or cached replay differs: "
                + repr([(row["process"], row["status"]) for row in rows])
            )
        if not (output / "phase3_owned_a_review_9ECN").is_dir():
            raise RuntimeError("known-control did not reach its owned review")
    document = json.loads(manifest.read_text())
    document["crystal_id"] = "unknown_case"
    atomic_write_json(manifest, document)
    rejected = subprocess.run(
        [*command, "-resume"],
        cwd=REPOSITORY,
        env=environment,
        capture_output=True,
        text=True,
    )
    if rejected.returncode == 0:
        raise RuntimeError("known-control route admitted an unknown crystal")


def main() -> int:
    with tempfile.TemporaryDirectory(
        prefix="nf-gtd-reviewed-reopen-", dir="/tmp"
    ) as temporary:
        run_reviewed_reopening_stub(Path(temporary) / "qualification")
    print("Reviewed JSON, staging, no-A Nextflow dispatch and cached replay passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
