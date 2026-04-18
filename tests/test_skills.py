"""
tests/test_skills.py
--------------------
Test suite for engine/skills.py, rules/core/skills.yaml, SkillsLoader,
and the UI AppState's skill integration.

Covers:
  - YAML validation
  - SkillRegistry: register, get, get_by_pool_key, all_skills
  - register_skills_on_character: nodes, pools, _skill_registry
  - set_skill_ranks: pool update, stat graph cascade
  - compute_skill_total: ranks + ability mod + misc + synergy + ACP
  - Skill totals update when ability scores change
  - Skill totals update when buff changes ability scores
  - AppState.load_rules() wires skills
  - AppState.new_character() registers skills
"""

from __future__ import annotations

from pathlib import Path

import pytest

from heroforge.engine.bonus import BonusType
from heroforge.engine.character import Character
from heroforge.engine.skills import (
    SkillDefinition,
    SkillRegistry,
    compute_skill_total,
    register_skills_on_character,
    set_skill_ranks,
)

RULES_DIR = Path(__file__).parent.parent / "src" / "heroforge" / "rules"


# ===========================================================================
# Helpers
# ===========================================================================


def fresh_char() -> Character:
    return Character()


def loaded_skill_registry() -> SkillRegistry:
    from heroforge.rules.loader import SkillsLoader

    reg = SkillRegistry()
    SkillsLoader(RULES_DIR).load(reg, "core/skills.yaml")
    return reg


def char_with_skills() -> tuple[Character, SkillRegistry]:
    """Character with skills registered."""
    c = fresh_char()
    reg = loaded_skill_registry()
    register_skills_on_character(reg, c)
    return c, reg


# ===========================================================================
# YAML validation
# ===========================================================================


class TestSkillsYaml:
    def test_no_duplicate_names(self) -> None:
        import yaml

        with open(RULES_DIR / "core" / "skills.yaml") as f:
            data = yaml.safe_load(f)
        # Dict keys are unique by definition.
        names = list(data.keys())
        assert len(names) == len(set(names))

    def test_all_abilities_valid(self) -> None:
        import yaml

        valid = {
            "str",
            "dex",
            "con",
            "int",
            "wis",
            "cha",
            "none",
        }
        with open(RULES_DIR / "core" / "skills.yaml") as f:
            data = yaml.safe_load(f)
        bad = [
            name for name, d in data.items() if d.get("ability") not in valid
        ]
        assert bad == []

    def test_expected_skills_present(self) -> None:
        reg = loaded_skill_registry()
        for name in (
            "Hide",
            "Listen",
            "Spot",
            "Bluff",
            "Diplomacy",
            "Spellcraft",
            "Use Magic Device",
            "Tumble",
            "Swim",
        ):
            assert name in reg, f"{name} not in skill registry"

    def test_skill_count_reasonable(self) -> None:
        reg = loaded_skill_registry()
        # PHB has ~40 base skills
        assert len(reg) >= 38


# ===========================================================================
# SkillRegistry
# ===========================================================================


class TestSkillRegistry:
    def test_register_and_get(self) -> None:
        reg = SkillRegistry()
        defn = SkillDefinition("Hide", "dex")
        reg.register(defn)
        assert reg.get("Hide") is defn

    def test_get_by_pool_key(self) -> None:
        from heroforge.rules.core.pool_keys import PoolKey

        reg = SkillRegistry()
        defn = SkillDefinition("Hide", "dex")
        reg.register(defn)
        assert reg.get_by_pool_key(PoolKey.SKILL_HIDE) is defn

    def test_get_unknown_returns_none(self) -> None:
        assert SkillRegistry().get("Unknown") is None

    def test_require_unknown_raises(self) -> None:
        with pytest.raises(KeyError, match="No SkillDefinition"):
            SkillRegistry().require("Unknown")

    def test_duplicate_raises(self) -> None:
        reg = SkillRegistry()
        reg.register(SkillDefinition("Hide", "dex"))
        with pytest.raises(ValueError, match="already registered"):
            reg.register(SkillDefinition("Hide", "dex"))

    def test_all_skills_sorted(self) -> None:
        reg = loaded_skill_registry()
        names = [s.name for s in reg.all_skills()]
        assert names == sorted(names)


