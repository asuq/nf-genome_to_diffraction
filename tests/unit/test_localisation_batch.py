import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.localisation import (
    BatchLocalisationImportRequest,
    FirstWaveDisposition,
    LocalisationBatchImportError,
    LocalisationOutcome,
    import_catalogue_localisation_batch,
    validate_catalogue_localisation_batch,
)
from genome_to_diffraction.localisation.batch import (
    DEEPTMHMM_IMAGE_MANIFEST_SHA256,
    PSORTB_IMAGE_MANIFEST_SHA256,
)
from genome_to_diffraction.schemas.results import (
    SequenceGroupRecord,
    SourceProteinRecord,
)
from tests.support.unknown_pass1_fixture import (
    materialise_localisation_container_execution_fixture,
)


def _group(sequence: str, source_count: int) -> SequenceGroupRecord:
    digest = hashlib.sha256(sequence.encode("ascii")).hexdigest()
    return SequenceGroupRecord(
        schema_version="1.0",
        sequence_group_id=f"seq_{digest}",
        sha256=digest,
        sequence=sequence,
        length_aa=len(sequence),
        mass_method="test exact sequence mass",
        residue_policy="canonical test residues",
        source_record_count=source_count,
    )


def _source(group: SequenceGroupRecord, protein_id: str) -> SourceProteinRecord:
    digest = hashlib.sha256(f"source:{protein_id}".encode("ascii")).hexdigest()
    return SourceProteinRecord(
        schema_version="1.0",
        source_record_id=f"src_{digest}",
        catalogue_id="catalogue_test",
        original_protein_id=protein_id,
        original_header=f"{protein_id} test protein",
        sequence_group_id=group.sequence_group_id,
        source_annotation_provider="test annotation",
    )


def _inputs(tmp_path: Path) -> BatchLocalisationImportRequest:
    soluble = _group("ACDEFGHIKLMNPQRSTVWU", 2)
    membrane = _group("MAVILFWYACDEGHKNPQRS", 1)
    conflicting = _group("MKKLLVVAAACCGGTTNNQQ", 2)
    groups = (soluble, membrane, conflicting)
    soluble_source = _source(soluble, "PROT_SOL")
    sources = (
        soluble_source,
        soluble_source.model_copy(update={"source_record_id": "src_" + "f" * 64}),
        _source(membrane, "PROT_MEM"),
        _source(conflicting, "PROT_CONFLICT_A"),
        _source(conflicting, "PROT_CONFLICT_B"),
    )
    sequence_groups = tmp_path / "sequence_groups.jsonl"
    sequence_groups.write_text(
        "".join(f"{canonical_json_text(row)}\n" for row in reversed(groups)),
        encoding="ascii",
    )
    source_records = tmp_path / "source_records.jsonl"
    source_records.write_text(
        "".join(f"{canonical_json_text(row)}\n" for row in reversed(sources)),
        encoding="ascii",
    )
    psortb = tmp_path / "psortb.tsv"
    psortb.write_text(
        "SeqID\tLocalization\tScore\n"
        "PROT_CONFLICT_B test protein\tCytoplasmic\t8.00\n"
        "PROT_MEM test protein\tCytoplasmicMembrane\t9.99\n"
        "PROT_SOL test protein\tCytoplasmic\t9.50\n"
        "PROT_CONFLICT_A test protein\tCytoplasmic\t8.00\n",
        encoding="ascii",
    )
    deep = tmp_path / "deeptmhmm.3line"
    deep.write_text(
        ">PROT_MEM | TM\n"
        f"{membrane.sequence}\n"
        f"{'M' * membrane.length_aa}\n"
        ">PROT_CONFLICT_A | TM\n"
        f"{conflicting.sequence}\n"
        f"{'M' * conflicting.length_aa}\n"
        ">PROT_SOL | GLOB\n"
        f"{soluble.sequence}\n"
        f"{'O' * soluble.length_aa}\n"
        ">PROT_CONFLICT_B | TM\n"
        f"{conflicting.sequence}\n"
        f"{'M' * conflicting.length_aa}\n",
        encoding="ascii",
    )
    gel = tmp_path / "gel.json"
    gel.write_text('{"schema_version":"2.0","observations":[]}\n', encoding="ascii")
    group_by_id = {group.sequence_group_id: group for group in groups}
    catalogue_fasta = tmp_path / "catalogue.faa"
    catalogue_fasta.write_text(
        "".join(
            f">{source.original_header}\n"
            f"{group_by_id[source.sequence_group_id].sequence}\n"
            for source in sources
            if source.source_record_id != "src_" + "f" * 64
        ),
        encoding="ascii",
    )
    execution = materialise_localisation_container_execution_fixture(
        tmp_path,
        catalogue_fasta=catalogue_fasta,
        psortb_output=psortb,
        deeptmhmm_output=deep,
    )
    return BatchLocalisationImportRequest(
        sequence_groups_jsonl=sequence_groups,
        source_records_jsonl=source_records,
        catalogue_fasta=catalogue_fasta,
        psortb_terse=psortb,
        deeptmhmm_topologies=deep,
        gel_evidence=gel,
        container_execution_bundle=execution,
        output_directory=tmp_path / "output",
    )


