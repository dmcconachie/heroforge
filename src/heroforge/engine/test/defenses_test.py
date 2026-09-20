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


class TestArmourMaterialDamageReduction:
    """
    DMG p. 284: adamantine armour grants DR 1/- (light),
    2/- (medium) or 3/- (heavy). Starmetal is equal to
    adamantine for all purposes (Complete Arcane p. 141).
    """

    def _in(self, armour: str, material: str) -> Character:
        c = _char(cls="Fighter", level=1)
        equip_armor(c, get_rules().armor.get(armour), material=material)
        return c

    @pytest.mark.parametrize(
        ("armour", "amount"),
        [("Chain Shirt", 1), ("Breastplate", 2), ("Full Plate", 3)],
    )
    def test_adamantine_by_category(self, armour: str, amount: int) -> None:
        d = collect_defenses(self._in(armour, "Adamantine"))
        assert d.damage_reduction == (DamageReduction(amount, "-"),)

    def test_starmetal_matches_adamantine(self) -> None:
        d = collect_defenses(self._in("Full Plate", "Starmetal"))
        assert d.damage_reduction == (DamageReduction(3, "-"),)

    def test_a_plain_material_grants_none(self) -> None:
        d = collect_defenses(self._in("Full Plate", "Mithral"))
        assert d.damage_reduction == ()

    def test_it_takes_the_best_against_a_class_feature(self) -> None:
        """
        A barbarian's DR and the armour's are both x/-, so the
        better one applies rather than the two adding.
        """
        c = _char(level=19)
        equip_armor(
            c, get_rules().armor.get("Chain Shirt"), material="Adamantine"
        )
        # Barbarian 19 is DR 5/-; adamantine light armour is 1/-.
        assert collect_defenses(c).damage_reduction == (
            DamageReduction(5, "-"),
        )


class TestCreatureTemplateTables:
    """
    MM: the Celestial and Fiendish Creature templates scale
    both resistance and DR with Hit Dice, on the same table.

        HD        resistance   damage reduction
        1-3       5            --
        4-7       5            5/magic
        8-11      10           5/magic
        12+       10           10/magic

    Celestial resists acid, cold and electricity; fiendish
    resists cold and fire.
    """

    def _templated(self, name: str, level: int) -> Character:
        from heroforge.engine.templates import apply_template

        c = _char(cls="Fighter", level=level)
        defn = get_rules().templates.get(name)
        assert defn is not None, name
        apply_template(defn, c)
        return c

    @pytest.mark.parametrize(
        ("level", "resist", "dr"),
        [
            (1, 5, None),
            (3, 5, None),
            (4, 5, 5),
            (7, 5, 5),
            (8, 10, 5),
            (11, 10, 5),
            (12, 10, 10),
            (20, 10, 10),
        ],
    )
    def test_celestial_creature(
        self, level: int, resist: int, dr: int | None
    ) -> None:
        d = collect_defenses(self._templated("Celestial Creature", level))
        assert d.energy_resistance == {
            "acid": resist,
            "cold": resist,
            "electricity": resist,
        }
        expected = () if dr is None else (DamageReduction(dr, "magic"),)
        assert d.damage_reduction == expected

    @pytest.mark.parametrize(
        ("level", "resist", "dr"),
        [(1, 5, None), (4, 5, 5), (8, 10, 5), (12, 10, 10)],
    )
    def test_fiendish_creature(
        self, level: int, resist: int, dr: int | None
    ) -> None:
        d = collect_defenses(self._templated("Fiendish Creature", level))
        assert d.energy_resistance == {"cold": resist, "fire": resist}
        expected = () if dr is None else (DamageReduction(dr, "magic"),)
        assert d.damage_reduction == expected

    def test_below_four_hit_dice_there_is_no_dr(self) -> None:
        """The table's first row is an em dash, not a zero."""
        d = collect_defenses(self._templated("Fiendish Creature", 3))
        assert d.damage_reduction == ()


class TestFortification:
    """
    A chance to negate a critical hit or sneak attack. Not a
    bonus and not a reduction, but a defensive number the
    player needs, so it sits with the other defenses.

    DMG p. 219 and Draconomicon p. 83 both use the same
    grades: light 25%, moderate 75%, heavy 100%.
    """

    def _wear(self, *properties: str) -> Character:
        c = _char(cls="Fighter", level=1)
        equip_armor(
            c,
            get_rules().armor.get("Chain Shirt"),
            properties=list(properties),
        )
        return c

    @pytest.mark.parametrize(
        ("prop", "pct"),
        [
            ("Fortification, Light", 25),
            ("Fortification, Moderate", 75),
            ("Fortification, Heavy", 100),
        ],
    )
    def test_the_armour_property(self, prop: str, pct: int) -> None:
        assert collect_defenses(self._wear(prop)).fortification == pct

    @pytest.mark.parametrize(
        ("item", "pct"),
        [
            ("Gemstone of Light Fortification", 25),
            ("Gemstone of Moderate Fortification", 75),
            ("Gemstone of Heavy Fortification", 100),
        ],
    )
    def test_the_draconomicon_gemstones(self, item: str, pct: int) -> None:
        from heroforge.engine.equipment import equip_item

        c = _char(cls="Fighter", level=1)
        defn = get_rules().magic_items.get(item)
        assert defn is not None, item
        equip_item(c, defn)
        c.equipment["worn"] = [{"name": item}]
        assert collect_defenses(c).fortification == pct

    def test_none_by_default(self) -> None:
        assert collect_defenses(self._wear()).fortification == 0

    def test_the_best_applies(self) -> None:
        c = self._wear("Fortification, Light", "Fortification, Heavy")
        assert collect_defenses(c).fortification == 100

    def test_it_reaches_the_sheet(self) -> None:
        sheet = gather_sheet(self._wear("Fortification, Heavy"), None)
        assert sheet.combat.fortification == 100

    def test_it_is_omitted_when_there_is_none(self) -> None:
        sheet = gather_sheet(self._wear(), None)
        assert sheet.combat.fortification == 0


class TestTemplateSpellResistance:
    """
    MM: the half-outsiders are HD + 10 (maximum 35); the
    Celestial and Fiendish Creature templates are HD + 5
    (maximum 25).
    """

    def _templated(self, name: str, level: int) -> Character:
        from heroforge.engine.templates import apply_template

        c = _char(cls="Fighter", level=level)
        apply_template(get_rules().templates.get(name), c)
        return c

    @pytest.mark.parametrize(
        ("name", "level", "sr"),
        [
            ("Half-Celestial", 5, 15),
            ("Half-Celestial", 20, 30),
            ("Half-Fiend", 12, 22),
            ("Celestial Creature", 5, 10),
            ("Fiendish Creature", 12, 17),
        ],
    )
    def test_spell_resistance(self, name: str, level: int, sr: int) -> None:
        assert self._templated(name, level).get("sr") == sr

    def test_the_half_outsider_cap(self) -> None:
        c = self._templated("Half-Celestial", 30)
        assert c.get("sr") == 35

    def test_the_creature_template_cap(self) -> None:
        c = self._templated("Celestial Creature", 30)
        assert c.get("sr") == 25

    def test_removing_the_template_removes_it(self) -> None:
        from heroforge.engine.templates import (
            apply_template,
            remove_template,
        )

        c = _char(cls="Fighter", level=5)
        defn = get_rules().templates.get("Half-Celestial")
        apply_template(defn, c)
        assert c.get("sr") == 15
        remove_template(defn, c)
        assert c.get("sr") == 0
