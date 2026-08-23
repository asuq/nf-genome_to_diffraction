"""Focused contracts for Phase III file-based human review decisions."""

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from genome_to_diffraction.schemas.io import ContractLoadError, load_contract
from genome_to_diffraction.schemas.results import ReviewDecision, ReviewDecisionManifest
from genome_to_diffraction.schemas.v2 import (
    PhaseIIIReviewCheckpoint,
    PhaseIIIReviewDecision,
    PhaseIIIReviewDecisionFile,
    PhaseIIIReviewDecisionValue,
)

HASHES = tuple(f"{index:x}" * 64 for index in range(1, 8))


def _decision(
    item_id: str,
    value: PhaseIIIReviewDecisionValue,
    *,
    crystal_id: str = "unknown_1",
) -> PhaseIIIReviewDecision:
    return PhaseIIIReviewDecision(
        crystal_id=crystal_id,
        item_id=item_id,
        decision=value,
        reviewer="reviewer_1",
        reviewed_at=datetime(2026, 8, 23, 16, 0, tzinfo=UTC),
        reason="reviewed against the checksum-bound package",
        comment="independent map and crystallographic evidence considered",
    )


def _decision_file(
    checkpoint: PhaseIIIReviewCheckpoint,
    decisions: tuple[PhaseIIIReviewDecision, ...],
) -> PhaseIIIReviewDecisionFile:
    return PhaseIIIReviewDecisionFile.from_content(
        checkpoint=checkpoint,
        owned_parent_run_id="gtd-unknown-screen-owned-run",
        review_package_id="reviewpkg_phase3_unknown",
        review_package_manifest_sha256=HASHES[0],
        decisions=decisions,
    )


@pytest.mark.parametrize(
    ("checkpoint", "decision"),
    (
        (
            PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
            PhaseIIIReviewDecisionValue.PROCEED,
        ),
        (
            PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
            PhaseIIIReviewDecisionValue.HOLD,
        ),
        (
            PhaseIIIReviewCheckpoint.A_SEED,
            PhaseIIIReviewDecisionValue.APPROVE,
        ),
        (
            PhaseIIIReviewCheckpoint.A_SEED,
            PhaseIIIReviewDecisionValue.REJECT,
        ),
        (
            PhaseIIIReviewCheckpoint.A_SEED,
            PhaseIIIReviewDecisionValue.DEFER,
        ),
        (
            PhaseIIIReviewCheckpoint.COMPOSITION,
            PhaseIIIReviewDecisionValue.APPROVE,
        ),
        (
            PhaseIIIReviewCheckpoint.COMPOSITION,
            PhaseIIIReviewDecisionValue.REJECT,
        ),
        (
            PhaseIIIReviewCheckpoint.COMPOSITION,
            PhaseIIIReviewDecisionValue.DEFER,
        ),
        (
            PhaseIIIReviewCheckpoint.COMPOSITION,
            PhaseIIIReviewDecisionValue.RETAIN_PARTIAL,
        ),
        (
            PhaseIIIReviewCheckpoint.SEQUENCE,
            PhaseIIIReviewDecisionValue.APPROVE,
        ),
        (
            PhaseIIIReviewCheckpoint.SEQUENCE,
            PhaseIIIReviewDecisionValue.RETAIN_ALTERNATIVE,
        ),
        (
            PhaseIIIReviewCheckpoint.SEQUENCE,
            PhaseIIIReviewDecisionValue.NO_ASSIGNMENT,
        ),
    ),
)
def test_each_checkpoint_has_an_immutable_content_addressed_decision_file(
    checkpoint: PhaseIIIReviewCheckpoint,
    decision: PhaseIIIReviewDecisionValue,
) -> None:
    record = _decision_file(checkpoint, (_decision("item_1", decision),))

    assert record.decision_file_id.startswith("phase3review_")
    assert record.decisions[0].reviewed_at.utcoffset() == UTC.utcoffset(None)
    assert (
        PhaseIIIReviewDecisionFile.model_validate_json(record.model_dump_json())
        == record
    )


