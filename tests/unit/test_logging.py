"""Unit tests for structured logging."""

import json
import logging

import pytest

from genome_to_diffraction.logging import configure_logging, parse_log_level


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


def test_human_logging_retains_structured_context(
    capsys: pytest.CaptureFixture[str],
) -> None:
    logger = configure_logging(
        level=logging.INFO, logger_name="test.human", log_format="human"
    )
    logger.info("reading", extra={"records": 42, "stage": "catalogue"})
    assert capsys.readouterr().err.strip() == (
        "info: reading [records=42 stage=catalogue]"
    )


def test_parse_log_level_is_explicit() -> None:
    assert parse_log_level("warning") == logging.WARNING
    with pytest.raises(ValueError, match="unknown log level"):
        parse_log_level("verbose")
