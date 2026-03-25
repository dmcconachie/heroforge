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
from heroforge.engine.magic_items import (
    MagicItemRegistry,
)
from heroforge.rules.loader import MagicItemLoader

RULES_DIR = Path(__file__).parent.parent / "src" / "heroforge" / "rules"


def _load_items() -> tuple[MagicItemRegistry, BuffRegistry]:
    item_reg = MagicItemRegistry()
    buff_reg = BuffRegistry()
    MagicItemLoader(RULES_DIR).load(
        item_reg,
        buff_reg,
        "core/magic_items.yaml",
    )
    return item_reg, buff_reg


class TestMagicItemsLoader:
    def test_loads_successfully(self) -> None:
        item_reg, buff_reg = _load_items()
        assert len(item_reg) >= 50

    def test_dual_registration(self) -> None:
        """Items appear in both registries."""
        item_reg, buff_reg = _load_items()
        ring = item_reg.get("Ring of Protection +2")
        assert ring is not None
        buff = buff_reg.get("Ring of Protection +2")
        assert buff is not None

    def test_ring_of_protection(self) -> None:
        item_reg, buff_reg = _load_items()
        r = buff_reg.get("Ring of Protection +2")
        assert r is not None
        targets = {e.target for e in r.effects}
        assert "ac" in targets

    def test_cloak_of_resistance(self) -> None:
        item_reg, buff_reg = _load_items()
        c = buff_reg.get("Cloak of Resistance +3")
        assert c is not None
        targets = {e.target for e in c.effects}
        assert "fort_save" in targets
        assert "ref_save" in targets
        assert "will_save" in targets

    def test_belt_of_giant_strength(self) -> None:
        item_reg, buff_reg = _load_items()
        b = buff_reg.get("Belt of Giant Strength +4")
        assert b is not None
        assert any(e.target == "str_score" for e in b.effects)

    def test_item_definition_fields(self) -> None:
        """MagicItemDefinition has correct fields."""
        item_reg, _ = _load_items()
        ring = item_reg.get("Ring of Protection +2")
        assert ring is not None
        assert ring.source_book == "SRD"
        assert len(ring.effects) > 0

    def test_buff_category_is_item(self) -> None:
        """Buff entries have ITEM category."""
        from heroforge.engine.effects import (
            BuffCategory,
        )

        _, buff_reg = _load_items()
        ring = buff_reg.get("Ring of Protection +2")
        assert ring is not None
        assert ring.category == BuffCategory.ITEM


class TestMagicItemEffects:
    def test_ring_of_protection_ac(self) -> None:
        _, buff_reg = _load_items()
        c = Character()
        base_ac = c.get("ac")
        ring = buff_reg.get("Ring of Protection +2")
        apply_buff(ring, c)
        assert c.get("ac") == base_ac + 2

    def test_ability_enhancement(self) -> None:
        _, buff_reg = _load_items()
        c = Character()
        c.set_ability_score("str", 14)
        belt = buff_reg.get("Belt of Giant Strength +4")
        apply_buff(belt, c)
        assert c.get("str_score") == 18
