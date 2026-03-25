"""
tests/test_spells_yaml.py
-------------------------
Tests for spell compendium YAML files with buff effects.

Covers:
  - SpellCompendiumLoader registers spells into SpellCompendium
  - Spells with effects dual-register into BuffRegistry
  - Known spells have correct bonus types and targets
  - Formula spells resolve correctly at various caster levels
  - Condition keys attach the right callables
  - Mutually exclusive relationships are stored
  - apply_buff() with a registry-loaded definition produces
    correct stats
  - Stacking rules work correctly for loaded spells
"""

from __future__ import annotations

from pathlib import Path

from heroforge.engine.bonus import BonusType
from heroforge.engine.character import Character, ClassLevel
from heroforge.engine.effects import (
    BuffCategory,
    BuffRegistry,
    apply_buff,
    remove_buff,
)
from heroforge.engine.spells import SpellCompendium
from heroforge.rules.loader import SpellCompendiumLoader

RULES_DIR = Path(__file__).parent.parent / "src" / "heroforge" / "rules"

COMPENDIUM_FILES = (
    "core/spells_srd_0_3.yaml",
    "core/spells_srd_4_6.yaml",
    "core/spells_srd_7_9.yaml",
)


# ===========================================================
# Helpers
# ===========================================================


def loaded_registries() -> tuple[SpellCompendium, BuffRegistry]:
    comp = SpellCompendium()
    reg = BuffRegistry()
    loader = SpellCompendiumLoader(RULES_DIR)
    for f in COMPENDIUM_FILES:
        loader.load(comp, f, buff_registry=reg)
    return comp, reg


def fighter(n: int) -> list[ClassLevel]:
    return [
        ClassLevel(
            class_name="Fighter",
            level=n,
            hp_rolls=[10] * n,
            bab_contribution=n,
            fort_contribution=2 + n // 2,
            ref_contribution=n // 3,
            will_contribution=n // 3,
        )
    ]


def fresh_char(**kwargs: object) -> Character:
    return Character(**kwargs)


# ===========================================================
# Dual registration: compendium + buff registry
# ===========================================================


class TestDualRegistration:
    def setup_method(self) -> None:
        self.comp, self.reg = loaded_registries()

    def test_compendium_has_many_entries(self) -> None:
        assert len(self.comp) >= 500

    def test_bless_in_compendium(self) -> None:
        e = self.comp.get("Bless")
        assert e is not None
        assert e.level.get("Cleric") == 1

    def test_bless_in_buff_registry(self) -> None:
        b = self.reg.get("Bless")
        assert b is not None
        assert b.category == BuffCategory.SPELL

    def test_shield_of_faith_in_both(self) -> None:
        assert self.comp.get("Shield of Faith") is not None
        assert self.reg.get("Shield of Faith") is not None

    def test_fireball_not_in_buff_registry(self) -> None:
        """Fireball has no stat effects."""
        assert self.comp.get("Fireball") is not None
        assert self.reg.get("Fireball") is None

    def test_barkskin_in_both(self) -> None:
        assert self.comp.get("Barkskin") is not None
        assert self.reg.get("Barkskin") is not None

    def test_all_buff_spells_also_in_compendium(
        self,
    ) -> None:
        for name in self.reg.all_names():
            assert self.comp.get(name) is not None, (
                f"{name!r} in buff registry but not in compendium"
            )


# ===========================================================
# Specific spell definitions
# ===========================================================


