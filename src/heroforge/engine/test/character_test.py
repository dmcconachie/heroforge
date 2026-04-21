"""
tests/test_character.py
-----------------------
Test suite for engine/character.py.

Covers:
  - Construction and default stat values
  - Ability score get/set with cascade
  - Buff registration, activation, deactivation
  - Buff entries appearing in and disappearing from pools
  - Stacking rules respected through the full Character.get() path
  - Change notification firing on mutations
  - Class level wiring (BAB, saves, HP)
  - DM override management
  - Convenience properties
  - Edge cases (unknown stat keys, invalid scores, double-toggle, etc.)
"""

from __future__ import annotations

import pytest

from heroforge.engine.bonus import BonusEntry, BonusPool, BonusType
from heroforge.engine.character import (
    Character,
    CharacterError,
    CharacterLevel,
)

# ===========================================================================
# Helpers
# ===========================================================================


def make_char(**kwargs: object) -> Character:
    return Character(**kwargs)


def simple_buff(
    char: Character,
    name: str,
    pool_key: str,
    value: int,
    btype: BonusType = BonusType.UNTYPED,
) -> None:
    """Register a simple single-entry buff on a character."""
    entry = BonusEntry(value=value, bonus_type=btype, source=name)
    char.register_buff_definition(name, [(pool_key, entry)])


def fighter_levels(n: int) -> list[CharacterLevel]:
    """
    n Fighter levels, HP 10 each. Real Fighter class from
    the rules registry supplies BAB / save progressions."""
    return [
        CharacterLevel(
            character_level=i + 1,
            class_name="Fighter",
            hp_roll=10,
        )
        for i in range(n)
    ]


# ===========================================================================
# Construction and defaults
# ===========================================================================


class TestConstruction:
    def test_default_ability_scores_are_ten(self) -> None:
        c = make_char()
        for ab in ("str", "dex", "con", "int", "wis", "cha"):
            assert c.get_ability_score(ab) == 10

    def test_default_ability_modifiers_are_zero(self) -> None:
        c = make_char()
        for ab in ("str", "dex", "con", "int", "wis", "cha"):
            assert c.get_ability_modifier(ab) == 0

    def test_default_ac_is_ten(self) -> None:
        c = make_char()
        assert c.ac == 10

    def test_default_bab_is_zero(self) -> None:
        c = make_char()
        assert c.bab == 0

    def test_default_saves_are_zero(self) -> None:
        c = make_char()
        assert c.fort == 0
        assert c.ref == 0
        assert c.will == 0

    def test_default_initiative_is_zero(self) -> None:
        c = make_char()
        assert c.initiative == 0

    def test_default_total_level_is_zero(self) -> None:
        c = make_char()
        assert c.total_level == 0

    def test_name_stored(self) -> None:
        c = make_char(name="Farzin", player="Dale")
        assert c.name == "Farzin"
        assert c.player == "Dale"

    def test_repr_contains_name_and_level(self) -> None:
        c = make_char(name="Grog")
        assert "Grog" in repr(c)

    def test_get_unknown_stat_returns_zero(self) -> None:
        """Unknown stat keys should return 0, not raise."""
        c = make_char()
        assert c.get("nonexistent_stat") == 0


# ===========================================================================
# Ability score mutation
# ===========================================================================


