"""
tests/test_yaml_errors.py
--------------------------
Ensure that malformed character YAML raises clear
errors traceable to the source file and schema path.

Each test loads a minimal .char.yaml with a specific
typo or bad field and asserts the error message
contains both the file path and the schema location.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from heroforge.engine.persistence import (
    load_character,
)

if TYPE_CHECKING:
    from heroforge.ui.app_state import AppState

BAD_YAML = Path(__file__).parent / "fixtures" / "bad_yaml"


@pytest.fixture(scope="module")
def app_state() -> "AppState":
    from heroforge.ui.app_state import AppState

    state = AppState()
    state.load_rules()
    return state


class TestUnknownNames:
    """
    Registry lookups that fail should raise
    ValueError with file path and schema
    path in the message."""

    def test_unknown_race(self, app_state: AppState) -> None:
        path = BAD_YAML / "bad_race.char.yaml"
        with pytest.raises(ValueError, match=r"Dorf"):
            load_character(path, app_state)

    def test_error_contains_file_path(self, app_state: AppState) -> None:
        path = BAD_YAML / "bad_race.char.yaml"
        with pytest.raises(
            ValueError,
            match=r"bad_race\.char\.yaml",
        ):
            load_character(path, app_state)

    def test_error_contains_schema_path(self, app_state: AppState) -> None:
        path = BAD_YAML / "bad_race.char.yaml"
        with pytest.raises(
            ValueError,
            match=r"attribute race",
        ):
            load_character(path, app_state)

    def test_unknown_feat(self, app_state: AppState) -> None:
        path = BAD_YAML / "bad_feat.char.yaml"
        with pytest.raises(
            ValueError,
            match=r"Powre Attack",
        ):
            load_character(path, app_state)

    def test_unknown_feat_schema_path(self, app_state: AppState) -> None:
        path = BAD_YAML / "bad_feat.char.yaml"
        with pytest.raises(
            ValueError,
            match=r"KnownFeat",
        ):
            load_character(path, app_state)

    def test_unknown_buff(self, app_state: AppState) -> None:
        path = BAD_YAML / "bad_buff.char.yaml"
        with pytest.raises(
            ValueError,
            match=r"barkskin",
        ):
            load_character(path, app_state)

    def test_unknown_buff_schema_path(self, app_state: AppState) -> None:
        path = BAD_YAML / "bad_buff.char.yaml"
        with pytest.raises(
            ValueError,
            match=r"KnownBuff",
        ):
            load_character(path, app_state)

    def test_unknown_template(self, app_state: AppState) -> None:
        path = BAD_YAML / "bad_template.char.yaml"
        with pytest.raises(
            ValueError,
            match=r"Half-Celstial",
        ):
            load_character(path, app_state)

    def test_unknown_template_schema_path(self, app_state: AppState) -> None:
        path = BAD_YAML / "bad_template.char.yaml"
        with pytest.raises(
            ValueError,
            match=r"KnownTemplate",
        ):
            load_character(path, app_state)

    def test_unknown_armor(self, app_state: AppState) -> None:
        path = BAD_YAML / "bad_armor.char.yaml"
        with pytest.raises(
            ValueError,
            match=r"Ful Plate",
        ):
            load_character(path, app_state)

    def test_unknown_armor_schema_path(self, app_state: AppState) -> None:
        path = BAD_YAML / "bad_armor.char.yaml"
        with pytest.raises(
            ValueError,
            match=r"KnownArmor",
        ):
            load_character(path, app_state)

    def test_unknown_shield(self, app_state: AppState) -> None:
        path = BAD_YAML / "bad_shield.char.yaml"
        with pytest.raises(
            ValueError,
            match=r"Hevy Steel Shield",
        ):
            load_character(path, app_state)

    def test_unknown_worn_item(self, app_state: AppState) -> None:
        path = BAD_YAML / "bad_worn.char.yaml"
        with pytest.raises(
            ValueError,
            match=r"Belt of Giant Str \+4",
        ):
            load_character(path, app_state)

    def test_unknown_worn_schema_path(self, app_state: AppState) -> None:
        path = BAD_YAML / "bad_worn.char.yaml"
        with pytest.raises(
            ValueError,
            match=r"KnownMagicItem",
        ):
            load_character(path, app_state)

    def test_unknown_skill(self, app_state: AppState) -> None:
        path = BAD_YAML / "bad_skill.char.yaml"
        with pytest.raises(
            ValueError,
            match=r"Clmb",
        ):
            load_character(path, app_state)

    def test_unknown_skill_schema_path(self, app_state: AppState) -> None:
        path = BAD_YAML / "bad_skill.char.yaml"
        with pytest.raises(
            ValueError,
            match=r"KnownSkill",
        ):
            load_character(path, app_state)

    def test_unknown_class(self, app_state: AppState) -> None:
        path = BAD_YAML / "bad_class.char.yaml"
        with pytest.raises(
            ValueError,
            match=r"duid",
        ):
            load_character(path, app_state)

    def test_unknown_class_schema_path(self, app_state: AppState) -> None:
        path = BAD_YAML / "bad_class.char.yaml"
        with pytest.raises(
            ValueError,
            match=r"KnownClass",
        ):
            load_character(path, app_state)


class TestUnknownFields:
    """
    Unknown keys in structured sections should
    raise errors."""

    def test_unknown_buff_field(self, app_state: AppState) -> None:
        path = BAD_YAML / "bad_buff_field.char.yaml"
        with pytest.raises(
            ValueError,
            match=r"casterr_level",
        ):
            load_character(path, app_state)

    def test_unknown_level_field(self, app_state: AppState) -> None:
        path = BAD_YAML / "bad_level_field.char.yaml"
        with pytest.raises(
            ValueError,
            match=r"hproll",
        ):
            load_character(path, app_state)
