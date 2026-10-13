"""Pytest konfiguracija za HA testni harness (tests/test_integration.py).

Harness se učitava samo ako je instaliran (vidi README, Razvoj):
    .venv-ha/bin/pytest tests/test_integration.py
"""

from __future__ import annotations

import importlib.util

import pytest

if importlib.util.find_spec("pytest_homeassistant_custom_component") is not None:
    pytest_plugins = ["pytest_homeassistant_custom_component"]

    @pytest.fixture(autouse=True)
    def auto_enable_custom_integrations(enable_custom_integrations):
        """Dozvoli HA-u da učita custom_components/ iz repozitorija."""
        yield
