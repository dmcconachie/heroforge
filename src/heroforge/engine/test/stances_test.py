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
from heroforge.engine.enums import Ability
from heroforge.engine.persistence import load_character
from heroforge.engine.sheet import gather_sheet
from heroforge.engine.weapons import (
    Stance,
    register_weapons_on_character,
    strength_damage_adjust,
    two_weapon_penalty,
)
from heroforge.rules.rules import get_rules


def _char(
    cls: str, level: int, *weapons: dict, strength: int = 16
) -> Character:
    c = Character(name="Stancer")
    for ab in Ability:
        c.set_ability_score(ab, 10)
    c.set_ability_score(Ability.STR, strength)
    c.set_ability_score(Ability.DEX, 14)
    c.levels = [
        CharacterLevel(character_level=i + 1, class_name=cls, hp_roll=8)
        for i in range(level)
    ]
    c._invalidate_class_stats()
    c.equipment["weapons"] = [dict(w) for w in weapons]
    register_weapons_on_character(c)
    return c


def _weapons(c: Character) -> list:
    return gather_sheet(c).equipment.weapons


_YAML = """
identity:
  name: Stancer
  race: Human
  alignment: lawful_neutral
ability_scores: {{str: 16, dex: 14, con: 10, int: 10, wis: 10, cha: 10}}
levels:
  - {{level: 1, class: Fighter, hp_roll: 8}}
equipment:
  weapons:
    - base: Longsword
      stances: [{stance}]
"""


class TestTheVocabulary:
    def test_it_is_closed(self) -> None:
        assert {s.value for s in Stance} == {
            "two_handed",
            "primary",
            "off_hand",
            "flurry",
            "rapid_shot",
        }

    def test_a_misspelled_stance_is_refused_at_load(
        self, tmp_path: Path
    ) -> None:
        """
        A typo must not read as "no stance". The sheet would
        print a quietly weaker weapon rather than fail.
        """
        path = tmp_path / "t.char.yaml"
        path.write_text(_YAML.format(stance="two_hnded"))
        with pytest.raises(Exception, match="two_hnded"):
            load_character(path)

    def test_a_spelled_stance_loads(self, tmp_path: Path) -> None:
        path = tmp_path / "t.char.yaml"
        path.write_text(_YAML.format(stance="two_handed"))
        c = load_character(path)
        assert strength_damage_adjust(c, c.equipment["weapons"][0]) == 1


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
        load_character(path)

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


class TestDoubleWeapons:
    """
    PHB p. 113: a character "can fight with both ends of a
    double weapon as if fighting with two weapons ... just as
    though the character were wielding a one-handed weapon and
    a light weapon. The character can also choose to use a
    double weapon two handed, attacking with only one end."

    So the two uses are exclusive, and which one is chosen
    decides the Strength on each end.
    """

    def _staff_pair(self) -> Character:
        return _char(
            "Fighter",
            6,
            {"base": "Quarterstaff", "stances": ["primary"]},
            {"base": "Quarterstaff", "stances": ["off_hand"]},
        )

    def test_two_handed_is_one_and_a_half(self) -> None:
        c = _char("Fighter", 6, {"base": "Quarterstaff"})
        assert strength_damage_adjust(c, c.equipment["weapons"][0]) == 1

    def test_fought_as_two_weapons_the_primary_end_is_full(
        self,
    ) -> None:
        """
        Not one and a half: fighting with both ends is the
        one-handed-plus-light case, not the two-handed one.
        """
        c = self._staff_pair()
        assert strength_damage_adjust(c, c.equipment["weapons"][0]) == 0

    def test_and_the_other_end_is_half(self) -> None:
        c = self._staff_pair()
        assert strength_damage_adjust(c, c.equipment["weapons"][1]) == -2

    def test_the_off_end_counts_as_light_for_the_penalty(self) -> None:
        """
        PHB Table 8-10: the penalty is the one for an off-hand
        light weapon, -4/-8 without the feat, not the -6/-10
        a heavier off-hand would cost.
        """

        c = self._staff_pair()
        weapons = c.equipment["weapons"]
        assert two_weapon_penalty(c, weapons[0], weapons) == -4
        assert two_weapon_penalty(c, weapons[1], weapons) == -8

    def test_the_definition_knows_it_is_double(self) -> None:

        staff = get_rules().weapons.get("Quarterstaff")
        greatsword = get_rules().weapons.get("Greatsword")
        assert staff is not None and greatsword is not None
        assert staff.double
        assert not greatsword.double

    def test_a_non_double_two_hander_cannot_be_paired(
        self, tmp_path: Path
    ) -> None:
        """
        You cannot fight with both ends of a greatsword.
        """
        body = TestIncompatibleStances.HEAD.replace(
            "WEAPON", "Greatsword"
        ).replace("STANCES", "[primary]")
        path = tmp_path / "g.char.yaml"
        path.write_text(body)
        with pytest.raises(Exception, match="Greatsword"):
            load_character(path)


