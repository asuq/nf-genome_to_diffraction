"""Tests for the exact-source Phase III finding-closure gate."""

from pathlib import Path

import pytest

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.execution.finding_closure import (
    FindingDisposition,
    PhaseIIIFindingClosureEntry,
    PhaseIIIFindingClosureError,
    PhaseIIIFindingClosureEvidenceFiles,
    PhaseIIIFindingClosureRecord,
    validate_phase3_finding_closure,
)

COMMIT = "1" * 40
TREE = "2" * 40
def _write_ledger(path: Path, *, first_status: str = "Fixed") -> None:
    path.write_text(
        "# Finding ledger\n\n"
        "| Finding | Disposition | Evidence |\n"
        "| --- | --- | --- |\n"
        f"| `FCB-P0-01` Packing | {first_status} | retained |\n"
        "| `PIPE-P1-01` | Deleted | removed |\n",
        encoding="utf-8",
    )


def _record(
    ledger: Path,
    evidence_files: PhaseIIIFindingClosureEvidenceFiles,
    *,
    entries: tuple[PhaseIIIFindingClosureEntry, ...] | None = None,
) -> PhaseIIIFindingClosureRecord:
    selected = entries or (
        PhaseIIIFindingClosureEntry(
            finding_id="FCB-P0-01",
            disposition=FindingDisposition.FIXED,
            regression_ids=("tests/unit/test_packing.py",),
            evidence_ids=("control-6rtz",),
        ),
        PhaseIIIFindingClosureEntry(
            finding_id="PIPE-P1-01",
            disposition=FindingDisposition.DELETED,
            regression_ids=("tests/contract/test_policy.py",),
            evidence_ids=("commit-clean-break",),
        ),
    )
    return PhaseIIIFindingClosureRecord.from_content(
        source_commit=COMMIT,
        source_tree=TREE,
        ledger_sha256=sha256_file(ledger, progress=False),
        adverse_review_sha256=sha256_file(evidence_files.adverse_review),
        integration_gate_sha256=sha256_file(evidence_files.integration_gate),
        known_control_evidence_sha256=sha256_file(
            evidence_files.known_control_evidence
        ),
        m6_evidence_sha256=sha256_file(evidence_files.m6_evidence),
        unknown_pass1_evidence_sha256=sha256_file(
            evidence_files.unknown_pass1_evidence
        ),
        exact_source_ci_evidence_sha256=sha256_file(
            evidence_files.exact_source_ci_evidence
        ),
        exact_source_ci_run_id=123,
        exact_source_ci_job_id=456,
        exact_source_ci_status="success",
        entries=selected,
    )


def _write_record(path: Path, record: PhaseIIIFindingClosureRecord) -> None:
    atomic_write_json(path, record.model_dump(mode="json"))


def _evidence_files(root: Path) -> PhaseIIIFindingClosureEvidenceFiles:
    paths = {
        name: root / f"{name}.json"
        for name in (
            "adverse_review",
            "integration_gate",
            "known_control",
            "m6",
            "unknown_pass1",
        )
    }
    for name, path in paths.items():
        atomic_write_json(path, {"schema_version": "1.0", "evidence": name})
    ci = root / "exact_source_ci.json"
    atomic_write_json(
        ci,
        {
            "schema_version": "1.0",
            "run_id": 123,
            "job_id": 456,
            "head_sha": COMMIT,
            "conclusion": "success",
        },
    )
    return PhaseIIIFindingClosureEvidenceFiles(
        adverse_review=paths["adverse_review"],
        integration_gate=paths["integration_gate"],
        known_control_evidence=paths["known_control"],
        m6_evidence=paths["m6"],
        unknown_pass1_evidence=paths["unknown_pass1"],
        exact_source_ci_evidence=ci,
    )


def test_complete_exact_source_finding_closure_passes(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.md"
    closure = tmp_path / "closure.json"
    _write_ledger(ledger)
    evidence = _evidence_files(tmp_path)
    expected = _record(ledger, evidence)
    _write_record(closure, expected)

    observed = validate_phase3_finding_closure(
        closure,
        ledger,
        expected_source_commit=COMMIT,
        expected_source_tree=TREE,
        evidence_files=evidence,
    )

    assert observed == expected


def test_incomplete_finding_inventory_fails(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.md"
    closure = tmp_path / "closure.json"
    _write_ledger(ledger)
    evidence = _evidence_files(tmp_path)
    complete = _record(ledger, evidence)
    incomplete = _record(ledger, evidence, entries=(complete.entries[0],))
    _write_record(closure, incomplete)

    with pytest.raises(PhaseIIIFindingClosureError, match="inventory differs"):
        validate_phase3_finding_closure(
            closure,
            ledger,
            expected_source_commit=COMMIT,
            expected_source_tree=TREE,
            evidence_files=evidence,
        )


def test_locally_qualified_disposition_is_not_final(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.md"
    closure = tmp_path / "closure.json"
    _write_ledger(ledger, first_status="Fixed locally; CI pending")
    evidence = _evidence_files(tmp_path)
    _write_record(closure, _record(ledger, evidence))

    with pytest.raises(PhaseIIIFindingClosureError, match="non-final dispositions"):
        validate_phase3_finding_closure(
            closure,
            ledger,
            expected_source_commit=COMMIT,
            expected_source_tree=TREE,
            evidence_files=evidence,
        )


def test_changed_ledger_bytes_fail(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.md"
    closure = tmp_path / "closure.json"
    _write_ledger(ledger)
    evidence = _evidence_files(tmp_path)
    _write_record(closure, _record(ledger, evidence))
    ledger.write_text(ledger.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(PhaseIIIFindingClosureError, match="differs"):
        validate_phase3_finding_closure(
            closure,
            ledger,
            expected_source_commit=COMMIT,
            expected_source_tree=TREE,
            evidence_files=evidence,
        )


def test_changed_gate_evidence_bytes_fail(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.md"
    closure = tmp_path / "closure.json"
    _write_ledger(ledger)
    evidence = _evidence_files(tmp_path)
    _write_record(closure, _record(ledger, evidence))
    evidence.m6_evidence.write_text('{"changed":true}\n', encoding="utf-8")

    with pytest.raises(PhaseIIIFindingClosureError, match="M6 evidence differs"):
        validate_phase3_finding_closure(
            closure,
            ledger,
            expected_source_commit=COMMIT,
            expected_source_tree=TREE,
            evidence_files=evidence,
        )


def test_cross_source_closure_fails(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.md"
    closure = tmp_path / "closure.json"
    _write_ledger(ledger)
    evidence = _evidence_files(tmp_path)
    _write_record(closure, _record(ledger, evidence))

    with pytest.raises(PhaseIIIFindingClosureError, match="another source commit"):
        validate_phase3_finding_closure(
            closure,
            ledger,
            expected_source_commit="8" * 40,
            expected_source_tree=TREE,
            evidence_files=evidence,
        )


def test_duplicate_json_key_fails(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.md"
    closure = tmp_path / "closure.json"
    _write_ledger(ledger)
    evidence = _evidence_files(tmp_path)
    closure.write_text(
        '{"schema_version":"2.0","schema_version":"2.0"}\n',
        encoding="utf-8",
    )

    with pytest.raises(PhaseIIIFindingClosureError, match="duplicate"):
        validate_phase3_finding_closure(
            closure,
            ledger,
            expected_source_commit=COMMIT,
            expected_source_tree=TREE,
            evidence_files=evidence,
        )