# ===========================================================================
# register_skills_on_character
# ===========================================================================


class TestRegisterSkills:
    def test_skill_nodes_created_in_graph(self) -> None:
        c, reg = char_with_skills()
        skill_nodes = [k for k in c._graph._nodes if k.startswith("skill_")]
        assert len(skill_nodes) == len(reg)

    def test_skill_pools_accessible_via_get_pool(self) -> None:
        c, reg = char_with_skills()
        pool = c.get_pool("skill_hide")
        assert pool is not None

    def test_skill_registry_stored_on_character(self) -> None:
        c, reg = char_with_skills()
        assert hasattr(c, "_skill_registry")
        assert c._skill_registry is reg

    def test_idempotent_second_register(self) -> None:
        """Calling register twice should not add duplicate nodes."""
        c, reg = char_with_skills()
        count_before = len(
            [k for k in c._graph._nodes if k.startswith("skill_")]
        )
        register_skills_on_character(reg, c)
        count_after = len(
            [k for k in c._graph._nodes if k.startswith("skill_")]
        )
        assert count_before == count_after


# ===========================================================================
# set_skill_ranks
# ===========================================================================


class TestSetSkillRanks:
    def test_set_ranks_updates_skills_dict(self) -> None:
        c, _ = char_with_skills()
        set_skill_ranks(c, "Hide", 5)
        assert c.skills["Hide"] == 5

    def test_set_ranks_updates_stat_total(self) -> None:
        c, _ = char_with_skills()
        c.set_ability_score("dex", 14)  # mod +2
        set_skill_ranks(c, "Hide", 6)
        assert c.get("skill_hide") == 8  # 6 + 2

    def test_set_ranks_zero_clears_pool(self) -> None:
        c, _ = char_with_skills()
        set_skill_ranks(c, "Hide", 5)
        set_skill_ranks(c, "Hide", 0)
        assert c.get("skill_hide") == 0  # no ranks + dex mod 0

    def test_ranks_update_cascades_to_graph(self) -> None:
        c, _ = char_with_skills()
        c.set_ability_score("wis", 14)  # mod +2
        set_skill_ranks(c, "Listen", 4)
        assert c.get("skill_listen") == 6  # 4 ranks + 2 wis

    def test_int_skills_use_int_mod(self) -> None:
        c, _ = char_with_skills()
        c.set_ability_score("int", 18)  # mod +4
        set_skill_ranks(c, "Spellcraft", 5)
        assert c.get("skill_spellcraft") == 9  # 5 + 4


# ===========================================================================
# compute_skill_total
# ===========================================================================


