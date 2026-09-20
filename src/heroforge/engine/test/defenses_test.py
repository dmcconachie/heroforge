"""
Damage reduction, resistance to energy, and immunity.

Neither DR nor energy resistance is a bonus, so neither can
live in a BonusPool: DR is keyed by what bypasses it and
energy resistance by which energy, and in both cases the best
single source applies rather than a sum.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from heroforge.engine.character import Character, CharacterLevel
from heroforge.engine.defenses import (
    DamageReduction,
    collect_defenses,
)
from heroforge.engine.equipment import equip_armor
from heroforge.engine.persistence import load_character
from heroforge.engine.sheet import gather_sheet
from heroforge.rules.rules import get_rules


def _char(cls: str = "Barbarian", level: int = 1) -> Character:
    c = Character(name="Grim")
    for ab in ("str", "dex", "con", "int", "wis", "cha"):
        c.set_ability_score(ab, 12)
    c.levels = [
        CharacterLevel(character_level=i + 1, class_name=cls, hp_roll=8)
        for i in range(level)
    ]
    c._invalidate_class_stats()
    return c


def _wear(c: Character, *properties: str) -> Character:
    equip_armor(
        c, get_rules().armor.get("Chain Shirt"), properties=list(properties)
    )
    return c


class TestDamageReduction:
    @pytest.mark.parametrize(
        ("level", "amount"),
        [(7, 1), (9, 1), (10, 2), (13, 3), (16, 4), (19, 5), (20, 5)],
    )
    def test_barbarian_progression(self, level: int, amount: int) -> None:
        """PHB Table 3-3: 1/- at 7th, rising at 10/13/16/19."""
        d = collect_defenses(_char(level=level))
        assert d.damage_reduction == (DamageReduction(amount, "-"),)

    def test_below_seventh_there_is_none(self) -> None:
        assert collect_defenses(_char(level=6)).damage_reduction == ()

    def test_invulnerability_gives_dr_against_magic(self) -> None:
        d = collect_defenses(_wear(_char(level=1), "Invulnerability"))
        assert d.damage_reduction == (DamageReduction(5, "magic"),)

    def test_different_bypasses_are_listed_separately(self) -> None:
        """
        DR does not stack, but "the best in a given situation"
        depends on what is attacking, so each bypass keeps its
        own entry.
        """
        d = collect_defenses(_wear(_char(level=10), "Invulnerability"))
        assert set(d.damage_reduction) == {
            DamageReduction(2, "-"),
            DamageReduction(5, "magic"),
        }

    def test_the_same_bypass_takes_the_best(self) -> None:
        from heroforge.engine.defenses import best_damage_reduction

        got = best_damage_reduction(
            [
                DamageReduction(5, "magic"),
                DamageReduction(10, "magic"),
                DamageReduction(2, "-"),
            ]
        )
        assert set(got) == {
            DamageReduction(10, "magic"),
            DamageReduction(2, "-"),
        }


class TestEnergyResistance:
    def test_a_resistance_property(self) -> None:
        d = collect_defenses(_wear(_char(), "Fire Resistance"))
        assert d.energy_resistance == {"fire": 10}

    @pytest.mark.parametrize(
        ("prop", "points"),
        [
            ("Cold Resistance", 10),
            ("Cold Resistance, Improved", 20),
            ("Cold Resistance, Greater", 30),
        ],
    )
    def test_grades(self, prop: str, points: int) -> None:
        d = collect_defenses(_wear(_char(), prop))
        assert d.energy_resistance == {"cold": points}

    def test_multiple_energies_are_kept_apart(self) -> None:
        d = collect_defenses(
            _wear(_char(), "Fire Resistance", "Acid Resistance, Greater")
        )
        assert d.energy_resistance == {"fire": 10, "acid": 30}

    def test_it_does_not_stack_with_itself(self) -> None:
        """
        Rules Compendium p. 48: only the highest value applies
        to any given attack.
        """
        d = collect_defenses(
            _wear(_char(), "Fire Resistance", "Fire Resistance, Greater")
        )
        assert d.energy_resistance == {"fire": 30}


class TestOnTheSheet:
    def test_damage_reduction_reads_as_amount_slash_bypass(self) -> None:
        sheet = gather_sheet(_char(level=10), None)
        assert sheet.combat.damage_reduction == ["2/-"]

    def test_energy_resistance_is_a_mapping(self) -> None:
        sheet = gather_sheet(_wear(_char(), "Fire Resistance"), None)
        assert sheet.combat.energy_resistance == {"fire": 10}

    def test_a_character_with_none_shows_none(self) -> None:
        sheet = gather_sheet(_char(cls="Fighter", level=5), None)
        assert sheet.combat.damage_reduction == []
        assert sheet.combat.energy_resistance == {}
        assert sheet.combat.immunities == []


class TestItPersists:
    CHAR = (
        """
