"""Exercise the fixed B--F beam's typed-empty and cached-resume path."""

import csv
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
FIXTURE = REPOSITORY / "tests/fixtures/stubs/phase3_composition_beam"


def _run(command: list[str], environment: dict[str, str]) -> None:
    completed = subprocess.run(
        command,
        cwd=REPOSITORY,
        env=environment,
        check=False,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Phase III composition-beam stub failed:\n"
            f"{completed.stdout}\n{completed.stderr}"
        )


def _trace(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def main() -> int:
    """Require one typed terminal depth and byte-identical cached replay."""

    with tempfile.TemporaryDirectory(
        prefix="nf-genome-to-diffraction-phase3-beam-",
        dir="/tmp",
    ) as temporary:
        root = Path(temporary)
        output = root / "results"
        output.mkdir()
        cache = root / "cache"
        cache.mkdir()
        nxf_home = root / "nxf-home"
        nxf_home.mkdir()
        environment = dict(os.environ)
        environment["NXF_HOME"] = str(nxf_home)
        command = [
            "nextflow",
            "-C",
            str(FIXTURE / "nextflow.config"),
            "run",
            str(FIXTURE / "main.nf"),
            "-stub-run",
            "--fixture_root",
            str(FIXTURE),
            "--outdir",
            str(output),
            "--cache_root",
            str(cache),
        ]
        _run(command, environment)
        terminal = output / "composition_beam_stub_crystal_depth2"
        result = terminal / "composition_beam_depth_result.json"
        if not result.is_file() or '"status":"terminal"' not in result.read_text():
            raise RuntimeError("composition beam did not publish its typed empty stop")
        if not (output / "phase3_owned_a_review_stub_no_a_crystal").is_dir():
            raise RuntimeError("no-A expansion did not publish an owned review package")
        if not (output / "phase3_pass2_review_stub_crystal").is_dir():
            raise RuntimeError("composition beam did not publish final review packages")
        first = _trace(output / "pipeline_info/trace.tsv")
        processes = {row["process"].split(":")[-1] for row in first}
        if processes != {
            "PLAN_PHASE3_COMPOSITION_DEPTH",
            "COLLECT_PHASE3_COMPOSITION_DEPTH",
            "BUILD_PHASE3_PASS2_REVIEW_PACKAGES",
            "RUN_PHASE3_NO_A_FIRST_COPY",
            "BUILD_PHASE3_NO_A_REVIEW",
            "BUILD_PHASE3_NO_A_OWNED_REVIEW",
        } or {row["status"] for row in first} != {"COMPLETED"}:
            raise RuntimeError("composition beam scheduled an unexpected stub graph")
        before = result.read_bytes()
        _run([*command[:5], "-resume", *command[5:]], environment)
        resumed = _trace(output / "pipeline_info/trace.tsv")
        if {row["status"] for row in resumed} != {"CACHED"}:
            raise RuntimeError("composition beam cached replay was incomplete")
        if result.read_bytes() != before:
            raise RuntimeError("composition beam cached replay changed output bytes")
    print("Phase III composition beam stub and cached resume passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
