"""
engine/effects.py
-----------------
BuffDefinition: the data model for spells, class features, feats, items,
and conditions that contribute bonuses to character stats.

This module handles:
  - The BuffDefinition dataclass and its component types
  - A sandboxed formula evaluator for caster-level-scaling bonuses
  - BuffRegistry: lookup by name and category
  - Applying / removing a BuffDefinition to / from a Character

What this module does NOT do:
  - Prerequisite checking (engine/prerequisites.py)
  - Persistence (rules/loader.py reads YAML → creates BuffDefinitions)
  - GUI (ui/)

Design notes:
  ─────────────────────────────────────────────────────────────────────────
  A BuffDefinition is the *template* for a buff.  A BuffState (in
  character.py) is the *instance* — whether it is currently active and
  what caster level is stored for it.

  The two main types of effect value:
    • Static int  — e.g. Bless always gives +1 morale.
    • Formula str — e.g. Divine Favor gives "max(1, caster_level // 3)".

  Formulas are evaluated in a restricted namespace containing only safe
  math operations and a small set of named variables resolved from the
  active character/buff state at evaluation time.

  Conditions on BonusEffect (e.g. "only works on humanoids") use Python
  callables, not formula strings — they are set in Python by the loader
  and tested in tests.  Formula strings are only used for the *value*
  calculation.
  ─────────────────────────────────────────────────────────────────────────

Public API:
  BuffCategory       — enum: SPELL, CLASS, FEAT, ITEM,
                       CONDITION, RACIAL, TEMPLATE
  BonusEffect        — one stat contribution from a buff (value + type + target)
  BuffDefinition     — complete description of a buff's effects
  BuffRegistry       — lookup and registration of BuffDefinitions
  FormulaError       — raised on bad formula strings
  evaluate_formula() — safe formula evaluator
  apply_buff()       — apply a BuffDefinition to a Character
  remove_buff()      — remove a BuffDefinition from a Character
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from heroforge.engine.bonus import BonusEntry
from heroforge.engine.character import Ability

if TYPE_CHECKING:
    from typing import Any, Callable

    from heroforge.engine.bonus import BonusType
    from heroforge.engine.character import Character


# ---------------------------------------------------------------------------
# BuffCategory
# ---------------------------------------------------------------------------


class BuffCategory(enum.Enum):
    SPELL = "spell"
    CLASS = "class"
    FEAT = "feat"
    ITEM = "item"
    CONDITION = "condition"  # status effects: shaken, fatigued, etc.
    RACIAL = "racial"  # racial traits that can be toggled (e.g. shifter)
    TEMPLATE = "template"  # creature template effects


# ---------------------------------------------------------------------------
# FormulaError and safe evaluator
# ---------------------------------------------------------------------------


class FormulaError(Exception):
    """Raised when a formula string cannot be parsed or evaluated."""


# Safe names available inside formula expressions.
# Only math functions and a handful of helpers — no builtins, no imports.
_SAFE_MATH = {
    "abs": abs,
    "max": max,
    "min": min,
    "round": round,
    "floor": math.floor,
    "ceil": math.ceil,
    "int": int,
}


def evaluate_formula(
    formula: str,
    caster_level: int = 0,
    character: "Character | None" = None,
    extra: dict[str, Any] | None = None,
) -> int:
    """
    Evaluate a formula string to an integer.

    Available names inside the formula:
      caster_level   — the buff's stored caster level (0 if not set)
      character_level — character.total_level (0 if no character)
      str_mod, dex_mod, …  — ability modifiers (0 if no character)
      bab            — base attack bonus (0 if no character)
      All names in _SAFE_MATH (abs, max, min, floor, ceil, int, round)
      Any names in `extra` dict (for caller-supplied context)

    Returns an int.  Raises FormulaError on syntax or evaluation errors.

    Examples:
      "max(1, caster_level // 3)"         → Divine Favor luck bonus
      "2 + caster_level // 6"             → Shield of Faith deflection
      "min(30, caster_level * 2)"         → Heart of Earth AC (capped)
      "4 + 2 * (caster_level >= 12)"      → conditional scaling
    """
    namespace: dict[str, Any] = {**_SAFE_MATH}

    # Inject caster level
    namespace["caster_level"] = int(caster_level or 0)

    # Inject character-derived values when available
    if character is not None:
        namespace["character_level"] = character.total_level
        for ab in Ability:
            namespace[f"{ab}_mod"] = character.get_ability_modifier(ab)
        namespace["bab"] = character.get("bab")
    else:
        namespace["character_level"] = 0
        for ab in Ability:
            namespace[f"{ab}_mod"] = 0
        namespace["bab"] = 0

    # Caller-supplied extras (for loader-injected context)
    if extra:
        namespace.update(extra)

    # Strip __builtins__ from the eval namespace entirely
    namespace["__builtins__"] = {}

    try:
        result = eval(compile(formula, "<formula>", "eval"), namespace)  # noqa: S307
    except SyntaxError as e:
        raise FormulaError(f"Syntax error in formula {formula!r}: {e}") from e
    except Exception as e:
        raise FormulaError(f"Error evaluating formula {formula!r}: {e}") from e

    try:
        return int(result)
    except (TypeError, ValueError) as e:
        raise FormulaError(
            f"Formula {formula!r} returned non-numeric value {result!r}"
        ) from e


# ---------------------------------------------------------------------------
# BonusEffect
# ---------------------------------------------------------------------------


@dataclass
class BonusEffect:
    """
    One stat contribution from a buff.

    A single BuffDefinition may have multiple BonusEffects — for example,
    Haste contributes to attack rolls, AC (dodge), and speed simultaneously.

    Attributes
    ----------
    target      : The BonusPool key this effect feeds into.
                  e.g. "str_score", "ac", "attack_melee", "attack_all",
                  "fort_save", "speed", "initiative".
                  Special key "attack_all" feeds both attack_melee and
                  attack_ranged.
    bonus_type  : The BonusType for stacking purposes.
    value       : Static integer value OR a formula string.
                  If str, it is evaluated via evaluate_formula() at
                  application time using the buff's stored caster level.
    condition   : Optional callable(Character) -> bool.  The BonusEntry
                  is only active when condition returns True.
                  None = unconditionally active.
    source_label: Human-readable label for the BonusEntry.source field.
                  Defaults to the parent BuffDefinition's name.
    """

    target: str
    bonus_type: BonusType
    value: int | str  # int = static; str = formula
    condition_key: str = ""
    source_label: str = ""
    # Derived (set by loader from condition_key):
    condition: Callable | None = field(default=None, init=False)

    def is_formula(self) -> bool:
        return isinstance(self.value, str)

    def resolve_value(
        self,
        caster_level: int = 0,
        character: "Character | None" = None,
    ) -> int:
        """
        Resolve the value to an integer.
        If value is already an int, returns it directly.
        If value is a formula string, evaluates it.
        """
        if isinstance(self.value, int):
            return self.value
        return evaluate_formula(self.value, caster_level, character)

    def to_bonus_entry(
        self,
        source_label: str,
        caster_level: int = 0,
        character: "Character | None" = None,
    ) -> BonusEntry:
        """
        Build the BonusEntry that gets registered in a BonusPool.

        For static values: the int is baked in.
        For formula values: the int is evaluated now (at activation time),
        using the stored caster level.  If the caster level changes, the
        buff must be re-applied (deactivate then activate) to pick up the
        new value.
        """
        label = self.source_label or source_label
        resolved = self.resolve_value(caster_level, character)
        return BonusEntry(
            value=resolved,
            bonus_type=self.bonus_type,
            source=label,
            condition=self.condition,
        )


# ---------------------------------------------------------------------------
# BuffDefinition
# ---------------------------------------------------------------------------

# Special pool-key aliases expanded at application time
_MULTI_TARGET_EXPANSIONS: dict[str, list[str]] = {
    "attack_all": ["attack_melee", "attack_ranged"],
    "damage_all": ["damage_melee", "damage_ranged"],
}


@dataclass
class BuffDefinition:
    """
    Complete description of a buff: its effects, category, and metadata.

    Attributes
    ----------
    name                   : Unique name used as the buff key everywhere.
    category               : What kind of effect this is.
    source_book            : e.g. "PHB", "SpC", "CAd".
    effects                : List of BonusEffects this buff applies.
    requires_caster_level  : True if any effect uses a formula that needs CL.
    mutually_exclusive_with: Names of buffs that cannot be active at the
                             same time (e.g. Rage and Greater Rage).
    note                   : Display hint shown in the buff panel UI.
    ongoing_condition      : Optional callable(Character) -> bool.  If the
                             character stops satisfying this condition (e.g.
                             alignment change for a paladin buff), the buff
                             should be auto-deactivated.  Checked by the
                             validator, not the buff engine.
    """

    name: str
    category: BuffCategory
    source_book: str = "PHB"
    effects: list[BonusEffect] = field(default_factory=list)
    requires_caster_level: bool = False
    mutually_exclusive_with: list[str] = field(default_factory=list)
    note: str = ""
    condition_key: str = ""
    # Derived (set by loader from condition_key):
    ongoing_condition: Callable | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        # Auto-detect whether CL is needed from formula effects
        if not self.requires_caster_level:
            for effect in self.effects:
                if effect.is_formula():
                    self.requires_caster_level = True
                    break

    def pool_entries(
        self,
        caster_level: int = 0,
        character: "Character | None" = None,
    ) -> list[tuple[str, BonusEntry]]:
        """
        Expand effects into (pool_key, BonusEntry) pairs ready for
        registration into BonusPools.

        Multi-target keys (e.g. "attack_all") are expanded to their
        constituent pool keys here — the expansion is invisible to the
        caller.

        Returns a flat list.  Multiple effects on the same pool key are
        all included; the pool's aggregate() handles stacking.
        """
        result: list[tuple[str, BonusEntry]] = []
        for effect in self.effects:
            entry = effect.to_bonus_entry(self.name, caster_level, character)
            targets = _MULTI_TARGET_EXPANSIONS.get(
                effect.target, [effect.target]
            )
            for target in targets:
                result.append((target, entry))
        return result


# ---------------------------------------------------------------------------
# BuffRegistry
# ---------------------------------------------------------------------------


class BuffRegistry:
    """
    Central lookup for all loaded BuffDefinitions.

    One registry is shared across the application (loaded at startup from
    rules YAML files).  Characters hold references to BuffStates; they
    look up the full definition here when applying or removing a buff.

    The registry is read-only after loading.  Splatbook definitions are
    merged in priority order; later registrations for the same name
    override earlier ones (e.g. SpC version of a spell supersedes PHB).
    """

    def __init__(self) -> None:
        self._defs: dict[str, BuffDefinition] = {}

    def register(self, defn: BuffDefinition, overwrite: bool = False) -> None:
        """
        Register a BuffDefinition.  If a definition with the same name
        already exists, raises unless overwrite=True.
        """
        if defn.name in self._defs and not overwrite:
            raise ValueError(
                f"BuffDefinition {defn.name!r} already registered. "
                f"Pass overwrite=True to replace it (splatbook override)."
            )
        self._defs[defn.name] = defn

    def get(self, name: str) -> BuffDefinition | None:
        return self._defs.get(name)

    def require(self, name: str) -> BuffDefinition:
        defn = self._defs.get(name)
        if defn is None:
            raise KeyError(f"No BuffDefinition registered for {name!r}.")
        return defn

    def all_names(self) -> list[str]:
        return sorted(self._defs.keys())

    def by_category(self, category: BuffCategory) -> list[BuffDefinition]:
        return [d for d in self._defs.values() if d.category == category]

    def by_source_book(self, book: str) -> list[BuffDefinition]:
        return [d for d in self._defs.values() if d.source_book == book]

    def __len__(self) -> int:
        return len(self._defs)

    def __contains__(self, name: str) -> bool:
        return name in self._defs


# ---------------------------------------------------------------------------
# build_buff_from_effects — shared by all domain loaders
# ---------------------------------------------------------------------------

# Condition keys map to Python callables.
# The builder attaches these to BonusEffect.condition.
CONDITION_REGISTRY: dict[str, object] = {
    "humanoid_only": lambda char: (
        getattr(char, "_race_type", "Humanoid") == "Humanoid"
    ),
}


def build_buff_from_effects(
    name: str,
    category: BuffCategory,
    effects_raw: list[dict],
    source_book: str = "SRD",
    note: str = "",
    requires_caster_level: bool = False,
    mutually_exclusive_with: (list[str] | None) = None,
    condition_key: str = "",
) -> BuffDefinition | None:
    """
    Build a BuffDefinition from raw effect dicts.

    Returns None if *effects_raw* is empty.
    Resolves BonusType enums and condition_keys.
    Raises ValueError on unknown bonus_type or
    condition_key.
    """
    if not effects_raw:
        return None

    from heroforge.engine.bonus import BonusType

    bt_map: dict[str, BonusType] = {bt.value: bt for bt in BonusType}

    effects: list[BonusEffect] = []
    for eff_decl in effects_raw:
        target = eff_decl.get("target")
        if not target:
            msg = f"{name!r}: effect missing 'target': {eff_decl}"
            raise ValueError(msg)

        bt_str = eff_decl.get("bonus_type", "untyped")
        bonus_type = bt_map.get(bt_str)
        if bonus_type is None:
            msg = f"{name!r}: unknown bonus_type {bt_str!r}"
            raise ValueError(msg)

        raw_value = eff_decl.get("value", 0)
        if isinstance(raw_value, bool):
            raw_value = int(raw_value)

        cond_key = eff_decl.get("condition_key", "")
        eff = BonusEffect(
            target=target,
            bonus_type=bonus_type,
            value=raw_value,
            condition_key=cond_key,
            source_label=eff_decl.get("source_label", ""),
        )
        if cond_key:
            resolved = CONDITION_REGISTRY.get(cond_key)
            if resolved is None:
                msg = (
                    f"{name!r}: unknown "
                    f"condition_key {cond_key!r}. "
                    f"Known: "
                    f"{sorted(CONDITION_REGISTRY)}"
                )
                raise ValueError(msg)
            eff.condition = resolved
        effects.append(eff)

    # Resolve spell-level condition_key too
    ongoing = None
    if condition_key:
        resolved = CONDITION_REGISTRY.get(condition_key)
        if resolved is None:
            msg = f"{name!r}: unknown condition_key {condition_key!r}"
            raise ValueError(msg)
        ongoing = resolved

    defn = BuffDefinition(
        name=name,
        category=category,
        source_book=source_book,
        effects=effects,
        requires_caster_level=requires_caster_level,
        mutually_exclusive_with=(mutually_exclusive_with or []),
        note=note,
        condition_key=condition_key,
    )
    if ongoing is not None:
        defn.ongoing_condition = ongoing
    return defn


# ---------------------------------------------------------------------------
# apply_buff / remove_buff
# ---------------------------------------------------------------------------


def apply_buff(
    defn: BuffDefinition,
    character: "Character",
    caster_level: int = 0,
) -> set[str]:
    """
    Apply a BuffDefinition to a Character.

    1. Builds (pool_key, BonusEntry) pairs from the definition.
    2. Calls character.register_buff_definition() if not already known.
    3. Calls character.toggle_buff(name, True, caster_level).

    Returns the set of stat keys that were invalidated.
    """
    pairs = defn.pool_entries(caster_level, character)

    # Register if the character hasn't seen this buff yet
    if defn.name not in character._buff_states:
        character.register_buff_definition(defn.name, pairs)
    else:
        # Update the registered entries in case CL changed the values
        character._buff_entries[defn.name] = pairs

    return character.toggle_buff(defn.name, True, caster_level or None)


def remove_buff(
    defn: BuffDefinition,
    character: "Character",
) -> set[str]:
    """
    Remove a BuffDefinition from a Character.

    Simply delegates to character.toggle_buff(name, False).
    Idempotent: safe to call even if the buff is already inactive.
    """
    if defn.name not in character._buff_states:
        return set()
    return character.toggle_buff(defn.name, False)
