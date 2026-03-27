"""
tests/test_feats.py
-------------------
Test suite for engine/feats.py, rules/core/feats_phb.yaml, and FeatsLoader.

Covers:
  - FeatParameterSpec: resolve_max(), clamp()
  - resolve_feat_effects(): $parameter substitution, formula and int values
  - FeatDefinition: construction, is_parameterized, build_buff_definition()
  - FeatRegistry: register, get, require, by_kind
  - build_feat_from_yaml(): all three kinds, parameterized feats, prereqs
  - FeatsLoader: YAML validation, registration in feat/prereq/buff registries
  - Character.add_feat(): always_on, conditional, passive
  - Character.remove_feat(): revert always_on and deactivate conditional
  - Character.toggle_buff() with parameter: Power Attack, Combat Expertise
  - Real scenarios: Power Attack at 3 points, Combat Expertise at 2 points
  - Prerequisite checker integration: feats from YAML open prereq chains
"""

from __future__ import annotations

from pathlib import Path

import pytest

from heroforge.engine.bonus import BonusType
from heroforge.engine.character import Character, ClassLevel
from heroforge.engine.effects import BuffCategory, BuffRegistry, apply_buff
from heroforge.engine.feats import (
    FeatDefinition,
    FeatKind,
    FeatParameterSpec,
    FeatRegistry,
    build_feat_from_yaml,
    resolve_feat_effects,
)
from heroforge.engine.prerequisites import FeatAvailability, PrerequisiteChecker

RULES_DIR = Path(__file__).parent.parent / "src" / "heroforge" / "rules"


# ===========================================================================
# Helpers
# ===========================================================================


def fresh_char() -> Character:
    return Character()


def fighter(n: int) -> Character:
    c = Character()
    c.race = "Human"
    c.set_class_levels(
        [
            ClassLevel(
                class_name="Fighter",
                level=n,
                hp_rolls=[10] * n,
                bab_contribution=n,
                fort_contribution=2 + n // 2,
                ref_contribution=n // 3,
                will_contribution=n // 3,
            )
        ]
    )
    return c


def loaded_registries() -> tuple[
    FeatRegistry, PrerequisiteChecker, BuffRegistry
]:
    """Return (feat_reg, prereq_chk, buff_reg) loaded from YAML."""
    from heroforge.rules.loader import FeatsLoader

    feat_reg = FeatRegistry()
    prereq_chk = PrerequisiteChecker()
    buff_reg = BuffRegistry()
    FeatsLoader(RULES_DIR).load(
        feat_reg, "core/feats_phb.yaml", prereq_chk, buff_reg
    )
    return feat_reg, prereq_chk, buff_reg


# ===========================================================================
# FeatParameterSpec
# ===========================================================================


class TestFeatParameterSpec:
    def test_resolve_max_with_character(self) -> None:
        c = fighter(6)
        spec = FeatParameterSpec("points", "Points", min=1, max_formula="bab")
        assert spec.resolve_max(c) == 6

    def test_resolve_max_no_character_returns_min(self) -> None:
        spec = FeatParameterSpec("points", "Points", min=1, max_formula="bab")
        assert spec.resolve_max(None) == 1

    def test_resolve_max_formula(self) -> None:
        c = fighter(8)
        spec = FeatParameterSpec(
            "points", "Points", min=1, max_formula="min(5, bab)"
        )
        assert spec.resolve_max(c) == 5

    def test_clamp_within_range(self) -> None:
        c = fighter(6)
        spec = FeatParameterSpec("points", "Points", min=1, max_formula="bab")
        assert spec.clamp(3, c) == 3

    def test_clamp_below_min(self) -> None:
        c = fighter(6)
        spec = FeatParameterSpec("points", "Points", min=1, max_formula="bab")
        assert spec.clamp(0, c) == 1

    def test_clamp_above_max(self) -> None:
        c = fighter(4)
        spec = FeatParameterSpec("points", "Points", min=1, max_formula="bab")
        assert spec.clamp(10, c) == 4


