"""Give each pytest case its own Nextflow history and log namespace."""

import pytest


@pytest.fixture(autouse=True)
def isolated_nextflow_state(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep resume local to one test, including under pytest-xdist."""

    # Keep runtime files outside each test's otherwise empty tmp_path fixture.
    root = tmp_path_factory.mktemp("nextflow-state")
    monkeypatch.setenv("NXF_CACHE_DIR", str(root / "cache"))
    monkeypatch.setenv("NXF_LOG_FILE", str(root / "nextflow.log"))
