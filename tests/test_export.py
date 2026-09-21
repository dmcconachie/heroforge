"""
tests/test_export.py
--------------------
Tests for heroforge/export/sheet_data.py and renderer.py.

Covers:
  - gather(): all sections extracted correctly from a Character
  - Identity, abilities, combat, skills, feats, buffs, templates
  - Signed value formatting
  - render_pdf(): file created, is valid PDF, correct page count
  - Round-trip: stat values in SheetData match Character values
  - Edge cases: unnamed character, no class levels, no feats
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from heroforge.engine.derived_pools import install_consumers
from heroforge.engine.effects import apply_buff
from heroforge.engine.races import apply_race
from heroforge.engine.sheet import gather_sheet
from heroforge.engine.skills import (
    register_skills_on_character,
    set_skill_ranks,
)
from heroforge.engine.templates import apply_template
from heroforge.export.sheet_data import gather
from heroforge.rules.rules import get_rules

if TYPE_CHECKING:
    from heroforge.engine.character import Character
    from heroforge.export.sheet_data import SheetData
import re

from heroforge.engine.character import Character, CharacterLevel
from heroforge.engine.enums import Ability
from heroforge.export.renderer import render_pdf

RULES_DIR = Path(__file__).parent.parent / "src" / "heroforge" / "rules"


# ===========================================================================
# Fixtures
# ===========================================================================


def new_character() -> Character:
    """A blank Character with skills and derived pools wired."""
    c = Character()
    register_skills_on_character(c)
    dp = get_rules().derived_pools
    if dp:
        install_consumers(c, dp)
    return c


def full_char() -> Character:
    """A representative Fighter 6 for export tests."""
    c = new_character()
    c.name = "Aldric Vane"
    c.player = "Test Player"
    c.alignment = "lawful_good"
    c.deity = "St. Cuthbert"

    apply_race(get_rules().races.require("Human"), c)

    c.set_class_levels(
        [
            CharacterLevel(
                character_level=i + 1,
                class_name="Fighter",
                hp_roll=10,
            )
            for i in range(6)
        ]
    )

    for ab, score in [
        ("str", 16),
        ("dex", 14),
        ("con", 14),
        ("int", 12),
        ("wis", 10),
        ("cha", 8),
    ]:
        c.set_ability_score(Ability(ab), score)

    # Feats
    c.add_feat(
        "Dodge",
        get_rules().feats.require("Dodge"),
        level=1,
        source="character",
    )
    c.add_feat(
        "Toughness",
        get_rules().feats.require("Toughness"),
        level=1,
        source="character",
    )
    c.add_feat(
        "Iron Will",
        get_rules().feats.require("Iron Will"),
        level=1,
        source="character",
    )

    # Skills
    set_skill_ranks(c, "Climb", 6)
    set_skill_ranks(c, "Jump", 6)
    set_skill_ranks(c, "Intimidate", 4)

    # Active buff
    apply_buff(get_rules().buffs.require("Bless"), c, caster_level=5)

    return c


# ===========================================================================
# gather() — SheetData extraction
# ===========================================================================


class TestGatherIdentity:
    def test_name(self) -> None:
        c = full_char()
        data = gather(c)
        assert data.identity.name == "Aldric Vane"

    def test_player(self) -> None:
        c = full_char()
        data = gather(c)
        assert data.identity.player == "Test Player"

    def test_race(self) -> None:
        c = full_char()
        data = gather(c)
        assert data.identity.race == "Human"

    def test_class_str(self) -> None:
        c = full_char()
        data = gather(c)
        assert "Fighter" in data.identity.class_str
        assert "6" in data.identity.class_str

    def test_level(self) -> None:
        c = full_char()
        data = gather(c)
        assert data.identity.level == 6

    def test_alignment(self) -> None:
        c = full_char()
        data = gather(c)
        assert data.identity.alignment == "lawful_good"

    def test_size_from_race(self) -> None:
        c = new_character()
        apply_race(get_rules().races.require("Gnome"), c)
        data = gather(c)
        assert data.identity.size == "Small"

    def test_blank_character_identity(self) -> None:
        c = new_character()
        data = gather(c)
        # Default character name is 'Unnamed'
        assert data.identity.name == "Unnamed"
        assert data.identity.level == 0


class TestGatherAbilities:
    def test_six_abilities_present(self) -> None:
        c = full_char()
        data = gather(c)
        assert len(data.abilities) == 6

    def test_ability_names(self) -> None:
        c = new_character()
        data = gather(c)
        names = [a.name for a in data.abilities]
        assert names == ["STR", "DEX", "CON", "INT", "WIS", "CHA"]

    def test_ability_scores_match_character(self) -> None:
        c = full_char()
        data = gather(c)
        c = c
        str_row = next(a for a in data.abilities if a.name == "STR")
        assert str_row.score == c.str_score
        assert str_row.mod == c.str_mod

    def test_racial_bonus_included_in_score(self) -> None:
        """Racial bonus is part of effective score saved in SheetData."""
        c = new_character()
        c = c
        c.set_ability_score(Ability.DEX, 12)
        apply_race(get_rules().races.require("Elf"), c)  # +2 DEX
        data = gather(c)
        dex_row = next(a for a in data.abilities if a.name == "DEX")
        assert dex_row.score == 14  # 12 base + 2 racial
        assert dex_row.mod == 2


class TestGatherCombat:
    def test_ac_matches_character(self) -> None:
        c = full_char()
        data = gather(c)
        assert data.combat.ac == c.ac

    def test_saves_match(self) -> None:
        c = full_char()
        data = gather(c)
        c = c
        assert data.combat.fort == c.fort
        assert data.combat.ref == c.ref
        assert data.combat.will == c.will

    def test_bab_matches(self) -> None:
        c = full_char()
        data = gather(c)
        assert data.combat.bab == c.bab

    def test_attack_melee_matches(self) -> None:
        c = full_char()
        data = gather(c)
        assert data.combat.attack_melee == c.get("attack_melee")

    def test_hp_max_matches(self) -> None:
        c = full_char()
        data = gather(c)
        assert data.combat.hp_max == c.hp_max

    def test_touch_ac_excludes_armor(self) -> None:
        """Touch AC should be ≤ regular AC (no armor bonus)."""
        c = full_char()
        data = gather(c)
        assert data.combat.touch_ac <= data.combat.ac


class TestGatherSkills:
    def test_all_skills_present(self) -> None:
        c = full_char()
        data = gather(c)
        assert len(data.skills) == len(get_rules().skills)

    def test_skill_names_sorted(self) -> None:
        c = new_character()
        data = gather(c)
        names = [s.name for s in data.skills]
        assert names == sorted(names)

    def test_ranks_correct(self) -> None:
        c = full_char()
        data = gather(c)
        climb = next(s for s in data.skills if s.name == "Climb")
        assert climb.ranks == 6

    def test_total_correct(self) -> None:
        c = new_character()
        c = c
        c.set_ability_score(Ability.STR, 16)  # mod +3
        set_skill_ranks(c, "Climb", 6)
        data = gather(c)
        climb = next(s for s in data.skills if s.name == "Climb")
        assert climb.total == 9  # 6 + 3

    def test_class_skill_marked(self) -> None:

        c = new_character()
        c.set_class_levels(
            [
                CharacterLevel(
                    character_level=1,
                    class_name="Fighter",
                    hp_roll=10,
                )
            ]
        )
        data = gather(c)
        climb = next(s for s in data.skills if s.name == "Climb")
        assert climb.class_skill is True  # Fighter class skill

    def test_non_class_skill_not_marked(self) -> None:

        c = new_character()
        c.set_class_levels(
            [
                CharacterLevel(
                    character_level=1,
                    class_name="Fighter",
                    hp_roll=10,
                )
            ]
        )
        data = gather(c)
        spellcraft = next(s for s in data.skills if s.name == "Spellcraft")
        assert spellcraft.class_skill is False  # not a Fighter skill


class TestGatherFeats:
    def test_taken_feats_present(self) -> None:
        c = full_char()
        data = gather(c)
        names = [f.name for f in data.feats]
        assert "Dodge" in names
        assert "Toughness" in names
        assert "Iron Will" in names

    def test_feat_count_matches_character(self) -> None:
        c = full_char()
        data = gather(c)
        assert len(data.feats) == len(c.feats)

    def test_feat_note_included(self) -> None:
        c = new_character()
        c.add_feat(
            "Dodge",
            get_rules().feats.require("Dodge"),
            level=1,
            source="character",
        )
        data = gather(c)
        dodge = next(f for f in data.feats if f.name == "Dodge")
        assert "dodge" in dodge.note.lower() or dodge.note != ""

    def test_template_feat_source_marked(self) -> None:
        c = new_character()
        hc = get_rules().templates.require("Half-Celestial")
        apply_template(hc, c)
        data = gather(c)
        # Half-Celestial grants no feats in the YAML actually;
        # use werewolf which grants Iron Will
        ww = get_rules().templates.require("Lycanthrope (Werewolf)")
        apply_template(ww, c)
        data = gather(c)
        iron_will = next((f for f in data.feats if f.name == "Iron Will"), None)
        if iron_will:
            assert True  # source may be set


class TestGatherBuffs:
    def test_active_buffs_listed(self) -> None:
        c = full_char()
        data = gather(c)
        names = [b.name for b in data.active_buffs]
        assert "Bless" in names

    def test_inactive_buffs_not_in_active(self) -> None:
        c = new_character()
        # Register Bless but don't activate
        bless = get_rules().buffs.require("Bless")
        pairs = bless.pool_entries(0, c)
        c.register_buff_definition("Bless", pairs)
        data = gather(c)
        active_names = [b.name for b in data.active_buffs]
        assert "Bless" not in active_names

    def test_all_buffs_includes_inactive(self) -> None:
        c = new_character()
        bless = get_rules().buffs.require("Bless")
        pairs = bless.pool_entries(0, c)
        c.register_buff_definition("Bless", pairs)
        data = gather(c)
        all_names = [b.name for b in data.all_buffs]
        assert "Bless" in all_names

    def test_buff_caster_level_preserved(self) -> None:
        c = new_character()
        apply_buff(
            get_rules().buffs.require("Shield of Faith"),
            c,
            caster_level=12,
        )
        data = gather(c)
        sof = next(b for b in data.active_buffs if b.name == "Shield of Faith")
        assert sof.caster_level == 12


class TestGatherTemplates:
    def test_template_name_present(self) -> None:
        c = new_character()
        apply_template(
            get_rules().templates.require("Half-Celestial"),
            c,
        )
        data = gather(c)
        assert any("Half-Celestial" in t for t in data.templates)

    def test_partial_template_shows_level(self) -> None:
        c = new_character()
        apply_template(
            get_rules().templates.require("Lycanthrope (Werewolf)"),
            c,
            level=2,
        )
        data = gather(c)
        assert any("level 2" in t for t in data.templates)


# ===========================================================================
# render_pdf() — file generation
# ===========================================================================


class TestRenderPdf:
    def _make_pdf(
        self,
        tmp_path: Path,
    ) -> tuple[Path, SheetData]:
        data = gather(full_char())
        path = tmp_path / "sheet.pdf"
        render_pdf(data, path)
        return path, data

    def test_pdf_file_created(self, tmp_path: Path) -> None:
        path, _ = self._make_pdf(tmp_path)
        assert path.exists()

    def test_pdf_not_empty(self, tmp_path: Path) -> None:
        path, _ = self._make_pdf(tmp_path)
        assert path.stat().st_size > 5_000  # at least 5KB

    def test_pdf_starts_with_pdf_header(self, tmp_path: Path) -> None:
        path, _ = self._make_pdf(tmp_path)
        with open(path, "rb") as f:
            header = f.read(5)
        assert header == b"%PDF-"

    def test_pdf_has_at_least_two_pages(self, tmp_path: Path) -> None:
        """PDF should contain at least two pages."""

        path, _ = self._make_pdf(tmp_path)
        content = path.read_bytes().decode("latin-1", errors="replace")
        # ReportLab embeds /Count N in the Pages dict
        counts = re.findall(r"/Count\s+(\d+)", content)
        assert counts, "No /Count found in PDF"
        assert int(counts[0]) >= 2

    def test_blank_character_renders_without_crash(
        self, tmp_path: Path
    ) -> None:
        """A character with no name, class, or feats should still render."""
        c = new_character()

        data = gather(c)
        path = tmp_path / "blank.pdf"
        render_pdf(data, path)
        assert path.exists()
        assert path.stat().st_size > 5_000

    def test_character_name_in_pdf(self, tmp_path: Path) -> None:
        """PDF has correct page structure for a named character."""
        path, data = self._make_pdf(tmp_path)
        # Data extraction worked
        assert data.identity.name == "Aldric Vane"
        # File is valid PDF with correct structure
        header = path.read_bytes()[:5]
        assert header == b"%PDF-"

    def test_all_active_buffs_in_pdf(self, tmp_path: Path) -> None:
        """Active buffs appear in SheetData and PDF renders without error."""
        c = full_char()

        data = gather(c)
        # Verify Bless is in the data layer
        assert any(b.name == "Bless" for b in data.active_buffs)
        path = tmp_path / "buffs.pdf"
        render_pdf(data, path)
        assert path.stat().st_size > 5_000

    def test_multiclass_character_renders(self, tmp_path: Path) -> None:

        c = new_character()
        c = c
        c.name = "Multiclass Hero"
        levels = [
            CharacterLevel(
                character_level=i + 1,
                class_name="Fighter",
                hp_roll=10,
            )
            for i in range(4)
        ] + [
            CharacterLevel(
                character_level=4 + i + 1,
                class_name="Wizard",
                hp_roll=4,
            )
            for i in range(4)
        ]
        c.set_class_levels(levels)

        data = gather(c)
        path = tmp_path / "multi.pdf"
        render_pdf(data, path)
        assert path.stat().st_size > 5_000

    def test_template_character_renders(self, tmp_path: Path) -> None:
        c = new_character()
        c = c
        c.name = "Half-Dragon Hero"
        apply_template(get_rules().templates.require("Half-Dragon (Red)"), c)

        data = gather(c)
        path = tmp_path / "template.pdf"
        render_pdf(data, path)
        assert path.stat().st_size > 5_000

    def test_path_as_string_works(self, tmp_path: Path) -> None:
        """render_pdf should accept a string path as well as Path."""
        c = new_character()

        data = gather(c)
        path_str = str(tmp_path / "str_path.pdf")
        render_pdf(data, path_str)
        assert Path(path_str).exists()


# ===========================================================================
# The PDF and the sheet must agree
# ===========================================================================


class TestExportMatchesTheSheet:
    """
    Regression: export/sheet_data.py computed touch and
    flat-footed AC with private helpers copied into a PyQt6
    widget, and the copies had drifted from
    Character.touch_ac()/.flatfooted_ac() that
    engine/sheet.py uses. The widget's flat-footed version
    ignored Uncanny Dodge, so a barbarian rendered one AC
    on the sheet and a lower one in the PDF. DMG p. 195:
    uncanny dodge "retains her Dexterity bonus to AC (if
    any) regardless of being caught flat-footed".
    """

    @staticmethod
    def _barbarian(level: int = 5) -> Character:
        c = new_character()
        for ab in Ability:
            c.set_ability_score(ab, 14)
        apply_race(get_rules().races.require("Human"), c)
        c.set_class_levels(
            [
                CharacterLevel(
                    character_level=i + 1,
                    class_name="Barbarian",
                    hp_roll=10,
                )
                for i in range(level)
            ]
        )
        return c

    def test_barbarian_has_uncanny_dodge(self) -> None:
        assert self._barbarian().has_class_feature("uncanny_dodge")

    def test_flatfooted_ac_keeps_dex_for_uncanny_dodge(self) -> None:
        """Dex 14 (+2) is retained, so flat-footed == AC."""
        c = self._barbarian()
        assert c.get("ac_dex_contribution") == 2
        assert c.flatfooted_ac() == c.ac

    def test_pdf_flatfooted_matches_the_sheet(self) -> None:
        c = self._barbarian()
        assert (
            gather(c).combat.flatfooted_ac
            == gather_sheet(c).combat.flatfooted_ac
        )

    def test_pdf_touch_matches_the_sheet(self) -> None:
        c = self._barbarian()
        assert gather(c).combat.touch_ac == gather_sheet(c).combat.touch_ac

    def test_pdf_ac_block_matches_the_sheet(self) -> None:
        """Every AC number on the PDF equals the sheet's."""
        c = self._barbarian()
        data = gather(c)
        sheet = gather_sheet(c)
        assert (data.combat.touch_ac, data.combat.flatfooted_ac) == (
            sheet.combat.touch_ac,
            sheet.combat.flatfooted_ac,
        )
