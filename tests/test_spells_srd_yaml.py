"""
Tests for SRD spell compendium files and dual
registration of buff effects.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from heroforge.engine.effects import BuffRegistry
from heroforge.engine.spells import SpellCompendium
from heroforge.rules.loader import SpellCompendiumLoader

RULES_DIR = Path(__file__).parent.parent / "src" / "heroforge" / "rules"


class TestSpellCompendium:
    def test_load_all_three_files(self) -> None:
        comp = SpellCompendium()
        loader = SpellCompendiumLoader(RULES_DIR)
        for f in (
            "core/spells_srd_0_3.yaml",
            "core/spells_srd_4_6.yaml",
            "core/spells_srd_7_9.yaml",
        ):
            loader.load(comp, f)
        assert len(comp) >= 500

    def test_all_entries_have_levels(
        self,
    ) -> None:
        comp = SpellCompendium()
        loader = SpellCompendiumLoader(RULES_DIR)
        for f in (
            "core/spells_srd_0_3.yaml",
            "core/spells_srd_4_6.yaml",
            "core/spells_srd_7_9.yaml",
        ):
            loader.load(comp, f)
        for entry in comp.all_entries():
            assert len(entry.level) > 0, f"{entry.name!r} has no level info"

    def test_fireball_is_wiz3(self) -> None:
        comp = SpellCompendium()
        loader = SpellCompendiumLoader(RULES_DIR)
        loader.load(comp, "core/spells_srd_0_3.yaml")
        fb = comp.get("Fireball")
        assert fb is not None
        assert fb.level.get("Sorcerer") == 3
        assert fb.level.get("Wizard") == 3

    def test_by_class_and_level(self) -> None:
        comp = SpellCompendium()
        loader = SpellCompendiumLoader(RULES_DIR)
        loader.load(comp, "core/spells_srd_0_3.yaml")
        wiz0 = comp.by_class_and_level("Wizard", 0)
        names = {s.name for s in wiz0}
        assert "Detect Magic" in names
        assert "Prestidigitation" in names


class TestCompendiumBuffRegistration:
    """
    Spells with effects in compendium YAML also
    register in BuffRegistry via dual registration."""

    def setup_method(self) -> None:
        self.comp = SpellCompendium()
        self.reg = BuffRegistry()
        loader = SpellCompendiumLoader(RULES_DIR)
        for f in (
            "core/spells_srd_0_3.yaml",
            "core/spells_srd_4_6.yaml",
            "core/spells_srd_7_9.yaml",
        ):
            loader.load(
                self.comp,
                f,
                buff_registry=self.reg,
            )

    def test_buff_count_at_least_twenty(
        self,
    ) -> None:
        assert len(self.reg) >= 20

    def test_bless_registered(self) -> None:
        assert "Bless" in self.reg

    def test_shield_of_faith_registered(
        self,
    ) -> None:
        assert "Shield of Faith" in self.reg

    def test_protection_from_evil_effects(
        self,
    ) -> None:
        defn = self.reg.get("Protection from Evil")
        assert defn is not None
        targets = {e.target for e in defn.effects}
        assert "ac" in targets

    def test_barkskin_is_formula(self) -> None:
        defn = self.reg.require("Barkskin")
        assert defn.requires_caster_level is True
        assert defn.effects[0].is_formula()

    def test_haste_registered(self) -> None:
        assert "Haste" in self.reg

    def test_fireball_not_registered(self) -> None:
        """No stat effects -> no buff."""
        assert "Fireball" not in self.reg


class TestSpellListsYaml:
    def test_structure(self) -> None:
        path = RULES_DIR / "core" / "spell_lists.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)
        assert "spell_lists" in data
        for cls in [
            "Bard",
            "Cleric",
            "Druid",
            "Paladin",
            "Ranger",
            "Sorcerer",
            "Wizard",
        ]:
            assert cls in data["spell_lists"], f"Missing class: {cls}"

    def test_wizard_has_9_levels(self) -> None:
        path = RULES_DIR / "core" / "spell_lists.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)
        wiz = data["spell_lists"]["Wizard"]
        assert 0 in wiz
        assert 9 in wiz

    def test_bard_max_level_6(self) -> None:
        path = RULES_DIR / "core" / "spell_lists.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)
        bard = data["spell_lists"]["Bard"]
        assert 6 in bard
        assert 7 not in bard

    def test_paladin_starts_at_1(self) -> None:
        path = RULES_DIR / "core" / "spell_lists.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)
        pal = data["spell_lists"]["Paladin"]
        assert 0 not in pal
        assert 1 in pal
