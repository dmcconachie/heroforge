"""
tests/integration/test_full_builds.py
------------------------------------
Parametrized golden-file tests for character sheets.

Each .char.yaml in the configured directories is fed
through the `charsheet` CLI, and its stdout is compared
against the matching .expected.yaml file as raw text.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_INTEGRATION_DIR = Path(__file__).parent

CHAR_DIRS: list[Path] = [
    _INTEGRATION_DIR / "base_characters",
    _INTEGRATION_DIR / "custom_characters",
]

# Builds that need additional rules content (splatbook
# feats/classes) before they can run. Remove from this
# set as the rules catch up.
_SKIP_BUILDS: frozenset[str] = frozenset({"drufus"})


def _discover() -> list[tuple[str, Path]]:
    """Find runnable .char.yaml stems across CHAR_DIRS."""
    builds: list[tuple[str, Path]] = []
    for d in CHAR_DIRS:
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.char.yaml")):
            stem = p.name.removesuffix(".char.yaml")
            if stem in _SKIP_BUILDS:
                continue
            builds.append((stem, d))
    return builds


_BUILDS = _discover()
_IDS = [name for name, _ in _BUILDS]


@pytest.mark.parametrize("build,char_dir", _BUILDS, ids=_IDS)
def test_character(build: str, char_dir: Path) -> None:
    """
    Run the `charsheet` CLI on a build and diff its
    stdout against the matching .expected.yaml file.
    """
    char_path = char_dir / f"{build}.char.yaml"
    expected_path = char_dir / f"{build}.expected.yaml"

    if not expected_path.exists():
        pytest.fail(f"No expected file: {expected_path.name}")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "heroforge.engine.sheet",
            str(char_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout == expected_path.read_text()