class TestLoadedSpellDefinitions:
    def setup_method(self) -> None:
        _, self.reg = loaded_registries()

    def test_bless_morale_attack_all(self) -> None:
        b = self.reg.require("Bless")
        assert len(b.effects) == 1
        eff = b.effects[0]
        assert eff.target == "attack_all"
        assert eff.bonus_type == BonusType.MORALE
        assert eff.value == 1

    def test_haste_three_effects(self) -> None:
        b = self.reg.require("Haste")
        targets = {e.target for e in b.effects}
        assert "attack_all" in targets
        assert "ac" in targets
        assert "ref_save" in targets

    def test_haste_ac_is_dodge(self) -> None:
        b = self.reg.require("Haste")
        ac_eff = next(e for e in b.effects if e.target == "ac")
        assert ac_eff.bonus_type == BonusType.DODGE

    def test_bulls_strength_enhancement_str(
        self,
    ) -> None:
        b = self.reg.require("Bull's Strength")
        assert len(b.effects) == 1
        eff = b.effects[0]
        assert eff.target == "str_score"
        assert eff.bonus_type == BonusType.ENHANCEMENT
        assert eff.value == 4

    def test_divine_favor_is_formula(self) -> None:
        b = self.reg.require("Divine Favor")
        assert b.requires_caster_level is True
        for eff in b.effects:
            assert eff.is_formula()

    def test_divine_favor_attack_and_damage(
        self,
    ) -> None:
        b = self.reg.require("Divine Favor")
        targets = {e.target for e in b.effects}
        assert "attack_all" in targets
        assert "damage_all" in targets

    def test_shield_of_faith_deflection_formula(
        self,
    ) -> None:
        b = self.reg.require("Shield of Faith")
        assert b.requires_caster_level is True
        eff = b.effects[0]
        assert eff.target == "ac"
        assert eff.bonus_type == BonusType.DEFLECTION
        assert eff.is_formula()

    def test_prayer_five_effects(self) -> None:
        b = self.reg.require("Prayer")
        targets = {e.target for e in b.effects}
        assert targets == {
            "attack_all",
            "damage_all",
            "fort_save",
            "ref_save",
            "will_save",
        }

    def test_resistance_three_save_effects(
        self,
    ) -> None:
        b = self.reg.require("Resistance")
        targets = {e.target for e in b.effects}
        assert targets == {
            "fort_save",
            "ref_save",
            "will_save",
        }
        for eff in b.effects:
            assert eff.bonus_type == BonusType.RESISTANCE
            assert eff.value == 1

    def test_enlarge_person_has_condition(
        self,
    ) -> None:
        b = self.reg.require("Enlarge Person")
        for eff in b.effects:
            assert eff.condition is not None, (
                f"Enlarge Person effect {eff.target!r} missing condition"
            )

    def test_reduce_person_has_condition(
        self,
    ) -> None:
        b = self.reg.require("Reduce Person")
        for eff in b.effects:
            assert eff.condition is not None

    def test_greater_heroism_mx_with_heroism(
        self,
    ) -> None:
        b = self.reg.require("Heroism (Greater)")
        assert "Heroism" in b.mutually_exclusive_with

    def test_spells_are_spell_category(self) -> None:
        for name in (
            "Bless",
            "Haste",
            "Prayer",
            "Bull's Strength",
            "Shield of Faith",
            "Divine Favor",
        ):
            b = self.reg.require(name)
            assert b.category == BuffCategory.SPELL, (
                f"{name} should be SPELL category"
            )


# ===========================================================
# Formula resolution at various caster levels
# ===========================================================


class TestFormulaResolution:
    def setup_method(self) -> None:
        _, self.reg = loaded_registries()

    def test_divine_favor_cl3(self) -> None:
        df = self.reg.require("Divine Favor")
        pairs = df.pool_entries(caster_level=3)
        # max(1, 3//3) = 1
        for _, entry in pairs:
            assert entry.value == 1

    def test_divine_favor_cl6(self) -> None:
        df = self.reg.require("Divine Favor")
        pairs = df.pool_entries(caster_level=6)
        # max(1, 6//3) = 2
        for _, entry in pairs:
            assert entry.value == 2

    def test_divine_favor_cl9(self) -> None:
        df = self.reg.require("Divine Favor")
        pairs = df.pool_entries(caster_level=9)
        for _, entry in pairs:
            assert entry.value == 3

    def test_divine_favor_caps_at_nothing(
        self,
    ) -> None:
        df = self.reg.require("Divine Favor")
        pairs = df.pool_entries(caster_level=15)
        # formula: max(1, 15//3) = 5
        for _, entry in pairs:
            assert entry.value == 5

    def test_shield_of_faith_cl1(self) -> None:
        sof = self.reg.require("Shield of Faith")
        pairs = sof.pool_entries(caster_level=1)
        # 2 + 1//6 = 2
        assert pairs[0][1].value == 2

    def test_shield_of_faith_cl6(self) -> None:
        sof = self.reg.require("Shield of Faith")
        pairs = sof.pool_entries(caster_level=6)
        # 2 + 6//6 = 3
        assert pairs[0][1].value == 3

    def test_shield_of_faith_cl12(self) -> None:
        sof = self.reg.require("Shield of Faith")
        pairs = sof.pool_entries(caster_level=12)
        # 2 + 12//6 = 4
        assert pairs[0][1].value == 4

    def test_barkskin_cl3(self) -> None:
        b = self.reg.require("Barkskin")
        pairs = b.pool_entries(caster_level=3)
        # max(2, 1 + 3//3) = max(2, 2) = 2
        assert pairs[0][1].value == 2

    def test_barkskin_cl6(self) -> None:
        b = self.reg.require("Barkskin")
        pairs = b.pool_entries(caster_level=6)
        # max(2, 1 + 6//3) = max(2, 3) = 3
        assert pairs[0][1].value == 3

    def test_barkskin_cl12(self) -> None:
        b = self.reg.require("Barkskin")
        pairs = b.pool_entries(caster_level=12)
        # max(2, 1 + 12//3) = max(2, 5) = 5
        assert pairs[0][1].value == 5


# ===========================================================
# Integration: loaded spells applied to Character
# ===========================================================