class TestAbilityScores:
    def test_set_ability_score_updates_score(self) -> None:
        c = make_char()
        c.set_ability_score("str", 18)
        assert c.get_ability_score("str") == 18

    def test_set_ability_score_updates_modifier(self) -> None:
        c = make_char()
        c.set_ability_score("str", 18)
        assert c.str_mod == 4

    def test_modifier_floors_correctly(self) -> None:
        c = make_char()
        c.set_ability_score("str", 9)
        assert c.str_mod == -1

    def test_set_dex_updates_initiative(self) -> None:
        c = make_char()
        c.set_ability_score("dex", 16)
        assert c.initiative == 3

    def test_set_dex_updates_ac(self) -> None:
        c = make_char()
        c.set_ability_score("dex", 14)
        # AC = 10 + dex_mod(2) = 12
        assert c.ac == 12

    def test_set_con_updates_hp_max_with_levels(self) -> None:
        c = make_char()
        c.set_class_levels(fighter_levels(5))
        c.set_ability_score("con", 14)
        # hp_from_rolls = 50 (5×10), con_mod=2, 5 levels → +10
        assert c.hp_max == 60

    def test_set_ability_score_invalid_name_raises(
        self,
    ) -> None:
        c = make_char()
        with pytest.raises(ValueError):
            c.set_ability_score("luck", 12)

    def test_set_ability_score_zero_raises(self) -> None:
        c = make_char()
        with pytest.raises(CharacterError):
            c.set_ability_score("str", 0)

    def test_set_ability_score_above_99_raises(self) -> None:
        c = make_char()
        with pytest.raises(CharacterError):
            c.set_ability_score("str", 100)

    def test_set_ability_score_boundary_1_valid(self) -> None:
        c = make_char()
        c.set_ability_score("str", 1)
        assert c.str_mod == -5

    def test_set_ability_score_boundary_99_valid(self) -> None:
        c = make_char()
        c.set_ability_score("str", 99)
        assert c.str_score == 99

    def test_convenience_properties_reflect_scores(self) -> None:
        c = make_char()
        c.set_ability_score("wis", 16)
        assert c.wis_score == 16
        assert c.wis_mod == 3


# ===========================================================================
# Buff registration and toggling
# ===========================================================================


class TestBuffManagement:
    def test_register_buff_creates_inactive_state(self) -> None:
        c = make_char()
        simple_buff(c, "Bless", "attack_melee", 1, BonusType.MORALE)
        state = c.get_buff_state("Bless")
        assert state is not None
        assert state.active is False

    def test_toggle_buff_on_activates_it(self) -> None:
        c = make_char()
        simple_buff(c, "Bless", "attack_melee", 1, BonusType.MORALE)
        c.toggle_buff("Bless", True)
        assert c.is_buff_active("Bless") is True

    def test_toggle_buff_off_deactivates_it(self) -> None:
        c = make_char()
        simple_buff(c, "Bless", "attack_melee", 1, BonusType.MORALE)
        c.toggle_buff("Bless", True)
        c.toggle_buff("Bless", False)
        assert c.is_buff_active("Bless") is False

    def test_toggle_unregistered_buff_raises(self) -> None:
        c = make_char()
        with pytest.raises(CharacterError, match="not registered"):
            c.toggle_buff("Ghost Buff", True)

    def test_active_buffs_lists_active_only(self) -> None:
        c = make_char()
        simple_buff(c, "Bless", "attack_melee", 1)
        simple_buff(c, "Prayer", "attack_melee", 1)
        c.toggle_buff("Bless", True)
        assert "Bless" in c.active_buffs()
        assert "Prayer" not in c.active_buffs()

    def test_buff_with_caster_level(self) -> None:
        c = make_char()
        entry = BonusEntry(2, BonusType.LUCK, "Divine Favor")
        c.register_buff_definition(
            "Divine Favor",
            [("attack_melee", entry)],
        )
        c.toggle_buff("Divine Favor", True, caster_level=6)
        state = c.get_buff_state("Divine Favor")
        assert state.caster_level == 6
        assert state.active is True

    def test_caster_level_persists_across_toggles(self) -> None:
        c = make_char()
        entry = BonusEntry(2, BonusType.LUCK, "Divine Favor")
        c.register_buff_definition("Divine Favor", [("attack_melee", entry)])
        c.toggle_buff("Divine Favor", True, caster_level=9)
        c.toggle_buff("Divine Favor", False)
        c.toggle_buff("Divine Favor", True)
        # CL should still be 9 from earlier
        assert c.get_buff_state("Divine Favor").caster_level == 9

    def test_double_activate_is_idempotent(self) -> None:
        """
        Activating an already-active buff must not double-count.
        This is guaranteed structurally by set_source overwriting, not by
        a was_active guard — the second toggle_buff(True) is identical in
        effect to the first because set_source is idempotent.
        """
        c = make_char()
        simple_buff(c, "Bless", "attack_melee", 1, BonusType.MORALE)
        c.set_class_levels(fighter_levels(5))
        c.toggle_buff("Bless", True)
        atk_once = c.get("attack_melee")
        c.toggle_buff("Bless", True)  # second activation
        c.toggle_buff("Bless", True)  # third activation
        assert (
            c.get("attack_melee") == atk_once
        )  # structurally identical, not guarded

    def test_double_deactivate_is_idempotent(self) -> None:
        """
        Deactivating an already-inactive buff is a silent no-op.
        clear_source on an absent key does nothing.
        """
        c = make_char()
        simple_buff(c, "Bless", "attack_melee", 1, BonusType.MORALE)
        c.toggle_buff("Bless", True)
        c.toggle_buff("Bless", False)
        c.toggle_buff("Bless", False)  # clear_source on absent key — no-op
        c.toggle_buff("Bless", False)  # and again
        assert c.is_buff_active("Bless") is False
        assert c.get("attack_melee") == c.bab  # no residual bonus


