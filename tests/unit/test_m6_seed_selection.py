"""Focused regression for truthless M6 seed advancement."""

from itertools import permutations
from pathlib import Path

from genome_to_diffraction.benchmarks.m6_nextflow import (
    _m6_seed_advancement_rows,
    _select_m6_seed_candidates,
)
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.mr.phaser import PhaserRunOutput
from genome_to_diffraction.schemas.manifests import PrototypeProfile
from genome_to_diffraction.schemas.results import (
    MrHypothesis,
    MrHypothesisStatus,
    MrSearchStage,
    NormalisedMrResult,
)
from genome_to_diffraction.status import ExecutionStatus


def _candidate(
    hypothesis_id: str,
    sequence_group_id: str,
    model_id: str,
    copy_count: int,
    llg: float,
    tfz: float,
) -> tuple[PhaserRunOutput, MrHypothesis]:
    hypothesis = MrHypothesis(
        schema_version="1.0",
        hypothesis_id=hypothesis_id,
        crystal_id="M6C001",
        sequence_group_id=sequence_group_id,
        model_id=model_id,
        copy_count_expected=copy_count,
        copy_number_to_search=copy_count,
        space_group="P 1",
        obs_labels="F,SIGF",
        search_stage=MrSearchStage.FIRST_COPY,
        resource_profile=PrototypeProfile.PILOT,
        status=MrHypothesisStatus.COMPLETED_HIT,
    )
    result = NormalisedMrResult(
        schema_version="1.0",
        hypothesis_id=hypothesis_id,
        tool_version="test",
        execution_status=ExecutionStatus.COMPLETED_HIT,
        llg=llg,
        tfz=tfz,
        placed_copy_count=copy_count,
        packing_summary={"top_solution_packed": True},
        raw_log_pointer=f"{hypothesis_id}.log",
    )
    attempt = PhaserRunOutput(
        result=result,
        result_json=Path(f"{hypothesis_id}.json"),
        result_jsonl=Path(f"{hypothesis_id}.jsonl"),
        command_json=Path(f"{hypothesis_id}.command.json"),
    )
    return attempt, hypothesis


def test_seed_advancement_uses_evidence_not_largest_copy_count() -> None:
    smaller_stronger = _candidate(
        "hyp_same_model_two",
        "seq_same_model",
        "model_same",
        2,
        120.0,
        12.0,
    )
    larger_weaker = _candidate(
        "hyp_same_model_four",
        "seq_same_model",
        "model_same",
        4,
        10.0,
        3.0,
    )
    candidates = (
        smaller_stronger,
        _candidate("hyp_other_1", "seq_1", "model_1", 1, 110.0, 11.0),
        _candidate("hyp_other_2", "seq_2", "model_2", 3, 100.0, 10.0),
        _candidate("hyp_other_3", "seq_3", "model_3", 4, 90.0, 9.0),
        _candidate("hyp_other_4", "seq_4", "model_4", 1, 80.0, 8.0),
        larger_weaker,
    )
    candidate_rank = {
        "seq_same_model": 1,
        "seq_1": 2,
        "seq_2": 3,
        "seq_3": 4,
        "seq_4": 5,
    }
    observed_outputs: set[str] = set()

    for permuted in permutations(candidates):
        eligible, selected = _select_m6_seed_candidates(permuted, candidate_rank)
        selected_ids = {hypothesis.hypothesis_id for _, hypothesis in selected}
        rows = _m6_seed_advancement_rows(
            "M6C001",
            eligible,
            selected_ids,
            candidate_rank,
        )
        observed_outputs.add("".join(canonical_json_text(row) for row in rows))

    assert len(observed_outputs) == 1
    eligible, selected = _select_m6_seed_candidates(candidates, candidate_rank)
    eligible_ids = [hypothesis.hypothesis_id for _, hypothesis in eligible]
    selected_ids = {hypothesis.hypothesis_id for _, hypothesis in selected}
    rows = _m6_seed_advancement_rows(
        "M6C001",
        eligible,
        selected_ids,
        candidate_rank,
    )

    assert eligible_ids == [
        "hyp_same_model_two",
        "hyp_other_1",
        "hyp_other_2",
        "hyp_other_3",
        "hyp_other_4",
        "hyp_same_model_four",
    ]
    assert len(rows) == len(candidates)
    assert rows[0]["expected_copy_count"] == 2
    assert rows[0]["advancement_disposition"] == "selected"
    assert rows[-1]["expected_copy_count"] == 4
    assert rows[-1]["advancement_disposition"] == "deferred_seed_cap"
    assert all(row["eligible_hypothesis_retained"] is True for row in rows)
