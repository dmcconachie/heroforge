"""
Every spell carries a school, and its subschool and descriptors
use the published vocabularies (PHB pp. 172-175).

School data is what prohibited-school and specialty-slot rules
have to be checked against, so gaps here silently disable those
rules rather than failing loudly.
"""

from __future__ import annotations

import pytest

from heroforge.engine.enums import School
from heroforge.rules.rules import get_rules

# PHB p. 173. Conjuration also prints "Creation or Calling".
SUBSCHOOLS = {
    "Calling",
    "Charm",
    "Compulsion",
    "Creation",
    "Figment",
    "Glamer",
    "Healing",
    "Pattern",
    "Phantasm",
    "Scrying",
    "Shadow",
    "Summoning",
    "Teleportation",
}

# PHB p. 174.
DESCRIPTORS = {
    "Acid",
    "Air",
    "Chaotic",
    "Cold",
    "Darkness",
    "Death",
    "Earth",
    "Electricity",
    "Evil",
    "Fear",
    "Fire",
    "Force",
    "Good",
    "Language-Dependent",
    "Lawful",
    "Light",
    "Mind-Affecting",
    "Sonic",
    "Water",
}


def _spells() -> list:
    return get_rules().spells.all_entries()


def _tokens(raw: str) -> list[str]:
    """Split a multi-valued cell, tolerating 'X or Y' and 'X, Y'."""
    out: list[str] = []
    for part in raw.replace(" or ", ",").split(","):
        part = part.strip()
        if part and not part.startswith("see text"):
            out.append(part)
    return out


class TestSpellSchools:
    def test_every_spell_has_a_school(self) -> None:
        missing = [s.name for s in _spells() if not s.school]
        assert not missing, (
            f"{len(missing)} spells lack a school: {missing[:10]}"
        )

    def test_schools_are_valid(self) -> None:
        valid = {s.value for s in School} | {"Universal"}
        bad = {s.name: s.school for s in _spells() if s.school not in valid}
        assert not bad, f"unknown schools: {bad}"

    def test_subschools_are_valid(self) -> None:
        bad = {
            s.name: s.subschool
            for s in _spells()
            if s.subschool
            and any(t not in SUBSCHOOLS for t in _tokens(s.subschool))
        }
        assert not bad, f"unknown subschools: {bad}"

    def test_descriptors_are_valid(self) -> None:
        bad = {
            s.name: s.descriptor
            for s in _spells()
            if s.descriptor
            and any(t not in DESCRIPTORS for t in _tokens(s.descriptor))
        }
        assert not bad, f"unknown descriptors: {bad}"


class TestSpellMetaSpotChecks:
    @pytest.mark.parametrize(
        ("name", "school", "subschool", "descriptor"),
        [
            ("Fireball", "Evocation", "", "Fire"),
            ("Magic Missile", "Evocation", "", "Force"),
            ("Silent Image", "Illusion", "Figment", ""),
            ("Charm Person", "Enchantment", "Charm", "Mind-Affecting"),
            ("Teleport", "Conjuration", "Teleportation", ""),
            ("Cure Light Wounds", "Conjuration", "Healing", ""),
            ("Holy Smite", "Evocation", "", "Good"),
            ("Unholy Blight", "Evocation", "", "Evil"),
            ("Chaos Hammer", "Evocation", "", "Chaotic"),
            ("Order's Wrath", "Evocation", "", "Lawful"),
            # PHB prints "Conjuration [Creation]", but Creation is a
            # subschool and there is no Creation descriptor.
            ("Heroes' Feast", "Conjuration", "Creation", ""),
        ],
    )
    def test_spot_check(
        self, name: str, school: str, subschool: str, descriptor: str
    ) -> None:
        entry = get_rules().spells.get(name)
        assert entry is not None, f"{name} missing from the compendium"
        assert entry.school == school
        assert entry.subschool == subschool
        assert entry.descriptor == descriptor

    def test_specialty_school_can_be_matched(self) -> None:
        """The point of the data: schools are comparable to School."""
        fireball = get_rules().spells.get("Fireball")
        assert fireball is not None
        assert fireball.school == School.EVOCATION
