"""
rules/rules.py
--------------
Single container for every rule-definition artifact loaded from
YAML at startup, plus a module-level accessor so engine code can
reach rules without wiring through Character or AppState.

Usage:
    from heroforge.rules.rules import get_rules
    rules = get_rules()            # lazy-loads on first call
    feat = rules.feats.get("Power Attack")

Tests override via ``set_rules(r)`` and reset with
``reset_rules()``.

Per-book layout
---------------
Each top-level subdirectory of ``rules/`` is a "book": ``core/``
(SRD), ``custom/`` (homebrew), and one folder per published
splatbook. ``Rules.load()`` discovers books by globbing
``rules/`` — adding a splatbook means dropping in a new folder
that follows the per-book file convention; no changes here.

Per-book file convention:
    <book>/feats.yaml          (optional)
    <book>/classes/*.yaml      (optional)
    <book>/magic_items.yaml    (optional; core uses per-slot files)
    <book>/materials.yaml      (optional)

Core-only categories (stats, skills, templates, races, domains,
armor, weapons, spells, conditions, derived pools) live solely
under ``core/`` and load directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from heroforge.engine.classes import ClassRegistry
from heroforge.engine.conditions import ConditionRegistry
from heroforge.engine.domains import DomainRegistry
from heroforge.engine.effects import BuffRegistry
from heroforge.engine.equipment import (
    ArmorRegistry,
    MaterialRegistry,
    WeaponRegistry,
)
from heroforge.engine.feats import FeatRegistry
from heroforge.engine.magic_items import MagicItemRegistry
from heroforge.engine.prerequisites import PrerequisiteChecker
from heroforge.engine.races import RaceRegistry
from heroforge.engine.skills import SkillRegistry
from heroforge.engine.spells import SpellCompendium
from heroforge.engine.templates import TemplateRegistry
from heroforge.rules.loader import (
    ClassesLoader,
    ConditionLoader,
    DerivedPoolsLoader,
    DomainsLoader,
    EquipmentLoader,
    FeatsLoader,
    MagicItemLoader,
    RacesLoader,
    SkillsLoader,
    SpellCompendiumLoader,
    TemplatesLoader,
)

RULES_DIR = Path(__file__).parent

CORE = "core"
CUSTOM = "custom"

# Subdirectory names under rules/ that are not books.
_NON_BOOK_DIRS = frozenset({"test", "__pycache__"})

# Magic-item slot files under rules/core/magic_items/. Non-core
# books use a single flat magic_items.yaml instead.
MAGIC_ITEM_SLOTS: tuple[str, ...] = (
    "head",
    "face",
    "throat",
    "shoulders",
    "body",
    "torso",
    "arms",
    "hands",
    "ring",
    "waist",
    "feet",
    "slotless",
    "tool",
    "consumable",
)


def book_dirs(rules_dir: Path | None = None) -> list[str]:
    """
    Names of book subdirectories under ``rules_dir``.

    Order: ``core`` first, ``custom`` last, all other books
    alphabetical between. Custom is loaded last so its entries
    can override published-book entries on name collision.

    Hidden directories, dunder dirs, and ``test`` are skipped.
    """
    rd = rules_dir or RULES_DIR
    names = [
        p.name
        for p in rd.iterdir()
        if p.is_dir()
        and not p.name.startswith((".", "_"))
        and p.name not in _NON_BOOK_DIRS
    ]
    middle = sorted(n for n in names if n not in (CORE, CUSTOM))
    head = [CORE] if CORE in names else []
    tail = [CUSTOM] if CUSTOM in names else []
    return head + middle + tail


@dataclass
class Rules:
    """
    All rule-definition registries + derived pools + prereq
    checker. Treat as read-only after load()."""

    buffs: BuffRegistry = field(default_factory=BuffRegistry)
    conditions: ConditionRegistry = field(default_factory=ConditionRegistry)
    magic_items: MagicItemRegistry = field(default_factory=MagicItemRegistry)
    spells: SpellCompendium = field(default_factory=SpellCompendium)
    feats: FeatRegistry = field(default_factory=FeatRegistry)
    armor: ArmorRegistry = field(default_factory=ArmorRegistry)
    weapons: WeaponRegistry = field(default_factory=WeaponRegistry)
    materials: MaterialRegistry = field(default_factory=MaterialRegistry)
    domains: DomainRegistry = field(default_factory=DomainRegistry)
    skills: SkillRegistry = field(default_factory=SkillRegistry)
    templates: TemplateRegistry = field(default_factory=TemplateRegistry)
    classes: ClassRegistry = field(default_factory=ClassRegistry)
    races: RaceRegistry = field(default_factory=RaceRegistry)
    derived_pools: dict = field(default_factory=dict)
    prereq_checker: PrerequisiteChecker | None = None

    def load(self, rules_dir: Path | None = None) -> None:
        """
        Populate from YAML. Instantiates PrerequisiteChecker
        locally, passes it to loaders that register into it,
        then assigns the populated checker to self."""
        rd = rules_dir or RULES_DIR

        prereq_checker = PrerequisiteChecker()

        # --- Core-only categories -----------------------------
        ConditionLoader(rd).load(
            self.conditions,
            self.buffs,
            f"{CORE}/conditions_srd.yaml",
        )
        SkillsLoader(rd).load(self.skills, f"{CORE}/skills.yaml")
        TemplatesLoader(rd).load(self.templates, f"{CORE}/templates.yaml")
        RacesLoader(rd).load(self.races, f"{CORE}/races.yaml")
        DomainsLoader(rd).load(self.domains, f"{CORE}/domains.yaml")

        eq_loader = EquipmentLoader(rd)
        eq_loader.load_armor(self.armor, f"{CORE}/armor.yaml")
        eq_loader.load_weapons(self.weapons, f"{CORE}/weapons.yaml")

        scl = SpellCompendiumLoader(rd)
        for lvl in range(10):
            scl.load(
                self.spells,
                f"{CORE}/spells_level_{lvl}.yaml",
                buff_registry=self.buffs,
            )

        # --- Per-book categories ------------------------------
        # Iterate each category once across all books so that
        # later-loading books (e.g. ``custom``) override earlier
        # ones, and within a book all feats load before any
        # class definitions reference them.
        books = book_dirs(rd)
        mi_loader = MagicItemLoader(rd)

        for book in books:
            self._load_book_magic_items(rd, mi_loader, book)

        for book in books:
            self._load_book_feats(rd, book, prereq_checker)

        for book in books:
            self._load_book_classes(rd, book, prereq_checker)

        for book in books:
            self._load_book_materials(rd, eq_loader, book)

        # --- Final wiring -------------------------------------
        self.prereq_checker = prereq_checker
        self.derived_pools = DerivedPoolsLoader(rd).load(
            f"{CORE}/derived_pools.yaml"
        )

    def _load_book_magic_items(
        self,
        rd: Path,
        mi_loader: MagicItemLoader,
        book: str,
    ) -> None:
        if book == CORE:
            for slot in MAGIC_ITEM_SLOTS:
                mi_loader.load(
                    self.magic_items,
                    f"{book}/magic_items/{slot}.yaml",
                )
            return
        mi_yaml = rd / book / "magic_items.yaml"
        if mi_yaml.exists():
            mi_loader.load(self.magic_items, f"{book}/magic_items.yaml")

    def _load_book_feats(
        self,
        rd: Path,
        book: str,
        prereq_checker: PrerequisiteChecker,
    ) -> None:
        f_yaml = rd / book / "feats.yaml"
        if not f_yaml.exists():
            return
        FeatsLoader(rd).load(
            self.feats,
            f"{book}/feats.yaml",
            prereq_checker,
            self.buffs,
        )

    def _load_book_classes(
        self,
        rd: Path,
        book: str,
        prereq_checker: PrerequisiteChecker,
    ) -> None:
        c_dir = rd / book / "classes"
        if not c_dir.is_dir():
            return
        ClassesLoader(rd).load(
            self.classes,
            f"{book}/classes",
            prereq_checker=prereq_checker,
            buff_registry=self.buffs,
        )

    def _load_book_materials(
        self,
        rd: Path,
        eq_loader: EquipmentLoader,
        book: str,
    ) -> None:
        m_yaml = rd / book / "materials.yaml"
        if not m_yaml.exists():
            return
        eq_loader.load_materials(self.materials, f"{book}/materials.yaml")


_rules: Rules | None = None


def get_rules() -> Rules:
    """Return the process-wide Rules, lazy-loading on first call."""
    global _rules  # noqa: PLW0603
    if _rules is None:
        r = Rules()
        r.load()
        _rules = r
    return _rules


def set_rules(rules: Rules) -> None:
    """Override the singleton. For tests and alternate rulesets."""
    global _rules  # noqa: PLW0603
    _rules = rules


def reset_rules() -> None:
    """Forget the current singleton. Next get_rules() rebuilds."""
    global _rules  # noqa: PLW0603
    _rules = None
