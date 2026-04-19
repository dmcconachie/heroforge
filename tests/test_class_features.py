"""
Tests for class feature mechanics: rage buffs, inspire
courage, resource tracking, etc.
"""

from __future__ import annotations

from pathlib import Path

from heroforge.engine.character import Character
from heroforge.engine.classes import ClassRegistry
from heroforge.engine.effects import (
    BuffRegistry,
    apply_buff,
    remove_buff,
)
from heroforge.engine.resources import (
    ResourceTracker,
)
from heroforge.rules.loader import ClassesLoader

RULES_DIR = Path(__file__).parent.parent / "src" / "heroforge" / "rules"


def _load_class_buffs() -> BuffRegistry:
    reg = BuffRegistry()
    cr = ClassRegistry()
    ClassesLoader(RULES_DIR).load(
        cr,
        "core/classes",
        buff_registry=reg,
    )
    return reg


class TestBarbarianRage:
    def test_rage_adds_str_con(self) -> None:
        reg = _load_class_buffs()
        c = Character()
        c.set_ability_score("str", 16)
        c.set_ability_score("con", 14)
        rage = reg.get("Barbarian Rage")
        assert rage is not None
        apply_buff(rage, c)
        assert c.get("str_score") == 20  # 16+4
        assert c.get("con_score") == 18  # 14+4

    def test_rage_will_bonus(self) -> None:
        reg = _load_class_buffs()
        c = Character()
        c.set_ability_score("wis", 10)
        rage = reg.get("Barbarian Rage")
        apply_buff(rage, c)
        # Will save = base(0) + WIS(0) + morale(2)
        assert c.get("will_save") == 2

    def test_rage_ac_penalty(self) -> None:
        reg = _load_class_buffs()
        c = Character()
        rage = reg.get("Barbarian Rage")
        base_ac = c.get("ac")
        apply_buff(rage, c)
        assert c.get("ac") == base_ac - 2

    def test_rage_remove(self) -> None:
        reg = _load_class_buffs()
        c = Character()
        c.set_ability_score("str", 16)
        rage = reg.get("Barbarian Rage")
        apply_buff(rage, c)
        remove_buff(rage, c)
        assert c.get("str_score") == 16


class TestInspireCourage:
    def test_inspire_courage_plus_1(self) -> None:
        reg = _load_class_buffs()
        c = Character()
        ic = reg.get("Inspire Courage +1")
        assert ic is not None
        apply_buff(ic, c)
        assert c.get("attack_melee") >= 1


class TestResourceTracker:
    def test_use_and_exhaust(self) -> None:
        r = ResourceTracker(name="Rage", max_formula="3")
        r.reset(3)
        assert r.current == 3
        assert not r.exhausted
        assert r.use()
        assert r.current == 2
        assert r.use()
        assert r.use()
        assert r.exhausted
        assert not r.use()

    def test_reset(self) -> None:
        r = ResourceTracker(name="Turn Undead")
        r.reset(5)
        r.use()
        r.use()
        assert r.current == 3
        r.reset(5)
        assert r.current == 5


class TestClassBuffsLoader:
    def test_all_buffs_load(self) -> None:
        reg = _load_class_buffs()
        assert reg.get("Barbarian Rage") is not None
        assert reg.get("Greater Rage") is not None
        assert reg.get("Mighty Rage") is not None
        assert reg.get("Inspire Courage +1") is not None

    def test_at_least_some_class_buffs(self) -> None:
        reg = _load_class_buffs()
        # Count class category buffs. Phase 1 trimmed
        # non-passive buffs (Flurry of Blows, Smite Evil,
        # Favored Enemy tiers); remaining class buffs are
        # the explicit buff_name:-declared transitory ones.
        count = sum(1 for n in reg._defs if reg.get(n) is not None)
        assert count >= 5


# Names removed from the buff registry in Phase 1 of the
# passive-features cleanup. Alignment-conditional spells
# (Magic Circle, Protection from X), one-shots (Smite Evil,
# Bless Weapon), conditional feats (Dodge), ranger Favored
# Enemy tiers, and a few others don't belong on the buff
# toggle panel. They will surface in the future conditional
# effects sheet panel; for now they are note-only and are
# NOT registered as BuffDefinitions.
_REMOVED_NON_PASSIVE_BUFF_NAMES: tuple[str, ...] = (
    "Bless Weapon",
    "Dodge",
    "Favored Enemy +2",
    "Favored Enemy +4",
    "Favored Enemy +6",
    "Flurry of Blows",
    "Invisibility",
    "Magic Circle against Chaos",
    "Magic Circle against Evil",
    "Magic Circle against Good",
    "Magic Circle against Law",
    "Moment of Prescience",
    "Protection from Chaos",
    "Protection from Evil",
    "Protection from Good",
    "Protection from Law",
    "Smite Evil",
)


