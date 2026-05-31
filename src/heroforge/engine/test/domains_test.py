"""
Tests for cleric domains: data loading and structure.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from heroforge.engine.character import Character, CharacterLevel
from heroforge.engine.domains import (
    DomainRegistry,
)
from heroforge.engine.persistence import load_character, save_character
from heroforge.engine.sheet import gather_sheet
from heroforge.rules.loader import DomainsLoader

RULES_DIR = Path(__file__).parent.parent.parent / "rules"


class TestDomainsLoader:
    def test_load_all_domains(self) -> None:
        reg = DomainRegistry()
        loader = DomainsLoader(RULES_DIR)
        names = loader.load(reg, "core/domains.yaml")
        assert len(names) == 22

    def test_war_domain(self) -> None:
        reg = DomainRegistry()
        DomainsLoader(RULES_DIR).load(reg, "core/domains.yaml")
        war = reg.get("War")
        assert war is not None
        assert war.domain_spells[1] == "Magic Weapon"
        assert war.domain_spells[9] == "Power Word Kill"
        assert "Weapon Focus" in war.granted_power

    def test_all_have_9_spells(self) -> None:
        reg = DomainRegistry()
        DomainsLoader(RULES_DIR).load(reg, "core/domains.yaml")
        for d in reg.all_domains():
            for lvl in range(1, 10):
                assert lvl in d.domain_spells, f"{d.name}: missing level {lvl}"

    def test_names_sorted(self) -> None:
        reg = DomainRegistry()
        DomainsLoader(RULES_DIR).load(reg, "core/domains.yaml")
        names = reg.names()
        assert names == sorted(names)
        assert "Air" in names
        assert "Water" in names


def _cleric_with_domains(domains: list[str]) -> Character:
    c = Character()
    c.name = "Test Cleric"
    c.race = "Human"
    c.alignment = "neutral_good"
    c.set_class_levels(
        [CharacterLevel(character_level=1, class_name="Cleric", hp_roll=8)]
    )
    c.domains = list(domains)
    return c


class TestCharacterDomains:
    """Domains round-trip through persistence and appear in the sheet."""

    def test_save_load_round_trip(self, tmp_path: Path) -> None:
        c = _cleric_with_domains(["Knowledge", "War"])
        path = tmp_path / "cleric.char.yaml"
        save_character(c, path)
        reloaded = load_character(path, None)
        assert reloaded.domains == ["Knowledge", "War"]

    def test_saved_yaml_has_domains_key(self, tmp_path: Path) -> None:
        c = _cleric_with_domains(["Trickery"])
        path = tmp_path / "cleric.char.yaml"
        save_character(c, path)
        assert "Trickery" in path.read_text()

    def test_load_rejects_unknown_domain(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.char.yaml"
        path.write_text(
            "identity:\n"
            "  name: X\n"
            "  race: Human\n"
            "  alignment: neutral\n"
            "domains:\n"
            "  - Bogus\n"
        )
        with pytest.raises(ValueError, match="Bogus"):
            load_character(path, None)

    def test_sheet_emits_domains(self) -> None:
        c = _cleric_with_domains(["War"])
        sheet = gather_sheet(c, None)
        assert "War" in sheet.domains
        entry = sheet.domains["War"]
        assert "Weapon Focus" in entry.granted_power
        assert entry.domain_spells[1] == "Magic Weapon"

    def test_sheet_omits_domains_when_none(self) -> None:
        c = _cleric_with_domains([])
        sheet = gather_sheet(c, None)
        assert sheet.domains == {}


class TestDeityRegistry:
    def test_loads_full_roster(self) -> None:
        from heroforge.rules.rules import get_rules

        assert len(get_rules().deities) == 194

    def test_spot_check_entries(self) -> None:
        from heroforge.rules.rules import get_rules

        reg = get_rules().deities
        istus = reg.get("Istus")
        assert istus.alignment == "neutral"
        assert "Knowledge" in istus.domains
        heironeous = reg.get("Heironeous")
        assert heironeous.alignment == "lawful_good"
        assert "War" in heironeous.domains

    def test_load_rejects_unknown_deity(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.char.yaml"
        path.write_text(
            "identity:\n"
            "  name: X\n"
            "  race: Human\n"
            "  alignment: neutral\n"
            "  deity: Zzyzx the Invented\n"
        )
        with pytest.raises(ValueError, match="Zzyzx the Invented"):
            load_character(path, None)

    def test_empty_deity_allowed(self, tmp_path: Path) -> None:
        path = tmp_path / "ok.char.yaml"
        path.write_text(
            "identity:\n"
            "  name: X\n"
            "  race: Human\n"
            "  alignment: neutral\n"
            "  deity: ''\n"
        )
        loaded = load_character(path, None)  # must not raise
        assert loaded.deity == ""


class TestWarDomainEffect:
    """War domain grants Weapon Focus with the deity's favored weapon."""

    def _war_cleric(self, deity: str, tmp_path: Path) -> Character:
        c = _cleric_with_domains(["War", "Good"])
        c.deity = deity
        path = tmp_path / "war.char.yaml"
        save_character(c, path)
        return load_character(path, None)

    def test_weapon_focus_plus_one_on_attacks(self, tmp_path: Path) -> None:
        c = self._war_cleric("Heironeous", tmp_path)
        sheet = gather_sheet(c, None)
        assert sheet.combat.attack_melee.typed.get("weapon_focus") == 1
        assert sheet.combat.attack_ranged.typed.get("weapon_focus") == 1

    def test_not_persisted_as_feat(self, tmp_path: Path) -> None:
        c = _cleric_with_domains(["War"])
        c.deity = "Heironeous"
        path = tmp_path / "war.char.yaml"
        save_character(c, path)
        assert "Weapon Focus" not in path.read_text()

    def test_no_effect_without_war_domain(self, tmp_path: Path) -> None:
        c = _cleric_with_domains(["Good"])
        c.deity = "Heironeous"
        path = tmp_path / "now.char.yaml"
        save_character(c, path)
        loaded = load_character(path, None)
        sheet = gather_sheet(loaded, None)
        assert "weapon_focus" not in sheet.combat.attack_melee.typed

    def test_war_with_no_deity_no_crash(self, tmp_path: Path) -> None:
        # War domain but no deity → no favored weapon → no effect.
        c = _cleric_with_domains(["War"])
        c.deity = ""
        path = tmp_path / "war.char.yaml"
        save_character(c, path)
        loaded = load_character(path, None)  # must not raise
        sheet = gather_sheet(loaded, None)
        assert "weapon_focus" not in sheet.combat.attack_melee.typed