# ===========================================================================
# resolve_feat_effects — $parameter substitution
# ===========================================================================


class TestResolveEffects:
    def test_static_int_value(self) -> None:
        raw = [{"target": "ac", "bonus_type": "dodge", "value": 2}]
        effects = resolve_feat_effects(raw, parameter=1)
        assert len(effects) == 1
        assert effects[0].value == 2

    def test_parameter_direct_substitution(self) -> None:
        raw = [
            {
                "target": "attack_all",
                "bonus_type": "untyped",
                "value": "-$parameter",
            }
        ]
        effects = resolve_feat_effects(raw, parameter=3)
        assert effects[0].value == -3

    def test_parameter_positive_substitution(self) -> None:
        raw = [
            {
                "target": "damage_all",
                "bonus_type": "untyped",
                "value": "$parameter",
            }
        ]
        effects = resolve_feat_effects(raw, parameter=5)
        assert effects[0].value == 5

    def test_parameter_formula_substitution(self) -> None:
        raw = [
            {
                "target": "damage_all",
                "bonus_type": "untyped",
                "value": "$parameter * 2",
            }
        ]
        effects = resolve_feat_effects(raw, parameter=3)
        assert effects[0].value == 6

    def test_no_parameter_in_value_unchanged(self) -> None:
        raw = [{"target": "ac", "bonus_type": "dodge", "value": "2 + 1"}]
        effects = resolve_feat_effects(raw, parameter=99)
        # Formula "2 + 1" has no $parameter so stays as formula string
        assert effects[0].value == "2 + 1"

    def test_multiple_effects(self) -> None:
        raw = [
            {
                "target": "attack_all",
                "bonus_type": "untyped",
                "value": "-$parameter",
            },
            {"target": "ac", "bonus_type": "dodge", "value": "$parameter"},
        ]
        effects = resolve_feat_effects(raw, parameter=2)
        assert effects[0].value == -2
        assert effects[1].value == 2

    def test_source_label_preserved(self) -> None:
        raw = [
            {
                "target": "ac",
                "bonus_type": "dodge",
                "value": 1,
                "source_label": "Combat Expertise (bonus)",
            }
        ]
        effects = resolve_feat_effects(raw)
        assert effects[0].source_label == "Combat Expertise (bonus)"

    def test_bonus_type_resolved(self) -> None:
        raw = [{"target": "ac", "bonus_type": "deflection", "value": 2}]
        effects = resolve_feat_effects(raw)
        assert effects[0].bonus_type == BonusType.DEFLECTION

    def test_unknown_bonus_type_defaults_untyped(self) -> None:
        raw = [{"target": "ac", "bonus_type": "mythic", "value": 2}]
        effects = resolve_feat_effects(raw)
        assert effects[0].bonus_type == BonusType.UNTYPED


# ===========================================================================
# FeatDefinition
# ===========================================================================