def test_decision_file_identity_rejects_parent_and_human_evidence_mutation() -> None:
    record = _decision_file(
        PhaseIIIReviewCheckpoint.A_SEED,
        (_decision("compstate_1", PhaseIIIReviewDecisionValue.APPROVE),),
    )

    changed_parent = record.model_dump(mode="python")
    changed_parent["review_package_manifest_sha256"] = HASHES[1]
    with pytest.raises(ValidationError, match="decision_file_id"):
        PhaseIIIReviewDecisionFile.model_validate(changed_parent)

    changed_human = record.model_dump(mode="python")
    changed_human["decisions"][0]["reason"] = "changed scientific rationale"
    with pytest.raises(ValidationError, match="decision_file_id"):
        PhaseIIIReviewDecisionFile.model_validate(changed_human)


def test_every_required_provenance_and_human_field_changes_content_identity() -> None:
    record = _decision_file(
        PhaseIIIReviewCheckpoint.A_SEED,
        (_decision("compstate_1", PhaseIIIReviewDecisionValue.APPROVE),),
    )
    base = record.model_dump(mode="python", exclude={"decision_file_id"})
    variants: list[dict[str, object]] = []

    for field, value in (
        ("checkpoint", PhaseIIIReviewCheckpoint.COMPOSITION),
        ("owned_parent_run_id", "gtd-different-owned-run"),
        ("review_package_id", "reviewpkg_different"),
        ("review_package_manifest_sha256", HASHES[1]),
    ):
        variant = deepcopy(base)
        variant[field] = value
        variants.append(variant)

    for field, value in (
        ("crystal_id", "unknown_2"),
        ("item_id", "compstate_2"),
        ("decision", PhaseIIIReviewDecisionValue.REJECT),
        ("reviewer", "reviewer_2"),
        ("reviewed_at", datetime(2026, 8, 23, 16, 1, tzinfo=UTC)),
        ("reason", "different scientific rationale"),
        ("comment", "different optional context"),
    ):
        variant = deepcopy(base)
        variant["decisions"][0][field] = value
        variants.append(variant)

    derived = {
        PhaseIIIReviewDecisionFile.from_content(**variant).decision_file_id
        for variant in variants
    }
    assert len(derived) == len(variants)
    assert record.decision_file_id not in derived


def test_checkpoint_rejects_a_decision_from_another_checkpoint() -> None:
    with pytest.raises(ValidationError, match="invalid for checkpoint"):
        _decision_file(
            PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
            (_decision("diffsel_1", PhaseIIIReviewDecisionValue.APPROVE),),
        )


def test_conflicting_duplicate_target_decisions_fail() -> None:
    with pytest.raises(ValidationError, match="duplicate or conflict"):
        _decision_file(
            PhaseIIIReviewCheckpoint.A_SEED,
            (
                _decision("compstate_1", PhaseIIIReviewDecisionValue.APPROVE),
                _decision("compstate_1", PhaseIIIReviewDecisionValue.REJECT),
            ),
        )


@pytest.mark.parametrize(
    ("checkpoint", "values", "message"),
    (
        (
            PhaseIIIReviewCheckpoint.A_SEED,
            (PhaseIIIReviewDecisionValue.APPROVE,) * 4,
            "approved A states",
        ),
        (
            PhaseIIIReviewCheckpoint.COMPOSITION,
            (
                PhaseIIIReviewDecisionValue.APPROVE,
                PhaseIIIReviewDecisionValue.RETAIN_PARTIAL,
                PhaseIIIReviewDecisionValue.RETAIN_PARTIAL,
                PhaseIIIReviewDecisionValue.APPROVE,
            ),
            "combined composition finalists",
        ),
    ),
)
def test_per_crystal_retained_state_limit_is_three(
    checkpoint: PhaseIIIReviewCheckpoint,
    values: tuple[PhaseIIIReviewDecisionValue, ...],
    message: str,
) -> None:
    decisions = tuple(
        _decision(f"state_{index}", value)
        for index, value in enumerate(values, start=1)
    )

    with pytest.raises(ValidationError, match=message):
        _decision_file(checkpoint, decisions)

    split_crystals = tuple(
        _decision(
            f"state_{index}",
            value,
            crystal_id="unknown_1" if index <= 3 else "unknown_2",
        )
        for index, value in enumerate(values, start=1)
    )
    assert len(_decision_file(checkpoint, split_crystals).decisions) == 4