# ===========================================================================
# Buff effect on stats (integration with stat graph)
# ===========================================================================


class TestBuffStatEffects:
    def test_buff_increases_targeted_stat(self) -> None:
        c = make_char()
        simple_buff(c, "Bless", "attack_melee", 1, BonusType.MORALE)
        c.set_class_levels(fighter_levels(4))  # bab=4, so base attack = 4
        base_atk = c.get("attack_melee")
        c.toggle_buff("Bless", True)
        assert c.get("attack_melee") == base_atk + 1

    def test_buff_deactivation_reverts_stat(self) -> None:
        c = make_char()
        simple_buff(c, "Bless", "attack_melee", 1, BonusType.MORALE)
        c.set_class_levels(fighter_levels(4))
        base_atk = c.get("attack_melee")
        c.toggle_buff("Bless", True)
        c.toggle_buff("Bless", False)
        assert c.get("attack_melee") == base_atk

    def test_two_same_type_buffs_only_highest_counts(self) -> None:
        """Two morale bonuses: +2 and +3. Only +3 should apply."""
        c = make_char()
        simple_buff(c, "Bless", "attack_melee", 2, BonusType.MORALE)
        simple_buff(c, "Prayer", "attack_melee", 3, BonusType.MORALE)
        c.set_class_levels(fighter_levels(3))
        base = c.get("attack_melee")
        c.toggle_buff("Bless", True)
        c.toggle_buff("Prayer", True)
        assert c.get("attack_melee") == base + 3  # not base + 5

    def test_different_type_buffs_stack(self) -> None:
        """Morale +1 and Luck +1 are different types — both apply."""
        c = make_char()
        simple_buff(c, "Bless", "attack_melee", 1, BonusType.MORALE)
        simple_buff(c, "Prayer", "attack_melee", 1, BonusType.LUCK)
        c.set_class_levels(fighter_levels(3))
        base = c.get("attack_melee")
        c.toggle_buff("Bless", True)
        c.toggle_buff("Prayer", True)
        assert c.get("attack_melee") == base + 2

    def test_buff_on_ability_score_cascades_to_modifier(self) -> None:
        """Bull's Strength (+4 enhancement to str_score) → str_mod increases."""
        c = make_char()
        c.set_ability_score("str", 14)  # mod = 2
        entry = BonusEntry(4, BonusType.ENHANCEMENT, "Bull's Strength")
        c.register_buff_definition("Bull's Strength", [("str_score", entry)])

        assert c.str_mod == 2
        c.toggle_buff("Bull's Strength", True)
        # str_score = 14 + 4 = 18, mod = 4
        assert c.str_score == 18
        assert c.str_mod == 4

    def test_str_buff_cascades_to_melee_attack(self) -> None:
        """Bull's Strength raises STR → STR mod → melee attack."""
        c = make_char()
        c.set_ability_score("str", 14)  # mod = 2
        c.set_class_levels(fighter_levels(4))  # bab = 4
        # baseline attack: bab(4) + str_mod(2) = 6
        assert c.get("attack_melee") == 6

        entry = BonusEntry(4, BonusType.ENHANCEMENT, "Bull's Strength")
        c.register_buff_definition("Bull's Strength", [("str_score", entry)])
        c.toggle_buff("Bull's Strength", True)

        # str_score = 18, mod = 4, attack = bab(4) + str_mod(4) = 8
        assert c.get("attack_melee") == 8

    def test_buff_on_ac_pool(self) -> None:
        """Shield of Faith adds deflection bonus to AC."""
        c = make_char()
        entry = BonusEntry(3, BonusType.DEFLECTION, "Shield of Faith")
        c.register_buff_definition("Shield of Faith", [("ac", entry)])
        assert c.ac == 10
        c.toggle_buff("Shield of Faith", True)
        assert c.ac == 13

    def test_multiple_buffs_on_different_stats(self) -> None:
        """Haste (+1 untyped attack, +1 dodge AC) — two pools, both affected."""
        c = make_char()
        haste_entries = [
            ("attack_all", BonusEntry(1, BonusType.UNTYPED, "Haste")),
            ("ac", BonusEntry(1, BonusType.DODGE, "Haste")),
        ]
        c.register_buff_definition("Haste", haste_entries)
        c.set_class_levels(fighter_levels(5))

        atk_before = c.get("attack_melee")
        ac_before = c.ac

        c.toggle_buff("Haste", True)

        assert c.get("attack_melee") == atk_before + 1
        assert c.ac == ac_before + 1

    def test_haste_deactivation_removes_both_effects(self) -> None:
        c = make_char()
        haste_entries = [
            ("attack_all", BonusEntry(1, BonusType.UNTYPED, "Haste")),
            ("ac", BonusEntry(1, BonusType.DODGE, "Haste")),
        ]
        c.register_buff_definition("Haste", haste_entries)
        c.set_class_levels(fighter_levels(5))
        atk_before = c.get("attack_melee")
        ac_before = c.ac

        c.toggle_buff("Haste", True)
        c.toggle_buff("Haste", False)

        assert c.get("attack_melee") == atk_before
        assert c.ac == ac_before

    def test_conditional_buff_entry_respects_character_state(self) -> None:
        """
        Enlarge Person only works on humanoids.
        We model this as a condition on the BonusEntry.
        """
        c = make_char()
        c._race_type = "Humanoid"  # normally set by race loader

        entry = BonusEntry(
            2,
            BonusType.ENHANCEMENT,
            "Enlarge Person",
            condition=lambda char: (
                getattr(char, "_race_type", "") == "Humanoid"
            ),
        )
        c.register_buff_definition("Enlarge Person", [("str_score", entry)])
        c.toggle_buff("Enlarge Person", True)
        c.set_ability_score("str", 12)

        # Humanoid: condition True → +2 applies
        assert c.str_score == 14

    def test_conditional_buff_entry_excluded_when_condition_false(self) -> None:
        c = make_char()
        c._race_type = "Undead"  # not humanoid

        entry = BonusEntry(
            2,
            BonusType.ENHANCEMENT,
            "Enlarge Person",
            condition=lambda char: (
                getattr(char, "_race_type", "") == "Humanoid"
            ),
        )
        c.register_buff_definition("Enlarge Person", [("str_score", entry)])
        c.toggle_buff("Enlarge Person", True)
        c.set_ability_score("str", 12)

        # Not humanoid: condition False → +2 excluded
        assert c.str_score == 12


