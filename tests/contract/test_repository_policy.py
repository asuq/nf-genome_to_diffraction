"""Contract tests for the intentionally narrow foundation repository."""

from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]


def test_documentation_tree_is_not_present() -> None:
    assert not (REPOSITORY / "docs").exists()
    assert not (REPOSITORY / "prompts").exists()
    assert not (REPOSITORY / "scaffold").exists()


def test_packaging_only_handoff_files_are_absent() -> None:
    for name in (
        "DEVELOPER_SPECIFICATION.md",
        "FILE_INDEX.txt",
        "PACKAGE_MANIFEST.json",
        "SHA256SUMS",
    ):
        assert not (REPOSITORY / name).exists()


def test_remote_sequence_submission_defaults_off() -> None:
    crystal = (REPOSITORY / "examples" / "crystal_manifest.json").read_text(
        encoding="utf-8"
    )
    assert '"allow_remote_sequence_submission": false' in crystal
