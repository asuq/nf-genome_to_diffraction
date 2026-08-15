"""The T13.2 report stays inside and verifies the T12.5 package."""

import json
import re
from pathlib import Path

from genome_to_diffraction.checksums import sha256_file
from genome_to_diffraction.review.crystal_report import (
    CrystalReportRequest,
    build_crystal_report,
)


def _write_checkpoint(root: Path) -> tuple[Path, Path]:
    seed_id = "sol_test"
    asset_dir = root / "assets" / seed_id
    asset_dir.mkdir(parents=True)
    assets: dict[str, str] = {}
    for name in (
        "brief_refine_001.pdb",
        "brief_refine_001.mtz",
        "brief_refine_2mFo-DFc.ccp4",
        "sequence_from_map.pdb",
    ):
        path = asset_dir / name
        path.write_text(name, encoding="utf-8")
        assets[path.relative_to(root).as_posix()] = sha256_file(path)

    outputs: dict[str, str] = {}
    for name in (
        "sequence_candidates.html",
        "sequence_candidates_top10.tsv",
        "sequence_candidates_top25.tsv",
        "sequence_candidates_full.tsv",
        "sequence_approval_candidates.tsv",
        "approved_sequence_groups.tsv",
    ):
        path = root / name
        path.write_text(name, encoding="utf-8")
        outputs[name] = sha256_file(path)
    (root / "sequence_checkpoint_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "gtd-t12-test",
                "package_id": "seqreview_test",
                "finalist_count": 1,
                "outputs": outputs,
                "identity": {"assets": assets},
            }
        ),
        encoding="utf-8",
    )
    status = root.parent / "status.json"
    status.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "crystal_id": "crystal_test",
                "execution_status": "completed_success",
                "scientific_status": "insufficient_evidence",
                "prototype_assumption_status": "unknown",
                "credible_seed_count": 1,
                "approved_seed_count": 1,
                "primary_sequence_groups": [],
                "extended_sequence_groups": [],
                "best_supported_copy_counts": {seed_id: 2},
                "residual_content_suspected": False,
                "warnings": ["human_sequence_approval_pending"],
                "completed_at": "2026-08-15T07:33:27Z",
                "provenance_pointers": ["t12-summary.json"],
            }
        ),
        encoding="utf-8",
    )
    return status, root


def test_report_links_to_every_verified_local_asset(tmp_path: Path) -> None:
    status, checkpoint = _write_checkpoint(tmp_path / "checkpoint")

    output = build_crystal_report(
        CrystalReportRequest(status_json=status, checkpoint_directory=checkpoint)
    )

    report = output.report_html.read_text(encoding="utf-8")
    assert "completed_success" in report
    assert "insufficient_evidence" in report
    assert "No primary group approved" in report
    links = re.findall(r'href="([^"]+)"', report)
    assert links
    assert all((checkpoint / link).is_file() for link in links)
    manifest = json.loads(output.manifest_json.read_text(encoding="utf-8"))
    assert manifest["report_id"] == output.report_id
    assert manifest["identity"]["checkpoint_package_id"] == "seqreview_test"
    assert manifest["outputs"][output.report_html.name] == sha256_file(
        output.report_html
    )
