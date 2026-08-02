"""Unit tests for checksums and atomic writes."""

import hashlib
import json
import logging
from pathlib import Path

import pytest

from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)


def test_sha256_file_known_vector_and_path_with_spaces(tmp_path: Path) -> None:
    source = tmp_path / "input with spaces.txt"
    source.write_bytes(b"abc")
    assert sha256_file(source, chunk_size=1) == hashlib.sha256(b"abc").hexdigest()


def test_sha256_file_rejects_non_positive_chunk_size(tmp_path: Path) -> None:
    source = tmp_path / "input.txt"
    source.write_text("content", encoding="utf-8")
    with pytest.raises(ValueError, match="positive"):
        sha256_file(source, chunk_size=0)
    with pytest.raises(ValueError, match="positive"):
        sha256_file(source, log_interval_bytes=0)


def test_sha256_file_emits_bounded_structured_progress_for_large_files(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    source = tmp_path / "large fixture.bin"
    source.write_bytes(b"abcdef")
    logger = logging.getLogger("tests.checksums")

    with caplog.at_level(logging.INFO, logger=logger.name):
        digest = sha256_file(
            source,
            chunk_size=2,
            logger=logger,
            log_interval_bytes=2,
        )

    assert digest == hashlib.sha256(b"abcdef").hexdigest()
    assert [record.message for record in caplog.records] == [
        "checksum started",
        "checksum progress",
        "checksum progress",
        "checksum progress",
        "checksum complete",
    ]
    assert caplog.records[-1].__dict__["processed_bytes"] == 6
    assert caplog.records[-1].__dict__["total_bytes"] == 6


def test_sha256_file_can_report_byte_progress(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "progress.bin"
    source.write_bytes(b"abcdef")
    sha256_file(source, chunk_size=2, progress=True, description="Digest fixture")
    assert "Digest fixture" in capsys.readouterr().err


def test_atomic_write_text_replaces_existing_file(tmp_path: Path) -> None:
    destination = tmp_path / "nested folder" / "output.txt"
    atomic_write_text(destination, "first")
    atomic_write_text(destination, "second")
    assert destination.read_text(encoding="utf-8") == "second"
    assert list(destination.parent.glob("*.tmp")) == []


def test_atomic_write_json_is_sorted_and_terminated(tmp_path: Path) -> None:
    destination = tmp_path / "record.json"
    atomic_write_json(destination, {"z": 2, "a": 1})
    payload = destination.read_text(encoding="utf-8")
    assert payload.endswith("\n")
    assert json.loads(payload) == {"a": 1, "z": 2}
    assert payload.index('"a"') < payload.index('"z"')
