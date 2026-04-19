"""
Tests for class feature mechanics: rage buffs, inspire
courage, resource tracking, etc.
"""

from __future__ import annotations

from pathlib import Path

from heroforge.engine.character import Character, ClassLevel
from heroforge.engine.classes import ClassRegistry
from heroforge.engine.effects import (
    BuffRegistry,
    apply_buff,
    remove_buff,
)
from heroforge.engine.equipment import (
    ArmorCategory,
    ArmorDefinition,
    equip_armor,
    unequip_armor,
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


# Medium armor definition for gate tests (SRD Scale Mail
# stats).
_SCALE_MAIL = ArmorDefinition(
    name="Scale Mail",
    category=ArmorCategory.MEDIUM,
    armor_bonus=4,
    max_dex_bonus=3,
    armor_check_penalty=-4,
    arcane_spell_failure=25,
    speed_30=20,
    speed_20=15,
)

_CHAIN_SHIRT = ArmorDefinition(
    name="Chain Shirt",
    category=ArmorCategory.LIGHT,
    armor_bonus=4,
    max_dex_bonus=4,
    armor_check_penalty=-2,
    arcane_spell_failure=20,
    speed_30=30,
    speed_20=20,
)

_FULL_PLATE = ArmorDefinition(
    name="Full Plate",
    category=ArmorCategory.HEAVY,
    armor_bonus=8,
    max_dex_bonus=1,
    armor_check_penalty=-6,
    arcane_spell_failure=35,
    speed_30=20,
    speed_20=15,
)


def _make_barbarian_1(state: object) -> Character:
    """
    Construct a Human barbarian 1 via AppState, with
    the class_registry wired so passive class-feature
    effects apply."""
    state.new_character()  # type: ignore[attr-defined]
    c = state.character  # type: ignore[attr-defined]
    c.race = "Human"
    c.set_ability_score("str", 14)
    c.set_ability_score("dex", 10)
    c.set_ability_score("con", 12)
    c.set_class_levels(
        [
            ClassLevel(
                class_name="Barbarian",
                level=1,
                hp_rolls=[12],
                bab_contribution=1,
                fort_contribution=2,
                ref_contribution=0,
                will_contribution=0,
            )
        ]
    )
    return c


class TestBarbarianFastMovementGate:
    """
    Barbarian fast movement: +10 ft land speed.
    SRD (PHB p.25): applies only when wearing no / light /
    medium armor AND not carrying a heavy load.
    """

    def _state(self) -> object:
        from heroforge.ui.app_state import AppState

        state = AppState()
        state.load_rules()
        return state

    def test_bare_barbarian_speed_40(self) -> None:
        state = self._state()
        c = _make_barbarian_1(state)
        # Human base speed 30 + barbarian fast move 10 = 40.
        assert c.get("speed") == 40

    def test_light_armor_keeps_fast_movement(self) -> None:
        state = self._state()
        c = _make_barbarian_1(state)
        equip_armor(c, _CHAIN_SHIRT)
        # Light armor doesn't slow; fast move still applies.
        assert c.get("speed") == 40

    def test_medium_armor_keeps_fast_movement(self) -> None:
        state = self._state()
        c = _make_barbarian_1(state)
        equip_armor(c, _SCALE_MAIL)
        # SRD: medium armor still allows fast movement.
        # Scale mail speed_30 = 20 (armor reduces base 30
        # to 20). Plus the +10 from fast movement → 30.
        assert c.get("speed") == 30

    def test_heavy_armor_removes_fast_movement(self) -> None:
        state = self._state()
        c = _make_barbarian_1(state)
        equip_armor(c, _FULL_PLATE)
        # Full plate reduces speed 30 -> 20; no fast move.
        assert c.get("speed") == 20

    def test_heavy_load_removes_fast_movement(self) -> None:
        state = self._state()
        c = _make_barbarian_1(state)
        # STR 14: heavy load threshold = 175 lbs. Push
        # current weight above heavy so the load gate
        # fails.
        c.set_current_weight(200)
        assert c.get("speed") == 30  # base, no fast move

    def test_remove_armor_restores_fast_movement(self) -> None:
        state = self._state()
        c = _make_barbarian_1(state)
        equip_armor(c, _FULL_PLATE)
        assert c.get("speed") == 20
        unequip_armor(c)
        assert c.get("speed") == 40


def _make_duelist_1(state: object) -> Character:
    """Construct a Human duelist 1 with Int 14 (+2 mod)."""
    state.new_character()  # type: ignore[attr-defined]
    c = state.character  # type: ignore[attr-defined]
    c.race = "Human"
    c.set_ability_score("str", 12)
    c.set_ability_score("dex", 14)
    c.set_ability_score("con", 12)
    c.set_ability_score("int", 14)  # +2 mod
    c.set_class_levels(
        [
            ClassLevel(
                class_name="Duelist",
                level=1,
                hp_rolls=[10],
                bab_contribution=1,
                fort_contribution=0,
                ref_contribution=2,
                will_contribution=0,
            )
        ]
    )
    return c


class TestDuelistCannyDefenseGate:
    """
    Duelist Canny Defense (DMG p.185): INT bonus to AC
    only when not wearing armor and not using a shield.
    (Plan note: the SRD also requires "wielding a melee
    weapon" — weapon-wielding state isn't modelled yet,
    so that third gate is deferred.)
    """

    def _state(self) -> object:
        from heroforge.ui.app_state import AppState

        state = AppState()
        state.load_rules()
        return state

    def test_bare_gets_int_to_ac(self) -> None:
        state = self._state()
        c = _make_duelist_1(state)
        # Base AC: 10 + Dex(2) + Int(2) = 14.
        assert c.get("ac") == 14

    def test_armor_removes_int_to_ac(self) -> None:
        state = self._state()
        c = _make_duelist_1(state)
        equip_armor(c, _CHAIN_SHIRT)
        # Armor gates off canny defense. Base AC:
        # 10 + Dex(2) + armor(4) = 16, no Int bonus.
        assert c.get("ac") == 16

    def test_shield_removes_int_to_ac(self) -> None:
        state = self._state()
        c = _make_duelist_1(state)
        # Manually mark shield as equipped without
        # bothering with shield AC bonuses.
        c.equipment["shield"] = {
            "name": "Heavy Steel Shield",
            "armor_bonus": 0,  # not modelled here
        }
        # No armor, but shield = no canny defense.
        # Expected AC: 10 + Dex(2) + 0 shield_bonus = 12.
        assert c.get("ac") == 12


class TestDuelistGraceGate:
    """
    Duelist Grace (DMG p.185): +2 competence on Reflex
    saves at L4, only when not wearing armor and not using
    a shield.
    """

    def _state(self) -> object:
        from heroforge.ui.app_state import AppState

        state = AppState()
        state.load_rules()
        return state

    def _l4_duelist(self, state: object) -> Character:
        state.new_character()  # type: ignore[attr-defined]
        c = state.character  # type: ignore[attr-defined]
        c.race = "Human"
        c.set_ability_score("dex", 14)  # +2 Ref base
        c.set_class_levels(
            [
                ClassLevel(
                    class_name="Duelist",
                    level=4,
                    hp_rolls=[10, 10, 10, 10],
                    bab_contribution=4,
                    fort_contribution=1,
                    ref_contribution=4,
                    will_contribution=1,
                )
            ]
        )
        return c

    def test_bare_gets_grace(self) -> None:
        state = self._state()
        c = self._l4_duelist(state)
        # Ref = 4 (base) + 2 (Dex) + 2 (grace) = 8.
        assert c.get("ref_save") == 8

    def test_armor_removes_grace(self) -> None:
        state = self._state()
        c = self._l4_duelist(state)
        equip_armor(c, _CHAIN_SHIRT)
        # Armor gates off grace: Ref = 4 + 2 + 0 = 6.
        assert c.get("ref_save") == 6

    def test_shield_removes_grace(self) -> None:
        state = self._state()
        c = self._l4_duelist(state)
        c.equipment["shield"] = {"name": "Buckler"}
        # Shield gates off grace: Ref = 4 + 2 + 0 = 6.
        assert c.get("ref_save") == 6


def _make_monk(state: object, level: int, wis: int = 14) -> Character:
    state.new_character()  # type: ignore[attr-defined]
    c = state.character  # type: ignore[attr-defined]
    c.race = "Human"
    c.set_ability_score("dex", 14)
    c.set_ability_score("wis", wis)
    c.set_class_levels(
        [
            ClassLevel(
                class_name="Monk",
                level=level,
                hp_rolls=[8] * level,
                bab_contribution=(level * 3) // 4,
                fort_contribution=2 + level // 2,
                ref_contribution=2 + level // 2,
                will_contribution=2 + level // 2,
            )
        ]
    )
    return c


class TestMonkAcBonus:
    """
    Monk AC bonus (PHB p.40): WIS mod + monk_level//5,
    gated by unarmored / no-shield / not medium-or-heavy
    load. AC bonus table from PHB p.40:
      L1-4: +0; L5-9: +1; L10-14: +2; L15-19: +3; L20: +4.
    """

    def _state(self) -> object:
        from heroforge.ui.app_state import AppState

        state = AppState()
        state.load_rules()
        return state

    def test_monk_5_wis_14_bare(self) -> None:
        state = self._state()
        c = _make_monk(state, level=5, wis=14)
        # 10 base + 2 Dex + 2 Wis + 1 (L5 table) = 15.
        assert c.get("ac") == 15

    def test_monk_5_plate_no_monk_bonus(self) -> None:
        state = self._state()
        c = _make_monk(state, level=5, wis=14)
        equip_armor(c, _FULL_PLATE)
        # Wis + L5 monk bonus gated off; keep Dex + armor.
        # 10 base + 1 Dex (plate caps at 1) + 8 armor = 19.
        assert c.get("ac") == 19

    def test_monk_5_shield_no_monk_bonus(self) -> None:
        state = self._state()
        c = _make_monk(state, level=5, wis=14)
        c.equipment["shield"] = {"name": "Buckler"}
        # 10 + 2 Dex + 0 = 12 (no Wis, no L5 bonus).
        assert c.get("ac") == 12

    def test_monk_10_wis_14_bare(self) -> None:
        state = self._state()
        c = _make_monk(state, level=10, wis=14)
        # 10 + 2 Dex + 2 Wis + 2 (L10) = 16.
        assert c.get("ac") == 16

    def test_monk_20_wis_18_bare(self) -> None:
        state = self._state()
        c = _make_monk(state, level=20, wis=18)
        # 10 + 2 Dex + 4 Wis + 4 (L20) = 20.
        assert c.get("ac") == 20


class TestMonkFastMovement:
    """
    Monk fast movement (PHB Table 3-10 p.40). Starts
    at L3 (+10), scaling +10 per three levels to +60 at
    L20. Gated by unarmored / no-shield / not
    medium-or-heavy load.
    """

    def _state(self) -> object:
        from heroforge.ui.app_state import AppState

        state = AppState()
        state.load_rules()
        return state

    def test_monk_1_bare_speed_30(self) -> None:
        state = self._state()
        c = _make_monk(state, level=1)
        # No fast movement at L1.
        assert c.get("speed") == 30

    def test_monk_3_bare_speed_40(self) -> None:
        state = self._state()
        c = _make_monk(state, level=3)
        assert c.get("speed") == 40

    def test_monk_9_bare_speed_60(self) -> None:
        state = self._state()
        c = _make_monk(state, level=9)
        # PHB Table 3-10: L9-11 fast move = +30.
        # Base 30 + 30 = 60.
        assert c.get("speed") == 60

    def test_monk_20_bare_speed_90(self) -> None:
        state = self._state()
        c = _make_monk(state, level=20)
        assert c.get("speed") == 90

    def test_monk_20_plate_no_fast(self) -> None:
        state = self._state()
        c = _make_monk(state, level=20)
        equip_armor(c, _FULL_PLATE)
        # Plate reduces speed_30 -> 20 and gates off fast
        # movement.
        assert c.get("speed") == 20

    def test_monk_fast_movement_is_enhancement_type(self) -> None:
        """
        PHB p.41: 'a monk gains an enhancement bonus to
        her speed'. Verify the contribution lands as
        enhancement, not untyped — matters for stacking
        with other enhancement-typed speed bonuses like
        Longstrider."""
        from collections import Counter

        state = self._state()
        c = _make_monk(state, level=20)
        pool = c.get_pool("speed")
        assert pool is not None
        types = Counter(e.bonus_type.value for e in pool.active_entries(c))
        # Fast movement entry should be present as
        # enhancement, not as untyped.
        assert types["enhancement"] >= 1, (
            f"expected enhancement bonus in speed pool; got {types}"
        )


class TestMonkAcBreakdown:
    """
    The sheet's AC breakdown should show the monk AC
    formula's two components separately (monk_wis_ac_bonus
    and monk_ac_bonus) rather than lumping them into a
    single `untyped` line."""

    def _state(self) -> object:
        from heroforge.ui.app_state import AppState

        state = AppState()
        state.load_rules()
        return state

    def test_monk_5_wis_14_ac_breakdown(self) -> None:
        from heroforge.engine.sheet import gather_sheet

        state = self._state()
        c = _make_monk(state, level=5, wis=14)
        sheet = gather_sheet(c, state)  # type: ignore[arg-type]
        typed = sheet.combat.ac.typed
        # Wis 14 (+2 mod) + L5 monk bonus (+1) should
        # appear as two separate lines, not as
        # `untyped: 3`.
        assert typed.get("monk_wis_ac_bonus") == 2, (
            f"expected monk_wis_ac_bonus=2, typed={typed}"
        )
        assert typed.get("monk_ac_bonus") == 1, (
            f"expected monk_ac_bonus=1, typed={typed}"
        )
        assert "untyped" not in typed, (
            f"should not see aggregated untyped; typed={typed}"
        )
