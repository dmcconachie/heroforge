"""
engine/character.py
-------------------
The Character class.  This is the central object that the UI, export layer,
and rules engine all talk to.

Responsibilities:
  - Hold all raw character inputs (ability scores, class levels, feats, etc.)
  - Own the StatGraph and all BonusPools for this character
  - Manage active buffs and their effects on pools/stats
  - Provide the interface for buff toggling, ability score changes, and
    any other mutation that must cascade through the stat graph
  - Emit change notifications (via a simple observer list) so the UI can
    update displayed values without polling

What this module does NOT do:
  - No GUI imports
  - No YAML serialisation (that lives in persistence.py, not yet written)
  - No rules data loading (that lives in the rules registry)
  - No prerequisite checking (engine/prerequisites.py)

Public API:
  AbilityScore        — enum of the six ability scores
  ClassLevel          — named tuple (class_name, level, hp_rolls)
  BuffState           — persisted per-buff toggle state
  Character           — the main class
  CharacterError      — raised on invalid operations
"""

from __future__ import annotations

import contextlib
import enum
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any, Callable

    from heroforge.engine.bonus import BonusEntry
    from heroforge.engine.feats import FeatDefinition

from heroforge.engine.bonus import BonusPool
from heroforge.engine.stat import (
    StatError,
    StatGraph,
    StatNode,
    compute_ability_modifier,
    compute_capped_dex,
    compute_sum,
)

# ---------------------------------------------------------------------------
# Supporting types
# ---------------------------------------------------------------------------


class AbilityScore(enum.Enum):
    STR = "str"
    DEX = "dex"
    CON = "con"
    INT = "int"
    WIS = "wis"
    CHA = "cha"


ABILITY_TO_SAVE = {
    "fort": "con",
    "ref": "dex",
    "will": "wis",
}


@dataclass
class ClassLevel:
    """One class entry in the character's class list."""

    class_name: str
    level: int
    hp_rolls: list[int] = field(default_factory=list)
    # bab_per_level and save_progressions are looked up from rules data;
    # stored here as cached values once the rules registry is wired up.
    bab_contribution: int = 0  # total BAB from this class entry
    fort_contribution: int = 0
    ref_contribution: int = 0
    will_contribution: int = 0


@dataclass
class BuffState:
    """
    Persistent per-character per-buff state.
    Stored in the character YAML and re-applied on load.
    """

    active: bool
    caster_level: int | None = None  # None if buff doesn't scale with CL
    parameter: int | None = None  # For parameterized feats (e.g. Power Attack)
    note: str = ""  # optional DM/player annotation


@dataclass
class DmOverride:
    """A DM override for a prerequisite check."""

    target: str  # feat name, PrC name, etc.
    note: str = ""


class CharacterError(Exception):
    pass


# ---------------------------------------------------------------------------
# Change notification
# ---------------------------------------------------------------------------


class ChangeNotifier:
    """
    Minimal observer pattern.  The UI registers callbacks here; the
    Character calls notify() when stats change.

    Keeps the Character decoupled from PyQt6 signals — the UI layer wraps
    this in a QObject signal if needed, or the Character can be used
    headlessly in tests without any Qt dependency.
    """

    def __init__(self) -> None:
        self._listeners: list[Callable[[set[str]], None]] = []

    def subscribe(self, fn: Callable[[set[str]], None]) -> None:
        """Register a callback(changed_stat_keys: set[str])."""
        if fn not in self._listeners:
            self._listeners.append(fn)

    def unsubscribe(self, fn: Callable[[set[str]], None]) -> None:
        with contextlib.suppress(ValueError):
            self._listeners.remove(fn)

    def notify(self, changed_keys: set[str]) -> None:
        for fn in self._listeners:
            fn(changed_keys)


# ---------------------------------------------------------------------------
# Character
# ---------------------------------------------------------------------------


