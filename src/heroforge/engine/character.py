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
  - No YAML serialisation (that lives in persistence.py)
  - No rules data loading (that lives in the rules registry)
  - No prerequisite checking (engine/prerequisites.py)

Public API:
  Ability             — StrEnum for ability scores
  Alignment           — StrEnum for alignments
  Save                — StrEnum for saving throws
  BuffState           — persisted per-buff toggle state
  Character           — the main class
  CharacterError      — raised on invalid operations
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any, Callable

    from heroforge.engine.bonus import BonusEntry
    from heroforge.engine.effects import BuffDefinition
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


class Ability(StrEnum):
    STR = "str"
    DEX = "dex"
    CON = "con"
    INT = "int"
    WIS = "wis"
    CHA = "cha"


class Alignment(StrEnum):
    LAWFUL_GOOD = "lawful_good"
    LAWFUL_NEUTRAL = "lawful_neutral"
    LAWFUL_EVIL = "lawful_evil"
    NEUTRAL_GOOD = "neutral_good"
    NEUTRAL = "neutral"
    NEUTRAL_EVIL = "neutral_evil"
    CHAOTIC_GOOD = "chaotic_good"
    CHAOTIC_NEUTRAL = "chaotic_neutral"
    CHAOTIC_EVIL = "chaotic_evil"


class Save(StrEnum):
    FORT = "fort"
    REF = "ref"
    WILL = "will"


SAVE_ABILITY: dict[Save, Ability] = {
    Save.FORT: Ability.CON,
    Save.REF: Ability.DEX,
    Save.WILL: Ability.WIS,
}


@dataclass
class ClassLevel:
    """
    One class entry (cumulative levels per class).

    TODO: remove this legacy dataclass. New code
    should use CharacterLevel and Character.levels.
    """

    class_name: str
    level: int
    hp_rolls: list[int] = field(default_factory=list)
    bab_contribution: int = 0
    fort_contribution: int = 0
    ref_contribution: int = 0
    will_contribution: int = 0


