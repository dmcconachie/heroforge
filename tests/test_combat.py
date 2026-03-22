"""
Tests for grapple modifier, carrying capacity, and size
modifiers added in Phase 5.
"""

from __future__ import annotations

import pytest

from heroforge.engine.character import Character


@pytest.fixture()
def char() -> Character:
    return Character()


class TestGrappleModifier:
    """Grapple = BAB + STR mod + size grapple mod."""

    def test_medium_grapple_zero_level(self, char: Character) -> None:
        # STR 10 → mod 0, BAB 0, Medium → size 0
        char.set_ability_score("str", 10)
        assert char.get("grapple") == 0

    def test_medium_grapple_with_str(self, char: Character) -> None:
        char.set_ability_score("str", 18)
        # mod 4, BAB 0, Medium → 0+4+0 = 4
        assert char.get("grapple") == 4

    def test_small_grapple(self, char: Character) -> None:
        char.set_ability_score("str", 10)
        char._size_override = "Small"
        # BAB 0 + STR 0 + Small(-4) = -4
        assert char.get("grapple") == -4

    def test_large_grapple(self, char: Character) -> None:
        char.set_ability_score("str", 10)
        char._size_override = "Large"
        # BAB 0 + STR 0 + Large(+4) = 4
        assert char.get("grapple") == 4


class TestSizeModifiers:
    """Size modifier helpers."""

    def test_hide_small(self, char: Character) -> None:
        char._size_override = "Small"
        assert char._compute_size_mod_hide() == 4

    def test_hide_large(self, char: Character) -> None:
        char._size_override = "Large"
        assert char._compute_size_mod_hide() == -4

    def test_hide_fine(self, char: Character) -> None:
        char._size_override = "Fine"
        assert char._compute_size_mod_hide() == 16

    def test_grapple_colossal(self, char: Character) -> None:
        char._size_override = "Colossal"
        assert char._compute_size_mod_grapple() == 16

    def test_grapple_tiny(self, char: Character) -> None:
        char._size_override = "Tiny"
        assert char._compute_size_mod_grapple() == -8


class TestCarryingCapacity:
    """STR-based carrying capacity with size mult."""

    def test_str_10_medium(self, char: Character) -> None:
        char.set_ability_score("str", 10)
        light, med, heavy = char.carrying_capacity()
        assert light == 33
        assert med == 66
        assert heavy == 100

    def test_str_18_medium(self, char: Character) -> None:
        char.set_ability_score("str", 18)
        light, med, heavy = char.carrying_capacity()
        assert light == 100
        assert med == 200
        assert heavy == 300

    def test_str_1_medium(self, char: Character) -> None:
        char.set_ability_score("str", 1)
        light, med, heavy = char.carrying_capacity()
        assert light == 3
        assert med == 6
        assert heavy == 10

    def test_small_size_multiplier(self, char: Character) -> None:
        char.set_ability_score("str", 10)
        char._size_override = "Small"
        light, med, heavy = char.carrying_capacity()
        # Medium: 33/66/100 × 3/4
        assert light == 24
        assert med == 49
        assert heavy == 75

    def test_large_size_multiplier(self, char: Character) -> None:
        char.set_ability_score("str", 10)
        char._size_override = "Large"
        light, med, heavy = char.carrying_capacity()
        # Medium: 33/66/100 × 2
        assert light == 66
        assert med == 132
        assert heavy == 200

    def test_str_29_medium(self, char: Character) -> None:
        char.set_ability_score("str", 29)
        light, med, heavy = char.carrying_capacity()
        assert light == 466
        assert med == 933
        assert heavy == 1400
