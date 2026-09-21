"""
Tests for alternative class features.

ACFs trade a standard class feature for a different one
(Complete Mage p. 31). Racial substitution levels are the same
shape with a race requirement, so they share this mechanism.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from heroforge.engine.acfs import (
    AcfDefinition,
    AcfRegistry,
    acf_slot_deltas,
    extra_prohibited_schools,
    replaced_feature_keys,
    validate_acf_selection,
)
from heroforge.engine.character import Character, CharacterLevel
from heroforge.engine.enums import Ability, School
from heroforge.engine.persistence import load_character, save_character
from heroforge.engine.sheet import gather_sheet
from heroforge.engine.spellcasting import Specialization
from heroforge.rules.known import KnownClass
from heroforge.rules.rules import get_rules


def wizard(levels: int, spec: Specialization | None = None) -> Character:
    c = Character()
    c.name = "ACF Wizard"
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


def focused_illusionist(levels: int = 5) -> Character:
    c = wizard(
        levels,
        Specialization(
            school=School.ILLUSION,
            prohibited=(
                School.ENCHANTMENT,
                School.NECROMANCY,
                School.EVOCATION,
            ),
        ),
    )
    c.acfs = [{"name": "Focused Specialist", "level": 1}]
    return c


class TestAcfRegistry:
    def test_focused_specialist_loads(self) -> None:
        defn = get_rules().acfs.get("Focused Specialist")
        assert defn is not None
        assert defn.classes == ("Wizard",)
        assert defn.levels == (1,)
        assert defn.requires.get("specialist") is True

    def test_spontaneous_divination_loads(self) -> None:
        defn = get_rules().acfs.get("Spontaneous Divination")
        assert defn is not None
        assert defn.levels == (5, 10, 15, 20)

    def test_no_longer_a_feat(self) -> None:
        """Migrated off the feat-as-ACF hack."""
        assert get_rules().feats.get("Spontaneous Divination") is None


class TestAcfValidation:
    def _defn(self, **kw: object) -> AcfDefinition:
        base = {
            "name": "Test ACF",
            "classes": ("Wizard",),
            "levels": (1,),
        }
        base.update(kw)
        return AcfDefinition(**base)  # type: ignore[arg-type]

    def test_valid_selection_passes(self) -> None:
        validate_acf_selection(wizard(5), self._defn(), 1)

    def test_wrong_class_rejected(self) -> None:
        c = Character()
        c.race = "Human"
        c.set_class_levels(
            [
                CharacterLevel(
                    character_level=1, class_name="Fighter", hp_roll=10
                )
            ]
        )
        with pytest.raises(ValueError, match="Wizard"):
            validate_acf_selection(c, self._defn(), 1)

    def test_level_not_offered_rejected(self) -> None:
        with pytest.raises(ValueError, match="level"):
            validate_acf_selection(wizard(5), self._defn(levels=(5,)), 3)

    def test_level_above_character_rejected(self) -> None:
        with pytest.raises(ValueError, match="level"):
            validate_acf_selection(wizard(2), self._defn(levels=(5,)), 5)

    def test_specialist_requirement_enforced(self) -> None:
        defn = self._defn(requires={"specialist": True})
        with pytest.raises(ValueError, match="specialist"):
            validate_acf_selection(wizard(5), defn, 1)

    def test_specialist_requirement_met(self) -> None:
        defn = self._defn(requires={"specialist": True})
        c = wizard(5, Specialization(school=School.ILLUSION))
        validate_acf_selection(c, defn, 1)

    def test_race_requirement_enforced(self) -> None:
        """Racial substitution levels ride the same mechanism."""
        defn = self._defn(requires={"race": "Dwarf"})
        with pytest.raises(ValueError, match="Dwarf"):
            validate_acf_selection(wizard(5), defn, 1)

    def test_race_requirement_met(self) -> None:
        defn = self._defn(requires={"race": "Dwarf"})
        c = wizard(5)
        c.race = "Dwarf"
        validate_acf_selection(c, defn, 1)


class TestFeatureReplacement:
    def test_replaced_feature_hidden_from_sheet(self) -> None:
        c = wizard(10)
        c.acfs = [{"name": "Spontaneous Divination", "level": 10}]
        keys = replaced_feature_keys(c)
        assert "bonus_feat_wizard_10" in keys
        features = gather_sheet(c).class_features
        assert not [f for f in features if f.startswith("bonus_feat_wizard_10")]

    def test_other_levels_untouched(self) -> None:
        c = wizard(10)
        c.acfs = [{"name": "Spontaneous Divination", "level": 10}]
        features = gather_sheet(c).class_features
        assert [f for f in features if f.startswith("bonus_feat_wizard_5")]

    def test_no_acfs_replaces_nothing(self) -> None:
        assert replaced_feature_keys(wizard(10)) == set()


class TestFocusedSpecialist:
    """
    Complete Mage p. 34: lose one spell slot from each level you
    can cast and one more prohibited school, gain two more
    specialty slots per level.
    """

    def test_slot_deltas(self) -> None:
        general, specialty = acf_slot_deltas(focused_illusionist())
        assert general == -1
        assert specialty == 2

    def test_extra_prohibited_school_required(self) -> None:
        assert extra_prohibited_schools(focused_illusionist()) == 1
        assert extra_prohibited_schools(wizard(5)) == 0

    def test_general_slots_reduced(self) -> None:
        plain = gather_sheet(wizard(5)).spellcasting[KnownClass("Wizard")]
        foc = gather_sheet(focused_illusionist()).spellcasting[
            KnownClass("Wizard")
        ]
        for lvl, base in enumerate(plain.slots_per_day):
            if base is None:
                continue
            assert foc.slots_per_day[lvl] == base - 1

    def test_three_specialty_slots_per_level(self) -> None:
        foc = gather_sheet(focused_illusionist()).spellcasting[
            KnownClass("Wizard")
        ]
        assert foc.specialist_slots_per_day is not None
        assert foc.specialist_slots_per_day[0] == 3
        assert foc.specialist_slots_per_day[1] == 3

    def test_requires_three_prohibited_schools(self, tmp_path: Path) -> None:
        c = wizard(
            5,
            Specialization(
                school=School.ILLUSION,
                prohibited=(School.ENCHANTMENT, School.NECROMANCY),
            ),
        )
        c.acfs = [{"name": "Focused Specialist", "level": 1}]
        path = tmp_path / "bad.char.yaml"
        save_character(c, path)
        with pytest.raises(ValueError, match="3 prohibited"):
            load_character(path)

    def test_requires_specialist(self, tmp_path: Path) -> None:
        c = wizard(5)
        c.acfs = [{"name": "Focused Specialist", "level": 1}]
        path = tmp_path / "bad.char.yaml"
        save_character(c, path)
        with pytest.raises(ValueError, match="specialist"):
            load_character(path)


class TestAcfPersistence:
    def test_round_trip(self, tmp_path: Path) -> None:
        c = focused_illusionist()
        path = tmp_path / "acf.char.yaml"
        save_character(c, path)
        reloaded = load_character(path)
        assert reloaded.acfs == [{"name": "Focused Specialist", "level": 1}]

    def test_unknown_acf_rejected(self, tmp_path: Path) -> None:
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
            "acfs:\n"
            "  - name: Not An ACF\n"
            "    level: 1\n"
        )
        with pytest.raises(ValueError, match="Not An ACF"):
            load_character(path)


class TestAcfRegistryBasics:
    def test_register_and_get(self) -> None:
        reg = AcfRegistry()
        defn = AcfDefinition(name="X", classes=("Wizard",), levels=(1,))
        reg.register(defn)
        assert reg.get("X") is defn
        assert reg.names() == ["X"]
        assert len(reg) == 1