@dataclass
class CharacterLevel:
    """
    One character level (e.g. level 3 = Rogue).

    Per-character-level model: each entry represents
    exactly one level taken in a specific class.
    """

    character_level: int  # 1-based
    class_name: str
    hp_roll: int = 0
    skill_ranks: dict[str, int] = field(default_factory=dict)
    # skill_ranks stores skill points SPENT at this
    # level (not ranks gained). For class skills
    # 1 point = 1 rank; for cross-class 2 pts = 1 rank.
    feats: list[dict] = field(default_factory=list)
    # feats acquired at this level. Each entry:
    #   {"name": str, "source": str,
    #    "parameter": int|None}
    spells_learned: dict = field(default_factory=dict)
    # spells learned at this level (spontaneous casters)
    # keyed by spell level: {0: ["Detect Magic"], 1: [...]}
    spells_replaced: list[dict] = field(default_factory=list)
    # spells swapped at this level:
    #   [{"old": str, "new": str}]
    ability_bump: Ability | None = None
    # Ability score increase at every 4th character level
    # (4, 8, 12, …). One of the Ability enum members
    # or None if not yet chosen / not a bump level.
    inherent_bumps: dict[Ability, int] = field(default_factory=dict)
    # Inherent bonuses consumed at this level (e.g.
    # Tomes/Manuals). Maps Ability -> bonus value.


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
        self._ability_scores: dict[Ability, int] = {ab: 10 for ab in Ability}
        self.levels: list[CharacterLevel] = []
        self._cached_class_levels: list[ClassLevel] = []
        self._class_registry_ref: Any = None
        self._feat_registry_ref: Any = None
        self.race: str = ""
        self.alignment: Alignment | str = ""
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
        self._race_favored_class: str = "any"

        self.enabled_sources: list[str] = ["PHB"]
        self.notes: str = ""

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
        pools = [
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
        for pk in pools:
            pool = BonusPool(pk)
            self._pools[pk] = pool
            g.register_pool(pool)

        # ---- Ability scores ------------------------------------------------
        # Each score has a base (set by _ability_scores)
        # + level-up bumps + inherent bonuses + pool bonuses.
        for ab in Ability:
            base = self._ability_scores[ab]
            pool_key = f"{ab}_score"

            def make_score_compute(
                ability: Ability,
            ) -> Callable[[int], int]:
                def compute(bt: int) -> int:
                    return (
                        self._ability_scores[ability]
                        + self._level_bump_total(ability)
                        + self._inherent_bonus_total(ability)
                        + bt
                    )

                return compute

            g.register_node(
                StatNode(
                    key=f"{ab}_score",
                    base=base,
                    pools=[pool_key],
                    compute=make_score_compute(ab),
                    description=f"{ab.upper()} score",
                )
            )

        # ---- Ability modifiers ---------------------------------------------
        for ab in Ability:
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
                pools=["bab_misc"],
                compute=lambda bt: self._compute_bab() + bt,
                description="Base Attack Bonus",
            )
        )

        # ---- Saving throws -------------------------------------------------
        # Base saves come from class levels; ability mod feeds in as input.
        for save, ab in SAVE_ABILITY.items():
            pool_key = f"{save}_save"
            g.register_node(
                StatNode(
                    key=f"{save}_save",
                    inputs=[f"{ab}_mod"],
                    pools=[pool_key],
                    compute=lambda inputs, bt, s=save: (
                        self._compute_base_save(s)
                        + inputs[f"{SAVE_ABILITY[s]}_mod"]
                        + bt
                    ),
                    description=(f"{save.capitalize()} save"),
                )
            )

        # ---- AC components -------------------------------------------------
        # max_dex_bonus: set by armour; -1 = uncapped
        g.register_node(
            StatNode(
                key="max_dex_bonus",
                compute=lambda bt: self._compute_max_dex_bonus() + bt,
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

        # Total AC: 10 + dex_contribution + size + pool
        g.register_node(
            StatNode(
                key="ac",
                inputs=["ac_dex_contribution"],
                pools=["ac"],
                compute=lambda inputs, bt: (
                    10
                    + inputs["ac_dex_contribution"]
                    + self._compute_size_mod_attack()
                    + bt
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
                pools=["initiative"],
                compute=compute_sum,
                description="Initiative modifier",
            )
        )

        # ---- Speed ---------------------------------------------------------
        g.register_node(
            StatNode(
                key="speed",
                pools=["speed"],
                compute=lambda bt: self._compute_base_speed() + bt,
                description="Movement speed (ft)",
            )
        )

        # ---- HP maximum ----------------------------------------------------
        g.register_node(
            StatNode(
                key="hp_max",
                inputs=["con_mod"],
                pools=["hp_bonus"],
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
                pools=["sr"],
                compute=compute_sum,
                description="Spell Resistance",
            )
        )

        # ---- Melee attack (primary) -----------------------
        # Iterative attacks are computed by attack_iteratives().
        # This node gives the primary attack bonus.
        g.register_node(
            StatNode(
                key="attack_melee",
                inputs=["bab", "str_mod"],
                pools=["attack_melee", "attack_all"],
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
                pools=["attack_ranged", "attack_all"],
                compute=lambda inputs, bt: (
                    inputs["bab"]
                    + inputs["dex_mod"]
                    + self._compute_size_mod_attack()
                    + bt
                ),
                description="Primary ranged attack bonus",
            )
        )

        # ---- Grapple modifier ----------------------------
        g.register_node(
            StatNode(
                key="grapple",
                inputs=["bab", "str_mod"],
                pools=["grapple"],
                compute=lambda inputs, bt: (
                    inputs["bab"]
                    + inputs["str_mod"]
                    + self._compute_size_mod_grapple()
                    + bt
                ),
                description="Grapple modifier",
            )
        )

        # ---- Damage (STR bonus; weapon dice handled by equipment)
        g.register_node(
            StatNode(
                key="damage_str_bonus",
                inputs=["str_mod"],
                pools=["damage_melee", "damage_all"],
                compute=compute_sum,
                description="STR bonus to melee damage",
            )
        )

    # -----------------------------------------------------------------------
    # Internal computation helpers
    # (called by lambdas in the stat graph; not part of public API)
    # -----------------------------------------------------------------------

    def _compute_bab(self) -> int:
        reg = self._class_registry_ref
        if reg is not None:
            total = 0
            for cn, lvl in self.class_level_map.items():
                defn = reg.get(cn)
                if defn is not None:
                    total += defn.bab_contribution(lvl)
            return total
        # Fallback: use cached ClassLevel contributions
        cached = getattr(self, "_cached_class_levels", [])
        return sum(cl.bab_contribution for cl in cached)

    def _compute_base_save(self, save: str) -> int:
        reg = self._class_registry_ref
        method = f"{save}_contribution"
        if reg is not None:
            total = 0
            for cn, lvl in self.class_level_map.items():
                defn = reg.get(cn)
                if defn is not None:
                    total += getattr(defn, method)(lvl)
            return total
        attr = f"{save}_contribution"
        cached = getattr(self, "_cached_class_levels", [])
        return sum(getattr(cl, attr, 0) for cl in cached)

    def _compute_max_dex_bonus(self) -> int:
        """
        Returns the max DEX bonus allowed by armour.
        -1 means no cap."""
        armor_item = self.equipment.get("armor")
        if armor_item is None:
            return -1
        return armor_item.get("max_dex_bonus", -1)

    def _compute_hp_from_rolls(self) -> int:
        return sum(lv.hp_roll for lv in self.levels)

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

    def _compute_size_mod_grapple(self) -> int:
        SIZE_GRAPPLE_MOD = {
            "Fine": -16,
            "Diminutive": -12,
            "Tiny": -8,
            "Small": -4,
            "Medium": 0,
            "Large": 4,
            "Huge": 8,
            "Gargantuan": 12,
            "Colossal": 16,
        }
        return SIZE_GRAPPLE_MOD.get(self.size, 0)

    def _compute_size_mod_hide(self) -> int:
        SIZE_HIDE_MOD = {
            "Fine": 16,
            "Diminutive": 12,
            "Tiny": 8,
            "Small": 4,
            "Medium": 0,
            "Large": -4,
            "Huge": -8,
            "Gargantuan": -12,
            "Colossal": -16,
        }
        return SIZE_HIDE_MOD.get(self.size, 0)

    def carrying_capacity(
        self,
    ) -> tuple[int, int, int]:
        """
        Return (light, medium, heavy) load in lbs.

        Uses the SRD Table 9-1 for STR-based carrying
        capacity, with size multipliers for non-Medium
        creatures.
        """
        # SRD carrying capacity by STR score (1-29)
        _TABLE: list[tuple[int, int, int]] = [
            (0, 0, 0),  # STR 0 (placeholder)
            (3, 6, 10),  # STR 1
            (6, 13, 20),  # STR 2
            (10, 20, 30),  # STR 3
            (13, 26, 40),  # STR 4
            (16, 33, 50),  # STR 5
            (20, 40, 60),  # STR 6
            (23, 46, 70),  # STR 7
            (26, 53, 80),  # STR 8
            (30, 60, 90),  # STR 9
            (33, 66, 100),  # STR 10
            (38, 76, 115),  # STR 11
            (43, 86, 130),  # STR 12
            (50, 100, 150),  # STR 13
            (58, 116, 175),  # STR 14
            (66, 133, 200),  # STR 15
            (76, 153, 230),  # STR 16
            (86, 173, 260),  # STR 17
            (100, 200, 300),  # STR 18
            (116, 233, 350),  # STR 19
            (133, 266, 400),  # STR 20
            (153, 306, 460),  # STR 21
            (173, 346, 520),  # STR 22
            (200, 400, 600),  # STR 23
            (233, 466, 700),  # STR 24
            (266, 533, 800),  # STR 25
            (306, 613, 920),  # STR 26
            (346, 693, 1040),  # STR 27
            (400, 800, 1200),  # STR 28
            (466, 933, 1400),  # STR 29
        ]
        _SIZE_MULT = {
            "Fine": 1 / 8,
            "Diminutive": 1 / 4,
            "Tiny": 1 / 2,
            "Small": 3 / 4,
            "Medium": 1,
            "Large": 2,
            "Huge": 4,
            "Gargantuan": 8,
            "Colossal": 16,
        }
        str_score = self.get("str_score")
        if str_score <= 0:
            return (0, 0, 0)
        if str_score < len(_TABLE):
            light, med, heavy = _TABLE[str_score]
        else:
            # STR > 29: ×4 per 10 above 20
            base_idx = 20 + (str_score - 20) % 10
            if base_idx >= len(_TABLE):
                base_idx = 29
            light, med, heavy = _TABLE[base_idx]
            mult = 4 ** ((str_score - 20) // 10)
            light *= mult
            med *= mult
            heavy *= mult
        size_mult = _SIZE_MULT.get(self.size, 1)
        return (
            int(light * size_mult),
            int(med * size_mult),
            int(heavy * size_mult),
        )

    def touch_ac(self) -> int:
        """
        Touch AC = 10 + DEX mod + dodge + deflection
        + untyped + luck/insight/sacred/profane/morale/
        competence. Excludes armor, shield, natural armor.
        """
        from collections import defaultdict

        ac_pool = self.get_pool("ac")
        if ac_pool is None:
            return 10 + self.dex_mod

        touch = 10 + self.get("ac_dex_contribution")
        active = ac_pool.active_entries(self)
        from heroforge.engine.bonus import (
            ALWAYS_STACKING,
            BonusType,
        )

        touch_types = {
            BonusType.DODGE,
            BonusType.DEFLECTION,
            BonusType.UNTYPED,
            BonusType.LUCK,
            BonusType.INSIGHT,
            BonusType.SACRED,
            BonusType.PROFANE,
            BonusType.MORALE,
            BonusType.COMPETENCE,
        }

        stacking = 0
        typed: dict = defaultdict(list)
        for e in active:
            if e.bonus_type not in touch_types:
                continue
            if e.bonus_type in ALWAYS_STACKING:
                stacking += e.value
            else:
                typed[e.bonus_type].append(e.value)
        for vals in typed.values():
            stacking += max(vals)
        return touch + stacking

    def has_class_feature(self, feature_key: str) -> bool:
        """Check if this character has a class feature."""
        reg = self._class_registry_ref
        if reg is None:
            return False
        for cn, lvl in self.class_level_map.items():
            defn = reg.get(cn)
            if defn is None:
                continue
            for feat in defn.class_features:
                if feat.feature == feature_key and feat.level <= lvl:
                    return True
        return False

    def flatfooted_ac(self) -> int:
        """
        Flat-footed AC = AC without DEX or dodge bonuses.
        If character has Uncanny Dodge, retains DEX bonus.
        """
        from collections import defaultdict

        ac_pool = self.get_pool("ac")
        if ac_pool is None:
            if self.has_class_feature("uncanny_dodge"):
                return 10 + self.dex_mod
            return 10

        has_ud = self.has_class_feature("uncanny_dodge")

        flat = 10
        if has_ud:
            flat += self.get("ac_dex_contribution")

        active = ac_pool.active_entries(self)
        from heroforge.engine.bonus import (
            ALWAYS_STACKING,
            BonusType,
        )

        excluded = {BonusType.DODGE}

        stacking = 0
        typed: dict = defaultdict(list)
        for e in active:
            if e.bonus_type in excluded:
                continue
            if e.bonus_type in ALWAYS_STACKING:
                stacking += e.value
            else:
                typed[e.bonus_type].append(e.value)
        for vals in typed.values():
            if vals:
                stacking += max(vals)
        return flat + stacking

    # -----------------------------------------------------------------------
    # Public properties
    # -----------------------------------------------------------------------

    @property
    def total_level(self) -> int:
        return len(self.levels)

    @property
    def class_level_map(self) -> dict[str, int]:
        """{'Fighter': 5, 'Rogue': 3} cumulative."""
        counts: dict[str, int] = {}
        for lv in self.levels:
            counts[lv.class_name] = counts.get(lv.class_name, 0) + 1
        return counts

    @property
    def class_levels(self) -> list[ClassLevel]:
        """
        Legacy compat: aggregate levels into
        cumulative ClassLevel objects."""
        counts: dict[str, int] = {}
        hp_map: dict[str, list[int]] = {}
        for lv in self.levels:
            cn = lv.class_name
            counts[cn] = counts.get(cn, 0) + 1
            hp_map.setdefault(cn, []).append(lv.hp_roll)
        result: list[ClassLevel] = []
        reg = self._class_registry_ref
        for cn, lvl in counts.items():
            cl = ClassLevel(
                class_name=cn,
                level=lvl,
                hp_rolls=hp_map.get(cn, []),
            )
            if reg is not None:
                defn = reg.get(cn)
                if defn is not None:
                    cl.bab_contribution = defn.bab_contribution(lvl)
                    cl.fort_contribution = defn.fort_contribution(lvl)
                    cl.ref_contribution = defn.ref_contribution(lvl)
                    cl.will_contribution = defn.will_contribution(lvl)
            result.append(cl)
        return result

    @class_levels.setter
    def class_levels(self, value: list[ClassLevel]) -> None:
        """
        Legacy compat: set levels from ClassLevel
        objects (expands into per-level entries).
        Also caches the original ClassLevel data for
        fallback BAB/save computation without registry.
        """
        self._cached_class_levels = list(value)
        new_levels: list[CharacterLevel] = []
        idx = 1
        for cl in value:
            for i in range(cl.level):
                hp = cl.hp_rolls[i] if i < len(cl.hp_rolls) else 0
                new_levels.append(
                    CharacterLevel(
                        character_level=idx,
                        class_name=cl.class_name,
                        hp_roll=hp,
                    )
                )
                idx += 1
        self.levels = new_levels

    @property
    def size(self) -> str:
        """Current size category. Overridden by templates."""
        return getattr(self, "_size_override", None) or self._base_size

    @property
    def _base_size(self) -> str:
        """Base size from race.  Defaults to Medium until race is loaded."""
        return getattr(self, "_race_size", "Medium")

    def attack_iteratives(self, melee: bool = True) -> list[int]:
        """
        Compute iterative attack bonuses.

        In 3.5e, you get extra attacks at -5 each
        when BAB reaches +6, +11, +16.
        Returns list like [+11, +6, +1].
        """
        key = "attack_melee" if melee else "attack_ranged"
        base = self.get(key)
        bab = self.bab
        attacks = [base]
        extra_bab = bab - 5
        while extra_bab >= 1:
            attacks.append(base - (bab - extra_bab))
            extra_bab -= 5
        return attacks

    def multiclass_xp_penalty(self) -> bool:
        """
        Check if character has multiclass XP penalty.

        In 3.5e, if any two non-favored, non-prestige
        classes differ by more than 1 level, there is
        an XP penalty.
        """
        clm = self.class_level_map
        if len(clm) <= 1:
            return False
        # Determine favored class from race
        fav = self._race_favored_class
        if fav == "any":
            # "any" = highest-level class is favored
            favored = max(clm, key=lambda c: clm[c])
        elif fav in clm:
            favored = fav
        else:
            favored = None
        # Check non-favored, non-prestige levels
        reg = self._class_registry_ref
        levels = []
        for cn, lvl in clm.items():
            if cn == favored:
                continue
            if reg:
                defn = reg.get(cn)
                if defn and defn.is_prestige:
                    continue
            levels.append(lvl)
        if len(levels) <= 1:
            return False
        return max(levels) - min(levels) > 1

    # -----------------------------------------------------------------------
    # Ability score mutation
    # -----------------------------------------------------------------------

    def set_ability_score(self, ability: Ability, value: int) -> None:
        """Set a base ability score and cascade."""
        ability = Ability(ability)
        if not (1 <= value <= 99):
            raise CharacterError(
                f"Ability score must be between 1 and 99, got {value}."
            )

        self._ability_scores[ability] = value
        # The score node's compute fn reads directly from _ability_scores,
        # so we just need to invalidate it.
        self._graph.invalidate(f"{ability}_score")
        self._notify({f"{ability}_score", f"{ability}_mod"})

    def get_ability_score(self, ability: Ability) -> int:
        """Return total ability score (base + all)."""
        return self._graph.resolve(f"{ability}_score", self)

    def get_ability_modifier(self, ability: Ability) -> int:
        return self._graph.resolve(f"{ability}_mod", self)

    # ---------------------------------------------------------------
    # Level-up ability bumps & inherent bonuses
    # ---------------------------------------------------------------

    def _level_bump_total(self, ability: Ability) -> int:
        """Count +1 bumps to *ability* across all levels."""
        return sum(lv.ability_bump == ability for lv in self.levels)

    def _inherent_bonus_total(self, ability: Ability) -> int:
        """
        Effective inherent bonus for *ability*.

        Per 3.5e, inherent bonuses don't stack — only
        the highest applies, capped at +5.
        """
        best = 0
        for lv in self.levels:
            val = lv.inherent_bumps.get(ability, 0)
            best = max(best, val)
        return min(best, 5)

    def _inherent_bonus_at_level(
        self, ability: Ability, char_level: int
    ) -> int:
        """
        Highest inherent bonus for *ability* from
        levels up to and including *char_level*."""
        best = 0
        for lv in self.levels[:char_level]:
            val = lv.inherent_bumps.get(ability, 0)
            best = max(best, val)
        return min(best, 5)

    def int_mod_at_level(self, char_level: int) -> int:
        """
        INT modifier using base + bumps/inherent up
        to *char_level*.  Used for skill-point budgets
        so that later INT changes are not retroactive.
        """
        base = self._ability_scores[Ability.INT]
        bumps = sum(
            lv.ability_bump == Ability.INT for lv in self.levels[:char_level]
        )
        inherent = self._inherent_bonus_at_level(Ability.INT, char_level)
        return (base + bumps + inherent - 10) // 2

    def set_level_ability_bump(
        self,
        char_level: int,
        ability: Ability | None,
    ) -> None:
        """
        Set or clear the ability bump at
        *char_level*.

        Invalidates affected ability score node(s).
        """
        if ability is None:
            return

        ability = Ability(ability)
        idx = char_level - 1
        if idx < 0 or idx >= len(self.levels):
            raise CharacterError(f"No level {char_level} to set bump on")
        old = self.levels[idx].ability_bump
        self.levels[idx].ability_bump = ability
        changed: set[str] = set()
        for ab in {old, ability} - {None}:
            self._graph.invalidate(f"{ab}_score")
            changed.add(f"{ab}_score")
            changed.add(f"{ab}_mod")
        if changed:
            self._notify(changed)

    def add_inherent_bump(
        self,
        char_level: int,
        ability: Ability,
        value: int,
    ) -> None:
        """
        Record an inherent bonus consumed at
        *char_level* (e.g. a Tome of Clear Thought).
        """
        idx = char_level - 1
        if idx < 0 or idx >= len(self.levels):
            raise CharacterError(f"No level {char_level}")
        if not 1 <= value <= 5:
            raise CharacterError("Inherent bonus must be 1-5")
        self.levels[idx].inherent_bumps[ability] = value
        self._graph.invalidate(f"{ability}_score")
        self._notify({f"{ability}_score", f"{ability}_mod"})

    def remove_inherent_bump(
        self,
        char_level: int,
        ability: Ability,
    ) -> None:
        """
        Remove an inherent bonus entry at
        *char_level*.
        """
        idx = char_level - 1
        if idx < 0 or idx >= len(self.levels):
            raise CharacterError(f"No level {char_level}")
        self.levels[idx].inherent_bumps.pop(ability, None)
        self._graph.invalidate(f"{ability}_score")
        self._notify({f"{ability}_score", f"{ability}_mod"})

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
                if pk in node.pools:
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

    def _apply_feat_pool_bonuses(
        self,
        feat_name: str,
        buff_defn: "BuffDefinition",
    ) -> None:
        """Apply an always-on feat directly to pools."""
        pairs = buff_defn.pool_entries(0, self)
        source_key = f"feat:{feat_name}"
        affected: set[str] = set()
        pool_map: dict[str, list] = {}
        for pool_key, entry in pairs:
            pool_map.setdefault(pool_key, []).append(entry)
        for pool_key, entries in pool_map.items():
            p = self._pools.get(pool_key)
            if p is None:
                continue
            p.set_source(source_key, entries)
            affected.add(pool_key)
        invalidated: set[str] = set()
        for pk in affected:
            self._graph.invalidate_pool(pk)
            for node in self._graph._nodes.values():
                if pk in node.pools:
                    invalidated.add(node.key)
                    invalidated.update(self._graph.dependents_of(node.key))
        if invalidated:
            self._notify(invalidated)

    def _remove_feat_pool_bonuses(
        self,
        feat_name: str,
        buff_defn: "BuffDefinition",
    ) -> None:
        """Remove an always-on feat's bonuses."""
        pairs = buff_defn.pool_entries(0, self)
        source_key = f"feat:{feat_name}"
        affected: set[str] = set()
        seen: set[str] = set()
        for pool_key, _entry in pairs:
            if pool_key in seen:
                continue
            seen.add(pool_key)
            p = self._pools.get(pool_key)
            if p is None:
                continue
            p.clear_source(source_key)
            affected.add(pool_key)
        invalidated: set[str] = set()
        for pk in affected:
            self._graph.invalidate_pool(pk)
            for node in self._graph._nodes.values():
                if pk in node.pools:
                    invalidated.add(node.key)
                    invalidated.update(self._graph.dependents_of(node.key))
        if invalidated:
            self._notify(invalidated)

    def add_feat(
        self,
        feat_name: str,
        defn: FeatDefinition | None = None,
        *,
        level: int,
        source: str,
        parameter: int | None = None,
    ) -> None:
        """
        Add a feat to this character.

        level:  character level at which feat is acquired.
        source: why the feat was granted (e.g.
                'character', 'fighter_bonus',
                'human_bonus', 'class:Ranger',
                'template:Half-Dragon').

        For always_on feats: immediately applies the feat's
        stat effects directly to the relevant pools (never
        shown in the Buffs panel).

        For conditional feats: registers the buff definition
        so it can be toggled via toggle_buff().  Does NOT
        activate it — the user does that via the Buffs panel.

        For passive feats: records the feat name only; no
        pool effects.

        defn: the FeatDefinition (from FeatsLoader).  If
              None, the feat is recorded but no effects are
              applied.
        """
        # Avoid duplicate feat entries
        existing = {f.get("name") for f in self.feats}
        if feat_name in existing:
            return

        entry: dict = {
            "name": feat_name,
            "level": level,
            "source": source,
        }
        if parameter is not None:
            entry["parameter"] = parameter
        self.feats.append(entry)

        # Also store in the matching CharacterLevel
        # (skip if already present, e.g. during load)
        for lv in self.levels:
            if lv.character_level == level:
                names = {f.get("name") for f in lv.feats}
                if feat_name not in names:
                    lv.feats.append(entry)
                break

        if defn is None:
            return

        # Apply effects based on feat kind
        # Compare kind using .value to handle FeatKind enum or plain string
        kind_val = getattr(defn, "kind", None)
        if hasattr(kind_val, "value"):
            kind_val = kind_val.value

        if kind_val == "always_on" and defn.buff_definition is not None:
            self._apply_feat_pool_bonuses(feat_name, defn.buff_definition)

        elif kind_val == "conditional" and defn.buff_definition is not None:
            # Register but do NOT activate — user toggles from Buffs panel
            pairs = defn.buff_definition.pool_entries(0, self)
            if feat_name not in self._buff_states:
                self.register_buff_definition(feat_name, pairs)

    def remove_feat(
        self,
        feat_name: str,
        defn: FeatDefinition | None = None,
    ) -> None:
        """
        Remove a feat from this character.

        Reverses always_on stat effects and deactivates
        any conditional buff that was active.
        """
        self.feats = [f for f in self.feats if f.get("name") != feat_name]

        if defn is None:
            return

        kind_val = getattr(defn, "kind", None)
        if hasattr(kind_val, "value"):
            kind_val = kind_val.value

        if kind_val == "always_on" and defn.buff_definition is not None:
            self._remove_feat_pool_bonuses(feat_name, defn.buff_definition)
        elif kind_val == "conditional" and feat_name in self._buff_states:
            self.toggle_buff(feat_name, False)
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
        Replace class levels (legacy API).

        Expands ClassLevel objects into per-character-level
        CharacterLevel entries via the class_levels setter.
        """
        self.class_levels = levels
        self._invalidate_class_stats()

    def _invalidate_class_stats(self) -> None:
        """Invalidate all stats derived from class levels."""
        self._apply_class_feature_effects()
        self._graph.invalidate("bab")
        self._graph.invalidate("fort_save")
        self._graph.invalidate("ref_save")
        self._graph.invalidate("will_save")
        self._graph.invalidate("hp_max")
        # Levels may carry ability bumps / inherent
        # bonuses, so invalidate all ability scores.
        for ab in Ability:
            self._graph.invalidate(f"{ab}_score")
        self._notify(
            {
                "bab",
                "fort_save",
                "ref_save",
                "will_save",
                "hp_max",
                "attack_melee",
                "attack_ranged",
                "str_score",
                "dex_score",
                "con_score",
                "int_score",
                "wis_score",
                "cha_score",
            }
        )

    def _apply_class_feature_effects(self) -> None:
        """
        Auto-apply always-on class feature effects
        based on current class levels.

        Called whenever class levels change. Clears
        stale features and applies current ones.
        """
        from heroforge.engine.effects import (
            BuffCategory,
            build_buff_from_effects,
        )

        reg = self._class_registry_ref
        if reg is None:
            return

        # Track which feature keys are currently valid
        active_keys: set[str] = set()

        for cn, lvl in self.class_level_map.items():
            defn = reg.get(cn)
            if defn is None:
                continue
            for feat in defn.class_features:
                if feat.level > lvl:
                    continue
                if not feat.effects:
                    continue
                # Skip toggleable features (have a
                # buff_name) — those are user-activated
                if feat.buff_name:
                    continue
                src = f"classfeature:{cn}:{feat.feature}"
                active_keys.add(src)
                buff = build_buff_from_effects(
                    name=src,
                    category=BuffCategory.CLASS,
                    effects_raw=list(feat.effects),
                )
                if buff is None:
                    continue
                pairs = buff.pool_entries(0, self)
                pool_map: dict[str, list] = {}
                for pk, entry in pairs:
                    pool_map.setdefault(pk, []).append(entry)
                for pk, entries in pool_map.items():
                    p = self._pools.get(pk)
                    if p is None:
                        continue
                    p.set_source(src, entries)
                    self._graph.invalidate_pool(pk)

        # Clear features that no longer apply
        prefix = "classfeature:"
        for pool in self._pools.values():
            for sk in pool.source_keys():
                if sk.startswith(prefix) and sk not in active_keys:
                    pool.clear_source(sk)

    def add_level(self, class_name: str, hp_roll: int) -> None:
        """Append a new character level."""
        idx = len(self.levels) + 1
        self.levels.append(
            CharacterLevel(
                character_level=idx,
                class_name=class_name,
                hp_roll=hp_roll,
            )
        )
        self._invalidate_class_stats()

    def remove_last_level(self) -> None:
        """Remove the most recent character level."""
        if not self.levels:
            return
        self.levels.pop()
        self._invalidate_class_stats()

    def set_level_class(self, char_level: int, class_name: str) -> None:
        """Change which class a specific level uses."""
        idx = char_level - 1
        if 0 <= idx < len(self.levels):
            self.levels[idx].class_name = class_name
            self._invalidate_class_stats()

    def set_level_hp(self, char_level: int, hp_roll: int) -> None:
        """Change the HP roll for a specific level."""
        idx = char_level - 1
        if 0 <= idx < len(self.levels):
            self.levels[idx].hp_roll = hp_roll
            self._graph.invalidate("hp_max")
            self._notify({"hp_max"})

    def set_level_skill_ranks(
        self,
        char_level: int,
        skill_ranks: dict[str, int],
    ) -> None:
        """Set skill point allocation for one level."""
        idx = char_level - 1
        if 0 <= idx < len(self.levels):
            self.levels[idx].skill_ranks = skill_ranks
            self._notify({"skills"})

    def skill_points_for_level(self, char_level: int) -> int:
        """
        Compute skill point budget at a level.

        Formula: (skills_per_level + INT_mod),
        x4 at level 1, +1 for humans, min 1.
        """
        idx = char_level - 1
        if idx < 0 or idx >= len(self.levels):
            return 0
        lv = self.levels[idx]
        reg = self._class_registry_ref
        base = 2  # default
        if reg is not None:
            defn = reg.get(lv.class_name)
            if defn is not None:
                base = defn.skills_per_level
        int_mod = self.int_mod_at_level(char_level)
        pts = base + int_mod
        # Humans get +1 skill point per level
        if self.race == "Human":
            pts += 1
        pts = max(pts, 1)
        if char_level == 1:
            pts *= 4
        return pts

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

    def has_feat(self, feat_name: str) -> bool:
        return any(f.get("name", "") == feat_name for f in self.feats)

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

    def validate(self) -> list[str]:
        """
        Check character legality.

        Returns a list of issues (empty = valid).
        """
        issues: list[str] = []
        if not self.race:
            issues.append("No race selected")
        if not self.levels:
            issues.append("No class levels")
        if self.multiclass_xp_penalty():
            issues.append(
                "Multiclass XP penalty: class levels differ by more than 1"
            )
        # Check skill rank caps
        from heroforge.engine.skills import (
            max_skill_ranks,
        )

        for skill_name, ranks in self.skills.items():
            # Use total_level for max rank check
            cap = max_skill_ranks(self.total_level, True)
            if ranks > cap:
                issues.append(
                    f"{skill_name}: {ranks} ranks exceeds max {int(cap)}"
                )
        return issues

    def __repr__(self) -> str:
        lvl = self.total_level
        return f"Character({self.name!r}, level={lvl}, race={self.race!r})"
