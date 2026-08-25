"""Exercise control-independent catalogue partner search and fixed controls."""

import sys
import tempfile
from collections import Counter
from pathlib import Path

from tests.scripts.check_nextflow import _assert_files, _environment, _read_trace, _run


def _command(root: Path, *, control: bool) -> tuple[list[str], Path]:
    label = "control" if control else "application"
    output = root / f"{label}-results"
    command = [
        "nextflow",
        "run",
        "main.nf",
        "-profile",
        "test",
        "-stub-run",
        "-params-file",
        "tests/fixtures/stubs/main_params.yaml",
        "--analysis_stage",
        "heteromer",
        "--approved_mr_seeds",
        "examples/approvals/approved_mr_seeds.tsv",
        "--outdir",
        str(output),
        "--cache_root",
        str(root / f"{label}-cache"),
    ]
    if control:
        command.extend(
            [
                "--heteromer_control_preparation",
                "tests/fixtures/stubs/approved_partner_search",
            ]
        )
    return command, output


def _counts(output: Path) -> Counter[str]:
    rows = _read_trace(output / "pipeline_info" / "trace.tsv")
    if not rows or any(row["status"] != "COMPLETED" for row in rows):
        raise RuntimeError("heteromer application did not complete every task")
    return Counter(row["process"].split(":")[-1] for row in rows)


def main() -> int:
    """Keep a reviewed catalogue application independent of fixed 6RTZ data."""

    with tempfile.TemporaryDirectory(
        prefix="nf-gtd-heteromer-application-",
        dir="/tmp",
    ) as temporary:
        root = Path(temporary)
        environment = _environment(root / "nxf-home")
        application, application_output = _command(root, control=False)
        _run(application, environment=environment)
        application_counts = _counts(application_output)
        required = (
            "STAGE_APPROVED_MR_SEEDS",
            "BUILD_PARTNER_PLAN",
            "RUN_PLANNED_PARTNER_PHASER",
            "SUMMARIZE_PARTNER_ATTEMPTS",
        )
        if any(application_counts[name] != 1 for name in required):
            raise RuntimeError(
                "control-independent application lost its reviewed partner chain: "
                f"{dict(sorted(application_counts.items()))}"
            )
        if application_counts["RUN_APPROVED_PARTNER_PHASER"] != 0:
            raise RuntimeError("normal application scheduled the fixed 6RTZ control")
        if (application_output / "approved_partner_search").exists():
            raise RuntimeError("normal application published fixed-control evidence")
        _assert_files(
            application_output,
            {
                "validated_mr_seed_decisions.json",
                "partner_search_plan.json",
                "partner_candidates.jsonl",
                "selected_partner_candidate_ids.txt",
                "partner_attempt_summary.json",
                "partner_search_result.json",
            },
        )

        resumed = _run([*application, "-resume"], environment=environment)
        if "cached" not in f"{resumed.stdout}\n{resumed.stderr}".lower():
            raise RuntimeError("control-independent application did not resume")

        control, control_output = _command(root, control=True)
        _run(control, environment=environment)
        control_counts = _counts(control_output)
        if control_counts["RUN_APPROVED_PARTNER_PHASER"] != 1:
            raise RuntimeError("explicit fixed-control execution was not retained")
        if any(control_counts[name] != 1 for name in required):
            raise RuntimeError("fixed control lost the shared catalogue partner chain")
        if not (control_output / "approved_partner_search").is_dir():
            raise RuntimeError("fixed-control result was not retained")

    print("Control-independent heteromer application and fixed control passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
