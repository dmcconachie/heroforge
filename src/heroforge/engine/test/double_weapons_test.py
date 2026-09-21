"""
The six SRD double weapons.

Two of them are asymmetric: the gnome hooked hammer's ends
differ in damage die, critical multiplier *and* damage type,
and the dwarven urgrosh's differ in die and type. So a double
weapon's far end needs its own stats, not just its own
Strength share.
"""

from __future__ import annotations

import pytest

from heroforge.engine.character import Character, CharacterLevel
from heroforge.engine.enums import Ability, Size
from heroforge.engine.sheet import gather_sheet
from heroforge.engine.weapons import register_weapons_on_character
from heroforge.rules.rules import get_rules

DOUBLES = (
    "Quarterstaff",
    "Dire Flail",
    "Dwarven Urgrosh",
    "Gnome Hooked Hammer",
    "Orc Double Axe",
    "Two-Bladed Sword",
)


def _wielder(*weapons: dict) -> Character:
    c = Character(name="Twirler")
    for ab in Ability:
        c.set_ability_score(ab, 10)
    c.levels = [
        CharacterLevel(character_level=i + 1, class_name="Fighter", hp_roll=10)
        for i in range(6)
    ]
    c._invalidate_class_stats()
    c.equipment["weapons"] = [dict(w) for w in weapons]
    register_weapons_on_character(c)
    return c


class TestAllSixExist:
    @pytest.mark.parametrize("name", DOUBLES)
    def test_it_is_in_the_data(self, name: str) -> None:
        assert get_rules().weapons.get(name) is not None, name

    @pytest.mark.parametrize("name", DOUBLES)
    def test_it_is_marked_double(self, name: str) -> None:
        defn = get_rules().weapons.get(name)
        assert defn is not None, name
        assert defn.double, name

    @pytest.mark.parametrize("name", DOUBLES)
    def test_it_is_two_handed(self, name: str) -> None:
        defn = get_rules().weapons.get(name)
        assert defn is not None, name
        assert defn.wield_class == "two_handed"


class TestSymmetricEnds:
    """
    Four of the six have matching ends, so the far end needs
    no separate description.
    """

    @pytest.mark.parametrize(
        ("name", "dice", "mult"),
        [
            ("Quarterstaff", "1d6", 2),
            ("Dire Flail", "1d8", 2),
            ("Orc Double Axe", "1d8", 3),
            ("Two-Bladed Sword", "1d8", 2),
        ],
    )
    def test_both_ends_read_alike(
        self, name: str, dice: str, mult: int
    ) -> None:
        c = _wielder(
            {"base": name, "stances": ["primary"]},
            {"base": name, "stances": ["off_hand"]},
        )
        primary, off = gather_sheet(c).equipment.weapons
        assert primary.damage_dice == dice
        assert off.damage_dice == dice
        assert primary.crit_mult == f"x{mult}"
        assert off.crit_mult == f"x{mult}"

    def test_the_two_bladed_sword_keeps_its_threat_range(self) -> None:
        c = _wielder({"base": "Two-Bladed Sword", "stances": ["off_hand"]})
        assert gather_sheet(c).equipment.weapons[0].crit_range == ("19-20")


class TestTheGnomeHookedHammer:
    """
    PHB p. 118: "The hammer's blunt head is a bludgeoning
    weapon ... Its hook is a piercing weapon ... (crit x4)."
    Table 7-5 gives it as 1d8/1d6, crit x3/x4.
    """

    def _both(self) -> tuple:
        c = _wielder(
            {"base": "Gnome Hooked Hammer", "stances": ["primary"]},
            {"base": "Gnome Hooked Hammer", "stances": ["off_hand"]},
        )
        return tuple(gather_sheet(c).equipment.weapons)

    def test_the_hammer_head(self) -> None:
        primary, _ = self._both()
        assert primary.damage_dice == "1d8"
        assert primary.crit_mult == "x3"

    def test_the_hook(self) -> None:
        _, off = self._both()
        assert off.damage_dice == "1d6"
        assert off.crit_mult == "x4"

    def test_a_small_hammer_uses_the_small_column(self) -> None:
        """Table 7-5 Dmg (S) is 1d6/1d4."""
        c = _wielder(
            {"base": "Gnome Hooked Hammer", "stances": ["primary"]},
            {"base": "Gnome Hooked Hammer", "stances": ["off_hand"]},
        )
        c._race_size = Size.SMALL
        register_weapons_on_character(c)
        primary, off = gather_sheet(c).equipment.weapons
        assert primary.damage_dice == "1d6"
        assert off.damage_dice == "1d4"


class TestTheDwarvenUrgrosh:
    """
    PHB p. 120: "The urgrosh's axe head is a slashing weapon
    that deals 1d8 ... Its spear head is a piercing weapon
    that deals 1d6." Both ends crit x3.
    """

    def _both(self) -> tuple:
        c = _wielder(
            {"base": "Dwarven Urgrosh", "stances": ["primary"]},
            {"base": "Dwarven Urgrosh", "stances": ["off_hand"]},
        )
        return tuple(gather_sheet(c).equipment.weapons)

    def test_the_axe_head(self) -> None:
        primary, _ = self._both()
        assert primary.damage_dice == "1d8"
        assert primary.crit_mult == "x3"

    def test_the_spear_head(self) -> None:
        _, off = self._both()
        assert off.damage_dice == "1d6"
        assert off.crit_mult == "x3"


class TestTheWholeSrdTable:
    def test_every_srd_weapon_is_present(self) -> None:
        reg = get_rules().weapons
        missing = [
            n
            for n in (
                # Simple
                "Gauntlet",
                "Unarmed Strike",
                "Dagger",
                "Punching Dagger",
                "Spiked Gauntlet",
                "Light Mace",
                "Sickle",
                "Club",
                "Heavy Mace",
                "Morningstar",
                "Shortspear",
                "Longspear",
                "Quarterstaff",
                "Spear",
                "Heavy Crossbow",
                "Light Crossbow",
                "Dart",
                "Javelin",
                "Sling",
                # Martial
                "Throwing Axe",
                "Light Hammer",
                "Handaxe",
                "Kukri",
                "Light Pick",
                "Sap",
                "Short Sword",
                "Battleaxe",
                "Flail",
                "Longsword",
                "Heavy Pick",
                "Rapier",
                "Scimitar",
                "Trident",
                "Warhammer",
                "Falchion",
                "Glaive",
                "Greataxe",
                "Greatclub",
                "Heavy Flail",
                "Greatsword",
                "Guisarme",
                "Halberd",
                "Lance",
                "Ranseur",
                "Scythe",
                "Longbow",
                "Composite Longbow",
                "Shortbow",
                "Composite Shortbow",
                # Exotic
                "Kama",
                "Nunchaku",
                "Sai",
                "Siangham",
                "Bastard Sword",
                "Dwarven Waraxe",
                "Whip",
                "Orc Double Axe",
                "Spiked Chain",
                "Dire Flail",
                "Gnome Hooked Hammer",
                "Two-Bladed Sword",
                "Dwarven Urgrosh",
                "Hand Crossbow",
                "Repeating Heavy Crossbow",
                "Repeating Light Crossbow",
                "Net",
                "Shuriken",
                "Bolas",
            )
            if reg.get(n) is None
        ]
        assert missing == []
