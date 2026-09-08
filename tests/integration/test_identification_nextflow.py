"""Exercise real Nextflow preparation and the explicit non-scientific MR stub."""

import csv
import json
import os
import subprocess
from pathlib import Path

import pytest

from genome_to_diffraction.checksums import atomic_write_json
from genome_to_diffraction.hpc.identification_inputs import execution_cases
from tests.support.identification_fixture import (
    materialise_afdb_identification_fixture,
    materialise_identification_fixture,
)

REPOSITORY = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("predicted_model", [False, True])
def test_identification_nextflow_fans_out_only_ready_cases(
    tmp_path: Path, predicted_model: bool
) -> None:
    factory = (
        materialise_afdb_identification_fixture
        if predicted_model
        else materialise_identification_fixture
    )
    root, plan = factory(tmp_path)
    selected = tmp_path / "execution_cases.json"
    atomic_write_json(
        selected, [c.model_dump(mode="json") for c in execution_cases(plan)]
    )
    config = tmp_path / "stub.config"
    config.write_text(
        "process { withName: RUN_IDENTIFICATION_PHASER "
        "{ cpus = 1; memory = '1 GB' } }\n"
    )
    out = tmp_path / "results"
    (tmp_path / "unused_stub_manifest.json").write_text("{}\n")
    environment = {
        **os.environ,
        "NXF_ANSI_LOG": "false",
        "NXF_DISABLE_CHECK_LATEST": "true",
        "NXF_HOME": str(tmp_path / "nxf-home"),
        "NXF_SYNTAX_PARSER": "v2",
    }
    result = subprocess.run(
        [
            "nextflow",
            "-log",
            str(tmp_path / "nextflow.log"),
            "run",
            str(REPOSITORY / "qualification.nf"),
            "--qualification_stage",
            "identification_screen",
            "-qs",
            "4",
            "-stub-run",
            "-c",
            str(config),
            "--identification_inputs",
            str(root),
            "--identification_cases",
            str(selected),
            "--identification_input_id",
            "synthetic_input",
            "--phenix_manifest",
            str(tmp_path / "unused_stub_manifest.json"),
            "--outdir",
            str(out),
            "--cache_root",
            str(tmp_path / "cache"),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "capacity=4;" in (tmp_path / "nextflow.log").read_text()
    case = plan.cases[0]
    record = json.loads((out / "mr" / case.case_id / "run.json").read_text())
    assert record["status"] == "stub_not_scientific"
    assert record["identity_accepted"] is False
    prep = json.loads(
        (out / "prepared" / case.case_id / "preparation.json").read_text()
    )
    assert prep["status"] == ("stub_not_scientific" if predicted_model else "prepared")
    if predicted_model:
        assert not (out / "prepared" / case.case_id / "model.pdb").exists()
    trace = list(
        csv.DictReader((out / "pipeline_info/trace.tsv").open(), delimiter="\t")
    )
    assert len(trace) == 2
    assert all(row["status"] == "COMPLETED" and row["exit"] == "0" for row in trace)
    assert len(list((out / "mr").iterdir())) == 1
    if predicted_model:
        (tmp_path / "unused_stub_manifest.json").write_text('{"changed":true}\n')
        changed = subprocess.run(
            [*result.args, "-resume"],
            cwd=tmp_path,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        assert changed.returncode == 0, changed.stdout + changed.stderr
        with (out / "pipeline_info/trace.tsv").open() as handle:
            changed_trace = list(csv.DictReader(handle, delimiter="\t"))
        assert len(changed_trace) == 2
        assert all(row["status"] == "COMPLETED" for row in changed_trace)
