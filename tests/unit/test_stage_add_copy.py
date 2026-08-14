"""Regression tests for additional-copy staging provenance."""

from pathlib import Path

import pytest

from genome_to_diffraction.mr.stage_add_copy import _model_source_relative_path


def test_cross_site_model_source_is_relative_to_stage_output(tmp_path: Path) -> None:
    parent = tmp_path / "import-parent"
    real_output = tmp_path / "mounted/m4-copy-inputs"
    source = real_output / "review_package/assets/solution/solution.pdb"
    source.parent.mkdir(parents=True)
    source.write_text("ATOM\n", encoding="ascii")
    output = tmp_path / "m4-copy-inputs"
    output.symlink_to(real_output, target_is_directory=True)

    assert (
        _model_source_relative_path(
            source.resolve(strict=True),
            parent=parent,
            output=output,
            cross_site_import=True,
        )
        == "review_package/assets/solution/solution.pdb"
    )


def test_model_source_outside_selected_provenance_root_fails(tmp_path: Path) -> None:
    (tmp_path / "parent").mkdir()
    with pytest.raises(ValueError, match="outside its provenance root"):
        _model_source_relative_path(
            tmp_path / "elsewhere/model.pdb",
            parent=tmp_path / "parent",
            output=tmp_path / "output",
            cross_site_import=False,
        )