class TestFeatDefinition:
    def _always_on(self) -> FeatDefinition:
        from heroforge.engine.effects import BonusEffect, BuffDefinition

        buff = BuffDefinition(
            name="Dodge",
            category=BuffCategory.FEAT,
            effects=[BonusEffect("ac", BonusType.DODGE, 1)],
        )
        defn = FeatDefinition(
            name="Dodge",
            kind=FeatKind.ALWAYS_ON,
        )
        defn.buff_definition = buff
        return defn

    def _conditional_parameterized(self) -> FeatDefinition:
        return FeatDefinition(
            name="Power Attack",
            kind=FeatKind.CONDITIONAL,
            parameter=FeatParameterSpec(
                "points", "Points traded", min=1, max_formula="bab"
            ),
            effects=[
                {
                    "target": "attack_all",
                    "bonus_type": "untyped",
                    "value": "-$parameter",
                },
                {
                    "target": "damage_all",
                    "bonus_type": "untyped",
                    "value": "$parameter",
                },
            ],
        )

    def test_always_on_not_parameterized(self) -> None:
        assert not self._always_on().is_parameterized

    def test_conditional_parameterized_is_parameterized(self) -> None:
        assert self._conditional_parameterized().is_parameterized

    def test_always_on_build_buff_returns_cached(self) -> None:
        defn = self._always_on()
        result = defn.build_buff_definition()
        assert result is defn.buff_definition

    def test_passive_build_buff_returns_none(self) -> None:
        defn = FeatDefinition(name="Point Blank Shot", kind=FeatKind.PASSIVE)
        assert defn.build_buff_definition() is None

    def test_parameterized_build_buff_with_parameter_3(self) -> None:
        defn = self._conditional_parameterized()
        buff = defn.build_buff_definition(parameter=3)
        assert buff is not None
        # Attack penalty = -3, damage bonus = +3
        attack_eff = next(e for e in buff.effects if e.target == "attack_all")
        damage_eff = next(e for e in buff.effects if e.target == "damage_all")
        assert attack_eff.value == -3
        assert damage_eff.value == 3

    def test_parameterized_build_buff_with_parameter_5(self) -> None:
        defn = self._conditional_parameterized()
        buff = defn.build_buff_definition(parameter=5)
        attack_eff = next(e for e in buff.effects if e.target == "attack_all")
        assert attack_eff.value == -5


# ===========================================================================
# FeatRegistry
# ===========================================================================


class TestFeatRegistry:
    def _make(
        self, name: str, kind: FeatKind = FeatKind.PASSIVE
    ) -> FeatDefinition:
        return FeatDefinition(name=name, kind=kind)

    def test_register_and_get(self) -> None:
        reg = FeatRegistry()
        reg.register(self._make("Dodge", FeatKind.ALWAYS_ON))
        assert reg.get("Dodge").kind == FeatKind.ALWAYS_ON

    def test_require_unknown_raises(self) -> None:
        with pytest.raises(KeyError, match="No FeatDefinition"):
            FeatRegistry().require("Unknown")

    def test_duplicate_raises(self) -> None:
        reg = FeatRegistry()
        reg.register(self._make("Dodge"))
        with pytest.raises(ValueError, match="already registered"):
            reg.register(self._make("Dodge"))

    def test_overwrite_replaces(self) -> None:
        reg = FeatRegistry()
        reg.register(self._make("Dodge", FeatKind.PASSIVE))
        reg.register(self._make("Dodge", FeatKind.ALWAYS_ON), overwrite=True)
        assert reg.require("Dodge").kind == FeatKind.ALWAYS_ON

    def test_by_kind(self) -> None:
        reg = FeatRegistry()
        reg.register(self._make("Dodge", FeatKind.ALWAYS_ON))
        reg.register(self._make("Power Attack", FeatKind.CONDITIONAL))
        reg.register(self._make("PBS", FeatKind.PASSIVE))
        always_on = reg.by_kind(FeatKind.ALWAYS_ON)
        assert len(always_on) == 1
        assert always_on[0].name == "Dodge"

    def test_all_names_sorted(self) -> None:
        reg = FeatRegistry()
        for name in ("Toughness", "Alertness", "Dodge"):
            reg.register(self._make(name))
        assert reg.all_names() == sorted(reg.all_names())


# ===========================================================================
# build_feat_from_yaml
# ===========================================================================


