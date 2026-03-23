"""
Tests for cleric domains: data loading and structure.
"""

from __future__ import annotations

from pathlib import Path

from heroforge.engine.classes_races import (
    DomainRegistry,
)
from heroforge.rules.loader import DomainsLoader

RULES_DIR = Path(__file__).parent.parent / "src" / "heroforge" / "rules"


class TestDomainsLoader:
    def test_load_all_domains(self) -> None:
        reg = DomainRegistry()
        loader = DomainsLoader(RULES_DIR)
        names = loader.load(reg)
        assert len(names) == 22

    def test_war_domain(self) -> None:
        reg = DomainRegistry()
        DomainsLoader(RULES_DIR).load(reg)
        war = reg.get("War")
        assert war is not None
        assert war.domain_spells[1] == "Magic Weapon"
        assert war.domain_spells[9] == "Power Word Kill"
        assert "Weapon Focus" in war.granted_power

    def test_all_have_9_spells(self) -> None:
        reg = DomainRegistry()
        DomainsLoader(RULES_DIR).load(reg)
        for d in reg.all_domains():
            for lvl in range(1, 10):
                assert lvl in d.domain_spells, f"{d.name}: missing level {lvl}"

    def test_names_sorted(self) -> None:
        reg = DomainRegistry()
        DomainsLoader(RULES_DIR).load(reg)
        names = reg.names()
        assert names == sorted(names)
        assert "Air" in names
        assert "Water" in names
