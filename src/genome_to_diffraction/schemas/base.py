"""Shared primitives for versioned data contracts.

Contracts are strict because misspelled scientific fields must fail loudly. Paths
remain serialised as strings; execution layers resolve and checksum them before use.
"""

from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


def _normalise_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include a UTC offset")
    return value.astimezone(UTC)


UtcTimestamp = Annotated[datetime, AfterValidator(_normalise_utc)]
NonEmptyString = Annotated[str, Field(min_length=1)]
OperatorIdentifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")]
Sha256Hex = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
PositiveFloat = Annotated[float, Field(gt=0)]
PositiveInt = Annotated[int, Field(gt=0)]


class ContractModel(BaseModel):
    """Base for immutable, strict versioned contract records."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        # JSON Schema validation enforces wire types before model construction.
        # Pydantic must still parse ISO timestamps and string-backed enums.
        strict=False,
        validate_default=True,
    )
