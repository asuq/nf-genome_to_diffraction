"""Focused offline localisation command, parser, contract, and failure tests."""

import hashlib
import json
from pathlib import Path

import pytest

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.localisation import (
    DeepTMHMMRuntimeContract,
    LocalisationOutcome,
    PSortbRuntimeContract,
    build_psortb_command,
    parse_psortb_terse,
    plan_deeptmhmm_invocation,
    resolve_localisation_outcome,
    run_psortb,
    write_sequence_group_fasta,
)
from genome_to_diffraction.schemas.results import SequenceGroupRecord
from genome_to_diffraction.status import (
    ExecutionStatus,
    InputContractError,
    ResultParseError,
)

REPOSITORY = Path(__file__).resolve().parents[2]
FIXTURE = REPOSITORY / "tests/fixtures/localisation/psortb_archaea_terse.tsv"
SEQUENCE = "MFEFITDEDERGQVGIGTLIVFIAMVLVAAIAAGVLINTAGY"
SEQUENCE_SHA256 = hashlib.sha256(SEQUENCE.encode("ascii")).hexdigest()
SEQUENCE_GROUP_ID = f"seq_{SEQUENCE_SHA256}"


def _sequence_group(sequence: str = SEQUENCE) -> SequenceGroupRecord:
    digest = hashlib.sha256(sequence.encode("ascii")).hexdigest()
    return SequenceGroupRecord(
        schema_version="1.0",
        sequence_group_id=f"seq_{digest}",
        sha256=digest,
        sequence=sequence,
        length_aa=len(sequence),
        molecular_mass_da=None,
        mass_method="not_calculated",
        residue_policy="standard_amino_acids",
        source_record_count=1,
    )