class Character:
    """
    The central character object.

    Construction
    ------------
    Build via the constructor, then call bootstrap_stat_graph() to wire up
    the standard 3.5e stat nodes.  When the rules registry is available,
    the loader calls apply_class_levels(), apply_race(), etc. to populate
    the derived fields.

    Mutation protocol
    -----------------
    All mutations go through the public methods (set_ability_score,
    toggle_buff, etc.) which handle pool updates, stat invalidation, and
    change notification.  Never mutate _graph or _pools directly.
    """

    def __init__(
        self,
        name: str = "Unnamed",
        player: str = "",
        campaign: str = "",
    ) -> None:
        # --- Identity -------------------------------------------------------
        self.name: str = name
        self.player: str = player
        self.campaign: str = campaign

        # --- Raw inputs (persisted) -----------------------------------------
        self._ability_scores: dict[str, int] = {
            "str": 10,
            "dex": 10,
            "con": 10,
            "int": 10,
            "wis": 10,
            "cha": 10,
        }
        self.class_levels: list[ClassLevel] = []
        self.race: str = ""
        self.alignment: str = ""
        self.deity: str = ""
        self.feats: list[dict[str, Any]] = []
        # feat entries: {"name": str, "parameter": str|None}

        self.skills: dict[str, int] = {}
        # skill_name → ranks invested

        # --- Template tracking ----------------------------------------------
        self.templates: list = []
        # list of TemplateApplication objects (from engine/templates.py)

        # Template-derived character state (written by engine/templates.py)
        self._creature_type_override: str | None = None
        self._template_subtypes: list = []

        # Race-derived state (written by engine/classes_races.apply_race)
        self._race_base_speed: int = 30
        self._race_creature_type: str = "Humanoid"
        self._race_subtypes: list = []

        self.enabled_sources: list[str] = ["PHB"]

        # --- Equipment (simplified for now) --------------------------------
        self.equipment: dict[str, Any] = {}
        # slot_name → item dict; populated by equipment manager

        # --- Buff management ------------------------------------------------
        self._buff_states: dict[str, BuffState] = {}
        # buff_name → BuffState

        # Entries contributed by each active buff, indexed by buff name.
        # When a buff is deactivated its entries are removed from the pools.
        self._buff_entries: dict[str, list[tuple[str, BonusEntry]]] = {}
        # buff_name → [(pool_key, BonusEntry), ...]

        # --- DM overrides ---------------------------------------------------
        self.dm_overrides: list[DmOverride] = []

        # --- HP tracking ----------------------------------------------------
        self.hp_current: int = 0
        # hp_max is computed from class_levels + con_mod

        # --- Companion sub-objects ------------------------------------------
        self.familiar: Any | None = None
        self.animal_companion: Any | None = None

        # --- Stat graph & pools ---------------------------------------------
        self._graph: StatGraph = StatGraph()
        self._pools: dict[str, BonusPool] = {}

        # --- Change notification ---------------------------------------------
        self.on_change: ChangeNotifier = ChangeNotifier()

        # Bootstrap the standard stat graph
        self._bootstrap_stat_graph()

    # -----------------------------------------------------------------------
    # Stat graph bootstrap
    # -----------------------------------------------------------------------

    def _bootstrap_stat_graph(self) -> None:
        """
        Register all standard 3.5e stat nodes and pools.

        Pools are registered first, then nodes in dependency order
        (leaves before anything that depends on them).

        This creates the skeleton; actual values come from:
          - _ability_scores (set via set_ability_score)
          - class_levels (BAB and save contributions)
          - pools populated by buffs, feats, equipment
        """
        g = self._graph

        # ---- Pools ---------------------------------------------------------
        pool_keys = [
            # Ability score pools (buffs like Bull's Strength go here)
            "str_score",
            "dex_score",
            "con_score",
            "int_score",
            "wis_score",
            "cha_score",
            # Save pools (resistance bonuses, luck, etc.)
            "fort_save",
            "ref_save",
            "will_save",
            # Attack pools
            "attack_melee",
            "attack_ranged",
            "attack_all",
            # Damage pools
            "damage_melee",
            "damage_ranged",
            "damage_all",
            # AC pools
            "ac",
            # Initiative
            "initiative",
            # Speed
            "speed",
            # HP bonus pool (temporary HP, Toughness, etc.)
            "hp_bonus",
            # Skill pools — populated by skills.py; placeholder here
            # (individual skill pools added dynamically)
            # Misc
            "sr",  # spell resistance
            "bab_misc",  # miscellaneous BAB bonuses (rare)
        ]
        for pk in pool_keys:
            pool = BonusPool(pk)
            self._pools[pk] = pool
            g.register_pool(pool)

        # ---- Ability scores ------------------------------------------------
        # Each score has a base (set by _ability_scores) + pool bonuses.
        for ab in ("str", "dex", "con", "int", "wis", "cha"):
            base = self._ability_scores[ab]
            pool_key = f"{ab}_score"

            def make_score_compute(
                ability: str,
            ) -> Callable[[dict, int], int]:
                def compute(inputs: dict, bt: int) -> int:
                    return self._ability_scores[ability] + bt

                return compute

            g.register_node(
                StatNode(
                    key=f"{ab}_score",
                    base=base,
                    pool_keys=[pool_key],
                    compute=make_score_compute(ab),
                    description=f"{ab.upper()} score",
                )
            )

        # ---- Ability modifiers ---------------------------------------------
        for ab in ("str", "dex", "con", "int", "wis", "cha"):
            g.register_node(
                StatNode(
                    key=f"{ab}_mod",
                    inputs=[f"{ab}_score"],
                    compute=compute_ability_modifier,
                    description=f"{ab.upper()} modifier",
                )
            )

        # ---- BAB -----------------------------------------------------------
        # bab is computed from class contributions; starts at 0.
        # Class engine will update bab_contribution on ClassLevel objects
        # and call invalidate("bab") when levels change.
        g.register_node(
            StatNode(
                key="bab",
                pool_keys=["bab_misc"],
                compute=lambda inputs, bt: self._compute_bab() + bt,
                description="Base Attack Bonus",
            )
        )

        # ---- Saving throws -------------------------------------------------
        # Base saves come from class levels; ability mod feeds in as input.
        for save, ab in ABILITY_TO_SAVE.items():
            pool_key = f"{save}_save"
            g.register_node(
                StatNode(
                    key=f"{save}_save",
                    inputs=[f"{ab}_mod"],
                    pool_keys=[pool_key],
                    compute=lambda inputs, bt, s=save: (
                        self._compute_base_save(s)
                        + inputs[f"{ABILITY_TO_SAVE[s]}_mod"]
                        + bt
                    ),
                    description=f"{save.capitalize()} save",
                )
            )

        # ---- AC components -------------------------------------------------
        # max_dex_bonus: set by armour; -1 = uncapped
        g.register_node(
            StatNode(
                key="max_dex_bonus",
                compute=lambda inputs, bt: self._compute_max_dex_bonus() + bt,
                description="Maximum DEX bonus to AC from armour",
            )
        )

        g.register_node(
            StatNode(
                key="ac_dex_contribution",
                inputs=["dex_mod", "max_dex_bonus"],
                compute=compute_capped_dex("max_dex_bonus"),
                description="DEX contribution to AC (capped by armour)",
            )
        )

        # Total AC: 10 + dex_contribution + pool bonuses
        # (armour, shield, natural, deflection, etc. go into "ac" pool)
        g.register_node(
            StatNode(
                key="ac",
                inputs=["ac_dex_contribution"],
                pool_keys=["ac"],
                compute=lambda inputs, bt: (
                    10 + inputs["ac_dex_contribution"] + bt
                ),
                description="Armour Class",
            )
        )

        # Touch AC: no armour/shield/natural — just 10 + dex + deflection/dodge
        # Computed dynamically in get_touch_ac(); not a separate node here
        # because it reuses the same pools with a filter.

        # ---- Initiative ----------------------------------------------------
        g.register_node(
            StatNode(
                key="initiative",
                inputs=["dex_mod"],
                pool_keys=["initiative"],
                compute=compute_sum,
                description="Initiative modifier",
            )
        )

        # ---- Speed ---------------------------------------------------------
        g.register_node(
            StatNode(
                key="speed",
                pool_keys=["speed"],
                compute=lambda inputs, bt: self._compute_base_speed() + bt,
                description="Movement speed (ft)",
            )
        )

        # ---- HP maximum ----------------------------------------------------
        g.register_node(
            StatNode(
                key="hp_max",
                inputs=["con_mod"],
                pool_keys=["hp_bonus"],
                compute=lambda inputs, bt: (
                    self._compute_hp_from_rolls()
                    + inputs["con_mod"] * self.total_level
                    + bt
                ),
                description="Maximum hit points",
            )
        )

        # ---- Spell resistance ----------------------------------------------
        g.register_node(
            StatNode(
                key="sr",
                pool_keys=["sr"],
                compute=compute_sum,
                description="Spell Resistance",
            )
        )

        # ---- Melee attack (primary, no iteratives) -------------------------
        # Full iterative attack strings are computed in combat.py;
        # this node gives the primary attack bonus.
        g.register_node(
            StatNode(
                key="attack_melee",
                inputs=["bab", "str_mod"],
                pool_keys=["attack_melee", "attack_all"],
                compute=lambda inputs, bt: (
                    inputs["bab"]
                    + inputs["str_mod"]
                    + self._compute_size_mod_attack()
                    + bt
                ),
                description="Primary melee attack bonus",
            )
        )

        g.register_node(
            StatNode(
                key="attack_ranged",
                inputs=["bab", "dex_mod"],
                pool_keys=["attack_ranged", "attack_all"],
                compute=lambda inputs, bt: (
                    inputs["bab"]
                    + inputs["dex_mod"]
                    + self._compute_size_mod_attack()
                    + bt
                ),
                description="Primary ranged attack bonus",
            )
        )

        # ---- Damage (unarmed baseline — weapon damage computed in combat.py)
        g.register_node(
            StatNode(
                key="damage_str_bonus",
                inputs=["str_mod"],
                pool_keys=["damage_melee", "damage_all"],
                compute=compute_sum,
                description="STR bonus to melee damage",
            )
        )

    # -----------------------------------------------------------------------
    # Internal computation helpers
    # (called by lambdas in the stat graph; not part of public API)
    # -----------------------------------------------------------------------

    def _compute_bab(self) -> int:
        return sum(cl.bab_contribution for cl in self.class_levels)

    def _compute_base_save(self, save: str) -> int:
        attr = f"{save}_contribution"
        return sum(getattr(cl, attr, 0) for cl in self.class_levels)

    def _compute_max_dex_bonus(self) -> int:
        """
        Returns the maximum DEX bonus allowed by equipped armour.
        -1 means no cap.  Lowest value among all equipped items wins.
        """
        armor_item = self.equipment.get("armor")
        if armor_item is None:
            return -1
        cap = armor_item.get("max_dex_bonus", -1)
        return cap

    def _compute_hp_from_rolls(self) -> int:
        return sum(sum(cl.hp_rolls) for cl in self.class_levels)

    def _compute_base_speed(self) -> int:
        # Returns the race's base speed (set by apply_race()).
        # Armour speed penalties go through the speed pool, not here.
        return self._race_base_speed

    def _compute_size_mod_attack(self) -> int:
        # Size modifiers to attack: Fine+8, Diminutive+4, Tiny+2, Small+1,
        # Medium 0, Large-1, Huge-2, Gargantuan-4, Colossal-8
        SIZE_ATK_MOD = {
            "Fine": 8,
            "Diminutive": 4,
            "Tiny": 2,
            "Small": 1,
            "Medium": 0,
            "Large": -1,
            "Huge": -2,
            "Gargantuan": -4,
            "Colossal": -8,
        }
        return SIZE_ATK_MOD.get(self.size, 0)

    # -----------------------------------------------------------------------
    # Public properties
    # -----------------------------------------------------------------------

    @property
    def total_level(self) -> int:
        return sum(cl.level for cl in self.class_levels)

    @property
    def size(self) -> str:
        """Current size category. Overridden by templates."""
        return getattr(self, "_size_override", None) or self._base_size

    @property
    def _base_size(self) -> str:
        """Base size from race.  Defaults to Medium until race is loaded."""
        return getattr(self, "_race_size", "Medium")

    # -----------------------------------------------------------------------
    # Ability score mutation
    # -----------------------------------------------------------------------

    def set_ability_score(self, ability: str, value: int) -> None:
        """
        Set a base ability score and cascade invalidation.

        ability: one of "str", "dex", "con", "int", "wis", "cha"
        value:   the new base score (before any bonuses)
        """
        ability = ability.lower()
        if ability not in self._ability_scores:
            raise CharacterError(f"Unknown ability score: {ability!r}")
        if not (1 <= value <= 99):
            raise CharacterError(
                f"Ability score must be between 1 and 99, got {value}."
            )

        self._ability_scores[ability] = value
        # The score node's compute fn reads directly from _ability_scores,
        # so we just need to invalidate it.
        self._graph.invalidate(f"{ability}_score")
        self._notify({f"{ability}_score", f"{ability}_mod"})

    def get_ability_score(self, ability: str) -> int:
        """Return the total ability score (base + all bonuses)."""
        return self._graph.resolve(f"{ability.lower()}_score", self)

    def get_ability_modifier(self, ability: str) -> int:
        return self._graph.resolve(f"{ability.lower()}_mod", self)

    # -----------------------------------------------------------------------
    # Stat resolution (general)
    # -----------------------------------------------------------------------

    def get(self, stat_key: str) -> int:
        """
        Resolve any stat by key.  The primary interface for the UI and
        export layer to read computed values.

        Returns 0 for unknown keys rather than raising, to simplify
        display code that may reference stats not yet implemented.
        """
        try:
            return self._graph.resolve(stat_key, self)
        except StatError:
            return 0

    def get_breakdown(self, stat_key: str) -> dict[str, int]:
        """
        Return the bonus breakdown for a pool associated with stat_key.
        Used by tooltip displays.  Returns {} if no pool exists.
        """
        pool = self._pools.get(stat_key)
        if pool is None:
            return {}
        return pool.breakdown(self)

    # -----------------------------------------------------------------------
    # Buff management
    # -----------------------------------------------------------------------

    def register_buff_definition(
        self,
        buff_name: str,
        entries: list[tuple[str, BonusEntry]],
        requires_caster_level: bool = False,
    ) -> None:
        """
        Tell the character about a buff and the pool entries it contributes.

        Called by the rules registry when a buff definition is loaded.
        Does NOT activate the buff — that is toggle_buff's job.

        entries: list of (pool_key, BonusEntry) pairs
        """
        # Store the template entries; actual pool registration happens
        # only when the buff is activated.
        self._buff_entries[buff_name] = entries
        # Initialise buff state if not already present (e.g. on load the
        # YAML provides the state, so we don't overwrite it).
        if buff_name not in self._buff_states:
            self._buff_states[buff_name] = BuffState(
                active=False,
                caster_level=None,
            )

    def toggle_buff(
        self,
        buff_name: str,
        active: bool,
        caster_level: int | None = None,
        parameter: int | None = None,
    ) -> set[str]:
        """
        Activate or deactivate a buff.

        caster_level: stored on the buff state; used by CL-scaling formulas.
        parameter:    for parameterized feats (e.g. Power Attack).  When set,
                      the buff's $parameter token is substituted before pool
                      registration.  Stored on buff state for persistence.

        Idempotent: repeated calls with the same arguments have no effect.

        Returns the set of stat keys that were invalidated.
        """
        if buff_name not in self._buff_states:
            raise CharacterError(
                f"Buff {buff_name!r} is not registered on this character. "
                f"Call register_buff_definition() first."
            )

        state = self._buff_states[buff_name]

        if caster_level is not None:
            state.caster_level = caster_level
        if parameter is not None:
            state.parameter = parameter

        state.active = active

        # Group the buff's entries by pool key, then set_source or
        # clear_source on each pool.  Both operations are idempotent.
        affected_pools: set[str] = set()

        # Build per-pool entry lists for this buff
        pool_entries: dict[str, list] = {}
        for pool_key, entry in self._buff_entries.get(buff_name, []):
            pool_entries.setdefault(pool_key, []).append(entry)

        for pool_key, entries in pool_entries.items():
            p = self._pools.get(pool_key)
            if p is None:
                continue
            if active:
                p.set_source(buff_name, entries)
            else:
                p.clear_source(buff_name)
            affected_pools.add(pool_key)

        # Cascade invalidation through the stat graph
        invalidated: set[str] = set()
        for pk in affected_pools:
            self._graph.invalidate_pool(pk)
            for node in self._graph._nodes.values():
                if pk in node.pool_keys:
                    invalidated.add(node.key)
                    invalidated.update(self._graph.dependents_of(node.key))

        if invalidated:
            self._notify(invalidated)

        return invalidated

    def get_buff_state(self, buff_name: str) -> BuffState | None:
        return self._buff_states.get(buff_name)

    def is_buff_active(self, buff_name: str) -> bool:
        state = self._buff_states.get(buff_name)
        return state.active if state else False

    def active_buffs(self) -> list[str]:
        return [
            name for name, state in self._buff_states.items() if state.active
        ]

    # -----------------------------------------------------------------------
    # Feat management
    # -----------------------------------------------------------------------

    def add_feat(
        self,
        feat_name: str,
        defn: FeatDefinition | None = None,
        parameter: int | None = None,
        source: str = "",
    ) -> None:
        """
        Add a feat to this character.

        For always_on feats: immediately applies the feat's stat effects
        as an auto-active buff (never shown in the Buffs panel).

        For conditional feats: registers the buff definition so it can
        be toggled via toggle_buff().  Does NOT activate it — the user
        does that via the Buffs panel.

        For passive feats: records the feat name only; no pool effects.

        defn: the FeatDefinition (from FeatsLoader).  If None, the feat
              is recorded but no effects are applied.
        """
        # Avoid duplicate feat entries
        existing = {f.get("name") for f in self.feats}
        if feat_name in existing:
            return

        entry: dict = {"name": feat_name}
        if source:
            entry["source"] = source
        if parameter is not None:
            entry["parameter"] = parameter
        self.feats.append(entry)

        if defn is None:
            return

        # Apply effects based on feat kind
        # Compare kind using .value to handle FeatKind enum or plain string
        kind_val = getattr(defn, "kind", None)
        if hasattr(kind_val, "value"):
            kind_val = kind_val.value

        if kind_val == "always_on" and defn.buff_definition is not None:
            from heroforge.engine.effects import apply_buff

            apply_buff(defn.buff_definition, self)
            # Mark it as auto — not user-toggled
            if feat_name in self._buff_states:
                self._buff_states[feat_name].note = "auto:feat"

        elif kind_val == "conditional" and defn.buff_definition is not None:
            # Register but do NOT activate — user toggles from Buffs panel
            pairs = defn.buff_definition.pool_entries(0, self)
            if feat_name not in self._buff_states:
                self.register_buff_definition(
                    feat_name,
                    pairs,
                    requires_caster_level=False,
                )

    def remove_feat(
        self,
        feat_name: str,
        defn: FeatDefinition | None = None,
    ) -> None:
        """
        Remove a feat from this character.

        Reverses always_on stat effects and deactivates any conditional
        buff that was active.
        """
        self.feats = [f for f in self.feats if f.get("name") != feat_name]

        if defn is None:
            return

        kind_val = getattr(defn, "kind", None)
        if hasattr(kind_val, "value"):
            kind_val = kind_val.value

        if (
            kind_val in ("always_on", "conditional")
            and feat_name in self._buff_states
        ):
            self.toggle_buff(feat_name, False)
            # Clean up registration
            del self._buff_states[feat_name]
            self._buff_entries.pop(feat_name, None)

    # -----------------------------------------------------------------------
    # Pool access (for rules registry and equipment manager)
    # -----------------------------------------------------------------------

    def get_pool(self, key: str) -> BonusPool | None:
        return self._pools.get(key)

    def add_pool(self, pool: BonusPool) -> None:
        """Register an additional pool (e.g. a per-skill pool)."""
        self._pools[pool.stat_key] = pool
        self._graph.register_pool(pool)

    # -----------------------------------------------------------------------
    # Class levels
    # -----------------------------------------------------------------------

    def set_class_levels(self, levels: list[ClassLevel]) -> None:
        """
        Replace the class level list and invalidate all derived stats.
        Called by the character builder and rules loader.
        """
        self.class_levels = levels
        # BAB, saves, and hp_max all depend on class levels
        self._graph.invalidate("bab")
        self._graph.invalidate("fort_save")
        self._graph.invalidate("ref_save")
        self._graph.invalidate("will_save")
        self._graph.invalidate("hp_max")
        self._notify(
            {
                "bab",
                "fort_save",
                "ref_save",
                "will_save",
                "hp_max",
                "attack_melee",
                "attack_ranged",
            }
        )

    # -----------------------------------------------------------------------
    # DM overrides
    # -----------------------------------------------------------------------

    def add_dm_override(self, target: str, note: str = "") -> None:
        if not any(o.target == target for o in self.dm_overrides):
            self.dm_overrides.append(DmOverride(target=target, note=note))

    def remove_dm_override(self, target: str) -> bool:
        before = len(self.dm_overrides)
        self.dm_overrides = [o for o in self.dm_overrides if o.target != target]
        return len(self.dm_overrides) < before

    def has_dm_override(self, target: str) -> bool:
        return any(o.target == target for o in self.dm_overrides)

    # -----------------------------------------------------------------------
    # Change notification
    # -----------------------------------------------------------------------

    def _notify(self, changed_keys: set[str]) -> None:
        self.on_change.notify(changed_keys)

    # -----------------------------------------------------------------------
    # Convenience computed properties
    # -----------------------------------------------------------------------

    @property
    def str_score(self) -> int:
        return self.get("str_score")

    @property
    def dex_score(self) -> int:
        return self.get("dex_score")

    @property
    def con_score(self) -> int:
        return self.get("con_score")

    @property
    def int_score(self) -> int:
        return self.get("int_score")

    @property
    def wis_score(self) -> int:
        return self.get("wis_score")

    @property
    def cha_score(self) -> int:
        return self.get("cha_score")

    @property
    def str_mod(self) -> int:
        return self.get("str_mod")

    @property
    def dex_mod(self) -> int:
        return self.get("dex_mod")

    @property
    def con_mod(self) -> int:
        return self.get("con_mod")

    @property
    def int_mod(self) -> int:
        return self.get("int_mod")

    @property
    def wis_mod(self) -> int:
        return self.get("wis_mod")

    @property
    def cha_mod(self) -> int:
        return self.get("cha_mod")

    @property
    def ac(self) -> int:
        return self.get("ac")

    @property
    def fort(self) -> int:
        return self.get("fort_save")

    @property
    def ref(self) -> int:
        return self.get("ref_save")

    @property
    def will(self) -> int:
        return self.get("will_save")

    @property
    def bab(self) -> int:
        return self.get("bab")

    @property
    def initiative(self) -> int:
        return self.get("initiative")

    @property
    def hp_max(self) -> int:
        return self.get("hp_max")

    def __repr__(self) -> str:
        lvl = self.total_level
        return f"Character({self.name!r}, level={lvl}, race={self.race!r})"