class TestRemovedNonPassiveBuffs:
    """
    Buffs removed from KnownCoreBuff in Phase 1.

    These names must not appear in the full buff registry
    (loaded via AppState.load_rules) and must not appear
    in the KnownCoreBuff enum.
    """

    def test_removed_names_not_in_buff_registry(self) -> None:
        from heroforge.ui.app_state import AppState

        state = AppState()
        state.load_rules()
        for name in _REMOVED_NON_PASSIVE_BUFF_NAMES:
            assert state.buff_registry.get(name) is None, (
                f"{name!r} should not be registered as a buff"
            )

    def test_removed_names_not_in_known_core_buff_enum(
        self,
    ) -> None:
        from heroforge.rules.core.buffs import KnownCoreBuff

        enum_values = {m.value for m in KnownCoreBuff}
        for name in _REMOVED_NON_PASSIVE_BUFF_NAMES:
            assert name not in enum_values, (
                f"{name!r} should not be in KnownCoreBuff"
            )


# Auto-generated "Class feature_key" buff names produced
# when a class feature YAML declares effects but no
# buff_name. These represent permanent class bonuses
# (always-on passives like Paladin divine_grace) that the
# loader was wrapping in BuffDefinitions as a side effect.
# Phase 3 stops that auto-registration.
_PHASE3_PASSIVE_FEATURE_BUFF_NAMES: tuple[str, ...] = (
    "Barbarian fast_movement",
    "Blackguard dark_blessing",
    "Dragon Disciple natural_armor_1",
    "Dragon Disciple natural_armor_4",
    "Dragon Disciple natural_armor_7",
    "Dragon Disciple str_increase_2",
    "Dragon Disciple str_increase_4",
    "Duelist canny_defense",
    "Duelist grace",
    "Duelist improved_reaction",
    "Paladin divine_grace",
)


class TestPassiveFeaturesNotInBuffRegistry:
    """
    Permanent class features must not produce
    zombie BuffDefinitions just because they declare
    effects. They apply via
    _apply_class_feature_effects on Character, not via
    the buff toggle system.
    """

    def test_passive_names_not_in_buff_registry(self) -> None:
        from heroforge.ui.app_state import AppState

        state = AppState()
        state.load_rules()
        for name in _PHASE3_PASSIVE_FEATURE_BUFF_NAMES:
            assert state.buff_registry.get(name) is None, (
                f"{name!r} should not be registered as a buff"
            )

    def test_passive_names_not_in_known_core_buff_enum(
        self,
    ) -> None:
        from heroforge.rules.core.buffs import KnownCoreBuff

        enum_values = {m.value for m in KnownCoreBuff}
        for name in _PHASE3_PASSIVE_FEATURE_BUFF_NAMES:
            assert name not in enum_values, (
                f"{name!r} should not be in KnownCoreBuff"
            )

    def test_paladin_divine_grace_still_applied_as_passive(
        self,
    ) -> None:
        # Phase 3 removes the zombie buff registration, but
        # the feature itself (CHA to all saves at paladin
        # L2) must still apply. Verified via the live stat
        # pipeline — a paladin L2 with Cha 14 gets +2 on
        # every save from divine grace (passive).
        from heroforge.engine.character import ClassLevel
        from heroforge.ui.app_state import AppState

        state = AppState()
        state.load_rules()
        state.new_character()
        c = state.character
        c.set_ability_score("cha", 14)
        c.set_class_levels(
            [
                ClassLevel(
                    class_name="Paladin",
                    level=2,
                    hp_rolls=[10, 10],
                    bab_contribution=2,
                    fort_contribution=3,
                    ref_contribution=0,
                    will_contribution=0,
                )
            ]
        )
        # Without divine grace: fort_save = 3 (base).
        # With divine grace: fort_save = 3 + 2 (cha) = 5.
        assert c.get("fort_save") == 5
        assert c.get("ref_save") == 2  # 0 base + 2 cha
        assert c.get("will_save") == 2  # 0 base + 2 cha
