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


def builds() -> list[tuple[str, Path]]:
    """Yield runnable .char.yaml stems across CHAR_DIRS."""
    results: list[tuple[str, Path]] = []
    for d in CHAR_DIRS:
        for p in sorted(d.glob("*.char.yaml")):
            stem = p.name.removesuffix(".char.yaml")
            results.append((stem, d))
    return results


@pytest.mark.parametrize("build,char_dir", builds())
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