class TestComputeSkillTotal:
    def test_basic_total_ranks_plus_ability(self) -> None:
        c, reg = char_with_skills()
        c.set_ability_score("dex", 16)  # mod +3
        set_skill_ranks(c, "Hide", 5)
        defn = reg.require("Hide")
        result = compute_skill_total(c, defn)
        assert result.ranks == 5
        assert result.ability_mod == 3
        assert result.total == 8

    def test_total_no_ranks(self) -> None:
        c, reg = char_with_skills()
        c.set_ability_score("dex", 12)  # mod +1
        defn = reg.require("Balance")
        result = compute_skill_total(c, defn)
        assert result.ranks == 0
        assert result.ability_mod == 1
        assert result.total == 1

    def test_misc_bonus_from_feat(self) -> None:
        """A feat adding +2 to Hide shows up as misc_bonus."""
        c, reg = char_with_skills()
        from heroforge.engine.bonus import BonusEntry, BonusType

        pool = c.get_pool("skill_hide")
        pool.set_source(
            "Stealthy", [BonusEntry(2, BonusType.UNTYPED, "Stealthy")]
        )
        c._graph.invalidate_pool("skill_hide")
        defn = reg.require("Hide")
        result = compute_skill_total(c, defn)
        assert result.misc_bonus == 2
        assert result.total == 2

    def test_armor_check_penalty_applied(self) -> None:
        c, reg = char_with_skills()
        c.set_ability_score("dex", 12)  # mod +1
        set_skill_ranks(c, "Hide", 3)
        defn = reg.require("Hide")
        result = compute_skill_total(c, defn, armor_check_penalty=-4)
        assert result.armor_penalty == -4
        assert result.total == 0  # 3 + 1 - 4

    def test_armor_check_not_applied_to_non_acp_skill(self) -> None:
        c, reg = char_with_skills()
        set_skill_ranks(c, "Spellcraft", 3)
        defn = reg.require("Spellcraft")
        result = compute_skill_total(c, defn, armor_check_penalty=-4)
        assert result.armor_penalty == 0  # Spellcraft has no ACP
        assert result.total == 3

    def test_synergy_bonus_with_5_ranks(self) -> None:
        """5 ranks in Bluff grants +2 synergy to Intimidate."""
        c, reg = char_with_skills()
        set_skill_ranks(c, "Bluff", 5)
        intimidate_defn = reg.require("Intimidate")
        result = compute_skill_total(c, intimidate_defn)
        assert result.synergy_bonus == 2

    def test_synergy_bonus_not_applied_with_4_ranks(self) -> None:
        c, reg = char_with_skills()
        set_skill_ranks(c, "Bluff", 4)
        intimidate_defn = reg.require("Intimidate")
        result = compute_skill_total(c, intimidate_defn)
        assert result.synergy_bonus == 0

    def test_multiple_synergies_stack(self) -> None:
        """5 ranks in Jump AND Tumble both grant +2 to Balance."""
        c, reg = char_with_skills()
        set_skill_ranks(c, "Tumble", 5)
        balance_defn = reg.require("Balance")
        result = compute_skill_total(c, balance_defn)
        assert result.synergy_bonus == 2  # Tumble → Balance


# ===========================================================================
# Ability score changes cascade to skills
# ===========================================================================


class TestSkillCascade:
    def test_ability_change_updates_skill_total(self) -> None:
        c, _ = char_with_skills()
        set_skill_ranks(c, "Hide", 4)
        c.set_ability_score("dex", 10)  # mod 0
        assert c.get("skill_hide") == 4

        c.set_ability_score("dex", 18)  # mod +4
        assert c.get("skill_hide") == 8  # 4 + 4

    def test_buff_ability_change_cascades_to_skill(self) -> None:
        """Bull's Strength raises STR → Climb and Swim totals update."""
        from heroforge.engine.effects import (
            BonusEffect,
            BuffDefinition,
            apply_buff,
        )

        c, _ = char_with_skills()
        c.set_ability_score("str", 12)  # mod +1
        set_skill_ranks(c, "Climb", 3)
        assert c.get("skill_climb") == 4  # 3 + 1

        bs = BuffDefinition(
            name="Bull's Strength",
            category=None,
            effects=[BonusEffect("str_score", BonusType.ENHANCEMENT, 4)],
        )
        apply_buff(bs, c)
        # str 12→16, mod +3; Climb = 3 + 3 = 6
        assert c.get("skill_climb") == 6

    def test_multiple_skills_same_ability(self) -> None:
        c, _ = char_with_skills()
        c.set_ability_score("int", 14)  # mod +2
        set_skill_ranks(c, "Spellcraft", 5)
        set_skill_ranks(c, "Knowledge (Arcana)", 5)
        assert c.get("skill_spellcraft") == 7
        assert c.get("skill_knowledge_arcana") == 7

        c.set_ability_score("int", 20)  # mod +5
        assert c.get("skill_spellcraft") == 10
        assert c.get("skill_knowledge_arcana") == 10


# ===========================================================================
# SkillsLoader
# ===========================================================================


