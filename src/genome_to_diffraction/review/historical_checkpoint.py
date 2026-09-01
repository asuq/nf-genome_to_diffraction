"""Read and verify immutable historical T12.5 review evidence without claims."""

from pathlib import Path, PurePosixPath

from pydantic import BaseModel, Field, ValidationError

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.schemas.v2.review import validate_phase3_review_relative_path
from genome_to_diffraction.status import InputContractError


class HistoricalCheckpointError(InputContractError):
    """An immutable historical review checkpoint is malformed or unsafe."""


class HistoricalCheckpointIdentity(BaseModel):
    """Checksum-bound assets retained by an existing v1 checkpoint."""

    assets: dict[str, str]


class HistoricalCheckpointManifest(BaseModel):
    """Read-only historical checkpoint fields required for retained evidence."""

    schema_version: str
    run_id: str
    package_id: str
    finalist_count: int
    outputs: dict[str, str]
    identity: HistoricalCheckpointIdentity
    crystal_context: dict[str, object] = Field(default_factory=dict)
    matthews_policy: dict[str, object] = Field(default_factory=dict)
    sequence_assignment_model_role: str | None = None


def verify_historical_checkpoint(
    root: Path,
) -> tuple[HistoricalCheckpointManifest, Path]:
    """Validate an existing checkpoint without writing or promoting its claims."""

    if root.is_symlink() or not root.is_dir():
        raise HistoricalCheckpointError("checkpoint directory is absent or unsafe")
    manifest_path = root / "sequence_checkpoint_manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise HistoricalCheckpointError(
            "sequence checkpoint manifest is absent or unsafe"
        )
    try:
        manifest = HistoricalCheckpointManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError, ValueError) as error:
        raise HistoricalCheckpointError(
            f"invalid sequence checkpoint manifest: {error}"
        ) from error

    resolved_root = root.resolve(strict=True)
    for relative, expected in {**manifest.outputs, **manifest.identity.assets}.items():
        try:
            validate_phase3_review_relative_path(relative)
        except ValueError as error:
            raise HistoricalCheckpointError(
                f"checkpoint path is unsafe or escapes package: {relative}"
            ) from error
        path = resolved_root
        for part in PurePosixPath(relative).parts:
            path = path / part
            if path.is_symlink():
                raise HistoricalCheckpointError(
                    f"checkpoint asset contains a symlink: {relative}"
                )
        try:
            resolved = path.resolve(strict=True)
        except OSError as error:
            raise HistoricalCheckpointError(
                f"checkpoint asset failed verification: {relative}"
            ) from error
        if (
            not resolved.is_relative_to(resolved_root)
            or not resolved.is_file()
            or sha256_file(resolved) != expected
        ):
            raise HistoricalCheckpointError(
                f"checkpoint asset failed verification: {relative}"
            )
    return manifest, manifest_path
