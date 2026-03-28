"""
Fixtures for golden-file integration tests.
"""

from __future__ import annotations

import pytest

from heroforge.ui.app_state import AppState


@pytest.fixture(scope="module")
def app_state() -> AppState:
    """Fully initialised AppState with rules loaded."""
    state = AppState()
    state.load_rules()
    return state
