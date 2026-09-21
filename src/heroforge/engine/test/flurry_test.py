"""
Flurry of blows.

Like two-weapon fighting, a flurry is a choice made per full
attack rather than a property of the monk, so the weapon slot
declares it. Unlike Rapid Shot, which follows from holding
the feat, flurry has to be asked for.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from heroforge.engine.character import Character, CharacterLevel
from heroforge.engine.enums import Ability
from heroforge.engine.equipment import equip_armor
from heroforge.engine.persistence import load_character
from heroforge.engine.sheet import gather_sheet
from heroforge.engine.weapons import (
    flurry_applies,
    flurry_extra_attacks,
    flurry_penalty,
    register_weapons_on_character,
)
from heroforge.rules.rules import get_rules


def _monk(
    level: int, weapon: str = "Unarmed Strike", flurry: bool = True
) -> Character:
    c = Character(name="Grasshopper")
    for ab in Ability:
        c.set_ability_score(ab, 10)
    c.levels = [
        CharacterLevel(character_level=i + 1, class_name="Monk", hp_roll=8)
        for i in range(level)
    ]
    c._invalidate_class_stats()
    item: dict[str, object] = {"base": weapon}
    if flurry:
        item["stances"] = ["flurry"]
    c.equipment["weapons"] = [item]
    register_weapons_on_character(c)
    return c


def _sequence(c: Character) -> list[int]:
    return gather_sheet(c).equipment.weapons[0].attack_iteratives


# PHB Table 3-10, the Flurry of Blows Attack Bonus column, for
# a monk with no Strength bonus and an unenchanted weapon.
TABLE = {
    1: [-2, -2],
    2: [-1, -1],
    3: [0, 0],
    4: [1, 1],
    5: [2, 2],
    6: [3, 3],
    7: [4, 4],
    8: [5, 5, 0],
    9: [6, 6, 1],
    10: [7, 7, 2],
    11: [8, 8, 8, 3],
    12: [9, 9, 9, 4],
    13: [9, 9, 9, 4],
    14: [10, 10, 10, 5],
    15: [11, 11, 11, 6, 1],
    16: [12, 12, 12, 7, 2],
    17: [12, 12, 12, 7, 2],
    18: [13, 13, 13, 8, 3],
    19: [14, 14, 14, 9, 4],
    20: [15, 15, 15, 10, 5],
}


class TestTheFlurryColumn:
    @pytest.mark.parametrize("level", sorted(TABLE))
    def test_matches_table_3_10(self, level: int) -> None:
        assert _sequence(_monk(level)) == TABLE[level]


class TestThePenalty:
    @pytest.mark.parametrize(
        ("level", "penalty"),
        [(1, -2), (4, -2), (5, -1), (8, -1), (9, 0), (20, 0)],
    )
    def test_it_eases_with_level(self, level: int, penalty: int) -> None:
        assert flurry_penalty(_monk(level)) == penalty

    def test_it_shows_in_the_breakdown(self) -> None:
        """
        The penalty applies to every attack that round, so it
        belongs on the weapon's line and not only on the
        sequence -- the same reasoning as Rapid Shot's -2.
        """
        weapon = gather_sheet(_monk(1)).equipment.weapons[0]
        assert weapon.attack is not None
        assert weapon.attack.typed["flurry_of_blows"] == -2
        assert weapon.attack.total == weapon.attack_iteratives[0]

    def test_no_penalty_line_from_ninth(self) -> None:
        weapon = gather_sheet(_monk(9)).equipment.weapons[0]
        assert weapon.attack is not None
        assert "flurry_of_blows" not in weapon.attack.typed


class TestGreaterFlurry:
    @pytest.mark.parametrize("level", [1, 5, 10])
    def test_one_extra_attack_before_eleventh(self, level: int) -> None:
        assert flurry_extra_attacks(_monk(level)) == 1

    @pytest.mark.parametrize("level", [11, 20])
    def test_two_from_eleventh(self, level: int) -> None:
        assert flurry_extra_attacks(_monk(level)) == 2


class TestWhenItApplies:
    def test_not_unless_asked_for(self) -> None:
        c = _monk(20, flurry=False)
        assert not flurry_applies(c, c.equipment["weapons"][0])
        # Plain sequence from BAB 15.
        assert _sequence(c) == [15, 10, 5]

    def test_not_while_armoured(self) -> None:
        """PHB: "When unarmored, a monk may strike with a flurry"."""
        c = _monk(20)
        equip_armor(c, get_rules().armor.require("Chain Shirt"))
        register_weapons_on_character(c)
        assert not flurry_applies(c, c.equipment["weapons"][0])

    def test_special_monk_weapons_qualify(self) -> None:
        for weapon in ("Kama", "Nunchaku", "Quarterstaff", "Sai", "Siangham"):
            c = _monk(9, weapon=weapon)
            assert flurry_applies(c, c.equipment["weapons"][0]), weapon

    def test_the_stance_is_named_on_the_weapon(self) -> None:
        name = gather_sheet(_monk(9)).equipment.weapons[0].name
        assert "Flurry of Blows" in name


class TestValidation:
    HEAD = """
identity:
  name: Grasshopper
  race: Human
  alignment: lawful_neutral
ability_scores: {str: 10, dex: 10, con: 10, int: 10, wis: 10, cha: 10}
levels:
"""

    def _load(self, tmp_path: Path, cls: str, weapon: str) -> Character:
        body = (
            self.HEAD
            + "".join(
                f"  - {{level: {i}, class: {cls}, hp_roll: 8}}\n"
                for i in range(1, 10)
            )
            + f"""equipment:
  weapons:
    - base: {weapon}
      stances:
        - flurry
"""
        )
        path = tmp_path / "m.char.yaml"
        path.write_text(body)
        return load_character(path)

    def test_it_round_trips(self, tmp_path: Path) -> None:
        c = self._load(tmp_path, "Monk", "Unarmed Strike")
        assert _sequence(c) == [6, 6, 1]

    def test_a_non_monk_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(Exception, match="flurry"):
            self._load(tmp_path, "Fighter", "Unarmed Strike")

    def test_an_ineligible_weapon_is_refused(self, tmp_path: Path) -> None:
        """
        Flurry works only with unarmed strikes and the special
        monk weapons, so a longsword is a data error.
        """
        with pytest.raises(Exception, match="Longsword"):
            self._load(tmp_path, "Monk", "Longsword")
