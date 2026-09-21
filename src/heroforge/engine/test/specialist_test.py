"""
Tests for wizard school specialization (PHB p. 57).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from heroforge.engine.character import Character, CharacterLevel
from heroforge.engine.enums import Ability, School
from heroforge.engine.persistence import load_character, save_character
from heroforge.engine.sheet import gather_sheet
from heroforge.engine.spellcasting import (
    Specialization,
    slots_per_day,
    specialist_slots_per_day,
    validate_specialization,
)
from heroforge.rules.known import KnownClass


def wizard(levels: int, spec: Specialization | None = None) -> Character:
    c = Character()
    c.name = "Test Wizard"
    c.race = "Human"
    c.alignment = "neutral"
    c.set_ability_score(Ability.INT, 16)
    c.set_class_levels(
        [
            CharacterLevel(
                character_level=i + 1, class_name="Wizard", hp_roll=4
            )
            for i in range(levels)
        ]
    )
    c.specialization = spec
    return c


def illusionist() -> Specialization:
    return Specialization(
        school=School.ILLUSION,
        prohibited=(School.ENCHANTMENT, School.NECROMANCY),
    )


class TestSpecialistSlots:
    """
    PHB p. 57: "A specialist wizard can prepare one additional
    spell of her specialty school per spell level each day."
    Level 0 is a spell level, and the prohibited-school rule
    explicitly reaches cantrips, so the bonus starts there.
    """

    def test_one_per_castable_level_including_cantrips(self) -> None:
        slots = slots_per_day("Wizard", 1, 16)
        s = specialist_slots_per_day(slots)
        assert s[0] == 1
        assert s[1] == 1

    def test_none_above_castable_range(self) -> None:
        slots = slots_per_day("Wizard", 1, 16)
        s = specialist_slots_per_day(slots)
        assert all(x is None for x in s[2:])

    def test_does_not_scale_with_int(self) -> None:
        low = specialist_slots_per_day(slots_per_day("Wizard", 5, 12))
        high = specialist_slots_per_day(slots_per_day("Wizard", 5, 20))
        assert low == high

    def test_general_allotment_untouched(self) -> None:
        slots = slots_per_day("Wizard", 5, 16)
        before = list(slots)
        specialist_slots_per_day(slots)
        assert slots == before


class TestSpecializationValidation:
    def test_valid_passes(self) -> None:
        validate_specialization(illusionist())  # must not raise

    def test_specialty_cannot_be_prohibited(self) -> None:
        spec = Specialization(
            school=School.ILLUSION,
            prohibited=(School.ILLUSION, School.NECROMANCY),
        )
        with pytest.raises(ValueError, match="own specialty"):
            validate_specialization(spec)

    def test_divination_cannot_be_prohibited(self) -> None:
        spec = Specialization(
            school=School.ILLUSION,
            prohibited=(School.DIVINATION, School.NECROMANCY),
        )
        with pytest.raises(ValueError, match="[Dd]ivination"):
            validate_specialization(spec)

    def test_two_prohibited_required(self) -> None:
        spec = Specialization(
            school=School.ILLUSION, prohibited=(School.NECROMANCY,)
        )
        with pytest.raises(ValueError, match="2 prohibited"):
            validate_specialization(spec)

    def test_diviner_gives_up_only_one(self) -> None:
        spec = Specialization(
            school=School.DIVINATION, prohibited=(School.NECROMANCY,)
        )
        validate_specialization(spec)  # must not raise


class TestSpecialistSheet:
    def test_sheet_reports_specialization(self) -> None:
        entry = gather_sheet(wizard(5, illusionist())).spellcasting[
            KnownClass("Wizard")
        ]
        assert entry.specialty_school == School.ILLUSION
        assert set(entry.prohibited_schools) == {
            School.ENCHANTMENT,
            School.NECROMANCY,
        }
        assert entry.specialist_slots_per_day is not None
        assert entry.specialist_slots_per_day[1] == 1

    def test_generalist_has_no_specialist_fields(self) -> None:
        entry = gather_sheet(wizard(5)).spellcasting[KnownClass("Wizard")]
        assert entry.specialty_school is None
        assert entry.specialist_slots_per_day is None
        assert entry.prohibited_schools == []

    def test_specialization_does_not_change_general_slots(self) -> None:
        plain = gather_sheet(wizard(5)).spellcasting[KnownClass("Wizard")]
        spec = gather_sheet(wizard(5, illusionist())).spellcasting[
            KnownClass("Wizard")
        ]
        assert spec.slots_per_day == plain.slots_per_day


class TestSpecializationPersistence:
    def test_round_trip(self, tmp_path: Path) -> None:
        c = wizard(5, illusionist())
        path = tmp_path / "spec.char.yaml"
        save_character(c, path)
        reloaded = load_character(path)
        assert reloaded.specialization == illusionist()

    def test_generalist_round_trip(self, tmp_path: Path) -> None:
        c = wizard(5)
        path = tmp_path / "plain.char.yaml"
        save_character(c, path)
        assert load_character(path).specialization is None

    def test_load_rejects_invalid(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.char.yaml"
        path.write_text(
            "identity:\n"
            "  name: X\n"
            "  race: Human\n"
            "  alignment: neutral\n"
            "levels:\n"
            "  - level: 1\n"
            "    class: Wizard\n"
            "    hp_roll: 4\n"
            "specialization:\n"
            "  school: Illusion\n"
            "  prohibited:\n"
            "    - Divination\n"
            "    - Necromancy\n"
        )
        with pytest.raises(ValueError, match="[Dd]ivination"):
            load_character(path)
