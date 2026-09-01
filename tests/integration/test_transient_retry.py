"""Exercise the actual bounded Nextflow infrastructure retry boundary."""

import csv
import os
import subprocess
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]


def _run_retry_probe(
    *,
    root: Path,
    scenario: str,
) -> tuple[subprocess.CompletedProcess[str], tuple[dict[str, str], ...]]:
    output = root / scenario / "results"
    environment = dict(os.environ)
    environment.update(
        {
            "NXF_AGENT_MODE": "true",
            "NXF_ANSI_LOG": "false",
            "NXF_DISABLE_CHECK_LATEST": "true",
            "NXF_HOME": str(root / "nxf-home"),
            "NXF_SYNTAX_PARSER": "v2",
        }
    )
    result = subprocess.run(
        [
            "nextflow",
            "-C",
            "conf/base.config",
            "run",
            "tests/fixtures/stubs/transient_retry/main.nf",
            "--scenario",
            scenario,
            "--outdir",
            str(output),
            "--cache_root",
            str(root / scenario / "cache"),
        ],
        cwd=REPOSITORY,
        env=environment,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    trace = output / "pipeline_info" / "trace.tsv"
    assert trace.is_file(), (
        f"Nextflow trace is missing: {result.stdout}\n{result.stderr}"
    )
    with trace.open(encoding="utf-8", newline="") as handle:
        rows = tuple(csv.DictReader(handle, delimiter="\t"))
    return result, rows


def test_transient_retries_once_but_contract_failure_never_retries(
    tmp_path: Path,
) -> None:
    transient, transient_rows = _run_retry_probe(root=tmp_path, scenario="transient")
    assert transient.returncode == 0, f"{transient.stdout}\n{transient.stderr}"
    assert tuple(row["attempt"] for row in transient_rows) == ("1", "2")
    assert tuple(row["exit"] for row in transient_rows) == ("75", "0")
    assert (tmp_path / "transient/results/result.txt").read_text(encoding="ascii") == (
        "2\n"
    )

    contract, contract_rows = _run_retry_probe(root=tmp_path, scenario="contract")
    assert contract.returncode != 0
    assert len(contract_rows) == 1
    assert contract_rows[0]["attempt"] == "1"
    assert contract_rows[0]["exit"] == "65"
