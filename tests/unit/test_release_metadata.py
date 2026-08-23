"""Release-boundary metadata consistency checks."""

import re
import tomllib
from pathlib import Path

from genome_to_diffraction import __version__

REPOSITORY = Path(__file__).resolve().parents[2]
RELEASE_VERSION = "0.2.0"


def test_release_metadata_and_documentation_are_consistent() -> None:
    pyproject = tomllib.loads(
        (REPOSITORY / "pyproject.toml").read_text(encoding="utf-8")
    )
    pixi = tomllib.loads((REPOSITORY / "pixi.toml").read_text(encoding="utf-8"))
    nextflow = (REPOSITORY / "nextflow.config").read_text(encoding="utf-8")
    match = re.search(r"^\s*version\s*=\s*'([^']+)'$", nextflow, re.MULTILINE)
    changelog = (REPOSITORY / "CHANGELOG.md").read_text(encoding="utf-8")
    release_notes = REPOSITORY / "docs/releases/v0.2.0.md"

    assert match is not None
    assert {
        __version__,
        pyproject["project"]["version"],
        pixi["workspace"]["version"],
        match.group(1),
    } == {RELEASE_VERSION}
    assert "## 0.2.0 - 2026-08-23" in changelog
    assert release_notes.is_file()
    assert "P6_EVIDENCE_PENDING" not in release_notes.read_text(encoding="utf-8")
