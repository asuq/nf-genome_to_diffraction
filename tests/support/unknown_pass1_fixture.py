"""Materialise the synthetic public unknown-pass-1 integration fixture."""

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.execution.unknown_screen import (
    UnknownPass1CrystalInput,
    UnknownPass1ModelInput,
    UnknownPass1ReviewDecisionInput,
    UnknownPass1SharedPreparationInput,
    build_unknown_pass1_screen_inventory,
    stage_unknown_pass1_crystallographic_reviews,
    write_unknown_pass1_screen_inventory,
)
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.localisation import (
    BatchLocalisationImportRequest,
    import_catalogue_localisation_batch,
)
from genome_to_diffraction.localisation.batch import (
    DEEPTMHMM_IMAGE_MANIFEST_SHA256,
    LOCALISATION_BATCH_ADAPTER_VERSION,
    PSORTB_IMAGE_MANIFEST_SHA256,
)
from genome_to_diffraction.localisation.container_execution import (
    DEEPTMHMM_IMAGE_REFERENCE,
    PSORTB_IMAGE_REFERENCE,
    LocalisationBatchExecutionManifest,
    LocalisationContainerToolExecution,
)
from genome_to_diffraction.review.owned_run import (
    OwnedPhaseIIIReviewPackageSource,
    register_phase3_owned_run,
)
from genome_to_diffraction.review.phase3_package import (
    PhaseIIIReviewEvidenceSource,
    PhaseIIIReviewPackageRequest,
    build_phase3_review_package,
)
from genome_to_diffraction.review.phase3_stage import (
    OwnedPhaseIIIParentRun,
)
from genome_to_diffraction.schemas.results import (
    SearchScientificStatus,
    SequenceGroupRecord,
    SourceProteinRecord,
    StructuralSearchResult,
)
from genome_to_diffraction.schemas.v2 import (
    ExecutionArtifactIdentity,
    ExecutionToolIdentity,
    ModelUnavailableReason,
    PhaseIIIExecutionIdentity,
    PhaseIIIReviewCheckpoint,
    PhaseIIIReviewDecision,
    PhaseIIIReviewDecisionFile,
    PhaseIIIReviewDecisionValue,
    UnknownPass1AHypothesis,
    UnknownPass1AHypothesisDisposition,
    UnknownPass1ScreenInventory,
)
from genome_to_diffraction.status import ExecutionStatus
from genome_to_diffraction.structure_search import (
    DisabledProviderBundleRequest,
    PhaseIIIProviderLoginStageFile,
    PhaseIIIProviderLoginStageManifest,
    emit_disabled_provider_bundle,
    validate_phase3_provider_discovery_package,
    validate_phase3_provider_login_stage,
)

PUBLIC_STUB_CRYSTAL_IDS = (
    "public_stub_01",
    "public_stub_02",
    "public_stub_03",
)
_PHENIX = (
    "phenix.maps",
    "phenix.phaser",
    "phenix.process_predicted_model",
    "phenix.refine",
    "phenix.reflection_file_converter",
    "phenix.sequence_from_map",
    "phenix.xtriage",
)


