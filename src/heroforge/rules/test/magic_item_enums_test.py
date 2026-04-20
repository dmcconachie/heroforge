"""
tests/test_magic_item_enums.py
-------------------------------
Contract test for the magic-item StrEnum generator.

Pins the invariant that the committed per-slot magic-item enum
modules (rules/core/magic_items/*.py), the slot aggregator
(rules/core/magic_items/__init__.py), and the custom enum
(rules/custom/magic_items.py) match what ``_gen_magic_item_enums``
would regenerate from their YAML sources right now. If this
test fails, run ``uv run check-magic-items --fix`` and commit
the result.
"""

from __future__ import annotations

import os

from heroforge.rules._gen_magic_item_enums import main as check_magic_items


def test_generator_is_idempotent() -> None:
    """
    Running _gen_magic_item_enums.main() against the committed
    YAML must reproduce the committed .py files byte-for-byte.
    """
    assert check_magic_items(argv=[]) == os.EX_OK, (
        "magic-item enums are out of sync with YAML — "
        "run `uv run check-magic-items --fix`"
    )