class TestFlurryAndTwoWeaponFighting:
    """
    The two combine. 3.5 FAQ: "a monk can combine two-weapon
    fighting with a flurry of blows to gain an extra attack
    with her off hand (but remember that she can use only
    unarmed strikes or special monk weapons as part of the
    flurry). The penalties for two-weapon fighting stack with
    the penalties for flurry of blows."
    """

    def _monk(
        self, level: int, strength: int, *weapons: dict, feat: bool = True
    ) -> Character:
        c = _char("Monk", level, *weapons, strength=strength)
        if feat:
            c.add_feat("Two-Weapon Fighting", level=1, source="")
        register_weapons_on_character(c)
        return c

    def test_the_faq_worked_example(self) -> None:
        """
        3.5 FAQ, verbatim: a 4th-level monk with the
        Two-Weapon Fighting feat and Strength 14, flurrying
        unarmed with an off-hand attack thrown in.

        "The monk has a base attack bonus of +3 and a +2
        Strength bonus. With a flurry, the character can make
        two attacks, each at +3 (base +3, -2 flurry, +2
        Strength). An unarmed strike is a light weapon, so the
        monk suffers an additional -2 penalty for both the
        flurry and the off-hand attack, and the monk makes
        three attacks, each at an attack bonus of +1. The two
        attacks from the flurry are primary attacks and add
        the monk's full Strength bonus to damage of +2. The
        single off-hand attack adds half the monk's Strength
        bonus to damage (+1)."
        """
        c = self._monk(
            4,
            14,
            {"base": "Unarmed Strike", "stances": ["flurry", "primary"]},
            {"base": "Unarmed Strike", "stances": ["flurry", "off_hand"]},
        )
        primary, off = _weapons(c)

        assert primary.attack_iteratives == [1, 1]
        assert off.attack_iteratives == [1]
        assert primary.damage.total == 2
        assert off.damage.total == 1

    def test_the_penalties_stack(self) -> None:
        """Both the flurry's -2 and the pairing's -2 appear."""
        c = self._monk(
            4,
            14,
            {"base": "Unarmed Strike", "stances": ["flurry", "primary"]},
            {"base": "Unarmed Strike", "stances": ["flurry", "off_hand"]},
        )
        typed = _weapons(c)[0].attack.typed
        assert typed["flurry_of_blows"] == -2
        assert typed["two_weapon_fighting"] == -2

    def test_a_quarterstaff_fought_with_both_ends_while_flurrying(
        self,
    ) -> None:
        """
        The hardest case: a quarterstaff is a special monk
        weapon, so it may be used in a flurry, and a double
        weapon, so both ends may be fought with as two
        weapons. Fighting with both ends is the
        one-handed-plus-light use, so no end gets one and a
        half Strength -- full on the primary, half on the
        other -- and the far end counts as light for the
        pairing penalty.
        """
        c = self._monk(
            11,
            16,
            {"base": "Quarterstaff", "stances": ["flurry", "primary"]},
            {"base": "Quarterstaff", "stances": ["flurry", "off_hand"]},
        )
        primary, off = _weapons(c)

        # Monk 11: base attack +8, no flurry penalty by 9th,
        # -2 from the pairing, +3 Strength.
        assert primary.attack.total == 9
        # Greater flurry from 11th: two extra attacks at full
        # base attack bonus, on top of the +8/+3 sequence.
        assert primary.attack_iteratives == [9, 9, 9, 4]
        # One off-hand attack, at the same bonus.
        assert off.attack_iteratives == [9]

        # Full Strength on the primary end, half on the other,
        # and one and a half on neither.
        assert primary.damage.total == 3
        assert off.damage.total == 1

    def test_both_stances_are_named(self) -> None:
        c = self._monk(
            11,
            16,
            {"base": "Quarterstaff", "stances": ["flurry", "primary"]},
            {"base": "Quarterstaff", "stances": ["flurry", "off_hand"]},
        )
        names = [w.name for w in _weapons(c)]
        assert names[0] == "Quarterstaff (TWF: Primary, Flurry of Blows)"
        assert names[1] == "Quarterstaff (TWF: Off-hand, Flurry of Blows)"

    def test_without_the_feat_the_pairing_costs_more(self) -> None:
        """
        Table 8-10 with a light off-hand and no feat: -4 on
        the primary, -8 on the off hand, stacking with the
        flurry as before.
        """
        c = self._monk(
            4,
            14,
            {"base": "Unarmed Strike", "stances": ["flurry", "primary"]},
            {"base": "Unarmed Strike", "stances": ["flurry", "off_hand"]},
            feat=False,
        )
        primary, off = _weapons(c)
        assert primary.attack.typed["two_weapon_fighting"] == -4
        assert off.attack.typed["two_weapon_fighting"] == -8


class TestTheDamageBreakdownSums:
    """
    Regression: the grip's Strength correction was both folded
    into the `str` line and listed beside it, so an off-hand
    weapon's damage breakdown read `str: 1, strength_hands:
    -2` against a total of 1. The breakdown and the total are
    the same number seen two ways.
    """

    def _check(self, c: Character) -> None:
        for w in _weapons(c):
            assert sum(w.damage.typed.values()) == w.damage.total, w.name

    def test_two_handed(self) -> None:
        self._check(_char("Fighter", 6, {"base": "Greatsword"}))

    def test_one_handed_in_two(self) -> None:
        self._check(
            _char(
                "Fighter",
                6,
                {"base": "Longsword", "stances": ["two_handed"]},
            )
        )

    def test_a_pairing(self) -> None:
        self._check(
            _char(
                "Fighter",
                6,
                {"base": "Short Sword", "stances": ["primary"]},
                {"base": "Dagger", "stances": ["off_hand"]},
            )
        )

    def test_a_double_weapon_pairing(self) -> None:
        self._check(
            _char(
                "Fighter",
                6,
                {"base": "Quarterstaff", "stances": ["primary"]},
                {"base": "Quarterstaff", "stances": ["off_hand"]},
            )
        )