# ===========================================================================
# Class levels and derived stats
# ===========================================================================


class TestClassLevels:
    def test_set_class_levels_updates_bab(self) -> None:
        c = make_char()
        c.set_class_levels(fighter_levels(6))
        assert c.bab == 6

    def test_set_class_levels_updates_fort_save(self) -> None:
        c = make_char()
        c.set_class_levels(fighter_levels(4))
        # good Fort at 4: 2 + 4//2 = 4
        assert c.fort == 4

    def test_set_class_levels_updates_will_save(self) -> None:
        c = make_char()
        c.set_class_levels(fighter_levels(6))
        # poor Will at 6: 6//3 = 2
        assert c.will == 2

    def test_saves_include_ability_modifier(self) -> None:
        c = make_char()
        c.set_ability_score("con", 14)  # con_mod = 2
        c.set_class_levels(fighter_levels(4))
        # Fort: base(4) + con_mod(2) = 6
        assert c.fort == 6

    def test_hp_max_from_class_levels_and_con(self) -> None:
        c = make_char()
        c.set_ability_score("con", 12)  # con_mod = 1
        c.set_class_levels(fighter_levels(3))
        # rolls: 10+10+10 = 30; con_mod(1) × 3 levels = 3 → total 33
        assert c.hp_max == 33

    def test_total_level_sums_all_classes(self) -> None:
        c = make_char()
        levels: list[CharacterLevel] = []
        for i in range(5):
            levels.append(
                CharacterLevel(
                    character_level=i + 1,
                    class_name="Fighter",
                    hp_roll=10,
                )
            )
        for i in range(3):
            levels.append(
                CharacterLevel(
                    character_level=5 + i + 1,
                    class_name="Wizard",
                    hp_roll=4,
                )
            )
        c.set_class_levels(levels)
        assert c.total_level == 8

    def test_multiclass_bab_sums(self) -> None:
        c = make_char()
        levels: list[CharacterLevel] = []
        for i in range(5):
            levels.append(
                CharacterLevel(
                    character_level=i + 1,
                    class_name="Fighter",
                    hp_roll=10,
                )
            )
        for i in range(3):
            levels.append(
                CharacterLevel(
                    character_level=5 + i + 1,
                    class_name="Wizard",
                    hp_roll=4,
                )
            )
        c.set_class_levels(levels)
        # Fighter 5 = +5 BAB, Wizard 3 = +1 BAB (half)
        assert c.bab == 6

    def test_attack_melee_includes_bab_and_str(self) -> None:
        c = make_char()
        c.set_ability_score("str", 16)  # mod = 3
        c.set_class_levels(fighter_levels(5))  # bab = 5
        assert c.get("attack_melee") == 8  # 5 + 3

    def test_attack_ranged_uses_dex(self) -> None:
        c = make_char()
        c.set_ability_score("dex", 14)  # mod = 2
        c.set_class_levels(fighter_levels(4))  # bab = 4
        assert c.get("attack_ranged") == 6  # 4 + 2


