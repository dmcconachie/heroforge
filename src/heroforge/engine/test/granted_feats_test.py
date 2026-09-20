"""
Feats granted by a class feature or a magic item.

A Swashbuckler gets Weapon Finesse at 1st level and a wearer of
Gloves of the Balanced Hand fights as though they had Two-Weapon
Fighting. Both are real feats for every purpose that matters —
prerequisites, and per-weapon attack lines — so they belong in
the character's feat list rather than only in prose.

They are derived, not chosen: recomputed on load from the class
levels and worn items, never written to the character file.
"""

from __future__ import annotations

from pathlib import Path

from heroforge.engine.character import Character, CharacterLevel
from heroforge.engine.persistence import load_character, save_character
from heroforge.engine.sheet import gather_sheet


def swashbuckler(levels: int = 3) -> Character:
    c = Character()
    c.name = "Granted"
    c.race = "Human"
    c.alignment = "neutral"
    c.set_class_levels(
        [
            CharacterLevel(
                character_level=i + 1,
                class_name="Swashbuckler",
                hp_roll=10,
            )
            for i in range(levels)
        ]
    )
    return c


def _round_trip(c: Character, tmp_path: Path) -> Character:
    path = tmp_path / "granted.char.yaml"
    save_character(c, path)
    return load_character(path, None)


class TestClassGrantedFeats:
    def test_swashbuckler_gains_weapon_finesse(self, tmp_path: Path) -> None:
        loaded = _round_trip(swashbuckler(), tmp_path)
        assert loaded.has_feat("Weapon Finesse")
        assert "Weapon Finesse" in gather_sheet(loaded, None).feats

    def test_not_written_to_the_character_file(self, tmp_path: Path) -> None:
        path = tmp_path / "granted.char.yaml"
        save_character(swashbuckler(), path)
        assert "Weapon Finesse" not in path.read_text()

    def test_absent_before_the_granting_level(self, tmp_path: Path) -> None:
        c = Character()
        c.race = "Human"
        c.alignment = "neutral"
        c.set_class_levels(
            [
                CharacterLevel(
                    character_level=1, class_name="Fighter", hp_roll=10
                )
            ]
        )
        assert not _round_trip(c, tmp_path).has_feat("Weapon Finesse")

    def test_granted_feat_survives_reload(self, tmp_path: Path) -> None:
        """Derived means recomputed, so it must not accumulate."""
        once = _round_trip(swashbuckler(), tmp_path)
        twice = _round_trip(once, tmp_path)
        names = [f["name"] for f in twice.feats]
        assert names.count("Weapon Finesse") == 1


class TestItemGrantedFeats:
    def test_gloves_grant_two_weapon_fighting(self, tmp_path: Path) -> None:
        c = swashbuckler()
        c.equipment["worn"] = [{"name": "Gloves of the Balanced Hand"}]
        loaded = _round_trip(c, tmp_path)
        assert loaded.has_feat("Two-Weapon Fighting")

    def test_no_item_no_grant(self, tmp_path: Path) -> None:
        loaded = _round_trip(swashbuckler(), tmp_path)
        assert not loaded.has_feat("Two-Weapon Fighting")
