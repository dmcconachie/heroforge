"""
tests/integration/test_full_builds.py
------------------------------------
Parametrized golden-file tests for character sheets.

Each .char.yaml in the configured directories is loaded
through the engine, and the resulting sheet is compared
against the matching .expected.yaml file.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from heroforge.engine.sheet import extract_sheet
from heroforge.ui.app_state import AppState

_INTEGRATION_DIR = Path(__file__).parent

CHAR_DIRS: list[Path] = [
    _INTEGRATION_DIR / "base_characters",
    _INTEGRATION_DIR / "custom_characters",
]


def _discover() -> list[tuple[str, Path]]:
    """Find all .char.yaml stems across CHAR_DIRS."""
    builds: list[tuple[str, Path]] = []
    for d in CHAR_DIRS:
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.char.yaml")):
            stem = p.name.removesuffix(".char.yaml")
            builds.append((stem, d))
    return builds


_BUILDS = _discover()
_IDS = [name for name, _ in _BUILDS]


@pytest.mark.parametrize("build,char_dir", _BUILDS, ids=_IDS)
def test_character(
    build: str,
    char_dir: Path,
    app_state: AppState,
) -> None:
    """
    Load a character, extract the sheet, compare
    against the expected golden file.
    """
    char_path = char_dir / f"{build}.char.yaml"
    expected_path = char_dir / f"{build}.expected.yaml"

    if not expected_path.exists():
        pytest.fail(f"No expected file: {expected_path.name}")

    actual = extract_sheet(char_path, app_state)

    with open(expected_path) as f:
        expected = yaml.safe_load(f)

    assert expected == actual