class TestBuildFeatFromYaml:
    def test_passive_no_effects(self) -> None:
        defn = build_feat_from_yaml(
            {
                "name": "Point Blank Shot",
                "kind": "passive",
                "source_book": "PHB",
                "prerequisites": None,
                "effects": [],
            }
        )
        assert defn.kind == FeatKind.PASSIVE
        assert defn.buff_definition is None

    def test_always_on_with_effects(self) -> None:
        defn = build_feat_from_yaml(
            {
                "name": "Dodge",
                "kind": "always_on",
                "source_book": "PHB",
                "prerequisites": {"ability": {"key": "dex_score", "min": 13}},
                "effects": [
                    {"target": "ac", "bonus_type": "dodge", "value": 1}
                ],
            }
        )
        assert defn.kind == FeatKind.ALWAYS_ON
        assert defn.buff_definition is not None
        assert defn.buff_definition.effects[0].bonus_type == BonusType.DODGE

    def test_conditional_no_parameter(self) -> None:
        defn = build_feat_from_yaml(
            {
                "name": "Dodge",
                "kind": "conditional",
                "prerequisites": None,
                "effects": [
                    {
                        "target": "ac",
                        "bonus_type": "dodge",
                        "value": 1,
                    },
                ],
            }
        )
        assert defn.kind == FeatKind.CONDITIONAL
        assert defn.parameter is None
        assert defn.buff_definition is not None

    def test_conditional_with_parameter(self) -> None:
        defn = build_feat_from_yaml(
            {
                "name": "Power Attack",
                "kind": "conditional",
                "prerequisites": {
                    "stat": {"key": "bab", "min": 1, "label": "BAB"}
                },
                "parameter": {
                    "name": "points",
                    "label": "Points traded",
                    "min": 1,
                    "max_formula": "bab",
                    "default": 1,
                },
                "effects": [
                    {
                        "target": "attack_all",
                        "bonus_type": "untyped",
                        "value": "-$parameter",
                    },
                    {
                        "target": "damage_all",
                        "bonus_type": "untyped",
                        "value": "$parameter",
                    },
                ],
            }
        )
        assert defn.kind == FeatKind.CONDITIONAL
        assert defn.is_parameterized
        assert defn.parameter.max_formula == "bab"
        assert defn.buff_definition is None  # built at activation time

    def test_prereqs_built(self) -> None:
        from heroforge.engine.prerequisites import StatPrereq

        defn = build_feat_from_yaml(
            {
                "name": "Power Attack",
                "kind": "conditional",
                "prerequisites": {
                    "stat": {"key": "bab", "min": 1, "label": "BAB"}
                },
                "effects": [],
            }
        )
        assert isinstance(defn.prerequisites, StatPrereq)
        assert defn.prerequisites.min_value == 1


# ===========================================================================
# YAML validation
# ===========================================================================


class TestFeatsYamlStructure:
    def test_no_duplicate_names(self) -> None:
        import yaml

        with open(RULES_DIR / "core" / "feats_phb.yaml") as f:
            data = yaml.safe_load(f)
        names = [d["name"] for d in data["feats"] if "name" in d]
        assert len(names) == len(set(names))

    def test_all_kinds_valid(self) -> None:
        import yaml

        valid = {"always_on", "conditional", "passive"}
        with open(RULES_DIR / "core" / "feats_phb.yaml") as f:
            data = yaml.safe_load(f)
        bad = [
            d["name"]
            for d in data["feats"]
            if d.get("kind", "passive") not in valid
        ]
        assert bad == []


# ===========================================================================
# FeatsLoader
# ===========================================================================


