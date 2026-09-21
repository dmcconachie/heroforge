"""
Tests for cleric domains: data loading and structure.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from heroforge.engine.character import Character, CharacterLevel
from heroforge.engine.domains import (
    DomainDefinition,
    DomainRegistry,
    refresh_domain_resources,
)
from heroforge.engine.persistence import load_character, save_character
from heroforge.engine.sheet import gather_sheet
from heroforge.engine.spells import SpellCompendium, SpellEntry
from heroforge.rules.loader import (
    DomainsLoader,
    LoaderError,
    SpellCompendiumLoader,
    validate_domain_spells,
)
from heroforge.rules.rules import get_rules
from heroforge.rules.schema import converter

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


def _compendium(*names: str) -> SpellCompendium:
    """A SpellCompendium holding exactly the named spells."""
    comp = SpellCompendium()
    for name in names:
        comp.register(SpellEntry(name=name))
    return comp


def _domains(**spells_by_domain: dict[int, str]) -> DomainRegistry:
    """A DomainRegistry built from plain dicts."""
    reg = DomainRegistry()
    for name, spells in spells_by_domain.items():
        reg.register(DomainDefinition(name=name, domain_spells=spells))
    return reg


@pytest.mark.no_cached_rules
class TestDomainSpellValidation:
    """
    Every domain spell must name a spell in the compendium.

    These exercise the loader against fresh registries, so they
    opt out of the session-cached Rules (see conftest.py).
    """

    def test_all_known_passes(self) -> None:
        reg = _domains(Air={1: "Obscuring Mist", 2: "Wind Wall"})
        comp = _compendium("Obscuring Mist", "Wind Wall")
        validate_domain_spells(reg, comp)  # must not raise

    def test_unknown_spell_raises(self) -> None:
        reg = _domains(Air={1: "Obscurring Mist"})
        with pytest.raises(LoaderError, match="Obscurring Mist"):
            validate_domain_spells(reg, _compendium("Obscuring Mist"))

    def test_error_names_domain_and_level(self) -> None:
        reg = _domains(Air={4: "Air Walkk"})
        with pytest.raises(LoaderError) as exc:
            validate_domain_spells(reg, _compendium())
        msg = str(exc.value)
        assert "Air" in msg
        assert "4" in msg

    def test_reports_every_unknown_at_once(self) -> None:
        reg = _domains(
            Air={1: "Obscurring Mist", 2: "Wind Wall"},
            Water={1: "Obscuring Mist", 3: "Watter Breathing"},
        )
        comp = _compendium("Obscuring Mist", "Wind Wall")
        with pytest.raises(LoaderError) as exc:
            validate_domain_spells(reg, comp)
        msg = str(exc.value)
        assert "Obscurring Mist" in msg
        assert "Watter Breathing" in msg
        assert "Wind Wall" not in msg

    def test_core_domain_spells_all_known(self) -> None:
        """Regression: core/domains.yaml vs the real compendium."""
        reg = DomainRegistry()
        DomainsLoader(RULES_DIR).load(reg, "core/domains.yaml")
        comp = SpellCompendium()
        scl = SpellCompendiumLoader(RULES_DIR)
        for lvl in range(10):
            scl.load(comp, f"core/spells_level_{lvl}.yaml")
        validate_domain_spells(reg, comp)  # must not raise


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

        assert len(get_rules().deities) == 194

    def test_spot_check_entries(self) -> None:

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

    def test_grants_deity_specific_weapon_focus(self, tmp_path: Path) -> None:
        """The sheet shows the specific weapon, not the generic feat."""
        c = self._war_cleric("Heironeous", tmp_path)
        sheet = gather_sheet(c, None)
        assert "Weapon Focus (Battleaxe)" in sheet.feats
        assert "Weapon Focus" not in sheet.feats

    def test_granted_feat_follows_deity(self, tmp_path: Path) -> None:
        """
        Derived, not stored: switching deity switches the granted
        feat and leaves no stale one behind.
        """
        c = self._war_cleric("Heironeous", tmp_path)
        assert "Weapon Focus (Battleaxe)" in gather_sheet(c, None).feats

        c.deity = "Kord"
        path = tmp_path / "rededicated.char.yaml"
        save_character(c, path)
        feats = gather_sheet(load_character(path, None), None).feats
        assert "Weapon Focus (Greatsword)" in feats
        assert "Weapon Focus (Battleaxe)" not in feats

    def test_weapon_focus_adds_no_generic_attack_bonus(
        self, tmp_path: Path
    ) -> None:
        """
        Weapon Focus applies only to the favored weapon, so it must
        not inflate the weapon-agnostic attack lines.
        """
        c = self._war_cleric("Heironeous", tmp_path)
        sheet = gather_sheet(c, None)
        assert "weapon_focus" not in sheet.combat.attack_melee.typed
        assert "weapon_focus" not in sheet.combat.attack_ranged.typed

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
        assert not [f for f in sheet.feats if f.startswith("Weapon Focus")]

    def test_war_with_no_deity_no_crash(self, tmp_path: Path) -> None:
        # War domain but no deity → no favored weapon → no feat.
        c = _cleric_with_domains(["War"])
        c.deity = ""
        path = tmp_path / "war.char.yaml"
        save_character(c, path)
        loaded = load_character(path, None)  # must not raise
        sheet = gather_sheet(loaded, None)
        assert not [f for f in sheet.feats if f.startswith("Weapon Focus")]


class TestDomainSpellSlots:
    """
    The domain slot is a separate restricted track: it appears
    alongside the general allotment on the sheet and never
    inflates it.
    """

    def _cleric(self, levels: int, domains: list[str]) -> Character:
        c = Character()
        c.name = "Slot Cleric"
        c.race = "Human"
        c.alignment = "neutral_good"
        c.set_class_levels(
            [
                CharacterLevel(
                    character_level=i + 1,
                    class_name="Cleric",
                    hp_roll=8,
                )
                for i in range(levels)
            ]
        )
        c.domains = list(domains)
        return c

    def test_cleric_with_domains_gets_domain_slots(self) -> None:
        c = self._cleric(1, ["Good", "War"])
        entry = gather_sheet(c, None).spellcasting["Cleric"]
        assert entry.domain_slots_per_day is not None
        assert entry.domain_slots_per_day[0] is None
        assert entry.domain_slots_per_day[1] == 1

    def test_general_allotment_unchanged_by_domains(self) -> None:
        without = gather_sheet(self._cleric(5, []), None)
        with_dom = gather_sheet(self._cleric(5, ["Good", "War"]), None)
        assert (
            with_dom.spellcasting["Cleric"].slots_per_day
            == without.spellcasting["Cleric"].slots_per_day
        )

    def test_no_domains_no_domain_slots(self) -> None:
        c = self._cleric(5, [])
        entry = gather_sheet(c, None).spellcasting["Cleric"]
        assert entry.domain_slots_per_day is None

    def test_non_domain_caster_has_none(self) -> None:
        c = Character()
        c.race = "Human"
        c.set_class_levels(
            [CharacterLevel(character_level=1, class_name="Wizard", hp_roll=4)]
        )
        c.domains = ["Good"]  # nonsensical, but must not grant slots
        entry = gather_sheet(c, None).spellcasting["Wizard"]
        assert entry.domain_slots_per_day is None


class TestDomainSchemaRejectsUnknownKeys:
    """
    The DomainDefinition hook bypasses forbid_extra_keys, so it
    must reject unknown keys itself — a silently dropped key is
    how `class_skills` went missing when it was first added.
    """

    def test_unknown_key_raises(self) -> None:

        decl = {"name": "Bogus", "granted_powr": "typo"}
        with pytest.raises(ValueError, match="granted_powr"):
            converter.structure(decl, DomainDefinition)

    def test_known_keys_structure(self) -> None:

        decl = {
            "name": "Animal",
            "granted_power": "x",
            "domain_spells": {1: "Calm Animals"},
            "class_skills": ["Knowledge (Nature)"],
        }
        defn = converter.structure(decl, DomainDefinition)
        assert defn.class_skills == ["Knowledge (Nature)"]
        assert defn.domain_spells[1] == "Calm Animals"


class TestDomainResources:
    """
    Domain granted powers with a daily limit become real
    ResourceTrackers (PHB pp. 186-187). Seven domains are strictly
    once per day; Travel is a duration pool of 1 round per cleric
    level, so the unit has to be carried or the sheet misreports.
    """

    def _cleric(self, levels: int, domains: list[str]) -> Character:
        c = Character()
        c.name = "Resource Cleric"
        c.race = "Human"
        c.alignment = "neutral_good"
        c.set_class_levels(
            [
                CharacterLevel(
                    character_level=i + 1,
                    class_name="Cleric",
                    hp_roll=8,
                )
                for i in range(levels)
            ]
        )
        c.domains = list(domains)
        refresh_domain_resources(c)
        return c

    def test_death_touch_once_per_day(self) -> None:
        c = self._cleric(7, ["Death", "War"])
        r = c.resources["Death Touch"]
        assert r.current == 1
        assert r.unit == "use"

    def test_travel_scales_with_cleric_level(self) -> None:
        c = self._cleric(7, ["Travel"])
        r = c.resources["Freedom of Movement"]
        assert r.current == 7
        assert r.unit == "round"

    def test_domain_without_resource_adds_nothing(self) -> None:
        c = self._cleric(7, ["War", "Good"])
        assert c.resources == {}

    def test_tracker_is_consumable(self) -> None:
        c = self._cleric(5, ["Luck"])
        r = c.resources["Reroll"]
        assert r.use()
        assert r.exhausted
        assert not r.use()

    def test_refresh_replaces_stale_resources(self) -> None:
        """Dropping a domain drops its resource."""
        c = self._cleric(5, ["Death"])
        assert "Death Touch" in c.resources
        c.domains = ["War"]
        refresh_domain_resources(c)
        assert "Death Touch" not in c.resources

    def test_sheet_emits_resources(self) -> None:
        c = self._cleric(7, ["Death", "Travel"])
        sheet = gather_sheet(c, None)
        assert sheet.resources["Death Touch"].max_uses == 1
        fom = sheet.resources["Freedom of Movement"]
        assert fom.max_uses == 7
        assert fom.unit == "round"

    def test_sheet_omits_resources_when_none(self) -> None:
        c = self._cleric(7, ["War"])
        assert gather_sheet(c, None).resources == {}

    def test_all_declared_resources_load(self) -> None:
        """Every domain resource in the YAML is well-formed."""

        named = {
            d.name: d.resource
            for d in get_rules().domains.all_domains()
            if d.resource is not None
        }
        assert set(named) == {
            "Animal",
            "Death",
            "Destruction",
            "Luck",
            "Protection",
            "Strength",
            "Sun",
            "Travel",
        }


class TestDomainToggleableBuffs:
    """
    Strength and Protection grant a scaling bonus when activated
    (PHB p. 187). Both are registered as toggleable buffs so the
    player turns them on for the round/save they apply to, rather
    than the sheet pretending they are always on.
    """

    def _cleric(self, levels: int, domains: list[str]) -> Character:
        c = Character()
        c.race = "Human"
        c.alignment = "neutral_good"
        c.set_ability_score("str", 12)
        c.set_class_levels(
            [
                CharacterLevel(
                    character_level=i + 1,
                    class_name="Cleric",
                    hp_roll=8,
                )
                for i in range(levels)
            ]
        )
        c.domains = list(domains)
        refresh_domain_resources(c)
        return c

    def test_feat_of_strength_registered_inactive(self) -> None:
        c = self._cleric(6, ["Strength"])
        assert "Feat of Strength" in c._buff_states
        assert not c._buff_states["Feat of Strength"].active
        assert c.get_ability_score("str") == 12

    def test_feat_of_strength_scales_with_cleric_level(self) -> None:
        c = self._cleric(6, ["Strength"])
        c.toggle_buff("Feat of Strength", True)
        assert c.get_ability_score("str") == 18  # 12 + 6

    def test_feat_of_strength_toggles_off(self) -> None:
        c = self._cleric(6, ["Strength"])
        c.toggle_buff("Feat of Strength", True)
        c.toggle_buff("Feat of Strength", False)
        assert c.get_ability_score("str") == 12

    def test_protective_ward_covers_all_saves(self) -> None:
        c = self._cleric(4, ["Protection"])
        before = (c.fort, c.ref, c.will)
        c.toggle_buff("Protective Ward", True)
        assert (c.fort, c.ref, c.will) == tuple(x + 4 for x in before)

    def test_buff_absent_without_the_domain(self) -> None:
        c = self._cleric(6, ["War", "Luck"])
        assert "Feat of Strength" not in c._buff_states
        assert "Protective Ward" not in c._buff_states

    def test_resource_without_effects_registers_no_buff(self) -> None:
        """Luck has a daily limit but no expressible bonus."""
        c = self._cleric(6, ["Luck"])
        assert "Reroll" in c.resources
        assert "Reroll" not in c._buff_states
