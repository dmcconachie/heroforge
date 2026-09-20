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