def test_operator_tsv_derives_the_canonical_file_identity(tmp_path: Path) -> None:
    path = tmp_path / "a-seed-decisions.tsv"
    path.write_text(
        "\t".join(
            (
                "checkpoint",
                "owned_parent_run_id",
                "review_package_id",
                "review_package_manifest_sha256",
                "crystal_id",
                "item_id",
                "decision",
                "reviewer",
                "reviewed_at",
                "reason",
                "comment",
            )
        )
        + "\n"
        + "\t".join(
            (
                "a_seed",
                "gtd-unknown-screen-owned-run",
                "reviewpkg_phase3_unknown",
                HASHES[0],
                "unknown_1",
                "compstate_1",
                "approve",
                "reviewer_1",
                "2026-08-23T16:00:00Z",
                "map inspected",
                "retain for A expansion",
            )
        )
        + "\n",
        encoding="utf-8",
    )

    loaded = load_contract(path, "phase3-review-decisions", progress=False)

    assert isinstance(loaded, PhaseIIIReviewDecisionFile)
    assert loaded.decision_file_id.startswith("phase3review_")
    assert loaded.checkpoint is PhaseIIIReviewCheckpoint.A_SEED
    assert loaded.decisions[0].decision is PhaseIIIReviewDecisionValue.APPROVE

    json_path = tmp_path / "a-seed-decisions.json"
    json_path.write_text(loaded.model_dump_json(), encoding="utf-8")
    assert load_contract(json_path, "phase3-review-decisions", progress=False) == loaded


def test_operator_tsv_cannot_mix_parent_review_packages(tmp_path: Path) -> None:
    path = tmp_path / "mixed-package.tsv"
    header = (
        "checkpoint\towned_parent_run_id\treview_package_id\t"
        "review_package_manifest_sha256\tcrystal_id\titem_id\tdecision\t"
        "reviewer\treviewed_at\treason\n"
    )
    row_1 = (
        f"a_seed\trun_1\tpackage_1\t{HASHES[0]}\tunknown_1\tstate_1\t"
        "approve\treviewer\t2026-08-23T16:00:00Z\tmap inspected\n"
    )
    row_2 = (
        f"a_seed\trun_1\tpackage_2\t{HASHES[1]}\tunknown_1\tstate_2\t"
        "approve\treviewer\t2026-08-23T16:01:00Z\tmap inspected\n"
    )
    path.write_text(header + row_1 + row_2, encoding="utf-8")

    with pytest.raises(ContractLoadError, match="mixes checkpoint or parent-package"):
        load_contract(path, "phase3-review-decisions", progress=False)


def test_existing_v1_review_decisions_remain_unchanged() -> None:
    legacy = ReviewDecisionManifest(
        schema_version="1.0",
        decisions=(
            ReviewDecision(
                checkpoint="mr_seed",
                item_id="sol_legacy",
                decision="approve",
                reviewer="reviewer_1",
                reviewed_at=datetime(2026, 8, 23, 16, 0, tzinfo=UTC),
                comment="existing v1 decision",
            ),
        ),
    )

    assert (
        ReviewDecisionManifest.model_validate_json(legacy.model_dump_json()) == legacy
    )
    with pytest.raises(ValidationError):
        PhaseIIIReviewDecisionFile.model_validate_json(legacy.model_dump_json())
