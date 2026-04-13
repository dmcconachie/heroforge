"""
engine/bonus.py
---------------
The typed bonus aggregation system.  This is the foundational layer of the
entire engine — every other module depends on this getting stacking rules right.

3.5e stacking rules summary:
  - Most bonus types are typed and non-stacking: only the single highest bonus
    of each type applies to a given stat.
  - Dodge bonuses always stack with each other (and with everything else).
  - Racial bonuses typically stack (handled as stacking here; edge cases noted).
  - Untyped bonuses always stack.
  - Penalties always stack regardless of type.
  - Two bonuses of the same type from the same source do not stack (e.g. two
    castings of Bull's Strength — handled at the source/buff level, not here).

Public API:
  BonusType          — enum of all valid bonus types
  BonusEntry         — a single bonus: value, type, display
                       label, optional condition
  BonusPool          — source-keyed collection;
                       set_source/clear_source are idempotent
  aggregate()        — functional helper: aggregate a list of BonusEntries
"""

from __future__ import annotations

import enum
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from heroforge.engine.character import Character


# ---------------------------------------------------------------------------
# Bonus Types
# ---------------------------------------------------------------------------


class BonusType(enum.Enum):
    # --- Typed, non-stacking (only highest of same type applies) -----------
    ENHANCEMENT = "enhancement"
    MORALE = "morale"
    LUCK = "luck"
    DEFLECTION = "deflection"
    RESISTANCE = "resistance"
    COMPETENCE = "competence"
    CIRCUMSTANCE = "circumstance"
    SACRED = "sacred"
    PROFANE = "profane"
    INSIGHT = "insight"
    ALCHEMICAL = "alchemical"
    ARMOR = "armor"
    SHIELD = "shield"
    NATURAL_ARMOR = "natural_armor"
    NATURAL_ARMOR_ENHANCEMENT = "natural_armor_enhancement"
    SIZE = "size"
    # --- Stacking (all instances sum) ---------------------------------------
    DODGE = "dodge"
    RACIAL = "racial"
    UNTYPED = "untyped"


# Types whose positive values always stack with each other.
ALWAYS_STACKING: frozenset[BonusType] = frozenset(
    {
        BonusType.DODGE,
        BonusType.RACIAL,
        BonusType.UNTYPED,
    }
)


# ---------------------------------------------------------------------------
# BonusEntry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BonusEntry:
    """
    A single bonus or penalty contribution to a stat.

    Attributes
    ----------
    value       : The numeric amount.  Negative = penalty.
    bonus_type  : How this bonus stacks with others of the same type.
    source      : Human-readable display label for tooltips and breakdown.
                  (e.g. "Bull's Strength", "Rage", "Weapon Focus")
    condition   : Optional callable(Character) -> bool.  The entry is only
                  counted when condition returns True.  None = always active.

    Identity within a BonusPool is entirely handled by the pool's source key
    (the string passed to set_source / clear_source).  BonusEntry is a pure
    value object; it carries no pool-level identity of its own.
    """

    value: int
    bonus_type: BonusType
    source: str = ""
    condition: object = field(default=None, compare=False, hash=False)

    def is_active(self, character: "Character | None" = None) -> bool:
        if self.condition is None:
            return True
        if character is None:
            return False
        return bool(self.condition(character))


# ---------------------------------------------------------------------------
# Core aggregation function
# ---------------------------------------------------------------------------


def aggregate(
    entries: list[BonusEntry], character: "Character | None" = None
) -> int:
    """
    Aggregate a list of BonusEntries into a single integer total.

    Rules:
      1. Entries whose condition is False are excluded.
      2. Negative values (penalties) always stack regardless of type.
      3. ALWAYS_STACKING types (dodge, racial, untyped) always sum.
      4. All other typed bonuses: only the highest value per type counts.
    """
    stacking_total: int = 0
    penalty_total: int = 0
    typed_buckets: dict[BonusType, list[int]] = defaultdict(list)

    for entry in entries:
        if not entry.is_active(character):
            continue
        if entry.value < 0:
            penalty_total += entry.value
        elif entry.bonus_type in ALWAYS_STACKING:
            stacking_total += entry.value
        else:
            typed_buckets[entry.bonus_type].append(entry.value)

    typed_total = sum(
        max(bucket) for bucket in typed_buckets.values() if bucket
    )
    return stacking_total + typed_total + penalty_total


