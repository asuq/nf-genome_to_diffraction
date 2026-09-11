"""Reference known-control continuation through the shared native copy adapter.

Inputs are a rederived RF paired authority, its exact admission request and one
selected seed's original model, diffraction/preflight and Phenix binding. One
call handles one scientifically dependent chain; Nextflow must fan out separate
seeds. No production entrypoint imports this fixture. Reference authority is
revalidated for every attempt and recorded distinctly in native commands and
receipts. No human approval is inferred or written.

The shared adapter writes native Phaser parameters, commands, logs and typed
results; this fixture retains the best authenticated parent and the shared
receipt validator checks every parent/child asset. An already-complete root
has a zero-attempt receipt, not an invented native copy search. Tool/parse
failures stay typed failures and are never native acceptance. Cache identity
includes the frozen authority/source, original inputs and native attempt IDs.
"""

import shutil
from dataclasses import replace
from pathlib import Path

from tests.fixtures.ranking_four_arm_advancement import (
    REFERENCE_AUTHORITY_KIND,
    REFERENCE_COPY_ADAPTER,
    validate_reference_advancement,
)

from genome_to_diffraction.benchmarks.m6_stages import _validate_copy_receipt
from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.mr.add_copy import (
    AddCopyRunRequest,
    _BenchmarkProvenance,
    _resolve_review_seed,
    _Resolved,
    _run_additional_copy_phaser,
    _run_additional_copy_series,
    _SeedAuthority,
)
from genome_to_diffraction.mr.phaser import PhaserInputError
from genome_to_diffraction.ranking.funnel import DiverseFirstCopyFunnelRequest


def _reference_authority(
    request: AddCopyRunRequest,
    admission: DiverseFirstCopyFunnelRequest,
    manifest_path: Path,
) -> _SeedAuthority:
    if any(
        value is not None
        for value in (
            request.review_validation_json,
            request.review_package_manifest,
            request.phase3_seed_stage_manifest,
            request.benchmark_advancement_manifest,
            request.diffraction_selection_json,
            request.expected_search_model_sha256,
        )
    ):
        raise PhaserInputError(
            "reference execution rejects production/human/model overrides"
        )
    validated = validate_reference_advancement(
        manifest_path, admission, hypotheses_jsonl=request.hypotheses_jsonl
    )
    if request.seed_solution_id not in {
        row.solution_id for row in validated.manifest.recommended
    }:
        raise PhaserInputError("seed is not selected by either reference arm")
    inputs = validated.manifest.input_sha256
    if (
        sha256_file(request.sequence_groups_jsonl)
        != inputs["admission_sequence_groups"]
        or sha256_file(request.preflight_jsonl) != inputs["admission_mtz_preflight"]
    ):
        raise PhaserInputError(
            "reference execution differs from its admitted scientific inputs"
        )
    return _SeedAuthority(
        review_id=validated.manifest.advancement_id,
        review_root=validated.review_manifest.parent,
        review_document=validated.review_document,
        benchmark=_BenchmarkProvenance(
            authority_kind=REFERENCE_AUTHORITY_KIND,
            advancement_id=validated.manifest.advancement_id,
            manifest_sha256=sha256_file(manifest_path),
            adapter_version=REFERENCE_COPY_ADAPTER,
        ),
    )


def _seed_task(request: AddCopyRunRequest, resolved: _Resolved) -> dict[str, object]:
    benchmark = resolved.benchmark
    if benchmark is None:
        raise PhaserInputError("reference seed lacks its execution provenance")
    return {
        "schema_version": "1.0",
        "execution_authority_kind": REFERENCE_AUTHORITY_KIND,
        "case_id": resolved.hypothesis.crystal_id,
        "seed_solution_id": request.seed_solution_id,
        "hypothesis_id": resolved.hypothesis.hypothesis_id,
        "sequence_group_id": resolved.group.sequence_group_id,
        "model_id": resolved.hypothesis.model_id,
        "expected_copy_count": resolved.hypothesis.copy_count_expected,
        "first_copy_placed_count": resolved.parent_copy_count,
        "search_model_sha256": resolved.search_model_sha256,
        "advancement_id": resolved.review_id,
        "advancement_manifest_sha256": benchmark.manifest_sha256,
    }