# ===========================================================================
# DM overrides
# ===========================================================================


class TestDmOverrides:
    def test_add_dm_override(self) -> None:
        c = make_char()
        c.add_dm_override(
            "Weapon Focus (Bastard Sword)", note="Proficiency via background"
        )
        assert c.has_dm_override("Weapon Focus (Bastard Sword)")

    def test_add_duplicate_override_is_idempotent(self) -> None:
        c = make_char()
        c.add_dm_override("Some Feat")
        c.add_dm_override("Some Feat")
        assert len([o for o in c.dm_overrides if o.target == "Some Feat"]) == 1

    def test_remove_dm_override(self) -> None:
        c = make_char()
        c.add_dm_override("Some Feat")
        removed = c.remove_dm_override("Some Feat")
        assert removed is True
        assert not c.has_dm_override("Some Feat")

    def test_remove_nonexistent_override_returns_false(self) -> None:
        c = make_char()
        removed = c.remove_dm_override("Ghost Feat")
        assert removed is False

    def test_override_note_stored(self) -> None:
        c = make_char()
        c.add_dm_override("Test Feat", note="DM approved at session 5")
        override = next(o for o in c.dm_overrides if o.target == "Test Feat")
        assert "session 5" in override.note


# ===========================================================================
# Change notification
# ===========================================================================


