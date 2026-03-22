"""
tests/test_classes_races.py
---------------------------
Test suite for engine/classes_races.py, rules/core/classes.yaml,
rules/core/races.yaml, ClassesLoader, and RacesLoader.

Covers:
  - BAB and save progression helper functions at key level boundaries
  - ClassDefinition construction and make_class_level()
  - ClassRegistry: register, get, require
  - RaceDefinition construction and size modifiers
  - RaceRegistry: register, get, require
  - build_class_from_yaml / build_race_from_yaml
  - ClassesLoader: YAML validation, registration, all 9 core classes
  - RacesLoader: YAML validation, registration, all 7 core races
  - apply_race(): ability bonuses, base speed, creature type
  - remove_race(): full revert
  - Character integration: race + class levels → correct all stats
"""

from __future__ import annotations

from pathlib import Path

import pytest

from heroforge.engine.bonus import BonusType
from heroforge.engine.character import Character
from heroforge.engine.classes_races import (
    BABProgression,
    ClassDefinition,
    ClassFeature,
    ClassRegistry,
    RaceAbilityMod,
    RaceDefinition,
    RaceRegistry,
    SaveProgression,
    apply_race,
    bab_at_level,
    remove_race,
    save_at_level,
)

RULES_DIR = Path(__file__).parent.parent / "src" / "heroforge" / "rules"


# ===========================================================================
# Helpers
# ===========================================================================


def loaded_class_registry() -> ClassRegistry:
    from heroforge.rules.loader import ClassesLoader

    reg = ClassRegistry()
    ClassesLoader(RULES_DIR).load(reg)
    return reg


def loaded_race_registry() -> RaceRegistry:
    from heroforge.rules.loader import RacesLoader

    reg = RaceRegistry()
    RacesLoader(RULES_DIR).load(reg)
    return reg


def fresh_char() -> Character:
    return Character()


# ===========================================================================
# BAB progression helper
# ===========================================================================


class TestBabAtLevel:
    def test_full_bab_level_1(self) -> None:
        assert bab_at_level(BABProgression.FULL, 1) == 1

    def test_full_bab_level_10(self) -> None:
        assert bab_at_level(BABProgression.FULL, 10) == 10

    def test_full_bab_level_20(self) -> None:
        assert bab_at_level(BABProgression.FULL, 20) == 20

    def test_medium_bab_level_1(self) -> None:
        assert bab_at_level(BABProgression.MEDIUM, 1) == 0

    def test_medium_bab_level_2(self) -> None:
        assert bab_at_level(BABProgression.MEDIUM, 2) == 1

    def test_medium_bab_level_4(self) -> None:
        assert bab_at_level(BABProgression.MEDIUM, 4) == 3

    def test_medium_bab_level_8(self) -> None:
        assert bab_at_level(BABProgression.MEDIUM, 8) == 6

    def test_medium_bab_level_20(self) -> None:
        assert bab_at_level(BABProgression.MEDIUM, 20) == 15

    def test_poor_bab_level_1(self) -> None:
        assert bab_at_level(BABProgression.POOR, 1) == 0

    def test_poor_bab_level_2(self) -> None:
        assert bab_at_level(BABProgression.POOR, 2) == 1

    def test_poor_bab_level_10(self) -> None:
        assert bab_at_level(BABProgression.POOR, 10) == 5

    def test_poor_bab_level_20(self) -> None:
        assert bab_at_level(BABProgression.POOR, 20) == 10

    def test_level_zero_returns_zero(self) -> None:
        for prog in BABProgression:
            assert bab_at_level(prog, 0) == 0


# ===========================================================================
# Save progression helper
# ===========================================================================


class TestSaveAtLevel:
    def test_good_save_level_1(self) -> None:
        assert save_at_level(SaveProgression.GOOD, 1) == 2

    def test_good_save_level_2(self) -> None:
        assert save_at_level(SaveProgression.GOOD, 2) == 3

    def test_good_save_level_4(self) -> None:
        assert save_at_level(SaveProgression.GOOD, 4) == 4

    def test_good_save_level_10(self) -> None:
        assert save_at_level(SaveProgression.GOOD, 10) == 7

    def test_good_save_level_20(self) -> None:
        assert save_at_level(SaveProgression.GOOD, 20) == 12

    def test_poor_save_level_1(self) -> None:
        assert save_at_level(SaveProgression.POOR, 1) == 0

    def test_poor_save_level_3(self) -> None:
        assert save_at_level(SaveProgression.POOR, 3) == 1

    def test_poor_save_level_6(self) -> None:
        assert save_at_level(SaveProgression.POOR, 6) == 2

    def test_poor_save_level_20(self) -> None:
        assert save_at_level(SaveProgression.POOR, 20) == 6

    def test_level_zero_returns_zero(self) -> None:
        for prog in SaveProgression:
            assert save_at_level(prog, 0) == 0


