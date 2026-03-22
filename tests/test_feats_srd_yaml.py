"""
Tests for rules/core/feats_srd.yaml.

Validates structure, no duplicates with feats_phb.yaml,
and that prerequisite references are valid.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from heroforge.engine.effects import BuffRegistry
from heroforge.engine.feats import FeatRegistry
from heroforge.engine.prerequisites import (
    PrerequisiteChecker,
)
from heroforge.rules.loader import FeatsLoader

RULES_DIR = Path(__file__).parent.parent / "src" / "heroforge" / "rules"


@pytest.fixture()
def phb_names() -> set[str]:
    path = RULES_DIR / "core" / "feats_phb.yaml"
    with open(path) as f:
        data = yaml.safe_load(f)
    return {d["name"] for d in data["feats"]}


@pytest.fixture()
def srd_data() -> list[dict]:
    path = RULES_DIR / "core" / "feats_srd.yaml"
    with open(path) as f:
        data = yaml.safe_load(f)
    return data["feats"]


class TestFeatsSrdYaml:
    def test_all_have_names(self, srd_data: list[dict]) -> None:
        for d in srd_data:
            assert "name" in d

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
                f"{d['name']!r} duplicates feats_phb.yaml"
            )

    def test_valid_kinds(self, srd_data: list[dict]) -> None:
        valid = {"always_on", "conditional", "passive"}
        for d in srd_data:
            assert d.get("kind") in valid, f"{d['name']!r}: bad kind"

    def test_loader_accepts_file(self) -> None:
        feat_reg = FeatRegistry()
        prereq = PrerequisiteChecker()
        buff_reg = BuffRegistry()
        loader = FeatsLoader(RULES_DIR)
        # Load PHB first (some SRD feats prereq PHB)
        loader.load(feat_reg, prereq, buff_reg)
        names = loader.load(
            feat_reg,
            prereq,
            buff_reg,
            "core/feats_srd.yaml",
        )
        assert len(names) > 0

    def test_at_least_25_feats(self, srd_data: list[dict]) -> None:
        assert len(srd_data) >= 25
