"""
Tests for weapon, armor and shield proficiency (PHB pp. 113,
122) and the penalties nonproficiency carries.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from cattrs.errors import ClassValidationError

from heroforge.engine.character import Character, CharacterLevel
from heroforge.engine.classes import Proficiencies
from heroforge.engine.enums import ArmorCategory, WeaponCategory
from heroforge.engine.equipment import (
    ArmorDefinition,
    WeaponDefinition,
    equip_armor,
    equip_shield,
)
from heroforge.engine.feats import refresh_granted_feats
from heroforge.engine.persistence import load_character
from heroforge.engine.proficiency import (
    is_proficient_with_armor,
    is_proficient_with_shield,
    is_proficient_with_weapon,
)
from heroforge.engine.races import apply_race
from heroforge.engine.sheet import gather_sheet
from heroforge.engine.skills import (
    compute_skill_total,
    register_skills_on_character,
)
from heroforge.engine.weapons import register_weapons_on_character
from heroforge.rules.rules import get_rules
from heroforge.rules.schema import converter


def _char(class_name: str, race: str = "Human") -> Character:
    c = Character(name="Test")
    register_skills_on_character(c)
    for ab in ("str", "dex", "con", "int", "wis", "cha"):
        c.set_ability_score(ab, 12)
    c.levels = [
        CharacterLevel(character_level=1, class_name=class_name, hp_roll=8)
    ]
    c.race = race
    defn = get_rules().races.get(race)
    if defn is not None:
        apply_race(defn, c)
    c._invalidate_class_stats()
    return c


def _weapon(name: str) -> WeaponDefinition | None:
    return get_rules().weapons.get(name)


def _armor(name: str) -> ArmorDefinition | None:
    return get_rules().armor.get(name)


class TestClassProficiencyData:
    def test_every_base_class_declares_proficiencies(self) -> None:
        """
        A missing block would silently mean "proficient with
        nothing", which would quietly penalise every character
        of that class. Base classes must be explicit.
        """
        missing = [
            name
            for name in get_rules().classes.all_names()
            if not get_rules().classes.require(name).is_prestige
            and get_rules().classes.require(name).proficiencies is None
        ]
        assert missing == []

    def test_the_categories_are_enums(self) -> None:
        """
        Armour and weapon categories are closed sets, so a
        misspelling in a class entry must fail at load rather
        than silently granting nothing.
        """
        for name in get_rules().classes.all_names():
            prof = get_rules().classes.require(name).proficiencies
            if prof is None:
                continue
            for cat in prof.armor:
                assert isinstance(cat, ArmorCategory), name
            for cat in prof.weapons:
                assert isinstance(cat, WeaponCategory), name

    def test_a_misspelled_category_is_refused_at_load(self) -> None:
        with pytest.raises(ClassValidationError):
            converter.structure({"armor": ["lite"]}, Proficiencies)

    def test_fighter_has_everything(self) -> None:
        p = get_rules().classes.require("Fighter").proficiencies
        assert p is not None
        assert set(p.weapons) == {"simple", "martial"}
        assert set(p.armor) == {"light", "medium", "heavy"}
        assert p.shields and p.tower_shields

    def test_wizard_has_a_named_short_list(self) -> None:
        p = get_rules().classes.require("Wizard").proficiencies
        assert p is not None
        assert p.weapons == ()
        assert set(p.weapon_names) == {
            "Club",
            "Dagger",
            "Heavy Crossbow",
            "Light Crossbow",
            "Quarterstaff",
        }
        assert p.armor == ()
        assert not p.shields

    def test_barbarian_excludes_tower_shields(self) -> None:
        p = get_rules().classes.require("Barbarian").proficiencies
        assert p is not None
        assert p.shields
        assert not p.tower_shields


class TestWeaponProficiency:
    def test_fighter_is_proficient_with_a_martial_weapon(self) -> None:
        c = _char("Fighter")
        assert is_proficient_with_weapon(c, _weapon("Longsword"))

    def test_wizard_is_not(self) -> None:
        c = _char("Wizard")
        assert not is_proficient_with_weapon(c, _weapon("Longsword"))

    def test_wizard_is_proficient_with_a_named_weapon(self) -> None:
        c = _char("Wizard")
        assert is_proficient_with_weapon(c, _weapon("Quarterstaff"))

    def test_nobody_is_proficient_with_an_exotic_by_default(self) -> None:
        c = _char("Fighter")
        assert not is_proficient_with_weapon(c, _weapon("Spiked Chain"))

    def test_the_feat_grants_the_named_weapon(self) -> None:
        c = _char("Fighter")
        c.add_feat(
            "Exotic Weapon Proficiency",
            parameter="Spiked Chain",
            level=1,
            source="",
        )
        assert is_proficient_with_weapon(c, _weapon("Spiked Chain"))

    def test_the_feat_grants_only_the_named_weapon(self) -> None:
        c = _char("Fighter")
        c.add_feat(
            "Exotic Weapon Proficiency",
            parameter="Spiked Chain",
            level=1,
            source="",
        )
        assert not is_proficient_with_weapon(c, _weapon("Whip"))

    def test_elves_get_their_racial_weapons(self) -> None:
        """PHB p. 16: elves get the longsword as a bonus feat."""
        c = _char("Wizard", race="Elf")
        assert is_proficient_with_weapon(c, _weapon("Longsword"))

    def test_simple_weapon_proficiency_feat_covers_the_category(
        self,
    ) -> None:
        c = _char("Wizard")
        assert not is_proficient_with_weapon(c, _weapon("Sling"))
        c.add_feat("Simple Weapon Proficiency", level=1, source="")
        assert is_proficient_with_weapon(c, _weapon("Sling"))


class TestArmorAndShieldProficiency:
    def test_fighter_is_proficient_with_heavy_armor(self) -> None:
        assert is_proficient_with_armor(_char("Fighter"), _armor("Full Plate"))

    def test_rogue_is_not(self) -> None:
        assert not is_proficient_with_armor(
            _char("Rogue"), _armor("Full Plate")
        )

    def test_rogue_is_proficient_with_light_armor(self) -> None:
        assert is_proficient_with_armor(
            _char("Rogue"), _armor("Studded Leather")
        )

    def test_rogue_is_not_proficient_with_shields(self) -> None:
        assert not is_proficient_with_shield(
            _char("Rogue"), _armor("Heavy Steel Shield")
        )

    def test_barbarian_shield_but_not_tower(self) -> None:
        c = _char("Barbarian")
        assert is_proficient_with_shield(c, _armor("Heavy Steel Shield"))
        assert not is_proficient_with_shield(c, _armor("Tower Shield"))

    def test_the_feat_grants_heavy_armor(self) -> None:
        c = _char("Rogue")
        c.add_feat("Armor Proficiency (Light)", level=1, source="")
        c.add_feat("Armor Proficiency (Medium)", level=1, source="")
        c.add_feat("Armor Proficiency (Heavy)", level=1, source="")
        assert is_proficient_with_armor(c, _armor("Full Plate"))


class TestNonproficiencyPenalties:
    """
    PHB p. 122: a character wearing armor or using a shield
    they are not proficient with takes that piece's armor
    check penalty on attack rolls and on every STR- and
    DEX-based ability and skill check. The two stack.
    """

    def _in_full_plate(self, class_name: str) -> Character:
        c = _char(class_name)
        equip_armor(c, _armor("Full Plate"))
        return c

    def test_proficient_wearer_takes_no_attack_penalty(self) -> None:
        c = self._in_full_plate("Fighter")
        sheet = gather_sheet(c, None)
        assert "nonproficient_armor" not in sheet.combat.attack_melee.typed

    def test_nonproficient_wearer_takes_the_check_penalty(self) -> None:
        c = self._in_full_plate("Rogue")
        sheet = gather_sheet(c, None)
        # Full plate's armor check penalty is -6.
        assert sheet.combat.attack_melee.typed["nonproficient_armor"] == -6

    def test_penalty_reaches_a_dex_skill_that_has_no_acp(self) -> None:
        """
        Ride is DEX-based but carries no armor check penalty,
        so only nonproficiency can put the penalty there.
        """
        ride = get_rules().skills.get("Ride")
        assert ride is not None
        proficient = compute_skill_total(
            self._in_full_plate("Fighter"), ride
        ).total
        penalised = compute_skill_total(
            self._in_full_plate("Rogue"), ride
        ).total
        assert penalised == proficient - 6

    def test_penalty_skips_a_wis_skill(self) -> None:
        listen = get_rules().skills.get("Listen")
        assert listen is not None
        proficient = compute_skill_total(
            self._in_full_plate("Fighter"), listen
        ).total
        penalised = compute_skill_total(
            self._in_full_plate("Rogue"), listen
        ).total
        assert penalised == proficient

    def test_armor_and_shield_nonproficiency_stack(self) -> None:
        c = self._in_full_plate("Rogue")
        equip_shield(c, _armor("Heavy Steel Shield"))
        sheet = gather_sheet(c, None)
        typed = sheet.combat.attack_melee.typed
        # -6 from the plate, -2 from the shield.
        assert typed["nonproficient_armor"] == -6
        assert typed["nonproficient_shield"] == -2

    def test_nonproficient_weapon_costs_four(self) -> None:
        c = _char("Wizard")
        c.equipment["weapons"] = [{"base": "Longsword"}]
        register_weapons_on_character(c)
        sheet = gather_sheet(c, None)
        assert sheet.equipment.weapons[0].attack.typed["nonproficient"] == -4

    def test_proficient_weapon_has_no_such_entry(self) -> None:
        c = _char("Fighter")
        c.equipment["weapons"] = [{"base": "Longsword"}]
        register_weapons_on_character(c)
        sheet = gather_sheet(c, None)
        assert "nonproficient" not in sheet.equipment.weapons[0].attack.typed


class TestProficiencyPersists:
    CHAR = """
