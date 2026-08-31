from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

REPOSITORY = Path(__file__).parents[2]
SCRIPT = REPOSITORY / "tools/docs_atlas/build_inventory.py"
HTML_SCRIPT = REPOSITORY / "tools/docs_atlas/build_html.py"


def _module() -> ModuleType:
    specification = importlib.util.spec_from_file_location(
        "docs_atlas_inventory", SCRIPT
    )
    assert specification is not None
    assert specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def _html_module() -> ModuleType:
    sys.path.insert(0, str(HTML_SCRIPT.parent))
    specification = importlib.util.spec_from_file_location(
        "docs_atlas_html", HTML_SCRIPT
    )
    assert specification is not None
    assert specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def test_inventory_covers_all_executable_surface_kinds() -> None:
    document = _module().build_inventory(REPOSITORY)

    assert document["schema_version"] == "1.0"
    assert document["inventory_id"].startswith("atlasinv_")
    assert "main.nf" in document["root_nextflow_entrypoints"]
    assert any(
        item["path"] == "src/genome_to_diffraction/cli.py"
        for item in document["python_modules"]
    )
    assert any(
        declaration["kind"] == "process"
        for item in document["nextflow_files"]
        for declaration in item["declarations"]
    )
    assert any(item["functions"] for item in document["shell_files"])
    assert document["schemas"]
    assert document["project_scripts"]


def test_inventory_is_byte_deterministic() -> None:
    module = _module()
    first = module._json_bytes(module.build_inventory(REPOSITORY))
    second = module._json_bytes(module.build_inventory(REPOSITORY))

    assert first == second


def test_html_atlas_is_deterministic_and_private_path_free() -> None:
    module = _html_module()
    first = module.build_outputs(REPOSITORY)
    second = module.build_outputs(REPOSITORY)

    assert first == second
    assert module.CURRENT / "index.html" in first
    assert module.CURRENT / "scientist.html" in first
    assert module.CURRENT / "developer.html" in first
    assert module.CURRENT / "validation.html" in first
    assert module.CURRENT / "stages/authorities.html" in first
    assert module.CURRENT / "stages/report.html" in first
    assert module.CURRENT / "diagrams/scientist-workflow.html" in first
    assert module.CURRENT / "diagrams/developer-architecture.html" in first
    assert module.CURRENT / "manifest.json" in first
    generated = b"\n".join(first.values())
    assert b"/Users/" not in generated
    assert b"/private/tmp/" not in generated
    assert b"/bioinf/" not in generated


def test_html_atlas_surfaces_two_audience_homes_and_keeps_index_internal() -> None:
    module = _html_module()
    outputs = module.build_outputs(REPOSITORY)
    index = outputs[module.CURRENT / "index.html"].decode("utf-8")
    scientist = outputs[module.CURRENT / "scientist.html"].decode("utf-8")
    developer = outputs[module.CURRENT / "developer.html"].decode("utf-8")

    assert '<meta http-equiv="refresh" content="0;url=scientist.html">' in index
    assert "<body></body>" in index
    assert "<nav" not in index
    assert "<iframe" not in scientist
    assert "<iframe" not in developer
    assert 'class="toolbar"' in scientist
    assert 'class="toolbar"' in developer
    assert 'id="archify-guided-views-data"' in scientist
    assert 'id="archify-guided-views-data"' in developer
    assert 'id="btn-present"' in scientist
    assert 'id="btn-export"' in developer
    assert 'id="atlas-docs-drawer"' in scientist
    assert 'id="atlas-docs-drawer"' in developer
    assert "phase3_application.nf" in developer
    assert "sole public <code>main.nf</code>" in developer
    assert "prepare_databases.nf" in developer
    assert "Validation &amp; Evidence" in scientist
    assert "Validation &amp; Evidence" in developer

    generated_html = "\n".join(
        content.decode("utf-8")
        for path, content in outputs.items()
        if path.suffix == ".html"
    )
    assert re.search(r'href=["\'][^"\']*index\.html', generated_html) is None


def test_scientist_home_stage_order_and_progressive_disclosure() -> None:
    module = _html_module()
    outputs = module.build_outputs(REPOSITORY)
    scientist = outputs[module.CURRENT / "scientist.html"].decode("utf-8")
    expected = [
        "stages/authorities.html",
        "stages/preflight.html",
        "stages/discovery-models.html",
        "stages/rank-mr.html",
        "stages/review-refine-maps.html",
        "stages/composition.html",
        "stages/report.html",
    ]

    positions = [scientist.index(target) for target in expected]
    assert positions == sorted(positions)
    assert "Cross-cutting localisation and gel evidence" in scientist
    assert "depths four through six remain provisional" in scientist

    composition = outputs[module.CURRENT / "stages/composition.html"].decode("utf-8")
    assert (
        "<details><summary>Operator commands and implementation links</summary>"
        in composition
    )
    assert "phase3-composition-beam-stub" in composition
    assert "Depths 4-6 remain visible but unvalidated" in composition

    module_pages = [
        content.decode("utf-8")
        for path, content in outputs.items()
        if path.is_relative_to(module.CURRENT / "modules") and path.suffix == ".html"
    ]
    assert module_pages
    assert any('<details class="symbol"' in page for page in module_pages)
    assert all("data-atlas-search" in page for page in module_pages)


def test_surfaced_viewers_derive_from_unchanged_frozen_archify_artifacts() -> None:
    module = _html_module()
    outputs = module.build_outputs(REPOSITORY)
    scientist_base_path = module.CURRENT / "diagrams/scientist-workflow.html"
    developer_base_path = module.CURRENT / "diagrams/developer-architecture.html"
    scientist_base = (REPOSITORY / scientist_base_path).read_bytes()
    developer_base = (REPOSITORY / developer_base_path).read_bytes()

    assert outputs[scientist_base_path] == scientist_base
    assert outputs[developer_base_path] == developer_base
    assert b"atlas-docs-drawer" not in scientist_base
    assert b"atlas-docs-drawer" not in developer_base
    assert b"atlas-docs-drawer" in outputs[module.CURRENT / "scientist.html"]
    assert b"atlas-docs-drawer" in outputs[module.CURRENT / "developer.html"]
