"""Regression tests for additional-copy staging provenance."""

from pathlib import Path

import pytest

from genome_to_diffraction.mr.stage_add_copy import _model_source_relative_path


def test_cross_site_model_source_is_relative_to_stage_output(tmp_path: Path) -> None:
    parent = tmp_path / "import-parent"
    output = tmp_path / "m4-copy-inputs"
    source = output / "review_package/assets/solution/solution.pdb"

    assert _model_source_relative_path(
        source,
        parent=parent,
        output=output,
        cross_site_import=True,
    ) == "review_package/assets/solution/solution.pdb"


def test_model_source_outside_selected_provenance_root_fails(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="outside its provenance root"):
        _model_source_relative_path(
            tmp_path / "elsewhere/model.pdb",
            parent=tmp_path / "parent",
            output=tmp_path / "output",
            cross_site_import=False,
        )