identity:
  name: Underdressed
  race: Human
  alignment: neutral
ability_scores: {str: 12, dex: 12, con: 12, int: 12, wis: 12, cha: 12}
levels:
  - level: 1
    class: Wizard
    hp_roll: 4
equipment:
  armor:
    base: Full Plate
  weapons:
    - base: Longsword
"""

    def test_penalties_appear_in_the_sheet_after_a_load(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "u.char.yaml"
        path.write_text(self.CHAR)
        sheet = gather_sheet(load_character(path, None), None)
        assert sheet.combat.attack_melee.typed["nonproficient_armor"] == -6
        assert sheet.equipment.weapons[0].attack.typed["nonproficient"] == -4


class TestNonproficiencyDoesNotDouble:
    """
    Rules Compendium p. 14: wearing armor you are not
    proficient with applies the armor check penalty to attack
    rolls and all STR- and DEX-based checks, which
    "effectively adds Open Lock, Ride, and Use Rope to the
    list of penalized skills". It extends the list — it does
    not apply the penalty a second time to a skill that
    already carries one.
    """

    def _plated(self, class_name: str) -> Character:
        c = _char(class_name)
        equip_armor(c, _armor("Full Plate"))
        return c

    def _total(self, class_name: str, skill: str) -> int:
        defn = get_rules().skills.get(skill)
        assert defn is not None
        return compute_skill_total(self._plated(class_name), defn).total

    def test_climb_is_penalised_once(self) -> None:
        assert self._total("Rogue", "Climb") == self._total("Fighter", "Climb")

    def test_swim_keeps_its_doubled_penalty_and_no_more(self) -> None:
        assert self._total("Rogue", "Swim") == self._total("Fighter", "Swim")

    def test_hide_is_penalised_once(self) -> None:
        assert self._total("Rogue", "Hide") == self._total("Fighter", "Hide")

    def test_the_three_skills_the_rule_adds_are_penalised(self) -> None:
        for skill in ("Open Lock", "Ride", "Use Rope"):
            assert self._total("Rogue", skill) == (
                self._total("Fighter", skill) - 6
            ), skill


class TestMonkUnarmedProficiency:
    def test_a_monk_is_proficient_with_her_own_fists(self) -> None:
        """
        Regression: the PHB's monk weapon list omits the
        unarmed strike, because it is a simple weapon covered
        by the class's own unarmed strike feature. Taking that
        list literally left a monk nonproficient with her
        fists, costing -4 on every unarmed attack.
        """
        assert is_proficient_with_weapon(
            _char("Monk"), _weapon("Unarmed Strike")
        )

    def test_she_gets_improved_unarmed_strike(self) -> None:
        """PHB p. 41: a bonus feat at 1st level."""
        c = _char("Monk")

        refresh_granted_feats(c)
        assert c.has_feat("Improved Unarmed Strike")


class TestRacialWeaponFamiliarity:
    """
    PHB p. 15/17: dwarves may treat dwarven waraxes and
    dwarven urgroshes as martial weapons rather than exotic,
    and gnomes may treat gnome hooked hammers likewise.

    Familiarity only reclassifies. A character still needs
    martial proficiency to use the weapon, which is why these
    are tested against a fighter and not a wizard.
    """

    @pytest.mark.parametrize(
        ("race", "weapon"),
        [
            ("Dwarf", "Dwarven Waraxe"),
            ("Dwarf", "Dwarven Urgrosh"),
            ("Gnome", "Gnome Hooked Hammer"),
        ],
    )
    def test_the_race_may_treat_it_as_martial(
        self, race: str, weapon: str
    ) -> None:
        assert is_proficient_with_weapon(
            _char("Fighter", race=race), _weapon(weapon)
        )

    @pytest.mark.parametrize(
        "weapon",
        ["Dwarven Waraxe", "Dwarven Urgrosh", "Gnome Hooked Hammer"],
    )
    def test_everyone_else_still_needs_the_exotic_feat(
        self, weapon: str
    ) -> None:
        c = _char("Fighter", race="Human")
        assert not is_proficient_with_weapon(c, _weapon(weapon))
        c.add_feat(
            "Exotic Weapon Proficiency",
            parameter=weapon,
            level=1,
            source="",
        )
        assert is_proficient_with_weapon(c, _weapon(weapon))

    def test_a_gnome_is_not_familiar_with_dwarven_weapons(self) -> None:
        assert not is_proficient_with_weapon(
            _char("Fighter", race="Gnome"), _weapon("Dwarven Urgrosh")
        )

    def test_familiarity_alone_is_not_proficiency(self) -> None:
        """
        A gnome wizard has no martial proficiency, so treating
        the hammer as martial gains nothing.
        """
        assert not is_proficient_with_weapon(
            _char("Wizard", race="Gnome"), _weapon("Gnome Hooked Hammer")
        )

    def test_no_race_names_a_weapon_that_does_not_exist(self) -> None:
        """
        Regression: the dwarven urgrosh was named in the dwarf's
        familiarity list for as long as it was absent from the
        weapon table, so the entry silently did nothing.
        """
        rules = get_rules()
        dangling = {
            (race, name)
            for race in rules.races.all_names()
            for name in rules.races.get(race).weapon_familiarity
            if rules.weapons.get(name) is None
        }
        assert dangling == set()

    def test_no_race_grants_a_weapon_that_does_not_exist(self) -> None:
        rules = get_rules()
        dangling = {
            (race, name)
            for race in rules.races.all_names()
            for name in rules.races.get(race).weapon_proficiencies
            if rules.weapons.get(name) is None
        }
        assert dangling == set()
