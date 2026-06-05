"""T1 acceptance — the packaging skeleton is real.

Proves two things the rest of M1 stands on:
1. the src-layout editable install resolves ``import config`` and
   ``import ingestion`` (so every later module has a package to live in), and
2. the ``slow`` marker is registered (so the @slow rebuild test in T10 is a
   first-class deselectable marker, not an "unknown marker" warning).
"""

import importlib


def test_config_and_ingestion_importable():
    config = importlib.import_module("config")
    ingestion = importlib.import_module("ingestion")
    assert config.__name__ == "config"
    assert ingestion.__name__ == "ingestion"


def test_slow_marker_registered(pytestconfig):
    markers = pytestconfig.getini("markers")
    assert any(m.split(":", 1)[0] == "slow" for m in markers), (
        "the 'slow' marker must be registered in [tool.pytest.ini_options]"
    )