# ===========================================================================
# ClassDefinition
# ===========================================================================


class TestClassDefinition:
    def _fighter(self) -> ClassDefinition:
        return ClassDefinition(
            name="Fighter",
            hit_die=10,
            bab_progression=BABProgression.FULL,
            fort_progression=SaveProgression.GOOD,
            ref_progression=SaveProgression.POOR,
            will_progression=SaveProgression.POOR,
        )

    def test_bab_contribution(self) -> None:
        f = self._fighter()
        assert f.bab_contribution(6) == 6

    def test_fort_contribution(self) -> None:
        f = self._fighter()
        assert f.fort_contribution(4) == 4  # 2 + 4//2

    def test_will_contribution(self) -> None:
        f = self._fighter()
        assert f.will_contribution(3) == 1  # floor(3/3)

    def test_make_class_level_correct_bab(self) -> None:
        f = self._fighter()
        cl = f.make_class_level(5)
        assert cl.bab_contribution == 5
        assert cl.fort_contribution == 4  # 2 + 5//2 = 4

    def test_make_class_level_default_max_hp(self) -> None:
        f = self._fighter()
        cl = f.make_class_level(3)
        assert cl.hp_rolls == [10, 10, 10]

    def test_features_at_level(self) -> None:
        f = ClassDefinition(
            name="Test",
            class_features=[
                ClassFeature(1, "feat_a", "desc a"),
                ClassFeature(2, "feat_b", "desc b"),
                ClassFeature(2, "feat_c", "desc c"),
                ClassFeature(3, "feat_d", "desc d"),
            ],
        )
        assert len(f.features_at_level(2)) == 2
        assert f.features_at_level(2)[0].feature == "feat_b"

    def test_features_up_to_level(self) -> None:
        f = ClassDefinition(
            name="Test",
            class_features=[
                ClassFeature(1, "a", ""),
                ClassFeature(3, "b", ""),
                ClassFeature(5, "c", ""),
            ],
        )
        assert len(f.features_up_to_level(3)) == 2


# ===========================================================================
# ClassRegistry
# ===========================================================================


class TestClassRegistry:
    def test_register_and_get(self) -> None:
        reg = ClassRegistry()
        reg.register(ClassDefinition(name="Fighter"))
        assert reg.get("Fighter").name == "Fighter"

    def test_require_unknown_raises(self) -> None:
        with pytest.raises(KeyError, match="No ClassDefinition"):
            ClassRegistry().require("Unknown")

    def test_duplicate_raises(self) -> None:
        reg = ClassRegistry()
        reg.register(ClassDefinition(name="Fighter"))
        with pytest.raises(ValueError, match="already registered"):
            reg.register(ClassDefinition(name="Fighter"))

    def test_all_names_sorted(self) -> None:
        reg = ClassRegistry()
        for name in ("Wizard", "Barbarian", "Cleric"):
            reg.register(ClassDefinition(name=name))
        assert reg.all_names() == ["Barbarian", "Cleric", "Wizard"]


# ===========================================================================
# RaceDefinition
# ===========================================================================


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


# ===========================================================================
# apply_race / remove_race
# ===========================================================================


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

    def test_apply_race_sets_character_race_name(self) -> None:
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

    def test_remove_race_reverts_ability_bonuses(self) -> None:
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
        assert c.ac == base_ac + 1  # dex 10→12, mod 0→1

    def test_halfling_small_speed(self) -> None:
        c = fresh_char()
        halfling = RaceDefinition(name="Halfling", base_speed=20)
        apply_race(halfling, c)
        assert c._race_base_speed == 20


# ===========================================================================
# ClassesLoader
# ===========================================================================


