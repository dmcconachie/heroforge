"""
tests/conftest.py
------------------
Shared fixtures and configuration for the test suite.
"""

import os

# Force offscreen rendering before any Qt import
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Session-scoped QApplication — one per process."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app
