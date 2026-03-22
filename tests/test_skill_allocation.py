"""
tests/test_skill_allocation.py
------------------------------
Tests for per-level skill budget, max ranks,
and validation.
"""

from __future__ import annotations

from heroforge.engine.character import (
    Character,
)
from heroforge.engine.skills import (
    compute_skill_budget,
    max_skill_ranks,
)

# ===============================================
# compute_skill_budget
# ===============================================


class TestComputeSkillBudget:
    def test_level_1_is_quadrupled(self) -> None:
        # Fighter (2 + 0 INT) * 4 = 8
        assert compute_skill_budget(2, 0, 1) == 8

    def test_level_2_is_not_quadrupled(self) -> None:
        assert compute_skill_budget(2, 0, 2) == 2

    def test_int_mod_adds(self) -> None:
        # 2 + 3 INT mod = 5
        assert compute_skill_budget(2, 3, 2) == 5

    def test_human_bonus(self) -> None:
        # 2 + 0 + 1 human = 3
        assert compute_skill_budget(2, 0, 2, is_human=True) == 3

    def test_human_bonus_at_level_1(self) -> None:
        # (2 + 0 + 1) * 4 = 12
        assert compute_skill_budget(2, 0, 1, is_human=True) == 12

    def test_minimum_1(self) -> None:
        # 2 + (-4) = -2 → clamped to 1
        assert compute_skill_budget(2, -4, 2) == 1

    def test_minimum_1_at_level_1(self) -> None:
        # min(1) * 4 = 4
        assert compute_skill_budget(2, -4, 1) == 4

    def test_rogue_high_int(self) -> None:
        # Rogue (8) + 2 INT = 10
        assert compute_skill_budget(8, 2, 3) == 10


# ===============================================
# max_skill_ranks
# ===============================================


class TestMaxSkillRanks:
    def test_class_skill_level_1(self) -> None:
        assert max_skill_ranks(1, True) == 4.0

    def test_class_skill_level_5(self) -> None:
        assert max_skill_ranks(5, True) == 8.0

    def test_cross_class_level_1(self) -> None:
        assert max_skill_ranks(1, False) == 2.0

    def test_cross_class_level_5(self) -> None:
        assert max_skill_ranks(5, False) == 4.0


# ===============================================
# Character.add_level / remove_last_level
# ===============================================


class TestCharacterLevelMethods:
    def test_add_level(self) -> None:
        c = Character()
        c.add_level("Fighter", 10)
        assert len(c.levels) == 1
        assert c.levels[0].class_name == "Fighter"
        assert c.levels[0].hp_roll == 10
        assert c.levels[0].character_level == 1

    def test_add_two_levels(self) -> None:
        c = Character()
        c.add_level("Fighter", 10)
        c.add_level("Rogue", 6)
        assert len(c.levels) == 2
        assert c.levels[1].character_level == 2
        assert c.levels[1].class_name == "Rogue"

    def test_remove_last_level(self) -> None:
        c = Character()
        c.add_level("Fighter", 10)
        c.add_level("Rogue", 6)
        c.remove_last_level()
        assert len(c.levels) == 1
        assert c.levels[0].class_name == "Fighter"

    def test_remove_from_empty(self) -> None:
        c = Character()
        c.remove_last_level()  # no error
        assert len(c.levels) == 0

    def test_class_level_map(self) -> None:
        c = Character()
        c.add_level("Fighter", 10)
        c.add_level("Fighter", 8)
        c.add_level("Rogue", 6)
        assert c.class_level_map == {
            "Fighter": 2,
            "Rogue": 1,
        }

    def test_total_level(self) -> None:
        c = Character()
        c.add_level("Fighter", 10)
        c.add_level("Fighter", 8)
        assert c.total_level == 2

    def test_set_level_class(self) -> None:
        c = Character()
        c.add_level("Fighter", 10)
        c.set_level_class(1, "Rogue")
        assert c.levels[0].class_name == "Rogue"

    def test_set_level_hp(self) -> None:
        c = Character()
        c.add_level("Fighter", 10)
        c.set_level_hp(1, 7)
        assert c.levels[0].hp_roll == 7

    def test_set_level_skill_ranks(self) -> None:
        c = Character()
        c.add_level("Fighter", 10)
        c.set_level_skill_ranks(1, {"Climb": 4})
        assert c.levels[0].skill_ranks == {"Climb": 4}

    def test_hp_from_levels(self) -> None:
        c = Character()
        c.add_level("Fighter", 10)
        c.add_level("Fighter", 8)
        assert c._compute_hp_from_rolls() == 18


# ===============================================
# skill_points_for_level
# ===============================================


class TestSkillPointsForLevel:
    def test_without_registry(self) -> None:
        c = Character()
        c.add_level("Fighter", 10)
        # No registry → uses default 2, INT 10 → mod 0
        # Level 1: (2 + 0) * 4 = 8
        assert c.skill_points_for_level(1) == 8

    def test_human_bonus(self) -> None:
        c = Character()
        c.race = "Human"
        c.add_level("Fighter", 10)
        # (2 + 0 + 1) * 4 = 12
        assert c.skill_points_for_level(1) == 12

    def test_level_2(self) -> None:
        c = Character()
        c.add_level("Fighter", 10)
        c.add_level("Fighter", 8)
        # Level 2: 2 + 0 = 2
        assert c.skill_points_for_level(2) == 2