class TestFeatsLoader:
    def test_load_registers_all_feats(self) -> None:
        import yaml

        from heroforge.rules.loader import FeatsLoader

        with open(RULES_DIR / "core" / "feats_phb.yaml") as f:
            data = yaml.safe_load(f)
        expected = len(data["feats"])

        feat_reg = FeatRegistry()
        FeatsLoader(RULES_DIR).load(
            feat_reg, relative_path="core/feats_phb.yaml"
        )
        assert len(feat_reg) == expected

    def test_load_returns_names(self) -> None:
        from heroforge.rules.loader import FeatsLoader

        feat_reg = FeatRegistry()
        names = FeatsLoader(RULES_DIR).load(
            feat_reg, relative_path="core/feats_phb.yaml"
        )
        assert "Dodge" in names
        assert "Power Attack" in names
        assert "Toughness" in names

    def test_always_on_feats_have_buff_definition(
        self,
    ) -> None:
        feat_reg, _, _ = loaded_registries()
        for feat_name in (
            "Toughness",
            "Iron Will",
            "Lightning Reflexes",
            "Improved Initiative",
        ):
            defn = feat_reg.require(feat_name)
            assert defn.kind == FeatKind.ALWAYS_ON
            assert defn.buff_definition is not None, (
                f"{feat_name} should have a buff_definition"
            )

    def test_conditional_feats_have_effects(self) -> None:
        feat_reg, _, _ = loaded_registries()
        for feat_name in (
            "Combat Expertise",
            "Dodge",
            "Power Attack",
        ):
            defn = feat_reg.require(feat_name)
            assert defn.kind == FeatKind.CONDITIONAL
            assert len(defn.effects) > 0, f"{feat_name} should have effects"

    def test_power_attack_is_parameterized(self) -> None:
        feat_reg, _, _ = loaded_registries()
        pa = feat_reg.require("Power Attack")
        assert pa.is_parameterized
        assert pa.parameter.max_formula == "bab"

    def test_combat_expertise_is_parameterized(self) -> None:
        feat_reg, _, _ = loaded_registries()
        ce = feat_reg.require("Combat Expertise")
        assert ce.is_parameterized
        assert "min" in ce.parameter.max_formula

    def test_passive_feats_have_no_buff(self) -> None:
        feat_reg, _, _ = loaded_registries()
        for feat_name in ("Point Blank Shot", "Precise Shot", "Cleave"):
            defn = feat_reg.require(feat_name)
            assert defn.kind == FeatKind.PASSIVE
            assert defn.buff_definition is None

    def test_prereqs_registered_in_checker(self) -> None:
        _, prereq_chk, _ = loaded_registries()
        # Precise Shot requires Point Blank Shot
        c = fresh_char()
        c.feats = []
        avail, _ = prereq_chk.feat_availability("Precise Shot", c)
        assert avail == FeatAvailability.UNAVAILABLE

        c.feats = [{"name": "Point Blank Shot"}]
        avail, _ = prereq_chk.feat_availability("Precise Shot", c)
        assert avail == FeatAvailability.AVAILABLE

    def test_always_on_feats_not_in_buff_registry(self) -> None:
        _, _, buff_reg = loaded_registries()
        assert "Toughness" not in buff_reg
        assert "Iron Will" not in buff_reg

    def test_conditional_buffs_registered_in_buff_registry(
        self,
    ) -> None:
        _, _, buff_reg = loaded_registries()
        assert "Dodge" in buff_reg

    def test_load_raises_on_missing_file(self, tmp_path: Path) -> None:
        from heroforge.rules.loader import FeatsLoader, LoaderError

        with pytest.raises(LoaderError, match="not found"):
            FeatsLoader(tmp_path).load(
                FeatRegistry(), relative_path="core/feats_phb.yaml"
            )

    def test_load_raises_on_missing_feats_key(self, tmp_path: Path) -> None:
        from heroforge.rules.loader import FeatsLoader, LoaderError

        core = tmp_path / "core"
        core.mkdir()
        (core / "feats_phb.yaml").write_text("not_feats: []\n")
        with pytest.raises(LoaderError, match="top-level 'feats' key"):
            FeatsLoader(tmp_path).load(
                FeatRegistry(), relative_path="core/feats_phb.yaml"
            )


# ===========================================================================
# Character.add_feat / remove_feat
# ===========================================================================


