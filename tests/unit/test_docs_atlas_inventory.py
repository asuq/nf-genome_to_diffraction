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
    assert module.CURRENT / "documentation.html" in first
    assert module.CURRENT / "developer-view.html" in first
    assert module.CURRENT / "scientist.html" not in first
    assert module.CURRENT / "developer.html" not in first
    assert module.CURRENT / "validation.html" in first
    assert module.CURRENT / "stages/inputs-records.html" in first
    assert module.CURRENT / "stages/report.html" in first
    assert module.CURRENT / "diagrams/scientist-workflow.html" in first
    assert module.CURRENT / "diagrams/developer-architecture.html" in first
    assert module.CURRENT / "manifest.json" in first
    generated = b"\n".join(first.values())
    assert b"/Users/" not in generated
    assert b"/private/tmp/" not in generated
    assert b"/bioinf/" not in generated


def test_html_atlas_has_one_canonical_home_and_internal_developer_view() -> None:
    module = _html_module()
    outputs = module.build_outputs(REPOSITORY)
    index = outputs[module.CURRENT / "index.html"].decode("utf-8")
    scientist = outputs[module.CURRENT / "documentation.html"].decode("utf-8")
    developer = outputs[module.CURRENT / "developer-view.html"].decode("utf-8")

    assert '<meta http-equiv="refresh" content="0;url=documentation.html">' in index
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
    assert '<nav class="atlas-view-switch"' in scientist
    assert '<a href="documentation.html" aria-current="page">Scientist</a>' in scientist
    assert '<a href="developer-view.html#developer">Developer</a>' in scientist
    assert "if (location.hash === '#developer')" in scientist
    assert "history.replaceState(null, '', 'documentation.html#developer')" in developer
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
    assert 'href="scientist.html"' not in generated_html
    assert 'href="developer.html"' not in generated_html


def test_scientist_home_stage_order_and_progressive_disclosure() -> None:
    module = _html_module()
    outputs = module.build_outputs(REPOSITORY)
    scientist = outputs[module.CURRENT / "documentation.html"].decode("utf-8")
    expected = [
        "stages/inputs-records.html",
        "stages/preflight.html",
        "stages/discovery-models.html",
        "stages/rank-mr.html",
        "stages/review-refine-maps.html",
        "stages/composition.html",
        "stages/report.html",
    ]

    positions = [scientist.index(target) for target in expected]
    assert positions == sorted(positions)
    assert "User-provided localisation and molecular-weight evidence" in scientist
    assert "supplies these observations at the beginning" in scientist
    assert "depths four through six remain provisional" in scientist
    assert "Solid green: forward workflow step" in scientist
    assert "Dashed red: reviewed decision, pause, or stop" in scientist
    assert "Dashed purple: evidence influence or repeat/continue" in scientist

    composition = outputs[module.CURRENT / "stages/composition.html"].decode("utf-8")
    assert (
        "<details><summary>Run commands and implementation links</summary>"
        in composition
    )
    assert "phase3-composition-beam-stub" in composition
    assert "Depths 4-6 remain visible but unvalidated" in composition
    assert "How the B-F loop works" in composition
    assert "<strong>A</strong> is the first reviewed component" in composition
    assert "Run Molecular Replacement attempts" in composition
    assert 'class="stage-navigator"' in composition
    assert "data-stage-select" in composition
    assert composition.count('aria-current="step"') == 1
    assert "../documentation.html" in composition

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
    assert b"atlas-docs-drawer" in outputs[module.CURRENT / "documentation.html"]
    assert b"atlas-docs-drawer" in outputs[module.CURRENT / "developer-view.html"]


def test_node_focus_opens_dark_reserved_documentation_panel() -> None:
    module = _html_module()
    outputs = module.build_outputs(REPOSITORY)
    scientist = outputs[module.CURRENT / "documentation.html"].decode("utf-8")
    developer = outputs[module.CURRENT / "developer-view.html"].decode("utf-8")

    for node_id in (
        "inputs",
        "preflight",
        "preflight_checkpoint",
        "discover_prepare",
        "rank_mr",
        "review_refine",
        "component_slots",
        "composition_cycle",
        "report",
        "localisation_weight",
        "paused",
    ):
        assert f'data-atlas-node-doc="{node_id}"' in scientist
    for node_id in (
        "control_plane",
        "public_entrypoints",
        "phase3_entrypoint",
        "nextflow",
        "process_modules",
        "python_services",
        "contracts",
        "external_tools",
        "human_review",
        "evidence_store",
        "publication",
        "validation_plane",
    ):
        assert f'data-atlas-node-doc="{node_id}"' in developer

    assert "node.hasAttribute('data-focus-selected')" in scientist
    assert "showNode(node.dataset.nodeId)" in scientist
    assert ".focus-chip" in scientist
    assert "display: none !important" in scientist
    assert "body { padding-right: 440px; }" in scientist
    assert "@media (max-width: 700px)" in scientist
    assert ".atlas-docs-drawer { width: 100vw; }" in scientist
    assert "overflow-x: clip" in scientist
    assert "forceDark" in scientist

    stage = outputs[module.CURRENT / "stages/preflight.html"].decode("utf-8")
    assert 'data-theme="dark"' in stage
    assert "data-theme-toggle" not in stage
    assert "Preflight Checkpoint" in scientist
    assert "Paused" in stage
    assert "Paused before Molecular Replacement" in scientist


def test_developer_legend_uses_domain_labels() -> None:
    module = _html_module()
    outputs = module.build_outputs(REPOSITORY)
    developer = outputs[module.CURRENT / "developer-view.html"].decode("utf-8")

    assert "Executable / orchestration layer" in developer
    assert "Contract / review gate" in developer
    assert "Evidence / output" in developer
    assert "External runtime" in developer
    assert ">Frontend<" not in developer
    assert ">Cloud service<" not in developer
    assert ">Message bus<" not in developer
