"""Entry modules must initialise independently of pytest's collection order."""

import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "module",
    [
        "genome_to_diffraction.hpc.unknown_inputs",
        "genome_to_diffraction.execution.composition",
        "genome_to_diffraction.ranking.funnel",
        "genome_to_diffraction.review.reconsideration",
        "genome_to_diffraction.cli",
    ],
)
def test_entry_module_imports_in_fresh_interpreter(module: str) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            (
                "import importlib, sys; "
                "sys.path.insert(0, sys.argv[1]); "
                "importlib.import_module(sys.argv[2])"
            ),
            str(REPOSITORY / "src"),
            module,
        ],
        cwd=REPOSITORY,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
