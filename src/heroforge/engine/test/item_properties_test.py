"""
Armour, shield and weapon special properties.

Only properties that apply permanently are wired to stats.
Anything activated (blinking, 1/day), reactive (arrow
deflection) or conditional on the target (bane, wounding)
stays display-only, because a number on the sheet would be
wrong most of the time.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from heroforge.engine.character import Character, CharacterLevel
from heroforge.engine.equipment import equip_armor, unequip_armor
from heroforge.engine.item_properties import (
    ItemPropertyDefinition,
    property_definition,
)
from heroforge.engine.persistence import load_character
from heroforge.engine.sheet import gather_sheet
from heroforge.engine.skills import (
    compute_skill_total,
    register_skills_on_character,
)
from heroforge.engine.weapons import register_weapons_on_character
from heroforge.rules.rules import get_rules


def _char(cls: str = "Rogue", level: int = 12) -> Character:
    c = Character(name="Sneak")
    register_skills_on_character(c)
    for ab in ("str", "dex", "con", "int", "wis", "cha"):
        c.set_ability_score(ab, 10)
    c.levels = [
        CharacterLevel(character_level=i + 1, class_name=cls, hp_roll=6)
        for i in range(level)
    ]
    c._invalidate_class_stats()
    return c


def _skill(c: Character, name: str) -> int:
    defn = get_rules().skills.get(name)
    assert defn is not None
    return compute_skill_total(c, defn).total


def _wear(c: Character, *properties: str) -> Character:
    armor = get_rules().armor.get("Chain Shirt")
    equip_armor(c, armor, properties=list(properties))
    return c


class TestRegistry:
    def test_lookup_is_case_insensitive(self) -> None:
        assert property_definition("Greater Shadow") is not None
        assert property_definition("greater shadow") is not None

    def test_an_unknown_property_is_none(self) -> None:
        assert property_definition("not a real property") is None

    def test_definitions_declare_what_they_apply_to(self) -> None:
        defn = property_definition("greater shadow")
        assert isinstance(defn, ItemPropertyDefinition)
        assert defn.applies_to == "armor"


class TestPermanentArmourProperties:
    """DMG p. 219; the armour check penalty still applies."""

    @pytest.mark.parametrize(
        ("prop", "bonus"),
        [("shadow", 5), ("improved shadow", 10), ("greater shadow", 15)],
    )
    def test_shadow_family_bonuses_hide(self, prop: str, bonus: int) -> None:
        plain = _skill(_wear(_char()), "Hide")
        assert _skill(_wear(_char(), prop), "Hide") == plain + bonus

    @pytest.mark.parametrize(
        ("prop", "bonus"),
        [
            ("silent moves", 5),
            ("improved silent moves", 10),
            ("greater silent moves", 15),
        ],
    )
    def test_silent_moves_family(self, prop: str, bonus: int) -> None:
        plain = _skill(_wear(_char()), "Move Silently")
        assert _skill(_wear(_char(), prop), "Move Silently") == (plain + bonus)

    def test_blueshine_bonuses_hide(self) -> None:
        """MIC: +2 competence on Hide."""
        plain = _skill(_wear(_char()), "Hide")
        assert _skill(_wear(_char(), "blueshine"), "Hide") == plain + 2

    def test_they_do_not_stack_with_each_other(self) -> None:
        """Both are competence bonuses, so only the best counts."""
        plain = _skill(_wear(_char()), "Hide")
        both = _wear(_char(), "greater shadow", "blueshine")
        assert _skill(both, "Hide") == plain + 15

    def test_removing_the_armour_removes_the_bonus(self) -> None:
        bare = _skill(_char(), "Hide")
        c = _wear(_char(), "greater shadow")
        assert _skill(c, "Hide") > bare
        unequip_armor(c)
        # Back to the unarmoured baseline: the property's
        # bonus went with the armour, as did its check penalty.
        assert _skill(c, "Hide") == bare


class TestActivatedPropertiesAreNotWired:
    """
    These are real properties with real numbers, but the
    numbers apply only when used or against certain targets.
    They are defined so the name is recognised, and carry no
    effects.
    """

    @pytest.mark.parametrize(
        "prop",
        [
            "blinking",
            "vanishing",
            "mindarmor",
            "animated",
            "arrow deflection",
            "mind cloaking",
        ],
    )
    def test_no_stat_change(self, prop: str) -> None:
        assert property_definition(prop) is not None
        plain = _skill(_wear(_char()), "Hide")
        assert _skill(_wear(_char(), prop), "Hide") == plain

    def test_they_still_show_on_the_sheet(self) -> None:
        c = _wear(_char(), "blinking")
        assert "blinking" in gather_sheet(c, None).equipment.armor.properties


class TestSpeedWeapon:
    """
    DMG: one extra attack at the wielder's full base attack
    bonus when making a full attack."""

    def _armed(self, *props: str) -> Character:
        c = _char(cls="Fighter", level=6)
        c.equipment["weapons"] = [
            {"base": "Longsword", "properties": list(props)}
        ]
        register_weapons_on_character(c)
        return c

    def test_plain_weapon_iteratives(self) -> None:
        w = gather_sheet(self._armed(), None).equipment.weapons[0]
        assert len(w.attack_iteratives) == 2

    def test_speed_adds_one_attack_at_the_top(self) -> None:
        w = gather_sheet(self._armed("speed"), None).equipment.weapons[0]
        assert len(w.attack_iteratives) == 3
        assert w.attack_iteratives[0] == w.attack_iteratives[1]

    def test_speed_is_not_a_bonus_on_the_line(self) -> None:
        plain = gather_sheet(self._armed(), None).equipment.weapons[0]
        fast = gather_sheet(self._armed("speed"), None).equipment.weapons[0]
        assert fast.attack.total == plain.attack.total


class TestItPersists:
    CHAR = """
