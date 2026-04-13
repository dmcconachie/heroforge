"""
tests/test_templates.py
-----------------------
Test suite for engine/templates.py and rules/core/templates.yaml.

Covers:
  - TemplateDefinition construction
  - TemplateRegistry: register, get, require, overwrite
  - build_template_from_yaml() for all fields
  - apply_template(): ability score bonuses, natural armor, type changes,
    subtype changes, feat grants, idempotence
  - remove_template(): full revert
  - Partial templates: level scaling
  - Multiple template stacking
  - effective_type() / effective_subtypes()
  - TemplatesLoader: YAML validation, registration, error paths
  - Prerequisites integration: creature type after template
    affects prereq checks
"""

from __future__ import annotations

from pathlib import Path

import pytest

from heroforge.engine.bonus import BonusType
from heroforge.engine.character import Character
from heroforge.engine.prerequisites import (
    CreatureTypePrereq,
    PrerequisiteChecker,
)
from heroforge.engine.templates import (
    TemplateAbilityModifier,
    TemplateDefinition,
    TemplateRegistry,
    apply_template,
    build_template_from_yaml,
    effective_subtypes,
    effective_type,
    remove_template,
)

RULES_DIR = Path(__file__).parent.parent / "src" / "heroforge" / "rules"


# ===========================================================================
# Helpers
# ===========================================================================


def fresh_char(race: str = "Human") -> Character:
    c = Character()
    c.race = race
    return c


def half_celestial() -> TemplateDefinition:
    return TemplateDefinition(
        name="Half-Celestial",
        source_book="MM",
        cr_adjustment="+1",
        la_adjustment="+4",
        subtype_add=["Good", "Extraplanar"],
        ability_modifiers=[
            TemplateAbilityModifier("str", 4),
            TemplateAbilityModifier("dex", 2),
            TemplateAbilityModifier("con", 4),
            TemplateAbilityModifier("int", 2),
            TemplateAbilityModifier("wis", 4),
            TemplateAbilityModifier("cha", 4),
        ],
        natural_armor_bonus=1,
    )


def half_dragon() -> TemplateDefinition:
    return TemplateDefinition(
        name="Half-Dragon (Red)",
        source_book="MM",
        type_change="Dragon",
        ability_modifiers=[
            TemplateAbilityModifier("str", 8),
            TemplateAbilityModifier("con", 2),
            TemplateAbilityModifier("int", 2),
            TemplateAbilityModifier("cha", 2),
        ],
        natural_armor_bonus=4,
    )


def werewolf_template() -> TemplateDefinition:
    return TemplateDefinition(
        name="Lycanthrope (Werewolf)",
        source_book="MM",
        subtype_add=["Shapechanger"],
        ability_modifiers=[
            TemplateAbilityModifier("str", 2),
            TemplateAbilityModifier("con", 4),
            TemplateAbilityModifier("wis", 2),
        ],
        natural_armor_bonus=2,
        grants_feats=["Iron Will"],
    )


# ===========================================================================
# TemplateDefinition
# ===========================================================================


class TestTemplateDefinition:
    def test_construction_defaults(self) -> None:
        t = TemplateDefinition(name="Test")
        assert t.source_book == "MM"
        assert t.type_change is None
        assert t.subtype_add == []
        assert t.ability_modifiers == []
        assert t.natural_armor_bonus == 0

    def test_construction_full(self) -> None:
        t = half_celestial()
        assert t.name == "Half-Celestial"
        assert len(t.ability_modifiers) == 6
        assert t.natural_armor_bonus == 1
        assert "Good" in t.subtype_add

    def test_ability_modifier_default_untyped(self) -> None:
        m = TemplateAbilityModifier("str", 4)
        assert m.bonus_type == BonusType.UNTYPED


# ===========================================================================
# TemplateRegistry
# ===========================================================================


