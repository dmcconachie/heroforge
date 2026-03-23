"""
engine/stat.py
--------------
The reactive stat graph.  Every derived character statistic is a StatNode.
Nodes declare their dependencies; when an input changes, the node is marked
dirty and recomputed lazily on next access.

Design goals:
  - No circular dependencies (enforced at registration time).
  - Lazy evaluation: nothing is recomputed until asked for.
  - Dirty cascading: marking a node dirty also marks every node that
    depends on it, transitively.
  - BonusPool integration: each node can have zero or more BonusPools
    whose aggregate is included in the computation.
  - Pure Python: no GUI imports, fully testable in isolation.

Public API:
  StatNode       — a single computable stat
  StatGraph      — registry of all nodes; handles cascade and resolution
  StatError      — raised on cycle detection or missing dependency
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Callable

    from heroforge.engine.bonus import BonusPool
    from heroforge.engine.character import Character


class StatError(Exception):
    pass


# ---------------------------------------------------------------------------
# StatNode
# ---------------------------------------------------------------------------


@dataclass
class StatNode:
    """
    A single computed statistic in the character stat graph.

    Attributes
    ----------
    key         : Unique string identifier, e.g. "str_mod", "attack_melee".
    base        : Optional hard-coded base value (e.g. 10 for a base ability
                  score before racial modifiers).  If None the node has no
                  intrinsic base and must compute entirely from inputs/pools.
    inputs      : Keys of other StatNodes whose resolved values are passed
                  to `compute` as a dict.
    compute     : fn(input_values: dict[str, int], bonus_total: int) -> int
                  Receives resolved values of all declared inputs, plus the
                  pre-aggregated total of all attached BonusPools.
                  Default: base + bonus_total (simple accumulator).
    pools   : Keys of BonusPools (looked up in StatGraph.pools) that
                  feed into this node's bonus_total.
    description : Human-readable description for UI tooltips.
    """

    key: str
    base: int | None = None
    inputs: list[str] = field(default_factory=list)
    compute: str | Callable[[dict[str, int], int], int] | None = field(
        default=None, repr=False
    )
    pools: list[str] = field(default_factory=list)
    description: str = ""
    sheet: int = 0
    save_name: str = ""

    # Runtime state — not part of identity
    _cache: int | None = field(
        default=None, init=False, repr=False, compare=False
    )
    _dirty: bool = field(default=True, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        # Install the default compute function if none was provided.
        if self.compute is None:
            base = self.base if self.base is not None else 0
            self.compute = lambda _inputs, bonus_total: base + bonus_total

    def invalidate(self) -> None:
        """Mark this node as needing recomputation."""
        self._dirty = True
        self._cache = None

    @property
    def is_dirty(self) -> bool:
        return self._dirty


# ---------------------------------------------------------------------------
# StatGraph
# ---------------------------------------------------------------------------


class StatGraph:
    """
    Registry of all StatNodes and BonusPools for a single character.

    Responsibilities:
      - Register nodes and pools.
      - Detect dependency cycles at registration time.
      - Resolve a node's value, computing lazily and caching.
      - Cascade dirty flags when a node is invalidated.
      - Track which nodes depend on which (reverse adjacency) so that
        invalidating a node also invalidates all downstream dependents.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, StatNode] = {}
        self._pools: dict[str, "BonusPool"] = {}
        # Reverse adjacency: dependents[X] = {nodes that list X in their inputs}
        self._dependents: dict[str, set[str]] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_node(self, node: StatNode) -> None:
        """
        Add a StatNode to the graph.
        Raises StatError if a node with the same key is already registered
        or if adding this node would create a dependency cycle.
        """
        if node.key in self._nodes:
            raise StatError(f"Node {node.key!r} is already registered.")

        # Verify all declared inputs exist (or will exist — allow forward
        # references only if added in dependency order, enforced here).
        for dep_key in node.inputs:
            if dep_key not in self._nodes:
                raise StatError(
                    f"Node {node.key!r} declares input {dep_key!r} "
                    f"which is not yet registered."
                )

        self._nodes[node.key] = node

        # Build reverse adjacency.
        self._dependents.setdefault(node.key, set())
        for dep_key in node.inputs:
            self._dependents.setdefault(dep_key, set()).add(node.key)

        # Cycle check: the graph must remain a DAG.
        self._assert_no_cycle(node.key)

    def register_pool(self, pool: "BonusPool") -> None:
        """
        Register a BonusPool.  The pool's stat_key is used to look it up
        when nodes declare it in their pools.
        """
        self._pools[pool.stat_key] = pool

    def node(self, key: str) -> StatNode:
        """Return the StatNode for key, raising StatError if absent."""
        try:
            return self._nodes[key]
        except KeyError:
            raise StatError(
                f"No stat node registered for key {key!r}."
            ) from None

    def pool(self, key: str) -> "BonusPool":
        """Return the BonusPool for key, raising StatError if absent."""
        try:
            return self._pools[key]
        except KeyError:
            raise StatError(
                f"No bonus pool registered for key {key!r}."
            ) from None

    def has_node(self, key: str) -> bool:
        return key in self._nodes

    def has_pool(self, key: str) -> bool:
        return key in self._pools

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def resolve(self, key: str, character: "Character | None" = None) -> int:
        """
        Return the current value of stat `key`.

        If the node is dirty it is recomputed from its inputs and pools,
        then cached.  If it is clean the cached value is returned directly.

        `character` is passed through to BonusPools so conditional
        BonusEntries (e.g. "only while raging") can be evaluated.
        """
        node = self.node(key)

        if not node._dirty and node._cache is not None:
            return node._cache

        # Resolve all inputs first (recursive, but DAG guarantees termination).
        input_values: dict[str, int] = {
            dep_key: self.resolve(dep_key, character) for dep_key in node.inputs
        }

        # Sum bonus pools.
        bonus_total = sum(
            self._pools[pk].total(character)
            for pk in node.pools
            if pk in self._pools
        )

        value = node.compute(input_values, bonus_total)

        node._cache = value
        node._dirty = False
        return value

    # ------------------------------------------------------------------
    # Invalidation
    # ------------------------------------------------------------------

    def invalidate(self, key: str) -> None:
        """
        Mark `key` as dirty and cascade to all transitive dependents.
        Uses iterative BFS to avoid recursion depth issues on large graphs.
        """
        if key not in self._nodes:
            return  # silently ignore unknown keys (pools may not have nodes)

        visited: set[str] = set()
        queue: list[str] = [key]

        while queue:
            current = queue.pop()
            if current in visited:
                continue
            visited.add(current)
            if current in self._nodes:
                self._nodes[current].invalidate()
            for dependent in self._dependents.get(current, set()):
                if dependent not in visited:
                    queue.append(dependent)

    def invalidate_all(self) -> None:
        """Mark every node dirty.  Used after bulk changes (e.g. level-up)."""
        for node in self._nodes.values():
            node.invalidate()

    def invalidate_pool(self, pool_key: str) -> None:
        """
        Invalidate all nodes that have `pool_key` in their pools,
        then cascade.  Called when a BonusPool's contents change.
        """
        for node in self._nodes.values():
            if pool_key in node.pools:
                self.invalidate(node.key)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def dependencies_of(self, key: str) -> list[str]:
        """Return the direct input keys of `key`."""
        return list(self.node(key).inputs)

    def dependents_of(self, key: str) -> list[str]:
        """Return keys of nodes that directly depend on `key`."""
        return sorted(self._dependents.get(key, set()))

    def all_keys(self) -> list[str]:
        """Return all registered node keys in registration order."""
        return list(self._nodes.keys())

    def dirty_keys(self) -> list[str]:
        """Return keys of all currently dirty nodes."""
        return [k for k, n in self._nodes.items() if n._dirty]

    # ------------------------------------------------------------------
    # Cycle detection
    # ------------------------------------------------------------------

    def _assert_no_cycle(self, start_key: str) -> None:
        """
        DFS from start_key through the dependency graph (following inputs).
        Raises StatError if a cycle is detected.
        Called after adding a new node.
        """
        visited: set[str] = set()
        rec_stack: set[str] = set()

        def dfs(key: str) -> None:
            visited.add(key)
            rec_stack.add(key)
            node = self._nodes.get(key)
            if node:
                for dep in node.inputs:
                    if dep not in visited:
                        dfs(dep)
                    elif dep in rec_stack:
                        raise StatError(
                            f"Dependency cycle detected involving {dep!r}."
                        )
            rec_stack.discard(key)

        dfs(start_key)


