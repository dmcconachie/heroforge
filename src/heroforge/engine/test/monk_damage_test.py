"""
Monk unarmed strike damage: PHB Table 3-10 for a Medium monk
and Table 3-11 for a Small or Large one, driven by the
effective_monk_level_damage derived pool so the Monk's Belt
can raise it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from heroforge.engine.character import Character, CharacterLevel
from heroforge.engine.enums import Size
from heroforge.engine.equipment import equip_item
from heroforge.engine.persistence import load_character
from heroforge.engine.sheet import gather_sheet
from heroforge.engine.weapons import (
    monk_unarmed_damage,
    register_weapons_on_character,
)
from heroforge.rules.rules import get_rules


def _monk(level: int, size: str = "Medium", cls: str = "Monk") -> Character:
    c = Character(name="Grasshopper")
    for ab in ("str", "dex", "con", "int", "wis", "cha"):
        c.set_ability_score(ab, 12)
    c.levels = [
        CharacterLevel(character_level=i + 1, class_name=cls, hp_roll=8)
        for i in range(level)
    ]
    c._race_size = size
    c._invalidate_class_stats()
    c.equipment["weapons"] = [{"base": "Unarmed Strike"}]
    register_weapons_on_character(c)
    return c


def _dice(c: Character) -> str:
    return gather_sheet(c, None).equipment.weapons[0].damage_dice


class TestTheTable:
    """PHB Table 3-10 (Medium) and Table 3-11 (Small/Large)."""

    @pytest.mark.parametrize(
        ("level", "small", "medium", "large"),
        [
            (1, "1d4", "1d6", "1d8"),
            (3, "1d4", "1d6", "1d8"),
            (4, "1d6", "1d8", "2d6"),
            (7, "1d6", "1d8", "2d6"),
            (8, "1d8", "1d10", "2d8"),
            (11, "1d8", "1d10", "2d8"),
            (12, "1d10", "2d6", "3d6"),
            (15, "1d10", "2d6", "3d6"),
            (16, "2d6", "2d8", "3d8"),
            (19, "2d6", "2d8", "3d8"),
            (20, "2d8", "2d10", "4d8"),
        ],
    )
    def test_rows(
        self, level: int, small: str, medium: str, large: str
    ) -> None:
        assert monk_unarmed_damage(level, Size.SMALL) == small
        assert monk_unarmed_damage(level, Size.MEDIUM) == medium
        assert monk_unarmed_damage(level, Size.LARGE) == large

    def test_beyond_twenty_holds_at_the_last_row(self) -> None:
        assert monk_unarmed_damage(25, Size.MEDIUM) == "2d10"

    def test_no_effective_levels_is_not_a_monk(self) -> None:
        assert monk_unarmed_damage(0, Size.MEDIUM) is None

    def test_an_unmodelled_size_raises(self) -> None:
        with pytest.raises(ValueError):
            monk_unarmed_damage(5, Size.HUGE)


class TestOnTheSheet:
    def test_a_first_level_monk(self) -> None:
        assert _dice(_monk(1)) == "1d6"

    def test_a_twelfth_level_monk(self) -> None:
        assert _dice(_monk(12)) == "2d6"

    def test_a_halfling_monk_uses_the_small_column(self) -> None:
        assert _dice(_monk(12, size="Small")) == "1d10"

    def test_a_non_monk_gets_the_plain_weapon(self) -> None:
        # Unarmed Strike is 1d3 for anyone else.
        assert _dice(_monk(12, cls="Fighter")) == "1d3"

    def test_a_small_non_monk_still_resizes_normally(self) -> None:
        assert _dice(_monk(12, size="Small", cls="Fighter")) == "1d2"


class TestMonksBelt:
    """
    DMG p. 248: unarmed damage as a monk of five levels
    higher; a non-monk counts as a 5th-level monk."""

    def _belted(self, c: Character) -> Character:
        item = get_rules().magic_items.get("Monk's Belt")
        assert item is not None
        equip_item(c, item)
        register_weapons_on_character(c)
        return c

    def test_it_adds_five_levels_for_a_monk(self) -> None:
        c = self._belted(_monk(3))
        # 3rd + 5 = 8th, which is 1d10.
        assert _dice(c) == "1d10"

    def test_a_non_monk_becomes_a_fifth_level_monk(self) -> None:
        c = self._belted(_monk(12, cls="Fighter"))
        assert _dice(c) == "1d8"

    def test_it_still_raises_the_ac_pool(self) -> None:
        c = self._belted(_monk(3))
        assert c.get("effective_monk_level_ac") == 8


class TestItPersists:
    CHAR = """
identity:
  name: Belted
  race: Human
  alignment: lawful_neutral
ability_scores: {str: 12, dex: 12, con: 12, int: 12, wis: 12, cha: 12}
levels:
  - {level: 1, class: Monk, hp_roll: 8}
  - {level: 2, class: Monk, hp_roll: 5}
  - {level: 3, class: Monk, hp_roll: 5}
equipment:
  worn:
    - Monk's Belt
  weapons:
    - base: Unarmed Strike
"""

    def test_damage_survives_a_load(self, tmp_path: Path) -> None:
        path = tmp_path / "m.char.yaml"
        path.write_text(self.CHAR)
        assert _dice(load_character(path, None)) == "1d10"
