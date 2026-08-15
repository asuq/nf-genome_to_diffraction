"""Build the T13.2 review report inside a verified T12.5 package."""

import html
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ValidationError

from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import content_id
from genome_to_diffraction.schemas.results import ScientificStatusRecord
from genome_to_diffraction.status import InputContractError


class CrystalReportError(InputContractError):
    """The status or T12.5 checkpoint cannot support a trusted report."""


class _CheckpointIdentity(BaseModel):
    assets: dict[str, str]


class _CheckpointManifest(BaseModel):
    schema_version: str
    run_id: str
    package_id: str
    finalist_count: int
    outputs: dict[str, str]
    identity: _CheckpointIdentity


@dataclass(frozen=True)
class CrystalReportRequest:
    """Inputs for one self-contained review report."""

    status_json: Path
    checkpoint_directory: Path


@dataclass(frozen=True)
class CrystalReportOutput:
    """Stable report files written into the checkpoint directory."""

    report_id: str
    report_html: Path
    status_json: Path
    manifest_json: Path


def _load_status(path: Path) -> ScientificStatusRecord:
    if path.is_symlink() or not path.is_file():
        raise CrystalReportError("scientific status is absent or unsafe")
    try:
        return ScientificStatusRecord.model_validate_json(path.read_text("utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        raise CrystalReportError(f"invalid scientific status: {exc}") from exc


def _load_checkpoint(root: Path) -> tuple[_CheckpointManifest, Path]:
    if root.is_symlink() or not root.is_dir():
        raise CrystalReportError("checkpoint directory is absent or unsafe")
    manifest_path = root / "sequence_checkpoint_manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise CrystalReportError("sequence checkpoint manifest is absent or unsafe")
    try:
        manifest = _CheckpointManifest.model_validate_json(
            manifest_path.read_text("utf-8")
        )
    except (OSError, ValidationError, ValueError) as exc:
        raise CrystalReportError(
            f"invalid sequence checkpoint manifest: {exc}"
        ) from exc
    return manifest, manifest_path


def _verify_checkpoint(root: Path, manifest: _CheckpointManifest) -> None:
    for relative, expected in {**manifest.outputs, **manifest.identity.assets}.items():
        path = root / relative
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise CrystalReportError(
                f"checkpoint path escapes package: {relative}"
            ) from exc
        if path.is_symlink() or not path.is_file() or sha256_file(path) != expected:
            raise CrystalReportError(
                f"checkpoint asset failed verification: {relative}"
            )


def verify_checkpoint_package(root: Path) -> tuple[_CheckpointManifest, Path]:
    """Load and checksum-verify one T12.5 package."""

    manifest, manifest_path = _load_checkpoint(root)
    _verify_checkpoint(root, manifest)
    return manifest, manifest_path


def _list_items(items: tuple[str, ...], empty_text: str) -> str:
    if not items:
        return f"<p>{html.escape(empty_text)}</p>"
    return (
        "<ul>"
        + "".join(f"<li><code>{html.escape(item)}</code></li>" for item in items)
        + "</ul>"
    )


def _render_report(
    status: ScientificStatusRecord,
    checkpoint: _CheckpointManifest,
) -> str:
    warning_items = _list_items(status.warnings, "None recorded")
    primary = _list_items(status.primary_sequence_groups, "No primary group approved")
    extended = _list_items(
        status.extended_sequence_groups, "No alternative group retained"
    )
    rows: list[str] = []
    asset_names = (
        ("Refined PDB", "brief_refine_001.pdb"),
        ("Refined MTZ", "brief_refine_001.mtz"),
        ("2mFo-DFc map", "brief_refine_2mFo-DFc.ccp4"),
        ("Sequence model", "sequence_from_map.pdb"),
    )
    for seed_id, copy_count in sorted(status.best_supported_copy_counts.items()):
        asset_root = f"assets/{seed_id}"
        links = " ".join(
            f'<a href="{html.escape(asset_root + "/" + filename)}">'
            f"{html.escape(label)}</a>"
            for label, filename in asset_names
        )
        rows.append(
            "<tr>"
            f"<td><code>{html.escape(seed_id)}</code></td>"
            f"<td>{copy_count}</td><td>{links}</td>"
            "</tr>"
        )
    provenance = _list_items(status.provenance_pointers, "None recorded")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(status.crystal_id)} review report</title>
  <style>
    body {{
      font-family: system-ui, sans-serif; max-width: 1100px;
      margin: 2rem auto; padding: 0 1rem; line-height: 1.45;
    }}
    .status {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: .75rem;
    }}
    .card {{ border: 1px solid #bbb; border-radius: .5rem; padding: .8rem; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{
      border: 1px solid #ccc; padding: .45rem;
      text-align: left; vertical-align: top;
    }}
    code {{ overflow-wrap: anywhere; }}
    .caution {{ border-left: .35rem solid #b36b00; padding-left: .8rem; }}
  </style>
</head>
<body>
  <h1>{html.escape(status.crystal_id)} review report</h1>
  <p class="caution">
    This report preserves ranked evidence and human decisions. It is not a
    validated structure or exact identity unless the recorded scientific
    status says so.
  </p>
  <div class="status">
    <div class="card"><strong>Execution</strong><br>
      {html.escape(status.execution_status.value)}</div>
    <div class="card"><strong>Scientific status</strong><br>
      {html.escape(status.scientific_status.value)}</div>
    <div class="card"><strong>Prototype assumption</strong><br>
      {html.escape(status.prototype_assumption_status.value)}</div>
    <div class="card"><strong>T12.5 package</strong><br>
      <code>{html.escape(checkpoint.package_id)}</code></div>
  </div>
  <h2>Warnings</h2>{warning_items}
  <h2>Primary sequence groups</h2>{primary}
  <h2>Retained sequence alternatives</h2>{extended}
  <h2>Sequence review</h2>
  <ul>
    <li><a href="sequence_candidates.html">Interactive finalist view</a></li>
    <li><a href="sequence_candidates_top10.tsv">Top 10 per finalist</a></li>
    <li><a href="sequence_candidates_top25.tsv">Top 25 per finalist</a></li>
    <li><a href="sequence_candidates_full.tsv">All scored groups</a></li>
    <li><a href="sequence_approval_candidates.tsv">Unique approval candidates</a></li>
    <li><a href="approved_sequence_groups.tsv">Human decisions</a></li>
  </ul>
  <h2>Structural finalists</h2>
  <table><thead><tr>
    <th>Seed solution</th><th>Copy count</th><th>Assets</th>
  </tr></thead>
  <tbody>{"".join(rows)}</tbody></table>
  <h2>Provenance pointers</h2>{provenance}
  <p><a href="scientific_status.json">Machine-readable status</a> ·
    <a href="sequence_checkpoint_manifest.json">T12.5 manifest</a></p>
</body>
</html>
"""


def build_crystal_report(request: CrystalReportRequest) -> CrystalReportOutput:
    """Verify the checkpoint and atomically add the T13.2 report files."""

    status = _load_status(request.status_json)
    checkpoint, checkpoint_manifest_path = verify_checkpoint_package(
        request.checkpoint_directory
    )
    if len(status.best_supported_copy_counts) != checkpoint.finalist_count:
        raise CrystalReportError("status and checkpoint finalist counts disagree")

    report_html = request.checkpoint_directory / "crystal_report.html"
    status_output = request.checkpoint_directory / "scientific_status.json"
    manifest_output = request.checkpoint_directory / "crystal_report_manifest.json"
    atomic_write_json(status_output, status.model_dump(mode="json"))
    atomic_write_text(report_html, _render_report(status, checkpoint))
    identity = {
        "adapter_version": "crystal-report-v1",
        "crystal_id": status.crystal_id,
        "checkpoint_package_id": checkpoint.package_id,
        "checkpoint_manifest_sha256": sha256_file(checkpoint_manifest_path),
        "scientific_status_sha256": sha256_file(status_output),
        "report_html_sha256": sha256_file(report_html),
    }
    report_id = content_id("report_", identity)
    atomic_write_json(
        manifest_output,
        {
            "schema_version": "1.0",
            "report_id": report_id,
            "identity": identity,
            "outputs": {
                status_output.name: sha256_file(status_output),
                report_html.name: sha256_file(report_html),
            },
        },
    )
    return CrystalReportOutput(
        report_id=report_id,
        report_html=report_html,
        status_json=status_output,
        manifest_json=manifest_output,
    )
