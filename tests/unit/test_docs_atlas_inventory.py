from __future__ import annotations

import importlib.util
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
    assert module.CURRENT / "portals/scientist.html" in first
    assert module.CURRENT / "portals/developer.html" in first
    assert module.CURRENT / "portals/validation.html" in first
    assert module.CURRENT / "manifest.json" in first
    generated_html = b"\n".join(
        content for path, content in first.items() if path.suffix == ".html"
    )
    assert b"/Users/" not in generated_html
    assert b"/bioinf/" not in generated_html
