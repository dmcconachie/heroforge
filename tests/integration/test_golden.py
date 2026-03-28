"""
tests/integration/test_golden.py
---------------------------------
Parametrized golden-file tests for character sheets.

Each .char.yaml in characters/ is loaded through the
engine, and the resulting sheet is compared against the
matching .expected.yaml file.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from heroforge.engine.sheet import extract_sheet
from heroforge.ui.app_state import AppState

CHAR_DIR = Path(__file__).parent / "characters"


def _discover() -> list[str]:
    """Find all .char.yaml stems."""
    return sorted(
        p.name.removesuffix(".char.yaml") for p in CHAR_DIR.glob("*.char.yaml")
    )


def _compare(
    actual: dict,
    expected: dict,
    path: str = "",
) -> list[str]:
    """
    Recursively compare actual vs expected dicts.

    Only checks keys present in expected (allows
    incremental expected file construction). Returns
    list of mismatch descriptions.
    """
    errors: list[str] = []
    for key, exp_val in expected.items():
        full = f"{path}.{key}" if path else str(key)
        if key not in actual:
            errors.append(f"{full}: missing in actual")
            continue
        act_val = actual[key]
        if isinstance(exp_val, dict):
            if not isinstance(act_val, dict):
                errors.append(
                    f"{full}: expected dict, got {type(act_val).__name__}"
                )
            else:
                errors.extend(_compare(act_val, exp_val, full))
        elif isinstance(exp_val, list):
            if not isinstance(act_val, list):
                errors.append(
                    f"{full}: expected list, got {type(act_val).__name__}"
                )
            elif act_val != exp_val:
                errors.append(f"{full}: expected {exp_val!r}, got {act_val!r}")
        elif act_val != exp_val:
            errors.append(f"{full}: expected {exp_val!r}, got {act_val!r}")
    return errors


@pytest.mark.parametrize("build", _discover())
def test_golden(
    build: str,
    app_state: AppState,
) -> None:
    """
    Load a character, extract the sheet, compare
    against the expected golden file.
    """
    char_path = CHAR_DIR / f"{build}.char.yaml"
    expected_path = CHAR_DIR / f"{build}.expected.yaml"

    if not expected_path.exists():
        pytest.skip(f"No expected file: {expected_path.name}")

    actual = extract_sheet(char_path, app_state)

    with open(expected_path) as f:
        expected = yaml.safe_load(f)

    errors = _compare(actual, expected)
    if errors:
        msg = f"\n{build}: {len(errors)} mismatch(es):\n"
        msg += "\n".join(f"  {e}" for e in errors)
        pytest.fail(msg)