class TestClassesLoader:
    def test_validate_yaml_no_errors(self) -> None:
        from heroforge.rules.loader import ClassesLoader

        errors = ClassesLoader(RULES_DIR).validate_yaml()
        assert errors == [], "classes.yaml errors:\n" + "\n".join(errors)

    def test_load_registers_all_classes(self) -> None:
        import yaml

        from heroforge.rules.loader import ClassesLoader

        with open(RULES_DIR / "core" / "classes.yaml") as f:
            data = yaml.safe_load(f)
        expected = len(data["classes"])
        reg = ClassRegistry()
        ClassesLoader(RULES_DIR).load(reg)
        assert len(reg) == expected

    def test_all_phb_classes_present(self) -> None:
        reg = loaded_class_registry()
        for name in (
            "Barbarian",
            "Bard",
            "Cleric",
            "Druid",
            "Fighter",
            "Monk",
            "Paladin",
            "Ranger",
            "Rogue",
            "Sorcerer",
            "Wizard",
        ):
            assert name in reg, f"{name} missing from class registry"

    def test_fighter_full_bab(self) -> None:
        reg = loaded_class_registry()
        f = reg.require("Fighter")
        assert f.bab_progression == BABProgression.FULL

    def test_fighter_good_fort(self) -> None:
        reg = loaded_class_registry()
        f = reg.require("Fighter")
        assert f.fort_progression == SaveProgression.GOOD
        assert f.will_progression == SaveProgression.POOR

    def test_wizard_poor_bab(self) -> None:
        reg = loaded_class_registry()
        w = reg.require("Wizard")
        assert w.bab_progression == BABProgression.POOR

    def test_wizard_good_will(self) -> None:
        reg = loaded_class_registry()
        w = reg.require("Wizard")
        assert w.will_progression == SaveProgression.GOOD

    def test_rogue_medium_bab(self) -> None:
        reg = loaded_class_registry()
        r = reg.require("Rogue")
        assert r.bab_progression == BABProgression.MEDIUM

    def test_rogue_good_ref(self) -> None:
        reg = loaded_class_registry()
        r = reg.require("Rogue")
        assert r.ref_progression == SaveProgression.GOOD

    def test_cleric_has_spellcasting(self) -> None:
        reg = loaded_class_registry()
        c = reg.require("Cleric")
        assert c.spellcasting is not None
        assert c.spellcasting.cast_type == "divine"
        assert c.spellcasting.stat == "wis"

    def test_fighter_has_no_spellcasting(self) -> None:
        reg = loaded_class_registry()
        f = reg.require("Fighter")
        assert f.spellcasting is None

    def test_paladin_spellcasting_starts_at_4(self) -> None:
        reg = loaded_class_registry()
        p = reg.require("Paladin")
        assert p.spellcasting is not None
        assert p.spellcasting.starts_at_level == 4
        assert p.spellcasting.max_spell_level == 4

    def test_hit_dice_correct(self) -> None:
        reg = loaded_class_registry()
        assert reg.require("Fighter").hit_die == 10
        assert reg.require("Wizard").hit_die == 4
        assert reg.require("Rogue").hit_die == 6
        assert reg.require("Barbarian").hit_die == 12

    def test_fighter_class_features_include_bonus_feats(self) -> None:
        reg = loaded_class_registry()
        f = reg.require("Fighter")
        feats = {cf.feature for cf in f.class_features}
        assert "bonus_feat_1" in feats
        assert "bonus_feat_2" in feats

    def test_make_class_level_from_registry(self) -> None:
        reg = loaded_class_registry()
        cl = reg.require("Fighter").make_class_level(8)
        assert cl.bab_contribution == 8
        assert cl.fort_contribution == 6  # 2 + 8//2

    def test_cleric_make_class_level(self) -> None:
        reg = loaded_class_registry()
        cl = reg.require("Cleric").make_class_level(5)
        assert cl.bab_contribution == 3  # medium: floor(5*3/4)
        assert cl.fort_contribution == 4  # good: 2 + 5//2

    def test_no_duplicate_class_names(self) -> None:
        import yaml

        with open(RULES_DIR / "core" / "classes.yaml") as f:
            data = yaml.safe_load(f)
        names = [d["name"] for d in data["classes"]]
        assert len(names) == len(set(names))

    def test_load_missing_file_raises(self, tmp_path: Path) -> None:
        from heroforge.rules.loader import ClassesLoader, LoaderError

        with pytest.raises(LoaderError, match="not found"):
            ClassesLoader(tmp_path).load(ClassRegistry())


# ===========================================================================
# RacesLoader
# ===========================================================================


class TestRacesLoader:
    def test_validate_yaml_no_errors(self) -> None:
        from heroforge.rules.loader import RacesLoader

        errors = RacesLoader(RULES_DIR).validate_yaml()
        assert errors == [], "races.yaml errors:\n" + "\n".join(errors)

    def test_load_registers_all_races(self) -> None:
        import yaml

        from heroforge.rules.loader import RacesLoader

        with open(RULES_DIR / "core" / "races.yaml") as f:
            data = yaml.safe_load(f)
        expected = len(data["races"])
        reg = RaceRegistry()
        RacesLoader(RULES_DIR).load(reg)
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
        import yaml

        with open(RULES_DIR / "core" / "races.yaml") as f:
            data = yaml.safe_load(f)
        names = [d["name"] for d in data["races"]]
        assert len(names) == len(set(names))

    def test_load_missing_file_raises(self, tmp_path: Path) -> None:
        from heroforge.rules.loader import LoaderError, RacesLoader

        with pytest.raises(LoaderError, match="not found"):
            RacesLoader(tmp_path).load(RaceRegistry())