# ---------------------------------------------------------------------------
# BonusPool
# ---------------------------------------------------------------------------


class BonusPool:
    """
    A source-keyed collection of BonusEntries for a single stat.

    Entries are stored in a dict keyed by *source key* — an arbitrary string
    chosen by the caller (buff name, item slot, class feature name, etc.).
    Each source key maps to a list of BonusEntries; a single source can
    contribute multiple entries to one pool.

    set_source() and clear_source() are fully idempotent:

      - set_source("Bless", [entry]) called twice is identical to calling
        it once.  The second call overwrites the first with the same data.
      - clear_source("Bless") on an absent key is a silent no-op.
      - Buff activation   → set_source(buff_name, entries)
      - Buff deactivation → clear_source(buff_name)

    No "was it already active?" guards are needed anywhere in the codebase.
    """

    def __init__(self, stat_key: str) -> None:
        self.stat_key: str = stat_key
        self._sources: dict[str, list[BonusEntry]] = {}

    # ------------------------------------------------------------------
    # Primary interface — idempotent
    # ------------------------------------------------------------------

    def set_source(self, source_key: str, entries: list[BonusEntry]) -> None:
        """
        Register (or replace) all entries from source_key.
        Idempotent: repeated calls with the same arguments have no additional
        effect.  Calling with different entries updates to the new set.
        """
        self._sources[source_key] = list(entries)

    def clear_source(self, source_key: str) -> None:
        """
        Remove all entries from source_key.
        Idempotent: no-op if source_key is not present.
        """
        self._sources.pop(source_key, None)

    def clear_all(self) -> None:
        """Remove every source and all their entries."""
        self._sources.clear()

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def _all_entries(self) -> list[BonusEntry]:
        result: list[BonusEntry] = []
        for entries in self._sources.values():
            result.extend(entries)
        return result

    def total(self, character: "Character | None" = None) -> int:
        """Compute the aggregated bonus total, respecting stacking rules."""
        return aggregate(self._all_entries(), character)

    def active_entries(
        self, character: "Character | None" = None
    ) -> list[BonusEntry]:
        """Return entries that are currently active (condition met)."""
        return [e for e in self._all_entries() if e.is_active(character)]

    def source_keys(self) -> list[str]:
        """Return all registered source keys."""
        return list(self._sources.keys())

    def entries_for(self, source_key: str) -> list[BonusEntry]:
        """Return the entries registered under source_key, or []."""
        return list(self._sources.get(source_key, []))

    def breakdown(self, character: "Character | None" = None) -> dict[str, int]:
        """
        Return a display-friendly breakdown of effective contributions.

        Format: {entry.source: effective_value}
        Entries that lose to a higher same-type bonus show 0.
        Inactive entries are excluded entirely.
        Useful for tooltip text: "Bull's Strength +4 (superseded by +6 item)".
        """
        active = [e for e in self._all_entries() if e.is_active(character)]
        result: dict[str, int] = {}

        for e in active:
            if e.value < 0:
                result[e.source] = e.value

        for e in active:
            if e.value >= 0 and e.bonus_type in ALWAYS_STACKING:
                result[e.source] = e.value

        typed_buckets: dict[BonusType, list[BonusEntry]] = defaultdict(list)
        for e in active:
            if e.value >= 0 and e.bonus_type not in ALWAYS_STACKING:
                typed_buckets[e.bonus_type].append(e)

        for bucket_entries in typed_buckets.values():
            best_val = max(e.value for e in bucket_entries)
            for e in bucket_entries:
                result[e.source] = e.value if e.value == best_val else 0

        return result

    def __len__(self) -> int:
        return sum(len(v) for v in self._sources.values())

    def __repr__(self) -> str:
        return (
            f"BonusPool({self.stat_key!r}, "
            f"{len(self._sources)} sources, {len(self)} entries)"
        )
