"""
engine/skills.py
----------------
Skill definitions, rank tracking, and total computation.

Skill total = ranks + ability_mod + misc_bonus_pool + synergy_bonuses
                  + conditional_bonuses (e.g. armor check penalty)

The skill system registers each skill as a StatNode in the character's
stat graph so that ability modifier changes cascade automatically.

Public API:
  SkillDefinition  — metadata for one skill
  SkillRegistry    — lookup by name or pool key
  SkillTotal       — result of computing a skill's total
  register_skills_on_character() — wire skills into a Character's stat graph
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from heroforge.engine.bonus import BonusEntry, BonusPool, BonusType
from heroforge.engine.stat import StatNode

if TYPE_CHECKING:
    from typing import Callable

    from heroforge.engine.character import Character


# ---------------------------------------------------------------------------
# SkillDefinition
# ---------------------------------------------------------------------------


@dataclass
class SkillDefinition:
    """Metadata describing one skill."""

    name: str
    key: str  # pool key e.g. "skill_hide"
    ability: str  # "str", "dex", etc.
    trained_only: bool = False
    armor_check: bool = False
    synergies: list[dict] = field(default_factory=list)
    # synergies: [{skill: "Bluff", bonus: 2}, ...]  (if 5+ ranks in this skill)
    description: str = ""


# ---------------------------------------------------------------------------
# SkillRegistry
# ---------------------------------------------------------------------------


class SkillRegistry:
    """Central lookup for SkillDefinitions."""

    def __init__(self) -> None:
        self._by_name: dict[str, SkillDefinition] = {}
        self._by_key: dict[str, SkillDefinition] = {}

    def register(self, defn: SkillDefinition, overwrite: bool = False) -> None:
        if defn.name in self._by_name and not overwrite:
            raise ValueError(
                f"SkillDefinition {defn.name!r} already registered."
            )
        self._by_name[defn.name] = defn
        self._by_key[defn.key] = defn

    def get(self, name: str) -> SkillDefinition | None:
        return self._by_name.get(name)

    def get_by_key(self, key: str) -> SkillDefinition | None:
        return self._by_key.get(key)

    def require(self, name: str) -> SkillDefinition:
        defn = self._by_name.get(name)
        if defn is None:
            raise KeyError(f"No SkillDefinition for {name!r}.")
        return defn

    def all_skills(self) -> list[SkillDefinition]:
        return sorted(self._by_name.values(), key=lambda d: d.name)

    def __len__(self) -> int:
        return len(self._by_name)

    def __contains__(self, name: str) -> bool:
        return name in self._by_name


# ---------------------------------------------------------------------------
# SkillTotal
# ---------------------------------------------------------------------------


@dataclass
class SkillTotal:
    """Breakdown of one skill's computed total."""

    skill_name: str
    ranks: int
    ability_mod: int
    misc_bonus: int  # from BonusPool (feats, magic items, etc.)
    synergy_bonus: int  # from synergies
    armor_penalty: int  # negative or 0
    total: int

    @property
    def usable(self) -> bool:
        """False if the skill is trained_only and ranks == 0."""
        return True  # caller checks trained_only against ranks if needed


# ---------------------------------------------------------------------------
# Skill compute function factory
# ---------------------------------------------------------------------------


def _make_skill_compute(
    ability: str,
    skill_key: str,
) -> Callable[[dict[str, int], int], int]:
    """
    Returns a compute function for a skill StatNode.

    inputs dict will have the ability modifier keyed by f"{ability}_mod".
    bonus_total is the sum of the skill's BonusPool.

    Ranks are stored in character.skills[skill_name] and injected into the
    pool under source key "ranks" so they participate in the total naturally.
    The BonusPool total includes ranks + misc bonuses — the compute function
    just adds the ability modifier.
    """
    mod_key = f"{ability}_mod"

    def compute(inputs: dict[str, int], bonus_total: int) -> int:
        return inputs.get(mod_key, 0) + bonus_total

    return compute


# ---------------------------------------------------------------------------
# register_skills_on_character
# ---------------------------------------------------------------------------