identity:
  name: Stubborn
  race: Human
  alignment: chaotic_neutral
ability_scores: {str: 14, dex: 12, con: 14, int: 10, wis: 10, cha: 10}
levels:
"""
        + "".join(
            f"  - {{level: {i}, class: Barbarian, hp_roll: 8}}\n"
            for i in range(1, 11)
        )
        + """equipment:
  armor:
    base: Chain Shirt
    properties:
      - Invulnerability
      - Fire Resistance, Greater
"""
    )

    def test_defenses_survive_a_load(self, tmp_path: Path) -> None:
        path = tmp_path / "b.char.yaml"
        path.write_text(self.CHAR)
        sheet = gather_sheet(load_character(path, None), None)
        assert sorted(sheet.combat.damage_reduction) == ["2/-", "5/magic"]
        assert sheet.combat.energy_resistance == {"fire": 30}


class TestWornItems:
    """
    A ring of energy resistance names its energy when it is
    made, so the item declares `$parameter` and the character
    file supplies the choice.
    """

    def _ringed(self, grade: str, energy: str) -> Character:
        from heroforge.engine.equipment import equip_item

        c = _char(cls="Fighter", level=1)
        name = f"Ring of Energy Resistance, {grade}"
        item = get_rules().magic_items.get(name)
        assert item is not None
        equip_item(c, item)
        c.equipment["worn"] = [{"name": name, "parameter": energy}]
        return c

    @pytest.mark.parametrize(
        ("grade", "points"),
        [("Minor", 10), ("Major", 20), ("Greater", 30)],
    )
    def test_the_ring_resists_its_chosen_energy(
        self, grade: str, points: int
    ) -> None:
        d = collect_defenses(self._ringed(grade, "fire"))
        assert d.energy_resistance == {"fire": points}

    def test_a_different_choice_gives_a_different_energy(self) -> None:
        d = collect_defenses(self._ringed("Minor", "sonic"))
        assert d.energy_resistance == {"sonic": 10}

    def test_the_item_declares_what_the_choice_is(self) -> None:
        item = get_rules().magic_items.get("Ring of Energy Resistance, Minor")
        assert item.takes_parameter
        assert item.parameter_label == "energy type"


class TestTemplates:
    def _templated(self, name: str, level: int = 1) -> Character:
        from heroforge.engine.templates import apply_template

        c = _char(cls="Fighter", level=level)
        defn = get_rules().templates.get(name)
        assert defn is not None, name
        apply_template(defn, c)
        return c

    def test_half_celestial_resistances(self) -> None:
        d = collect_defenses(self._templated("Half-Celestial"))
        assert d.energy_resistance == {
            "acid": 10,
            "cold": 10,
            "electricity": 10,
        }

    def test_half_celestial_immunity(self) -> None:
        d = collect_defenses(self._templated("Half-Celestial"))
        assert "disease" in d.immunities

    def test_half_fiend_adds_fire(self) -> None:
        d = collect_defenses(self._templated("Half-Fiend"))
        assert d.energy_resistance["fire"] == 10
        assert "poison" in d.immunities

    def test_damage_reduction_scales_with_hit_dice(self) -> None:
        """MM: 5/magic at HD 11 or less, 10/magic at 12 or more."""
        low = collect_defenses(self._templated("Half-Celestial", 11))
        high = collect_defenses(self._templated("Half-Celestial", 12))
        assert low.damage_reduction == (DamageReduction(5, "magic"),)
        assert high.damage_reduction == (DamageReduction(10, "magic"),)


class TestEnergyImmunity:
    """
    Immunity to a damage type has to be visible, and it
    supersedes resistance to the same type rather than being
    listed beside it.
    """

    def _red_dragon(self) -> Character:
        from heroforge.engine.templates import apply_template

        c = _char(cls="Fighter", level=1)
        apply_template(get_rules().templates.get("Half-Dragon (Red)"), c)
        return c

    def test_fire_immunity_is_listed(self) -> None:
        d = collect_defenses(self._red_dragon())
        assert "fire" in d.immunities

    def test_it_reaches_the_sheet(self) -> None:
        sheet = gather_sheet(self._red_dragon(), None)
        assert "fire" in sheet.combat.immunities

    def test_immunity_supersedes_resistance(self) -> None:
        """
        A red half-dragon wearing a ring of fire resistance is
        immune, so showing "resist fire 10" beside it would
        only mislead.
        """
        from heroforge.engine.equipment import equip_item

        c = self._red_dragon()
        name = "Ring of Energy Resistance, Minor"
        equip_item(c, get_rules().magic_items.get(name))
        c.equipment["worn"] = [{"name": name, "parameter": "fire"}]
        d = collect_defenses(c)
        assert "fire" in d.immunities
        assert "fire" not in d.energy_resistance
