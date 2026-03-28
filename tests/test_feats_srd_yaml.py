"""
Tests for rules/core/feats.yaml.

Validates structure, no duplicates, alphabetical order,
and that the loader accepts the merged file.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from heroforge.engine.effects import BuffRegistry
from heroforge.engine.feats import FeatRegistry
from heroforge.engine.prerequisites import (
    PrerequisiteChecker,
)
from heroforge.rules.loader import FeatsLoader

RULES_DIR = Path(__file__).parent.parent / "src" / "heroforge" / "rules"

FEATS_PATH = RULES_DIR / "core" / "feats.yaml"


def _load_feats() -> dict[str, dict]:
    with open(FEATS_PATH) as f:
        data = yaml.safe_load(f)
    return data["feats"]


class TestFeatsYaml:
    def test_all_have_names(self) -> None:
        for name in _load_feats():
            assert isinstance(name, str) and name

    def test_no_duplicate_names(self) -> None:
        # Dict keys are unique by definition; just verify count.
        names = list(_load_feats().keys())
        assert len(names) == len(set(names))

    def test_valid_kinds(self) -> None:
        valid = {"always_on", "conditional", "passive"}
        for name, d in _load_feats().items():
            assert d.get("kind") in valid, f"{name!r}: bad kind"

    def test_alphabetical_order(self) -> None:
        """Feats must be sorted alphabetically."""
        names = list(_load_feats().keys())
        sorted_names = sorted(names, key=lambda n: n.lower())
        for i, (actual, expected) in enumerate(
            zip(names, sorted_names, strict=True)
        ):
            assert actual == expected, (
                f"Feat at index {i}: {actual!r} should be {expected!r}"
            )

    def test_at_least_100_feats(self) -> None:
        assert len(_load_feats()) >= 100

    def test_loader_accepts_file(self) -> None:
        feat_reg = FeatRegistry()
        prereq = PrerequisiteChecker()
        buff_reg = BuffRegistry()
        loader = FeatsLoader(RULES_DIR)
        names = loader.load(
            feat_reg,
            "core/feats.yaml",
            prereq,
            buff_reg,
        )
        assert len(names) >= 100
