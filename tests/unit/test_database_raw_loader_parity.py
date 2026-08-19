"""Strict mutation parity for database state and external JSON responses."""

from collections.abc import Callable
from pathlib import Path

import pytest

from genome_to_diffraction.databases.cache import (
    _load_json_document as load_cache_document,
)
from genome_to_diffraction.databases.common import (
    _load_json_document as load_inventory_document,
)
from genome_to_diffraction.databases.network import _load_partial_state
from genome_to_diffraction.databases.prepare import (
    _load_json_document as load_preparation_document,
)
from genome_to_diffraction.databases.sources import _read_manifest
from genome_to_diffraction.status import GenomeToDiffractionError
from genome_to_diffraction.structure_search.afdb_exact import _parse_metadata

PathLoader = Callable[[Path], object]

_PATH_LOADERS: tuple[tuple[str, PathLoader, str | None], ...] = (
    (
        "database-preparation",
        lambda path: load_preparation_document(path, "fixture"),
        None,
    ),
    ("database-source", _read_manifest, None),
    (
        "partial-download",
        lambda path: _load_partial_state(
            path, requested_url="https://example.invalid/database"
        ),
        None,
    ),
    ("coordinate-cache", lambda path: load_cache_document(path, "fixture"), None),
    (
        "resource-inventory",
        lambda path: load_inventory_document(path, "fixture"),
        None,
    ),
    (
        "afdb-response",
        lambda path: _parse_metadata(
            path.read_bytes(),
            accession="P12345",
            raw_response_pointer=path.name,
            raw_response_sha256="0" * 64,
        ),
        "AFDB metadata",
    ),
)


def _contents(mutation: str) -> str:
    return (
        '{"root":{"value":1,"value":2}}\n'
        if mutation == "duplicate"
        else '{"root":{"value":NaN}}\n'
    )


@pytest.mark.parametrize(("loader_name", "loader", "label"), _PATH_LOADERS)
@pytest.mark.parametrize("mutation", ("duplicate", "non-finite"))
def test_database_json_boundaries_reject_ambiguous_numeric_documents(
    tmp_path: Path,
    loader_name: str,
    loader: PathLoader,
    label: str | None,
    mutation: str,
) -> None:
    path = tmp_path / f"{loader_name}-{mutation}.json"
    path.write_text(_contents(mutation), encoding="utf-8")

    with pytest.raises(GenomeToDiffractionError) as captured:
        loader(path)

    diagnostic = str(captured.value)
    assert (label or str(path)) in diagnostic
    assert "/root/value" in diagnostic
    expected = "duplicate mapping key" if mutation == "duplicate" else "numeric"
    assert expected in diagnostic
