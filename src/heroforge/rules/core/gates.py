"""
rules/core/gates.py
SRD gate keys — named equipment-state predicates used to
govern when an effect (class feature, magic item,
derived-pool consumer) contributes to a stat.

Gate vocabulary grows as features are implemented. Each
entry here corresponds to a Python predicate registered
in engine/gates.py's GATE_PREDICATES dict.
"""

from __future__ import annotations

from enum import StrEnum


class KnownCoreGate(StrEnum):
    # Barbarian fast movement (PHB p.25) gates.
    NOT_HEAVY_ARMOR = "not_heavy_armor"
    NOT_HEAVY_LOAD = "not_heavy_load"
