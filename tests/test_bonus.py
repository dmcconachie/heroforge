"""
tests/test_bonus.py
-------------------
Test suite for engine/bonus.py.

Covers every stacking rule, penalty behaviour, conditional entries,
pool mutation via the idempotent set_source/clear_source API, and the
breakdown helper.  Each test is named to describe exactly what rule or
behaviour it is verifying so failures are immediately actionable.
"""

import pytest

from heroforge.engine.bonus import (
    ALWAYS_STACKING,
    BonusEntry,
    BonusPool,
    BonusType,
    aggregate,
)

# ===========================================================================
# Fixtures & helpers
# ===========================================================================


def entry(
    value: int,
    btype: BonusType,
    source: str = "test",
    condition: object = None,
) -> BonusEntry:
    return BonusEntry(
        value=value, bonus_type=btype, source=source, condition=condition
    )


def pool(stat_key: str = "test_stat") -> BonusPool:
    return BonusPool(stat_key)


# ===========================================================================
# BonusType sanity
# ===========================================================================


class TestBonusType:
    def test_all_typed_non_stacking_not_in_always_stacking(
        self,
    ) -> None:
        typed_non_stacking = {
            BonusType.ENHANCEMENT,
            BonusType.MORALE,
            BonusType.LUCK,
            BonusType.DEFLECTION,
            BonusType.RESISTANCE,
            BonusType.COMPETENCE,
            BonusType.CIRCUMSTANCE,
            BonusType.SACRED,
            BonusType.PROFANE,
            BonusType.INSIGHT,
            BonusType.ALCHEMICAL,
            BonusType.ARMOR,
            BonusType.SHIELD,
            BonusType.NATURAL_ARMOR,
            BonusType.SIZE,
        }
        for bt in typed_non_stacking:
            assert bt not in ALWAYS_STACKING, f"{bt} should not always stack"

    def test_dodge_racial_untyped_in_always_stacking(self) -> None:
        for bt in (BonusType.DODGE, BonusType.RACIAL, BonusType.UNTYPED):
            assert bt in ALWAYS_STACKING


# ===========================================================================
# aggregate() — the core stacking function
# ===========================================================================


