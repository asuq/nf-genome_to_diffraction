"""Focused tests for trusted M6 RCSB family preparation."""

import hashlib
from pathlib import Path

import pytest

from genome_to_diffraction.benchmarks.m6_prepare import (
    _verify_m6_family_snapshots,
)
from genome_to_diffraction.benchmarks.m6_protocol import (
    M6BenchmarkProtocol,
    load_m6_protocol,
)
from genome_to_diffraction.benchmarks.public_control import PublicControlError

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "benchmarks" / "m6" / "protocol.yaml"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _synthetic_family_protocol(
    tmp_path: Path,
) -> tuple[M6BenchmarkProtocol, dict[int, bytes]]:
    payload = load_m6_protocol(PROTOCOL).model_dump(mode="json")
    lines: dict[int, list[bytes]] = {30: [], 70: []}
    for index, target in enumerate(payload["positives"], start=1):
        source = f"{target['source']['pdb_id']}_{target['source']['pdb_entity_ids'][0]}"
        safe_family_member = f"1A{index:02d}_1"
        line_70 = f"{source}\n".encode("ascii")
        line_30 = (
            line_70
            if target["target_key"] == "T06"
            else f"{source} {safe_family_member}\n".encode("ascii")
        )
        lines[30].append(line_30)
        lines[70].append(line_70)
        target["rcsb_30_cluster_line_sha256"] = _sha256(line_30)
        target["rcsb_70_cluster_line_sha256"] = _sha256(line_70)
        target["allowed_30_to_70_model_count"] = int(line_30 != line_70)

    serialised: dict[int, bytes] = {
        threshold: b"".join(threshold_lines)
        for threshold, threshold_lines in lines.items()
    }
    for threshold in (30, 70):
        snapshot = tmp_path / f"clusters-by-entity-{threshold}.txt"
        snapshot.write_bytes(serialised[threshold])
        resource = payload["leakage_policy"][f"rcsb_{threshold}_snapshot"]
        resource["sha256"] = _sha256(serialised[threshold])
        resource["size_bytes"] = len(serialised[threshold])
    return M6BenchmarkProtocol.model_validate(payload), serialised


def _replace_target_value(
    protocol: M6BenchmarkProtocol,
    *,
    target_key: str,
    field: str,
    value: object,
) -> M6BenchmarkProtocol:
    payload = protocol.model_dump(mode="json")
    target = next(
        item for item in payload["positives"] if item["target_key"] == target_key
    )
    target[field] = value
    return M6BenchmarkProtocol.model_validate(payload)


def test_verified_family_truth_uses_exact_snapshot_memberships(
    tmp_path: Path,
) -> None:
    protocol, snapshots_by_threshold = _synthetic_family_protocol(tmp_path)

    snapshots, families = _verify_m6_family_snapshots(protocol, tmp_path)

    assert [item.identity_threshold_percent for item in snapshots] == [30, 70]
    assert [item.sha256 for item in snapshots] == [
        _sha256(snapshots_by_threshold[30]),
        _sha256(snapshots_by_threshold[70]),
    ]
    assert all(item.target_line_count == 12 for item in snapshots)
    target = next(item for item in families if item.target_key == "T01")
    assert target.source_pdb_entity_id == "8GKV_1"
    assert target.cluster_30_entities == ("1A01_1", "8GKV_1")
    assert target.cluster_70_entities == ("8GKV_1",)
    assert target.operational_family_entities == ("1A01_1",)
    assert target.leakage_safe_family_entities == ("1A01_1",)
    assert target.frozen_allowed_30_to_70_model_count == 1
    assert target.observed_allowed_30_to_70_model_count == 1
    scarce = next(item for item in families if item.target_key == "T06")
    assert scarce.operational_family_entities == ()
    assert scarce.leakage_safe_family_entities == ()


def test_family_snapshot_verification_rejects_file_tampering(tmp_path: Path) -> None:
    protocol, snapshots_by_threshold = _synthetic_family_protocol(tmp_path)
    tampered = bytearray(snapshots_by_threshold[30])
    tampered[0] = ord("9") if tampered[0] != ord("9") else ord("8")
    (tmp_path / "clusters-by-entity-30.txt").write_bytes(tampered)

    with pytest.raises(PublicControlError, match="checksum differs"):
        _verify_m6_family_snapshots(protocol, tmp_path)


def test_family_line_hash_includes_the_lf_byte(tmp_path: Path) -> None:
    protocol, snapshots_by_threshold = _synthetic_family_protocol(tmp_path)
    first_line = snapshots_by_threshold[30].splitlines(keepends=True)[0]
    assert first_line.endswith(b"\n")
    protocol = _replace_target_value(
        protocol,
        target_key="T01",
        field="rcsb_30_cluster_line_sha256",
        value=_sha256(first_line[:-1]),
    )

    with pytest.raises(PublicControlError, match="cluster-line checksum changed"):
        _verify_m6_family_snapshots(protocol, tmp_path)


def test_family_verification_allows_independent_non_nested_cluster_partitions(
    tmp_path: Path,
) -> None:
    protocol, snapshots_by_threshold = _synthetic_family_protocol(tmp_path)
    lines_70 = snapshots_by_threshold[70].splitlines(keepends=True)
    lines_70[0] = lines_70[0][:-1] + b" 2A01_1\n"
    changed_70 = b"".join(lines_70)
    (tmp_path / "clusters-by-entity-70.txt").write_bytes(changed_70)
    payload = protocol.model_dump(mode="json")
    resource = payload["leakage_policy"]["rcsb_70_snapshot"]
    resource["sha256"] = _sha256(changed_70)
    resource["size_bytes"] = len(changed_70)
    target = next(item for item in payload["positives"] if item["target_key"] == "T01")
    target["rcsb_70_cluster_line_sha256"] = _sha256(lines_70[0])
    changed_protocol = M6BenchmarkProtocol.model_validate(payload)

    _, families = _verify_m6_family_snapshots(changed_protocol, tmp_path)

    family = next(item for item in families if item.target_key == "T01")
    assert "2A01_1" in family.cluster_70_entities
    assert "2A01_1" not in family.cluster_30_entities
    assert family.leakage_safe_family_entities == ("1A01_1",)


def test_family_verification_rejects_frozen_count_tampering(tmp_path: Path) -> None:
    protocol, _ = _synthetic_family_protocol(tmp_path)
    protocol = _replace_target_value(
        protocol,
        target_key="T01",
        field="allowed_30_to_70_model_count",
        value=2,
    )

    with pytest.raises(PublicControlError, match="frozen 30%-minus-70% count"):
        _verify_m6_family_snapshots(protocol, tmp_path)
