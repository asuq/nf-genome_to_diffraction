"""Catalogue-wide localisation coverage, wave decisions, and reopen tests."""

import hashlib
from collections.abc import Sequence
from pathlib import Path

import pytest

from genome_to_diffraction.checksums import atomic_write_json
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.localisation import (
    ActiveWaveCompletion,
    ActiveWaveGroupResult,
    ActiveWaveResultStatus,
    CatalogueLocalisationWavePolicy,
    DeepTMHMMBlockedResult,
    DeepTMHMMRuntimeContract,
    FirstWaveDisposition,
    LocalisationOutcome,
    LocalisationReopenPlan,
    LocalisationReopenStatus,
    LocalisationTaskInventory,
    PSortbRuntimeContract,
    build_catalogue_localisation_tasks,
    build_catalogue_localisation_wave_policy,
    first_wave_disposition,
    plan_localisation_reopen,
    run_catalogue_localisation_task,
)
from genome_to_diffraction.schemas.results import SequenceGroupRecord
from genome_to_diffraction.status import ExecutionStatus, InputContractError


def _group(residue: str, outcome: LocalisationOutcome) -> SequenceGroupRecord:
    sequence = residue * 20
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
        quality_flags=(f"stub_localisation:{outcome.value}",),
    )


def _write_groups(path: Path, groups: Sequence[SequenceGroupRecord]) -> None:
    path.write_text(
        "".join(f"{canonical_json_text(group)}\n" for group in groups),
        encoding="utf-8",
    )


