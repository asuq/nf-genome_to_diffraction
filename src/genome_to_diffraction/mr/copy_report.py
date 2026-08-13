"""Build a retained-candidate copy-count comparison from sequential MR results."""

import csv
import io
import logging
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError
from tqdm import tqdm

from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import canonical_json_text, content_id
from genome_to_diffraction.mr.phaser import PhaserInputError
from genome_to_diffraction.schemas.results import (
    AdditionalCopyResult,
    CopyCountAssessment,
)

_LOGGER = logging.getLogger("genome_to_diffraction.mr.copy_report")
_ADAPTER_VERSION = "copy-count-report-v1"
_TSV_COLUMNS = (
    "seed_solution_id",
    "hypothesis_id",
    "sequence_group_id",
    "expected_copy_count",
    "best_supported_copy_count",
    "attempted_transition_count",
    "reached_expected_copy_count",
    "terminal_reason",
    "final_execution_status",
    "final_llg",
    "final_tfz",
    "final_llg_delta_from_parent",
    "final_top_solution_packed",
    "final_placement_count",
    "review_flags",
)


@dataclass(frozen=True, slots=True)
class CopyCountReportRequest:
    """Inputs for one deterministic retained-candidate copy-count report."""

    results_jsonl: Path
    output_directory: Path
    progress: bool = True


@dataclass(frozen=True, slots=True)
class CopyCountReportOutput:
    """Machine-readable and human-readable copy-count comparison files."""

    assessments: tuple[CopyCountAssessment, ...]
    assessments_jsonl: Path
    assessments_tsv: Path
    report_markdown: Path
    manifest_json: Path


def _load(path: Path) -> tuple[AdditionalCopyResult, ...]:
    records: list[AdditionalCopyResult] = []
    resolved = path.resolve(strict=True)
    with resolved.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                records.append(AdditionalCopyResult.model_validate_json(line))
            except ValidationError as error:
                raise PhaserInputError(
                    f"invalid additional-copy result at line {line_number}"
                ) from error
    if not records:
        raise PhaserInputError("additional-copy results are empty")
    return tuple(records)


def _assess(records: list[AdditionalCopyResult]) -> CopyCountAssessment:
    ordered = sorted(records, key=lambda item: item.attempted_copy_number)
    first = ordered[0]
    expected_numbers = list(range(2, 2 + len(ordered)))
    if [item.attempted_copy_number for item in ordered] != expected_numbers:
        raise PhaserInputError(
            f"copy series is not contiguous for seed {first.seed_solution_id}"
        )
    for index, item in enumerate(ordered):
        if (
            item.review_id != first.review_id
            or item.hypothesis_id != first.hypothesis_id
            or item.sequence_group_id != first.sequence_group_id
            or item.expected_copy_count != first.expected_copy_count
        ):
            raise PhaserInputError(
                f"copy series provenance changes for seed {first.seed_solution_id}"
            )
        if index == 0:
            if (
                item.parent_copy_count != 1
                or item.parent_solution_id != item.seed_solution_id
            ):
                raise PhaserInputError(
                    "copy series does not begin at approved seed "
                    f"{first.seed_solution_id}"
                )
            continue
        parent = ordered[index - 1]
        if (
            not parent.additional_copy_supported
            or parent.child_solution_id is None
            or item.parent_solution_id != parent.child_solution_id
            or item.parent_copy_count != parent.best_supported_copy_count
        ):
            raise PhaserInputError(
                f"copy series lineage breaks for seed {first.seed_solution_id}"
            )
    if any(not item.additional_copy_supported for item in ordered[:-1]):
        raise PhaserInputError(
            "copy series continues after an unsupported attempt for "
            f"{first.seed_solution_id}"
        )
    final = ordered[-1]
    reached = final.best_supported_copy_count == final.expected_copy_count
    if final.additional_copy_supported and not reached:
        raise PhaserInputError(
            "copy series ends before expected count without a stop for "
            f"{first.seed_solution_id}"
        )
    flags = (
        ()
        if reached
        else (
            "expected_copy_count_not_reached",
            "possible_residual_content_or_special_position",
            "copy_absence_not_proven",
        )
    )
    identity = {
        "adapter_version": _ADAPTER_VERSION,
        "seed_solution_id": first.seed_solution_id,
        "attempt_ids": [item.attempt_id for item in ordered],
    }
    return CopyCountAssessment(
        schema_version="1.0",
        assessment_id=content_id("copyassessment_", identity),
        review_id=first.review_id,
        seed_solution_id=first.seed_solution_id,
        hypothesis_id=first.hypothesis_id,
        sequence_group_id=first.sequence_group_id,
        expected_copy_count=first.expected_copy_count,
        best_supported_copy_count=final.best_supported_copy_count,
        attempted_transition_count=len(ordered),
        reached_expected_copy_count=reached,
        final_execution_status=final.execution_status,
        final_llg=final.llg,
        final_tfz=final.tfz,
        final_llg_delta_from_parent=final.llg_delta_from_parent,
        final_top_solution_packed=final.top_solution_packed,
        final_placement_count=final.phaser_placement_count,
        terminal_reason=(
            "expected_copy_count_reached"
            if reached
            else "additional_copy_not_supported"
        ),
        review_flags=flags,
    )