def run_reference_copy_task(
    request: AddCopyRunRequest,
    admission: DiverseFirstCopyFunnelRequest,
    *,
    advancement_manifest: Path,
) -> Path:
    """Execute one selected reference seed with native best-parent receipts."""

    if request.parent_result_jsonl is not None or request.parent_coordinate is not None:
        raise PhaserInputError(
            "reference task must start at its authenticated root seed"
        )
    output = request.output_directory.resolve()
    if output.exists():
        raise PhaserInputError("reference copy output must not already exist")

    def resolve(current: AddCopyRunRequest) -> _Resolved:
        return _resolve_review_seed(
            current, _reference_authority(current, admission, advancement_manifest)
        )

    authority = _reference_authority(request, admission, advancement_manifest)
    resolved = _resolve_review_seed(request, authority)
    task = _seed_task(request, resolved)
    benchmark = authority.benchmark
    if benchmark is None:
        raise PhaserInputError("reference task lacks its execution provenance")
    if resolved.parent_copy_count > resolved.hypothesis.copy_count_expected:
        raise PhaserInputError("reference root exceeds its expected copy count")
    output.mkdir(parents=True, exist_ok=False)
    best_coordinate = resolved.parent_coordinate
    best_count = resolved.parent_copy_count
    if best_count == resolved.hypothesis.copy_count_expected:
        atomic_write_text(output / "additional_copy_series_results.jsonl", "")
        atomic_write_json(
            output / "additional_copy_series_summary.json",
            {
                "schema_version": "1.0",
                "seed_solution_id": request.seed_solution_id,
                "expected_copy_count": resolved.hypothesis.copy_count_expected,
                "attempt_count": 0,
                "best_supported_copy_count": best_count,
                "reached_expected_copy_count": True,
                "stop_reason": "first_copy_already_reached_expected_count",
                "parent_retained": True,
                **benchmark.command_fields(),
            },
        )
    else:
        series = _run_additional_copy_series(
            replace(request, output_directory=output / "series"),
            run_attempt=lambda current: _run_additional_copy_phaser(
                current, resolve=resolve
            ),
            authority=authority,
        )
        shutil.copy2(
            series.results_jsonl, output / "additional_copy_series_results.jsonl"
        )
        shutil.copy2(
            series.summary_json, output / "additional_copy_series_summary.json"
        )
        for attempt in series.attempts:
            if attempt.result.additional_copy_supported:
                coordinate = attempt.result.output_coordinate_path
                if coordinate is None:
                    raise PhaserInputError(
                        "supported reference child lacks coordinates"
                    )
                best_coordinate = attempt.result_json.parent / coordinate
                best_count = attempt.result.best_supported_copy_count
    shutil.copy2(best_coordinate, output / "best_parent.pdb")
    atomic_write_json(output / "seed_task.json", task)
    atomic_write_json(
        output / "best_parent.json",
        {
            "schema_version": "1.0",
            "case_id": resolved.hypothesis.crystal_id,
            "seed_solution_id": request.seed_solution_id,
            "sequence_group_id": resolved.group.sequence_group_id,
            "best_supported_copy_count": best_count,
            "parent_coordinate_sha256": sha256_file(output / "best_parent.pdb"),
            "parent_retained": True,
            **benchmark.command_fields(),
        },
    )
    # Revalidation after execution catches changed source/authority/root inputs.
    validate_reference_copy_receipt(
        output, request, admission, advancement_manifest=advancement_manifest
    )
    return output


def validate_reference_copy_receipt(
    root: Path,
    request: AddCopyRunRequest,
    admission: DiverseFirstCopyFunnelRequest,
    *,
    advancement_manifest: Path,
) -> tuple[str, int]:
    """Reconstruct reference authority, then verify the complete native chain."""

    if request.parent_result_jsonl is not None or request.parent_coordinate is not None:
        raise PhaserInputError("reference receipt must bind the original root seed")
    authority = _reference_authority(request, admission, advancement_manifest)
    resolved = _resolve_review_seed(request, authority)
    return _validate_copy_receipt(
        root.resolve(strict=True),
        task=_seed_task(request, resolved),
        parent_sha256=resolved.parent_coordinate_sha256,
        parent_result_sha256=resolved.parent_result_sha256,
        mtz_sha256=resolved.mtz_sha256,
        authority_kind=REFERENCE_AUTHORITY_KIND,
        adapter_version=REFERENCE_COPY_ADAPTER,
    )
