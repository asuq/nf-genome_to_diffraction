"""Unit tests for package metadata and time helpers."""

from datetime import datetime

from genome_to_diffraction import __version__
from genome_to_diffraction.time import utc_now, utc_now_iso


def test_version_is_v0_2_release() -> None:
    assert __version__ == "0.2.0"


def test_utc_now_is_timezone_aware() -> None:
    value = utc_now()
    offset = value.utcoffset()
    assert offset is not None
    assert offset.total_seconds() == 0


def test_utc_now_iso_is_parseable_and_uses_z_suffix() -> None:
    value = utc_now_iso()
    assert value.endswith("Z")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert parsed.utcoffset() is not None
