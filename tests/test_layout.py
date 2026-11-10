import importlib


def test_packages_import():
    for name in ("ingestion", "backend.app.law", "evals.search.hybrid"):
        importlib.import_module(name)
