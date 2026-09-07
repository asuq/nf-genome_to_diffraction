"""Protect full inventory coverage, fixed MR semantics and archive confinement."""

import io
import json
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

from genome_to_diffraction.checksums import atomic_write_json
from genome_to_diffraction.hpc import identification_run
from genome_to_diffraction.hpc.identification_inputs import (
    MANIFEST_NAME,
    IdentificationInputError,
    build_identification_input_bundle,
    execution_cases,
    unpack_identification_archive,
    validate_plan,
)
from genome_to_diffraction.mr_resources import MrResourcePlanError
from tests.support.identification_fixture import materialise_identification_fixture

REPOSITORY = Path(__file__).resolve().parents[2]
SOURCE_COMMIT = "a" * 40


def test_complete_inventory_has_no_25_candidate_acquisition_cap(tmp_path: Path) -> None:
    root, plan = materialise_identification_fixture(
        tmp_path, group_count=30, all_ready=True
    )
    validated = validate_plan(root, allowed_mtz_root=tmp_path)
    assert len(validated.cases) == 30
    assert len(execution_cases(plan)) == 30
    assert all(c.status == "ready" for c in validated.cases)


@pytest.mark.parametrize(
    "mutation", ["omit", "duplicate", "accession", "copies", "coordinate", "scope"]
)
def test_candidate_or_input_mutation_fails_closed(
    tmp_path: Path, mutation: str
) -> None:
    root, plan = materialise_identification_fixture(tmp_path)
    raw = plan.model_dump(mode="json")
    if mutation == "omit":
        raw["cases"].pop()
    elif mutation == "duplicate":
        raw["cases"].append(raw["cases"][0])
    elif mutation == "accession":
        raw["cases"][0]["accessions"] = ["another_gene"]
    elif mutation == "copies":
        raw["cases"][0]["component_copies"] += 1
    elif mutation == "scope":
        raw["crystals"][0]["symmetry_multiplicity"] = 2
    else:
        (root / "coordinates/1ABC.cif.gz").write_bytes(b"changed")
    atomic_write_json(root / "plan.json", raw)
    with pytest.raises(IdentificationInputError):
        validate_plan(root, allowed_mtz_root=tmp_path)


def test_bundle_is_source_bound_and_round_trips(tmp_path: Path) -> None:
    _root, plan = materialise_identification_fixture(tmp_path)
    first = build_identification_input_bundle(
        repository=tmp_path,
        archive_path=tmp_path / "first.tar",
        source_commit=SOURCE_COMMIT,
    )
    second = build_identification_input_bundle(
        repository=tmp_path,
        archive_path=tmp_path / "second.tar",
        source_commit=SOURCE_COMMIT,
    )
    assert first.archive_sha256 == second.archive_sha256
    result = unpack_identification_archive(
        first.archive_path,
        tmp_path / "unpacked",
        expected_input_id=first.input_id,
        source_commit=SOURCE_COMMIT,
        allowed_mtz_root=tmp_path,
    )
    assert result == plan
    with pytest.raises(IdentificationInputError, match="ownership"):
        unpack_identification_archive(
            first.archive_path,
            tmp_path / "different",
            expected_input_id=first.input_id,
            source_commit="b" * 40,
            allowed_mtz_root=tmp_path,
        )
    assert not (tmp_path / "different").exists()


@pytest.mark.parametrize(
    "unsafe", ["traversal", "symlink", "hardlink", "duplicate", "oversized"]
)
def test_unsafe_archive_is_rejected_before_extraction(
    tmp_path: Path, unsafe: str
) -> None:
    archive_path = tmp_path / "unsafe.tar"
    with tarfile.open(archive_path, "w") as archive:
        member = tarfile.TarInfo("../escaped" if unsafe == "traversal" else "member")
        member.size = 1
        if unsafe in {"symlink", "hardlink"}:
            member.type = tarfile.SYMTYPE if unsafe == "symlink" else tarfile.LNKTYPE
            member.linkname = "../escaped"
            member.size = 0
        if unsafe == "oversized":
            member.size = 2 * 1024**3
            # A header-only malformed archive must not reach extraction.
            archive.fileobj.write(member.tobuf())
        else:
            archive.addfile(member, io.BytesIO(b"x"))
            if unsafe == "duplicate":
                archive.addfile(member, io.BytesIO(b"x"))
    with pytest.raises((IdentificationInputError, tarfile.TarError)):
        unpack_identification_archive(
            archive_path,
            tmp_path / "output",
            expected_input_id="identificationinputs_" + "a" * 64,
            source_commit=SOURCE_COMMIT,
            allowed_mtz_root=tmp_path,
        )
    assert not (tmp_path / "output").exists()
    assert not (tmp_path.parent / "escaped").exists()


