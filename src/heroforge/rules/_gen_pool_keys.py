"""
_gen_pool_keys.py
------------------
Keep ``rules/core/pool_keys.py`` in sync with its YAML sources.

The ``PoolKey`` StrEnum is the closed set of BonusPool
identifiers used throughout the engine. Its members come from
two sources:

  - stats.yaml  — every ``pools:`` entry across every stat node
  - skills.yaml — one member per skill, named
                  ``SKILL_<enum_ident(name)>`` with value
                  ``"skill_<snake(enum_ident(name))>"``.

Usage:
    uv run check-pool-keys          # exit 1 if stale
    uv run check-pool-keys --fix    # regenerate
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import yaml

from heroforge.rules._gen_common import check_or_fix, emit_header, emit_member

RULES_DIR = Path(__file__).parent
CORE_DIR = RULES_DIR / "core"
STATS_YAML = CORE_DIR / "stats.yaml"
SKILLS_YAML = CORE_DIR / "skills.yaml"
OUT_FILE = CORE_DIR / "pool_keys.py"

# Pools registered in engine/character.py bootstrap that aren't
# (yet) reflected in stats.yaml. Kept here so PoolKey stays
# complete — move them into stats.yaml when/if the bootstrap is
# unified with the YAML stat graph.
_EXTRA_POOL_KEYS: tuple[str, ...] = (
    "grapple",
    "damage_ranged",
)


def _stat_pool_refs() -> list[str]:
    """
    Collect every pool key referenced in stats.yaml plus any
    ``_EXTRA_POOL_KEYS`` the engine registers in Python, in
    first-occurrence order (stable for diffs).
    """
    data = yaml.safe_load(STATS_YAML.read_text()) or []
    seen: list[str] = []
    seen_set: set[str] = set()
    for decl in data:
        for pk in decl.get("pools", []) or []:
            if pk not in seen_set:
                seen.append(pk)
                seen_set.add(pk)
    for pk in _EXTRA_POOL_KEYS:
        if pk not in seen_set:
            seen.append(pk)
            seen_set.add(pk)
    return seen


def _render() -> str:
    lines = emit_header(
        filename="pool_keys.py",
        description="Closed set of BonusPool identifiers used by the engine.",
        generator_file="_gen_pool_keys.py",
        toml_command="check-pool-keys",
        extra_imports=[
            ("heroforge.rules.combine_str_enum", "combine"),
            ("heroforge.rules.core.skills", "KnownCoreSkill"),
        ],
        cls_name="_StatPoolKey",
    )

    seen: set[str] = set()
    for val in _stat_pool_refs():
        ident = val.upper()
        if ident in seen:
            raise RuntimeError(
                f"Duplicate PoolKey ident {ident!r} from stats.yaml"
            )
        seen.add(ident)
        lines += emit_member(ident, val)

    lines += [
        "",
        "",
        "_SkillPoolKey = StrEnum(",
        '    "SkillPoolKey",',
        "    {",
        '        f"SKILL_{skill.name}": f"skill_{skill.name.lower()}"',
        "        for skill in KnownCoreSkill",
        "    },",
        ")",
        "",
        "",
        'PoolKey = combine("PoolKey", _StatPoolKey, _SkillPoolKey)',
    ]

    return "\n".join(lines) + "\n"


def _generate() -> dict[Path, str]:
    """Return {path: desired_content} for every generated file."""
    return {OUT_FILE: _render()}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check that pool_keys.py matches its YAML sources. "
            "Pass --fix to regenerate."
        )
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help=(
            "Regenerate pool_keys.py from its YAML sources. "
            "Default (no flag) is read-only: exit 1 if stale."
        ),
    )
    args = parser.parse_args()

    desired = _generate()
    check_ok = check_or_fix(desired, args.fix, "check-pool-keys", RULES_DIR)
    return os.EX_OK if check_ok else os.EX_SOFTWARE


if __name__ == "__main__":
    raise SystemExit(main())
