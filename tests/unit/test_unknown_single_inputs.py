"""Tests for the fixed A-seed decision archive."""

import tarfile
from pathlib import Path

import pytest

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.hpc.unknown_single_inputs import (
    UNKNOWN_SINGLE_SPEC_RELATIVE,
    UnknownSingleComponentInputError,
    build_unknown_single_component_input_bundle,
    stage_unknown_single_component_handoff,
    validate_unknown_single_component_input_tree,
)

PARENT = "gtd-unknown-screen-20260825T000000Z-aaaaaaaaaaaa-bbbbbbbb"
HEADER = (
    "checkpoint\towned_parent_run_id\treview_package_id\t"
    "review_package_manifest_sha256\tcrystal_id\titem_id\tdecision\t"
    "reviewer\treviewed_at\treason\n"
)


def _decision(path: Path, crystal_id: str, *, parent: str = PARENT) -> None:
    path.write_text(
        HEADER + f"a_seed\t{parent}\treviewpkg_{'1' * 64}\t{'2' * 64}\t"
        f"{crystal_id}\tsolution_1\tapprove\treviewer\t"
        "2026-08-25T00:00:00Z\tmap inspected\n",
        encoding="ascii",
    )


def _spec(root: Path, rows: tuple[tuple[str, Path], ...]) -> Path:
    path = root / UNKNOWN_SINGLE_SPEC_RELATIVE
    path.parent.mkdir(parents=True)
    atomic_write_json(
        path,
        {
            "schema_version": "1.0",
            "decisions": [
                {
                    "crystal_id": crystal_id,
                    "path": str(decision),
                    "sha256": sha256_file(decision, progress=False),
                }
                for crystal_id, decision in rows
            ],
        },
    )
    path.chmod(0o600)
    return path


def test_unknown_single_decision_archive_round_trips(tmp_path: Path) -> None:
    first_decision = tmp_path / "first.tsv"
    second_decision = tmp_path / "second.tsv"
    _decision(first_decision, "crystal_a")
    _decision(second_decision, "crystal_b")
    _spec(
        tmp_path,
        (("crystal_b", second_decision), ("crystal_a", first_decision)),
    )

    first = build_unknown_single_component_input_bundle(
        repository=tmp_path,
        parent_run_id=PARENT,
        archive_path=tmp_path / "first.tar",
    )
    second = build_unknown_single_component_input_bundle(
        repository=tmp_path,
        parent_run_id=PARENT,
        archive_path=tmp_path / "second.tar",
    )

    assert first.archive_sha256 == second.archive_sha256
    assert first.crystal_ids == ("crystal_a", "crystal_b")
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    with tarfile.open(first.archive_path, mode="r") as archive:
        archive.extractall(extracted, filter="data")
    assert (
        validate_unknown_single_component_input_tree(
            extracted,
            expected_input_id=first.input_id,
            expected_parent_run_id=PARENT,
        )
        == first.crystal_ids
    )


def test_cross_parent_decision_fails(tmp_path: Path) -> None:
    decision = tmp_path / "decision.tsv"
    _decision(decision, "crystal_a", parent="gtd-unknown-screen-other")
    _spec(tmp_path, (("crystal_a", decision),))

    with pytest.raises(UnknownSingleComponentInputError, match="another authority"):
        build_unknown_single_component_input_bundle(
            repository=tmp_path,
            parent_run_id=PARENT,
            archive_path=tmp_path / "inputs.tar",
        )


def test_checksum_confirmation_is_required(tmp_path: Path) -> None:
    decision = tmp_path / "decision.tsv"
    _decision(decision, "crystal_a")
    spec = _spec(tmp_path, (("crystal_a", decision),))
    document = {
        "schema_version": "1.0",
        "decisions": [
            {
                "crystal_id": "crystal_a",
                "path": str(decision),
                "sha256": "0" * 64,
            }
        ],
    }
    atomic_write_json(spec, document)
    spec.chmod(0o600)

    with pytest.raises(UnknownSingleComponentInputError, match="checksum differs"):
        build_unknown_single_component_input_bundle(
            repository=tmp_path,
            parent_run_id=PARENT,
            archive_path=tmp_path / "inputs.tar",
        )


def test_changed_extracted_decision_fails(tmp_path: Path) -> None:
    decision = tmp_path / "decision.tsv"
    _decision(decision, "crystal_a")
    _spec(tmp_path, (("crystal_a", decision),))
    bundle = build_unknown_single_component_input_bundle(
        repository=tmp_path,
        parent_run_id=PARENT,
        archive_path=tmp_path / "inputs.tar",
    )
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    with tarfile.open(bundle.archive_path, mode="r") as archive:
        archive.extractall(extracted, filter="data")
    staged = extracted / "decisions/crystal_a.tsv"
    staged.write_bytes(staged.read_bytes() + b"\n")

    with pytest.raises(UnknownSingleComponentInputError, match="changed"):
        validate_unknown_single_component_input_tree(
            extracted,
            expected_input_id=bundle.input_id,
            expected_parent_run_id=PARENT,
        )


def test_handoff_refuses_missing_parent_terminal_evidence(tmp_path: Path) -> None:
    decision = tmp_path / "decision.tsv"
    _decision(decision, "crystal_a")
    _spec(tmp_path, (("crystal_a", decision),))
    bundle = build_unknown_single_component_input_bundle(
        repository=tmp_path,
        parent_run_id=PARENT,
        archive_path=tmp_path / "inputs.tar",
    )
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    with tarfile.open(bundle.archive_path, mode="r") as archive:
        archive.extractall(extracted, filter="data")
    parent = tmp_path / PARENT
    child = tmp_path / "gtd-unknown-single-component-child"
    parent.mkdir()
    child.mkdir()

    with pytest.raises(UnknownSingleComponentInputError, match="terminal result"):
        stage_unknown_single_component_handoff(
            parent_run_root=parent,
            child_run_root=child,
            input_root=extracted,
            child_run_id=child.name,
            expected_input_id=bundle.input_id,
        )
