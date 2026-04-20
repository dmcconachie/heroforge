"""
tests/test_pool_keys.py
------------------------
Contract tests for the PoolKey StrEnum refactor.

These tests pin the invariants of the pool-key typing work:

  1. PoolKey enum covers every pool referenced by stats.yaml.
  2. PoolKey enum covers every skill derived from skills.yaml.
  3. The generator (_gen_pool_keys) is idempotent — rerunning it
     against the committed YAML reproduces the committed .py.
  4. skills.yaml no longer carries a redundant `key:` field.
  5. Constructing a BonusEffect with an unknown target raises
     a clear error.
  6. BonusPool round-trips a PoolKey as its stat_key (StrEnum is
     a str subclass, so dict lookups continue to work).
  7. Every `target:` field in every shipped rules YAML resolves
     to a real PoolKey member.

Until the refactor lands these tests are expected to be RED.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from heroforge.engine.bonus import BonusPool, BonusType
from heroforge.engine.effects import BonusEffect
from heroforge.rules._gen_common import enum_ident
from heroforge.rules._gen_pool_keys import main as check_pool_keys
from heroforge.rules.core.pool_keys import PoolKey

RULES_DIR = Path(__file__).parent.parent / "src" / "heroforge" / "rules"
CORE_DIR = RULES_DIR / "core"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stats_yaml_pool_refs() -> set[str]:
    """Collect every pool key referenced in stats.yaml."""
    data = yaml.safe_load((CORE_DIR / "stats.yaml").read_text())
    refs: set[str] = set()
    for decl in data:
        for pk in decl.get("pools", []) or []:
            refs.add(pk)
    return refs


def _skill_names() -> list[str]:
    """Return the skill names (YAML top-level keys) from skills.yaml."""
    data = yaml.safe_load((CORE_DIR / "skills.yaml").read_text())
    return list(data.keys())


def _iter_yaml_target_values() -> list[tuple[Path, str]]:
    """
    Walk every .yaml file under rules/ and collect every `target:`
    value (scalar strings only). Returns (path, value) pairs so
    failures can point at the offending file.
    """
    hits: list[tuple[Path, str]] = []

    def _walk(obj: object, path: Path) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == "target" and isinstance(v, str):
                    hits.append((path, v))
                else:
                    _walk(v, path)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item, path)

    for yaml_path in RULES_DIR.rglob("*.yaml"):
        try:
            data = yaml.safe_load(yaml_path.read_text())
        except yaml.YAMLError:
            continue
        _walk(data, yaml_path)
    return hits


# ---------------------------------------------------------------------------
# 1. stats.yaml coverage
# ---------------------------------------------------------------------------


def test_pool_key_enum_covers_stats_yaml() -> None:
    """Every pool referenced in stats.yaml must exist as a PoolKey."""
    refs = _stats_yaml_pool_refs()
    enum_values = {pk.value for pk in PoolKey}
    missing = sorted(refs - enum_values)
    assert missing == [], (
        f"stats.yaml references pools that are not in PoolKey: {missing}"
    )


# ---------------------------------------------------------------------------
# 2. skills.yaml coverage
# ---------------------------------------------------------------------------


def test_pool_key_enum_covers_skills_yaml() -> None:
    """
    For every skill name in skills.yaml there must be a PoolKey
    member named SKILL_<enum_ident(name)> whose value equals
    skill_<snake(enum_ident(name))>.
    """
    for name in _skill_names():
        ident = f"SKILL_{enum_ident(name)}"
        assert ident in PoolKey.__members__, (
            f"Missing PoolKey member {ident!r} for skill {name!r}"
        )
        expected_value = f"skill_{enum_ident(name).lower()}"
        assert PoolKey[ident].value == expected_value, (
            f"PoolKey.{ident} value is {PoolKey[ident].value!r}, "
            f"expected {expected_value!r}"
        )


# ---------------------------------------------------------------------------
# 3. Generator is idempotent
# ---------------------------------------------------------------------------


def test_generator_is_idempotent() -> None:
    """
    Running _gen_pool_keys.generate() should return content that
    matches what is currently committed, byte-for-byte.
    """
    assert check_pool_keys(argv=[]) == os.EX_OK, (
        "pool_keys.py is out of sync with YAML — "
        "run `uv run check-pool-keys --fix`"
    )


# ---------------------------------------------------------------------------
# 4. skills.yaml has no key: field
# ---------------------------------------------------------------------------


def test_skills_yaml_has_no_key_field() -> None:
    """
    The per-skill `key:` field is redundant (always
    skill_<snake(name)>). After the refactor it must be gone.
    """
    data = yaml.safe_load((CORE_DIR / "skills.yaml").read_text())
    offenders = [name for name, decl in data.items() if "key" in decl]
    assert offenders == [], (
        f"Skills still carry redundant `key:` field: {offenders}"
    )


# ---------------------------------------------------------------------------
# 5. Unknown target raises
# ---------------------------------------------------------------------------


def test_unknown_target_raises() -> None:
    """Constructing a BonusEffect with an unknown pool key must fail."""
    with pytest.raises((ValueError, KeyError)):
        BonusEffect(
            target="definitely_not_a_real_pool",
            bonus_type=BonusType.UNTYPED,
            value=1,
        )


# ---------------------------------------------------------------------------
# 6. BonusPool accepts PoolKey
# ---------------------------------------------------------------------------


def test_bonus_pool_accepts_pool_key() -> None:
    """
    BonusPool must accept a PoolKey as its stat_key, and since
    StrEnum subclasses str the value must compare equal to the
    underlying string.
    """
    pool = BonusPool(PoolKey.STR_SCORE)
    assert pool.stat_key == "str_score"
    assert pool.stat_key == PoolKey.STR_SCORE
    # Dict lookups must work interchangeably.
    d = {PoolKey.STR_SCORE: "ok"}
    assert d["str_score"] == "ok"


# ---------------------------------------------------------------------------
# 7. Every shipped YAML target: resolves
# ---------------------------------------------------------------------------


def test_every_yaml_target_resolves() -> None:
    """
    Sweep every rules YAML file; every `target:` scalar string
    must be a valid PoolKey value. This is the backstop that
    catches the ~600 real references in one go.
    """
    enum_values = {pk.value for pk in PoolKey}
    bad: list[tuple[Path, str]] = [
        (p, v) for p, v in _iter_yaml_target_values() if v not in enum_values
    ]
    assert bad == [], (
        "These YAML `target:` values don't match any PoolKey:\n  "
        + "\n  ".join(f"{p.relative_to(RULES_DIR)}: {v!r}" for p, v in bad)
    )
