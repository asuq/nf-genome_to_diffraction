"""Unit tests for canonical serialisation and persistent identifiers."""

import re

import pytest

from genome_to_diffraction.ids import (
    canonical_digest,
    canonical_json_text,
    canonical_sequence,
    content_id,
    identity_view,
    sequence_digest,
    sequence_group_id,
)


def test_canonical_json_is_order_independent() -> None:
    left = {"b": 1, "a": [True, None, "x"]}
    right = {"a": [True, None, "x"], "b": 1}
    assert canonical_json_text(left) == '{"a":[true,null,"x"],"b":1}'
    assert canonical_digest(left) == canonical_digest(right)


def test_sequence_identity_uses_uppercase_without_whitespace() -> None:
    assert canonical_sequence(" ac\nD\t") == "ACD"
    assert sequence_digest("acd") == sequence_digest("A C D")
    assert sequence_group_id("acd") == f"seq_{sequence_digest('ACD')}"


def test_sequence_rejects_empty_and_non_ascii() -> None:
    with pytest.raises(ValueError, match="empty"):
        canonical_sequence(" \n")
    with pytest.raises(ValueError, match="ASCII"):
        canonical_sequence("ACΔ")


def test_content_id_uses_full_digest_and_validates_prefix() -> None:
    identifier = content_id("hyp_", {"copy": 2, "sequence": "seq_example"})
    assert re.fullmatch(r"hyp_[a-f0-9]{64}", identifier)
    with pytest.raises(ValueError, match="prefix"):
        content_id("Hyp-", {})


def test_identity_view_can_remove_paths_and_timestamps_explicitly() -> None:
    excluded = frozenset({"created_at", "path"})
    first = identity_view(
        {"id": "sample", "path": "/machine/a", "created_at": "2026-01-01Z"},
        exclude_fields=excluded,
    )
    second = identity_view(
        {"id": "sample", "path": "/machine/b", "created_at": "2027-01-01Z"},
        exclude_fields=excluded,
    )
    assert content_id("run_", first) == content_id("run_", second)