def test_real_chain_preparation_and_resource_thread_contract(tmp_path: Path) -> None:
    root, plan = materialise_identification_fixture(tmp_path)
    case = plan.cases[0]
    prepared = tmp_path / "prepared"
    identification_run.prepare_case(root, case.case_id, prepared)
    record = json.loads((prepared / "preparation.json").read_text())
    assert record["status"] == "prepared"
    assert record["resource_plan"]["base_cpus"] == 8
    assert record["resource_plan"]["searched_copy_count"] == 1
    command = identification_run.phaser_command(plan, case, prepared, 8)
    assert "phaser.search_copies=1" in command
    assert f"phaser.component_copies={case.component_copies}" in command
    assert "phaser.keywords.general.jobs=8" in command
    assert (prepared / "candidate.fasta").read_text().endswith("ACDQ\n")
    with pytest.raises(MrResourcePlanError, match="threads"):
        identification_run.run_case(
            root,
            case.case_id,
            prepared,
            tmp_path / "absent_manifest.json",
            4,
            1,
            tmp_path / "not_started",
        )
    assert not (tmp_path / "not_started").exists()


@pytest.mark.parametrize("kind", ["no_hit", "malformed", "resource_failure"])
def test_native_execution_outcomes_stay_separate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    root, plan = materialise_identification_fixture(tmp_path)
    case = plan.cases[0]
    prepared = tmp_path / "prepared"
    identification_run.prepare_case(root, case.case_id, prepared)

    def capture(manifest, command, *, working_directory, timeout_seconds):
        assert timeout_seconds is None
        log = (
            (
                REPOSITORY / "tests/fixtures/phaser/phenix_2_1_no_solution.log"
            ).read_text()
            if kind == "no_hit"
            else "incomplete output"
        )
        (working_directory / "PHASER.log").write_text(log)
        return subprocess.CompletedProcess(
            command, 137 if kind == "resource_failure" else 0, b"native output", b""
        )

    monkeypatch.setattr(identification_run, "capture_from_manifest", capture)
    out = tmp_path / "run"
    code = identification_run.run_case(
        root, case.case_id, prepared, tmp_path / "mock_manifest", 8, 1, out
    )
    record = json.loads((out / "run.json").read_text())
    expected = {
        "no_hit": "completed_no_hit",
        "malformed": "failed_parse",
        "resource_failure": "execution_failed",
    }
    assert record["status"] == expected[kind]
    assert record["identity_accepted"] is False
    assert code == (137 if kind == "resource_failure" else 0)


def test_failed_preparation_does_not_become_a_no_hit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, plan = materialise_identification_fixture(tmp_path)

    def fail(*args, **kwargs):
        raise identification_run.PdbCoordinateParseError("author chain absent")

    monkeypatch.setattr(identification_run, "_pdb_entity", fail)
    out = tmp_path / "failed_preparation"
    identification_run.prepare_case(root, plan.cases[0].case_id, out)
    assert (
        json.loads((out / "preparation.json").read_text())["status"]
        == "model_preparation_failed"
    )
    assert not (out / "resource_plan.json").exists()


def test_collection_preserves_unpublished_killed_task_without_scientific_claim(
    tmp_path: Path,
) -> None:
    root, plan = materialise_identification_fixture(tmp_path)
    bundle = build_identification_input_bundle(
        repository=tmp_path,
        archive_path=tmp_path / "bundle.tar",
        source_commit=SOURCE_COMMIT,
    )
    shutil.copyfile(
        bundle.archive_path.with_suffix(".manifest.json"), root / MANIFEST_NAME
    )
    case = plan.cases[0]
    work_root = tmp_path / "work"
    work = work_root / "aa" / ("b" * 30)
    child = work / case.case_id
    child.mkdir(parents=True)
    (child / "PHASER.log").write_text("unfinished native calculation\n")
    (child / "PHASER.1.mtz").write_bytes(b"partial diagnostic map bytes")
    atomic_write_json(
        child / "run.json",
        {"case_id": case.case_id, "status": "running", "identity_accepted": False},
    )
    (work / ".exitcode").write_text("143\n")
    results = tmp_path / "results"
    (results / "pipeline_info").mkdir(parents=True)
    (results / "pipeline_info/trace.tsv").write_text(
        "task_id\ttag\tstatus\texit\tworkdir\n"
        + f"1\tidentification-mr:{case.case_id}\tFAILED\t143\t{work}\n"
    )
    out = tmp_path / "collected"
    identification_run.summarise(root, results, work_root, out)
    report = json.loads((out / "assessment.json").read_text())
    row = next(r for r in report["cases"] if r["case"]["case_id"] == case.case_id)
    assert row["execution_state"] == "mr_failed_without_published_result"
    assert report["identity_accepted"] is False
    assert (
        out / "attempts/1/PHASER.log"
    ).read_text() == "unfinished native calculation\n"
    assert not (out / "attempts/1/PHASER.1.mtz").exists()
    assert any(
        a["path"].endswith("PHASER.1.mtz") and not a["collected"]
        for a in report["artifacts"]
    )
