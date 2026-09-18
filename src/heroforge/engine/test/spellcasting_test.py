"""
Tests for the spellcasting module: spell slots, bonus
spells, spells known, spell save DCs.
"""

from __future__ import annotations

from heroforge.engine.spellcasting import (
    base_slots_per_day,
    bonus_spells,
    domain_slots_per_day,
    slots_per_day,
    spell_save_dc,
    spells_known,
)


class TestBaseSlots:
    def test_wizard_1(self) -> None:
        s = base_slots_per_day("Wizard", 1)
        assert s[0] == 3  # cantrips
        assert s[1] == 1  # 1st level
        assert s[2] is None  # no 2nd yet

    def test_wizard_20(self) -> None:
        s = base_slots_per_day("Wizard", 20)
        assert all(v == 4 for v in s)

    def test_sorcerer_1(self) -> None:
        s = base_slots_per_day("Sorcerer", 1)
        assert s[0] == 5
        assert s[1] == 3
        assert s[2] is None

    def test_cleric_5(self) -> None:
        s = base_slots_per_day("Cleric", 5)
        assert s[0] == 5
        assert s[3] == 1
        assert s[4] is None

    def test_bard_1(self) -> None:
        s = base_slots_per_day("Bard", 1)
        assert s[0] == 2
        assert len(s) == 7  # levels 0-6

    def test_paladin_3_no_spells(self) -> None:
        s = base_slots_per_day("Paladin", 3)
        assert s == []

    def test_paladin_4(self) -> None:
        s = base_slots_per_day("Paladin", 4)
        assert s[0] == 0  # 1st level slots
        assert s[1] is None

    def test_fighter_no_spells(self) -> None:
        s = base_slots_per_day("Fighter", 10)
        assert s == []


class TestBonusSpells:
    def test_mod_0(self) -> None:
        b = bonus_spells(0)
        assert b[0] == 0  # cantrips never bonus
        assert b[1] == 0
        assert b[9] == 0

    def test_mod_1(self) -> None:
        b = bonus_spells(1)
        assert b[0] == 0
        assert b[1] == 1  # 1 bonus 1st-level
        assert b[2] == 0

    def test_mod_5(self) -> None:
        b = bonus_spells(5)
        assert b[1] == 2  # (5-1)//4 + 1 = 2
        assert b[2] == 1
        assert b[5] == 1
        assert b[6] == 0

    def test_mod_10(self) -> None:
        b = bonus_spells(10)
        # lvl 1: (10-1)//4 + 1 = 3
        assert b[1] == 3
        assert b[9] == 1


class TestSlotsPerDay:
    def test_wizard_1_int_18(self) -> None:
        # INT 18 = mod 4
        s = slots_per_day("Wizard", 1, 18)
        assert s[0] == 3  # cantrips: no bonus
        assert s[1] == 2  # 1 base + 1 bonus
        assert s[2] is None

    def test_sorcerer_4_cha_16(self) -> None:
        # CHA 16 = mod 3
        s = slots_per_day("Sorcerer", 4, 16)
        assert s[0] == 6
        assert s[1] == 7  # 6 + 1
        assert s[2] == 4  # 3 + 1

    def test_no_bonus_to_unavailable(self) -> None:
        s = slots_per_day("Wizard", 1, 20)
        assert s[2] is None  # still unavailable


class TestSpellsKnown:
    def test_sorcerer_1(self) -> None:
        k = spells_known("Sorcerer", 1)
        assert k[0] == 4
        assert k[1] == 2
        assert k[2] is None

    def test_sorcerer_20(self) -> None:
        k = spells_known("Sorcerer", 20)
        assert k[0] == 9
        assert k[9] == 3

    def test_bard_4(self) -> None:
        k = spells_known("Bard", 4)
        assert k[0] == 6
        assert k[1] == 3
        assert k[2] == 2

    def test_wizard_not_spontaneous(self) -> None:
        k = spells_known("Wizard", 10)
        assert k == []


class TestSpellSaveDC:
    def test_basic(self) -> None:
        # INT mod 4, 3rd level spell
        assert spell_save_dc(4, 3) == 17

    def test_cantrip(self) -> None:
        assert spell_save_dc(3, 0) == 13


class TestDomainSlots:
    """
    PHB p. 32: a cleric gets one domain spell of each spell level
    he can cast, starting at 1st. It is a restricted slot, so it
    is tracked apart from the general allotment, never added to
    it, and never granted for orisons.
    """

    def test_cleric_1_gets_one_first_level_slot(self) -> None:
        slots = slots_per_day("Cleric", 1, 16)
        d = domain_slots_per_day(slots)
        assert d[0] is None  # no domain orison
        assert d[1] == 1

    def test_one_slot_per_castable_level(self) -> None:
        slots = slots_per_day("Cleric", 9, 18)
        d = domain_slots_per_day(slots)
        castable = [
            lvl
            for lvl, n in enumerate(slots)
            if lvl > 0 and n is not None and n >= 1
        ]
        assert castable  # guard: the fixture must exercise something
        for lvl in castable:
            assert d[lvl] == 1

    def test_no_slot_above_castable_range(self) -> None:
        slots = slots_per_day("Cleric", 1, 16)
        d = domain_slots_per_day(slots)
        assert all(x is None for x in d[2:])

    def test_does_not_alter_general_allotment(self) -> None:
        """The domain slot is additive elsewhere, not folded in."""
        slots = slots_per_day("Cleric", 5, 16)
        before = list(slots)
        domain_slots_per_day(slots)
        assert slots == before

    def test_high_ability_does_not_add_domain_slots(self) -> None:
        """Wisdom grants bonus spells, not extra domain slots."""
        low = domain_slots_per_day(slots_per_day("Cleric", 5, 12))
        high = domain_slots_per_day(slots_per_day("Cleric", 5, 20))
        assert low == high