class TestChangeNotification:
    def test_set_ability_score_fires_notification(self) -> None:
        c = make_char()
        received: list[set] = []
        c.on_change.subscribe(lambda keys: received.append(keys))
        c.set_ability_score("str", 16)
        assert len(received) == 1
        assert "str_score" in received[0]
        assert "str_mod" in received[0]

    def test_toggle_buff_fires_notification(self) -> None:
        c = make_char()
        simple_buff(c, "Bless", "attack_melee", 1, BonusType.MORALE)
        received: list[set] = []
        c.on_change.subscribe(lambda keys: received.append(keys))
        c.toggle_buff("Bless", True)
        assert len(received) == 1
        assert len(received[0]) > 0

    def test_no_notification_when_nothing_changes(self) -> None:
        """Toggling a buff with no entries should not notify."""
        c = make_char()
        c.register_buff_definition("Empty Buff", [])
        received: list[set] = []
        c.on_change.subscribe(lambda keys: received.append(keys))
        c.toggle_buff("Empty Buff", True)
        assert len(received) == 0

    def test_set_class_levels_fires_notification(self) -> None:
        c = make_char()
        received: list[set] = []
        c.on_change.subscribe(lambda keys: received.append(keys))
        c.set_class_levels(fighter_levels(5))
        assert len(received) == 1
        assert "bab" in received[0]

    def test_unsubscribe_stops_notifications(self) -> None:
        c = make_char()
        received: list[set] = []

        def fn(keys: set[str]) -> None:
            received.append(keys)

        c.on_change.subscribe(fn)
        c.on_change.unsubscribe(fn)
        c.set_ability_score("str", 14)
        assert len(received) == 0

    def test_multiple_subscribers_all_notified(self) -> None:
        c = make_char()
        received: list[set[str]] = [set(), set()]
        c.on_change.subscribe(lambda keys: received[0].update(keys))
        c.on_change.subscribe(lambda keys: received[1].update(keys))
        c.set_ability_score("con", 14)
        assert received[0] and received[1]
        assert received[0] == received[1]


# ===========================================================================
# Pool access
# ===========================================================================


class TestPoolAccess:
    def test_get_pool_returns_pool(self) -> None:
        c = make_char()
        pool = c.get_pool("attack_melee")
        assert pool is not None
        assert isinstance(pool, BonusPool)

    def test_get_pool_unknown_returns_none(self) -> None:
        c = make_char()
        assert c.get_pool("nonexistent") is None

    def test_add_custom_pool(self) -> None:
        c = make_char()
        new_pool = BonusPool("knowledge_arcana")
        c.add_pool(new_pool)
        assert c.get_pool("knowledge_arcana") is new_pool

    def test_get_breakdown_for_pool(self) -> None:
        c = make_char()
        simple_buff(c, "Bless", "attack_melee", 1, BonusType.MORALE)
        simple_buff(c, "Prayer", "attack_melee", 2, BonusType.MORALE)
        c.toggle_buff("Bless", True)
        c.toggle_buff("Prayer", True)
        bd = c.get_breakdown("attack_melee")
        # Prayer (+2) wins; Bless (+1) shows 0
        assert bd.get("Prayer") == 2
        assert bd.get("Bless") == 0

    def test_get_breakdown_unknown_pool_returns_empty(self) -> None:
        c = make_char()
        assert c.get_breakdown("no_such_pool") == {}


# ===========================================================================
# Full integration — combined scenario
# ===========================================================================


