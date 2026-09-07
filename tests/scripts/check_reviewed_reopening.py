"""Validate reviewed JSON authority before exercising the existing no-A graph."""

import csv
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from genome_to_diffraction.localisation import plan_batch_localisation_reopen
from genome_to_diffraction.status import ExecutionStatus
from tests.unit.test_localisation_reopen import _case, _reviewed_request

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


def main() -> int:
    with tempfile.TemporaryDirectory(
        prefix="nf-gtd-reviewed-reopen-", dir="/tmp"
    ) as temporary:
        run_reviewed_reopening_stub(Path(temporary) / "qualification")
    print("Reviewed JSON, staging, no-A Nextflow dispatch and cached replay passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
