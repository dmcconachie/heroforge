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

SLOT_FILES = [
    "head",
    "face",
    "throat",
    "shoulders",
    "body",
    "torso",
    "arms",
    "hands",
    "ring",
    "waist",
    "feet",
    "slotless",
    "tool",
    "consumable",
]


def _load_items() -> tuple[MagicItemRegistry, BuffRegistry]:
    item_reg = MagicItemRegistry()
    buff_reg = BuffRegistry()
    loader = MagicItemLoader(RULES_DIR)
    for slot_file in SLOT_FILES:
        loader.load(
            item_reg,
            buff_reg,
            f"core/magic_items/{slot_file}.yaml",
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


class TestMagicItemsSort:
    """
    Within each slot yaml file, every item's
    ``slot`` field must match the filename and
    entries must be sorted alphabetically.
    """

    def _file_items(self, slot_file: str) -> list[tuple[str, dict]]:
        import yaml

        path = RULES_DIR / "core" / "magic_items" / f"{slot_file}.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)
        if data is None:
            return []
        return list(data.items())

    def test_all_have_slot(self) -> None:
        for slot_file in SLOT_FILES:
            for name, item in self._file_items(slot_file):
                assert "slot" in item, f"{name!r} missing slot"

    def test_slot_matches_filename(self) -> None:
        for slot_file in SLOT_FILES:
            for name, item in self._file_items(slot_file):
                assert item["slot"] == slot_file, (
                    f"{name!r} in {slot_file}.yaml has slot {item['slot']!r}"
                )

    def test_sorted_alphabetically(self) -> None:
        for slot_file in SLOT_FILES:
            names = [n for n, _ in self._file_items(slot_file)]
            sorted_names = sorted(names, key=str.lower)
            assert names == sorted_names, (
                f"{slot_file}.yaml not sorted: {names} != {sorted_names}"
            )