class TestFullScenario:
    def test_fighter5_with_buffs(self) -> None:
        """
        Fighter 5, STR 16 (mod +3), CON 14 (mod +2).
        Active: Bull's Strength (+4 enh to STR),
        Bless (+1 morale attack).
        Expected:
          bab        = 5
          str_score  = 20 (16 + 4)
          str_mod    = 5
          attack_melee = bab(5) + str_mod(5) + morale(1) = 11
          fort       = base(4) + con_mod(2) = 6
          hp_max     = rolls(50) + con_mod(2)×5 = 60
          ac         = 10 (no armour or DEX bonus beyond 0)
        """
        c = make_char(name="Test Fighter")
        c.set_ability_score("str", 16)
        c.set_ability_score("con", 14)
        c.set_class_levels(fighter_levels(5))

        bs_entry = BonusEntry(4, BonusType.ENHANCEMENT, "Bull's Strength")
        c.register_buff_definition("Bull's Strength", [("str_score", bs_entry)])

        bless_entry = BonusEntry(1, BonusType.MORALE, "Bless")
        c.register_buff_definition("Bless", [("attack_melee", bless_entry)])

        c.toggle_buff("Bull's Strength", True)
        c.toggle_buff("Bless", True)

        assert c.bab == 5
        assert c.str_score == 20
        assert c.str_mod == 5
        assert c.get("attack_melee") == 11
        assert c.fort == 6
        assert c.hp_max == 60

    def test_buffs_stack_correctly_complex(self) -> None:
        """
        Attack pool has: morale +2 (Inspire Courage), luck +1 (Prayer),
        dodge +1 (Haste), enhancement +3 (already on weapon — via attack pool).
        Another morale +1 (Bless) — should NOT add
        since +2 morale already present.
        Expected total bonus from pools = 2 + 1 + 1 + 3 = 7 (not 8).
        """
        c = make_char()
        c.set_class_levels(fighter_levels(6))  # bab = 6

        for name, val, btype in [
            ("Inspire Courage", 2, BonusType.MORALE),
            ("Prayer", 1, BonusType.LUCK),
            ("Haste", 1, BonusType.DODGE),
            ("Magic Weapon +3", 3, BonusType.ENHANCEMENT),
            ("Bless", 1, BonusType.MORALE),  # lost to Inspire Courage
        ]:
            simple_buff(c, name, "attack_melee", val, btype)
            c.toggle_buff(name, True)

        # bab(6) + str_mod(0) + morale_max(2) + luck(1) + dodge(1) + enh(3) = 13
        assert c.get("attack_melee") == 13


# ===========================================================================
# Level-up ability bumps
# ===========================================================================


def _char_with_levels(n: int) -> Character:
    """Character with n Fighter levels (no class registry)."""
    c = make_char()
    for i in range(1, n + 1):
        c.levels.append(
            CharacterLevel(
                character_level=i,
                class_name="Fighter",
                hp_roll=10,
            )
        )
    c._invalidate_class_stats()
    return c


class TestAbilityBumps:
    def test_bump_at_level_4_increases_score(self) -> None:
        c = _char_with_levels(4)
        c.set_ability_score("str", 14)
        c.set_level_ability_bump(4, "str")
        assert c.get_ability_score("str") == 15

    def test_bumps_stack_across_levels(self) -> None:
        c = _char_with_levels(8)
        c.set_ability_score("str", 14)
        c.set_level_ability_bump(4, "str")
        c.set_level_ability_bump(8, "str")
        assert c.get_ability_score("str") == 16

    def test_bumps_to_different_abilities(self) -> None:
        c = _char_with_levels(8)
        c.set_ability_score("str", 14)
        c.set_ability_score("dex", 12)
        c.set_level_ability_bump(4, "str")
        c.set_level_ability_bump(8, "dex")
        assert c.get_ability_score("str") == 15
        assert c.get_ability_score("dex") == 13

    def test_change_bump_updates_both_stats(self) -> None:
        c = _char_with_levels(4)
        c.set_ability_score("str", 14)
        c.set_ability_score("dex", 12)
        c.set_level_ability_bump(4, "str")
        assert c.get_ability_score("str") == 15
        c.set_level_ability_bump(4, "dex")
        assert c.get_ability_score("str") == 14
        assert c.get_ability_score("dex") == 13

    def test_remove_bump(self) -> None:
        c = _char_with_levels(4)
        c.set_ability_score("str", 14)
        c.set_level_ability_bump(4, "str")
        assert c.get_ability_score("str") == 15
        c.set_level_ability_bump(4, None)
        assert c.get_ability_score("str") == 14

    def test_bump_affects_modifier(self) -> None:
        c = _char_with_levels(4)
        c.set_ability_score("str", 15)  # mod = 2
        c.set_level_ability_bump(4, "str")
        # 15 + 1 = 16 → mod = 3
        assert c.get_ability_modifier("str") == 3

    def test_invalid_level_raises(self) -> None:
        c = _char_with_levels(4)
        with pytest.raises(CharacterError):
            c.set_level_ability_bump(5, "str")

    def test_invalid_ability_raises(self) -> None:
        c = _char_with_levels(4)
        with pytest.raises(ValueError):
            c.set_level_ability_bump(4, "foo")