def _write_psortb(
    path: Path,
    groups: Sequence[SequenceGroupRecord],
) -> None:
    raw_labels = {
        LocalisationOutcome.MEMBRANE: "CytoplasmicMembrane",
        LocalisationOutcome.SURFACE: "Cellwall",
        LocalisationOutcome.EXTRACELLULAR: "Extracellular",
        LocalisationOutcome.SOLUBLE: "Cytoplasmic",
        LocalisationOutcome.UNKNOWN: "Unknown",
    }
    cases: list[str] = []
    for group in groups:
        outcome = LocalisationOutcome(
            group.quality_flags[0].removeprefix("stub_localisation:")
        )
        if outcome is LocalisationOutcome.FAILED:
            action = "printf 'synthetic failure\\n' >&2; exit 7"
        else:
            action = (
                f"printf '%s\\t{raw_labels[outcome]}\\t9.00\\n' \"$group_id\"; exit 0"
            )
        cases.append(f"  {group.sequence_group_id}) {action} ;;")
    path.write_text(
        "#!/usr/bin/env bash\n"
        "set -u\n"
        'if [[ "${1-}" == "--version" ]]; then\n'
        "  printf 'PSORTb version 3.0.6\\n'\n"
        "  exit 0\n"
        "fi\n"
        'input_fasta="${4}"\n'
        'IFS= read -r header < "$input_fasta"\n'
        'group_id="${header#>}"\n'
        'case "$group_id" in\n'
        + "\n".join(cases)
        + "\n  *) printf 'unknown group\\n' >&2; exit 9 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


@pytest.fixture(scope="module")
def mixed_policy(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[
    CatalogueLocalisationWavePolicy,
    LocalisationTaskInventory,
    Path,
    tuple[Path, ...],
]:
    root = tmp_path_factory.mktemp("localisation-wave-policy")
    groups = (
        _group("A", LocalisationOutcome.SOLUBLE),
        _group("C", LocalisationOutcome.MEMBRANE),
        _group("D", LocalisationOutcome.UNKNOWN),
        _group("E", LocalisationOutcome.FAILED),
        _group("F", LocalisationOutcome.EXTRACELLULAR),
    )
    sequence_groups = root / "sequence_groups.jsonl"
    _write_groups(sequence_groups, tuple(reversed(groups)))
    executable = root / "psort"
    _write_psortb(executable, groups)
    psortb_runtime = PSortbRuntimeContract.from_executable(executable)
    psortb_runtime_json = root / "psortb_runtime.json"
    atomic_write_json(
        psortb_runtime_json,
        psortb_runtime.model_dump(mode="json"),
    )
    image = root / "deeptmhmm-1.0.sif"
    image.write_bytes(b"synthetic user image")
    deeptmhmm_runtime = DeepTMHMMRuntimeContract.from_user_image(image)
    deeptmhmm_runtime_json = root / "deeptmhmm_runtime.json"
    atomic_write_json(
        deeptmhmm_runtime_json,
        deeptmhmm_runtime.model_dump(mode="json"),
    )
    tasks_output = build_catalogue_localisation_tasks(
        sequence_groups,
        psortb_runtime_json,
        deeptmhmm_runtime_json,
        root / "tasks",
    )
    result_directories: list[Path] = []
    for task in tasks_output.inventory.tasks:
        result = run_catalogue_localisation_task(
            root / "tasks/tasks" / task.task_id,
            psortb_runtime_json,
            deeptmhmm_runtime_json,
            root / f"result_{task.task_id}",
        )
        result_directories.append(result.output_directory)
    policy_output = build_catalogue_localisation_wave_policy(
        root / "tasks",
        tuple(reversed(result_directories)),
        root / "policy",
    )
    return (
        policy_output.policy,
        tasks_output.inventory,
        policy_output.policy_json,
        tuple(result_directories),
    )


def test_task_builder_is_one_per_group_and_order_invariant(tmp_path: Path) -> None:
    groups = (
        _group("A", LocalisationOutcome.SOLUBLE),
        _group("C", LocalisationOutcome.MEMBRANE),
    )
    executable = tmp_path / "psort"
    _write_psortb(executable, groups)
    psortb = PSortbRuntimeContract.from_executable(executable)
    psortb_json = tmp_path / "psortb.json"
    atomic_write_json(psortb_json, psortb.model_dump(mode="json"))
    image = tmp_path / "deeptmhmm.sif"
    image.write_bytes(b"image")
    deeptmhmm = DeepTMHMMRuntimeContract.from_user_image(image)
    deeptmhmm_json = tmp_path / "deeptmhmm.json"
    atomic_write_json(deeptmhmm_json, deeptmhmm.model_dump(mode="json"))
    forward = tmp_path / "forward.jsonl"
    reverse = tmp_path / "reverse.jsonl"
    _write_groups(forward, groups)
    _write_groups(reverse, tuple(reversed(groups)))

    first = build_catalogue_localisation_tasks(
        forward,
        psortb_json,
        deeptmhmm_json,
        tmp_path / "first",
    ).inventory
    second = build_catalogue_localisation_tasks(
        reverse,
        psortb_json,
        deeptmhmm_json,
        tmp_path / "second",
    ).inventory

    assert first.task_count == len(groups)
    assert first.tasks == second.tasks
    assert first.inventory_id == second.inventory_id
    assert len({task.sequence_group_id for task in first.tasks}) == len(groups)
    assert first.source_sequence_groups_sha256 != second.source_sequence_groups_sha256

    duplicated = tmp_path / "duplicated.jsonl"
    _write_groups(duplicated, (groups[0], groups[0]))
    with pytest.raises(InputContractError, match="duplicate sequence group"):
        build_catalogue_localisation_tasks(
            duplicated,
            psortb_json,
            deeptmhmm_json,
            tmp_path / "duplicate-output",
        )


@pytest.mark.parametrize(
    ("outcome", "expected"),
    (
        (LocalisationOutcome.SOLUBLE, FirstWaveDisposition.ACTIVE),
        (LocalisationOutcome.MEMBRANE, FirstWaveDisposition.EXCLUDED),
        (LocalisationOutcome.SURFACE, FirstWaveDisposition.EXCLUDED),
        (LocalisationOutcome.EXTRACELLULAR, FirstWaveDisposition.EXCLUDED),
        (LocalisationOutcome.TRANSMEMBRANE, FirstWaveDisposition.EXCLUDED),
        (LocalisationOutcome.UNKNOWN, FirstWaveDisposition.NEUTRAL),
        (LocalisationOutcome.CONFLICTING, FirstWaveDisposition.NEUTRAL),
        (LocalisationOutcome.FAILED, FirstWaveDisposition.NEUTRAL),
    ),
)
def test_first_wave_policy_never_excludes_uncertainty_or_failure(
    outcome: LocalisationOutcome,
    expected: FirstWaveDisposition,
) -> None:
    assert first_wave_disposition(outcome) is expected


def test_catalogue_merge_retains_every_group_and_failed_result(
    mixed_policy: tuple[
        CatalogueLocalisationWavePolicy,
        LocalisationTaskInventory,
        Path,
        tuple[Path, ...],
    ],
    tmp_path: Path,
) -> None:
    policy, inventory, _, result_directories = mixed_policy

    assert policy.sequence_group_count == 5
    assert policy.result_count == 5
    assert policy.psortb_completed_count == 4
    assert policy.psortb_failed_count == 1
    assert policy.deeptmhmm_blocked_count == 5
    assert policy.active_count == 1
    assert policy.excluded_count == 2
    assert policy.neutral_count == 2
    assert policy.first_wave_eligible_count == 3
    assert len(policy.retained_excluded_group_ids) == 2
    assert len(policy.first_wave_group_ids) == 3
    failed = next(
        item
        for item in policy.group_evidence
        if item.psortb_execution_status is ExecutionStatus.FAILED_TOOL_EXECUTION
    )
    assert failed.psortb_outcome is LocalisationOutcome.FAILED
    assert failed.merged_outcome is LocalisationOutcome.FAILED
    assert failed.first_wave_disposition is FirstWaveDisposition.NEUTRAL
    assert failed.first_wave_eligible is True

    blocked_path = result_directories[0] / "deeptmhmm-blocked-result.json"
    blocked = DeepTMHMMBlockedResult.model_validate_json(
        blocked_path.read_text(encoding="utf-8")
    )
    assert blocked.execution_status == "skipped_policy"
    assert blocked.invocation_status == "blocked_unverified_cli"
    assert blocked.command == ()
    assert blocked.outcome is None

    reordered = build_catalogue_localisation_wave_policy(
        mixed_policy[3][0].parent / "tasks",
        result_directories,
        tmp_path / "reordered-policy",
    )
    assert reordered.policy.policy_id == policy.policy_id
    assert reordered.policy.group_evidence == policy.group_evidence

    with pytest.raises(InputContractError, match="missing localisation result"):
        build_catalogue_localisation_wave_policy(
            mixed_policy[3][0].parent / "tasks",
            result_directories[:-1],
            tmp_path / "missing-policy",
        )
    with pytest.raises(InputContractError, match="duplicate localisation result"):
        build_catalogue_localisation_wave_policy(
            mixed_policy[3][0].parent / "tasks",
            (*result_directories, result_directories[0]),
            tmp_path / "duplicate-policy",
        )

    assert inventory.task_count == policy.sequence_group_count


def _source_digest(group_id: str) -> str:
    return hashlib.sha256(group_id.encode("ascii")).hexdigest()


def _completion(
    group_ids: tuple[str, ...],
    status: ActiveWaveResultStatus,
) -> ActiveWaveCompletion:
    return ActiveWaveCompletion.from_results(
        group_ids,
        tuple(
            ActiveWaveGroupResult(
                sequence_group_id=group_id,
                status=status,
                source_result_sha256=_source_digest(group_id),
            )
            for group_id in group_ids
        ),
    )


def test_reopen_requires_complete_zero_pack_and_retains_exclusions(
    mixed_policy: tuple[
        CatalogueLocalisationWavePolicy,
        LocalisationTaskInventory,
        Path,
        tuple[Path, ...],
    ],
    tmp_path: Path,
) -> None:
    policy, inventory, policy_json, _ = mixed_policy
    complete_no_pack = _completion(
        policy.first_wave_group_ids,
        ActiveWaveResultStatus.COMPLETED_NO_PACKED_RESULT,
    )
    activated = LocalisationReopenPlan.from_policy(policy, complete_no_pack)
    assert activated.status is LocalisationReopenStatus.ACTIVATED_NO_PACKED_RESULT
    assert activated.reopened_group_ids == policy.retained_excluded_group_ids
    assert activated.all_excluded_groups_retained is True

    completion_json = tmp_path / "active-wave-completion.json"
    atomic_write_json(completion_json, complete_no_pack.model_dump(mode="json"))
    written = plan_localisation_reopen(
        policy_json,
        completion_json,
        tmp_path / "reopen",
    )
    assert written.plan == activated
    assert (
        len(written.retained_excluded_jsonl.read_text(encoding="utf-8").splitlines())
        == policy.excluded_count
    )

    packed_results = list(complete_no_pack.results)
    packed_results[0] = packed_results[0].model_copy(
        update={"status": ActiveWaveResultStatus.PACKED}
    )
    packed = ActiveWaveCompletion.from_results(
        policy.first_wave_group_ids,
        packed_results,
    )
    packed_plan = LocalisationReopenPlan.from_policy(policy, packed)
    assert packed_plan.status is LocalisationReopenStatus.NOT_ACTIVATED_PACKED_RESULT
    assert packed_plan.reopened_group_ids == ()

    failed_results = list(complete_no_pack.results)
    failed_results[0] = failed_results[0].model_copy(
        update={"status": ActiveWaveResultStatus.FAILED}
    )
    failed = ActiveWaveCompletion.from_results(
        policy.first_wave_group_ids,
        failed_results,
    )
    assert failed.active_wave_complete is False
    assert (
        LocalisationReopenPlan.from_policy(policy, failed).status
        is LocalisationReopenStatus.PENDING_ACTIVE_WAVE
    )
    missing = ActiveWaveCompletion.from_results(
        policy.first_wave_group_ids,
        complete_no_pack.results[:-1],
    )
    assert missing.active_wave_complete is False
    assert (
        LocalisationReopenPlan.from_policy(policy, missing).status
        is LocalisationReopenStatus.PENDING_ACTIVE_WAVE
    )

    task_by_group = {task.sequence_group_id: task for task in inventory.tasks}
    evidence_by_group = {item.sequence_group_id: item for item in policy.group_evidence}
    excluded_tasks = tuple(
        task_by_group[group_id] for group_id in policy.retained_excluded_group_ids
    )
    excluded_inventory = LocalisationTaskInventory.from_tasks(
        excluded_tasks,
        source_sequence_groups_sha256=inventory.source_sequence_groups_sha256,
        psortb_runtime_contract_sha256=(inventory.psortb_runtime_contract_sha256),
        deeptmhmm_runtime_contract_sha256=(inventory.deeptmhmm_runtime_contract_sha256),
        psortb_runtime_identity_sha256=(inventory.psortb_runtime_identity_sha256),
        deeptmhmm_runtime_identity_sha256=(inventory.deeptmhmm_runtime_identity_sha256),
    )
    excluded_policy = CatalogueLocalisationWavePolicy.from_evidence(
        excluded_inventory,
        tuple(
            evidence_by_group[group_id]
            for group_id in policy.retained_excluded_group_ids
        ),
    )
    empty_completion = ActiveWaveCompletion.from_results((), ())
    empty_active_plan = LocalisationReopenPlan.from_policy(
        excluded_policy,
        empty_completion,
    )
    assert empty_active_plan.status is (
        LocalisationReopenStatus.ACTIVATED_NO_PACKED_RESULT
    )
    assert empty_active_plan.reopened_count == excluded_policy.excluded_count

    active_group_id = policy.first_wave_group_ids[0]
    active_inventory = LocalisationTaskInventory.from_tasks(
        (task_by_group[active_group_id],),
        source_sequence_groups_sha256=inventory.source_sequence_groups_sha256,
        psortb_runtime_contract_sha256=(inventory.psortb_runtime_contract_sha256),
        deeptmhmm_runtime_contract_sha256=(inventory.deeptmhmm_runtime_contract_sha256),
        psortb_runtime_identity_sha256=(inventory.psortb_runtime_identity_sha256),
        deeptmhmm_runtime_identity_sha256=(inventory.deeptmhmm_runtime_identity_sha256),
    )
    active_policy = CatalogueLocalisationWavePolicy.from_evidence(
        active_inventory,
        (evidence_by_group[active_group_id],),
    )
    not_required = LocalisationReopenPlan.from_policy(
        active_policy,
        ActiveWaveCompletion.from_results(active_policy.first_wave_group_ids, ()),
    )
    assert not_required.status is (
        LocalisationReopenStatus.NOT_REQUIRED_NO_EXCLUDED_GROUPS
    )

    wrong_completion = ActiveWaveCompletion.from_results(
        ("seq_" + "a" * 64,),
        (),
    )
    wrong_json = tmp_path / "wrong-completion.json"
    atomic_write_json(wrong_json, wrong_completion.model_dump(mode="json"))
    with pytest.raises(InputContractError, match="does not match"):
        plan_localisation_reopen(
            policy_json,
            wrong_json,
            tmp_path / "wrong-reopen",
        )
