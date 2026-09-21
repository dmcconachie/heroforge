"""
engine/domains.py
-----------------
Cleric domain definitions for D&D 3.5e.

Public API:
  DomainDefinition  -- domain with spells
  DomainRegistry    -- lookup by name
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from heroforge.engine.character import Character
from heroforge.engine.effects import (
    BuffCategory,
    build_buff_from_effects,
    evaluate_formula,
)
from heroforge.engine.resources import ResourceTracker, UseUnit


@dataclass(frozen=True)
class DomainResource:
    """A daily-limited granted power (PHB pp. 186-187)."""

    name: str
    max_formula: str = "1"
    unit: UseUnit = UseUnit.USE
    # Stat effects the power confers while active. Present only
    # for powers whose benefit the engine can express; the buff
    # is registered under the resource's own name.
    effects: tuple[dict, ...] = ()


@dataclass(frozen=True)
class DomainDefinition:
    """A cleric domain with granted power and spells."""

    name: str
    granted_power: str = ""
    domain_spells: dict[int, str] = field(
        default_factory=dict
    )  # level 1-9 -> spell name
    # Skills this domain adds to the cleric's class skill list
    # (PHB p. 31). Entries follow class-skill syntax, so
    # "Knowledge (all)" is a legal wildcard.
    class_skills: list[str] = field(default_factory=list)
    # Daily-limited granted power, if the domain has one.
    resource: DomainResource | None = None


class DomainRegistry:
    """Name-based lookup for domain definitions."""

    def __init__(self) -> None:
        self._entries: dict[str, DomainDefinition] = {}

    def register(self, defn: DomainDefinition) -> None:
        self._entries[defn.name] = defn

    def get(self, name: str) -> DomainDefinition | None:
        return self._entries.get(name)

    def all_domains(self) -> list[DomainDefinition]:
        return list(self._entries.values())

    def names(self) -> list[str]:
        return sorted(self._entries.keys())

    def __len__(self) -> int:
        return len(self._entries)


def refresh_domain_resources(character: "Character") -> None:
    """
    Rebuild ``character.resources`` from the character's domains.

    Replaces the whole domain-derived set rather than merging, so
    dropping a domain drops its resource instead of stranding it.
    Each tracker starts full; spending is the caller's business.
    """
    from heroforge.rules.rules import get_rules

    registry = get_rules().domains
    resources: dict[str, ResourceTracker] = {}
    for domain_name in character.domains:
        defn = registry.get(domain_name)
        if defn is None or defn.resource is None:
            continue
        spec = defn.resource
        max_uses = evaluate_formula(spec.max_formula, character=character)
        resources[spec.name] = ResourceTracker(
            name=spec.name,
            max_formula=spec.max_formula,
            current=max_uses,
            unit=spec.unit,
        )
        if spec.effects:
            buff = build_buff_from_effects(
                name=spec.name,
                category=BuffCategory.CLASS,
                effects_raw=[dict(e) for e in spec.effects],
                note=defn.granted_power,
            )
            if buff is not None:
                character.register_buff_definition(
                    spec.name, buff.pool_entries(0, character)
                )
    character.resources = resources
