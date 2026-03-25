"""
Tests for rules/core/conditions_srd.yaml.

Validates structure, no duplicates with spells_phb.yaml,
and that conditions with effects have valid bonus types.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from heroforge.engine.bonus import BonusType
from heroforge.engine.conditions import ConditionRegistry
from heroforge.engine.effects import BuffRegistry
from heroforge.rules.loader import ConditionLoader

RULES_DIR = Path(__file__).parent.parent / "src" / "heroforge" / "rules"


@pytest.fixture()
def phb_names() -> set[str]:
    path = RULES_DIR / "core" / "spells_phb.yaml"
    with open(path) as f:
        data = yaml.safe_load(f)
    return {d["name"] for d in data["spells"]}


@pytest.fixture()
def srd_data() -> list[dict]:
    path = RULES_DIR / "core" / "conditions_srd.yaml"
    with open(path) as f:
        data = yaml.safe_load(f)
    return data["conditions"]


class TestConditionsSrdYaml:
    def test_all_have_names(self, srd_data: list[dict]) -> None:
        for d in srd_data:
            assert "name" in d, f"Missing name: {d}"

    def test_no_duplicates_within_file(self, srd_data: list[dict]) -> None:
        names = [d["name"] for d in srd_data]
        assert len(names) == len(set(names))

    def test_no_duplicates_with_phb(
        self,
        srd_data: list[dict],
        phb_names: set[str],
    ) -> None:
        for d in srd_data:
            assert d["name"] not in phb_names, (
                f"{d['name']!r} duplicates spells_phb.yaml"
            )

    def test_no_category_field(self, srd_data: list[dict]) -> None:
        """
        Conditions YAML should not have a
        category field — the loader sets it."""
        for d in srd_data:
            assert "category" not in d, (
                f"{d['name']!r} has unexpected 'category' field"
            )

    def test_valid_bonus_types(self, srd_data: list[dict]) -> None:
        valid = {bt.value for bt in BonusType}
        for d in srd_data:
            for eff in d.get("effects", []):
                bt = eff.get("bonus_type", "untyped")
                assert bt in valid, f"{d['name']!r}: bad bonus_type {bt!r}"

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
        # Every condition in the condition registry
        for name in names:
            assert cond_reg.get(name) is not None
        # Every condition also in the buff registry
        for name in names:
            assert buff_reg.get(name) is not None

    def test_at_least_15_conditions(self, srd_data: list[dict]) -> None:
        assert len(srd_data) >= 15

    def test_top_level_key_is_conditions(
        self,
    ) -> None:
        """
        The YAML file must use 'conditions:'
        as its top-level key."""
        path = RULES_DIR / "core" / "conditions_srd.yaml"
        with open(path) as f:
            data = yaml.safe_load(f)
        assert "conditions" in data
        assert "spells" not in data