def materialise_localisation_container_execution_fixture(
    root: Path,
    *,
    catalogue_fasta: Path,
    psortb_output: Path,
    deeptmhmm_output: Path,
    psortb_failed_source_ids: tuple[str, ...] = (),
    deeptmhmm_failed_source_ids: tuple[str, ...] = (),
) -> Path:
    """Write checksum-valid synthetic Docker inspection evidence for tests."""

    output = root / "container-execution"
    output.mkdir(parents=True)
    records = []
    for index, (
        tool,
        image_reference,
        raw_output,
        failed_source_ids,
    ) in enumerate(
        (
            (
                "psortb",
                PSORTB_IMAGE_REFERENCE,
                psortb_output,
                psortb_failed_source_ids,
            ),
            (
                "deeptmhmm",
                DEEPTMHMM_IMAGE_REFERENCE,
                deeptmhmm_output,
                deeptmhmm_failed_source_ids,
            ),
        ),
        start=1,
    ):
        digest = image_reference.rsplit("sha256:", maxsplit=1)[1]
        command = (
            ("/usr/local/bin/psort", "-a", "-o", "terse", "-i", "/input.faa")
            if tool == "psortb"
            else ("python3", "predict.py", "--fasta", "/input.faa")
        )
        working_directory = "/tmp/results" if tool == "psortb" else "/openprotein"
        container_id = f"{index:064x}"
        image_id = f"sha256:{index + 10:064x}"
        container_json = json.dumps(
            [
                {
                    "Id": container_id,
                    "Image": image_id,
                    "Path": command[0],
                    "Args": list(command[1:]),
                    "Config": {
                        "Image": image_reference,
                        "WorkingDir": working_directory,
                    },
                    "HostConfig": {"NetworkMode": "none"},
                    "State": {
                        "Status": "exited",
                        "Running": False,
                        "ExitCode": 0,
                    },
                }
            ],
            sort_keys=True,
            separators=(",", ":"),
        )
        image_json = json.dumps(
            [
                {
                    "Id": image_id,
                    "Os": "linux",
                    "Architecture": "amd64",
                    "RepoDigests": [image_reference.removeprefix("docker.io/")],
                }
            ],
            sort_keys=True,
            separators=(",", ":"),
        )
        log_name = f"{tool}-container.log"
        log = output / log_name
        log.write_text(f"synthetic terminal {tool} log\n", encoding="ascii")
        records.append(
            LocalisationContainerToolExecution.from_content(
                tool=tool,
                tool_version="3.0.6" if tool == "psortb" else "1.0",
                container_id=container_id,
                image_reference=image_reference,
                image_manifest_sha256=digest,
                image_id=image_id,
                platform="linux/amd64",
                docker_engine_version="Docker Engine test",
                container_inspect_json=container_json,
                container_inspect_sha256=hashlib.sha256(
                    container_json.encode("utf-8")
                ).hexdigest(),
                image_inspect_json=image_json,
                image_inspect_sha256=hashlib.sha256(
                    image_json.encode("utf-8")
                ).hexdigest(),
                effective_command=command,
                working_directory=working_directory,
                network_mode="none",
                terminal_status="exited",
                exit_code=0,
                input_container_path="/input.faa",
                input_fasta_sha256=sha256_file(catalogue_fasta),
                input_fasta_size_bytes=catalogue_fasta.stat().st_size,
                output_container_path=(
                    "/tmp/results/psortb.tsv"
                    if tool == "psortb"
                    else "/openprotein/predicted_topologies.3line"
                ),
                raw_output_sha256=sha256_file(raw_output),
                raw_output_size_bytes=raw_output.stat().st_size,
                log_path=log_name,
                log_sha256=sha256_file(log),
                log_size_bytes=log.stat().st_size,
                explicit_failed_source_ids=failed_source_ids,
            )
        )
    manifest = LocalisationBatchExecutionManifest.from_content(
        source_fasta_sha256=sha256_file(catalogue_fasta),
        source_fasta_size_bytes=catalogue_fasta.stat().st_size,
        psortb=records[0],
        deeptmhmm=records[1],
    )
    atomic_write_json(
        output / "localisation_container_execution.json",
        manifest.model_dump(mode="json"),
    )
    return output


