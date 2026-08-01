"""Dedicated one-time Free-R generation through verified external Phenix."""

import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import gemmi  # type: ignore[import-untyped]
from tqdm import tqdm

from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.phenix.runtime import capture_from_manifest
from genome_to_diffraction.schemas.results import FreeRGenerationRecord
from genome_to_diffraction.status import InputContractError, ToolExecutionError
from genome_to_diffraction.time import utc_now

_LOGGER = logging.getLogger("genome_to_diffraction.diffraction")


class FreeRGenerationError(InputContractError):
    """Free-R flags cannot be generated without violating preservation policy."""


class FreeRToolError(ToolExecutionError):
    """Phenix reflection conversion failed during Free-R generation."""


@dataclass(frozen=True)
class FreeRGenerationRequest:
    """Explicit immutable output and deterministic flag-generation parameters."""

    source_mtz: Path
    output_mtz: Path
    phenix_manifest: Path
    command_log: Path
    record_path: Path
    test_fraction: float = 0.05
    maximum_free_reflections: int = 2000
    random_seed: int = 20260801
    timeout_seconds: float = 3600.0
    progress: bool = True


def generate_free_r(request: FreeRGenerationRequest) -> FreeRGenerationRecord:
    """Generate Free-R flags once, refusing existing flags and output targets."""

    if not 0 < request.test_fraction < 1:
        raise ValueError("Free-R test fraction must be between zero and one")
    if request.maximum_free_reflections < 1 or request.random_seed < 1:
        raise ValueError("Free-R maximum and random seed must be positive")
    source = request.source_mtz.resolve(strict=True)
    phenix_manifest = request.phenix_manifest.resolve(strict=True)
    output = request.output_mtz.resolve()
    if output.exists():
        raise FreeRGenerationError(f"Free-R output already exists: {output}")
    if source == output:
        raise FreeRGenerationError(
            "Free-R generation must not overwrite the source MTZ"
        )
    try:
        source_mtz = gemmi.read_mtz_file(str(source))
    except (OSError, RuntimeError) as error:
        raise FreeRGenerationError(
            f"cannot read source MTZ {source}: {error}"
        ) from error
    if source_mtz.rfree_column() is not None:
        raise FreeRGenerationError(
            "source MTZ already contains Free-R flags; preserve them unchanged: "
            f"{source}"
        )
    source_sha = sha256_file(source, progress=request.progress)
    manifest_sha = sha256_file(phenix_manifest, progress=request.progress)
    output.parent.mkdir(parents=True, exist_ok=True)
    request.command_log.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".free-r-", dir=output.parent) as temporary:
        temporary_output = Path(temporary) / output.name
        arguments = (
            "phenix.reflection_file_converter",
            str(source),
            f"--mtz={temporary_output}",
            "--generate-r-free-flags",
            "--use-lattice-symmetry-in-r-free-flag-generation",
            f"--r-free-flags-fraction={request.test_fraction}",
            f"--r-free-flags-max-free={request.maximum_free_reflections}",
            "--r-free-flags-format=cns",
            f"--random-seed={request.random_seed}",
        )
        with tqdm(
            total=1,
            desc="Generate Free-R flags",
            unit="command",
            disable=not request.progress,
        ) as progress_bar:
            completed = capture_from_manifest(
                phenix_manifest,
                arguments,
                working_directory=Path(temporary),
                timeout_seconds=request.timeout_seconds,
            )
            progress_bar.update(1)
        command_output = (completed.stdout + completed.stderr).decode(
            "utf-8", errors="replace"
        )
        atomic_write_text(request.command_log, command_output)
        if completed.returncode != 0:
            raise FreeRToolError(
                "phenix.reflection_file_converter failed with exit status "
                f"{completed.returncode}; see {request.command_log}"
            )
        if not temporary_output.is_file():
            raise FreeRToolError(
                "Phenix reported success but did not create the Free-R MTZ; "
                f"see {request.command_log}"
            )
        try:
            generated = gemmi.read_mtz_file(str(temporary_output))
        except (OSError, RuntimeError) as error:
            raise FreeRToolError(
                f"generated Free-R MTZ is unreadable: {error}"
            ) from error
        free_column = generated.rfree_column()
        if free_column is None or free_column.type != "I":
            raise FreeRToolError(
                "generated MTZ does not contain a recognised Free-R column"
            )
        if sha256_file(source) != source_sha:
            raise FreeRGenerationError("source MTZ changed during Free-R generation")
        os.replace(temporary_output, output)

    output_sha = sha256_file(output, progress=request.progress)
    identity = {
        "source_mtz_sha256": source_sha,
        "output_mtz_sha256": output_sha,
        "phenix_manifest_sha256": manifest_sha,
        "test_fraction": request.test_fraction,
        "maximum_free_reflections": request.maximum_free_reflections,
        "random_seed": request.random_seed,
        "use_lattice_symmetry": True,
        "flag_convention": "cns",
    }
    record = FreeRGenerationRecord(
        schema_version="1.0",
        generation_id=content_id("freer_", identity),
        source_mtz_path=str(source),
        source_mtz_sha256=source_sha,
        output_mtz_path=str(output),
        output_mtz_sha256=output_sha,
        free_flag_labels=free_column.label,
        test_fraction=request.test_fraction,
        maximum_free_reflections=request.maximum_free_reflections,
        random_seed=request.random_seed,
        use_lattice_symmetry=True,
        flag_convention="cns",
        phenix_manifest_sha256=manifest_sha,
        command=arguments,
        command_log=str(request.command_log.resolve()),
        generated_at=utc_now(),
    )
    atomic_write_json(request.record_path, record.model_dump(mode="json"))
    _LOGGER.info(
        "Free-R generation complete",
        extra={
            "generation_id": record.generation_id,
            "source_mtz_sha256": source_sha,
            "output_mtz_sha256": output_sha,
            "free_flag_labels": record.free_flag_labels,
            "output_mtz": str(output),
        },
    )
    return record