def register_skills_on_character(
    skill_registry: SkillRegistry,
    character: "Character",
) -> None:
    """
    Register all skills as StatNodes on the character's stat graph.

    For each skill:
      1. Create a BonusPool keyed by the skill's pool key.
      2. Create a StatNode that computes: ability_mod + pool_total.
         Ranks are contributed to the pool as an UNTYPED entry under
         source key "ranks" — updated when set_skill_ranks() is called.
      3. Register both with the stat graph.

    This is idempotent: if the node is already registered it is skipped.
    """
    for skill_def in skill_registry.all_skills():
        key = skill_def.key

        # Skip already-registered skills
        if character._graph.has_node(key):
            continue

        # Register pool if not present — use add_pool so it goes into
        # both character._pools (for get_pool()) and the graph
        if not character._graph.has_pool(key):
            pool = BonusPool(key)
            character.add_pool(pool)  # registers in both _pools and _graph

        compute_fn = _make_skill_compute(skill_def.ability, key)

        node = StatNode(
            key=key,
            base=None,
            inputs=[f"{skill_def.ability}_mod"],
            pool_keys=[key],
            compute=compute_fn,
            description=skill_def.name,
        )
        character._graph.register_node(node)

    # Store skill registry on character for rank management
    character._skill_registry = skill_registry


# ---------------------------------------------------------------------------
# Rank management helpers
# ---------------------------------------------------------------------------


def set_skill_ranks(
    character: "Character",
    skill_name: str,
    ranks: int,
) -> None:
    """
    Set the rank count for a skill on a character.

    Updates both character.skills[skill_name] and the corresponding
    BonusPool entry so the stat graph reflects the change.
    """
    skill_reg: SkillRegistry = getattr(character, "_skill_registry", None)
    if skill_reg is None:
        character.skills[skill_name] = ranks
        return

    defn = skill_reg.get(skill_name)
    if defn is None:
        character.skills[skill_name] = ranks
        return

    character.skills[skill_name] = ranks

    pool = character.get_pool(defn.key)
    if pool is None:
        return

    if ranks > 0:
        entry = BonusEntry(
            value=ranks,
            bonus_type=BonusType.UNTYPED,
            source=f"{skill_name} (ranks)",
        )
        pool.set_source("ranks", [entry])
    else:
        pool.clear_source("ranks")

    character._graph.invalidate_pool(defn.key)
    character._notify({defn.key})


def compute_skill_total(
    character: "Character",
    skill_def: SkillDefinition,
    armor_check_penalty: int = 0,
) -> SkillTotal:
    """
    Compute the full breakdown for a skill total.

    armor_check_penalty: negative integer applied if skill.armor_check is True
                         and character is wearing armor.
    """
    ranks = character.skills.get(skill_def.name, 0)
    ability_mod = character.get_ability_modifier(skill_def.ability)

    # Pool total includes ranks + feat bonuses + item bonuses
    pool = character.get_pool(skill_def.key)
    pool_total = pool.total(character) if pool else 0
    # misc = pool total minus ranks (ranks counted separately in breakdown)
    misc_bonus = pool_total - ranks

    # Synergy bonuses: scan all skills for any that grant a synergy bonus
    # TO this skill when the character has 5+ ranks in the SOURCE skill.
    # e.g. Tumble.synergies = [{skill: Balance, bonus: 2}]
    # means: 5 ranks in Tumble → +2 to Balance.
    synergy_bonus = 0
    skill_reg: SkillRegistry | None = getattr(
        character, "_skill_registry", None
    )
    if skill_reg is not None:
        for source_defn in skill_reg.all_skills():
            if character.skills.get(source_defn.name, 0) < 5:
                continue
            for syn in source_defn.synergies:
                if syn.get("skill", "") == skill_def.name:
                    synergy_bonus += syn.get("bonus", 2)

    # Armor check penalty (only if skill has armor_check=True)
    acp = armor_check_penalty if skill_def.armor_check else 0

    total = ranks + ability_mod + misc_bonus + synergy_bonus + acp

    return SkillTotal(
        skill_name=skill_def.name,
        ranks=ranks,
        ability_mod=ability_mod,
        misc_bonus=misc_bonus,
        synergy_bonus=synergy_bonus,
        armor_penalty=acp,
        total=total,
    )


# ---------------------------------------------------------------------------
# YAML builder
# ---------------------------------------------------------------------------


def build_skill_from_yaml(decl: dict) -> SkillDefinition:
    return SkillDefinition(
        name=decl["name"],
        key=decl["key"],
        ability=decl["ability"],
        trained_only=bool(decl.get("trained_only", False)),
        armor_check=bool(decl.get("armor_check", False)),
        synergies=decl.get("synergies", []),
        description=decl.get("description", ""),
    )
