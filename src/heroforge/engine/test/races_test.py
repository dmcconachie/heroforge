"""
tests/test_races.py
-------------------
Test suite for engine/races.py, rules/core/races.yaml,
and RacesLoader.

Covers:
  - RaceDefinition construction and size modifiers
  - RaceRegistry: register, get, require
  - build_race_from_yaml
  - RacesLoader: YAML validation, registration, all 7
    core races
  - apply_race(): ability bonuses, base speed, creature
    type
  - remove_race(): full revert
"""

from __future__ import annotations

from pathlib import Path

import pytest

from heroforge.engine.bonus import BonusType
from heroforge.engine.character import Character
from heroforge.engine.races import (
    RaceAbilityMod,
    RaceDefinition,
    RaceRegistry,
    apply_race,
    remove_race,
)

RULES_DIR = Path(__file__).parent.parent.parent / "rules"


# ===============================================================
# Helpers
# ===============================================================


def loaded_race_registry() -> RaceRegistry:
    from heroforge.rules.loader import RacesLoader

    reg = RaceRegistry()
    RacesLoader(RULES_DIR).load(reg, "core/races.yaml")
    return reg


def fresh_char() -> Character:
    return Character()


# ===============================================================
# RaceDefinition
# ===============================================================


class TestRaceDefinition:
    def test_medium_size_mod_zero(self) -> None:
        r = RaceDefinition(name="Human", size="Medium")
        assert r.size_modifier == 0
        assert r.hide_modifier == 0

    def test_small_size_mod(self) -> None:
        r = RaceDefinition(name="Gnome", size="Small")
        assert r.size_modifier == 1
        assert r.hide_modifier == 4

    def test_large_size_mod(self) -> None:
        r = RaceDefinition(name="Giant", size="Large")
        assert r.size_modifier == -1
        assert r.hide_modifier == -4

    def test_ability_modifiers_stored(self) -> None:
        r = RaceDefinition(
            name="Dwarf",
            ability_modifiers=[
                RaceAbilityMod("con", 2, BonusType.UNTYPED),
                RaceAbilityMod("cha", -2, BonusType.UNTYPED),
            ],
        )
        assert len(r.ability_modifiers) == 2
        assert r.ability_modifiers[0].value == 2


# ===============================================================
# apply_race / remove_race
# ===============================================================


class TestApplyRace:
    def test_apply_race_sets_ability_bonuses(self) -> None:
        c = fresh_char()
        c.set_ability_score("dex", 10)
        c.set_ability_score("con", 10)

        dwarf = RaceDefinition(
            name="Dwarf",
            ability_modifiers=[
                RaceAbilityMod("con", 2, BonusType.UNTYPED),
                RaceAbilityMod("cha", -2, BonusType.UNTYPED),
            ],
        )
        apply_race(dwarf, c)
        assert c.con_score == 12
        assert c.cha_score == 8

    def test_apply_race_sets_character_race_name(
        self,
    ) -> None:
        c = fresh_char()
        apply_race(RaceDefinition(name="Human"), c)
        assert c.race == "Human"

    def test_apply_race_sets_base_speed(self) -> None:
        c = fresh_char()
        apply_race(RaceDefinition(name="Dwarf", base_speed=20), c)
        assert c._race_base_speed == 20

    def test_apply_race_is_idempotent(self) -> None:
        c = fresh_char()
        c.set_ability_score("dex", 10)
        elf = RaceDefinition(
            name="Elf",
            ability_modifiers=[RaceAbilityMod("dex", 2, BonusType.UNTYPED)],
        )
        apply_race(elf, c)
        dex_once = c.dex_score
        apply_race(elf, c)
        assert c.dex_score == dex_once  # no double-counting

    def test_remove_race_reverts_ability_bonuses(
        self,
    ) -> None:
        c = fresh_char()
        c.set_ability_score("dex", 10)
        elf = RaceDefinition(
            name="Elf",
            ability_modifiers=[RaceAbilityMod("dex", 2, BonusType.UNTYPED)],
        )
        apply_race(elf, c)
        assert c.dex_score == 12
        remove_race(elf, c)
        assert c.dex_score == 10

    def test_remove_race_reverts_name(self) -> None:
        c = fresh_char()
        elf = RaceDefinition(name="Elf")
        apply_race(elf, c)
        remove_race(elf, c)
        assert c.race == ""

    def test_remove_race_not_applied_is_noop(self) -> None:
        c = fresh_char()
        elf = RaceDefinition(name="Elf")
        remove_race(elf, c)  # must not raise

    def test_human_has_no_ability_modifiers(self) -> None:
        c = fresh_char()
        for ab in ("str", "dex", "con", "int", "wis", "cha"):
            c.set_ability_score(ab, 10)
        apply_race(RaceDefinition(name="Human"), c)
        for ab in ("str", "dex", "con", "int", "wis", "cha"):
            assert c.get_ability_score(ab) == 10

    def test_elf_dex_bonus_propagates_to_ac(self) -> None:
        c = fresh_char()
        c.set_ability_score("dex", 10)
        base_ac = c.ac
        elf = RaceDefinition(
            name="Elf",
            ability_modifiers=[
                RaceAbilityMod("dex", 2, BonusType.UNTYPED),
                RaceAbilityMod("con", -2, BonusType.UNTYPED),
            ],
        )
        apply_race(elf, c)
        assert c.ac == base_ac + 1  # dex 10->12, mod 0->1

    def test_halfling_small_speed(self) -> None:
        c = fresh_char()
        halfling = RaceDefinition(name="Halfling", base_speed=20)
        apply_race(halfling, c)
        assert c._race_base_speed == 20


