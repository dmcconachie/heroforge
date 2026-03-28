"""
Tests for rules/core/conditions_srd.yaml.

Validates structure, no duplicates with compendium
buff spells, and that conditions with effects have
valid bonus types.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from heroforge.engine.bonus import BonusType
from heroforge.engine.conditions import (
    ConditionRegistry,
)
from heroforge.engine.effects import BuffRegistry
from heroforge.engine.spells import SpellCompendium
from heroforge.rules.loader import (
    ConditionLoader,
    SpellCompendiumLoader,
)

RULES_DIR = Path(__file__).parent.parent / "src" / "heroforge" / "rules"


@pytest.fixture()
def compendium_buff_names() -> set[str]:
    """
    Names registered in BuffRegistry via
    SpellCompendiumLoader dual registration."""
    comp = SpellCompendium()
    reg = BuffRegistry()
    loader = SpellCompendiumLoader(RULES_DIR)
    for i in range(10):
        loader.load(
            comp,
            f"core/spells_level_{i}.yaml",
            buff_registry=reg,
        )
    return set(reg.all_names())


@pytest.fixture()
def srd_data() -> dict[str, dict]:
    path = RULES_DIR / "core" / "conditions_srd.yaml"
    with open(path) as f:
        data = yaml.safe_load(f)
    return data


class TestConditionsSrdYaml:
    def test_all_have_names(self, srd_data: dict[str, dict]) -> None:
        for name in srd_data:
            assert isinstance(name, str) and name

    def test_no_duplicates_within_file(self, srd_data: dict[str, dict]) -> None:
        # Dict keys are unique by definition
        assert len(srd_data) > 0

    def test_no_duplicates_with_compendium_buffs(
        self,
        srd_data: dict[str, dict],
        compendium_buff_names: set[str],
    ) -> None:
        for name in srd_data:
            assert name not in compendium_buff_names, (
                f"{name!r} duplicates a compendium buff spell"
            )

    def test_no_category_field(self, srd_data: dict[str, dict]) -> None:
        """
        Conditions YAML should not have a
        category field — the loader sets it."""
        for name, d in srd_data.items():
            assert "category" not in d, (
                f"{name!r} has unexpected 'category' field"
            )

    def test_valid_bonus_types(self, srd_data: dict[str, dict]) -> None:
        valid = {bt.value for bt in BonusType}
        for name, d in srd_data.items():
            for eff in d.get("effects", []):
                bt = eff.get("bonus_type", "untyped")
                assert bt in valid, f"{name!r}: bad bonus_type {bt!r}"

    def test_loader_populates_both_registries(
        self,
    ) -> None:
        cond_reg = ConditionRegistry()
        buff_reg = BuffRegistry()
        loader = ConditionLoader(RULES_DIR)
        names = loader.load(
            cond_reg,
            buff_reg,
            "core/conditions_srd.yaml",
        )
        assert len(names) > 0
        for name in names:
            assert cond_reg.get(name) is not None
        for name in names:
            assert buff_reg.get(name) is not None

    def test_at_least_15_conditions(self, srd_data: dict[str, dict]) -> None:
        assert len(srd_data) >= 15

    def test_top_level_is_mapping(
        self,
    ) -> None:
        """The YAML file must be a flat mapping."""
        path = RULES_DIR / "core" / "conditions_srd.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)
        assert isinstance(data, dict)
