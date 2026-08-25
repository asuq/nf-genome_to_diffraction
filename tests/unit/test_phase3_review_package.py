"""Focused safety and determinism tests for Phase III review packages."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

import genome_to_diffraction.review.phase3_package as phase3_package
from genome_to_diffraction.review import (
    PhaseIIIReviewEvidenceSource,
    PhaseIIIReviewPackageError,
    PhaseIIIReviewPackageRequest,
    build_phase3_review_package,
    validate_phase3_review_package,
)
from genome_to_diffraction.schemas.v2 import (
    PhaseIIIReviewCheckpoint,
    PhaseIIIReviewEvidenceArtifact,
    PhaseIIIReviewPackageManifest,
    PhaseIIIReviewPackageTarget,
    PhaseIIIReviewTableArtifact,
)
from genome_to_diffraction.schemas.v2.review import (
    phase3_review_package_content_sha256,
)

EXECUTION_ID = f"phase3exec_{'a' * 64}"
CREATED_AT = datetime(2026, 8, 23, 20, 0, tzinfo=UTC)


def _request(
    *,
    input_root: Path,
    output: Path,
    checkpoint: PhaseIIIReviewCheckpoint = PhaseIIIReviewCheckpoint.A_SEED,
    targets: tuple[str, ...] = ("state_2", "state_1"),
    sources: tuple[PhaseIIIReviewEvidenceSource, ...] | None = None,
) -> PhaseIIIReviewPackageRequest:
    return PhaseIIIReviewPackageRequest(
        checkpoint=checkpoint,
        owned_parent_run_id="gtd-unknown-screen-owned-run",
        parent_profile="unknown-screen",
        parent_phase="phase3-pass1",
        execution_identity_id=EXECUTION_ID,
        crystal_id="AD4QS1P4G2_18",
        target_item_ids=targets,
        created_at=CREATED_AT,
        input_root=input_root,
        evidence_sources=(
            sources
            if sources is not None
            else (
                PhaseIIIReviewEvidenceSource(
                    role="xtriage_summary",
                    relative_path="crystallography/xtriage.json",
                ),
                PhaseIIIReviewEvidenceSource(
                    role="candidate_metrics",
                    relative_path="mr/candidates.tsv",
                ),
            )
        ),
        output_directory=output,
    )


def _inputs(tmp_path: Path) -> Path:
    root = tmp_path / "inputs"
    (root / "crystallography").mkdir(parents=True)
    (root / "mr").mkdir()
    (root / "crystallography" / "xtriage.json").write_text(
        '{"status":"review_required"}\n',
        encoding="ascii",
    )
    (root / "mr" / "candidates.tsv").write_text(
        "item_id\tllg\ttfz\nstate_1\t120\t11\n",
        encoding="ascii",
    )
    return root


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


@pytest.mark.parametrize(
    ("checkpoint", "adapter_version", "allowed_decisions"),
    (
        (
            PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
            "phase3-review-package-v1",
            "hold|proceed",
        ),
        (
            PhaseIIIReviewCheckpoint.A_SEED,
            "phase3-review-package-v1",
            "approve|defer|reject",
        ),
        (
            PhaseIIIReviewCheckpoint.COMPOSITION,
            "phase3-review-package-v2",
            "approve|defer|reject|retain_partial",
        ),
        (
            PhaseIIIReviewCheckpoint.SEQUENCE,
            "phase3-review-package-v2",
            "approve|no_assignment|retain_alternative",
        ),
    ),
)
def test_builds_one_path_free_content_addressed_package(
    tmp_path: Path,
    checkpoint: PhaseIIIReviewCheckpoint,
    adapter_version: str,
    allowed_decisions: str,
) -> None:
    input_root = _inputs(tmp_path)
    output = tmp_path / "review-package"
    output.mkdir()

    result = build_phase3_review_package(
        _request(
            input_root=input_root,
            output=output,
            checkpoint=checkpoint,
        )
    )

    manifest = validate_phase3_review_package(output)
    assert manifest.review_package_id == result.review_package_id
    assert manifest.review_package_id.startswith("phase3reviewpkg_")
    assert manifest.adapter_version == adapter_version
    assert manifest.execution_identity_id == EXECUTION_ID
    assert manifest.crystal_id == "AD4QS1P4G2_18"
    assert tuple(target.item_id for target in manifest.permitted_targets) == (
        "state_1",
        "state_2",
    )
    assert tuple(item.role for item in manifest.evidence_inventory) == (
        "candidate_metrics",
        "xtriage_summary",
    )
    assert result.review_table.read_text(encoding="ascii").count("\n") == 3
    assert result.evidence_files[0].read_text(encoding="ascii").startswith("item_id")
    manifest_text = result.manifest.read_text(encoding="ascii")
    table_text = result.review_table.read_text(encoding="ascii")
    assert table_text.count(allowed_decisions) == 2
    assert str(input_root) not in manifest_text
    assert str(input_root) not in table_text
    assert str(output) not in manifest_text
    assert str(output) not in table_text


def test_permuted_targets_and_evidence_produce_byte_identical_packages(
    tmp_path: Path,
) -> None:
    input_root = _inputs(tmp_path)
    output_a = tmp_path / "package-a"
    output_b = tmp_path / "package-b"
    output_a.mkdir()
    output_b.mkdir()
    sources = (
        PhaseIIIReviewEvidenceSource(
            role="candidate_metrics",
            relative_path="mr/candidates.tsv",
        ),
        PhaseIIIReviewEvidenceSource(
            role="xtriage_summary",
            relative_path="crystallography/xtriage.json",
        ),
    )

    first = build_phase3_review_package(
        _request(
            input_root=input_root,
            output=output_a,
            targets=("state_2", "state_1"),
            sources=sources,
        )
    )
    second = build_phase3_review_package(
        _request(
            input_root=input_root,
            output=output_b,
            targets=("state_1", "state_2"),
            sources=tuple(reversed(sources)),
        )
    )

    assert first.review_package_id == second.review_package_id
    assert first.package_content_sha256 == second.package_content_sha256
    assert _tree_bytes(output_a) == _tree_bytes(output_b)


def test_a_seed_no_model_package_retains_authenticated_empty_review(
    tmp_path: Path,
) -> None:
    input_root = _inputs(tmp_path)
    legacy = input_root / "mr" / "mr_seed_review_manifest.json"
    legacy.write_text(
        '{"schema_version":"1.0","review_package_kind":"mr_seed",'
        '"checkpoint":"mr_seed","candidate_count":0,'
        '"inspectable_solution_count":0,"items":[], '
        '"execution_status":"completed_success"}\n',
        encoding="ascii",
    )
    output = tmp_path / "empty-a-review-package"
    output.mkdir()

    result = build_phase3_review_package(
        _request(
            input_root=input_root,
            output=output,
            targets=(),
            sources=(
                PhaseIIIReviewEvidenceSource(
                    role="mr_seed_review_manifest",
                    relative_path="mr/mr_seed_review_manifest.json",
                ),
            ),
        )
    )

    manifest = validate_phase3_review_package(output)
    assert manifest.review_package_id == result.review_package_id
    assert manifest.adapter_version == "phase3-review-package-v2"
    assert manifest.checkpoint is PhaseIIIReviewCheckpoint.A_SEED
    assert manifest.permitted_targets == ()
    assert manifest.review_tables[0].row_count == 0
    assert manifest.review_tables[0].target_item_ids == ()
    assert result.review_table.read_text(encoding="ascii").count("\n") == 1
    assert result.evidence_files[0].read_bytes() == legacy.read_bytes()


@pytest.mark.parametrize(
    "failure",
    ("missing_evidence", "positive_count", "retained_target", "failed_execution"),
)
def test_empty_a_seed_package_rejects_unproven_no_model_state(
    tmp_path: Path,
    failure: str,
) -> None:
    input_root = _inputs(tmp_path)
    legacy = input_root / "mr" / "mr_seed_review_manifest.json"
    count = 1 if failure == "positive_count" else 0
    targets = (
        '[{"solution_id":"sol_present"}]' if failure == "retained_target" else "[]"
    )
    status = (
        "execution_failure" if failure == "failed_execution" else "completed_success"
    )
    legacy.write_text(
        '{"schema_version":"1.0","review_package_kind":"mr_seed",'
        f'"checkpoint":"mr_seed","candidate_count":{count},'
        f'"inspectable_solution_count":0,"items":{targets},'
        f'"execution_status":"{status}"}}\n',
        encoding="ascii",
    )
    source = (
        PhaseIIIReviewEvidenceSource("wrong_role", "mr/mr_seed_review_manifest.json")
        if failure == "missing_evidence"
        else PhaseIIIReviewEvidenceSource(
            "mr_seed_review_manifest", "mr/mr_seed_review_manifest.json"
        )
    )
    output = tmp_path / "must-remain-empty"
    output.mkdir()

    with pytest.raises(PhaseIIIReviewPackageError, match="empty A-seed"):
        build_phase3_review_package(
            _request(
                input_root=input_root,
                output=output,
                targets=(),
                sources=(source,),
            )
        )

    assert list(output.iterdir()) == []


@pytest.mark.parametrize(
    "checkpoint",
    (
        PhaseIIIReviewCheckpoint.CRYSTALLOGRAPHIC,
        PhaseIIIReviewCheckpoint.COMPOSITION,
        PhaseIIIReviewCheckpoint.SEQUENCE,
    ),
)
def test_only_a_seed_checkpoint_permits_an_evidence_backed_empty_package(
    tmp_path: Path,
    checkpoint: PhaseIIIReviewCheckpoint,
) -> None:
    output = tmp_path / "must-remain-empty"
    output.mkdir()

    with pytest.raises(PhaseIIIReviewPackageError, match="at least one target"):
        build_phase3_review_package(
            _request(
                input_root=_inputs(tmp_path),
                output=output,
                checkpoint=checkpoint,
                targets=(),
            )
        )

    assert list(output.iterdir()) == []


def test_input_mutation_fails_without_publishing_a_partial_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_root = _inputs(tmp_path)
    output = tmp_path / "review-package"
    output.mkdir()
    original_sha256_file = phase3_package.sha256_file
    mutation_done = False

    def _mutate_then_checksum(path: Path, *, progress: bool) -> str:
        nonlocal mutation_done
        if not mutation_done:
            path.write_bytes(b"mutated during packaging\n")
            mutation_done = True
        return original_sha256_file(path, progress=progress)

    monkeypatch.setattr(phase3_package, "sha256_file", _mutate_then_checksum)

    with pytest.raises(PhaseIIIReviewPackageError, match="changed while"):
        build_phase3_review_package(_request(input_root=input_root, output=output))

    assert list(output.iterdir()) == []


def test_post_publication_mutation_is_detected(tmp_path: Path) -> None:
    input_root = _inputs(tmp_path)
    output = tmp_path / "review-package"
    output.mkdir()
    result = build_phase3_review_package(_request(input_root=input_root, output=output))
    original = result.evidence_files[0].read_bytes()
    result.evidence_files[0].write_bytes(b"x" * len(original))

    with pytest.raises(PhaseIIIReviewPackageError, match="checksum differs"):
        validate_phase3_review_package(output)


def test_manifest_rejects_a_review_table_missing_one_target() -> None:
    evidence = (
        PhaseIIIReviewEvidenceArtifact(
            role="xtriage_summary",
            relative_path="evidence/xtriage.json",
            sha256="b" * 64,
            size_bytes=20,
        ),
    )
    tables = (
        PhaseIIIReviewTableArtifact(
            role="review_targets",
            relative_path="review_targets.tsv",
            sha256="c" * 64,
            size_bytes=100,
            row_count=1,
            target_item_ids=("state_1",),
        ),
    )

    with pytest.raises(ValueError, match="cover every target"):
        PhaseIIIReviewPackageManifest.from_content(
            adapter_version="phase3-review-package-v1",
            checkpoint=PhaseIIIReviewCheckpoint.A_SEED,
            owned_parent_run_id="gtd-owned-run",
            parent_profile="unknown-screen",
            parent_phase="phase3-pass1",
            execution_identity_id=EXECUTION_ID,
            crystal_id="AD4QS1P4G2_18",
            created_at=CREATED_AT,
            permitted_targets=(
                PhaseIIIReviewPackageTarget(
                    crystal_id="AD4QS1P4G2_18",
                    item_id="state_1",
                ),
                PhaseIIIReviewPackageTarget(
                    crystal_id="AD4QS1P4G2_18",
                    item_id="state_2",
                ),
            ),
            evidence_inventory=evidence,
            review_tables=tables,
            package_content_sha256=phase3_review_package_content_sha256(
                evidence_inventory=evidence,
                review_tables=tables,
            ),
        )


@pytest.mark.parametrize(
    ("sources", "message"),
    (
        (
            (
                PhaseIIIReviewEvidenceSource("same_role", "one.txt"),
                PhaseIIIReviewEvidenceSource("same_role", "two.txt"),
            ),
            "roles must be unique",
        ),
        (
            (
                PhaseIIIReviewEvidenceSource("role_one", "one.txt"),
                PhaseIIIReviewEvidenceSource("role_two", "one.txt"),
            ),
            "source paths must be unique",
        ),
    ),
)
def test_duplicate_evidence_role_or_path_fails(
    tmp_path: Path,
    sources: tuple[PhaseIIIReviewEvidenceSource, ...],
    message: str,
) -> None:
    input_root = tmp_path / "inputs"
    input_root.mkdir()
    (input_root / "one.txt").write_text("one\n", encoding="ascii")
    (input_root / "two.txt").write_text("two\n", encoding="ascii")
    output = tmp_path / "review-package"
    output.mkdir()

    with pytest.raises(PhaseIIIReviewPackageError, match=message):
        build_phase3_review_package(
            _request(
                input_root=input_root,
                output=output,
                sources=sources,
            )
        )


def test_symlink_and_path_escape_fail_before_publication(tmp_path: Path) -> None:
    input_root = tmp_path / "inputs"
    input_root.mkdir()
    real_file = input_root / "real.txt"
    real_file.write_text("evidence\n", encoding="ascii")
    (input_root / "linked.txt").symlink_to(real_file.name)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n", encoding="ascii")

    for relative_path, message in (
        ("linked.txt", "symlink"),
        ("../outside.txt", "unsafe"),
    ):
        output = tmp_path / f"package-{relative_path[0]}"
        output.mkdir()
        with pytest.raises(PhaseIIIReviewPackageError, match=message):
            build_phase3_review_package(
                _request(
                    input_root=input_root,
                    output=output,
                    sources=(
                        PhaseIIIReviewEvidenceSource(
                            role="evidence",
                            relative_path=relative_path,
                        ),
                    ),
                )
            )
        assert list(output.iterdir()) == []
