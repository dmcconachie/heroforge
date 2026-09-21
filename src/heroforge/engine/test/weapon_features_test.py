"""
Class features that designate a weapon.

The occult slayer bonds one masterwork weapon. That is not an
item property -- the weapon has not been enchanted, the
character has picked it -- so it is declared on the class
feature and designated from the weapon slot, where "which
one" is unambiguous even between two identical daggers.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from heroforge.engine.character import Character, CharacterLevel
from heroforge.engine.enums import Ability
from heroforge.engine.persistence import load_character
from heroforge.engine.sheet import gather_sheet
from heroforge.engine.weapons import (
    register_weapons_on_character,
    weapon_feature_names,
)
from heroforge.rules.rules import get_rules


def _slayer(*weapons: dict) -> Character:
    c = Character(name="Hunter")
    for ab in Ability:
        c.set_ability_score(ab, 12)
    c.levels = [
        CharacterLevel(character_level=i + 1, class_name="Rogue", hp_roll=6)
        for i in range(5)
    ] + [
        CharacterLevel(
            character_level=6 + i, class_name="Occult Slayer", hp_roll=8
        )
        for i in range(3)
    ]
    c._invalidate_class_stats()
    c.equipment["weapons"] = [dict(w) for w in weapons]
    register_weapons_on_character(c)
    return c


class TestTheFeatureDeclaresIt:
    def test_weapon_bond_designates_a_weapon(self) -> None:
        defn = get_rules().classes.require("Occult Slayer")
        feature = next(
            f for f in defn.class_features if f.feature == "weapon_bond"
        )
        assert feature.designates == "weapon"

    def test_an_ordinary_feature_designates_nothing(self) -> None:
        defn = get_rules().classes.require("Occult Slayer")
        feature = next(
            f for f in defn.class_features if f.feature == "auravision"
        )
        assert feature.designates == ""


class TestItShowsOnTheWeapon:
    def test_it_reaches_the_properties_list(self) -> None:
        c = _slayer(
            {"base": "Dagger", "features": ["weapon_bond"]},
            {"base": "Dagger"},
        )
        weapons = gather_sheet(c).equipment.weapons
        assert "Weapon Bond" in weapons[0].properties
        assert "Weapon Bond" not in weapons[1].properties

    def test_it_sits_with_the_item_properties(self) -> None:
        c = _slayer(
            {
                "base": "Dagger",
                "properties": ["Sacred"],
                "features": ["weapon_bond"],
            }
        )
        props = gather_sheet(c).equipment.weapons[0].properties
        assert props == ["Sacred", "Weapon Bond"]

    def test_a_weapon_with_no_features_is_unchanged(self) -> None:
        c = _slayer({"base": "Dagger", "properties": ["Sacred"]})
        props = gather_sheet(c).equipment.weapons[0].properties
        assert props == ["Sacred"]

    def test_the_helper_lists_them(self) -> None:
        item = {"base": "Dagger", "features": ["weapon_bond"]}
        assert weapon_feature_names(item) == ["Weapon Bond"]


class TestValidation:
    def _load(self, tmp_path: Path, body: str) -> Character:
        path = tmp_path / "s.char.yaml"
        path.write_text(body)
        return load_character(path)

    HEAD = """
identity:
  name: Hunter
  race: Human
  alignment: neutral
ability_scores: {str: 12, dex: 12, con: 12, int: 12, wis: 12, cha: 12}
levels:
"""

    def _levels(self, occult: bool) -> str:
        out = "".join(
            f"  - {{level: {i}, class: Rogue, hp_roll: 6}}\n"
            for i in range(1, 6)
        )
        if occult:
            out += "".join(
                f"  - {{level: {i}, class: Occult Slayer, hp_roll: 8}}\n"
                for i in range(6, 9)
            )
        return out

    def test_it_round_trips(self, tmp_path: Path) -> None:
        body = (
            self.HEAD
            + self._levels(True)
            + """equipment:
  weapons:
    - base: Dagger
      features:
        - weapon_bond
"""
        )
        c = self._load(tmp_path, body)
        sheet = gather_sheet(c)
        assert "Weapon Bond" in sheet.equipment.weapons[0].properties

    def test_a_feature_the_character_lacks_is_refused(
        self, tmp_path: Path
    ) -> None:
        """
        A rogue with no occult slayer levels has no weapon to
        bond with, so naming the feature is a data error
        rather than something to ignore.
        """
        body = (
            self.HEAD
            + self._levels(False)
            + """equipment:
  weapons:
    - base: Dagger
      features:
        - weapon_bond
"""
        )
        with pytest.raises(Exception, match="weapon_bond"):
            self._load(tmp_path, body)

    def test_an_unknown_feature_is_refused(self, tmp_path: Path) -> None:
        body = (
            self.HEAD
            + self._levels(True)
            + """equipment:
  weapons:
    - base: Dagger
      features:
        - not_a_feature
"""
        )
        with pytest.raises(Exception, match="not_a_feature"):
            self._load(tmp_path, body)

    def test_a_feature_that_designates_nothing_is_refused(
        self, tmp_path: Path
    ) -> None:
        body = (
            self.HEAD
            + self._levels(True)
            + """equipment:
  weapons:
    - base: Dagger
      features:
        - auravision
"""
        )
        with pytest.raises(Exception, match="auravision"):
            self._load(tmp_path, body)