class TestTemplateRegistry:
    def test_register_and_get(self) -> None:
        reg = TemplateRegistry()
        t = half_celestial()
        reg.register(t)
        assert reg.get("Half-Celestial") is t

    def test_require_known(self) -> None:
        reg = TemplateRegistry()
        reg.register(half_celestial())
        assert reg.require("Half-Celestial").name == "Half-Celestial"

    def test_require_unknown_raises(self) -> None:
        reg = TemplateRegistry()
        with pytest.raises(KeyError, match="No TemplateDefinition"):
            reg.require("Ghost")

    def test_get_unknown_returns_none(self) -> None:
        reg = TemplateRegistry()
        assert reg.get("Unknown") is None

    def test_duplicate_raises(self) -> None:
        reg = TemplateRegistry()
        reg.register(half_celestial())
        with pytest.raises(ValueError, match="already registered"):
            reg.register(half_celestial())

    def test_overwrite_replaces(self) -> None:
        reg = TemplateRegistry()
        t1 = TemplateDefinition(name="Half-Celestial", la_adjustment="+4")
        t2 = TemplateDefinition(name="Half-Celestial", la_adjustment="+5")
        reg.register(t1)
        reg.register(t2, overwrite=True)
        assert reg.require("Half-Celestial").la_adjustment == "+5"

    def test_len(self) -> None:
        reg = TemplateRegistry()
        assert len(reg) == 0
        reg.register(half_celestial())
        reg.register(half_dragon())
        assert len(reg) == 2

    def test_contains(self) -> None:
        reg = TemplateRegistry()
        reg.register(half_celestial())
        assert "Half-Celestial" in reg
        assert "Vampire" not in reg

    def test_all_names_sorted(self) -> None:
        reg = TemplateRegistry()
        reg.register(half_dragon())
        reg.register(half_celestial())
        names = reg.all_names()
        assert names == sorted(names)


# ===========================================================================
# apply_template
# ===========================================================================


class TestApplyTemplate:
    def test_ability_bonuses_applied(self) -> None:
        c = fresh_char()
        c.set_ability_score("str", 14)
        t = half_celestial()
        apply_template(t, c)
        # str 14 + 4 = 18
        assert c.str_score == 18

    def test_all_six_ability_bonuses(self) -> None:
        c = fresh_char()
        for ab in ("str", "dex", "con", "int", "wis", "cha"):
            c.set_ability_score(ab, 10)

        t = half_celestial()
        apply_template(t, c)

        assert c.str_score == 14  # +4
        assert c.dex_score == 12  # +2
        assert c.con_score == 14  # +4
        assert c.int_score == 12  # +2
        assert c.wis_score == 14  # +4
        assert c.cha_score == 14  # +4

    def test_natural_armor_applied_to_ac(self) -> None:
        c = fresh_char()
        base_ac = c.ac
        # Use a template with only natural armor to isolate
        from heroforge.engine.templates import TemplateDefinition

        t = TemplateDefinition(
            name="Natural Only", natural_armor_bonus=3, ability_modifiers=[]
        )
        apply_template(t, c)
        assert c.ac == base_ac + 3

    def test_type_change_recorded(self) -> None:
        c = fresh_char("Human")
        apply_template(half_dragon(), c)
        assert effective_type(c) == "Dragon"

    def test_subtype_add_recorded(self) -> None:
        c = fresh_char()
        apply_template(half_celestial(), c)
        subs = effective_subtypes(c)
        assert "Good" in subs
        assert "Extraplanar" in subs

    def test_template_recorded_in_character_templates(self) -> None:
        c = fresh_char()
        apply_template(half_celestial(), c)
        assert len(c.templates) == 1
        assert c.templates[0].template_name == "Half-Celestial"

    def test_feats_granted(self) -> None:
        c = fresh_char()
        apply_template(werewolf_template(), c)
        feat_names = {f["name"] for f in c.feats}
        assert "Iron Will" in feat_names

    def test_feats_not_duplicated_on_re_apply(self) -> None:
        c = fresh_char()
        apply_template(werewolf_template(), c)
        apply_template(werewolf_template(), c)
        iron_will_count = sum(1 for f in c.feats if f["name"] == "Iron Will")
        assert iron_will_count == 1

    def test_apply_is_idempotent(self) -> None:
        """Applying same template twice gives same result as once."""
        c = fresh_char()
        c.set_ability_score("str", 10)
        t = half_celestial()
        apply_template(t, c)
        str_once = c.str_score
        apply_template(t, c)
        assert c.str_score == str_once  # no double-counting

    def test_apply_does_not_affect_unrelated_stats(self) -> None:
        c = fresh_char()
        c.set_ability_score("str", 10)
        # Half-Celestial doesn't change str_score wait it does, use Vampire
        # Vampire changes STR+6 but not INT directly
        from heroforge.engine.templates import (
            TemplateAbilityModifier,
            TemplateDefinition,
        )

        vampire_light = TemplateDefinition(
            name="Vampire Light",
            ability_modifiers=[TemplateAbilityModifier("str", 4)],
        )
        apply_template(vampire_light, c)
        # INT should be unchanged
        assert c.int_score == 10


# ===========================================================================
# remove_template
# ===========================================================================


