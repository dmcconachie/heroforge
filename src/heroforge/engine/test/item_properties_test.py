"""
Armour, shield and weapon special properties.

Only properties that apply permanently are wired to stats.
Anything activated (blinking, 1/day), reactive (arrow
deflection) or conditional on the target (bane, wounding)
stays display-only, because a number on the sheet would be
wrong most of the time.

Names are the book's own, one canonical spelling each.
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


class TestCanonicalNames:
    def test_only_the_book_spelling_resolves(self) -> None:
        assert property_definition("Shadow, Greater") is not None
        for wrong in (
            "greater shadow",
            "shadow, greater",
            "Greater Shadow",
            "truedeath (greater)",
        ):
            assert property_definition(wrong) is None, wrong

    def test_crystals_use_their_full_names(self) -> None:
        for name in (
            "Truedeath Crystal, Least",
            "Truedeath Crystal, Lesser",
            "Truedeath Crystal, Greater",
            "Fiendslayer Crystal, Least",
            "Revelation Crystal, Greater",
            "Crystal of Mind Cloaking, Greater",
        ):
            assert property_definition(name) is not None, name

    def test_bane_takes_its_foe_as_a_parameter(self) -> None:
        """
        Bane is the one property with an open argument: its
        designated foe is any creature type or subtype, so
        "Bane Undead" resolves and carries "Undead".
        """
        registry = get_rules().item_properties
        defn = registry.get("Bane Undead")
        assert defn is not None
        assert defn.name == "Bane"
        assert registry.parameter_of("Bane Undead") == "Undead"
        assert registry.parameter_of("Shadow, Greater") == ""

    def test_an_unknown_property_is_none(self) -> None:
        assert property_definition("not a real property") is None

    def test_definitions_declare_what_they_apply_to(self) -> None:
        defn = property_definition("Shadow, Greater")
        assert isinstance(defn, ItemPropertyDefinition)
        assert defn.applies_to == "armor"


class TestPermanentArmourProperties:
    """DMG p. 219; the armour check penalty still applies."""

    @pytest.mark.parametrize(
        ("prop", "bonus"),
        [
            ("Shadow", 5),
            ("Shadow, Improved", 10),
            ("Shadow, Greater", 15),
        ],
    )
    def test_shadow_family_bonuses_hide(self, prop: str, bonus: int) -> None:
        plain = _skill(_wear(_char()), "Hide")
        assert _skill(_wear(_char(), prop), "Hide") == plain + bonus

    @pytest.mark.parametrize(
        ("prop", "bonus"),
        [
            ("Silent Moves", 5),
            ("Silent Moves, Improved", 10),
            ("Silent Moves, Greater", 15),
        ],
    )
    def test_silent_moves_family(self, prop: str, bonus: int) -> None:
        plain = _skill(_wear(_char()), "Move Silently")
        assert _skill(_wear(_char(), prop), "Move Silently") == (plain + bonus)

    @pytest.mark.parametrize(
        ("prop", "bonus"),
        [("Slick", 5), ("Slick, Improved", 10), ("Slick, Greater", 15)],
    )
    def test_slick_family_bonuses_escape_artist(
        self, prop: str, bonus: int
    ) -> None:
        plain = _skill(_wear(_char()), "Escape Artist")
        assert _skill(_wear(_char(), prop), "Escape Artist") == (plain + bonus)

    def test_blueshine_bonuses_hide(self) -> None:
        plain = _skill(_wear(_char()), "Hide")
        assert _skill(_wear(_char(), "Blueshine"), "Hide") == plain + 2

    def test_they_do_not_stack_with_each_other(self) -> None:
        """Both are competence bonuses, so only the best counts."""
        plain = _skill(_wear(_char()), "Hide")
        both = _wear(_char(), "Shadow, Greater", "Blueshine")
        assert _skill(both, "Hide") == plain + 15

    def test_removing_the_armour_removes_the_bonus(self) -> None:
        bare = _skill(_char(), "Hide")
        c = _wear(_char(), "Shadow, Greater")
        assert _skill(c, "Hide") > bare
        unequip_armor(c)
        assert _skill(c, "Hide") == bare

    @pytest.mark.parametrize("sr", [13, 15, 17, 19])
    def test_spell_resistance_grades(self, sr: int) -> None:
        c = _wear(_char(), f"Spell Resistance ({sr})")
        assert c.get("sr") == sr

    def test_spell_resistance_does_not_stack(self) -> None:
        c = _wear(_char(), "Spell Resistance (13)", "Spell Resistance (19)")
        assert c.get("sr") == 19


class TestActivatedPropertiesAreNotWired:
    @pytest.mark.parametrize(
        "prop",
        [
            "Blinking",
            "Vanishing",
            "Mindarmor",
            "Animated",
            "Arrow Deflection",
            "Crystal of Mind Cloaking, Greater",
        ],
    )
    def test_no_stat_change(self, prop: str) -> None:
        assert property_definition(prop) is not None
        plain = _skill(_wear(_char()), "Hide")
        assert _skill(_wear(_char(), prop), "Hide") == plain

    def test_they_still_show_on_the_sheet(self) -> None:
        c = _wear(_char(), "Blinking")
        assert "Blinking" in gather_sheet(c, None).equipment.armor.properties

    @pytest.mark.parametrize(
        "prop",
        ["Fire Resistance", "Invulnerability", "Fortification, Light"],
    )
    def test_permanent_but_unmodelled_are_inert_for_skills(
        self, prop: str
    ) -> None:
        defn = property_definition(prop)
        assert defn is not None
        plain = _skill(_wear(_char()), "Hide")
        assert _skill(_wear(_char(), prop), "Hide") == plain


class TestSpeedWeapon:
    """
    DMG p. 226: one extra attack at full base attack bonus
    when making a full attack."""

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
        w = gather_sheet(self._armed("Speed"), None).equipment.weapons[0]
        assert len(w.attack_iteratives) == 3
        assert w.attack_iteratives[0] == w.attack_iteratives[1]

    def test_speed_is_not_a_bonus_on_the_line(self) -> None:
        plain = gather_sheet(self._armed(), None).equipment.weapons[0]
        fast = gather_sheet(self._armed("Speed"), None).equipment.weapons[0]
        assert fast.attack.total == plain.attack.total


class TestDistance:
    """DMG p. 224: double the range increment."""

    def _inc(self, *props: str) -> int:
        c = _char()
        c.equipment["weapons"] = [
            {"base": "Longbow", "properties": list(props)}
        ]
        register_weapons_on_character(c)
        return gather_sheet(c, None).equipment.weapons[0].range_inc

    def test_plain_longbow(self) -> None:
        assert self._inc() == 100

    def test_distance_doubles_it(self) -> None:
        assert self._inc("Distance") == 200


class TestSrdCoverage:
    def test_every_srd_ability_is_defined(self) -> None:
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

    def test_every_property_a_fixture_names_resolves(self) -> None:
        """
        With both SRD lists and the MIC entries in place, a
        property no definition recognises is a data error.

        The two exemptions are miscategorised fixture data,
        not properties: Starmetal is a *material* and belongs
        in `material:`, and `weapon bond` is the occult
        slayer's class feature.
        """
        import glob

        import yaml

        exempt = {"Starmetal", "weapon bond"}
        registry = get_rules().item_properties
        unresolved: set[str] = set()
        for path in glob.glob("tests/integration/*/*.char.yaml"):
            data = yaml.safe_load(Path(path).read_text()) or {}
            eq = data.get("equipment") or {}
            names = []
            for slot in ("armor", "shield"):
                names += (eq.get(slot) or {}).get("properties", []) or []
            for w in eq.get("weapons") or []:
                names += w.get("properties", []) or []
            unresolved |= {
                n for n in names if n not in exempt and registry.get(n) is None
            }
        assert unresolved == set()


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
      - Shadow, Greater
  weapons:
    - base: Longsword
      properties:
        - Speed
"""

    def test_properties_survive_a_load(self, tmp_path: Path) -> None:
        path = tmp_path / "s.char.yaml"
        path.write_text(self.CHAR)
        c = load_character(path, None)
        sheet = gather_sheet(c, None)
        assert sheet.skills["Hide"].typed["competence"] == 15
        assert len(sheet.equipment.weapons[0].attack_iteratives) == 2