def _write_psortb(path: Path, *, exit_status: int = 0, malformed: bool = False) -> None:
    output = (
        "malformed-output"
        if malformed
        else f"{SEQUENCE_GROUP_ID}\\tCytoplasmicMembrane\\t9.80"
    )
    path.write_text(
        "#!/usr/bin/env bash\n"
        "set -u\n"
        'if [[ "${1-}" == "--version" ]]; then\n'
        "  printf 'PSORTb version 3.0.6\\n'\n"
        "  exit 0\n"
        "fi\n"
        "printf 'stub-stderr-marker\\n' >&2\n"
        f"printf '{output}\\n'\n"
        f"exit {exit_status}\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def test_psortb_command_matches_official_archaeal_terse_syntax(tmp_path: Path) -> None:
    executable = tmp_path / "psort"
    _write_psortb(executable)
    runtime = PSortbRuntimeContract.from_executable(executable)
    fasta = tmp_path / "sequence.faa"

    assert build_psortb_command(runtime, fasta) == (
        str(executable.resolve()),
        "-a",
        "-o",
        "terse",
        str(fasta),
    )
    assert runtime.provenance.public_sequence_submission is False
    assert runtime.provenance.network_access_used is False


def test_psortb_frozen_terse_parser() -> None:
    parsed = parse_psortb_terse(
        FIXTURE,
        expected_sequence_group_id=SEQUENCE_GROUP_ID,
    )

    assert parsed.raw_label == "Extracellular"
    assert parsed.score == pytest.approx(9.98)
    assert parsed.outcome is LocalisationOutcome.EXTRACELLULAR


@pytest.mark.parametrize(
    ("label", "expected"),
    (
        ("Cellwall", LocalisationOutcome.SURFACE),
        ("Cytoplasmic", LocalisationOutcome.SOLUBLE),
        ("Unknown", LocalisationOutcome.UNKNOWN),
    ),
)
def test_psortb_archaeal_labels_are_typed(
    tmp_path: Path,
    label: str,
    expected: LocalisationOutcome,
) -> None:
    raw = tmp_path / "psortb.tsv"
    raw.write_text(f"{SEQUENCE_GROUP_ID}\t{label}\t0.0\n", encoding="utf-8")

    parsed = parse_psortb_terse(raw, expected_sequence_group_id=SEQUENCE_GROUP_ID)

    assert parsed.outcome is expected


def test_psortb_parser_rejects_unrecognised_output(tmp_path: Path) -> None:
    raw = tmp_path / "psortb.tsv"
    raw.write_text(f"{SEQUENCE_GROUP_ID}\tPeriplasm\t8.2\n", encoding="utf-8")

    with pytest.raises(ResultParseError, match="unsupported PSORTb archaeal"):
        parse_psortb_terse(raw, expected_sequence_group_id=SEQUENCE_GROUP_ID)


def test_psortb_stub_retains_raw_output_and_bound_provenance(tmp_path: Path) -> None:
    executable = tmp_path / "psort"
    _write_psortb(executable)
    runtime = PSortbRuntimeContract.from_executable(executable)

    output = run_psortb(runtime, _sequence_group(), tmp_path / "attempt")

    assert output.result.execution_status is ExecutionStatus.COMPLETED_SUCCESS
    assert output.result.outcome is LocalisationOutcome.MEMBRANE
    assert output.result.raw_label == "CytoplasmicMembrane"
    assert output.result.score == pytest.approx(9.8)
    assert sha256_file(Path(output.result.raw_output_path)) == (
        output.result.raw_output_sha256
    )
    assert sha256_file(Path(output.result.raw_stderr_path)) == (
        output.result.raw_stderr_sha256
    )
    command = json.loads(output.command_json.read_text(encoding="utf-8"))
    assert command["command"][1:] == ["-a", "-o", "terse", command["input_fasta_path"]]
    assert command["runtime_identity_sha256"] == runtime.runtime_identity_sha256
    assert output.result.provenance.public_sequence_submission is False


def test_psortb_tool_failure_is_typed_and_retains_diagnostics(tmp_path: Path) -> None:
    executable = tmp_path / "psort"
    _write_psortb(executable, exit_status=7)
    runtime = PSortbRuntimeContract.from_executable(executable)

    result = run_psortb(runtime, _sequence_group(), tmp_path / "failure").result

    assert result.execution_status is ExecutionStatus.FAILED_TOOL_EXECUTION
    assert result.outcome is LocalisationOutcome.FAILED
    assert result.warnings == ("PSORTb exited with status 7",)
    assert "stub-stderr-marker" in Path(result.raw_stderr_path).read_text(
        encoding="utf-8"
    )
    assert Path(result.raw_output_path).read_text(encoding="utf-8").strip()


def test_psortb_parse_failure_is_a_typed_result(tmp_path: Path) -> None:
    executable = tmp_path / "psort"
    _write_psortb(executable, malformed=True)
    runtime = PSortbRuntimeContract.from_executable(executable)

    result = run_psortb(runtime, _sequence_group(), tmp_path / "parse-failure").result

    assert result.execution_status is ExecutionStatus.FAILED_PARSE
    assert result.outcome is LocalisationOutcome.FAILED
    assert "three columns" in result.warnings[0]


def test_psortb_runtime_checksum_mutation_fails_closed(tmp_path: Path) -> None:
    executable = tmp_path / "psort"
    _write_psortb(executable)
    runtime = PSortbRuntimeContract.from_executable(executable)
    executable.write_text("changed", encoding="utf-8")

    with pytest.raises(InputContractError, match="checksum"):
        run_psortb(runtime, _sequence_group(), tmp_path / "mutated")


def test_psortb_runtime_version_mismatch_fails_closed(tmp_path: Path) -> None:
    executable = tmp_path / "psort"
    _write_psortb(executable)
    executable.write_text(
        executable.read_text(encoding="utf-8").replace("3.0.6", "3.0.5"),
        encoding="utf-8",
    )
    runtime = PSortbRuntimeContract.from_executable(executable)

    with pytest.raises(InputContractError, match=r"required version 3\.0\.6"):
        run_psortb(runtime, _sequence_group(), tmp_path / "wrong-version")


def test_deeptmhmm_user_image_and_input_are_bound_but_cli_is_blocked(
    tmp_path: Path,
) -> None:
    image = tmp_path / "deeptmhmm-1.0.sif"
    image.write_bytes(b"user-provided-academic-image-fixture")
    runtime = DeepTMHMMRuntimeContract.from_user_image(image)
    fasta = tmp_path / "sequence.faa"
    write_sequence_group_fasta(fasta, _sequence_group())

    plan = plan_deeptmhmm_invocation(runtime, _sequence_group(), fasta)

    assert plan.invocation_status == "blocked_unverified_cli"
    assert plan.command == ()
    assert "does not specify" in plan.block_reason
    assert plan.image_sha256 == sha256_file(image)
    assert plan.input_fasta_sha256 == sha256_file(fasta)
    assert plan.raw_output_retention_required is True
    assert plan.provenance.public_sequence_submission is False
    assert runtime.image_supplied_by_user is True
    assert runtime.redistribute_image is False


def test_deeptmhmm_image_mutation_fails_closed(tmp_path: Path) -> None:
    image = tmp_path / "deeptmhmm-1.0.sif"
    image.write_bytes(b"original")
    runtime = DeepTMHMMRuntimeContract.from_user_image(image)
    fasta = tmp_path / "sequence.faa"
    write_sequence_group_fasta(fasta, _sequence_group())
    image.write_bytes(b"mutated")

    with pytest.raises(InputContractError, match="checksum"):
        plan_deeptmhmm_invocation(runtime, _sequence_group(), fasta)


def test_deeptmhmm_rejects_residues_outside_official_alphabet(
    tmp_path: Path,
) -> None:
    image = tmp_path / "deeptmhmm-1.0.sif"
    image.write_bytes(b"user-image")
    runtime = DeepTMHMMRuntimeContract.from_user_image(image)
    sequence = "ACDX"
    record = _sequence_group(sequence)
    fasta = tmp_path / "sequence.faa"
    write_sequence_group_fasta(fasta, record)

    with pytest.raises(InputContractError, match="unsupported residues: X"):
        plan_deeptmhmm_invocation(runtime, record, fasta)


@pytest.mark.parametrize(
    ("outcomes", "expected"),
    (
        ((LocalisationOutcome.UNKNOWN,), LocalisationOutcome.UNKNOWN),
        ((LocalisationOutcome.FAILED,), LocalisationOutcome.FAILED),
        (
            (LocalisationOutcome.MEMBRANE, LocalisationOutcome.TRANSMEMBRANE),
            LocalisationOutcome.TRANSMEMBRANE,
        ),
        (
            (LocalisationOutcome.SURFACE, LocalisationOutcome.UNKNOWN),
            LocalisationOutcome.SURFACE,
        ),
        (
            (LocalisationOutcome.SOLUBLE, LocalisationOutcome.TRANSMEMBRANE),
            LocalisationOutcome.CONFLICTING,
        ),
        (
            (LocalisationOutcome.EXTRACELLULAR, LocalisationOutcome.SURFACE),
            LocalisationOutcome.CONFLICTING,
        ),
    ),
)
def test_localisation_resolution_is_explicit(
    outcomes: tuple[LocalisationOutcome, ...],
    expected: LocalisationOutcome,
) -> None:
    assert resolve_localisation_outcome(outcomes) is expected
