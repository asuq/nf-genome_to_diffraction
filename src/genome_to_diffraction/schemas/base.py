"""Shared primitives for versioned data contracts.

Contracts are strict because misspelled scientific fields must fail loudly. Paths
remain serialised as strings; execution layers resolve and checksum them before use.
"""

import json
from datetime import UTC, datetime
from typing import Annotated, Any, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field
from pydantic.config import ExtraValues


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
        allow_inf_nan=False,
        extra="forbid",
        frozen=True,
        # Programmatic construction may use explicit Python-compatible values.
        # JSON wire input is forced through strict JSON-mode validation below.
        strict=False,
        validate_default=True,
    )

    @classmethod
    def model_validate_json(
        cls,
        json_data: str | bytes | bytearray,
        *,
        strict: bool | None = None,
        extra: ExtraValues | None = None,
        context: Any | None = None,
        by_alias: bool | None = None,
        by_name: bool | None = None,
    ) -> Self:
        """Validate one unambiguous finite JSON wire document in JSON mode."""

        if strict is False:
            raise ValueError("contract JSON validation cannot disable strict mode")
        from genome_to_diffraction.schemas.io import (
            ContractLoadError,
            parse_json_document,
        )

        try:
            payload = (
                json_data
                if isinstance(json_data, str)
                else bytes(json_data).decode("utf-8")
            )
        except UnicodeDecodeError as error:
            raise ContractLoadError(
                f"{cls.__name__}:/: contract JSON is not valid UTF-8"
            ) from error
        document = parse_json_document(payload, label=cls.__name__)
        normalised = json.dumps(
            document,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        )
        return super().model_validate_json(
            normalised,
            strict=True,
            extra=extra,
            context=context,
            by_alias=by_alias,
            by_name=by_name,
        )
