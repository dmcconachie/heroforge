"""
Top-level pytest fixtures.

The rules registry is loaded once per session (~73 YAML files)
and pointer-swapped into the module-level singleton for each
test via ``set_rules`` / ``reset_rules``. Tests should treat
the shared Rules as read-only: mutations leak between tests
because the cached object is shared. Tests needing a custom
ruleset build a fresh ``Rules()`` and call ``set_rules(r)`` —
the autouse teardown's ``reset_rules()`` clears it afterwards.

Loader tests that want to bypass the cached Rules entirely
(e.g. to exercise the loader against a fresh empty registry)
can mark themselves with ``@pytest.mark.no_cached_rules``. The
autouse fixture still ``reset_rules()``-es around them, so
``get_rules()`` inside the test would trigger a fresh load
(almost never what a loader test wants — the marker exists so
the test author controls the situation explicitly).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from heroforge.rules.rules import Rules, reset_rules, set_rules


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "no_cached_rules: skip the autouse install of the "
        "session-cached Rules for this test",
    )


@pytest.fixture(scope="session")
def _cached_rules() -> Rules:
    """Session-scoped Rules; YAML parsed once per session."""
    r = Rules()
    r.load()
    return r


@pytest.fixture(autouse=True)
def _isolated_rules(
    request: pytest.FixtureRequest,
) -> Iterator[None]:
    """
    Around each test: clear the rules singleton, install the
    cached Rules (unless opted out), yield, then clear again so
    no test can leak a set_rules() call to the next."""
    reset_rules()
    if "no_cached_rules" not in request.keywords:
        set_rules(request.getfixturevalue("_cached_rules"))
    yield
    reset_rules()
