"""Strict mutation parity for non-M6 scientific and operator documents."""

from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from genome_to_diffraction.benchmarks.control_slice_run import (
    _object as load_control_slice_object,
)
from genome_to_diffraction.benchmarks.mr_controls import (
    _read_json as load_mr_control_object,
)
from genome_to_diffraction.benchmarks.mr_controls import (
    load_first_copy_control_pair,
)
from genome_to_diffraction.benchmarks.panel import (
    HomomerWorkflowSuiteSpec,
    PublicControlPanelSpec,
    load_homomer_workflow_slice,
    load_homomer_workflow_suite,
    load_public_control_panel,
)
from genome_to_diffraction.benchmarks.public_control import (
    load_public_control_spec,
)
from genome_to_diffraction.mr.add_copy import _json_object as load_add_copy_object
from genome_to_diffraction.mr.phaser import _load_manifest as load_phaser_manifest
from genome_to_diffraction.mr.stage_add_copy import (
    _load_object as load_add_copy_stage_object,
)
from genome_to_diffraction.ranking.funnel import _load_object as load_funnel_object
from genome_to_diffraction.refinement.stage import _load_object as load_t12_object
from genome_to_diffraction.review.mr_seed import (
    _load_json_object as load_mr_seed_object,
)
from genome_to_diffraction.review.sequence_checkpoint import (
    _load_object as load_sequence_checkpoint_object,
)
from genome_to_diffraction.schema_check import _load_document as load_schema_document
from genome_to_diffraction.status import GenomeToDiffractionError
from genome_to_diffraction.structure_search.qualification import (
    _load_manifest as load_qualification_manifest,
)

DocumentLoader = Callable[[Path], object]

_JSON_LOADERS: tuple[tuple[str, DocumentLoader], ...] = (
    ("t12-stage", lambda path: load_t12_object(path, "fixture")),
    ("add-copy-stage", lambda path: load_add_copy_stage_object(path, "fixture")),
    ("phaser-manifest", load_phaser_manifest),
    ("add-copy", lambda path: load_add_copy_object(path, label="fixture")),
    ("funnel", lambda path: load_funnel_object(path, label="fixture")),
    ("mr-control", lambda path: load_mr_control_object(path, label="fixture")),
    ("control-slice", load_control_slice_object),
    ("mr-seed-review", lambda path: load_mr_seed_object(path, label="fixture")),
    (
        "sequence-checkpoint",
        lambda path: load_sequence_checkpoint_object(path, "fixture"),
    ),
    ("search-qualification", load_qualification_manifest),
    ("schema-check-json", load_schema_document),
)

_YAML_LOADERS: tuple[tuple[str, DocumentLoader], ...] = (
    ("first-copy-control", load_first_copy_control_pair),
    ("public-control", load_public_control_spec),
    ("public-panel", load_public_control_panel),
    (
        "workflow-suite",
        lambda path: load_homomer_workflow_suite(
            path, cast(PublicControlPanelSpec, object())
        ),
    ),
    (
        "workflow-slice",
        lambda path: load_homomer_workflow_slice(
            path,
            panel=cast(PublicControlPanelSpec, object()),
            suite=cast(HomomerWorkflowSuiteSpec, object()),
        ),
    ),
    ("schema-check-yaml", load_schema_document),
)


@pytest.mark.parametrize(("loader_name", "loader"), _JSON_LOADERS)
@pytest.mark.parametrize("mutation", ("duplicate", "non-finite"))
def test_scientific_json_loaders_reject_ambiguous_numeric_documents(
    tmp_path: Path,
    loader_name: str,
    loader: DocumentLoader,
    mutation: str,
) -> None:
    path = tmp_path / f"{loader_name}-{mutation}.json"
    contents = (
        '{"root":{"value":1,"value":2}}\n'
        if mutation == "duplicate"
        else '{"root":{"value":NaN}}\n'
    )
    path.write_text(contents, encoding="utf-8")

    with pytest.raises((GenomeToDiffractionError, ValueError)) as captured:
        loader(path)

    assert str(path) in str(captured.value)
    assert "/root/value" in str(captured.value)
    expected = "duplicate mapping key" if mutation == "duplicate" else "numeric"
    assert expected in str(captured.value)


@pytest.mark.parametrize(("loader_name", "loader"), _YAML_LOADERS)
@pytest.mark.parametrize("mutation", ("duplicate", "non-finite"))
def test_scientific_yaml_loaders_reject_ambiguous_numeric_documents(
    tmp_path: Path,
    loader_name: str,
    loader: DocumentLoader,
    mutation: str,
) -> None:
    path = tmp_path / f"{loader_name}-{mutation}.yaml"
    contents = (
        "root:\n  value: 1\n  value: 2\n"
        if mutation == "duplicate"
        else "root:\n  value: .nan\n"
    )
    path.write_text(contents, encoding="utf-8")

    with pytest.raises((GenomeToDiffractionError, ValueError)) as captured:
        loader(path)

    assert str(path) in str(captured.value)
    assert "/root/value" in str(captured.value)
    expected = "duplicate mapping key" if mutation == "duplicate" else "non-finite"
    assert expected in str(captured.value)
