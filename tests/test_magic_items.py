"""
Tests for magic items YAML data.
"""

from __future__ import annotations

from pathlib import Path

from heroforge.engine.character import Character
from heroforge.engine.effects import (
    BuffRegistry,
    apply_buff,
)
from heroforge.rules.loader import SpellsLoader

RULES_DIR = Path(__file__).parent.parent / "src" / "heroforge" / "rules"


def _load_items() -> BuffRegistry:
    reg = BuffRegistry()
    SpellsLoader(RULES_DIR).load(reg, "core/magic_items.yaml")
    return reg


class TestMagicItemsLoader:
    def test_loads_successfully(self) -> None:
        reg = _load_items()
        assert len(reg._defs) >= 50

    def test_ring_of_protection(self) -> None:
        reg = _load_items()
        r = reg.get("Ring of Protection +2")
        assert r is not None
        targets = {e.target for e in r.effects}
        assert "ac" in targets

    def test_cloak_of_resistance(self) -> None:
        reg = _load_items()
        c = reg.get("Cloak of Resistance +3")
        assert c is not None
        targets = {e.target for e in c.effects}
        assert "fort_save" in targets
        assert "ref_save" in targets
        assert "will_save" in targets

    def test_belt_of_giant_strength(self) -> None:
        reg = _load_items()
        b = reg.get("Belt of Giant Strength +4")
        assert b is not None
        assert any(e.target == "str_score" for e in b.effects)


class TestMagicItemEffects:
    def test_ring_of_protection_ac(self) -> None:
        reg = _load_items()
        c = Character()
        base_ac = c.get("ac")
        ring = reg.get("Ring of Protection +2")
        apply_buff(ring, c)
        assert c.get("ac") == base_ac + 2

    def test_ability_enhancement(self) -> None:
        reg = _load_items()
        c = Character()
        c.set_ability_score("str", 14)
        belt = reg.get("Belt of Giant Strength +4")
        apply_buff(belt, c)
        assert c.get("str_score") == 18