# ===========================================================================
# Inherent bonuses (Tomes / Manuals)
# ===========================================================================


class TestInherentBumps:
    def test_inherent_increases_score(self) -> None:
        c = _char_with_levels(5)
        c.set_ability_score("int", 14)
        c.add_inherent_bump(5, "int", 1)
        assert c.get_ability_score("int") == 15

    def test_inherent_does_not_stack(self) -> None:
        """Only the highest inherent bonus applies."""
        c = _char_with_levels(8)
        c.set_ability_score("int", 14)
        c.add_inherent_bump(3, "int", 1)
        c.add_inherent_bump(7, "int", 2)
        # Only +2 applies, not +1 + +2
        assert c.get_ability_score("int") == 16

    def test_inherent_capped_at_5(self) -> None:
        c = _char_with_levels(5)
        c.set_ability_score("str", 14)
        with pytest.raises(CharacterError):
            c.add_inherent_bump(5, "str", 6)

    def test_inherent_stacks_with_level_bump(self) -> None:
        c = _char_with_levels(8)
        c.set_ability_score("str", 14)
        c.set_level_ability_bump(4, "str")  # +1
        c.add_inherent_bump(5, "str", 2)  # +2
        # 14 + 1 (bump) + 2 (inherent) = 17
        assert c.get_ability_score("str") == 17

    def test_remove_inherent_bump(self) -> None:
        c = _char_with_levels(5)
        c.set_ability_score("str", 14)
        c.add_inherent_bump(5, "str", 2)
        assert c.get_ability_score("str") == 16
        c.remove_inherent_bump(5, "str")
        assert c.get_ability_score("str") == 14


# ===========================================================================
# INT modifier at level (for skill points)
# ===========================================================================


class TestIntModAtLevel:
    def test_base_int_only(self) -> None:
        c = _char_with_levels(4)
        c.set_ability_score("int", 14)  # mod +2
        assert c.int_mod_at_level(1) == 2
        assert c.int_mod_at_level(4) == 2

    def test_int_bump_excluded_before_bump_level(
        self,
    ) -> None:
        c = _char_with_levels(4)
        c.set_ability_score("int", 14)
        c.set_level_ability_bump(4, "int")
        # Level 3: no bump yet → mod +2
        assert c.int_mod_at_level(3) == 2
        # Level 4: bump included → 15 → mod +2
        assert c.int_mod_at_level(4) == 2

    def test_int_bump_crosses_modifier_threshold(
        self,
    ) -> None:
        c = _char_with_levels(4)
        c.set_ability_score("int", 13)  # mod +1
        c.set_level_ability_bump(4, "int")
        # Level 3: INT 13 → mod +1
        assert c.int_mod_at_level(3) == 1
        # Level 4: INT 14 → mod +2
        assert c.int_mod_at_level(4) == 2

    def test_inherent_int_at_level(self) -> None:
        c = _char_with_levels(8)
        c.set_ability_score("int", 13)  # mod +1
        c.add_inherent_bump(5, "int", 1)
        # Level 4: no inherent yet → mod +1
        assert c.int_mod_at_level(4) == 1
        # Level 5: inherent +1 → INT 14 → mod +2
        assert c.int_mod_at_level(5) == 2

    def test_multiple_int_bumps_accumulate(self) -> None:
        c = _char_with_levels(8)
        c.set_ability_score("int", 12)  # mod +1
        c.set_level_ability_bump(4, "int")  # +1
        c.set_level_ability_bump(8, "int")  # +1
        # Level 4: INT 13 → mod +1
        assert c.int_mod_at_level(4) == 1
        # Level 8: INT 14 → mod +2
        assert c.int_mod_at_level(8) == 2
