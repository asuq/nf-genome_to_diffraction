"""Exercise the two-stage comparison graph and cache with real empty-case tasks."""

import csv
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

from genome_to_diffraction.benchmarks.m6_comparison_results import (
    evaluate_m6_comparison_results,
)
from tests.unit.test_m6_comparison import PHENIX, ROOT, _plan


def _run(command: list[str], environment: dict[str, str]) -> None:
    completed = subprocess.run(
        command, cwd=ROOT, env=environment, capture_output=True, text=True, check=False
    )
    if completed.returncode:
        raise RuntimeError(
            f"M6 comparison graph failed:\n{completed.stdout}\n{completed.stderr}"
        )


def _trace(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def main() -> int:
    """Require every empty case/arm, no native work and an exact cached replay."""

    with tempfile.TemporaryDirectory(
        prefix="nf-gtd-m6-comparison-", dir="/tmp"
    ) as temporary:
        root = Path(temporary)
        plan = _plan(root)
        config = root / "nextflow.config"
        config.write_text(
            "\n".join(
                [
                    "process.executor = 'local'",
                    "process.cpus = 1",
                    "process.memory = '512 MB'",
                    "process.time = '5 min'",
                    "process.maxForks = 4",
                    "trace.enabled = true",
                    "trace.overwrite = true",
                    "trace.fields = 'task_id,process,name,status,hash,workdir,exit'",
                    'trace.file = "${params.outdir}/pipeline_info/trace.tsv"',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        environment = dict(os.environ)
        environment.update(
            NXF_HOME=str(root / "nxf-home"),
            NXF_ANSI_LOG="false",
            NXF_DISABLE_CHECK_LATEST="true",
            NXF_SYNTAX_PARSER="v2",
        )
        initial = root / "initial"
        command = [
            "nextflow",
            "-log",
            str(root / "initial.log"),
            "-C",
            str(config),
            "run",
            str(ROOT / "qualification.nf"),
            "--qualification_stage",
            "m6_comparison_initial",
            "--comparison_root",
            str(plan),
            "--software_lock",
            str(ROOT / "pixi.lock"),
            "--phenix_manifest",
            str(PHENIX),
            "--outdir",
            str(initial),
            "-work-dir",
            str(root / "work-initial"),
        ]
        _run(command, environment)
        frozen = initial / "comparison_advancement"
        record = frozen / "comparison_advancement.json"
        payload = json.loads(record.read_text())
        assert payload["continuation_chain_count"] == 0
        assert len(payload["arms"]) == 48
        trace = _trace(initial / "pipeline_info/trace.tsv")
        counts = Counter(row["process"].split(":")[-1] for row in trace)
        assert counts == {
            "M6_VALIDATE_COMPARISON": 1,
            "M6_COMPARISON_SELECT": 48,
            "M6_COMPARISON_FREEZE": 1,
        }
        assert {row["status"] for row in trace} == {"COMPLETED"}
        before = record.read_bytes()
        _run([*command, "-resume"], environment)
        assert {
            row["status"] for row in _trace(initial / "pipeline_info/trace.tsv")
        } == {"CACHED"}
        assert record.read_bytes() == before
        continuation = root / "continuation"
        _run(
            [
                "nextflow",
                "-log",
                str(root / "continuation.log"),
                "-C",
                str(config),
                "run",
                str(ROOT / "qualification.nf"),
                "--qualification_stage",
                "m6_comparison_continuation",
                "--comparison_root",
                str(frozen),
                "--software_lock",
                str(ROOT / "pixi.lock"),
                "--phenix_manifest",
                str(PHENIX),
                "--outdir",
                str(continuation),
                "-work-dir",
                str(root / "work-continuation"),
            ],
            environment,
        )
        result = json.loads(
            (continuation / "comparison_results/comparison_results.json").read_text()
        )
        assert len(result["cases"]) == 48
        assert result["full_63_case_m6_still_required"] is True
        counts = Counter(
            row["process"].split(":")[-1]
            for row in _trace(continuation / "pipeline_info/trace.tsv")
        )
        assert counts == {
            "M6_VALIDATE_COMPARISON": 1,
            "M6_EMPTY_FINALISTS": 48,
            "M6_ASSEMBLE_EMPTY_CASE": 48,
            "M6_COMPARISON_COLLECT": 1,
        }
        retained = continuation / "comparison_results"
        (retained / "cases/M6C001/A/case_record.json").write_text("changed\n")
        try:
            evaluate_m6_comparison_results(
                results_root=retained,
                protocol_path=ROOT / "benchmarks/m6/protocol.yaml",
                private_truth_map=root / "must-not-be-opened.json",
                output=root / "evaluation",
            )
        except ValueError as error:
            assert "changed before truth joining" in str(error)
        else:
            raise AssertionError(
                "comparison truth join accepted changed native evidence"
            )
    print(
        "M6 comparison accounting, cache and truth-boundary checks passed; "
        "no native science was run."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
