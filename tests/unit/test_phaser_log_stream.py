"""Bounded native-log extraction preserves supported Phaser parser evidence."""

import tracemalloc
from pathlib import Path

import pytest

from genome_to_diffraction.mr.phaser import (
    PhaserParseError,
    parse_phaser_log,
    read_phaser_log_evidence,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/phaser"


@pytest.mark.parametrize(
    "name",
    (
        "phenix_2_1_positive.log",
        "phenix_2_1_no_solution.log",
        "phenix_2_1_no_solution_packing.log",
    ),
)
def test_streamed_evidence_matches_frozen_supported_output(name: str) -> None:
    path = FIXTURES / name
    assert parse_phaser_log(read_phaser_log_evidence(path)) == parse_phaser_log(
        path.read_text()
    )


def test_streamed_evidence_memory_is_independent_of_repeated_log_records(
    tmp_path: Path,
) -> None:
    path = tmp_path / "PHASER.log"
    with path.open("w") as handle:
        for index in range(5_000):
            handle.write(f"LLGI={index}.0 " + "x" * 500 + "\n")
        handle.write((FIXTURES / "phenix_2_1_positive.log").read_text())
    tracemalloc.start()
    try:
        summary = read_phaser_log_evidence(path)
        _, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert path.stat().st_size > 2_500_000
    assert peak_bytes < 2_000_000
    assert len(summary) < 5_000
    assert parse_phaser_log(summary) == parse_phaser_log(path.read_text())
    assert parse_phaser_log(summary).llgi == 4999.0


def test_streamed_evidence_uses_latest_terminal_count_not_an_earlier_hit(
    tmp_path: Path,
) -> None:
    path = tmp_path / "PHASER.log"
    path.write_text(
        (FIXTURES / "phenix_2_1_positive.log").read_text()
        + (FIXTURES / "phenix_2_1_no_solution_packing.log").read_text()
    )
    parsed = parse_phaser_log(read_phaser_log_evidence(path))
    assert parsed == parse_phaser_log(path.read_text())
    assert parsed.solution_count == 0
    assert parsed.packed_solution_count == 0


@pytest.mark.parametrize(
    ("text", "reason"),
    (
        (
            "Top LLG (packs) = 120; 2 accepted of 2 solutions\n"
            "this line interrupts the packing record\n"
            "2 pack of 2 accepted solutions LLGI=5\n"
            "Refined TF/TFZ equivalent = 120/12\n** There were 2 solutions\n",
            "final packing evidence",
        ),
        (
            "Top LLG (packs) = 120\n"
            "LLGI=5 Solution #1 annotation (history):\n"
            "this line interrupts the annotation\n"
            "SOLU SET TFZ=12 PAK=0\n** SINGLE solution\n",
            "final LLG or TFZ",
        ),
    ),
)
def test_discarded_lines_never_join_unrelated_fragments_into_valid_evidence(
    tmp_path: Path,
    text: str,
    reason: str,
) -> None:
    path = tmp_path / "PHASER.log"
    path.write_text(text)
    for evidence in (text, read_phaser_log_evidence(path)):
        with pytest.raises(PhaserParseError, match=reason):
            parse_phaser_log(evidence)


def test_streamed_log_rejects_oversized_lines_explicitly(tmp_path: Path) -> None:
    path = tmp_path / "PHASER.log"
    path.write_text("x" * 1_048_577 + "\n")
    with pytest.raises(PhaserParseError, match="evidence limit"):
        read_phaser_log_evidence(path)
