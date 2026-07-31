"""Unit tests for structured logging."""

import json
import logging

import pytest

from genome_to_diffraction.logging import configure_logging


def test_configure_logging_emits_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    logger = configure_logging(level=logging.INFO, logger_name="test.foundation")
    logger.info("ready", extra={"stage": "foundation"})
    captured = capsys.readouterr()
    record = json.loads(captured.err)
    assert record["level"] == "info"
    assert record["logger"] == "test.foundation"
    assert record["message"] == "ready"
    assert record["stage"] == "foundation"
    assert record["timestamp"].endswith("Z")