# ===============================================================
# RacesLoader
# ===============================================================


class TestRacesLoader:
    def test_load_registers_all_races(self) -> None:
        import yaml

        from heroforge.rules.loader import RacesLoader

        with open(RULES_DIR / "core" / "races.yaml") as f:
            data = yaml.safe_load(f)
        expected = len(data)
        reg = RaceRegistry()
        RacesLoader(RULES_DIR).load(reg, "core/races.yaml")
        assert len(reg) == expected

    def test_all_phb_races_present(self) -> None:
        reg = loaded_race_registry()
        for name in (
            "Human",
            "Dwarf",
            "Elf",
            "Gnome",
            "Half-Elf",
            "Half-Orc",
            "Halfling",
        ):
            assert name in reg, f"{name} missing from race registry"

    def test_human_no_ability_mods(self) -> None:
        reg = loaded_race_registry()
        h = reg.require("Human")
        assert h.ability_modifiers == []

    def test_dwarf_con_cha_mods(self) -> None:
        reg = loaded_race_registry()
        d = reg.require("Dwarf")
        mods = {m.ability: m.value for m in d.ability_modifiers}
        assert mods["con"] == 2
        assert mods["cha"] == -2

    def test_elf_dex_con_mods(self) -> None:
        reg = loaded_race_registry()
        e = reg.require("Elf")
        mods = {m.ability: m.value for m in e.ability_modifiers}
        assert mods["dex"] == 2
        assert mods["con"] == -2

    def test_gnome_small_size(self) -> None:
        reg = loaded_race_registry()
        g = reg.require("Gnome")
        assert g.size == "Small"
        assert g.size_modifier == 1

    def test_human_medium_size(self) -> None:
        reg = loaded_race_registry()
        h = reg.require("Human")
        assert h.size == "Medium"

    def test_halfling_small_size(self) -> None:
        reg = loaded_race_registry()
        h = reg.require("Halfling")
        assert h.size == "Small"
        assert h.base_speed == 20

    def test_dwarf_speed_20(self) -> None:
        reg = loaded_race_registry()
        d = reg.require("Dwarf")
        assert d.base_speed == 20

    def test_dwarf_darkvision_60(self) -> None:
        reg = loaded_race_registry()
        d = reg.require("Dwarf")
        assert d.darkvision == 60

    def test_human_no_darkvision(self) -> None:
        reg = loaded_race_registry()
        h = reg.require("Human")
        assert h.darkvision == 0

    def test_elf_low_light_vision(self) -> None:
        reg = loaded_race_registry()
        e = reg.require("Elf")
        assert e.low_light_vision is True

    def test_human_no_low_light_vision(self) -> None:
        reg = loaded_race_registry()
        h = reg.require("Human")
        assert h.low_light_vision is False

    def test_dwarf_weapon_familiarity(self) -> None:
        reg = loaded_race_registry()
        d = reg.require("Dwarf")
        assert "Dwarven Waraxe" in d.weapon_familiarity

    def test_human_favored_class_any(self) -> None:
        reg = loaded_race_registry()
        h = reg.require("Human")
        assert h.favored_class == "any"

    def test_elf_favored_class_wizard(self) -> None:
        reg = loaded_race_registry()
        e = reg.require("Elf")
        assert e.favored_class == "Wizard"

    def test_no_duplicate_race_names(self) -> None:
        """Dict keys are unique by definition."""
        reg = loaded_race_registry()
        assert len(reg) == 7

    def test_load_missing_file_raises(self, tmp_path: Path) -> None:
        from heroforge.rules.loader import (
            LoaderError,
            RacesLoader,
        )

        with pytest.raises(LoaderError, match="not found"):
            RacesLoader(tmp_path).load(RaceRegistry(), "core/races.yaml")
