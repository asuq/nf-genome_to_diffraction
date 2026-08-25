"""Materialise deterministic MTZ preflight stub rows for an input manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.schemas.io import load_contract
from genome_to_diffraction.schemas.manifests import CrystalManifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--crystals", type=Path, required=True)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Write one typed stub preflight row per declared crystal."""

    arguments = _parser().parse_args(argv)
    manifest = load_contract(arguments.crystals, "crystal-manifest", progress=False)
    if not isinstance(manifest, CrystalManifest):
        raise TypeError("crystal manifest loader returned an unexpected model")
    template_lines = arguments.template.read_text(encoding="utf-8").splitlines()
    if len(template_lines) != 1:
        raise ValueError("MTZ preflight stub template must contain exactly one row")
    template = json.loads(template_lines[0])
    rows: list[str] = []
    for crystal in manifest.crystals:
        record = dict(template)
        record["crystal_id"] = crystal.crystal_id
        record["preflight_id"] = (
            "preflight_stub_"
            + hashlib.sha256(crystal.crystal_id.encode("utf-8")).hexdigest()
        )
        rows.append(canonical_json_text(record))
    arguments.output.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
