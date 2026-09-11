"""Real M6 process staging with same-basename, independently owned inputs.

Only the scientific CLI is simulated. The locked Nextflow runtime executes the
actual process definitions, stages files and checks fresh/resume/mutation paths.
This is a wiring regression, not native scientific or benchmark acceptance.
"""

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from genome_to_diffraction.benchmarks.m6_execution import (
    M6ChildOutputEvidenceRequest,
    collect_m6_child_output_evidence,
)
from genome_to_diffraction.benchmarks.public_control import PublicControlError
from tests.scripts.check_nextflow import _environment

REPOSITORY = Path(__file__).resolve().parents[2]


def test_m6_collections_keep_distinct_batches_and_cases_on_stage_and_resume(
    tmp_path: Path,
) -> None:
    inputs: dict[str, list[Path]] = {}
    for kind, basename in (
        ("pdb", "m6_pdb_bundle"),
        ("foldseek", "m6_foldseek_bundle"),
        ("case", "m6_case_evidence"),
    ):
        inputs[kind] = []
        for index in range(2):
            root = tmp_path / "original" / f"{kind}-{index}" / basename
            root.mkdir(parents=True)
            (root / "record.txt").write_text(f"{kind}-{index}\n", encoding="ascii")
            inputs[kind].append(root)
    for name in ("catalogue", "batch-plan", "runner", "published"):
        (tmp_path / name).mkdir()
    for name in ("protocol.yaml", "database.json", "phenix.json"):
        (tmp_path / name).write_text("fixture\n", encoding="ascii")

    simulator_bin = tmp_path / "simulator-bin"
    simulator_bin.mkdir()
    launcher = simulator_bin / "genome-to-diffraction"
    launcher.write_text(
        f"#!{sys.executable}\n"
        "import hashlib, json, pathlib, sys\n"
        "args = sys.argv[1:]\n"
        "mode = args[args.index('benchmark') + 1]\n"
        "kinds = ('pdb', 'foldseek') if mode == 'partition-m6-discovery' "
        "else ('case',)\n"
        "assert mode in ('partition-m6-discovery', 'aggregate-m6-track')\n"
        "records = {}\n"
        "for kind in kinds:\n"
        "    flag = '--case-evidence' if kind == 'case' else '--' + kind + '-result'\n"
        "    paths = [pathlib.Path(args[i + 1]) for i, value in enumerate(args) "
        "if value == flag]\n"
        "    assert len(paths) == 2 and len({p.resolve() for p in paths}) == 2, "
        "'staged inputs alias'\n"
        "    records[kind] = [{'path': str(p), 'original': str(p.resolve()),\n"
        "        'contents': (p / 'record.txt').read_text(),\n"
        "        'sha256': hashlib.sha256((p / 'record.txt').read_bytes()).hexdigest()}"
        " "
        "for p in paths]\n"
        "    assert len({row['contents'] for row in records[kind]}) == 2\n"
        "output = pathlib.Path(args[args.index('--outdir') + 1])\n"
        "output.mkdir()\n"
        "if mode == 'partition-m6-discovery':\n"
        "    (output / 'pdb_bundle').mkdir()\n"
        "    (output / 'foldseek_bundle').mkdir()\n"
        "(output / 'staging.json').write_text(json.dumps(records))\n",
        encoding="ascii",
    )
    launcher.chmod(0o755)
    lists = {
        kind: "[" + ", ".join(f"file('{path}')" for path in paths) + "]"
        for kind, paths in inputs.items()
    }
    entrypoint = tmp_path / "main.nf"
    entrypoint.write_text(
        "nextflow.enable.types = true\n"
        "include { M6_PARTITION_DISCOVERY; M6_AGGREGATE_TRACK } from "
        f"'{REPOSITORY}/modules/local/m6_nextflow_tasks'\n"
        "params { outdir: Path = file('published') }\n"
        "workflow {\n"
        "    M6_PARTITION_DISCOVERY(\n"
        f"        channel.of(['catalogue-key', file('{tmp_path}/catalogue')]),\n"
        f"        file('{tmp_path}/batch-plan'), {lists['pdb']}, {lists['foldseek']})\n"
        f"    M6_AGGREGATE_TRACK({lists['case']}, file('{tmp_path}/runner'),\n"
        f"        file('{tmp_path}/protocol.yaml'), file('{tmp_path}/database.json'),\n"
        f"        file('{tmp_path}/phenix.json'), 'operational', 'native_control')\n"
        "}\n",
        encoding="ascii",
    )
    config = tmp_path / "nextflow.config"
    config.write_text(
        f"params.outdir = '{tmp_path}/published'\n"
        "process.executor = 'local'\n"
        "process.cpus = 1\n"
        "executor.cpus = 2\n"
        "trace.enabled = true\n"
        "trace.overwrite = true\n"
        "trace.file = 'trace.tsv'\n"
        "trace.fields = 'process,status,hash,workdir'\n",
        encoding="ascii",
    )
    environment = _environment(tmp_path / "nxf-home")
    environment["PATH"] = f"{simulator_bin}:{environment['PATH']}"
    command = [
        "nextflow",
        "-C",
        str(config),
        "run",
        str(entrypoint),
        "-ansi-log",
        "false",
        "-w",
        str(tmp_path / "work"),
    ]

    def run(*, resume: bool) -> dict[str, dict[str, str]]:
        result = subprocess.run(
            [*command, *(["-resume"] if resume else [])],
            cwd=tmp_path,
            env=environment,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        with (tmp_path / "trace.tsv").open(encoding="ascii") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        assert len(rows) == 2
        return {row["process"]: row for row in rows}

    first = run(resume=False)
    assert all(row["status"] == "COMPLETED" for row in first.values())
    for process, output, kinds in (
        ("M6_PARTITION_DISCOVERY", "m6_discovery_partition", ("pdb", "foldseek")),
        ("M6_AGGREGATE_TRACK", "m6_scientific", ("case",)),
    ):
        root = Path(first[process]["workdir"])
        record = json.loads((root / output / "staging.json").read_text())
        for kind in kinds:
            assert [row["original"] for row in record[kind]] == [
                str(path.resolve()) for path in inputs[kind]
            ]
            assert len({row["path"] for row in record[kind]}) == 2
    resumed = run(resume=True)
    assert all(row["status"] == "CACHED" for row in resumed.values())
    assert {name: row["hash"] for name, row in first.items()} == {
        name: row["hash"] for name, row in resumed.items()
    }

    # The upstream producer here is explicitly simulated, not a native search.
    # Its genuine files must still pass the production byte-inventory guard.
    first_trace = tmp_path / "simulated-input-first.tsv"
    resume_trace = tmp_path / "simulated-input-resume.tsv"
    for trace, status in ((first_trace, "COMPLETED"), (resume_trace, "CACHED")):
        trace.write_text(
            "process\ttag\tstatus\thash\tworkdir\n"
            + "".join(
                f"M6_SEARCH_FOLDSEEK\tsimulated-{index}\t{status}\t00/{index:06d}\t"
                f"{path.parent}\n"
                for index, path in enumerate(inputs["foldseek"])
            ),
            encoding="ascii",
        )
    baseline = tmp_path / "simulated-input-checksums.json"
    collect_m6_child_output_evidence(
        M6ChildOutputEvidenceRequest(
            track="operational", trace=first_trace, output=baseline
        )
    )
    changed = inputs["foldseek"][1] / "record.txt"
    changed.write_text("foldseek-1 changed-size\n", encoding="ascii")
    mutated = run(resume=True)
    # Nextflow's directory cache is not the scientific checksum authority.
    # Even when scheduling remains cached, changed producer bytes must HOLD.
    assert all(row["status"] == "CACHED" for row in mutated.values())
    rejected = tmp_path / "rejected-input-checksums.json"
    with pytest.raises(PublicControlError, match="missing or changed child outputs"):
        collect_m6_child_output_evidence(
            M6ChildOutputEvidenceRequest(
                track="operational",
                trace=resume_trace,
                baseline=baseline,
                output=rejected,
            )
        )
    assert not rejected.exists()