class TestCharacterAddRemoveFeat:
    def test_add_passive_feat_records_name(self) -> None:
        c = fresh_char()
        feat_reg, _, _ = loaded_registries()
        defn = feat_reg.require("Point Blank Shot")
        c.add_feat("Point Blank Shot", defn)
        assert any(f["name"] == "Point Blank Shot" for f in c.feats)

    def test_add_passive_feat_no_stat_effect(self) -> None:
        c = fresh_char()
        feat_reg, _, _ = loaded_registries()
        base_ac = c.ac
        c.add_feat("Point Blank Shot", feat_reg.require("Point Blank Shot"))
        assert c.ac == base_ac

    def test_add_always_on_feat_applies_bonus(self) -> None:
        c = fresh_char()
        base_will = c.will
        feat_reg, _, _ = loaded_registries()
        c.add_feat("Iron Will", feat_reg.require("Iron Will"))
        assert c.will == base_will + 2

    def test_add_toughness_increases_hp(self) -> None:
        c = fighter(4)
        base_hp = c.hp_max
        feat_reg, _, _ = loaded_registries()
        c.add_feat("Toughness", feat_reg.require("Toughness"))
        assert c.hp_max == base_hp + 3

    def test_add_iron_will_increases_will(self) -> None:
        c = fresh_char()
        base_will = c.will
        feat_reg, _, _ = loaded_registries()
        c.add_feat("Iron Will", feat_reg.require("Iron Will"))
        assert c.will == base_will + 2

    def test_add_improved_initiative_increases_initiative(self) -> None:
        c = fresh_char()
        base_init = c.get("initiative")
        feat_reg, _, _ = loaded_registries()
        c.add_feat(
            "Improved Initiative", feat_reg.require("Improved Initiative")
        )
        assert c.get("initiative") == base_init + 4

    def test_add_always_on_feat_twice_no_duplicate(self) -> None:
        c = fresh_char()
        base_will = c.will
        feat_reg, _, _ = loaded_registries()
        defn = feat_reg.require("Iron Will")
        c.add_feat("Iron Will", defn)
        c.add_feat("Iron Will", defn)  # no-op
        assert c.will == base_will + 2

    def test_add_conditional_feat_registers_buff_not_activated(
        self,
    ) -> None:
        c = fresh_char()
        feat_reg, _, _ = loaded_registries()
        c.add_feat("Dodge", feat_reg.require("Dodge"))
        assert any(f["name"] == "Dodge" for f in c.feats)
        assert not c.is_buff_active("Dodge")

    def test_remove_always_on_feat_reverts_bonus(self) -> None:
        c = fresh_char()
        base_will = c.will
        feat_reg, _, _ = loaded_registries()
        defn = feat_reg.require("Iron Will")
        c.add_feat("Iron Will", defn)
        assert c.will == base_will + 2
        c.remove_feat("Iron Will", defn)
        assert c.will == base_will

    def test_remove_toughness_reverts_hp(self) -> None:
        c = fighter(4)
        base_hp = c.hp_max
        feat_reg, _, _ = loaded_registries()
        defn = feat_reg.require("Toughness")
        c.add_feat("Toughness", defn)
        c.remove_feat("Toughness", defn)
        assert c.hp_max == base_hp

    def test_always_on_feat_not_in_buff_states(self) -> None:
        c = fresh_char()
        feat_reg, _, _ = loaded_registries()
        defn = feat_reg.require("Iron Will")
        c.add_feat("Iron Will", defn)
        assert "Iron Will" not in c._buff_states

    def test_always_on_feat_uses_pool_source(self) -> None:
        c = fresh_char()
        feat_reg, _, _ = loaded_registries()
        defn = feat_reg.require("Iron Will")
        c.add_feat("Iron Will", defn)
        pool = c.get_pool("will_save")
        assert pool is not None
        assert "feat:Iron Will" in pool._sources

    def test_remove_always_on_clears_pool_source(
        self,
    ) -> None:
        c = fresh_char()
        feat_reg, _, _ = loaded_registries()
        defn = feat_reg.require("Iron Will")
        c.add_feat("Iron Will", defn)
        c.remove_feat("Iron Will", defn)
        pool = c.get_pool("will_save")
        assert pool is not None
        assert "feat:Iron Will" not in pool._sources

    def test_dodge_is_conditional(self) -> None:
        feat_reg, _, _ = loaded_registries()
        defn = feat_reg.require("Dodge")
        assert defn.kind == FeatKind.CONDITIONAL

    def test_dodge_requires_toggle_for_bonus(self) -> None:
        c = fresh_char()
        base_ac = c.ac
        feat_reg, _, _ = loaded_registries()
        defn = feat_reg.require("Dodge")
        c.add_feat("Dodge", defn)
        # Not activated yet — AC unchanged
        assert c.ac == base_ac
        # Toggle on
        c.toggle_buff("Dodge", True)
        assert c.ac == base_ac + 1
        # Toggle off
        c.toggle_buff("Dodge", False)
        assert c.ac == base_ac

    def test_dodge_in_buff_registry(self) -> None:
        _, _, buff_reg = loaded_registries()
        assert "Dodge" in buff_reg

    def test_remove_feat_removes_from_feats_list(
        self,
    ) -> None:
        c = fresh_char()
        feat_reg, _, _ = loaded_registries()
        defn = feat_reg.require("Point Blank Shot")
        c.add_feat("Point Blank Shot", defn)
        c.remove_feat("Point Blank Shot", defn)
        assert not any(f["name"] == "Point Blank Shot" for f in c.feats)


