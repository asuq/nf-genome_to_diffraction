"""Canonical serialisation and content-derived identifiers.

Sequence identity is the SHA-256 digest of canonical amino-acid bytes. Other
objects use RFC 8785 JSON so ordering and insignificant whitespace cannot change
their identity.
"""

import hashlib
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

import rfc8785
from pydantic import BaseModel

type CanonicalValue = (
    bool | int | float | str | list[CanonicalValue] | dict[str, CanonicalValue] | None
)

_PREFIX = re.compile(r"^[a-z][a-z0-9]*_$")


def canonical_sequence(sequence: str) -> str:
    """Uppercase a sequence and remove whitespace without repairing residues."""

    canonical = "".join(sequence.split()).upper()
    if not canonical:
        raise ValueError("sequence must not be empty")
    try:
        canonical.encode("ascii")
    except UnicodeEncodeError as error:
        raise ValueError("sequence must contain ASCII residue symbols") from error
    return canonical


def sequence_digest(sequence: str) -> str:
    """Return the full SHA-256 digest of canonical amino-acid bytes."""

    return hashlib.sha256(canonical_sequence(sequence).encode("ascii")).hexdigest()


def sequence_group_id(sequence: str) -> str:
    """Return the immutable exact-sequence group identifier."""

    return f"seq_{sequence_digest(sequence)}"


def _canonical_value(value: object) -> CanonicalValue:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("canonical timestamps must be timezone-aware")
        return (
            value.astimezone(UTC)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, Enum):
        return _canonical_value(value.value)
    if isinstance(value, BaseModel):
        return _canonical_value(
            value.model_dump(mode="python", by_alias=True, exclude_none=False)
        )
    if isinstance(value, Mapping):
        converted: dict[str, CanonicalValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("canonical JSON object keys must be strings")
            converted[key] = _canonical_value(item)
        return converted
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray | str):
        return [_canonical_value(item) for item in value]
    raise TypeError(f"unsupported canonical JSON value: {type(value).__name__}")


def canonical_json_bytes(value: object) -> bytes:
    """Serialise *value* using the JSON Canonicalization Scheme (RFC 8785)."""

    return rfc8785.dumps(_canonical_value(value))


def canonical_json_text(value: object) -> str:
    """Return canonical UTF-8 JSON text."""

    return canonical_json_bytes(value).decode("utf-8")


def canonical_digest(value: object) -> str:
    """Return the full SHA-256 digest of canonical JSON bytes."""

    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def identity_view(value: object, *, exclude_fields: frozenset[str]) -> CanonicalValue:
    """Build an explicit identity payload while excluding non-identity fields.

    Callers must name exclusions; there is deliberately no global guess about
    whether a timestamp or path is scientifically meaningful.
    """

    canonical = _canonical_value(value)

    def remove_fields(item: CanonicalValue) -> CanonicalValue:
        if isinstance(item, dict):
            return {
                key: remove_fields(child)
                for key, child in item.items()
                if key not in exclude_fields
            }
        if isinstance(item, list):
            return [remove_fields(child) for child in item]
        return item

    return remove_fields(canonical)


def content_id(prefix: str, identity_payload: object) -> str:
    """Create a prefixed full-digest identifier from an explicit identity view."""

    if _PREFIX.fullmatch(prefix) is None:
        raise ValueError("identifier prefix must match ^[a-z][a-z0-9]*_$")
    return f"{prefix}{canonical_digest(identity_payload)}"
