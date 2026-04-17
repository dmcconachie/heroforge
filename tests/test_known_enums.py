"""
tests/test_known_enums.py
--------------------------
Congruence tests: assert that the KnownXxx StrEnums
match the live registries exactly.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from heroforge.ui.app_state import AppState

from heroforge.rules.known import (
    KnownArmor,
    KnownBuff,
    KnownClass,
    KnownCondition,
    KnownDomain,
    KnownFeat,
    KnownMagicItem,
    KnownMaterial,
    KnownRace,
    KnownSkill,
    KnownTemplate,
    KnownWeapon,
)


@pytest.fixture(scope="module")
def app_state() -> AppState:
    from heroforge.ui.app_state import AppState

    state = AppState()
    state.load_rules()
    return state


def _registry_names(app_state: AppState, attr: str, method: str) -> set[str]:
    """Extract name set from a registry."""
    reg = getattr(app_state, attr)
    items = getattr(reg, method)()
    if items and hasattr(items[0], "name"):
        return {item.name for item in items}
    return set(items)


_CASES = [
    ("race_registry", "all_names", KnownRace),
    ("class_registry", "all_names", KnownClass),
    ("feat_registry", "all_names", KnownFeat),
    ("skill_registry", "all_skills", KnownSkill),
    ("buff_registry", "all_names", KnownBuff),
    ("template_registry", "all_names", KnownTemplate),
    ("armor_registry", "all_entries", KnownArmor),
    ("weapon_registry", "all_weapons", KnownWeapon),
    ("magic_item_registry", "all_items", KnownMagicItem),
    ("material_registry", "all_materials", KnownMaterial),
    ("domain_registry", "all_domains", KnownDomain),
    ("condition_registry", "all_conditions", KnownCondition),
]

_IDS = [c[0] for c in _CASES]


@pytest.mark.parametrize("reg_attr,method,enum_cls", _CASES, ids=_IDS)
class TestCongruence:
    """Every enum member matches a registry entry and vice versa."""

    def test_no_missing_enum_members(
        self,
        app_state: AppState,
        reg_attr: str,
        method: str,
        enum_cls: type[StrEnum],
    ) -> None:
        """Registry entries all in enum."""
        reg_names = _registry_names(app_state, reg_attr, method)
        enum_vals = {m.value for m in enum_cls}
        missing = reg_names - enum_vals
        assert not missing, (
            f"Registry entries missing from {enum_cls.__name__}: {missing}"
        )

    def test_no_stale_enum_members(
        self,
        app_state: AppState,
        reg_attr: str,
        method: str,
        enum_cls: type[StrEnum],
    ) -> None:
        """Enum members all in registry."""
        reg_names = _registry_names(app_state, reg_attr, method)
        enum_vals = {m.value for m in enum_cls}
        stale = enum_vals - reg_names
        assert not stale, f"Stale enum members in {enum_cls.__name__}: {stale}"
