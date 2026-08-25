"""Focused complete-catalogue fixed-128 ProstT5/Foldseek batch regressions."""

import json
import shutil
from pathlib import Path

import pytest

from genome_to_diffraction.checksums import atomic_write_json
from genome_to_diffraction.structure_search import (
    PhaseIIIFoldseekBatchError,
    build_phase3_foldseek_batches,
    merge_phase3_foldseek_batches,
)
from tests.scripts.write_phase3_foldseek_batch_stub import (
    write_phase3_foldseek_batch_stub,
    write_phase3_foldseek_stub_sequence_groups,
)


def _sequence_groups(path: Path, *, count: int) -> Path:
    return write_phase3_foldseek_stub_sequence_groups(output=path, count=count)


def _batch_outputs(plan: Path, output: Path) -> tuple[Path, ...]:
    output.mkdir()
    batches: list[Path] = []
    for batch in sorted((plan / "batches").iterdir()):
        destination = output / batch.name
        destination.mkdir()
        shutil.copy2(batch / "batch.json", destination / "batch.json")
        write_phase3_foldseek_batch_stub(batch=batch, output=destination / "search")
        batches.append(destination)
    return tuple(batches)


def test_complete_1621_group_catalogue_produces_exactly_13_bounded_batches(
    tmp_path: Path,
) -> None:
    groups = _sequence_groups(tmp_path / "groups.jsonl", count=1621)
    plan_root = build_phase3_foldseek_batches(
        sequence_groups=groups,
        output_directory=tmp_path / "plan",
    )
    plan = json.loads((plan_root / "batch_plan.json").read_bytes())

    assert plan["query_count"] == 1621
    assert plan["batch_count"] == 13
    assert plan["maximum_queries_per_batch"] == 128
    assert tuple(item["sequence_count"] for item in plan["batches"]) == (
        *([128] * 12),
        85,
    )
    identifiers = tuple(
        identifier
        for batch in plan["batches"]
        for identifier in batch["sequence_group_ids"]
    )
    assert identifiers == tuple(sorted(identifiers))
    assert len(set(identifiers)) == 1621


def test_batch_merge_retains_every_query_and_raw_evidence_independently_of_order(
    tmp_path: Path,
) -> None:
    groups = _sequence_groups(tmp_path / "groups.jsonl", count=257)
    plan = build_phase3_foldseek_batches(
        sequence_groups=groups,
        output_directory=tmp_path / "plan",
    )
    outputs = _batch_outputs(plan, tmp_path / "batch-results")
    first = merge_phase3_foldseek_batches(
        sequence_groups=groups,
        batch_plan=plan,
        batch_outputs=outputs,
        output_directory=tmp_path / "merged-first",
    )
    second = merge_phase3_foldseek_batches(
        sequence_groups=groups,
        batch_plan=plan,
        batch_outputs=tuple(reversed(outputs)),
        output_directory=tmp_path / "merged-second",
    )

    assert (first / "search_results.jsonl").read_bytes() == (
        second / "search_results.jsonl"
    ).read_bytes()
    assert (first / "search_manifest.json").read_bytes() == (
        second / "search_manifest.json"
    ).read_bytes()
    results = tuple(
        json.loads(line)
        for line in (first / "search_results.jsonl")
        .read_text(encoding="ascii")
        .splitlines()
    )
    assert len(results) == 257
    assert all((first / item["raw_result_pointer"]).is_file() for item in results)
    assert all((first / item["command_log_pointer"]).is_file() for item in results)
    manifest = json.loads((first / "search_manifest.json").read_bytes())
    assert manifest["batch_count"] == 3
    assert manifest["query_count"] == 257
    assert manifest["deferred_query_count"] == 0


@pytest.mark.parametrize(
    "mutation", ("missing", "duplicate", "deferred", "changed", "raw")
)
def test_incomplete_or_changed_batches_never_become_a_catalogue_result(
    tmp_path: Path,
    mutation: str,
) -> None:
    groups = _sequence_groups(tmp_path / "groups.jsonl", count=129)
    plan = build_phase3_foldseek_batches(
        sequence_groups=groups,
        output_directory=tmp_path / "plan",
    )
    outputs = _batch_outputs(plan, tmp_path / "batch-results")
    if mutation == "missing":
        outputs = outputs[:1]
    elif mutation == "duplicate":
        outputs = (outputs[0], outputs[0])
    elif mutation == "deferred":
        path = outputs[0] / "search/search_manifest.json"
        manifest = json.loads(path.read_bytes())
        manifest["deferred_query_count"] = 1
        atomic_write_json(path, manifest)
    elif mutation == "changed":
        (outputs[0] / "search/search_results.jsonl").write_text(
            "{}\n", encoding="ascii"
        )
    else:
        (outputs[0] / "search/raw/foldseek-results.tsv").write_text(
            "changed raw evidence\n", encoding="ascii"
        )

    with pytest.raises(PhaseIIIFoldseekBatchError):
        merge_phase3_foldseek_batches(
            sequence_groups=groups,
            batch_plan=plan,
            batch_outputs=outputs,
            output_directory=tmp_path / "merged",
        )