def materialise_neutral_localisation_fixture(
    root: Path,
    *,
    gel_evidence: Path,
    sequence_groups_jsonl: Path | None = None,
    source_records_jsonl: Path | None = None,
    psortb_label: str = "Cytoplasmic",
    deeptmhmm_type: str = "GLOB",
    deeptmhmm_topology_label: str = "O",
) -> Path:
    """Write one complete local result for archive/wiring tests."""

    if sequence_groups_jsonl is None:
        sequence = "MPEPTIDE"
        sequence_sha256 = hashlib.sha256(sequence.encode("ascii")).hexdigest()
        group = SequenceGroupRecord(
            schema_version="1.0",
            sequence_group_id=f"seq_{sequence_sha256}",
            sha256=sequence_sha256,
            sequence=sequence,
            length_aa=len(sequence),
            mass_method="test exact sequence mass",
            residue_policy="canonical test residues",
            source_record_count=1,
        )
    else:
        group = SequenceGroupRecord.model_validate_json(
            sequence_groups_jsonl.read_text(encoding="utf-8").strip()
        )
        sequence = group.sequence
    if source_records_jsonl is None:
        source = SourceProteinRecord(
            schema_version="1.0",
            source_record_id="src_" + "a" * 64,
            catalogue_id="public_catalogue",
            original_protein_id="stub_a",
            original_header="stub_a",
            sequence_group_id=group.sequence_group_id,
            source_annotation_provider="test annotation",
        )
    else:
        source = SourceProteinRecord.model_validate_json(
            source_records_jsonl.read_text(encoding="utf-8").strip()
        )
        if source.sequence_group_id != group.sequence_group_id:
            raise ValueError("localisation fixture source/group identity differs")
    sequence_groups = root / "localisation-sequence-groups.jsonl"
    source_records = root / "localisation-source-records.jsonl"
    catalogue_fasta = root / "localisation-catalogue.faa"
    psortb = root / "localisation-psortb.tsv"
    deeptmhmm = root / "localisation-deeptmhmm.3line"
    if sequence_groups_jsonl is None:
        atomic_write_text(sequence_groups, f"{canonical_json_text(group)}\n")
    else:
        shutil.copyfile(sequence_groups_jsonl, sequence_groups)
    if source_records_jsonl is None:
        atomic_write_text(source_records, f"{canonical_json_text(source)}\n")
    else:
        shutil.copyfile(source_records_jsonl, source_records)
    catalogue_fasta.write_text(
        f">{source.original_header}\n{sequence}\n",
        encoding="ascii",
    )
    atomic_write_text(
        psortb,
        f"SeqID\tLocalization\tScore\n{source.original_header}\t{psortb_label}\t9.50\n",
    )
    atomic_write_text(
        deeptmhmm,
        f">{source.original_protein_id} | {deeptmhmm_type}\n{sequence}\n"
        f"{deeptmhmm_topology_label * len(sequence)}\n",
    )
    execution = materialise_localisation_container_execution_fixture(
        root,
        catalogue_fasta=catalogue_fasta,
        psortb_output=psortb,
        deeptmhmm_output=deeptmhmm,
    )
    return import_catalogue_localisation_batch(
        BatchLocalisationImportRequest(
            sequence_groups_jsonl=sequence_groups,
            source_records_jsonl=source_records,
            catalogue_fasta=catalogue_fasta,
            psortb_terse=psortb,
            deeptmhmm_topologies=deeptmhmm,
            gel_evidence=gel_evidence,
            container_execution_bundle=execution,
            output_directory=root / "localisation",
        )
    ).output_directory


