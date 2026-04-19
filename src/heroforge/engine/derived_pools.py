"""
engine/derived_pools.py
Named compute strategies for derived-pool consumers and
for migrated class-feature / magic-item formulas too
complex for the simple `value:` DSL.

Follows stats.yaml's `compute:` dispatch pattern: YAML
declares the strategy by name, Python owns the function.
No string eval, no DSL — each strategy is a regular
Callable[[Character], int].

Public API:
  register_compute(name)         — decorator
  get_compute(name)              — lookup; raises KeyError
  registered_names()             — sorted list
  install_consumers(character,   — register consumers as
                    data)          dynamic BonusEntry
                                   instances on the
                                   character's target
                                   pools
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from heroforge.engine.bonus import BonusEntry, BonusType
from heroforge.engine.character import Ability
from heroforge.engine.gates import make_condition
from heroforge.rules.core.pool_keys import PoolKey

if TYPE_CHECKING:
    from heroforge.engine.character import Character


ComputeFn = Callable[["Character"], int]
_REGISTRY: dict[str, ComputeFn] = {}


def register_compute(name: str) -> Callable[[ComputeFn], ComputeFn]:
    def deco(fn: ComputeFn) -> ComputeFn:
        if name in _REGISTRY:
            raise ValueError(f"compute strategy {name!r} already registered")
        _REGISTRY[name] = fn
        return fn

    return deco


def get_compute(name: str) -> ComputeFn:
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(
            f"unknown compute strategy {name!r}. Known: {sorted(_REGISTRY)}"
        ) from exc


def registered_names() -> list[str]:
    return sorted(_REGISTRY)


# ---------------------------------------------------------------------------
# Built-in strategies
# ---------------------------------------------------------------------------


@register_compute("monk_ac_wis_bonus")
def _monk_ac_wis_bonus(character: "Character") -> int:
    """
    Wis-mod half of the monk AC bonus formula
    (PHB p.40). Only applies when some source has
    contributed monk levels to the pool — a Fighter with
    Wis 18 but no Monk's Belt should NOT get +4 AC just
    because his gates hold."""
    pool = character.get("effective_monk_level_ac")
    if pool <= 0:
        return 0
    return max(0, character.get_ability_modifier(Ability.WIS))


@register_compute("monk_ac_level_bonus")
def _monk_ac_level_bonus(character: "Character") -> int:
    """
    Level-based half of the monk AC bonus formula
    (PHB p.40): effective_monk_level // 5."""
    pool = character.get("effective_monk_level_ac")
    if pool <= 0:
        return 0
    return pool // 5


@register_compute("monk_fast_movement_bonus")
def _monk_fast_movement_bonus(character: "Character") -> int:
    """
    PHB Table 3-10: +10 ft per three monk levels from
    level 3 onward, capped by the L18-20 +60 row."""
    monk_level = character.class_level_map.get("Monk", 0)
    if monk_level < 3:
        return 0
    return ((monk_level - 3) // 3 + 1) * 10


# ---------------------------------------------------------------------------
# Consumer installation
# ---------------------------------------------------------------------------

_SOURCE_PREFIX = "derived_pool_consumer"


def _bonus_type_from_str(bt_str: str) -> BonusType:
    bt_map = {bt.value: bt for bt in BonusType}
    return bt_map.get(bt_str, BonusType.UNTYPED)


def install_consumers(
    character: "Character",
    data: dict,
) -> None:
    """
    Install derived-pool consumer formulas on a
    character. Each consumer becomes a passive BonusEntry
    on its target pool, keyed by a stable source string.

    Consumer values are refreshed on every
    _refresh_derived_consumers() call — the Character
    wires that up in its change-notification path.
    """
    character._derived_consumer_specs = []
    for pool_name, entry in data.items():
        for idx, consumer in enumerate(entry.get("consumers", [])):
            target = consumer.get("target")
            compute_name = consumer.get("compute")
            if not target or not compute_name:
                raise ValueError(
                    f"derived pool {pool_name!r} consumer "
                    f"{idx} missing target or compute"
                )
            target_key = PoolKey(target)
            bonus_type = _bonus_type_from_str(
                consumer.get("bonus_type", "untyped")
            )
            fn = get_compute(compute_name)
            gate = consumer.get("gate") or []
            condition = make_condition(tuple(gate))
            src = f"{_SOURCE_PREFIX}:{pool_name}:{idx}"
            # `source_label:` lets the sheet show this
            # contribution with a specific name in the
            # `typed:` breakdown for untyped / dodge /
            # racial entries (which group by source rather
            # than bonus type). Falls back to the pool
            # name + compute strategy when omitted.
            label = consumer.get("source_label") or (
                f"derived:{pool_name}:{compute_name}"
            )
            character._derived_consumer_specs.append(
                {
                    "src": src,
                    "target_key": target_key,
                    "fn": fn,
                    "bonus_type": bonus_type,
                    "label": label,
                    "condition": condition,
                }
            )

    refresh_derived_consumers(character)


def refresh_derived_consumers(character: "Character") -> None:
    """
    Recompute every installed consumer's BonusEntry
    and re-register it on its target pool."""
    specs = getattr(character, "_derived_consumer_specs", None)
    if not specs:
        return
    for spec in specs:
        entry = BonusEntry(
            value=spec["fn"](character),
            bonus_type=spec["bonus_type"],
            source=spec["label"],
            condition=spec["condition"],
        )
        pool = character._pools.get(spec["target_key"])
        if pool is None:
            continue
        pool.set_source(spec["src"], [entry])
        character._graph.invalidate_pool(spec["target_key"])