class TestRemoveTemplate:
    def test_remove_reverts_ability_bonuses(self) -> None:
        c = fresh_char()
        for ab in ("str", "dex", "con", "int", "wis", "cha"):
            c.set_ability_score(ab, 10)

        t = half_celestial()
        apply_template(t, c)
        remove_template(t, c)

        for ab in ("str", "dex", "con", "int", "wis", "cha"):
            assert c.get_ability_score(ab) == 10, f"{ab} not reverted"

    def test_remove_reverts_natural_armor(self) -> None:
        c = fresh_char()
        base_ac = c.ac
        t = half_celestial()
        apply_template(t, c)
        remove_template(t, c)
        assert c.ac == base_ac

    def test_remove_reverts_type_change(self) -> None:
        c = fresh_char("Human")
        t = half_dragon()
        apply_template(t, c)
        assert effective_type(c) == "Dragon"
        remove_template(t, c)
        # No other templates → type override cleared
        assert effective_type(c) == "Humanoid"  # Human reverts to Humanoid

    def test_remove_reverts_subtypes(self) -> None:
        c = fresh_char()
        t = half_celestial()
        apply_template(t, c)
        remove_template(t, c)
        subs = effective_subtypes(c)
        assert "Good" not in subs
        assert "Extraplanar" not in subs

    def test_remove_removes_granted_feats(self) -> None:
        c = fresh_char()
        t = werewolf_template()
        apply_template(t, c)
        remove_template(t, c)
        feat_names = {f["name"] for f in c.feats}
        assert "Iron Will" not in feat_names

    def test_remove_updates_templates_list(self) -> None:
        c = fresh_char()
        t = half_celestial()
        apply_template(t, c)
        remove_template(t, c)
        assert len(c.templates) == 0

    def test_remove_not_applied_is_noop(self) -> None:
        c = fresh_char()
        t = half_celestial()
        # Not applied — should not raise
        remove_template(t, c)
        assert c.str_score == 10


# ===========================================================================
# Multiple templates
# ===========================================================================


class TestMultipleTemplates:
    def test_two_templates_both_apply(self) -> None:
        """Half-Celestial + Feral template stacked."""
        c = fresh_char()
        for ab in ("str", "dex", "con", "int", "wis", "cha"):
            c.set_ability_score(ab, 10)

        hc = half_celestial()  # str+4, dex+2, con+4, int+2, wis+4, cha+4
        feral = TemplateDefinition(
            name="Feral",
            ability_modifiers=[
                TemplateAbilityModifier("str", 4),
                TemplateAbilityModifier("dex", 4),
                TemplateAbilityModifier("con", 2),
                TemplateAbilityModifier("int", -2),
            ],
            natural_armor_bonus=2,
        )

        apply_template(hc, c)
        apply_template(feral, c)

        # Both are untyped and go into the same pool — they should SUM
        # since untyped bonuses stack
        assert c.str_score == 18  # 10 + 4 (HC) + 4 (Feral)
        assert c.dex_score == 16  # 10 + 2 (HC) + 4 (Feral)
        assert c.int_score == 10  # 10 + 2 (HC) - 2 (Feral) = 10

    def test_two_templates_in_character_templates_list(self) -> None:
        c = fresh_char()
        apply_template(half_celestial(), c)
        apply_template(half_dragon(), c)
        assert len(c.templates) == 2
        names = {a.template_name for a in c.templates}
        assert "Half-Celestial" in names
        assert "Half-Dragon (Red)" in names

    def test_last_type_change_wins(self) -> None:
        """Half-Dragon changes type to Dragon; it's the last applied."""
        c = fresh_char("Human")
        apply_template(half_celestial(), c)  # no type change
        apply_template(half_dragon(), c)  # Dragon
        assert effective_type(c) == "Dragon"

    def test_subtypes_accumulate(self) -> None:
        c = fresh_char()
        hc = half_celestial()  # adds Good, Extraplanar

        hf = TemplateDefinition(
            name="Half-Fiend",
            subtype_add=["Evil", "Extraplanar"],  # Extraplanar again — no dup
        )
        apply_template(hc, c)
        apply_template(hf, c)
        subs = effective_subtypes(c)
        assert "Good" in subs
        assert "Evil" in subs
        assert subs.count("Extraplanar") == 1  # no duplicate


# ===========================================================================
# effective_type / effective_subtypes
# ===========================================================================