def _reauthorise(
    request: BatchLocalisationImportRequest,
    root: Path,
) -> BatchLocalisationImportRequest:
    execution = materialise_localisation_container_execution_fixture(
        root,
        catalogue_fasta=request.catalogue_fasta,
        psortb_output=request.psortb_terse,
        deeptmhmm_output=request.deeptmhmm_topologies,
    )
    return replace(request, container_execution_bundle=execution)


def test_importer_builds_complete_conservative_first_wave(tmp_path: Path) -> None:
    result = import_catalogue_localisation_batch(_inputs(tmp_path))

    policy = result.policy
    assert policy.sequence_group_count == 3
    assert policy.source_record_count == 5
    assert policy.gel_observation_count == 0
    assert policy.active_count == 1
    assert policy.excluded_count == 1
    assert policy.neutral_count == 1
    assert policy.conflicting_count == 1
    by_outcome = {row.merged_outcome: row for row in policy.group_evidence}
    assert by_outcome[LocalisationOutcome.SOLUBLE].first_wave_disposition is (
        FirstWaveDisposition.ACTIVE
    )
    assert len(by_outcome[LocalisationOutcome.SOLUBLE].source_record_ids) == 2
    assert by_outcome[LocalisationOutcome.SOLUBLE].warnings == (
        "psortb_replaced_selenocysteine_with_x",
    )
    assert by_outcome[LocalisationOutcome.TRANSMEMBRANE].first_wave_disposition is (
        FirstWaveDisposition.EXCLUDED
    )
    assert by_outcome[LocalisationOutcome.CONFLICTING].first_wave_disposition is (
        FirstWaveDisposition.NEUTRAL
    )
    assert len(by_outcome[LocalisationOutcome.CONFLICTING].source_record_ids) == 2
    assert policy.psortb_runtime.image_manifest_sha256 == PSORTB_IMAGE_MANIFEST_SHA256
    assert policy.psortb_runtime.network_mode == "none"
    assert (
        policy.deeptmhmm_runtime.image_manifest_sha256
        == DEEPTMHMM_IMAGE_MANIFEST_SHA256
    )
    assert policy.deeptmhmm_runtime.network_mode == "none"
    manifest = json.loads(result.manifest_json.read_text(encoding="utf-8"))
    assert manifest["sequence_group_count"] == 3
    assert manifest["source_record_count"] == 5
    assert (result.output_directory / "raw/psortb-terse.tsv").is_file()
    assert (result.output_directory / "raw/deeptmhmm-topologies.3line").is_file()
    assert validate_catalogue_localisation_batch(result.output_directory) == policy


