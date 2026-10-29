import importlib


def test_packages_import():
    for name in ("ingestion", "backend.app.retrieval"):
        importlib.import_module(name)