class TestAggregate:
    def test_single_typed_bonus_counts_fully(self) -> None:
        assert aggregate([entry(4, BonusType.ENHANCEMENT)]) == 4

    def test_two_same_type_only_highest_counts(self) -> None:
        entries = [
            entry(4, BonusType.ENHANCEMENT, "Bull's Strength"),
            entry(2, BonusType.ENHANCEMENT, "Gauntlets"),
        ]
        assert aggregate(entries) == 4

    def test_two_same_type_equal_value_not_doubled(self) -> None:
        entries = [
            entry(2, BonusType.MORALE, "Bless"),
            entry(2, BonusType.MORALE, "Prayer"),
        ]
        assert aggregate(entries) == 2

    def test_different_typed_bonuses_stack(self) -> None:
        entries = [
            entry(4, BonusType.ENHANCEMENT, "Bull's Strength"),
            entry(2, BonusType.MORALE, "Rage"),
        ]
        assert aggregate(entries) == 6

    def test_all_typed_non_stacking_types_each_contribute_highest(self) -> None:
        entries = [
            entry(1, bt)
            for bt in [
                BonusType.ENHANCEMENT,
                BonusType.MORALE,
                BonusType.LUCK,
                BonusType.DEFLECTION,
                BonusType.RESISTANCE,
                BonusType.COMPETENCE,
                BonusType.CIRCUMSTANCE,
                BonusType.SACRED,
                BonusType.PROFANE,
                BonusType.INSIGHT,
                BonusType.ALCHEMICAL,
                BonusType.ARMOR,
                BonusType.SHIELD,
                BonusType.NATURAL_ARMOR,
                BonusType.SIZE,
            ]
        ]
        assert aggregate(entries) == 15

    def test_dodge_bonuses_always_stack(self) -> None:
        entries = [
            entry(1, BonusType.DODGE, "Haste"),
            entry(1, BonusType.DODGE, "Dodge feat"),
        ]
        assert aggregate(entries) == 2

    def test_untyped_bonuses_always_stack(self) -> None:
        assert (
            aggregate(
                [entry(2, BonusType.UNTYPED), entry(3, BonusType.UNTYPED)]
            )
            == 5
        )

    def test_racial_bonuses_stack(self) -> None:
        assert (
            aggregate([entry(2, BonusType.RACIAL), entry(2, BonusType.RACIAL)])
            == 4
        )

    def test_penalties_always_stack_regardless_of_type(self) -> None:
        entries = [
            entry(-2, BonusType.MORALE, "Shaken"),
            entry(-2, BonusType.MORALE, "Sickened"),
        ]
        assert aggregate(entries) == -4

    def test_bonus_and_penalty_combine(self) -> None:
        entries = [
            entry(4, BonusType.ENHANCEMENT, "Bull's Strength"),
            entry(-2, BonusType.UNTYPED, "Exhausted"),
        ]
        assert aggregate(entries) == 2

    def test_empty_list_returns_zero(self) -> None:
        assert aggregate([]) == 0

    def test_complex_ac_scenario(self) -> None:
        """
        Armor+5, Shield+3, Deflection+2, Natural+3,
        Dodge+1 (Haste), Dodge+1 (feat), Untyped+1.
        Total = 5+3+2+3+1+1+1 = 16.
        """
        entries = [
            entry(5, BonusType.ARMOR, "Full Plate +1"),
            entry(3, BonusType.SHIELD, "Shield +1"),
            entry(2, BonusType.DEFLECTION, "Ring of Protection"),
            entry(3, BonusType.NATURAL_ARMOR, "Barkskin"),
            entry(1, BonusType.DODGE, "Haste"),
            entry(1, BonusType.DODGE, "Dodge feat"),
            entry(1, BonusType.UNTYPED, "Misc"),
        ]
        assert aggregate(entries) == 16

    # --- Conditional entries -----------------------------------------------

    class MockChar:
        def __init__(self, **kw: object) -> None:
            self.__dict__.update(kw)

    def test_active_condition_entry_is_included(self) -> None:
        char = self.MockChar(is_humanoid=True)
        e = entry(2, BonusType.ENHANCEMENT, condition=lambda c: c.is_humanoid)
        assert aggregate([e], char) == 2

    def test_inactive_condition_entry_is_excluded(self) -> None:
        char = self.MockChar(is_humanoid=False)
        e = entry(2, BonusType.ENHANCEMENT, condition=lambda c: c.is_humanoid)
        assert aggregate([e], char) == 0

    def test_conditional_entry_without_character_is_excluded(self) -> None:
        e = entry(4, BonusType.MORALE, condition=lambda c: c.raging)
        assert aggregate([e], character=None) == 0

    def test_conditional_wins_over_unconditional_same_type(self) -> None:
        char = self.MockChar(bs_active=True)
        entries = [
            entry(
                4,
                BonusType.ENHANCEMENT,
                "Bull's Strength",
                condition=lambda c: c.bs_active,
            ),
            entry(2, BonusType.ENHANCEMENT, "Gauntlets"),
        ]
        assert aggregate(entries, char) == 4

    def test_conditional_loses_when_inactive(self) -> None:
        char = self.MockChar(bs_active=False)
        entries = [
            entry(
                4,
                BonusType.ENHANCEMENT,
                "Bull's Strength",
                condition=lambda c: c.bs_active,
            ),
            entry(2, BonusType.ENHANCEMENT, "Gauntlets"),
        ]
        assert aggregate(entries, char) == 2


# ===========================================================================
# BonusPool — idempotent source-keyed API
# ===========================================================================


