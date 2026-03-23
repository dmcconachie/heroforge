"""
engine/feats.py
---------------
FeatDefinition: the data model for feats.

Three kinds:
  always_on   — applied automatically when taken; stat effects are permanent.
  conditional — shown in the Buffs panel; user toggles per encounter/round.
  passive     — no stat effects; exists only as a prerequisite chain node.

Parameterized feats (Power Attack, Combat Expertise) have a `parameter`
block that describes the integer value the user sets at activation time.
The effect values in the YAML may contain "$parameter" which is substituted
at activation time.

Public API:
  FeatKind             — enum: ALWAYS_ON / CONDITIONAL / PASSIVE
  FeatParameterSpec    — describes the parameter for parameterized feats
  FeatDefinition       — complete feat definition
  FeatRegistry         — lookup by name
  resolve_feat_effects — substitute $parameter and build BonusEffect list
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from heroforge.engine.bonus import BonusType
from heroforge.engine.effects import (
    BonusEffect,
    BuffCategory,
    BuffDefinition,
)

if TYPE_CHECKING:
    from typing import Any

    from heroforge.engine.character import Character


# ---------------------------------------------------------------------------
# FeatKind
# ---------------------------------------------------------------------------


class FeatKind(enum.Enum):
    ALWAYS_ON = "always_on"
    CONDITIONAL = "conditional"
    PASSIVE = "passive"


# ---------------------------------------------------------------------------
# FeatParameterSpec
# ---------------------------------------------------------------------------


@dataclass
class FeatParameterSpec:
    """
    Describes the integer parameter a user sets when activating a
    parameterized conditional feat (e.g. Power Attack).

    Attributes
    ----------
    name        : Internal key (e.g. "points")
    label       : Display label shown in the buff panel
    min         : Minimum allowed value
    max_formula : Formula string evaluated to find the maximum
                  (e.g. "bab" for Power Attack,
                  "min(5, bab)" for Combat Expertise)
    default     : Default value when first activated
    """

    name: str
    label: str
    min: int = 1
    max_formula: str = "1"
    default: int = 1

    def resolve_max(self, character: "Character | None") -> int:
        """Evaluate max_formula against the character."""
        if character is None:
            return self.min
        from heroforge.engine.effects import evaluate_formula

        try:
            return max(
                self.min,
                evaluate_formula(self.max_formula, character=character),
            )
        except Exception:
            return self.min

    def clamp(self, value: int, character: "Character | None" = None) -> int:
        """Clamp a value to [min, max]."""
        maximum = self.resolve_max(character)
        return max(self.min, min(maximum, value))


# ---------------------------------------------------------------------------
# FeatDefinition
# ---------------------------------------------------------------------------


@dataclass
class FeatDefinition:
    """
    Complete description of a feat.

    Attributes
    ----------
    name            : Unique feat name
    kind            : ALWAYS_ON / CONDITIONAL / PASSIVE
    source_book     : e.g. "PHB"
    note            : Display hint
    prerequisites   : Prereq tree root (or None)
    parameter        : For parameterized feats
    effects         : Raw effect dicts from YAML
    snapshot        : Prereqs checked at acquisition only
    parameterized_selection : Weapon/skill choice metadata
    buff_definition : (derived, init=False) Pre-built
                      BuffDefinition for non-parameterized
                      feats.
    """

    name: str
    kind: FeatKind
    source_book: str = "PHB"
    note: str = ""
    prerequisites: Any | None = None
    parameter: FeatParameterSpec | None = None
    effects: list[dict] = field(default_factory=list)
    snapshot: bool = False
    parameterized_selection: dict | None = None
    # Derived (not from YAML):
    buff_definition: BuffDefinition | None = field(default=None, init=False)

    @property
    def is_parameterized(self) -> bool:
        return self.parameter is not None

    def build_buff_definition(
        self,
        parameter: int | None = None,
    ) -> BuffDefinition | None:
        """
        Build a BuffDefinition for this feat, substituting $parameter.

        For non-parameterized feats: returns self.buff_definition (cached).
        For parameterized feats: builds a fresh BuffDefinition with the
        given parameter value substituted into effect values.
        Returns None for passive feats.
        """
        if self.kind == FeatKind.PASSIVE:
            return None

        if not self.is_parameterized:
            return self.buff_definition

        # Parameterized: build fresh with substituted values
        effects = resolve_feat_effects(self.effects, parameter or 1)
        category = (
            BuffCategory.FEAT
            if self.kind == FeatKind.ALWAYS_ON
            else BuffCategory.FEAT
        )
        return BuffDefinition(
            name=self.name,
            category=category,
            source_book=self.source_book,
            effects=effects,
            note=self.note,
        )


# ---------------------------------------------------------------------------
# FeatRegistry
# ---------------------------------------------------------------------------


class FeatRegistry:
    """Central lookup for FeatDefinitions."""

    def __init__(self) -> None:
        self._defs: dict[str, FeatDefinition] = {}

    def register(self, defn: FeatDefinition, overwrite: bool = False) -> None:
        if defn.name in self._defs and not overwrite:
            raise ValueError(
                f"FeatDefinition {defn.name!r} already registered."
            )
        self._defs[defn.name] = defn

    def get(self, name: str) -> FeatDefinition | None:
        return self._defs.get(name)

    def require(self, name: str) -> FeatDefinition:
        defn = self._defs.get(name)
        if defn is None:
            raise KeyError(f"No FeatDefinition registered for {name!r}.")
        return defn

    def all_names(self) -> list[str]:
        return sorted(self._defs.keys())

    def by_kind(self, kind: FeatKind) -> list[FeatDefinition]:
        return [d for d in self._defs.values() if d.kind == kind]

    def __len__(self) -> int:
        return len(self._defs)

    def __contains__(self, name: str) -> bool:
        return name in self._defs


# ---------------------------------------------------------------------------
# Effect resolution with $parameter substitution
# ---------------------------------------------------------------------------


def resolve_feat_effects(
    raw_effects: list[dict],
    parameter: int = 1,
) -> list[BonusEffect]:
    """
    Build a list of BonusEffect from raw YAML-parsed effect declarations,
    substituting $parameter with the given integer value.

    raw_effects: list of dicts with keys: target, bonus_type, value,
                 source_label (optional), condition_key (optional).

    The value field may be:
      - An integer: used as-is.
      - A plain formula string: used as-is (evaluated at activation time).
      - A string containing "$parameter": the literal text "$parameter"
        is replaced with str(parameter), producing a formula that evaluates
        to the substituted value.

    Examples:
      value: "$parameter"          → str(parameter), i.e. the int directly
      value: "-$parameter"         → evaluate_formula("-3") = -3 when param=3
      value: "$parameter * 2"      → evaluate_formula("3 * 2") = 6 when param=3
    """
    bonus_type_map = {bt.value: bt for bt in BonusType}
    effects: list[BonusEffect] = []

    for eff in raw_effects:
        target = eff.get("target", "")
        bt_str = eff.get("bonus_type", "untyped")
        bonus_type = bonus_type_map.get(bt_str, BonusType.UNTYPED)
        raw_value = eff.get("value", 0)
        source_label = eff.get("source_label", "")

        # Substitute $parameter
        if isinstance(raw_value, str) and "$parameter" in raw_value:
            substituted = raw_value.replace("$parameter", str(parameter))
            # Try plain int first; if that fails, evaluate as a formula.
            # Since the parameter is known at this point, we can resolve
            # fully to an int now — no need to defer evaluation.
            try:
                resolved: int | str = int(substituted)
            except ValueError:
                from heroforge.engine.effects import evaluate_formula

                try:
                    resolved = evaluate_formula(substituted)
                except Exception:
                    resolved = substituted  # fallback: leave as formula string
        elif isinstance(raw_value, str):
            resolved = raw_value
        else:
            resolved = int(raw_value)

        effects.append(
            BonusEffect(
                target=target,
                bonus_type=bonus_type,
                value=resolved,
                source_label=source_label,
            )
        )

    return effects


# ---------------------------------------------------------------------------
# Builder from YAML declaration
# ---------------------------------------------------------------------------


def build_feat_from_yaml(
    decl: dict,
) -> FeatDefinition:
    """Build a FeatDefinition from a YAML dict."""
    from heroforge.engine.prerequisites import (
        build_prereq_from_yaml,
    )
    from heroforge.rules.schema import (
        _forbid_extra,
    )

    _forbid_extra(
        decl,
        FeatDefinition,
        decl.get("name", "?"),
    )
    name = decl["name"]
    kind_str = decl.get("kind", "passive")
    kind = FeatKind(kind_str)

    # Parse parameter spec
    param_spec: FeatParameterSpec | None = None
    if "parameter" in decl:
        p = decl["parameter"]
        param_spec = FeatParameterSpec(
            name=p.get("name", "value"),
            label=p.get("label", "Value"),
            min=int(p.get("min", 1)),
            max_formula=str(p.get("max_formula", "1")),
            default=int(p.get("default", 1)),
        )

    # Parse prerequisites
    prereq_decl = decl.get("prerequisites")
    prereq = build_prereq_from_yaml(prereq_decl) if prereq_decl else None

    raw_effects = decl.get("effects", [])

    defn = FeatDefinition(
        name=name,
        kind=kind,
        source_book=decl.get("source_book", "PHB"),
        note=decl.get("note", ""),
        prerequisites=prereq,
        parameter=param_spec,
        effects=raw_effects,
        snapshot=bool(decl.get("snapshot", False)),
        parameterized_selection=decl.get("parameterized_selection"),
    )

    # Build BuffDefinition for non-parameterized
    # feats with effects (derived, not from YAML)
    if kind != FeatKind.PASSIVE and raw_effects and param_spec is None:
        resolved = resolve_feat_effects(raw_effects)
        defn.buff_definition = BuffDefinition(
            name=name,
            category=BuffCategory.FEAT,
            source_book=decl.get("source_book", "PHB"),
            effects=resolved,
            note=decl.get("note", ""),
        )

    return defn
