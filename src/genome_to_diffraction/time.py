"""Timezone-safe timestamp helpers."""

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return the current timezone-aware UTC time."""

    return datetime.now(UTC)


def utc_now_iso() -> str:
    """Return the current UTC time in second-precision ISO-8601 form."""

    return utc_now().isoformat(timespec="seconds").replace("+00:00", "Z")