class TestBonusPool:
    def test_empty_pool_totals_zero(self) -> None:
        assert pool().total() == 0

    def test_set_source_registers_entries(self) -> None:
        p = pool()
        p.set_source("Bless", [entry(1, BonusType.MORALE)])
        assert p.total() == 1

    def test_set_source_is_idempotent(self) -> None:
        """Calling set_source twice with the same args gives the same result."""
        p = pool()
        e = entry(4, BonusType.ENHANCEMENT, "Bull's Strength")
        p.set_source("Bull's Strength", [e])
        p.set_source("Bull's Strength", [e])  # second call — must not double
        assert p.total() == 4
        assert len(p) == 1

    def test_set_source_overwrites_previous_entries(self) -> None:
        """Calling set_source with different entries replaces, not appends."""
        p = pool()
        p.set_source("item", [entry(2, BonusType.ENHANCEMENT, "old")])
        p.set_source("item", [entry(5, BonusType.ENHANCEMENT, "upgraded")])
        assert p.total() == 5
        assert len(p) == 1

    def test_clear_source_removes_entries(self) -> None:
        p = pool()
        p.set_source("Bless", [entry(1, BonusType.MORALE)])
        p.clear_source("Bless")
        assert p.total() == 0
        assert len(p) == 0

    def test_clear_source_is_idempotent(self) -> None:
        """Clearing an absent key is a silent no-op."""
        p = pool()
        p.clear_source("Nonexistent")  # must not raise
        p.clear_source("Nonexistent")
        assert p.total() == 0

    def test_clear_source_only_removes_named_source(self) -> None:
        p = pool()
        p.set_source("Bless", [entry(1, BonusType.MORALE, "Bless")])
        p.set_source("Prayer", [entry(1, BonusType.LUCK, "Prayer")])
        p.clear_source("Bless")
        assert p.total() == 1  # Prayer still active

    def test_clear_all_empties_pool(self) -> None:
        p = pool()
        p.set_source("A", [entry(1, BonusType.MORALE)])
        p.set_source("B", [entry(2, BonusType.LUCK)])
        p.clear_all()
        assert p.total() == 0
        assert len(p) == 0

    def test_multiple_sources_stacking_rules_apply_across_them(self) -> None:
        """Two morale bonuses from different sources: only highest counts."""
        p = pool()
        p.set_source("Bless", [entry(1, BonusType.MORALE, "Bless")])
        p.set_source("Prayer", [entry(2, BonusType.MORALE, "Prayer")])
        assert p.total() == 2  # not 3

    def test_multiple_entries_per_source(self) -> None:
        """One source contributing multiple entries."""
        p = pool()
        p.set_source(
            "Haste",
            [
                entry(1, BonusType.UNTYPED, "Haste atk"),
                entry(1, BonusType.DODGE, "Haste AC"),
            ],
        )
        assert p.total() == 2
        assert len(p) == 2

    def test_activate_deactivate_cycle_leaves_no_residue(self) -> None:
        """Toggle a buff on then off; pool should be exactly as it started."""
        p = pool()
        p.set_source("Bless", [entry(1, BonusType.MORALE)])
        p.clear_source("Bless")
        assert p.total() == 0
        assert p.source_keys() == []

    def test_repeated_activate_deactivate_cycle_stays_clean(self) -> None:
        p = pool()
        e = entry(4, BonusType.ENHANCEMENT, "Bull's Strength")
        for _ in range(5):
            p.set_source("Bull's Strength", [e])
            assert p.total() == 4
            p.clear_source("Bull's Strength")
            assert p.total() == 0

    def test_source_keys_returns_registered_keys(self) -> None:
        p = pool()
        p.set_source("A", [entry(1, BonusType.MORALE)])
        p.set_source("B", [entry(2, BonusType.LUCK)])
        assert set(p.source_keys()) == {"A", "B"}

    def test_entries_for_returns_correct_entries(self) -> None:
        p = pool()
        e1 = entry(1, BonusType.MORALE, "Bless")
        e2 = entry(2, BonusType.MORALE, "Prayer")
        p.set_source("Bless", [e1])
        p.set_source("Prayer", [e2])
        assert p.entries_for("Bless") == [e1]
        assert p.entries_for("Prayer") == [e2]

    def test_entries_for_absent_key_returns_empty(self) -> None:
        assert pool().entries_for("Ghost") == []

    def test_len_counts_total_entries_across_sources(self) -> None:
        p = pool()
        p.set_source(
            "A", [entry(1, BonusType.MORALE), entry(2, BonusType.LUCK)]
        )
        p.set_source("B", [entry(3, BonusType.DODGE)])
        assert len(p) == 3

    def test_active_entries_filters_conditions(self) -> None:
        class C:
            raging = True

        char = C()
        p = pool()
        rage_e = entry(
            4, BonusType.MORALE, "Rage", condition=lambda c: c.raging
        )
        bless_e = entry(1, BonusType.MORALE, "Bless")
        p.set_source("Rage", [rage_e])
        p.set_source("Bless", [bless_e])
        active = p.active_entries(char)
        assert rage_e in active
        assert bless_e in active

    def test_active_entries_excludes_inactive_conditions(self) -> None:
        class C:
            raging = False

        char = C()
        p = pool()
        p.set_source(
            "Rage", [entry(4, BonusType.MORALE, condition=lambda c: c.raging)]
        )
        assert p.active_entries(char) == []
        assert p.total(char) == 0

    def test_repr_is_informative(self) -> None:
        p = BonusPool("ac")
        p.set_source("item", [entry(4, BonusType.ARMOR)])
        r = repr(p)
        assert "ac" in r
        assert "1" in r  # 1 source

    # --- breakdown() -------------------------------------------------------

    def test_breakdown_single_entry(self) -> None:
        p = pool()
        p.set_source(
            "Bull's Strength",
            [entry(4, BonusType.ENHANCEMENT, "Bull's Strength")],
        )
        bd = p.breakdown()
        assert bd["Bull's Strength"] == 4

    def test_breakdown_winner_shows_value_loser_shows_zero(self) -> None:
        p = pool()
        p.set_source(
            "Bull's Strength",
            [entry(4, BonusType.ENHANCEMENT, "Bull's Strength")],
        )
        p.set_source(
            "Gauntlets", [entry(2, BonusType.ENHANCEMENT, "Gauntlets")]
        )
        bd = p.breakdown()
        assert bd["Bull's Strength"] == 4
        assert bd["Gauntlets"] == 0

    def test_breakdown_dodge_both_contribute(self) -> None:
        p = pool()
        p.set_source("Haste", [entry(1, BonusType.DODGE, "Haste")])
        p.set_source("Dodge feat", [entry(1, BonusType.DODGE, "Dodge feat")])
        bd = p.breakdown()
        assert bd["Haste"] == 1
        assert bd["Dodge feat"] == 1

    def test_breakdown_penalty_shown_at_full(self) -> None:
        p = pool()
        p.set_source("Shaken", [entry(-2, BonusType.UNTYPED, "Shaken")])
        p.set_source("Sickened", [entry(-2, BonusType.UNTYPED, "Sickened")])
        bd = p.breakdown()
        assert bd["Shaken"] == -2
        assert bd["Sickened"] == -2

    def test_breakdown_total_consistent_with_total(self) -> None:
        p = pool()
        p.set_source("A", [entry(4, BonusType.ENHANCEMENT, "A")])
        p.set_source("B", [entry(2, BonusType.ENHANCEMENT, "B")])
        p.set_source("C", [entry(2, BonusType.MORALE, "C")])
        p.set_source("D", [entry(1, BonusType.DODGE, "D")])
        p.set_source("E", [entry(-1, BonusType.UNTYPED, "E")])
        bd = p.breakdown()
        assert sum(bd.values()) == p.total()


