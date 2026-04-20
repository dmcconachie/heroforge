"""
tests/test_classes.py
---------------------
Test suite for engine/classes.py, rules/core/classes.yaml,
and ClassesLoader.

Covers:
  - BAB and save progression helper functions at key level
    boundaries
  - ClassDefinition construction and make_class_level()
  - ClassRegistry: register, get, require
  - build_class_from_yaml
  - ClassesLoader: YAML validation, registration, all core
    classes
  - Character integration: race + class levels -> correct
    all stats
"""

from __future__ import annotations

from pathlib import Path

import pytest

from heroforge.engine.character import Character
from heroforge.engine.classes import (
    BABProgression,
    ClassDefinition,
    ClassFeature,
    ClassRegistry,
    SaveProgression,
    SaveProgressions,
    bab_at_level,
    save_at_level,
)

RULES_DIR = Path(__file__).parent.parent.parent / "rules"


# ===============================================================
# Helpers
# ===============================================================


def loaded_class_registry() -> ClassRegistry:
    from heroforge.rules.loader import ClassesLoader

    reg = ClassRegistry()
    ClassesLoader(RULES_DIR).load(reg, "core/classes")
    return reg


def fresh_char() -> Character:
    return Character()


# ===============================================================
# BAB progression helper
# ===============================================================


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


# ===============================================================
# Save progression helper
# ===============================================================


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


# ===============================================================
# ClassDefinition
# ===============================================================


class TestClassDefinition:
    def _fighter(self) -> ClassDefinition:
        return ClassDefinition(
            name="Fighter",
            hit_die=10,
            bab_progression=BABProgression.FULL,
            save_progressions=SaveProgressions(
                fort=SaveProgression.GOOD,
                ref=SaveProgression.POOR,
                will=SaveProgression.POOR,
            ),
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


# ===============================================================
# ClassRegistry
# ===============================================================


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
        assert reg.all_names() == [
            "Barbarian",
            "Cleric",
            "Wizard",
        ]


# ===============================================================
# ClassesLoader
# ===============================================================


class TestClassesLoader:
    def test_load_registers_all_classes(self) -> None:
        from heroforge.rules.loader import ClassesLoader

        reg = ClassRegistry()
        ClassesLoader(RULES_DIR).load(reg, "core/classes")
        # 11 PHB + 5 NPC + 15 prestige = 31
        assert len(reg) == 31

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
        assert f.save_progressions.fort == SaveProgression.GOOD
        assert f.save_progressions.will == SaveProgression.POOR

    def test_wizard_poor_bab(self) -> None:
        reg = loaded_class_registry()
        w = reg.require("Wizard")
        assert w.bab_progression == BABProgression.POOR

    def test_wizard_good_will(self) -> None:
        reg = loaded_class_registry()
        w = reg.require("Wizard")
        assert w.save_progressions.will == SaveProgression.GOOD

    def test_rogue_medium_bab(self) -> None:
        reg = loaded_class_registry()
        r = reg.require("Rogue")
        assert r.bab_progression == BABProgression.MEDIUM

    def test_rogue_good_ref(self) -> None:
        reg = loaded_class_registry()
        r = reg.require("Rogue")
        assert r.save_progressions.ref == SaveProgression.GOOD

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

    def test_fighter_class_features_include_bonus_feats(
        self,
    ) -> None:
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
        # medium: floor(5*3/4)
        assert cl.bab_contribution == 3
        assert cl.fort_contribution == 4  # good: 2 + 5//2

    def test_no_duplicate_class_names(self) -> None:
        """
        Loading with overwrite=False would raise on
        dups."""
        reg = loaded_class_registry()
        assert len(reg) == 31

    def test_load_missing_file_raises(self, tmp_path: Path) -> None:
        from heroforge.rules.loader import (
            ClassesLoader,
            LoaderError,
        )

        with pytest.raises(LoaderError, match="not found"):
            ClassesLoader(tmp_path).load(ClassRegistry(), "core/classes")


# ===============================================================
# Character integration: race + class
# ===============================================================


class TestCharacterIntegration:
    def _load_registries(self) -> tuple:
        from heroforge.engine.races import (
            RaceRegistry,
            apply_race,
            remove_race,
        )
        from heroforge.rules.loader import RacesLoader

        race_reg = RaceRegistry()
        RacesLoader(RULES_DIR).load(race_reg, "core/races.yaml")
        class_reg = loaded_class_registry()
        return race_reg, class_reg, apply_race, remove_race

    def test_dwarf_fighter_saves(self) -> None:
        """
        Dwarf Fighter 4:
          STR 14 (mod +2), DEX 10,
          CON 14 (+2 racial) = 16 (mod +3)
          Fort = base(4) + con_mod(3) = 7 (good fort)
          Ref  = base(1) + dex_mod(0) = 1 (poor ref)
          Will = base(1) + wis_mod(0) = 1 (poor will)
        """
        race_reg, class_reg, apply_race, _ = self._load_registries()

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
        race_reg, class_reg, apply_race, _ = self._load_registries()

        c = fresh_char()
        apply_race(race_reg.require("Elf"), c)
        cl = class_reg.require("Wizard").make_class_level(6)
        c.set_class_levels([cl])

        assert c.bab == 3
        assert c.will == 5

    def test_halfling_rogue_speed(self) -> None:
        """
        Halfling has base speed 20; should be
        reflected."""
        race_reg, class_reg, apply_race, _ = self._load_registries()

        c = fresh_char()
        apply_race(race_reg.require("Halfling"), c)
        cl = class_reg.require("Rogue").make_class_level(3)
        c.set_class_levels([cl])

        assert c._race_base_speed == 20

    def test_half_orc_barbarian_str(self) -> None:
        """
        Half-Orc Barbarian 5:
          +2 STR racial. STR 14 base -> 16.
          STR mod = 3. Attack = bab(5) + str_mod(3) = 8.
        """
        race_reg, class_reg, apply_race, _ = self._load_registries()

        c = fresh_char()
        c.set_ability_score("str", 14)
        apply_race(race_reg.require("Half-Orc"), c)
        assert c.str_score == 16

        cl = class_reg.require("Barbarian").make_class_level(5)
        c.set_class_levels([cl])
        assert c.get("attack_melee") == 8  # bab 5 + str 3

    def test_human_fighter_multiclass_bab(self) -> None:
        """
        Human Fighter 4 / Wizard 4:
          Fighter BAB = 4 (full),
          Wizard BAB = 2 (poor).
          Combined BAB = 6.
        """
        race_reg, class_reg, apply_race, _ = self._load_registries()

        c = fresh_char()
        apply_race(race_reg.require("Human"), c)

        f_cl = class_reg.require("Fighter").make_class_level(4)
        w_cl = class_reg.require("Wizard").make_class_level(4)
        c.set_class_levels([f_cl, w_cl])

        assert c.bab == 6

    def test_gnome_small_size_ac(self) -> None:
        """
        Gnome is Small (+1 size AC).
        Size modifiers to AC are handled via the size
        pool -- for now verify the size_modifier property
        is correct.
        """
        race_reg, _, _, _ = self._load_registries()
        g = race_reg.require("Gnome")
        assert g.size_modifier == 1

    def test_remove_race_then_reapply(self) -> None:
        """
        Remove and re-apply a race produces the same
        state as one apply."""
        (
            race_reg,
            _,
            apply_race,
            remove_race,
        ) = self._load_registries()
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