@dataclass(frozen=True, slots=True)
class UnknownPass1PublicFixture:
    """Materialised local inputs and their validated path-free inventory."""

    input_root: Path
    execution_identity: Path
    owned_run_registry: Path
    review_stage: Path
    review_stage_index: Path
    review_decisions: tuple[UnknownPass1ReviewDecisionInput, ...]
    shared_preparation: UnknownPass1SharedPreparationInput
    crystals: tuple[UnknownPass1CrystalInput, ...]
    inventory: UnknownPass1ScreenInventory


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def _model_bytes(crystal_id: str, rank: int) -> bytes:
    model_group = ((rank - 1) // 4) + 1
    return f"synthetic-public-model:{crystal_id}:{model_group}\n".encode("ascii")


def public_stub_model_bytes(crystal_id: str, rank: int) -> bytes:
    """Return the exact deterministic bytes for one synthetic model."""

    return _model_bytes(crystal_id, rank)


def _artifact(
    scope: str,
    owner_id: str,
    role: str,
    path: Path,
) -> ExecutionArtifactIdentity:
    return ExecutionArtifactIdentity.from_content(
        scope=scope,
        owner_id=owner_id,
        role=role,
        sha256=sha256_file(path, progress=False),
        size_bytes=path.stat().st_size,
        release_or_source="synthetic-public-stub",
    )


def _hypothesis(
    crystal_id: str,
    rank: int,
    disposition: UnknownPass1AHypothesisDisposition,
    *,
    allocation_rank: int | None = None,
) -> UnknownPass1AHypothesis:
    model_available = (
        disposition is not UnknownPass1AHypothesisDisposition.UNSEARCHABLE_NO_MODEL
    )
    model_group = ((rank - 1) // 4) + 1
    sequence_key = (
        f"model-group:{model_group}" if model_available else f"no-model:{rank}"
    )
    return UnknownPass1AHypothesis.from_content(
        crystal_id=crystal_id,
        candidate_rank=rank,
        allocation_rank=allocation_rank,
        sequence_group_id=f"seq_{_digest(f'{crystal_id}:sequence:{sequence_key}')}",
        requested_copy_count=((rank - 1) % 4) + 1,
        model_id=f"model_{_digest(f'{crystal_id}:model:{model_group}')}"
        if model_available
        else None,
        model_sha256=hashlib.sha256(_model_bytes(crystal_id, rank)).hexdigest()
        if model_available
        else None,
        disposition=disposition,
        no_model_reason=ModelUnavailableReason.NO_ELIGIBLE_MODEL
        if not model_available
        else None,
    )


def public_stub_hypothesis(
    crystal_id: str,
    rank: int,
    disposition: UnknownPass1AHypothesisDisposition,
    *,
    allocation_rank: int | None = None,
) -> UnknownPass1AHypothesis:
    """Build one deterministic synthetic A hypothesis for focused mutations."""

    return _hypothesis(
        crystal_id,
        rank,
        disposition,
        allocation_rank=allocation_rank,
    )


def materialise_unknown_pass1_public_fixture(
    launch_root: Path,
    *,
    source_commit: str = "1" * 40,
    source_tree: str = "2" * 40,
    nf_helper_commit: str = "3" * 40,
    pixi_lock_sha256: str = "4" * 64,
    mtz_paths_override: dict[str, Path] | None = None,
    database_manifest_override: Path | None = None,
) -> UnknownPass1PublicFixture:
    """Write fixed local inputs and return their validated screen inventory."""

    input_root = launch_root / "inputs"
    input_root.mkdir()
    catalogue_faa = input_root / "catalogue.faa"
    catalogue_faa.write_text(">stub_a\nMPEPTIDE\n", encoding="ascii")
    annotation = input_root / "annotation.gff"
    annotation.write_text("##gff-version 3\n", encoding="ascii")
    gel_evidence = input_root / "gel_evidence.json"
    gel_evidence.write_text(
        '{"schema_version":"2.0","observations":[]}\n',
        encoding="ascii",
    )
    database = input_root / "database.json"
    if database_manifest_override is None:
        database.write_text(
            '{"database":"synthetic-public-stub"}\n',
            encoding="ascii",
        )
    else:
        database = database_manifest_override

    if mtz_paths_override is None:
        mtz_root = input_root / "crystal_mtz"
        mtz_root.mkdir()
        mtz_paths: dict[str, Path] = {}
        for crystal_id in PUBLIC_STUB_CRYSTAL_IDS:
            path = mtz_root / f"{crystal_id}.mtz"
            path.write_text(
                f"synthetic-public-mtz:{crystal_id}\n",
                encoding="ascii",
            )
            mtz_paths[crystal_id] = path
    else:
        mtz_paths = dict(mtz_paths_override)
        if set(mtz_paths) != set(PUBLIC_STUB_CRYSTAL_IDS):
            raise ValueError("public fixture MTZ override must cover all crystals")
        mtz_root = input_root / "crystal_mtz"
        mtz_root.mkdir()
        for crystal_id, source in mtz_paths.items():
            (mtz_root / f"{crystal_id}.mtz").write_bytes(source.read_bytes())

    execution = PhaseIIIExecutionIdentity.from_content(
        source_commit=source_commit,
        source_tree=source_tree,
        nf_helper_commit=nf_helper_commit,
        pixi_lock_sha256=pixi_lock_sha256,
        execution_policy_sha256="5" * 64,
        catalogue_artifacts=tuple(
            sorted(
                (
                    _artifact(
                        "catalogue",
                        "public_catalogue",
                        "annotation_gff",
                        annotation,
                    ),
                    _artifact(
                        "catalogue",
                        "public_catalogue",
                        "gel_evidence",
                        gel_evidence,
                    ),
                    _artifact(
                        "catalogue",
                        "public_catalogue",
                        "proteome_faa",
                        catalogue_faa,
                    ),
                ),
                key=lambda item: (item.owner_id, item.role, item.artifact_id),
            )
        ),
        crystal_artifacts=tuple(
            sorted(
                (
                    _artifact("crystal", crystal_id, "mtz", mtz_paths[crystal_id])
                    for crystal_id in PUBLIC_STUB_CRYSTAL_IDS
                ),
                key=lambda item: (item.owner_id, item.role, item.artifact_id),
            )
        ),
        database_artifacts=(
            _artifact("database", "public_database", "database_manifest", database),
        ),
        tools=tuple(
            sorted(
                (
                    *(
                        ExecutionToolIdentity.from_content(
                            name=name,
                            version="synthetic-stub-not-executed",
                            executable_sha256=_digest(f"tool:{name}"),
                            adapter_version="unknown-pass1-stub-v1",
                        )
                        for name in _PHENIX
                    ),
                    ExecutionToolIdentity.from_content(
                        name="DeepTMHMM",
                        version="1.0",
                        executable_sha256=DEEPTMHMM_IMAGE_MANIFEST_SHA256,
                        adapter_version=LOCALISATION_BATCH_ADAPTER_VERSION,
                    ),
                    ExecutionToolIdentity.from_content(
                        name="PSORTb",
                        version="3.0.6",
                        executable_sha256=PSORTB_IMAGE_MANIFEST_SHA256,
                        adapter_version=LOCALISATION_BATCH_ADAPTER_VERSION,
                    ),
                ),
                key=lambda item: (item.name, item.tool_identity_id),
            )
        ),
        adapter_versions=tuple(
            sorted(
                (
                    (
                        "phase3_all_model_registry",
                        "all-eligible-model-registry-v3",
                    ),
                    (
                        "phase3_component_coordinates",
                        "phaser-component-coordinate-inventory-v2",
                    ),
                    (
                        "phase3_composition_attempt",
                        "phase3-composition-attempt-execution-v1",
                    ),
                    (
                        "phase3_composition_beam",
                        "phase3-composition-beam-depth-v1",
                    ),
                    (
                        "phase3_composition_depth",
                        "phase3-composition-depth-input-v1",
                    ),
                    (
                        "phase3_first_copy_funnel",
                        "multi-source-first-copy-funnel-v4-phase3-evidence",
                    ),
                    (
                        "phase3_localisation_batch",
                        LOCALISATION_BATCH_ADAPTER_VERSION,
                    ),
                    (
                        "phase3_multi_fixed_search",
                        "phenix-multi-fixed-joint-component-v2-diffraction",
                    ),
                    (
                        "phase3_no_a_expansion",
                        "phase3-no-a-expansion-v2",
                    ),
                    (
                        "phase3_pass2_a_seed",
                        "phase3-pass2-a-seed-v1",
                    ),
                    (
                        "phase3_partner_search",
                        "phenix-fixed-a-joint-b-v8-phase3-diffraction",
                    ),
                    ("unknown_pass1_inventory", "unknown-pass1-screen-v1"),
                    ("unknown_pass1_stub", "unknown-pass1-nextflow-stub-v1"),
                )
            )
        ),
    )
    execution_path = input_root / "phase3_execution_identity.json"
    atomic_write_json(execution_path, execution.model_dump(mode="json"))

    created_at = datetime(2026, 8, 23, 18, 0, tzinfo=UTC)
    parent = OwnedPhaseIIIParentRun(
        run_id="public-unknown-pass1-stub-parent",
        profile="unknown-screen-local-stub",
        phase="unknown-pass1-crystallographic-review",
    )
    decision_values = (
        PhaseIIIReviewDecisionValue.PROCEED,
        PhaseIIIReviewDecisionValue.HOLD,
        PhaseIIIReviewDecisionValue.PROCEED,
    )
    package_root = input_root / "review_packages"
    package_root.mkdir()
    decisions_root = input_root / "review_decisions"
    decisions_root.mkdir()
    review_stage = input_root / "review_stage"
    package_sources: list[OwnedPhaseIIIReviewPackageSource] = []
    decision_inputs: list[UnknownPass1ReviewDecisionInput] = []
    for index, (crystal_id, decision_value) in enumerate(
        zip(PUBLIC_STUB_CRYSTAL_IDS, decision_values, strict=True),
        start=1,
    ):
        package_directory = package_root / crystal_id
        package_directory.mkdir()
        package = build_phase3_review_package(
            PhaseIIIReviewPackageRequest(
                checkpoint=PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
                owned_parent_run_id=parent.run_id,
                parent_profile=parent.profile,
                parent_phase=parent.phase,
                execution_identity_id=execution.execution_identity_id,
                crystal_id=crystal_id,
                target_item_ids=("crystallographic-dataset",),
                created_at=created_at,
                input_root=input_root,
                evidence_sources=(
                    PhaseIIIReviewEvidenceSource(
                        role="diffraction_data",
                        relative_path=f"crystal_mtz/{crystal_id}.mtz",
                    ),
                ),
                output_directory=package_directory,
            )
        )
        decisions = PhaseIIIReviewDecisionFile.from_content(
            checkpoint=PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
            owned_parent_run_id=parent.run_id,
            review_package_id=package.review_package_id,
            review_package_manifest_sha256=sha256_file(
                package.manifest,
                progress=False,
            ),
            decisions=(
                PhaseIIIReviewDecision(
                    crystal_id=crystal_id,
                    item_id="crystallographic-dataset",
                    decision=decision_value,
                    reviewer="synthetic-public-stub-reviewer",
                    reviewed_at=created_at + timedelta(minutes=index),
                    reason="exercise a typed public-fixture review branch",
                ),
            ),
        )
        decisions_path = decisions_root / f"{crystal_id}.json"
        atomic_write_json(decisions_path, decisions.model_dump(mode="json"))
        package_sources.append(
            OwnedPhaseIIIReviewPackageSource(
                crystal_id=crystal_id,
                checkpoint=PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
                package_directory=package_directory,
            )
        )
        decision_inputs.append(
            UnknownPass1ReviewDecisionInput(
                crystal_id=crystal_id,
                decisions=decisions_path,
                confirmed_decisions_sha256=sha256_file(
                    decisions_path,
                    progress=False,
                ),
            )
        )

    owned_run_registry = input_root / "owned_run_registry"
    owned_run_registry.mkdir()
    register_phase3_owned_run(
        parent=parent,
        completed_at=created_at - timedelta(hours=1),
        execution_identity=execution_path,
        packages=tuple(package_sources),
        output_directory=owned_run_registry,
    )
    review_stage_output = stage_unknown_pass1_crystallographic_reviews(
        owned_run_registry=owned_run_registry,
        owned_run_id=parent.run_id,
        decisions=tuple(reversed(decision_inputs)),
        output_directory=review_stage,
    )

    catalogue_preparation = input_root / "catalogue_preparation.json"
    catalogue_preparation.write_text(
        '{"preparation_id":"public-catalogue-prepared-once"}\n',
        encoding="ascii",
    )
    provider_preparation = input_root / "provider_preparation.json"
    provider_preparation.write_text(
        '{"preparation_id":"public-provider-prepared-once",'
        '"remote_sequence_submission":false}\n',
        encoding="ascii",
    )
    localisation_preparation = input_root / "localisation_preparation.json"
    localisation_preparation.write_text(
        '{"execution_mode":"local_offline",'
        '"preparation_id":"public-localisation-prepared-once"}\n',
        encoding="ascii",
    )
    shared = UnknownPass1SharedPreparationInput(
        catalogue_preparation_id="public-catalogue-prepared-once",
        catalogue_preparation=catalogue_preparation,
        provider_preparation_id="public-provider-prepared-once",
        provider_preparation=provider_preparation,
        localisation_preparation_id="public-localisation-prepared-once",
        localisation_preparation=localisation_preparation,
    )

    first_hypotheses = (
        *(
            _hypothesis(
                PUBLIC_STUB_CRYSTAL_IDS[0],
                rank,
                UnknownPass1AHypothesisDisposition.SELECTED,
                allocation_rank=rank,
            )
            for rank in range(1, 26)
        ),
        _hypothesis(
            PUBLIC_STUB_CRYSTAL_IDS[0],
            26,
            UnknownPass1AHypothesisDisposition.DEFERRED_CAP,
        ),
        _hypothesis(
            PUBLIC_STUB_CRYSTAL_IDS[0],
            27,
            UnknownPass1AHypothesisDisposition.UNSEARCHABLE_NO_MODEL,
        ),
    )
    third_hypotheses = tuple(
        _hypothesis(
            PUBLIC_STUB_CRYSTAL_IDS[2],
            rank,
            UnknownPass1AHypothesisDisposition.UNSEARCHABLE_NO_MODEL,
        )
        for rank in range(1, 3)
    )
    model_root = input_root / "models"
    model_root.mkdir()
    model_inputs: list[UnknownPass1ModelInput] = []
    materialised_model_ids: set[str] = set()
    for hypothesis in first_hypotheses:
        if hypothesis.model_id is None or hypothesis.model_id in materialised_model_ids:
            continue
        model = model_root / f"{hypothesis.model_id}.pdb"
        model.write_bytes(
            _model_bytes(hypothesis.crystal_id, hypothesis.candidate_rank)
        )
        model_inputs.append(UnknownPass1ModelInput(hypothesis.model_id, model))
        materialised_model_ids.add(hypothesis.model_id)
    crystals = (
        UnknownPass1CrystalInput(
            PUBLIC_STUB_CRYSTAL_IDS[0],
            mtz_paths[PUBLIC_STUB_CRYSTAL_IDS[0]],
            first_hypotheses,
            tuple(model_inputs),
        ),
        UnknownPass1CrystalInput(
            PUBLIC_STUB_CRYSTAL_IDS[1],
            mtz_paths[PUBLIC_STUB_CRYSTAL_IDS[1]],
            (),
        ),
        UnknownPass1CrystalInput(
            PUBLIC_STUB_CRYSTAL_IDS[2],
            mtz_paths[PUBLIC_STUB_CRYSTAL_IDS[2]],
            third_hypotheses,
        ),
    )
    inventory = build_unknown_pass1_screen_inventory(
        execution_identity_path=execution_path,
        review_stage_index_path=review_stage_output.index_path,
        shared_preparation_input=shared,
        crystals=crystals,
    )
    write_unknown_pass1_screen_inventory(
        inventory,
        input_root / "unknown_pass1_screen_inventory.json",
    )
    crystal_item_root = input_root / "crystal_items"
    crystal_item_root.mkdir()
    for item in inventory.crystals:
        atomic_write_json(
            crystal_item_root / f"{item.crystal_id}--{item.branch.value}.json",
            item.model_dump(mode="json", exclude_none=False),
        )
    hypothesis_task_root = input_root / "hypothesis_tasks"
    hypothesis_task_root.mkdir()
    for task in inventory.hypothesis_tasks:
        atomic_write_json(
            hypothesis_task_root
            / f"{task.model_id}--{task.crystal_id}--{task.allocation_rank}.json",
            task.model_dump(mode="json", exclude_none=False),
        )
    return UnknownPass1PublicFixture(
        input_root=input_root,
        execution_identity=execution_path,
        owned_run_registry=owned_run_registry,
        review_stage=review_stage,
        review_stage_index=review_stage_output.index_path,
        review_decisions=tuple(decision_inputs),
        shared_preparation=shared,
        crystals=crystals,
        inventory=inventory,
    )


def materialise_phase3_provider_login_stub(
    discovery_package: Path,
    output_directory: Path,
) -> Path:
    """Write a typed no-coordinate login-stage fixture for offline stub MR."""

    discovery = validate_phase3_provider_discovery_package(discovery_package)
    output_directory.mkdir()
    groups = tuple(
        SequenceGroupRecord.model_validate_json(line)
        for line in (discovery_package / "catalogue/sequence_groups.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    pdb = output_directory / "pdb_coordinate_registration"
    pdb.mkdir()
    atomic_write_text(pdb / "coordinate_sources.jsonl", "")
    atomic_write_text(pdb / "owned_coordinate_sources.jsonl", "")
    atomic_write_text(pdb / "coordinate_hit_mappings.jsonl", "")
    atomic_write_json(
        pdb / "registration_manifest.json",
        {
            "schema_version": "1.0",
            "registration_id": "coordreg_phase3_login_stub",
            "selected_mapping_count": 0,
            "coordinate_source_count": 0,
        },
    )
    afdb = output_directory / "afdb_exact_search"
    raw = afdb / "raw"
    raw.mkdir(parents=True)
    raw_result = raw / "afdb-results.json"
    raw_log = raw / "afdb.log"
    raw_result.write_text("{}\n", encoding="ascii")
    raw_log.write_text("stub mode: no coordinate acquisition\n", encoding="ascii")
    afdb_results = tuple(
        StructuralSearchResult(
            schema_version="1.0",
            search_id=f"afdb_stub_{group.sequence_group_id}",
            sequence_group_id=group.sequence_group_id,
            provider="afdb_exact",
            database_id="afdb_stub",
            tool="AlphaFold DB prediction API",
            tool_version="stub-not-executed",
            adapter_version="afdb-exact-v3",
            cache_key=_digest(f"afdb-stub:{group.sequence_group_id}"),
            execution_status=ExecutionStatus.COMPLETED_NO_HIT,
            scientific_status=SearchScientificStatus.NO_HIT,
            hit_count=0,
            hits=(),
            raw_result_pointer="raw/afdb-results.json",
            raw_result_sha256=sha256_file(raw_result, progress=False),
            command_log_pointer="raw/afdb.log",
            command_log_sha256=sha256_file(raw_log, progress=False),
            warnings=("stub_mode_no_network_execution",),
        )
        for group in groups
    )
    atomic_write_text(
        afdb / "search_results.jsonl",
        "".join(f"{canonical_json_text(item)}\n" for item in afdb_results),
    )
    atomic_write_text(afdb / "structural_hits.jsonl", "")
    atomic_write_text(afdb / "coordinate_sources.jsonl", "")
    atomic_write_text(afdb / "owned_coordinate_sources.jsonl", "")
    atomic_write_json(
        afdb / "search_manifest.json",
        {
            "schema_version": "1.0",
            "search_count": len(afdb_results),
            "coordinate_source_count": 0,
            "scientific_execution_performed": False,
        },
    )
    esm = emit_disabled_provider_bundle(
        DisabledProviderBundleRequest(
            provider_entry_json=(
                discovery_package / "provider_plan/entries/esm_atlas.json"
            ),
            sequence_groups_jsonl=(
                discovery_package / "catalogue/sequence_groups.jsonl"
            ),
            output_directory=output_directory / "esm_atlas_search",
        )
    )
    shutil.copy2(
        discovery_package / "phase3_provider_discovery_manifest.json",
        output_directory / "phase3_provider_discovery_manifest.json",
    )
    files = tuple(
        PhaseIIIProviderLoginStageFile(
            relative_path=path.relative_to(output_directory).as_posix(),
            sha256=sha256_file(path, progress=False),
            size_bytes=path.stat().st_size,
        )
        for path in sorted(output_directory.rglob("*"))
        if path.is_file() and path.name != "provider_preparation.json"
    )
    manifest = PhaseIIIProviderLoginStageManifest.from_content(
        adapter_version="phase3-provider-login-stage-v3",
        discovery_package_id=discovery.package_id,
        discovery_owned_run_id=discovery.owned_run_id,
        execution_identity_id=discovery.execution_identity_id,
        provider_plan_id=discovery.provider_plan_id,
        sequence_group_count=discovery.sequence_group_count,
        pdb_coordinate_source_count=0,
        pdb_mapping_count=0,
        afdb_result_count=len(afdb_results),
        afdb_coordinate_source_count=0,
        esm_result_count=len(esm.results),
        staged_coordinate_object_count=0,
        maximum_hits_per_sequence_group=3,
        maximum_mappings=25,
        execution_class="bounded_login_staging",
        remote_sequence_submission=False,
        files=files,
    )
    atomic_write_json(
        output_directory / "provider_preparation.json",
        manifest.model_dump(mode="json"),
    )
    validate_phase3_provider_login_stage(output_directory)
    return output_directory


__all__ = [
    "PUBLIC_STUB_CRYSTAL_IDS",
    "UnknownPass1PublicFixture",
    "materialise_phase3_provider_login_stub",
    "materialise_unknown_pass1_public_fixture",
    "public_stub_hypothesis",
    "public_stub_model_bytes",
]
