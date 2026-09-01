"""Deterministic multi-batch M6 discovery partition regressions."""

import json
from pathlib import Path

import pytest

from genome_to_diffraction.benchmarks.m6_nextflow import _batch_search_records
from genome_to_diffraction.benchmarks.public_control import PublicControlError
from genome_to_diffraction.ids import sequence_digest

ROOT = Path(__file__).resolve().parents[2]
RESULT_FIXTURE = ROOT / "tests/fixtures/stubs/structure_search/search_results.jsonl"
HIT_FIXTURE = ROOT / "tests/fixtures/stubs/structure_search/structural_hits.jsonl"
HASH = "a" * 64


def _write_bundle(
    root: Path,
    *,
    batch_id: str,
    suffix: str,
    sequence: str,
) -> Path:
    bundle = root / suffix
    search = bundle / "search"
    search.mkdir(parents=True)
    group_id = f"seq_{sequence_digest(sequence)}"
    result = json.loads(RESULT_FIXTURE.read_text(encoding="utf-8"))
    hit = json.loads(HIT_FIXTURE.read_text(encoding="utf-8"))
    result["search_id"] = f"srch_{suffix}"
    result["sequence_group_id"] = group_id
    result["hits"][0]["hit_id"] = f"hit_{suffix}"
    result["hits"][0]["sequence_group_id"] = group_id
    hit["hit_id"] = f"hit_{suffix}"
    hit["sequence_group_id"] = group_id
    (search / "search_results.jsonl").write_text(
        f"{json.dumps(result, sort_keys=True)}\n", encoding="utf-8"
    )
    (search / "structural_hits.jsonl").write_text(
        f"{json.dumps(hit, sort_keys=True)}\n", encoding="utf-8"
    )
    (bundle / "batch_task.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "batch_id": batch_id,
                "provider": "pdb_sequence",
                "sequence_count": 1,
                "residue_count": len(sequence),
                "threads": 1,
                "database_manifest_sha256": HASH,
                "software_lock_sha256": HASH,
                "execution_policy_sha256": HASH,
                "search_cache_key": ("b" if suffix == "first" else "c") * 64,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (bundle / "bundle_manifest.json").write_text("{}\n", encoding="utf-8")
    return bundle


def test_batch_search_partition_is_independent_of_completion_order(
    tmp_path: Path,
) -> None:
    first = _write_bundle(tmp_path, batch_id="1" * 64, suffix="first", sequence="AAAA")
    second = _write_bundle(
        tmp_path, batch_id="2" * 64, suffix="second", sequence="CCCC"
    )

    groups = frozenset(
        {
            f"seq_{sequence_digest('AAAA')}",
            f"seq_{sequence_digest('CCCC')}",
        }
    )
    forward = _batch_search_records((first, second), "pdb_sequence", groups)
    reverse = _batch_search_records((second, first), "pdb_sequence", groups)

    assert forward == reverse
    assert [item.search_id for item in forward[0]] == ["srch_first", "srch_second"]
    assert [item.hit_id for item in forward[1]] == ["hit_first", "hit_second"]


def test_batch_search_partition_rejects_duplicate_batch_ids(tmp_path: Path) -> None:
    first = _write_bundle(tmp_path, batch_id="1" * 64, suffix="first", sequence="AAAA")
    duplicate = _write_bundle(
        tmp_path, batch_id="1" * 64, suffix="second", sequence="CCCC"
    )

    with pytest.raises(PublicControlError, match="batch is duplicated"):
        _batch_search_records(
            (first, duplicate),
            "pdb_sequence",
            frozenset(
                {
                    f"seq_{sequence_digest('AAAA')}",
                    f"seq_{sequence_digest('CCCC')}",
                }
            ),
        )