class TestEffectiveType:
    def test_human_default_humanoid(self) -> None:
        c = fresh_char("Human")
        assert effective_type(c) == "Humanoid"

    def test_tiefling_outsider(self) -> None:
        c = fresh_char("Tiefling")
        assert effective_type(c) == "Outsider"

    def test_warforged_construct(self) -> None:
        c = fresh_char("Warforged")
        assert effective_type(c) == "Construct"

    def test_half_dragon_overrides_to_dragon(self) -> None:
        c = fresh_char("Human")
        apply_template(half_dragon(), c)
        assert effective_type(c) == "Dragon"

    def test_subtypes_empty_for_plain_human(self) -> None:
        c = fresh_char("Human")
        subs = effective_subtypes(c)
        assert "Human" in subs  # racial subtype

    def test_subtypes_include_template_additions(self) -> None:
        c = fresh_char("Human")
        apply_template(half_celestial(), c)
        subs = effective_subtypes(c)
        assert "Good" in subs
        assert "Extraplanar" in subs


# ===========================================================================
# Integration with prerequisite checking
# ===========================================================================


class TestTemplatePrereqIntegration:
    def test_dragon_type_opens_dragon_gated_feats(self) -> None:
        """
        After Half-Dragon template, creature type is Dragon.
        A feat requiring Dragon type should now be available.
        """
        chk = PrerequisiteChecker()
        chk.register_feat("Draconic Heritage", CreatureTypePrereq(["Dragon"]))

        c = fresh_char("Human")
        avail_before, _ = chk.feat_availability("Draconic Heritage", c)
        from heroforge.engine.prerequisites import FeatAvailability

        assert avail_before == FeatAvailability.UNAVAILABLE

        apply_template(half_dragon(), c)

        avail_after, _ = chk.feat_availability("Draconic Heritage", c)
        assert avail_after == FeatAvailability.AVAILABLE

    def test_humanoid_type_feat_unavail_after_half_dragon(
        self,
    ) -> None:
        """
        Enlarge Person requires Humanoid type.
        After Half-Dragon (→ Dragon), it should be unavailable.
        """
        chk = PrerequisiteChecker()
        chk.register_feat(
            "Enlarge Person Compatible", CreatureTypePrereq(["Humanoid"])
        )

        c = fresh_char("Human")
        avail_before, _ = chk.feat_availability("Enlarge Person Compatible", c)
        from heroforge.engine.prerequisites import FeatAvailability

        assert avail_before == FeatAvailability.AVAILABLE

        apply_template(half_dragon(), c)
        avail_after, _ = chk.feat_availability("Enlarge Person Compatible", c)
        assert avail_after == FeatAvailability.UNAVAILABLE


# ===========================================================================
# build_template_from_yaml
# ===========================================================================


class TestBuildTemplateFromYaml:
    def test_basic_fields(self) -> None:
        t = build_template_from_yaml(
            {
                "name": "Test Template",
                "source_book": "MM",
                "cr_adjustment": "+1",
                "la_adjustment": "+2",
                "ability_modifiers": [],
            }
        )
        assert t.name == "Test Template"
        assert t.cr_adjustment == "+1"
        assert t.la_adjustment == "+2"

    def test_ability_modifiers(self) -> None:
        t = build_template_from_yaml(
            {
                "name": "Test",
                "ability_modifiers": [
                    {"ability": "str", "value": 4, "bonus_type": "untyped"},
                    {"ability": "dex", "value": 2, "bonus_type": "enhancement"},
                ],
            }
        )
        assert len(t.ability_modifiers) == 2
        assert t.ability_modifiers[0].ability == "str"
        assert t.ability_modifiers[0].value == 4
        assert t.ability_modifiers[1].bonus_type == BonusType.ENHANCEMENT

    def test_type_change(self) -> None:
        t = build_template_from_yaml(
            {
                "name": "Half-Dragon",
                "type_change": "Dragon",
                "ability_modifiers": [],
            }
        )
        assert t.type_change == "Dragon"

    def test_subtype_add(self) -> None:
        t = build_template_from_yaml(
            {
                "name": "Test",
                "subtype_add": ["Good", "Extraplanar"],
                "ability_modifiers": [],
            }
        )
        assert "Good" in t.subtype_add
        assert "Extraplanar" in t.subtype_add

    def test_grants_feats(self) -> None:
        t = build_template_from_yaml(
            {
                "name": "Vampire",
                "grants_feats": ["Alertness", "Dodge"],
                "ability_modifiers": [],
            }
        )
        assert "Alertness" in t.grants_feats

    def test_unknown_bonus_type_defaults_untyped(self) -> None:
        t = build_template_from_yaml(
            {
                "name": "Test",
                "ability_modifiers": [
                    {
                        "ability": "str",
                        "value": 2,
                        "bonus_type": "totally_unknown",
                    }
                ],
            }
        )
        assert t.ability_modifiers[0].bonus_type == BonusType.UNTYPED


