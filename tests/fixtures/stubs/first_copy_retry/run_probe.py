"""One real first-copy CLI call with only native Phenix mocked, never science.

Nextflow owns attempts. The public control's authenticated eight-thread request
is fixture data; no eight-CPU/native task runs here. Each invocation uses one
Python process and the caller's single-thread numerical environment.
"""

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from tests.unit.test_first_copy_retry import first_copy_arguments
from tests.unit.test_phaser_adapter import (
    NO_SOLUTION_LOG,
    _fake_runtime,
    _phase3_inputs,
)

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.cli import main as application_main


def main() -> int:
    """Propagate the actual public CLI status after saving this test-only receipt."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=("recover", "exhausted", "no_hit", "tool_failure"),
        required=True,
    )
    parser.add_argument("--attempt", type=int, choices=(1, 2), required=True)
    args = parser.parse_args()
    request = replace(
        _phase3_inputs(Path.cwd() / "inputs"),
        output_directory=Path.cwd() / "native-output",
    )
    native_exit = (
        75
        if args.scenario == "exhausted"
        or (args.scenario == "recover" and args.attempt == 1)
        else 2
        if args.scenario == "tool_failure"
        else 0
    )
    log = NO_SOLUTION_LOG if native_exit == 0 else "controlled native failure\n"
    with pytest.MonkeyPatch.context() as patch:
        calls = _fake_runtime(
            patch, log_text=log, returncode=native_exit, capture_bytes=log.encode()
        )
        status = application_main(first_copy_arguments(request))
    if len(calls) != 1:
        raise RuntimeError("retry probe did not execute exactly one mocked native call")
    result_path = request.output_directory / "normalised_mr_result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    Path("attempt-result.json").write_text(
        json.dumps(
            {
                "mocked_native_execution": True,
                "scenario": args.scenario,
                "attempt": args.attempt,
                "native_exit": native_exit,
                "cli_exit": status,
                "execution_status": result["execution_status"],
                "result_sha256": sha256_file(result_path),
                "hypothesis_id": request.hypothesis_id,
                "requested_threads": request.threads,
                "scientific_input_sha256": {
                    "hypotheses": sha256_file(request.hypotheses_jsonl),
                    "sequence_groups": sha256_file(request.sequence_groups_jsonl),
                    "mtz": sha256_file(request.mtz),
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="ascii",
    )
    return status


if __name__ == "__main__":
    sys.exit(main())