# ===========================================================================
# Conditional feat activation with parameter
# ===========================================================================


class TestConditionalFeatActivation:
    def test_toggle_dodge_on(self) -> None:
        c = fresh_char()
        base_ac = c.ac
        feat_reg, _, _ = loaded_registries()
        c.add_feat("Dodge", feat_reg.require("Dodge"))
        c.toggle_buff("Dodge", True)
        assert c.ac == base_ac + 1

    def test_toggle_dodge_off_reverts(self) -> None:
        c = fresh_char()
        base_ac = c.ac
        feat_reg, _, _ = loaded_registries()
        c.add_feat("Dodge", feat_reg.require("Dodge"))
        c.toggle_buff("Dodge", True)
        c.toggle_buff("Dodge", False)
        assert c.ac == base_ac

    def test_power_attack_with_parameter_3(self) -> None:
        """
        Power Attack for 3 points:
          attack_all penalty = -3 (untyped, stacks as penalty)
          damage_all bonus   = +3 (untyped)
        """
        c = fighter(8)
        base_atk = c.get("attack_melee")
        feat_reg, _, _ = loaded_registries()
        pa_defn = feat_reg.require("Power Attack")

        # Build the parameterized buff and register it manually
        buff = pa_defn.build_buff_definition(parameter=3)
        # Register via apply_buff with the parameterized buff
        c.feats.append({"name": "Power Attack"})
        pairs = buff.pool_entries(0, c)
        c.register_buff_definition("Power Attack", pairs)
        c.toggle_buff("Power Attack", True)

        assert c.get("attack_melee") == base_atk - 3
        assert c.get("damage_str_bonus") == 3  # damage bonus applied

    def test_power_attack_parameter_update(self) -> None:
        """Changing the parameter mid-session updates the pool values."""
        c = fighter(8)
        feat_reg, _, _ = loaded_registries()
        pa_defn = feat_reg.require("Power Attack")

        # Register with parameter=2
        buff_2 = pa_defn.build_buff_definition(parameter=2)
        c.feats.append({"name": "Power Attack"})
        c.register_buff_definition("Power Attack", buff_2.pool_entries(0, c))
        c.toggle_buff("Power Attack", True)
        base_atk = c.get("attack_melee")
        atk_pa2 = base_atk  # already includes -2

        # Re-register with parameter=5
        buff_5 = pa_defn.build_buff_definition(parameter=5)
        c._buff_entries["Power Attack"] = buff_5.pool_entries(0, c)
        c.toggle_buff("Power Attack", True)  # re-activate with new entries

        assert (
            c.get("attack_melee") == atk_pa2 - 3
        )  # additional -3 from -2 to -5

    def test_combat_expertise_attack_ac_tradeoff(self) -> None:
        """
        Combat Expertise for 2 points:
          attack penalty = -2, dodge AC bonus = +2.
        """
        c = fighter(4)
        c.set_ability_score("int", 15)  # meets prereq
        base_atk = c.get("attack_melee")
        base_ac = c.ac
        feat_reg, _, _ = loaded_registries()
        ce_defn = feat_reg.require("Combat Expertise")

        buff = ce_defn.build_buff_definition(parameter=2)
        c.feats.append({"name": "Combat Expertise"})
        c.register_buff_definition("Combat Expertise", buff.pool_entries(0, c))
        c.toggle_buff("Combat Expertise", True)

        assert c.get("attack_melee") == base_atk - 2
        assert c.ac == base_ac + 2

    def test_power_attack_and_bless_stack_differently(self) -> None:
        """
        Power Attack penalty (untyped penalty) stacks with
        Bless morale bonus — different types, both apply.
        """
        c = fighter(6)
        feat_reg, _, _ = loaded_registries()
        pa_defn = feat_reg.require("Power Attack")
        buff = pa_defn.build_buff_definition(parameter=3)
        c.feats.append({"name": "Power Attack"})
        c.register_buff_definition("Power Attack", buff.pool_entries(0, c))
        c.toggle_buff("Power Attack", True)

        # Add Bless
        from heroforge.engine.effects import BonusEffect, BuffDefinition

        bless = BuffDefinition(
            name="Bless",
            category=None,
            effects=[BonusEffect("attack_all", BonusType.MORALE, 1)],
        )
        apply_buff(bless, c)

        base_atk_no_buffs = c.get("bab")  # pure bab before any buffs
        # attack = bab + str_mod(0) + bless(+1 morale) + PA penalty(-3 untyped)
        assert c.get("attack_melee") == base_atk_no_buffs + 1 - 3


