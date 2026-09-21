"""
tests/test_known_enums.py
--------------------------
Congruence tests: assert that the KnownXxx StrEnums
match the live registries exactly.
"""

from __future__ import annotations

from enum import StrEnum

import pytest

from heroforge.rules.known import (
    KnownArmor,
    KnownBuff,
    KnownClass,
    KnownCondition,
    KnownDeity,
    KnownDomain,
    KnownFeat,
    KnownMagicItem,
    KnownMaterial,
    KnownRace,
    KnownSkill,
    KnownTemplate,
    KnownWeapon,
)
from heroforge.rules.rules import get_rules


def _registry_names(attr: str, method: str) -> set[str]:
    """Extract name set from a registry."""
    reg = getattr(get_rules(), attr)
    items = getattr(reg, method)()
    if items and hasattr(items[0], "name"):
        return {item.name for item in items}
    return set(items)


_CASES = [
    ("races", "all_names", KnownRace),
    ("classes", "all_names", KnownClass),
    ("feats", "all_names", KnownFeat),
    ("skills", "all_skills", KnownSkill),
    ("buffs", "all_names", KnownBuff),
    ("templates", "all_names", KnownTemplate),
    ("armor", "all_entries", KnownArmor),
    ("weapons", "all_weapons", KnownWeapon),
    ("magic_items", "all_items", KnownMagicItem),
    ("materials", "all_materials", KnownMaterial),
    ("domains", "all_domains", KnownDomain),
    ("deities", "all_deities", KnownDeity),
    ("conditions", "all_conditions", KnownCondition),
]

_IDS = [c[0] for c in _CASES]


@pytest.mark.parametrize("reg_attr,method,enum_cls", _CASES, ids=_IDS)
class TestCongruence:
    """Every enum member matches a registry entry and vice versa."""

    def test_no_missing_enum_members(
        self,
        reg_attr: str,
        method: str,
        enum_cls: type[StrEnum],
    ) -> None:
        """Registry entries all in enum."""
        reg_names = _registry_names(reg_attr, method)
        enum_vals = {m.value for m in enum_cls}
        missing = reg_names - enum_vals
        assert not missing, (
            f"Registry entries missing from {enum_cls.__name__}: {missing}"
        )

    def test_no_stale_enum_members(
        self,
        reg_attr: str,
        method: str,
        enum_cls: type[StrEnum],
    ) -> None:
        """Enum members all in registry."""
        reg_names = _registry_names(reg_attr, method)
        enum_vals = {m.value for m in enum_cls}
        stale = enum_vals - reg_names
        assert not stale, f"Stale enum members in {enum_cls.__name__}: {stale}"
