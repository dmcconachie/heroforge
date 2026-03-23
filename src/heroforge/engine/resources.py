"""
engine/resources.py
-------------------
Resource tracking for uses-per-day class abilities
(Rage, Turn Undead, Bardic Music, Wild Shape, etc.).

A ResourceTracker holds the maximum uses (computed from
a formula string) and current remaining uses. Resources
are separate from the stat graph — they are consumed
quantities, not modifiers.

Public API:
  ResourceTracker  — one tracked resource
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ResourceTracker:
    """
    A uses-per-day resource.

    Attributes
    ----------
    name        : Display name (e.g. "Rage")
    max_formula : Formula for max uses, evaluated with
                  character stats as variables.
                  e.g. "1 + barbarian_level // 4"
    current     : Remaining uses today. Reset to max
                  on long rest.
    """

    name: str
    max_formula: str = "1"
    current: int = 0

    def reset(self, max_uses: int) -> None:
        """Reset current uses to computed maximum."""
        self.current = max_uses

    def use(self) -> bool:
        """Consume one use. Returns False if empty."""
        if self.current <= 0:
            return False
        self.current -= 1
        return True

    @property
    def exhausted(self) -> bool:
        return self.current <= 0