identity:
  name: Shady
  race: Human
  alignment: neutral
ability_scores: {str: 10, dex: 10, con: 10, int: 10, wis: 10, cha: 10}
levels:
  - {level: 1, class: Rogue, hp_roll: 6}
equipment:
  armor:
    base: Chain Shirt
    properties:
      - greater shadow
  weapons:
    - base: Longsword
      properties:
        - speed
"""

    def test_properties_survive_a_load(self, tmp_path: Path) -> None:
        path = tmp_path / "s.char.yaml"
        path.write_text(self.CHAR)
        c = load_character(path, None)
        sheet = gather_sheet(c, None)
        assert sheet.skills["Hide"].typed["competence"] == 15
        assert len(sheet.equipment.weapons[0].attack_iteratives) == 2


class TestTheRestOfTheSrdList:
    """
    The SRD's armour and weapon special-ability lists in full.
    Three of them are permanent and land on a stat the engine
    already models; the rest are defined but inert.
    """

    @pytest.mark.parametrize(
        ("prop", "bonus"),
        [("slick", 5), ("improved slick", 10), ("greater slick", 15)],
    )
    def test_slick_family_bonuses_escape_artist(
        self, prop: str, bonus: int
    ) -> None:
        plain = _skill(_wear(_char()), "Escape Artist")
        assert _skill(_wear(_char(), prop), "Escape Artist") == (plain + bonus)

    @pytest.mark.parametrize("sr", [13, 15, 17, 19])
    def test_spell_resistance_grades(self, sr: int) -> None:
        c = _wear(_char(), f"spell resistance ({sr})")
        assert c.get("sr") == sr

    def test_spell_resistance_does_not_stack(self) -> None:
        """The highest applies, which the sr node already does."""
        c = _wear(_char(), "spell resistance (13)", "spell resistance (19)")
        assert c.get("sr") == 19

    def test_distance_doubles_a_range_increment(self) -> None:
        from heroforge.engine.sheet import gather_sheet

        def inc(*props: str) -> int:
            c = _char()
            c.equipment["weapons"] = [
                {"base": "Longbow", "properties": list(props)}
            ]
            register_weapons_on_character(c)
            return gather_sheet(c, None).equipment.weapons[0].range_inc

        assert inc() == 100
        assert inc("distance") == 200

    def test_distance_is_written_either_way(self) -> None:
        assert property_definition("Distance") is not None

    @pytest.mark.parametrize(
        "prop",
        ["shadow, greater", "greater shadow", "Shadow, Greater"],
    )
    def test_grade_forms_all_resolve(self, prop: str) -> None:
        defn = property_definition(prop)
        assert defn is not None
        assert defn.name == "Shadow, Greater"

    @pytest.mark.parametrize(
        "prop",
        ["fire resistance", "invulnerability", "fortification, light"],
    )
    def test_permanent_but_unmodelled_are_inert(self, prop: str) -> None:
        """
        Energy resistance, damage reduction and a chance to
        negate a critical are permanent, but none of them is a
        stat the sheet carries. Defined, described, inert.
        """
        defn = property_definition(prop)
        assert defn is not None
        assert defn.effects == ()

    def test_every_srd_ability_is_defined(self) -> None:
        """Nothing on the two SRD pages is missing."""
        registry = get_rules().item_properties
        missing = [
            n
            for n in (
                "Animated",
                "Arrow Catching",
                "Arrow Deflection",
                "Bashing",
                "Blinding",
                "Etherealness",
                "Fortification, Light",
                "Ghost Touch",
                "Glamered",
                "Invulnerability",
                "Reflecting",
                "Shadow",
                "Silent Moves",
                "Slick",
                "Spell Resistance (13)",
                "Undead Controlling",
                "Wild",
                "Acid Resistance",
                "Cold Resistance",
                "Electricity Resistance",
                "Fire Resistance",
                "Sonic Resistance",
                "Anarchic",
                "Axiomatic",
                "Bane",
                "Brilliant Energy",
                "Dancing",
                "Defending",
                "Disruption",
                "Distance",
                "Flaming",
                "Flaming Burst",
                "Frost",
                "Holy",
                "Icy Burst",
                "Keen",
                "Merciful",
                "Mighty Cleaving",
                "Returning",
                "Seeking",
                "Shock",
                "Shocking Burst",
                "Speed",
                "Spell Storing",
                "Throwing",
                "Thundering",
                "Unholy",
                "Vicious",
                "Vorpal",
                "Wounding",
            )
            if registry.get(n) is None
        ]
        assert missing == []