# ---------------------------------------------------------------------------
# Standard compute functions
# (used by the character bootstrap and rules YAML loader)
# ---------------------------------------------------------------------------


def compute_ability_modifier(inputs: dict[str, int], bonus_total: int) -> int:
    """
    Standard 3.5e ability modifier: floor((score - 10) / 2).
    The node's single input is the ability score.
    bonus_total is added after (e.g. for flat bonuses to the modifier itself,
    which are rare but exist).
    """
    score = next(iter(inputs.values()), 10)
    return math.floor((score - 10) / 2) + bonus_total


def compute_sum(inputs: dict[str, int], bonus_total: int) -> int:
    """Sum all inputs and the bonus total.  General-purpose accumulator."""
    return sum(inputs.values()) + bonus_total


def compute_max_zero(inputs: dict[str, int], bonus_total: int) -> int:
    """Like compute_sum but floors at 0.  E.g. DEX mod to AC when helpless."""
    return max(0, sum(inputs.values()) + bonus_total)


def compute_capped_dex(
    cap_key: str = "max_dex_bonus",
) -> Callable[[dict[str, int], int], int]:
    """
    Returns a compute function that applies the armour's max dex cap.
    cap_key is the input key holding the cap value (-1 = no cap).

    Usage:
        StatNode("ac_dex_contribution",
                 inputs=["dex_mod", "max_dex_bonus"],
                 compute=compute_capped_dex("max_dex_bonus"))
    """

    def _compute(inputs: dict[str, int], bonus_total: int) -> int:
        dex_mod = inputs.get("dex_mod", 0)
        cap = inputs.get(cap_key, -1)
        capped = dex_mod if cap < 0 else min(dex_mod, cap)
        return max(0, capped) + bonus_total

    return _compute


def compute_base_attack_bonus(inputs: dict[str, int], bonus_total: int) -> int:
    """
    BAB accumulator.  Inputs should be the individual class BAB contributions
    (computed by the class engine from level and progression type).
    """
    return sum(inputs.values()) + bonus_total


def compute_save(inputs: dict[str, int], bonus_total: int) -> int:
    """
    Standard save total = base_save + ability_mod + misc bonuses.
    Expects inputs: {"base_save": N, "<ability>_mod": M}
    """
    return sum(inputs.values()) + bonus_total


def compute_skill(inputs: dict[str, int], bonus_total: int) -> int:
    """
    Skill check total = ranks + ability_mod + misc bonuses.
    Untrained penalty and class-skill handling is in engine/skills.py.
    """
    return sum(inputs.values()) + bonus_total
