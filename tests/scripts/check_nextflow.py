"""Parse and exercise the foundation-only Nextflow entry points."""

import argparse
import os
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]


def _run(
    command: Sequence[str],
    *,
    environment: dict[str, str],
    expected_success: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=REPOSITORY,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    combined = f"{result.stdout}\n{result.stderr}"
    if expected_success and result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(command)}\n{combined}"
        )
    if not expected_success and result.returncode == 0:
        raise RuntimeError(f"command unexpectedly succeeded: {' '.join(command)}")
    return result


def _environment(nxf_home: Path) -> dict[str, str]:
    environment = dict(os.environ)
    environment.update(
        {
            "NXF_AGENT_MODE": "true",
            "NXF_ANSI_LOG": "false",
            "NXF_DISABLE_CHECK_LATEST": "true",
            "NXF_HOME": str(nxf_home),
            "NXF_SYNTAX_PARSER": "v2",
        }
    )
    return environment


def check_syntax() -> None:
    """Run the Nextflow parser/linter over all workflow sources."""

    with tempfile.TemporaryDirectory(
        prefix="nf-genome-to-diffraction-lint-", dir="/tmp"
    ) as temporary:
        environment = _environment(Path(temporary) / "nxf-home")
        _run(["nextflow", "lint", "."], environment=environment)


def _assert_files(root: Path, names: set[str]) -> None:
    actual = {path.name for path in root.rglob("*") if path.is_file()}
    missing = names - actual
    if missing:
        raise RuntimeError(f"missing outputs under {root}: {sorted(missing)}")


def _assert_fail_loud(command: Sequence[str], *, environment: dict[str, str]) -> None:
    result = _run(command, environment=environment, expected_success=False)
    combined = f"{result.stdout}\n{result.stderr}"
    if "foundation_only_not_implemented" not in combined:
        raise RuntimeError(
            "non-stub execution failed without the foundation-only diagnostic:\n"
            f"{combined}"
        )


def check_stubs() -> None:
    """Run both stubs, verify reports/outputs, resume, and fail-loud paths."""

    with tempfile.TemporaryDirectory(
        prefix="nf-genome-to-diffraction-stub-", dir="/tmp"
    ) as temporary:
        temporary_root = Path(temporary)
        environment = _environment(temporary_root / "nxf-home")
        main_out = temporary_root / "main-results"
        database_out = temporary_root / "database-results"
        cache_root = temporary_root / "cache"

        main_command = [
            "nextflow",
            "run",
            "main.nf",
            "-profile",
            "test",
            "-stub-run",
            "-params-file",
            "tests/fixtures/stubs/main_params.yaml",
            "--outdir",
            str(main_out),
            "--cache_root",
            str(cache_root),
        ]
        _run(main_command, environment=environment)
        _assert_files(
            main_out,
            {
                "catalogue_manifest.json",
                "crystal_manifest.json",
                "pipeline_config.yaml",
                "database_manifest.json",
                "phenix_install_manifest.json",
                "report.html",
                "timeline.html",
                "trace.tsv",
                "dag.html",
            },
        )

        resumed = _run([*main_command, "-resume"], environment=environment)
        resumed_output = f"{resumed.stdout}\n{resumed.stderr}".lower()
        if "cached" not in resumed_output:
            raise RuntimeError(
                "resumed stub run did not report cached work:\n" + resumed_output
            )

        database_command = [
            "nextflow",
            "run",
            "prepare_databases.nf",
            "-profile",
            "test",
            "-stub-run",
            "-params-file",
            "tests/fixtures/stubs/database_params.yaml",
            "--outdir",
            str(database_out),
            "--database_root",
            str(REPOSITORY / "tests/fixtures/stubs/database_root"),
        ]
        _run(database_command, environment=environment)
        _assert_files(
            database_out,
            {
                "database_manifest.json",
                "report.html",
                "timeline.html",
                "trace.tsv",
                "dag.html",
            },
        )

        _assert_fail_loud(
            [part for part in main_command if part != "-stub-run"],
            environment=environment,
        )
        _assert_fail_loud(
            [part for part in database_command if part != "-stub-run"],
            environment=environment,
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--syntax", action="store_true")
    mode.add_argument("--stub", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the requested Nextflow foundation check."""

    args = _build_parser().parse_args(argv)
    try:
        if args.syntax:
            check_syntax()
        else:
            check_stubs()
    except (OSError, RuntimeError) as error:
        print(error, file=sys.stderr)
        return 1
    print("Nextflow foundation check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
