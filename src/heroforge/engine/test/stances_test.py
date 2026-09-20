"""
Full-attack stances.

Two-handed, two-weapon fighting, flurry of blows and Rapid
Shot are all the same shape: a choice the character makes for
one full attack, about one weapon. None of them follows from
owning a feat or a weapon, so all four are declared on the
weapon slot and none is inferred.

    weapons:
      - base: Greatsword
        stances: [two_handed]
      - base: Longbow
        stances: [rapid_shot]
      - base: Unarmed Strike
        stances: [flurry]
      - base: Dagger
        stances: [primary]
"""

from __future__ import annotations

from pathlib import Path

import pytest

from heroforge.engine.character import Character, CharacterLevel
from heroforge.engine.persistence import load_character
from heroforge.engine.sheet import gather_sheet
from heroforge.engine.weapons import (
    STANCES,
    register_weapons_on_character,
    strength_damage_adjust,
)


def _char(
    cls: str, level: int, *weapons: dict, strength: int = 16
) -> Character:
    c = Character(name="Stancer")
    for ab in ("str", "dex", "con", "int", "wis", "cha"):
        c.set_ability_score(ab, 10)
    c.set_ability_score("str", strength)
    c.set_ability_score("dex", 14)
    c.levels = [
        CharacterLevel(character_level=i + 1, class_name=cls, hp_roll=8)
        for i in range(level)
    ]
    c._invalidate_class_stats()
    c.equipment["weapons"] = [dict(w) for w in weapons]
    register_weapons_on_character(c)
    return c


def _weapons(c: Character) -> list:
    return gather_sheet(c, None).equipment.weapons


class TestTheVocabulary:
    def test_it_is_closed(self) -> None:
        assert (
            frozenset(
                {"two_handed", "primary", "off_hand", "flurry", "rapid_shot"}
            )
            == STANCES
        )


class TestTwoHanded:
    """
    PHB p. 113: 1-1/2 times the Strength bonus with a
    two-handed weapon, or a one-handed weapon wielded in two
    hands. A light weapon gains nothing from two hands.
    """

    def test_a_two_handed_weapon_gets_it_without_asking(self) -> None:
        """Two hands are required, so it is not a choice."""
        c = _char("Fighter", 5, {"base": "Greatsword"})
        assert strength_damage_adjust(c, c.equipment["weapons"][0]) == 1

    def test_a_one_handed_weapon_has_to_ask(self) -> None:
        one = _char("Fighter", 5, {"base": "Longsword"})
        both = _char(
            "Fighter", 5, {"base": "Longsword", "stances": ["two_handed"]}
        )
        assert strength_damage_adjust(one, one.equipment["weapons"][0]) == 0
        assert strength_damage_adjust(both, both.equipment["weapons"][0]) == 1

    def test_a_light_weapon_gains_nothing(self) -> None:
        c = _char("Fighter", 5, {"base": "Dagger", "stances": ["two_handed"]})
        assert strength_damage_adjust(c, c.equipment["weapons"][0]) == 0

    def test_it_reaches_the_damage_line(self) -> None:
        # Strength 16 is +3; one and a half of that is 4.
        c = _char("Fighter", 5, {"base": "Greatsword"})
        assert _weapons(c)[0].damage.total == 4

    def test_the_stance_is_named(self) -> None:
        c = _char(
            "Fighter", 5, {"base": "Longsword", "stances": ["two_handed"]}
        )
        assert "Two-Handed" in _weapons(c)[0].name


class TestRapidShotIsAskedFor:
    """
    Rapid Shot needs the full attack action, so holding the
    feat is not the same as using it.
    """

    def _archer(self, *stances: str) -> Character:
        # 5th level: base attack +5, so one iterative before
        # Rapid Shot adds its own.
        c = _char(
            "Fighter",
            5,
            {"base": "Longbow", "stances": list(stances)},
        )
        c.add_feat("Point Blank Shot", level=1, source="")
        c.add_feat("Rapid Shot", level=1, source="")
        register_weapons_on_character(c)
        return c

    def test_the_feat_alone_does_nothing(self) -> None:
        w = _weapons(self._archer())[0]
        assert w.attack_iteratives == [w.attack.total]
        assert "rapid_shot" not in w.attack.typed

    def test_asking_for_it_adds_the_attack_and_the_penalty(self) -> None:
        w = _weapons(self._archer("rapid_shot"))[0]
        assert len(w.attack_iteratives) == 2
        assert w.attack.typed["rapid_shot"] == -2

    def test_it_is_named(self) -> None:
        assert "Rapid Shot" in _weapons(self._archer("rapid_shot"))[0].name


class TestTwoWeaponFighting:
    def _pair(self) -> Character:
        return _char(
            "Fighter",
            6,
            {"base": "Short Sword", "stances": ["primary"]},
            {"base": "Dagger", "stances": ["off_hand"]},
        )

    def test_the_off_hand_gets_half_strength(self) -> None:
        c = self._pair()
        assert strength_damage_adjust(c, c.equipment["weapons"][1]) == -2

    def test_both_are_named(self) -> None:
        names = [w.name for w in _weapons(self._pair())]
        assert "TWF: Primary" in names[0]
        assert "TWF: Off-hand" in names[1]


class TestIncompatibleStances:
    HEAD = """
identity:
  name: Confused
  race: Human
  alignment: neutral
ability_scores:
  str: 16
  dex: 14
  con: 10
  int: 10
  wis: 10
  cha: 10
levels:
  - level: 1
    class: Fighter
    hp_roll: 10
equipment:
  weapons:
    - base: WEAPON
      stances: STANCES
"""

    def _load(self, tmp_path: Path, weapon: str, stances: str) -> None:
        path = tmp_path / "c.char.yaml"
        body = self.HEAD.replace("WEAPON", weapon).replace("STANCES", stances)
        path.write_text(body)
        load_character(path, None)

    def test_two_handed_and_off_hand_conflict(self, tmp_path: Path) -> None:
        with pytest.raises(Exception, match="two_handed"):
            self._load(tmp_path, "Longsword", "[two_handed, off_hand]")

    def test_primary_and_off_hand_conflict(self, tmp_path: Path) -> None:
        with pytest.raises(Exception, match="off_hand"):
            self._load(tmp_path, "Longsword", "[primary, off_hand]")

    def test_an_unknown_stance_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(Exception, match="nonsense"):
            self._load(tmp_path, "Longsword", "[nonsense]")

    def test_rapid_shot_without_the_feat_is_refused(
        self, tmp_path: Path
    ) -> None:
        with pytest.raises(Exception, match="Rapid Shot"):
            self._load(tmp_path, "Longbow", "[rapid_shot]")

    def test_rapid_shot_on_a_melee_weapon_is_refused(
        self, tmp_path: Path
    ) -> None:
        with pytest.raises(Exception, match="rapid_shot"):
            self._load(tmp_path, "Longsword", "[rapid_shot]")
