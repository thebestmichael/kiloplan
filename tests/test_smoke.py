import importlib

import pytest


@pytest.mark.parametrize("subpackage", ["ingestion", "analytics", "api", "chatbot"])
def test_subpackage_imports(subpackage):
    importlib.import_module(f"kiloplan.{subpackage}")