# ===========================================================================
# BonusEntry — immutability and is_active
# ===========================================================================


class TestBonusEntry:
    def test_entry_is_frozen(self) -> None:
        e = entry(4, BonusType.ENHANCEMENT)
        with pytest.raises((AttributeError, TypeError)):
            e.value = 99  # type: ignore

    def test_is_active_no_condition_always_true(self) -> None:
        e = entry(4, BonusType.ENHANCEMENT)
        assert e.is_active() is True
        assert e.is_active(None) is True

    def test_is_active_condition_no_char_returns_false(self) -> None:
        e = entry(4, BonusType.ENHANCEMENT, condition=lambda c: c is not None)
        assert e.is_active(None) is False

    def test_entries_equal_when_fields_equal(self) -> None:
        a = entry(4, BonusType.ENHANCEMENT, "test")
        b = entry(4, BonusType.ENHANCEMENT, "test")
        assert a == b

    def test_entries_not_equal_when_fields_differ(self) -> None:
        a = entry(4, BonusType.ENHANCEMENT, "test")
        b = entry(2, BonusType.ENHANCEMENT, "test")
        assert a != b


# ===========================================================================
# Real 3.5e scenario tests
# ===========================================================================


class TestRealScenarios:
    def test_bulls_strength_and_gauntlets_only_highest(self) -> None:
        p = BonusPool("str_score")
        p.set_source(
            "Bull's Strength",
            [BonusEntry(4, BonusType.ENHANCEMENT, "Bull's Strength")],
        )
        p.set_source(
            "Gauntlets of Ogre Power",
            [BonusEntry(2, BonusType.ENHANCEMENT, "Gauntlets")],
        )
        assert p.total() == 4

    def test_haste_prayer_bless_all_stack(self) -> None:
        """All different types — all three apply."""
        p = BonusPool("attack_melee")
        p.set_source("Haste", [BonusEntry(1, BonusType.UNTYPED, "Haste")])
        p.set_source("Prayer", [BonusEntry(1, BonusType.LUCK, "Prayer")])
        p.set_source("Bless", [BonusEntry(1, BonusType.MORALE, "Bless")])
        assert p.total() == 3

    def test_two_bless_spells_do_not_stack(self) -> None:
        """Both morale type — only one +1 counts."""
        p = BonusPool("attack_melee")
        p.set_source("Bless A", [BonusEntry(1, BonusType.MORALE, "Bless A")])
        p.set_source("Bless B", [BonusEntry(1, BonusType.MORALE, "Bless B")])
        assert p.total() == 1

    def test_shaken_and_sickened_stack(self) -> None:
        p = BonusPool("attack_melee")
        p.set_source("Shaken", [BonusEntry(-2, BonusType.UNTYPED, "Shaken")])
        p.set_source(
            "Sickened", [BonusEntry(-2, BonusType.UNTYPED, "Sickened")]
        )
        assert p.total() == -4

    def test_mage_armor_and_bracers_only_highest(self) -> None:
        """Both armor type — higher wins."""
        p = BonusPool("ac")
        p.set_source(
            "Mage Armor", [BonusEntry(4, BonusType.ARMOR, "Mage Armor")]
        )
        p.set_source(
            "Bracers +3", [BonusEntry(3, BonusType.ARMOR, "Bracers +3")]
        )
        assert p.total() == 4

    def test_rage_and_bears_endurance_both_apply(self) -> None:
        """Morale (Rage) and Enhancement (Bear's Endurance)."""
        p = BonusPool("con_score")
        p.set_source("Rage", [BonusEntry(4, BonusType.MORALE, "Rage")])
        p.set_source(
            "Bear's Endurance",
            [BonusEntry(4, BonusType.ENHANCEMENT, "Bear's Endurance")],
        )
        assert p.total() == 8

    def test_inspire_courage_and_prayer_stack(self) -> None:
        """Morale vs Luck — both apply."""
        p = BonusPool("attack_melee")
        p.set_source(
            "Inspire Courage",
            [BonusEntry(2, BonusType.MORALE, "Inspire Courage")],
        )
        p.set_source("Prayer", [BonusEntry(1, BonusType.LUCK, "Prayer")])
        assert p.total() == 3

    def test_buff_toggle_cycle_exact_idempotence(self) -> None:
        """
        The core property: activating an already-active buff produces exactly
        the same pool state.  No guard needed; set_source overwrites.
        """
        p = BonusPool("attack_melee")
        e = BonusEntry(1, BonusType.MORALE, "Bless")

        # Activate once
        p.set_source("Bless", [e])
        total_after_first = p.total()

        # Activate again (as if the UI double-fired)
        p.set_source("Bless", [e])
        total_after_second = p.total()

        assert total_after_first == total_after_second == 1

    def test_deactivate_then_reactivate_restores_exact_value(self) -> None:
        p = BonusPool("str_score")
        e = BonusEntry(4, BonusType.ENHANCEMENT, "Bull's Strength")
        p.set_source("Bull's Strength", [e])
        assert p.total() == 4
        p.clear_source("Bull's Strength")
        assert p.total() == 0
        p.set_source("Bull's Strength", [e])
        assert p.total() == 4


class TestNaturalArmorEnhancement:
    """
    natural_armor_enhancement stacks with
    natural_armor but not with itself.
    """

    def test_stacks_with_natural_armor(self) -> None:
        p = BonusPool("ac")
        na = BonusEntry(1, BonusType.NATURAL_ARMOR, "Half-Celestial")
        nae = BonusEntry(
            3,
            BonusType.NATURAL_ARMOR_ENHANCEMENT,
            "Barkskin",
        )
        p.set_source("template", [na])
        p.set_source("spell", [nae])
        assert p.total() == 4  # 1 + 3

    def test_does_not_stack_with_itself(self) -> None:
        p = BonusPool("ac")
        b1 = BonusEntry(
            3,
            BonusType.NATURAL_ARMOR_ENHANCEMENT,
            "Barkskin",
        )
        b2 = BonusEntry(
            2,
            BonusType.NATURAL_ARMOR_ENHANCEMENT,
            "Amulet +2",
        )
        p.set_source("spell", [b1])
        p.set_source("item", [b2])
        # Only highest (3) applies
        assert p.total() == 3