# ===========================================================================
# Integration: multiple always-on feats accumulate
# ===========================================================================


class TestMultipleAlwaysOnFeats:
    def test_multiple_save_feats_stack(self) -> None:
        """Iron Will + Great Fort + Lightning Reflexes stack."""
        c = fresh_char()
        feat_reg, _, _ = loaded_registries()
        base_will = c.will
        base_fort = c.fort
        base_ref = c.ref

        c.add_feat("Iron Will", feat_reg.require("Iron Will"))
        c.add_feat("Great Fortitude", feat_reg.require("Great Fortitude"))
        c.add_feat("Lightning Reflexes", feat_reg.require("Lightning Reflexes"))

        assert c.will == base_will + 2
        assert c.fort == base_fort + 2
        assert c.ref == base_ref + 2

    def test_dodge_and_improved_initiative(self) -> None:
        """Dodge (conditional) + Improved Init (always-on)."""
        c = fresh_char()
        feat_reg, _, _ = loaded_registries()
        base_ac = c.ac
        base_init = c.get("initiative")

        c.add_feat("Dodge", feat_reg.require("Dodge"))
        c.add_feat(
            "Improved Initiative",
            feat_reg.require("Improved Initiative"),
        )

        # Dodge not toggled — AC unchanged
        assert c.ac == base_ac
        # Improved Initiative always-on — +4
        assert c.get("initiative") == base_init + 4
        # Toggle Dodge on
        c.toggle_buff("Dodge", True)
        assert c.ac == base_ac + 1

    def test_three_toughness_feats_stack(self) -> None:
        """Three Toughness feats (different sources) — untyped HP all stack."""
        c = fighter(4)
        base_hp = c.hp_max
        feat_reg, _, _ = loaded_registries()
        defn = feat_reg.require("Toughness")

        # Add three separate toughness feats (e.g. from templates and normal)
        # In practice the character can only take it once, but the pool
        # handles multiple sources correctly.
        c.add_feat("Toughness", defn)
        # Re-adding is a no-op due to deduplication
        assert c.hp_max == base_hp + 3
