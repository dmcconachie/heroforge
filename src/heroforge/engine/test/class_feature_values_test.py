"""
Class features that carry numbers: uses per day and the
computed values a player actually needs at the table
(smite's attack and damage, a turning check, insightful
strike's damage bonus).
"""

from __future__ import annotations

from pathlib import Path

from heroforge.engine.character import Character, CharacterLevel
from heroforge.engine.effects import evaluate_formula
from heroforge.engine.persistence import load_character
from heroforge.engine.sheet import gather_sheet
from heroforge.rules.rules import get_rules


def _char(class_name: str, level: int, **abilities: int) -> Character:
    c = Character(name="Test")
    defaults = dict(str=12, dex=12, con=12, int=12, wis=12, cha=12)
    defaults.update(abilities)
    for ab, val in defaults.items():
        c.set_ability_score(ab, val)
    c.levels = [
        CharacterLevel(character_level=i + 1, class_name=class_name, hp_roll=8)
        for i in range(level)
    ]
    c.race = "Human"
    c._invalidate_class_stats()
    return c


def _features(c: Character) -> dict:
    return gather_sheet(c, None).class_features


class TestSmiteEvil:
    """
    PHB p. 44: +CHA on the attack roll, +paladin level on
    damage, and a use count that grows with level."""

    def test_uses_per_day_at_first_level(self) -> None:
        f = _features(_char("Paladin", 1, cha=16))["smite_evil"]
        assert f.uses is not None
        assert f.uses.max == 1

    def test_uses_per_day_at_fifth(self) -> None:
        f = _features(_char("Paladin", 5, cha=16))["smite_evil"]
        assert f.uses.max == 2

    def test_attack_bonus_is_the_charisma_modifier(self) -> None:
        f = _features(_char("Paladin", 5, cha=16))["smite_evil"]
        assert f.values["attack"] == 3

    def test_damage_is_the_paladin_level(self) -> None:
        f = _features(_char("Paladin", 5, cha=16))["smite_evil"]
        assert f.values["damage"] == 5

    def test_a_charisma_penalty_does_not_help_the_attack(self) -> None:
        """
        PHB: add the CHA bonus, if any — a penalty is not
        added back as a bonus."""
        f = _features(_char("Paladin", 5, cha=8))["smite_evil"]
        assert f.values["attack"] == 0


class TestTurnUndead:
    """
    PHB p. 159: 3 + CHA mod attempts per day; the turning
    check is d20 + CHA mod; turning damage is 2d6 + level +
    CHA mod."""

    def test_attempts_per_day(self) -> None:
        f = _features(_char("Cleric", 5, cha=16))["turn_undead"]
        assert f.uses.max == 6

    def test_a_charisma_penalty_reduces_attempts(self) -> None:
        f = _features(_char("Cleric", 5, cha=8))["turn_undead"]
        assert f.uses.max == 2

    def test_turning_check_modifier(self) -> None:
        f = _features(_char("Cleric", 5, cha=16))["turn_undead"]
        assert f.values["turning_check"] == 3

    def test_turning_damage_bonus(self) -> None:
        f = _features(_char("Cleric", 5, cha=16))["turn_undead"]
        assert f.values["turning_damage_bonus"] == 8


class TestInsightfulStrike:
    """
    Complete Warrior p. 12. The swashbuckler adds her INT
    bonus to damage with Weapon Finesse-eligible weapons —
    but only against targets that can be critically hit, and
    not in medium/heavy armor or at medium/heavy load.
    """

    def test_damage_is_the_intelligence_modifier(self) -> None:
        f = _features(_char("Swashbuckler", 3, int=18))
        assert f["insightful_strike"].values["damage"] == 4

    def test_it_records_the_target_condition(self) -> None:
        f = _features(_char("Swashbuckler", 3, int=18))
        when = f["insightful_strike"].when
        assert "critical" in when.lower()

    def test_it_is_gated_on_armor_and_load(self) -> None:
        f = _features(_char("Swashbuckler", 3, int=18))
        gates = set(f["insightful_strike"].gated_by)
        assert gates == {"light_armor_or_less", "light_load_or_less"}

    def test_no_longer_carries_a_todo(self) -> None:
        defn = get_rules().classes.require("Swashbuckler")
        feature = next(
            f for f in defn.class_features if f.feature == "insightful_strike"
        )
        assert "TODO" not in feature.description


class TestFeatureShape:
    def test_features_are_keyed_by_feature_name(self) -> None:
        f = _features(_char("Paladin", 5, cha=16))
        assert "aura_of_good" in f
        assert f["aura_of_good"].description

    def test_a_plain_feature_has_no_numbers(self) -> None:
        f = _features(_char("Paladin", 5, cha=16))["detect_evil"]
        assert f.uses is None
        assert f.values == {}


class TestNumbersPersist:
    CHAR = """
identity:
  name: Smiter
  race: Human
  alignment: lawful_good
ability_scores: {str: 12, dex: 12, con: 12, int: 12, wis: 12, cha: 16}
levels:
  - {level: 1, class: Paladin, hp_roll: 10}
  - {level: 2, class: Paladin, hp_roll: 6}
  - {level: 3, class: Paladin, hp_roll: 6}
  - {level: 4, class: Paladin, hp_roll: 6}
  - {level: 5, class: Paladin, hp_roll: 6}
"""

    def test_values_survive_a_load(self, tmp_path: Path) -> None:
        path = tmp_path / "s.char.yaml"
        path.write_text(self.CHAR)
        f = _features(load_character(path, None))["smite_evil"]
        assert f.uses.max == 2
        assert f.values["attack"] == 3
        assert f.values["damage"] == 5


class TestMultiWordClassNames:
    def test_a_two_word_class_is_usable_in_a_formula(self) -> None:
        """
        Regression: class level variables were built with
        `name.lower()`, so "Wild Mage" produced the unusable
        name "wild mage_level" and any formula naming it blew
        up at sheet time.
        """
        c = _char("Wild Mage", 6)
        assert evaluate_formula("wild_mage_level", character=c) == 6
