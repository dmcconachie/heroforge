"""
Tests for SRD spell files: compendium and buff spells.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from heroforge.engine.effects import BuffRegistry
from heroforge.engine.spells import SpellCompendium
from heroforge.rules.loader import (
    SpellCompendiumLoader,
    SpellsLoader,
)

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


class TestSpellsSrdBuffs:
    def test_loader_accepts_file(self) -> None:
        reg = BuffRegistry()
        loader = SpellsLoader(RULES_DIR)
        names = loader.load(reg, "core/spells_srd_buffs.yaml")
        assert len(names) >= 20

    def test_no_duplicates_with_phb(self) -> None:
        phb_path = RULES_DIR / "core" / "spells_phb.yaml"
        with open(phb_path) as f:
            phb = yaml.safe_load(f)
        phb_names = {d["name"] for d in phb["spells"]}

        srd_path = RULES_DIR / "core" / "spells_srd_buffs.yaml"
        with open(srd_path) as f:
            srd = yaml.safe_load(f)
        for d in srd["spells"]:
            assert d["name"] not in phb_names, (
                f"{d['name']!r} duplicates spells_phb.yaml"
            )

    def test_protection_from_evil_effects(
        self,
    ) -> None:
        reg = BuffRegistry()
        loader = SpellsLoader(RULES_DIR)
        loader.load(reg, "core/spells_srd_buffs.yaml")
        defn = reg.get("Protection from Evil")
        assert defn is not None
        targets = {e.target for e in defn.effects}
        assert "ac" in targets


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