def test_importer_rejects_incomplete_tool_coverage(tmp_path: Path) -> None:
    request = _inputs(tmp_path)
    request.psortb_terse.write_text(
        request.psortb_terse.read_text(encoding="ascii").replace(
            "PROT_MEM test protein\tCytoplasmicMembrane\t9.99\n", ""
        ),
        encoding="ascii",
    )
    request = _reauthorise(request, tmp_path / "incomplete-execution")

    with pytest.raises(
        LocalisationBatchImportError,
        match="source coverage differs",
    ):
        import_catalogue_localisation_batch(request)


def test_importer_keeps_explicit_sequence_local_failures_neutral(
    tmp_path: Path,
) -> None:
    request = _inputs(tmp_path)
    request.psortb_terse.write_text(
        request.psortb_terse.read_text(encoding="ascii").replace(
            "PROT_SOL test protein\tCytoplasmic\t9.50\n",
            "",
        ),
        encoding="ascii",
    )
    deep_lines = request.deeptmhmm_topologies.read_text(encoding="ascii").splitlines()
    request.deeptmhmm_topologies.write_text(
        "\n".join(deep_lines[0:6] + deep_lines[9:]) + "\n",
        encoding="ascii",
    )
    execution = materialise_localisation_container_execution_fixture(
        tmp_path / "failed-execution",
        catalogue_fasta=request.catalogue_fasta,
        psortb_output=request.psortb_terse,
        deeptmhmm_output=request.deeptmhmm_topologies,
        psortb_failed_source_ids=("PROT_SOL",),
        deeptmhmm_failed_source_ids=("PROT_SOL",),
    )

    result = import_catalogue_localisation_batch(
        replace(
            request,
            container_execution_bundle=execution,
            output_directory=tmp_path / "failed-output",
        )
    )

    failed = next(
        row
        for row in result.policy.group_evidence
        if row.merged_outcome is LocalisationOutcome.FAILED
    )
    assert failed.first_wave_disposition is FirstWaveDisposition.NEUTRAL
    assert set(failed.warnings) >= {
        "psortb_sequence_local_failure",
        "deeptmhmm_sequence_local_failure",
    }


def test_importer_rejects_disagreement_for_duplicate_exact_sequence(
    tmp_path: Path,
) -> None:
    request = _inputs(tmp_path)
    request.deeptmhmm_topologies.write_text(
        request.deeptmhmm_topologies.read_text(encoding="ascii").replace(
            ">PROT_CONFLICT_B | TM", ">PROT_CONFLICT_B | GLOB"
        ),
        encoding="ascii",
    )
    request = _reauthorise(request, tmp_path / "disagreement-execution")

    with pytest.raises(
        LocalisationBatchImportError,
        match="different predictions",
    ):
        import_catalogue_localisation_batch(request)


def test_importer_rejects_unknown_deeptmhmm_topology_label(tmp_path: Path) -> None:
    request = _inputs(tmp_path)
    request.deeptmhmm_topologies.write_text(
        request.deeptmhmm_topologies.read_text(encoding="ascii").replace(
            "M" * 20,
            "Z" * 20,
            1,
        ),
        encoding="ascii",
    )
    request = _reauthorise(request, tmp_path / "unknown-label-execution")

    with pytest.raises(LocalisationBatchImportError, match="record 1 is invalid"):
        import_catalogue_localisation_batch(request)


def test_validator_rejects_mutated_raw_evidence(tmp_path: Path) -> None:
    result = import_catalogue_localisation_batch(_inputs(tmp_path))
    raw = result.output_directory / "raw/psortb-terse.tsv"
    raw.write_text(raw.read_text(encoding="ascii") + "changed\n", encoding="ascii")

    with pytest.raises(
        LocalisationBatchImportError,
        match="evidence changed",
    ):
        validate_catalogue_localisation_batch(result.output_directory)


def test_validator_rejects_bridge_network_runtime(tmp_path: Path) -> None:
    result = import_catalogue_localisation_batch(_inputs(tmp_path))
    policy_path = result.output_directory / "first_wave_policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["psortb_runtime"]["network_mode"] = "bridge"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")

    with pytest.raises(
        LocalisationBatchImportError,
        match="contract is invalid",
    ):
        validate_catalogue_localisation_batch(result.output_directory)