class TestLoadedSpellsOnCharacter:
    def setup_method(self) -> None:
        _, self.reg = loaded_registries()
        self.char = fresh_char()
        self.char.set_class_levels(fighter(6))

    def _apply(self, name: str, cl: int = 0) -> None:
        defn = self.reg.require(name)
        apply_buff(defn, self.char, caster_level=cl)

    def _remove(self, name: str) -> None:
        defn = self.reg.require(name)
        remove_buff(defn, self.char)

    def test_bless_increases_attack(self) -> None:
        base = self.char.get("attack_melee")
        self._apply("Bless")
        assert self.char.get("attack_melee") == base + 1

    def test_bless_and_prayer_stacking(
        self,
    ) -> None:
        """Both morale -- Prayer's luck also applies."""
        base = self.char.get("attack_melee")
        self._apply("Bless")
        self._apply("Prayer")
        # morale max(1,1)=1 + luck(1) = 2
        assert self.char.get("attack_melee") == base + 2

    def test_bless_and_heroism_stack(self) -> None:
        """Bless +1 morale vs Heroism +2 morale."""
        base = self.char.get("attack_melee")
        self._apply("Bless")
        self._apply("Heroism")
        # morale max = 2 (Heroism wins)
        assert self.char.get("attack_melee") == base + 2

    def test_heroism_and_greater_heroism(
        self,
    ) -> None:
        """Heroism (Greater) +4 wins over Heroism +2."""
        base = self.char.get("attack_melee")
        self._apply("Heroism")
        self._apply("Heroism (Greater)")
        assert self.char.get("attack_melee") == base + 4

    def test_haste_plus_bless_stack(self) -> None:
        """Haste (untyped) and Bless (morale) stack."""
        base = self.char.get("attack_melee")
        self._apply("Haste")
        self._apply("Bless")
        assert self.char.get("attack_melee") == base + 2

    def test_haste_dodge_ac(self) -> None:
        base_ac = self.char.ac
        self._apply("Haste")
        assert self.char.ac == base_ac + 1

    def test_shield_of_faith_deflection_ac(
        self,
    ) -> None:
        base_ac = self.char.ac
        self._apply("Shield of Faith", cl=6)
        assert self.char.ac == base_ac + 3

    def test_bulls_strength_str_cascade(
        self,
    ) -> None:
        self.char.set_ability_score("str", 14)
        base_atk = self.char.get("attack_melee")
        self._apply("Bull's Strength")
        # str 14->18, mod 2->4, attack +2
        assert self.char.get("attack_melee") == base_atk + 2

    def test_divine_favor_at_two_cls(self) -> None:
        """Changing CL updates the buff value."""
        base = self.char.get("attack_melee")
        self._apply("Divine Favor", cl=6)  # +2
        assert self.char.get("attack_melee") == base + 2
        self._apply("Divine Favor", cl=9)  # +3
        assert self.char.get("attack_melee") == base + 3

    def test_remove_buff_reverts(self) -> None:
        base_atk = self.char.get("attack_melee")
        base_ac = self.char.ac
        self._apply("Haste")
        self._apply("Prayer")
        self._remove("Haste")
        self._remove("Prayer")
        assert self.char.get("attack_melee") == base_atk
        assert self.char.ac == base_ac

    def test_enlarge_person_humanoid(self) -> None:
        self.char._race_type = "Humanoid"
        self.char.set_ability_score("str", 14)
        self._apply("Enlarge Person")
        assert self.char.str_score == 16

    def test_enlarge_person_non_humanoid(
        self,
    ) -> None:
        self.char._race_type = "Undead"
        self.char.set_ability_score("str", 14)
        self._apply("Enlarge Person")
        assert self.char.str_score == 14

    def test_resistance_saves(self) -> None:
        base_fort = self.char.fort
        base_ref = self.char.ref
        base_will = self.char.will
        self._apply("Resistance")
        assert self.char.fort == base_fort + 1
        assert self.char.ref == base_ref + 1
        assert self.char.will == base_will + 1

    def test_complex_stack_five_buffs(self) -> None:
        """
        Bless (+1 morale atk),
        Prayer (+1 luck atk/dmg/saves),
        Haste (+1 untyped atk, +1 dodge AC),
        Shield of Faith CL12 (+4 deflection AC),
        Resistance (+1 resistance saves).
        Fighter 6: bab=6, str=10 (mod 0).
        attack_melee = 6+1+1+1 = 9
        ac = 10+1+4 = 15
        fort = 5+0+1+1 = 7
        """
        self._apply("Bless")
        self._apply("Prayer")
        self._apply("Haste")
        self._apply("Shield of Faith", cl=12)
        self._apply("Resistance")
        assert self.char.get("attack_melee") == 9
        assert self.char.ac == 15
        assert self.char.fort == 7
