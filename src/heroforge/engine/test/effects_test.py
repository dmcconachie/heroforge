"""
tests/test_effects.py
---------------------
Test suite for engine/effects.py.

Covers:
  - evaluate_formula(): all variable bindings, error handling, edge cases
  - BonusEffect: static and formula values, to_bonus_entry(), conditions
  - BuffDefinition: construction, auto-detect CL, pool_entries() expansion
  - BuffRegistry: register, get, require, overwrite, category/book queries
  - apply_buff() / remove_buff(): full integration with Character
  - Multi-target expansion (attack_all → melee + ranged)
  - Mutually exclusive buff detection (checked by validator, not engine)
  - Real 3.5e spell scenarios end-to-end
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

from heroforge.engine.bonus import BonusType
from heroforge.engine.character import Character, CharacterLevel
from heroforge.engine.effects import (
    BonusEffect,
    BuffCategory,
    BuffDefinition,
    BuffRegistry,
    FormulaError,
    apply_buff,
    evaluate_formula,
    remove_buff,
)

# ===========================================================================
# Helpers
# ===========================================================================


def fighter(n: int) -> list[CharacterLevel]:
    return [
        CharacterLevel(
            character_level=i + 1,
            class_name="Fighter",
            hp_roll=10,
        )
        for i in range(n)
    ]


def fresh_char(**kwargs: object) -> Character:
    c = Character(**kwargs)
    return c


def simple_effect(
    target: str = "attack_melee",
    value: int | str = 1,
    btype: BonusType = BonusType.MORALE,
    condition: Callable | None = None,
    label: str = "",
) -> BonusEffect:
    eff = BonusEffect(
        target=target,
        bonus_type=btype,
        value=value,
        source_label=label,
    )
    eff.condition = condition
    return eff


def _cond_effect() -> BonusEffect:
    """BonusEffect with a humanoid-only condition."""
    eff = BonusEffect(
        target="str_score",
        bonus_type=BonusType.ENHANCEMENT,
        value=2,
    )
    eff.condition = lambda char: getattr(char, "_race_type", "") == "Humanoid"
    return eff


def simple_buff(
    name: str,
    effects: list[BonusEffect] | None = None,
    category: BuffCategory = BuffCategory.SPELL,
    book: str = "PHB",
) -> BuffDefinition:
    return BuffDefinition(
        name=name,
        category=category,
        source_book=book,
        effects=effects or [simple_effect()],
    )


# ===========================================================================
# evaluate_formula
# ===========================================================================


class TestEvaluateFormula:
    def test_static_integer_expression(self) -> None:
        assert evaluate_formula("4") == 4

    def test_caster_level_variable(self) -> None:
        assert evaluate_formula("caster_level", caster_level=6) == 6

    def test_caster_level_scaling_divine_favor(self) -> None:
        """Divine Favor: max(1, CL // 3)"""
        assert (
            evaluate_formula("max(1, caster_level // 3)", caster_level=3) == 1
        )
        assert (
            evaluate_formula("max(1, caster_level // 3)", caster_level=6) == 2
        )
        assert (
            evaluate_formula("max(1, caster_level // 3)", caster_level=9) == 3
        )

    def test_shield_of_faith_formula(self) -> None:
        """Shield of Faith: floor(2 + CL / 6)"""
        assert evaluate_formula("2 + caster_level // 6", caster_level=1) == 2
        assert evaluate_formula("2 + caster_level // 6", caster_level=6) == 3
        assert evaluate_formula("2 + caster_level // 6", caster_level=12) == 4

    def test_min_cap_formula(self) -> None:
        """Heart of Earth: min(30, CL * 2)"""
        assert (
            evaluate_formula("min(30, caster_level * 2)", caster_level=10) == 20
        )
        assert (
            evaluate_formula("min(30, caster_level * 2)", caster_level=20) == 30
        )

    def test_floor_function(self) -> None:
        assert evaluate_formula("floor(7 / 2)") == 3

    def test_ceil_function(self) -> None:
        assert evaluate_formula("ceil(7 / 2)") == 4

    def test_abs_function(self) -> None:
        assert evaluate_formula("abs(-5)") == 5

    def test_boolean_as_int(self) -> None:
        """Python bool is int subclass — useful for conditional scaling."""
        assert (
            evaluate_formula("4 + 2 * (caster_level >= 12)", caster_level=12)
            == 6
        )
        assert (
            evaluate_formula("4 + 2 * (caster_level >= 12)", caster_level=6)
            == 4
        )

    def test_caster_level_zero_when_not_provided(self) -> None:
        assert evaluate_formula("caster_level") == 0

    def test_character_level_from_character(self) -> None:
        c = fresh_char()
        c.set_class_levels(fighter(5))
        assert evaluate_formula("character_level", character=c) == 5

    def test_ability_modifier_from_character(self) -> None:
        c = fresh_char()
        c.set_ability_score("str", 18)  # mod = 4
        assert evaluate_formula("str_mod", character=c) == 4

    def test_ability_modifiers_zero_without_character(self) -> None:
        for ab in ("str", "dex", "con", "int", "wis", "cha"):
            assert evaluate_formula(f"{ab}_mod") == 0

    def test_bab_from_character(self) -> None:
        c = fresh_char()
        c.set_class_levels(fighter(6))
        assert evaluate_formula("bab", character=c) == 6

    def test_extra_context_injected(self) -> None:
        result = evaluate_formula("x + y", extra={"x": 3, "y": 7})
        assert result == 10

    def test_result_truncated_to_int(self) -> None:
        """Float results are truncated to int."""
        assert evaluate_formula("int(3.9)") == 3

    def test_syntax_error_raises_formula_error(self) -> None:
        with pytest.raises(FormulaError, match="Syntax error"):
            evaluate_formula("2 +* 3")

    def test_name_error_raises_formula_error(self) -> None:
        with pytest.raises(FormulaError):
            evaluate_formula("undefined_name")

    def test_no_builtins_access(self) -> None:
        """__import__ and other builtins must not be accessible."""
        with pytest.raises(FormulaError):
            evaluate_formula("__import__('os')")

    def test_no_open_access(self) -> None:
        with pytest.raises(FormulaError):
            evaluate_formula("open('/etc/passwd')")

    def test_formula_returning_non_numeric_raises(self) -> None:
        with pytest.raises(FormulaError, match="non-numeric"):
            evaluate_formula("'hello'")

    def test_result_is_always_int_not_float(self) -> None:
        result = evaluate_formula("10 / 2")
        assert isinstance(result, int)
        assert result == 5

    def test_negative_formula_result(self) -> None:
        assert evaluate_formula("caster_level - 10", caster_level=6) == -4

    def test_owl_insight_formula(self) -> None:
        """Owl's Insight: floor(CL / 2) to WIS score."""
        assert evaluate_formula("floor(caster_level / 2)", caster_level=9) == 4
        assert evaluate_formula("floor(caster_level / 2)", caster_level=10) == 5


# ===========================================================================
# BonusEffect
# ===========================================================================


class TestBonusEffect:
    def test_static_value_is_not_formula(self) -> None:
        e = simple_effect(value=4)
        assert not e.is_formula()

    def test_string_value_is_formula(self) -> None:
        e = simple_effect(value="caster_level // 3")
        assert e.is_formula()

    def test_resolve_static_value(self) -> None:
        e = simple_effect(value=4)
        assert e.resolve_value() == 4

    def test_resolve_formula_value(self) -> None:
        e = simple_effect(value="max(1, caster_level // 3)")
        assert e.resolve_value(caster_level=6) == 2

    def test_to_bonus_entry_static(self) -> None:
        e = BonusEffect(
            target="attack_melee",
            bonus_type=BonusType.MORALE,
            value=2,
            source_label="Bless",
        )
        entry = e.to_bonus_entry("Bless")
        assert entry.value == 2
        assert entry.bonus_type == BonusType.MORALE
        assert entry.source == "Bless"

    def test_to_bonus_entry_formula(self) -> None:
        e = BonusEffect(
            target="fort_save",
            bonus_type=BonusType.RESISTANCE,
            value="caster_level // 3",
            source_label="Resistance",
        )
        entry = e.to_bonus_entry("Resistance", caster_level=9)
        assert entry.value == 3

    def test_to_bonus_entry_uses_source_label_over_parent_name(self) -> None:
        e = BonusEffect(
            target="ac",
            bonus_type=BonusType.DEFLECTION,
            value=2,
            source_label="Custom Label",
        )
        entry = e.to_bonus_entry("Parent Name")
        assert entry.source == "Custom Label"

    def test_to_bonus_entry_falls_back_to_parent_name(self) -> None:
        e = BonusEffect(target="ac", bonus_type=BonusType.DEFLECTION, value=2)
        entry = e.to_bonus_entry("Shield of Faith")
        assert entry.source == "Shield of Faith"

    def test_to_bonus_entry_preserves_condition(self) -> None:
        def cond(c: object) -> bool:
            return c is not None

        e = BonusEffect(
            target="str_score",
            bonus_type=BonusType.ENHANCEMENT,
            value=2,
        )
        e.condition = cond
        entry = e.to_bonus_entry("Enlarge Person")
        assert entry.condition is cond


# ===========================================================================
# BuffDefinition
# ===========================================================================


class TestBuffDefinition:
    def test_construction_basic(self) -> None:
        b = simple_buff("Bless")
        assert b.name == "Bless"
        assert b.category == BuffCategory.SPELL
        assert b.source_book == "PHB"
        assert len(b.effects) == 1

    def test_auto_detect_requires_caster_level_false(self) -> None:
        b = simple_buff("Bless", [simple_effect(value=1)])
        assert b.requires_caster_level is False

    def test_auto_detect_requires_caster_level_true(self) -> None:
        b = simple_buff(
            "Divine Favor", [simple_effect(value="max(1, caster_level // 3)")]
        )
        assert b.requires_caster_level is True

    def test_explicit_requires_caster_level_respected(self) -> None:
        b = BuffDefinition(
            name="Test",
            category=BuffCategory.SPELL,
            effects=[simple_effect(value=1)],
            requires_caster_level=True,  # explicit override
        )
        assert b.requires_caster_level is True

    def test_pool_entries_single_effect(self) -> None:
        b = simple_buff(
            "Bless", [BonusEffect("attack_melee", BonusType.MORALE, 1)]
        )
        pairs = b.pool_entries()
        assert len(pairs) == 1
        pool_key, entry = pairs[0]
        assert pool_key == "attack_melee"
        assert entry.value == 1

    def test_pool_entries_attack_all_expands(self) -> None:
        """attack_all should expand to attack_melee AND attack_ranged."""
        b = simple_buff(
            "Haste", [BonusEffect("attack_all", BonusType.UNTYPED, 1)]
        )
        pairs = b.pool_entries()
        keys = [pk for pk, _ in pairs]
        assert "attack_melee" in keys
        assert "attack_ranged" in keys
        assert len(keys) == 2

    def test_pool_entries_damage_all_expands(self) -> None:
        b = simple_buff(
            "Inspire Courage", [BonusEffect("damage_all", BonusType.MORALE, 2)]
        )
        pairs = b.pool_entries()
        keys = [pk for pk, _ in pairs]
        assert "damage_melee" in keys
        assert "damage_ranged" in keys

    def test_pool_entries_multiple_effects(self) -> None:
        """Haste: attack + dodge AC + speed."""
        b = BuffDefinition(
            name="Haste",
            category=BuffCategory.SPELL,
            effects=[
                BonusEffect("attack_all", BonusType.UNTYPED, 1),
                BonusEffect("ac", BonusType.DODGE, 1),
                BonusEffect("speed", BonusType.UNTYPED, 30),
            ],
        )
        pairs = b.pool_entries()
        keys = [pk for pk, _ in pairs]
        assert "attack_melee" in keys
        assert "attack_ranged" in keys
        assert "ac" in keys
        assert "speed" in keys
        assert len(pairs) == 4  # 2 from attack_all + 1 ac + 1 speed

    def test_pool_entries_with_caster_level(self) -> None:
        b = BuffDefinition(
            name="Divine Favor",
            category=BuffCategory.SPELL,
            effects=[
                BonusEffect(
                    "attack_all", BonusType.LUCK, "max(1, caster_level // 3)"
                )
            ],
        )
        pairs = b.pool_entries(caster_level=6)
        # attack_all expands to 2 pairs, both with value 2
        assert all(entry.value == 2 for _, entry in pairs)

    def test_pool_entries_formula_zero_cl(self) -> None:
        b = BuffDefinition(
            name="Test",
            category=BuffCategory.SPELL,
            effects=[
                BonusEffect("ac", BonusType.DEFLECTION, "caster_level // 3")
            ],
        )
        pairs = b.pool_entries(caster_level=0)
        _, entry = pairs[0]
        assert entry.value == 0

    def test_mutually_exclusive_with_stored(self) -> None:
        b = BuffDefinition(
            name="Greater Rage",
            category=BuffCategory.CLASS,
            effects=[],
            mutually_exclusive_with=["Rage"],
        )
        assert "Rage" in b.mutually_exclusive_with


# ===========================================================================
# BuffRegistry
# ===========================================================================


class TestBuffRegistry:
    def test_register_and_get(self) -> None:
        r = BuffRegistry()
        b = simple_buff("Bless")
        r.register(b)
        assert r.get("Bless") is b

    def test_get_unknown_returns_none(self) -> None:
        r = BuffRegistry()
        assert r.get("Unknown") is None

    def test_require_unknown_raises(self) -> None:
        r = BuffRegistry()
        with pytest.raises(KeyError, match="No BuffDefinition"):
            r.require("Unknown")

    def test_require_known_returns_def(self) -> None:
        r = BuffRegistry()
        b = simple_buff("Bless")
        r.register(b)
        assert r.require("Bless") is b

    def test_duplicate_registration_raises(self) -> None:
        r = BuffRegistry()
        r.register(simple_buff("Bless"))
        with pytest.raises(ValueError, match="already registered"):
            r.register(simple_buff("Bless"))

    def test_overwrite_replaces_definition(self) -> None:
        r = BuffRegistry()
        b1 = simple_buff("Bless", book="PHB")
        b2 = simple_buff("Bless", book="SpC")
        r.register(b1)
        r.register(b2, overwrite=True)
        assert r.require("Bless").source_book == "SpC"

    def test_contains_operator(self) -> None:
        r = BuffRegistry()
        r.register(simple_buff("Bless"))
        assert "Bless" in r
        assert "Prayer" not in r

    def test_len(self) -> None:
        r = BuffRegistry()
        assert len(r) == 0
        r.register(simple_buff("Bless"))
        r.register(simple_buff("Prayer"))
        assert len(r) == 2

    def test_all_names_sorted(self) -> None:
        r = BuffRegistry()
        r.register(simple_buff("Prayer"))
        r.register(simple_buff("Bless"))
        r.register(simple_buff("Haste"))
        assert r.all_names() == ["Bless", "Haste", "Prayer"]

    def test_by_category(self) -> None:
        r = BuffRegistry()
        r.register(simple_buff("Bless", category=BuffCategory.SPELL))
        r.register(simple_buff("Rage", category=BuffCategory.CLASS))
        r.register(simple_buff("Shaken", category=BuffCategory.CONDITION))
        spells = r.by_category(BuffCategory.SPELL)
        assert len(spells) == 1
        assert spells[0].name == "Bless"

    def test_by_source_book(self) -> None:
        r = BuffRegistry()
        r.register(simple_buff("Bless", book="PHB"))
        r.register(simple_buff("Conviction", book="SpC"))
        r.register(simple_buff("Crown of Might", book="SpC"))
        spc = r.by_source_book("SpC")
        names = {b.name for b in spc}
        assert names == {"Conviction", "Crown of Might"}


# ===========================================================================
# apply_buff / remove_buff
# ===========================================================================


class TestApplyRemoveBuff:
    def test_apply_buff_activates_on_character(self) -> None:
        c = fresh_char()
        b = simple_buff(
            "Bless", [BonusEffect("attack_melee", BonusType.MORALE, 1)]
        )
        apply_buff(b, c)
        assert c.is_buff_active("Bless")

    def test_apply_buff_changes_stat(self) -> None:
        c = fresh_char()
        c.set_class_levels(fighter(4))
        base = c.get("attack_melee")
        b = simple_buff(
            "Bless", [BonusEffect("attack_melee", BonusType.MORALE, 1)]
        )
        apply_buff(b, c)
        assert c.get("attack_melee") == base + 1

    def test_remove_buff_reverts_stat(self) -> None:
        c = fresh_char()
        c.set_class_levels(fighter(4))
        base = c.get("attack_melee")
        b = simple_buff(
            "Bless", [BonusEffect("attack_melee", BonusType.MORALE, 1)]
        )
        apply_buff(b, c)
        remove_buff(b, c)
        assert c.get("attack_melee") == base

    def test_remove_buff_not_registered_is_noop(self) -> None:
        c = fresh_char()
        b = simple_buff("Ghost Buff")
        # Should not raise
        result = remove_buff(b, c)
        assert result == set()

    def test_apply_buff_idempotent(self) -> None:
        c = fresh_char()
        c.set_class_levels(fighter(4))
        b = simple_buff(
            "Bless", [BonusEffect("attack_melee", BonusType.MORALE, 1)]
        )
        apply_buff(b, c)
        val_once = c.get("attack_melee")
        apply_buff(b, c)
        apply_buff(b, c)
        assert c.get("attack_melee") == val_once

    def test_apply_buff_with_caster_level(self) -> None:
        c = fresh_char()
        b = BuffDefinition(
            name="Divine Favor",
            category=BuffCategory.SPELL,
            effects=[
                BonusEffect(
                    "attack_all", BonusType.LUCK, "max(1, caster_level // 3)"
                )
            ],
        )
        apply_buff(b, c, caster_level=6)
        assert c.get_buff_state("Divine Favor").caster_level == 6
        # attack bonus = BAB(0) + STR_mod(0) + luck(2) = 2
        assert c.get("attack_melee") == 2

    def test_apply_buff_attack_all_affects_both(self) -> None:
        """attack_all expansion: both melee and ranged should improve."""
        c = fresh_char()
        c.set_class_levels(fighter(5))
        melee_base = c.get("attack_melee")
        ranged_base = c.get("attack_ranged")
        b = BuffDefinition(
            name="Haste",
            category=BuffCategory.SPELL,
            effects=[BonusEffect("attack_all", BonusType.UNTYPED, 1)],
        )
        apply_buff(b, c)
        assert c.get("attack_melee") == melee_base + 1
        assert c.get("attack_ranged") == ranged_base + 1

    def test_stacking_rules_respected_via_apply(self) -> None:
        """Two morale buffs via apply_buff: only higher counts."""
        c = fresh_char()
        c.set_class_levels(fighter(4))
        base = c.get("attack_melee")

        bless = simple_buff(
            "Bless", [BonusEffect("attack_melee", BonusType.MORALE, 1)]
        )
        prayer = simple_buff(
            "Prayer", [BonusEffect("attack_melee", BonusType.MORALE, 2)]
        )
        apply_buff(bless, c)
        apply_buff(prayer, c)

        # morale max = 2, not 1+2 = 3
        assert c.get("attack_melee") == base + 2

    def test_conditional_effect_via_apply(self) -> None:
        """Enlarge Person only works on humanoids."""
        c = fresh_char()
        c._race_type = "Humanoid"
        c.set_ability_score("str", 12)

        b = BuffDefinition(
            name="Enlarge Person",
            category=BuffCategory.SPELL,
            effects=[_cond_effect()],
        )
        apply_buff(b, c)
        assert c.str_score == 14

    def test_conditional_effect_inactive_on_wrong_type(self) -> None:
        c = fresh_char()
        c._race_type = "Undead"
        c.set_ability_score("str", 12)

        b = BuffDefinition(
            name="Enlarge Person",
            category=BuffCategory.SPELL,
            effects=[_cond_effect()],
        )
        apply_buff(b, c)
        assert c.str_score == 12  # condition False → +2 not applied

    def test_apply_returns_invalidated_keys(self) -> None:
        c = fresh_char()
        b = simple_buff(
            "Bless", [BonusEffect("attack_melee", BonusType.MORALE, 1)]
        )
        keys = apply_buff(b, c)
        assert len(keys) > 0
        assert "attack_melee" in keys


# ===========================================================================
# Real 3.5e buff scenarios end-to-end
# ===========================================================================


class TestRealBuffScenarios:
    def test_bless_morale_attack(self) -> None:
        """Bless: +1 morale to attack rolls and saves vs. fear."""
        c = fresh_char()
        c.set_class_levels(fighter(4))  # bab = 4, str = 10 (mod 0)
        bless = BuffDefinition(
            name="Bless",
            category=BuffCategory.SPELL,
            source_book="PHB",
            effects=[BonusEffect("attack_melee", BonusType.MORALE, 1)],
        )
        assert c.get("attack_melee") == 4
        apply_buff(bless, c)
        assert c.get("attack_melee") == 5
        remove_buff(bless, c)
        assert c.get("attack_melee") == 4

    def test_divine_favor_scales_with_cl(self) -> None:
        """Divine Favor: luck bonus = max(1, CL // 3) to attack and damage."""
        c = fresh_char()
        c.set_class_levels(fighter(6))
        df = BuffDefinition(
            name="Divine Favor",
            category=BuffCategory.SPELL,
            source_book="PHB",
            effects=[
                BonusEffect(
                    "attack_all", BonusType.LUCK, "max(1, caster_level // 3)"
                ),
                BonusEffect(
                    "damage_all", BonusType.LUCK, "max(1, caster_level // 3)"
                ),
            ],
        )
        base_atk = c.get("attack_melee")
        apply_buff(df, c, caster_level=9)
        # luck bonus at CL 9 = max(1, 9//3) = 3
        assert c.get("attack_melee") == base_atk + 3

    def test_shield_of_faith_deflection_ac(self) -> None:
        """Shield of Faith: deflection = floor(2 + CL/6)."""
        c = fresh_char()
        sof = BuffDefinition(
            name="Shield of Faith",
            category=BuffCategory.SPELL,
            source_book="PHB",
            effects=[
                BonusEffect("ac", BonusType.DEFLECTION, "2 + caster_level // 6")
            ],
        )
        assert c.ac == 10
        apply_buff(sof, c, caster_level=6)
        assert c.ac == 13  # 10 + 3

    def test_haste_attack_and_ac(self) -> None:
        """Haste: +1 untyped attack, +1 dodge AC."""
        c = fresh_char()
        c.set_class_levels(fighter(5))
        haste = BuffDefinition(
            name="Haste",
            category=BuffCategory.SPELL,
            source_book="PHB",
            effects=[
                BonusEffect("attack_all", BonusType.UNTYPED, 1),
                BonusEffect("ac", BonusType.DODGE, 1),
            ],
        )
        melee_before = c.get("attack_melee")
        ranged_before = c.get("attack_ranged")
        ac_before = c.ac
        apply_buff(haste, c)
        assert c.get("attack_melee") == melee_before + 1
        assert c.get("attack_ranged") == ranged_before + 1
        assert c.ac == ac_before + 1

    def test_bulls_strength_str_cascade(self) -> None:
        """Bull's Strength: +4 enhancement to STR → flows to melee attack."""
        c = fresh_char()
        c.set_ability_score("str", 14)  # mod = 2
        c.set_class_levels(fighter(5))  # bab = 5
        assert c.get("attack_melee") == 7  # 5 + 2

        bs = BuffDefinition(
            name="Bull's Strength",
            category=BuffCategory.SPELL,
            source_book="PHB",
            effects=[BonusEffect("str_score", BonusType.ENHANCEMENT, 4)],
        )
        apply_buff(bs, c)
        # str = 18, mod = 4, attack = 5 + 4 = 9
        assert c.str_score == 18
        assert c.str_mod == 4
        assert c.get("attack_melee") == 9

    def test_rage_morale_str_and_con(self) -> None:
        """
        Barbarian Rage: +4 morale to STR and CON, -2 AC (untyped).
        (PHB actually calls Rage bonuses morale for STR/CON.)
        """
        c = fresh_char()
        c.set_ability_score("str", 16)  # mod = 3
        c.set_ability_score("con", 14)  # mod = 2
        c.set_class_levels(fighter(4))

        rage = BuffDefinition(
            name="Rage",
            category=BuffCategory.CLASS,
            source_book="PHB",
            effects=[
                BonusEffect("str_score", BonusType.MORALE, 4),
                BonusEffect("con_score", BonusType.MORALE, 4),
                BonusEffect("ac", BonusType.UNTYPED, -2),
            ],
        )
        apply_buff(rage, c)
        assert c.str_score == 20  # 16 + 4
        assert c.str_mod == 5
        assert c.con_score == 18  # 14 + 4
        assert c.ac == 8  # 10 + dex(0) + penalty(-2)

    def test_shaken_condition_penalty(self) -> None:
        """Shaken: -2 untyped to attack, saves, checks."""
        c = fresh_char()
        c.set_class_levels(fighter(4))
        shaken = BuffDefinition(
            name="Shaken",
            category=BuffCategory.CONDITION,
            source_book="PHB",
            effects=[
                BonusEffect("attack_melee", BonusType.UNTYPED, -2),
                BonusEffect("attack_ranged", BonusType.UNTYPED, -2),
                BonusEffect("fort_save", BonusType.UNTYPED, -2),
                BonusEffect("ref_save", BonusType.UNTYPED, -2),
                BonusEffect("will_save", BonusType.UNTYPED, -2),
            ],
        )
        apply_buff(shaken, c)
        assert c.get("attack_melee") == 4 - 2  # bab 4, penalty -2 = 2
        # Fighter 4: fort = base(4) + con_mod(0) - shaken(2) = 2
        assert c.fort == 2

    def test_inspire_courage_stacks_with_haste(self) -> None:
        """Morale (Inspire Courage) and Untyped (Haste) both apply."""
        c = fresh_char()
        c.set_class_levels(fighter(6))
        base = c.get("attack_melee")

        ic = BuffDefinition(
            name="Inspire Courage",
            category=BuffCategory.CLASS,
            effects=[BonusEffect("attack_all", BonusType.MORALE, 2)],
        )
        haste = BuffDefinition(
            name="Haste",
            category=BuffCategory.SPELL,
            effects=[BonusEffect("attack_all", BonusType.UNTYPED, 1)],
        )
        apply_buff(ic, c)
        apply_buff(haste, c)
        # morale +2, untyped +1 → total +3 from buffs
        assert c.get("attack_melee") == base + 3