# ===========================================================================
# Character integration: race + class
# ===========================================================================


class TestCharacterIntegration:
    def test_dwarf_fighter_saves(self) -> None:
        """
        Dwarf Fighter 4:
          STR 14 (mod +2), DEX 10, CON 14 (+2 racial) = 16 (mod +3)
          Fort = base(4) + con_mod(3) = 7 (good fort)
          Ref  = base(1) + dex_mod(0) = 1 (poor ref)
          Will = base(1) + wis_mod(0) = 1 (poor will)
        """
        race_reg = loaded_race_registry()
        class_reg = loaded_class_registry()

        c = fresh_char()
        c.set_ability_score("str", 14)
        c.set_ability_score("con", 14)

        apply_race(race_reg.require("Dwarf"), c)
        assert c.con_score == 16  # 14 + 2 racial

        cl = class_reg.require("Fighter").make_class_level(4)
        c.set_class_levels([cl])

        assert c.fort == 7  # good 4 + con_mod 3
        assert c.ref == 1  # poor 4//3 + dex 0
        assert c.will == 1

    def test_elf_wizard_bab_and_will(self) -> None:
        """
        Elf Wizard 6:
          BAB = poor floor(6/2) = 3
          Will = good 2+6//2=5 + wis_mod(0) = 5
        """
        race_reg = loaded_race_registry()
        class_reg = loaded_class_registry()

        c = fresh_char()
        apply_race(race_reg.require("Elf"), c)
        cl = class_reg.require("Wizard").make_class_level(6)
        c.set_class_levels([cl])

        assert c.bab == 3
        assert c.will == 5

    def test_halfling_rogue_speed(self) -> None:
        """Halfling has base speed 20; should be reflected."""
        race_reg = loaded_race_registry()
        class_reg = loaded_class_registry()

        c = fresh_char()
        apply_race(race_reg.require("Halfling"), c)
        cl = class_reg.require("Rogue").make_class_level(3)
        c.set_class_levels([cl])

        assert c._race_base_speed == 20

    def test_half_orc_barbarian_str(self) -> None:
        """
        Half-Orc Barbarian 5:
          +2 STR racial. STR 14 base → 16.
          STR mod = 3. Attack = bab(5) + str_mod(3) = 8.
        """
        race_reg = loaded_race_registry()
        class_reg = loaded_class_registry()

        c = fresh_char()
        c.set_ability_score("str", 14)
        apply_race(race_reg.require("Half-Orc"), c)
        assert c.str_score == 16

        cl = class_reg.require("Barbarian").make_class_level(5)
        c.set_class_levels([cl])
        assert c.get("attack_melee") == 8  # bab 5 + str_mod 3

    def test_human_fighter_multiclass_bab(self) -> None:
        """
        Human Fighter 4 / Wizard 4:
          Fighter BAB = 4 (full), Wizard BAB = 2 (poor).
          Combined BAB = 6.
        """
        race_reg = loaded_race_registry()
        class_reg = loaded_class_registry()

        c = fresh_char()
        apply_race(race_reg.require("Human"), c)

        f_cl = class_reg.require("Fighter").make_class_level(4)
        w_cl = class_reg.require("Wizard").make_class_level(4)
        c.set_class_levels([f_cl, w_cl])

        assert c.bab == 6

    def test_gnome_small_size_ac(self) -> None:
        """
        Gnome is Small (+1 size AC).
        Size modifiers to AC are handled via the size pool — for now
        verify the size_modifier property is correct.
        """
        race_reg = loaded_race_registry()
        g = race_reg.require("Gnome")
        assert g.size_modifier == 1

    def test_remove_race_then_reapply(self) -> None:
        """Remove and re-apply a race produces the same state as one apply."""
        race_reg = loaded_race_registry()
        c = fresh_char()
        c.set_ability_score("dex", 10)
        c.set_ability_score("con", 10)

        elf = race_reg.require("Elf")
        apply_race(elf, c)
        dex_after_apply = c.dex_score

        remove_race(elf, c)
        assert c.dex_score == 10

        apply_race(elf, c)
        assert c.dex_score == dex_after_apply
