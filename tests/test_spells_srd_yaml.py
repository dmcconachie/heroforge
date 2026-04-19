"""
Tests for SRD spell compendium files and dual
registration of buff effects.
"""

from __future__ import annotations

from pathlib import Path

from heroforge.engine.effects import BuffRegistry
from heroforge.engine.spells import SpellCompendium
from heroforge.rules.loader import SpellCompendiumLoader

RULES_DIR = Path(__file__).parent.parent / "src" / "heroforge" / "rules"

_SPELL_FILES = [f"core/spells_level_{i}.yaml" for i in range(10)]


def _load_all(
    comp: SpellCompendium | None = None,
    reg: BuffRegistry | None = None,
) -> SpellCompendium:
    if comp is None:
        comp = SpellCompendium()
    loader = SpellCompendiumLoader(RULES_DIR)
    for f in _SPELL_FILES:
        loader.load(comp, f, buff_registry=reg)
    return comp


class TestSpellCompendium:
    def test_load_all_files(self) -> None:
        comp = _load_all()
        assert len(comp) >= 500

    def test_all_entries_have_levels(
        self,
    ) -> None:
        comp = _load_all()
        for entry in comp.all_entries():
            assert len(entry.level) > 0, f"{entry.name!r} has no level"

    def test_fireball_is_wiz3(self) -> None:
        comp = SpellCompendium()
        loader = SpellCompendiumLoader(RULES_DIR)
        loader.load(comp, "core/spells_level_3.yaml")
        fb = comp.get("Fireball")
        assert fb is not None
        assert fb.level.get("Sorcerer") == 3
        assert fb.level.get("Wizard") == 3

    def test_by_class_and_level(self) -> None:
        comp = SpellCompendium()
        loader = SpellCompendiumLoader(RULES_DIR)
        loader.load(comp, "core/spells_level_0.yaml")
        wiz0 = comp.by_class_and_level("Wizard", 0)
        names = {s.name for s in wiz0}
        assert "Detect Magic" in names
        assert "Prestidigitation" in names


class TestCompendiumBuffRegistration:
    """
    Spells with effects in compendium YAML also
    register in BuffRegistry via dual registration."""

    def setup_method(self) -> None:
        self.reg = BuffRegistry()
        self.comp = _load_all(reg=self.reg)

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

    def test_protection_from_evil_not_a_buff(
        self,
    ) -> None:
        # Protection from X is alignment-conditional — its
        # +2 deflection / +2 resistance only apply vs the
        # opposed alignment. Removed from the buff registry
        # in Phase 1; a future conditional-effects panel
        # will surface it.
        assert self.reg.get("Protection from Evil") is None

    def test_barkskin_is_formula(self) -> None:
        defn = self.reg.require("Barkskin")
        assert defn.requires_caster_level is True
        assert defn.effects[0].is_formula()

    def test_haste_registered(self) -> None:
        assert "Haste" in self.reg

    def test_fireball_not_registered(self) -> None:
        """No stat effects -> no buff."""
        assert "Fireball" not in self.reg