# ===========================================================================
# TemplatesLoader
# ===========================================================================


class TestTemplatesLoader:
    from heroforge.rules.loader import TemplatesLoader

    def test_load_registers_all_templates(self) -> None:
        import yaml

        from heroforge.engine.templates import TemplateRegistry
        from heroforge.rules.loader import TemplatesLoader

        with open(RULES_DIR / "core" / "templates.yaml") as f:
            data = yaml.safe_load(f)
        expected_count = len(data)

        reg = TemplateRegistry()
        TemplatesLoader(RULES_DIR).load(reg, "core/templates.yaml")
        assert len(reg) == expected_count

    def test_load_returns_registered_names(self) -> None:
        from heroforge.engine.templates import TemplateRegistry
        from heroforge.rules.loader import TemplatesLoader

        reg = TemplateRegistry()
        names = TemplatesLoader(RULES_DIR).load(reg, "core/templates.yaml")
        assert "Half-Celestial" in names
        assert "Half-Dragon (Red)" in names
        assert "Vampire" in names

    def test_half_celestial_ability_mods_loaded(self) -> None:
        from heroforge.engine.templates import TemplateRegistry
        from heroforge.rules.loader import TemplatesLoader

        reg = TemplateRegistry()
        TemplatesLoader(RULES_DIR).load(reg, "core/templates.yaml")
        hc = reg.require("Half-Celestial")
        abilities = {m.ability: m.value for m in hc.ability_modifiers}
        assert abilities["str"] == 4
        assert abilities["cha"] == 4

    def test_half_dragon_type_change_loaded(self) -> None:
        from heroforge.engine.templates import TemplateRegistry
        from heroforge.rules.loader import TemplatesLoader

        reg = TemplateRegistry()
        TemplatesLoader(RULES_DIR).load(reg, "core/templates.yaml")
        hd = reg.require("Half-Dragon (Red)")
        assert hd.type_change == "Dragon"

    def test_vampire_grants_feats(self) -> None:
        from heroforge.engine.templates import TemplateRegistry
        from heroforge.rules.loader import TemplatesLoader

        reg = TemplateRegistry()
        TemplatesLoader(RULES_DIR).load(reg, "core/templates.yaml")
        vamp = reg.require("Vampire")
        assert "Alertness" in vamp.grants_feats
        assert "Dodge" in vamp.grants_feats

    def test_load_missing_file_raises(self, tmp_path: Path) -> None:
        from heroforge.engine.templates import TemplateRegistry
        from heroforge.rules.loader import LoaderError, TemplatesLoader

        with pytest.raises(LoaderError, match="not found"):
            TemplatesLoader(tmp_path).load(
                TemplateRegistry(), "core/templates.yaml"
            )

    def test_load_raises_on_bad_yaml(self, tmp_path: Path) -> None:
        from heroforge.engine.templates import (
            TemplateRegistry,
        )
        from heroforge.rules.loader import (
            LoaderError,
            TemplatesLoader,
        )

        core = tmp_path / "core"
        core.mkdir()
        (core / "templates.yaml").write_text("- a list\n")
        with pytest.raises(LoaderError, match="YAML mapping"):
            TemplatesLoader(tmp_path).load(
                TemplateRegistry(),
                "core/templates.yaml",
            )

    def test_no_duplicate_names_in_yaml(self) -> None:
        import yaml

        with open(RULES_DIR / "core" / "templates.yaml") as f:
            data = yaml.safe_load(f)
        names = [d["name"] for d in data if "name" in d]
        assert len(names) == len(set(names)), (
            "Duplicate template names: "
            f"{[n for n in names if names.count(n) > 1]}"
        )

    def test_loaded_template_applied_to_character(self) -> None:
        """End-to-end: load Half-Celestial from YAML and apply to character."""
        from heroforge.engine.templates import TemplateRegistry
        from heroforge.rules.loader import TemplatesLoader

        reg = TemplateRegistry()
        TemplatesLoader(RULES_DIR).load(reg, "core/templates.yaml")

        c = fresh_char("Human")
        c.set_ability_score("str", 14)
        hc = reg.require("Half-Celestial")
        apply_template(hc, c)

        assert c.str_score == 18  # 14 + 4
        # Half-Celestial: natural armor +1 AND dex +2 (10→12, mod 0→1) → AC 12
        assert c.ac == 12
        assert "Good" in effective_subtypes(c)
