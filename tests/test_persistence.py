"""
tests/test_persistence.py
--------------------------
Tests for heroforge/engine/persistence.py — save/load round-trips.

Covers:
  - save_character writes valid YAML
  - load_character restores identity, ability scores, class levels
  - Feats round-trip (always-on effects re-applied, conditional registered)
  - Skills round-trip
  - Active buffs round-trip (CL, parameter)
  - Inactive buff states preserved
  - Templates round-trip
  - DM overrides round-trip
  - Unknown race/class/buff/template load gracefully without crashing
  - Full character round-trip: saved stats == loaded stats
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from heroforge.engine.character import Character
    from heroforge.ui.app_state import AppState

from heroforge.engine.classes_races import apply_race
from heroforge.engine.effects import (
    apply_buff,
)
from heroforge.engine.persistence import (
    load_character,
    save_character,
)
from heroforge.engine.skills import set_skill_ranks

RULES_DIR = Path(__file__).parent.parent / "src" / "heroforge" / "rules"


# ===========================================================================
# Helpers
# ===========================================================================


def make_app_state() -> AppState:
    from heroforge.ui.app_state import AppState

    state = AppState()
    state.load_rules()
    state.new_character()
    return state


def fighter_char(app_state: AppState) -> Character:
    """A fully built Fighter 6 for round-trip tests."""
    from heroforge.engine.character import (
        CharacterLevel,
    )

    c = app_state.character
    c.name = "Aldric Vane"
    c.player = "Test Player"
    c.alignment = "lawful_good"
    c.deity = "St. Cuthbert"

    c.set_ability_score("str", 16)
    c.set_ability_score("dex", 14)
    c.set_ability_score("con", 14)
    c.set_ability_score("int", 10)
    c.set_ability_score("wis", 10)
    c.set_ability_score("cha", 8)

    apply_race(app_state.race_registry.require("Human"), c)

    # Build levels with per-level skill ranks
    c.levels = [
        CharacterLevel(
            character_level=1,
            class_name="Fighter",
            hp_roll=10,
            skill_ranks={"Climb": 4, "Swim": 4},
        ),
        CharacterLevel(
            character_level=2,
            class_name="Fighter",
            hp_roll=8,
            skill_ranks={"Climb": 1, "Swim": 1},
        ),
        CharacterLevel(
            character_level=3,
            class_name="Fighter",
            hp_roll=8,
        ),
        CharacterLevel(
            character_level=4,
            class_name="Fighter",
            hp_roll=8,
        ),
        CharacterLevel(
            character_level=5,
            class_name="Fighter",
            hp_roll=8,
        ),
        CharacterLevel(
            character_level=6,
            class_name="Fighter",
            hp_roll=8,
        ),
    ]
    c._invalidate_class_stats()

    # Set skill totals from level entries
    set_skill_ranks(c, "Climb", 5)
    set_skill_ranks(c, "Swim", 5)

    # Add a feat
    iw = app_state.feat_registry.require("Iron Will")
    c.add_feat("Iron Will", iw, level=1, source="character")

    # Activate Bless (CL 5)
    bless = app_state.buff_registry.require("Bless")
    apply_buff(bless, c, caster_level=5)

    return c


# ===========================================================================
# save_character
# ===========================================================================


class TestSaveCharacter:
    def test_creates_yaml_file(self, tmp_path: Path) -> None:
        state = make_app_state()
        path = tmp_path / "test.char.yaml"
        save_character(state.character, path)
        assert path.exists()
        assert path.stat().st_size > 100

    def test_yaml_is_valid(self, tmp_path: Path) -> None:
        state = make_app_state()
        path = tmp_path / "test.char.yaml"
        save_character(state.character, path)
        with open(path) as f:
            data = yaml.safe_load(f)
        assert isinstance(data, dict)
        assert "identity" in data
        assert "ability_scores" in data

    def test_identity_fields_saved(self, tmp_path: Path) -> None:
        state = make_app_state()
        c = state.character
        c.name = "Elara Swift"
        c.alignment = "chaotic_good"
        path = tmp_path / "c.char.yaml"
        save_character(c, path)
        with open(path) as f:
            data = yaml.safe_load(f)
        assert data["identity"]["name"] == "Elara Swift"
        assert data["identity"]["alignment"] == "chaotic_good"

    def test_ability_scores_saved(self, tmp_path: Path) -> None:
        state = make_app_state()
        c = state.character
        c.set_ability_score("str", 18)
        c.set_ability_score("dex", 16)
        path = tmp_path / "c.char.yaml"
        save_character(c, path)
        with open(path) as f:
            data = yaml.safe_load(f)
        assert data["ability_scores"]["str"] == 18
        assert data["ability_scores"]["dex"] == 16

    def test_levels_saved(self, tmp_path: Path) -> None:
        state = make_app_state()
        cl = state.class_registry.require("Fighter").make_class_level(4)
        state.character.set_class_levels([cl])
        path = tmp_path / "c.char.yaml"
        save_character(state.character, path)
        with open(path) as f:
            data = yaml.safe_load(f)
        levels = data["levels"]
        assert len(levels) == 4
        assert levels[0]["class"] == "Fighter"

    def test_active_buff_saved_with_cl(self, tmp_path: Path) -> None:
        state = make_app_state()
        bless = state.buff_registry.require("Bless")
        apply_buff(bless, state.character, caster_level=7)
        path = tmp_path / "c.char.yaml"
        save_character(state.character, path)
        with open(path) as f:
            data = yaml.safe_load(f)
        bless_data = data["buffs"].get("Bless")
        assert bless_data is not None
        assert bless_data["active"] is True

    def test_skill_ranks_in_levels(self, tmp_path: Path) -> None:
        """Skill ranks are stored per-level, not top-level."""
        state = make_app_state()
        c = state.character
        # Add a level with skill ranks
        from heroforge.engine.character import (
            CharacterLevel,
        )

        c.levels.append(
            CharacterLevel(
                character_level=1,
                class_name="Fighter",
                hp_roll=10,
                skill_ranks={"Hide": 4, "Climb": 4},
            )
        )
        path = tmp_path / "c.char.yaml"
        save_character(c, path)
        with open(path) as f:
            data = yaml.safe_load(f)
        lv1 = data["levels"][0]
        assert lv1["skill_ranks"]["Hide"] == 4
        assert "skills" not in data

    def test_dm_override_saved(self, tmp_path: Path) -> None:
        state = make_app_state()
        state.character.add_dm_override(
            "Improved Precise Shot", note="Campaign"
        )
        path = tmp_path / "c.char.yaml"
        save_character(state.character, path)
        with open(path) as f:
            data = yaml.safe_load(f)
        overrides = data.get("dm_overrides", [])
        assert any(ov["target"] == "Improved Precise Shot" for ov in overrides)


# ===========================================================================
# load_character
# ===========================================================================


class TestLoadCharacter:
    def _save_and_load(
        self, tmp_path: Path, character: Character
    ) -> tuple[Character, AppState]:
        state = make_app_state()
        path = tmp_path / "c.char.yaml"
        save_character(character, path)
        loaded = load_character(path, state)
        state.set_character(loaded)
        return loaded, state

    def test_identity_restored(self, tmp_path: Path) -> None:
        state = make_app_state()
        c = state.character
        c.name = "Thalindra"
        c.alignment = "neutral_good"
        loaded, _ = self._save_and_load(tmp_path, c)
        assert loaded.name == "Thalindra"
        assert loaded.alignment == "neutral_good"

    def test_ability_scores_restored(self, tmp_path: Path) -> None:
        state = make_app_state()
        c = state.character
        c.set_ability_score("str", 18)
        c.set_ability_score("wis", 16)
        loaded, _ = self._save_and_load(tmp_path, c)
        assert loaded.str_score == 18
        assert loaded.wis_score == 16

    def test_class_levels_restored(self, tmp_path: Path) -> None:
        state = make_app_state()
        cl = state.class_registry.require("Rogue").make_class_level(5)
        state.character.set_class_levels([cl])
        loaded, _ = self._save_and_load(tmp_path, state.character)
        assert loaded.total_level == 5
        assert loaded.class_levels[0].class_name == "Rogue"
        assert loaded.bab == 3  # medium BAB level 5

    def test_multiclass_levels_restored(self, tmp_path: Path) -> None:
        state = make_app_state()
        f_cl = state.class_registry.require("Fighter").make_class_level(4)
        w_cl = state.class_registry.require("Wizard").make_class_level(4)
        state.character.set_class_levels([f_cl, w_cl])
        loaded, _ = self._save_and_load(tmp_path, state.character)
        assert loaded.total_level == 8
        names = {cl.class_name for cl in loaded.class_levels}
        assert "Fighter" in names
        assert "Wizard" in names

    def test_race_applied_on_load(self, tmp_path: Path) -> None:
        state = make_app_state()
        apply_race(state.race_registry.require("Dwarf"), state.character)
        loaded, _ = self._save_and_load(tmp_path, state.character)
        assert loaded.race == "Dwarf"
        # Dwarf gets +2 CON
        assert loaded.con_score == 12  # 10 + 2 racial

    def test_always_on_feat_effect_restored(self, tmp_path: Path) -> None:
        from heroforge.engine.character import (
            CharacterLevel,
        )

        state = make_app_state()
        c = state.character
        c.levels = [
            CharacterLevel(
                character_level=1,
                class_name="Fighter",
                hp_roll=10,
            ),
        ]
        c._invalidate_class_stats()
        c.add_feat(
            "Iron Will",
            state.feat_registry.require("Iron Will"),
            level=1,
            source="character",
        )
        will_with_feat = c.will
        loaded, new_state = self._save_and_load(tmp_path, c)
        assert loaded.will == will_with_feat

    def test_skill_ranks_restored(self, tmp_path: Path) -> None:
        from heroforge.engine.character import (
            CharacterLevel,
        )

        state = make_app_state()
        c = state.character
        c.levels = [
            CharacterLevel(
                character_level=1,
                class_name="Rogue",
                hp_roll=6,
                skill_ranks={"Hide": 4, "Climb": 4},
            ),
            CharacterLevel(
                character_level=2,
                class_name="Rogue",
                hp_roll=4,
                skill_ranks={"Hide": 4},
            ),
        ]
        c._invalidate_class_stats()
        set_skill_ranks(c, "Hide", 8)
        set_skill_ranks(c, "Climb", 4)
        loaded, _ = self._save_and_load(tmp_path, c)
        assert loaded.skills.get("Hide") == 8
        assert loaded.skills.get("Climb") == 4

    def test_skill_total_correct_after_load(self, tmp_path: Path) -> None:
        from heroforge.engine.character import (
            CharacterLevel,
        )

        state = make_app_state()
        c = state.character
        c.set_ability_score("dex", 16)
        c.levels = [
            CharacterLevel(
                character_level=1,
                class_name="Rogue",
                hp_roll=6,
                skill_ranks={"Hide": 6},
            ),
        ]
        c._invalidate_class_stats()
        set_skill_ranks(c, "Hide", 6)
        loaded, new_state = self._save_and_load(tmp_path, c)
        # 6 ranks + 3 dex mod (dex 16, no race)
        assert new_state.skill_total("Hide") == 9

    def test_active_buff_restored(self, tmp_path: Path) -> None:
        state = make_app_state()
        apply_buff(state.buff_registry.require("Bless"), state.character)
        loaded, _ = self._save_and_load(tmp_path, state.character)
        assert loaded.is_buff_active("Bless")

    def test_inactive_buff_state_preserved(self, tmp_path: Path) -> None:
        state = make_app_state()
        c = state.character
        # Register Bless but don't activate it
        bless = state.buff_registry.require("Bless")
        pairs = bless.pool_entries(0, c)
        c.register_buff_definition("Bless", pairs)
        # Don't toggle it
        loaded, _ = self._save_and_load(tmp_path, c)
        assert not loaded.is_buff_active("Bless")

    def test_buff_caster_level_preserved(self, tmp_path: Path) -> None:
        state = make_app_state()
        sof = state.buff_registry.require("Shield of Faith")
        apply_buff(sof, state.character, caster_level=12)
        loaded, _ = self._save_and_load(tmp_path, state.character)
        state_obj = loaded.get_buff_state("Shield of Faith")
        assert state_obj is not None
        assert state_obj.caster_level == 12

    def test_buff_value_correct_after_load(self, tmp_path: Path) -> None:
        state = make_app_state()
        sof = state.buff_registry.require("Shield of Faith")
        apply_buff(sof, state.character, caster_level=12)
        loaded, _ = self._save_and_load(tmp_path, state.character)
        # Shield of Faith CL12 = 2 + 12//6 = 4 deflection
        assert loaded.ac == 14  # 10 + deflection 4

    def test_dm_override_restored(self, tmp_path: Path) -> None:
        state = make_app_state()
        state.character.add_dm_override(
            "Improved Precise Shot", note="Campaign"
        )
        loaded, _ = self._save_and_load(tmp_path, state.character)
        assert loaded.has_dm_override("Improved Precise Shot")

    def test_unknown_race_stored_without_crash(self, tmp_path: Path) -> None:
        """Unknown race name sets race but doesn't crash."""
        path = tmp_path / "unknown_race.char.yaml"
        path.write_text(
            "identity:\n  name: Test\n"
            "  race: Githzerai\n"
            "  alignment: ''\n  deity: ''\n"
            "ability_scores:"
            " {str: 10, dex: 10, con: 10,"
            " int: 10, wis: 10, cha: 10}\n"
            "levels: []\nbuffs: {}\n"
            "templates: []\n"
            "dm_overrides: []\nequipment: {}\n"
        )
        state = make_app_state()
        loaded = load_character(path, state)
        assert loaded.race == "Githzerai"

    def test_unknown_buff_round_trips(self, tmp_path: Path) -> None:
        """Unknown buff should round-trip cleanly."""
        path = tmp_path / "splatbook.char.yaml"
        path.write_text(
            "identity:\n  name: X\n"
            "  race: Human\n"
            "  alignment: ''\n  deity: ''\n"
            "ability_scores:"
            " {str: 10, dex: 10, con: 10,"
            " int: 10, wis: 10, cha: 10}\n"
            "levels: []\n"
            "buffs:\n"
            "  Homebrew Buff:\n"
            "    active: true\n"
            "    caster_level: 8\n"
            "templates: []\n"
            "dm_overrides: []\nequipment: {}\n"
        )
        state = make_app_state()
        loaded = load_character(path, state)
        state_obj = loaded.get_buff_state("Homebrew Buff")
        assert state_obj is not None