def build_copy_count_report(request: CopyCountReportRequest) -> CopyCountReportOutput:
    """Validate sequential lineage and compare expected with supported counts."""

    grouped: dict[str, list[AdditionalCopyResult]] = defaultdict(list)
    for record in _load(request.results_jsonl):
        grouped[record.seed_solution_id].append(record)
    assessments = tuple(
        _assess(grouped[seed])
        for seed in tqdm(
            sorted(grouped),
            desc="Assess copy-count series",
            unit="seed",
            disable=not request.progress,
        )
    )
    output = request.output_directory.resolve()
    if output.exists() and any(output.iterdir()):
        raise PhaserInputError(f"copy-count report directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    jsonl = output / "copy_count_assessments.jsonl"
    atomic_write_text(
        jsonl,
        "".join(f"{canonical_json_text(item)}\n" for item in assessments),
    )
    tsv = output / "copy_count_assessments.tsv"
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=_TSV_COLUMNS, delimiter="\t")
    writer.writeheader()
    for item in assessments:
        row = item.model_dump(mode="json")
        writer.writerow(
            {
                column: ";".join(row[column])
                if column == "review_flags"
                else row[column]
                for column in _TSV_COLUMNS
            }
        )
    atomic_write_text(tsv, buffer.getvalue())
    markdown = output / "copy_count_report.md"
    lines = [
        "# Copy-count comparison",
        "",
        "Stopped series retain their best parent and do not prove a copy absent.",
        "",
        "| Seed | Matthews expected | Best supported | State | Final LLG | Final TFZ |",
        "|---|---:|---:|---|---:|---:|",
    ]
    for item in assessments:
        state = (
            "expected count reached"
            if item.reached_expected_copy_count
            else "review residual content / special position"
        )
        lines.append(
            f"| `{item.seed_solution_id}` | {item.expected_copy_count} | "
            f"{item.best_supported_copy_count} | {state} | "
            f"{'' if item.final_llg is None else item.final_llg} | "
            f"{'' if item.final_tfz is None else item.final_tfz} |"
        )
    atomic_write_text(markdown, "\n".join(lines) + "\n")
    manifest = output / "copy_count_report_manifest.json"
    atomic_write_json(
        manifest,
        {
            "schema_version": "1.0",
            "adapter_version": _ADAPTER_VERSION,
            "candidate_count": len(assessments),
            "expected_count_reached_count": sum(
                item.reached_expected_copy_count for item in assessments
            ),
            "stopped_before_expected_count": sum(
                not item.reached_expected_copy_count for item in assessments
            ),
            "all_candidates_retained": True,
            "failed_addition_proves_absence": False,
            "input": {
                "results_jsonl": str(request.results_jsonl.resolve(strict=True)),
                "sha256": sha256_file(request.results_jsonl),
            },
            "outputs": {
                "assessments_jsonl": {
                    "path": jsonl.name,
                    "sha256": sha256_file(jsonl),
                },
                "assessments_tsv": {
                    "path": tsv.name,
                    "sha256": sha256_file(tsv),
                },
                "report_markdown": {
                    "path": markdown.name,
                    "sha256": sha256_file(markdown),
                },
            },
        },
    )
    _LOGGER.info(
        "copy-count report built",
        extra={
            "candidate_count": len(assessments),
            "expected_count_reached_count": sum(
                item.reached_expected_copy_count for item in assessments
            ),
            "manifest": str(manifest),
        },
    )
    return CopyCountReportOutput(assessments, jsonl, tsv, markdown, manifest)