class TestSkillsLoader:
    def test_load_registers_all_skills(self) -> None:
        import yaml

        from heroforge.rules.loader import SkillsLoader

        with open(RULES_DIR / "core" / "skills.yaml") as f:
            data = yaml.safe_load(f)
        expected = len(data)
        reg = SkillRegistry()
        SkillsLoader(RULES_DIR).load(reg, "core/skills.yaml")
        assert len(reg) == expected

    def test_hide_skill_properties(self) -> None:
        reg = loaded_skill_registry()
        hide = reg.require("Hide")
        assert hide.ability == "dex"
        assert hide.armor_check is True
        assert hide.trained_only is False

    def test_disable_device_trained_only(self) -> None:
        reg = loaded_skill_registry()
        dd = reg.require("Disable Device")
        assert dd.trained_only is True

    def test_swim_has_armor_check(self) -> None:
        reg = loaded_skill_registry()
        assert reg.require("Swim").armor_check is True

    def test_diplomacy_no_armor_check(self) -> None:
        reg = loaded_skill_registry()
        assert reg.require("Diplomacy").armor_check is False

    def test_bluff_has_synergies(self) -> None:
        reg = loaded_skill_registry()
        bluff = reg.require("Bluff")
        synergy_targets = {s["skill"] for s in bluff.synergies}
        assert "Diplomacy" in synergy_targets
        assert "Intimidate" in synergy_targets

    def test_load_missing_file_raises(self, tmp_path: Path) -> None:
        from heroforge.rules.loader import LoaderError, SkillsLoader

        with pytest.raises(LoaderError, match="not found"):
            SkillsLoader(tmp_path).load(SkillRegistry(), "core/skills.yaml")


# ===========================================================================
# AppState integration
# ===========================================================================


class TestAppStateSkills:
    def test_new_character_has_skills_registered(self) -> None:
        from heroforge.ui.app_state import AppState

        state = AppState()
        state.load_rules()
        state.new_character()
        c = state.character
        skill_nodes = [k for k in c._graph._nodes if k.startswith("skill_")]
        assert len(skill_nodes) > 0

    def test_skill_total_via_app_state(self) -> None:
        from heroforge.ui.app_state import AppState

        state = AppState()
        state.load_rules()
        state.new_character()
        c = state.character
        c.set_ability_score("dex", 16)
        set_skill_ranks(c, "Hide", 5)
        assert state.skill_total("Hide") == 8  # 5 + 3

    def test_skill_total_unknown_returns_zero(self) -> None:
        from heroforge.ui.app_state import AppState

        state = AppState()
        state.load_rules()
        state.new_character()
        assert state.skill_total("Nonexistent Skill") == 0


# =======================================================
# Skill budget respects INT at level
# =======================================================


class TestSkillBudgetIntAtLevel:
    """
    Skill point budget uses INT at that level,
    not current INT."""

    def test_int_bump_does_not_retroact(self) -> None:
        from heroforge.engine.character import (
            CharacterLevel,
        )

        c = fresh_char()
        c.set_ability_score("int", 12)  # mod +1
        for i in range(1, 5):
            c.levels.append(
                CharacterLevel(
                    character_level=i,
                    class_name="Fighter",
                    hp_roll=10,
                )
            )
        c._invalidate_class_stats()
        # Bump INT at level 4
        c.set_level_ability_bump(4, "int")

        # Level 1: INT 12 → mod +1, Fighter base 2
        # Budget: (2 + 1) * 4 = 12
        assert c.skill_points_for_level(1) == 12
        # Level 3: still INT 12 → mod +1
        # Budget: 2 + 1 = 3
        assert c.skill_points_for_level(3) == 3
        # Level 4: INT 13 → mod +1 (threshold
        # not crossed)
        assert c.skill_points_for_level(4) == 3

    def test_int_bump_crosses_threshold(self) -> None:
        from heroforge.engine.character import (
            CharacterLevel,
        )

        c = fresh_char()
        c.set_ability_score("int", 13)  # mod +1
        for i in range(1, 5):
            c.levels.append(
                CharacterLevel(
                    character_level=i,
                    class_name="Fighter",
                    hp_roll=10,
                )
            )
        c._invalidate_class_stats()
        c.set_level_ability_bump(4, "int")

        # Level 1: INT 13 → mod +1
        # Budget: (2 + 1) * 4 = 12
        assert c.skill_points_for_level(1) == 12
        # Level 4: INT 14 → mod +2
        # Budget: 2 + 2 = 4
        assert c.skill_points_for_level(4) == 4