# ===========================================================================
# Full round-trip: stat equality
# ===========================================================================


class TestRoundTrip:
    def test_full_fighter_round_trip(self, tmp_path: Path) -> None:
        """
        Build a complete Fighter 6, save, load, and compare every major stat.
        """
        state = make_app_state()
        c = fighter_char(state)

        # Snapshot stats before save
        before = {
            "ac": c.ac,
            "fort": c.fort,
            "ref": c.ref,
            "will": c.will,
            "bab": c.bab,
            "attack_melee": c.get("attack_melee"),
            "attack_ranged": c.get("attack_ranged"),
            "hp_max": c.hp_max,
            "str_score": c.str_score,
            "dex_score": c.dex_score,
            "initiative": c.get("initiative"),
        }

        path = tmp_path / "fighter.char.yaml"
        save_character(c, path)

        new_state = make_app_state()
        loaded = load_character(path, new_state)
        new_state.set_character(loaded)

        after = {
            "ac": loaded.ac,
            "fort": loaded.fort,
            "ref": loaded.ref,
            "will": loaded.will,
            "bab": loaded.bab,
            "attack_melee": loaded.get("attack_melee"),
            "attack_ranged": loaded.get("attack_ranged"),
            "hp_max": loaded.hp_max,
            "str_score": loaded.str_score,
            "dex_score": loaded.dex_score,
            "initiative": loaded.get("initiative"),
        }

        for stat, expected in before.items():
            assert after[stat] == expected, (
                f"{stat}: expected {expected}, got {after[stat]}"
            )

    def test_skill_totals_match_after_round_trip(self, tmp_path: Path) -> None:
        from heroforge.engine.character import (
            CharacterLevel,
        )

        state = make_app_state()
        c = state.character
        apply_race(state.race_registry.require("Elf"), c)
        c.set_ability_score("dex", 16)
        c.levels = [
            CharacterLevel(
                character_level=1,
                class_name="Rogue",
                hp_roll=6,
                skill_ranks={
                    "Hide": 4,
                    "Move Silently": 4,
                    "Tumble": 4,
                },
            ),
            CharacterLevel(
                character_level=2,
                class_name="Rogue",
                hp_roll=4,
                skill_ranks={
                    "Hide": 2,
                    "Move Silently": 2,
                    "Tumble": 1,
                },
            ),
        ]
        c._invalidate_class_stats()
        set_skill_ranks(c, "Hide", 6)
        set_skill_ranks(c, "Move Silently", 6)
        set_skill_ranks(c, "Tumble", 5)

        before_hide = state.skill_total("Hide")
        before_balance = state.skill_total("Balance")

        path = tmp_path / "elf.char.yaml"
        save_character(c, path)

        new_state = make_app_state()
        loaded = load_character(path, new_state)
        new_state.set_character(loaded)

        assert new_state.skill_total("Hide") == before_hide
        assert new_state.skill_total("Balance") == before_balance

    def test_template_effects_preserved(self, tmp_path: Path) -> None:
        state = make_app_state()
        c = state.character
        c.set_ability_score("str", 14)

        hc = state.template_registry.require("Half-Celestial")
        from heroforge.engine.templates import apply_template

        apply_template(hc, c)

        before_str = c.str_score  # 14 + 4 = 18

        path = tmp_path / "hc.char.yaml"
        save_character(c, path)

        new_state = make_app_state()
        loaded = load_character(path, new_state)
        assert loaded.str_score == before_str
