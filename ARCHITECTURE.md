# HeroForge Anew — Architecture

A PyQt6 desktop application for D&D 3.5e character management.
Clean separation between the **rules engine** (pure Python, no
GUI), the **data layer** (YAML rulebook definitions), the
**export layer** (PDF via ReportLab), and the **presentation
layer** (PyQt6 widgets).

---

## Directory layout

```
src/heroforge/
├── engine/                 # Pure Python, zero GUI deps
│   ├── bonus.py            # BonusType, BonusEntry, BonusPool
│   ├── stat.py             # StatNode, StatGraph: lazy DAG
│   ├── character.py        # Character, ChangeNotifier,
│   │                       #   CharacterLevel, ClassLevel,
│   │                       #   BuffState, DmOverride,
│   │                       #   grapple, carrying capacity
│   ├── effects.py          # BuffDefinition, BuffCategory,
│   │                       #   formula evaluation
│   ├── classes_races.py    # ClassDefinition, RaceDefinition,
│   │                       #   SpellcastingInfo, apply_race(),
│   │                       #   DomainDefinition, DomainRegistry
│   ├── skills.py           # SkillDefinition,
│   │                       #   register_skills_on_character()
│   ├── feats.py            # FeatDefinition, FeatKind,
│   │                       #   FeatRegistry
│   ├── prerequisites.py    # PrerequisiteChecker,
│   │                       #   FeatAvailability, PrC infra
│   ├── templates.py        # TemplateDefinition,
│   │                       #   apply_template()
│   ├── persistence.py      # save/load character YAML
│   ├── sheet.py            # extract_sheet(),
│   │                       #   gather_sheet(), charsheet
│   │                       #   CLI entry point
│   ├── equipment.py        # ArmorDefinition,
│   │                       #   WeaponDefinition,
│   │                       #   equip/unequip helpers
│   ├── spellcasting.py     # Spell slot tables, bonus
│   │                       #   spells, DCs, spells known
│   ├── spells.py           # SpellEntry, SpellCompendium
│   │                       #   (metadata for all spells)
│   ├── conditions.py       # ConditionDefinition,
│   │                       #   ConditionRegistry
│   ├── magic_items.py      # MagicItemDefinition,
│   │                       #   MagicItemRegistry
│   └── resources.py        # ResourceTracker (uses/day)
│
├── rules/
│   ├── schema.py           # cattrs Converter + hooks
│   ├── loader.py           # StatsLoader,
│   │                       #   ConditionLoader,
│   │                       #   MagicItemLoader,
│   │                       #   FeatsLoader, ClassesLoader,
│   │                       #   RacesLoader, SkillsLoader,
│   │                       #   TemplatesLoader,
│   │                       #   EquipmentLoader,
│   │                       #   DomainsLoader,
│   │                       #   SpellCompendiumLoader
│   └── core/               # YAML data files
│       ├── stats.yaml
│       ├── skills.yaml
│       ├── classes/           # 1 YAML per class
│       │                     #   (16 base + 15 prestige)
│       ├── races.yaml        # 7 core races
│       ├── feats.yaml        # 110 feats (alphabetical)
│       ├── spells_level_0..9.yaml  # Spell compendium
│       │                           #   (601 spells, 1
│       │                           #   file per level)
│       ├── conditions_srd.yaml  # 20 conditions
│       ├── templates.yaml    # 12 creature templates
│       ├── domains.yaml      # 22 cleric domains
│       ├── armor.yaml        # 18 armor/shields
│       ├── weapons.yaml      # 63 weapons
│       └── magic_items.yaml  # ~70 magic items
│
├── export/
│   ├── sheet_data.py       # gather(): Character → SheetData
│   └── renderer.py         # render_pdf(): SheetData → PDF
│
└── ui/                     # PyQt6 — never imported by
    │                       #   engine/ or export/
    ├── app.py              # QApplication entry point,
    │                       #   Ctrl+C handling
    ├── app_state.py        # AppState: registries + Character
    ├── main_window.py      # MainWindow: tabs, menus, I/O
    ├── sheets/
    │   ├── sheet1_summary.py   # Identity, abilities, combat
    │   ├── sheet_race.py       # Race selection tab
    │   ├── sheet_class.py      # Per-level class tab
    │   ├── sheet2_skills.py    # Full skill table
    │   ├── sheet3_feats.py     # Taken feats + feat picker
    │   ├── sheet_spells.py     # Spell buff toggles
    │   ├── sheet_equipment.py  # Equipment slots table
    │   └── sheet_notes.py      # Free-form notes
    ├── dialogs/
    │   ├── class_dialog.py     # Legacy class dialog
    │   └── race_dialog.py      # Legacy race dialog
    └── widgets/
        ├── common.py           # LabeledField, StatDisplay,
        │                       #   SectionHeader, etc.
        ├── ability_block.py    # Six ability score rows
        ├── combat_stats.py     # AC, saves, BAB, HP, init
        └── buff_panel.py       # Scrollable buff toggle list

tests/
├── conftest.py             # QT_QPA_PLATFORM=offscreen, qapp
├── integration/            # golden-file char sheets
│   ├── conftest.py         #   app_state fixture
│   ├── test_golden.py      #   parametrized golden tests
│   └── characters/         #   29 .char.yaml + .expected.yaml
│                           #   (11 base + 3 archetype + 15 PrC)
├── test_bonus.py
├── test_stat.py
├── test_character.py
├── test_effects.py
├── test_classes_races.py
├── test_skills.py
├── test_skill_allocation.py # Per-level skill budget/ranks
├── test_feats.py
├── test_prerequisites.py
├── test_templates.py
├── test_persistence.py
├── test_stats_yaml.py
├── test_spells_yaml.py
├── test_export.py
├── test_ui_smoke.py
├── test_combat.py          # Grapple, carrying capacity
├── test_equipment.py       # Armor, shields, weapons
├── test_spellcasting.py    # Spell slots, DCs
├── test_domains.py         # Cleric domains
├── test_class_features.py  # Rage, inspire courage, etc.
├── test_magic_items.py     # Magic item buffs
├── test_conditions_srd_yaml.py
├── test_feats_srd_yaml.py
└── test_spells_srd_yaml.py
```

---

## Layer 1: Bonus system (`engine/bonus.py`)

`BonusType` enum covers all 3.5e bonus types. `BonusEntry` is
a frozen value object (value, type, source, optional condition
lambda). `BonusPool` collects entries keyed by source name —
`set_source` / `clear_source` are idempotent.

`aggregate()` implements the core stacking rules: dodge,
racial, and untyped always stack; all other types take highest
only; penalties always stack.

## Layer 2: Stat graph (`engine/stat.py`)

`StatNode` is a single computable stat (key, base value, input
dependencies, pool keys, compute function). `StatGraph` is the
DAG registry with lazy evaluation and dirty-cascade
invalidation. Nodes are computed on first access after
invalidation.

Helper compute functions: `compute_ability_modifier`,
`compute_sum`, `compute_capped_dex`, `compute_save`.

## Layer 3: Character (`engine/character.py`)

The central mutable object. Holds identity fields, raw ability
scores, class levels, race, feats, skills, buff states, and
DM overrides. Owns a `StatGraph` and a dict of `BonusPool`s.

Supporting dataclasses:

- `CharacterLevel` — one per-character-level entry
  (e.g. level 3 = Rogue). Stores class name, HP roll,
  per-level skill point allocation, and feats acquired
  at that level (with source tag).
- `ClassLevel` — legacy cumulative model, now a computed
  property that aggregates `CharacterLevel` entries.
- `BuffState` — per-buff persistent state: active flag,
  optional caster level, optional parameter value.
- `DmOverride` — a DM-granted override: target name + note.

Per-level methods: `add_level()`, `remove_last_level()`,
`set_level_class()`, `set_level_hp()`,
`set_level_skill_ranks()`, `skill_points_for_level()`.

Computed properties: `class_level_map` (cumulative levels
per class), `total_level`, `attack_iteratives()`,
`multiclass_xp_penalty()`, `validate()`.

Combat helpers: `_compute_size_mod_grapple()`,
`_compute_size_mod_hide()`, `carrying_capacity()`.

Grapple stat node: BAB + STR mod + size grapple modifier.

Placeholder fields (defined but not yet wired to logic):
`hp_current`, `familiar`, `animal_companion`.

`_bootstrap_stat_graph()` wires up all standard 3.5e stat
nodes (ability scores → modifiers → saves/attacks/AC/HP/
grapple/etc.).

All mutations go through public methods (`set_ability_score`,
`toggle_buff`, `set_class_levels`, `add_feat`, etc.) which
handle pool updates, stat invalidation, and change
notification via `ChangeNotifier`.

`ChangeNotifier` is a simple observer list — the UI subscribes
callbacks; the Character calls `notify(changed_keys)` on
mutation. Keeps the engine decoupled from Qt signals.

## Layer 4: Effects (`engine/effects.py`)

`BuffDefinition` models any source of stat bonuses: spells,
feats, conditions, items, class features. Each has a list of
`BonusEffect` (target pool, bonus type, value or CL-scaling
formula string, optional condition). `BuffCategory` enum tags
the source kind (SPELL, CLASS, FEAT, ITEM, CONDITION, RACIAL,
TEMPLATE).

`evaluate_formula()` safely evaluates CL-scaling expressions
like `"2 + caster_level // 6"` in a restricted namespace.

`BuffRegistry` provides name-based lookup.

## Layer 5: Classes and races (`engine/classes_races.py`)

`ClassDefinition` holds BAB/save progressions, hit die,
class skills, `skills_per_level`, optional spellcasting
info, and prestige class fields (`max_level`,
`is_prestige`, `entry_prerequisites`,
`ongoing_prerequisites`). `SpellcastingInfo` records cast
type (arcane/divine), key ability, preparation mode, max
spell level, and starting level. `ClassFeature` records a
feature gained at a specific class level.

`RaceDefinition` holds ability modifiers, size, speed,
subtypes, and racial features.

`DomainDefinition` holds name, granted power text, and
domain spells (levels 1-9). `DomainRegistry` provides
name-based lookup for all 22 SRD cleric domains.

`apply_race()` wires racial ability bonuses into the
Character's pools. `bab_at_level()` and `save_at_level()`
compute progression values.

`ClassRegistry` and `RaceRegistry` provide name-based
lookup. Both base and prestige classes live in the same
`ClassRegistry`.

## Layer 6: Skills (`engine/skills.py`)

`SkillDefinition` holds ability key, trained-only flag,
armor check penalty flag, and synergy declarations.
`register_skills_on_character()` creates a pool and stat
node per skill. `set_skill_ranks()` updates ranks.
`compute_skill_total()` returns a full breakdown.

Per-level helpers: `compute_skill_budget()` computes
points per level (skills_per_level + INT mod, x4 at
level 1, +1 for humans, min 1). `max_skill_ranks()`
returns the cap (class skill: N+3, cross-class:
(N+3)/2). `validate_skill_allocation()` checks budget
and rank caps. `recompute_skills_from_levels()`
rebuilds total ranks from all `CharacterLevel` entries.

## Layer 7: Feats (`engine/feats.py`)

`FeatDefinition` has a `FeatKind` (ALWAYS_ON, CONDITIONAL,
PASSIVE), optional prerequisites, optional `BuffDefinition`
for stat effects, and optional `FeatParameterSpec` for
parameterized feats (e.g. Power Attack amount).

Always-on feats apply bonuses directly to the relevant
pools via `_apply_feat_pool_bonuses()` using source key
`"feat:<name>"` — they never appear in the buff panel.
Conditional feats register their buff for user toggling
via the buffs panel. Dodge is conditional (per 3.5e rules
the player designates one opponent per action).

## Layer 8: Prerequisites (`engine/prerequisites.py`)

Prerequisite types: `StatPrereq`, `AbilityPrereq`,
`FeatPrereq`, `SkillPrereq`, `ClassLevelPrereq`,
`SpellcastingPrereq`, `ClassFeaturePrereq`,
`CreatureTypePrereq`, plus compound `all_of` / `any_of` /
`none_of`.

`PrerequisiteChecker` evaluates prereqs against a Character
and classifies each feat as one of `FeatAvailability`:
AVAILABLE, TAKEN, OVERRIDE, UNAVAILABLE, or CHAIN_PARTIAL.
DM overrides short-circuit to OVERRIDE.

Prestige class support: `register_prc()` registers a
prestige class with entry and ongoing prerequisites;
`prc_availability()` checks whether a character qualifies
to enter; `ongoing_violations()` checks whether a
character in a PrC still meets ongoing requirements.
PrCs are loaded from `classes.yaml` by `ClassesLoader`
and registered with the checker automatically.

## Layer 9: Templates (`engine/templates.py`)

`TemplateDefinition` models creature templates (Half-Celestial,
etc.) with ability modifiers (bonus_type: racial, so they
stack with racial ability mods), type/subtype changes,
natural armor, granted feats, partial-application support,
and an optional `ongoing_prereq`.

`apply_template()` / `remove_template()` wire effects into the
Character. `effective_type()` and `effective_subtypes()` resolve
the final creature type after all template layers.

## Layer 10: Persistence (`engine/persistence.py`)

`save_character()` serializes to `.char.yaml` (version 2).
The `levels:` key stores per-character-level entries with
class name, HP roll, skill point allocation, and feats
acquired at that level (each with name, source, optional
parameter). Feats, skills, and class_levels are all
derived from `levels:` — no redundant top-level keys.
`load_character()` deserializes and re-applies race,
template, and feat effects through the normal engine
methods so all derived stats recompute correctly.

## Layer 10b: Sheet extraction (`engine/sheet.py`) — TODO

`extract_sheet(path, app_state)` loads a `.char.yaml` and
returns a complete dict of all numerical values with full
bonus-type breakdowns. `gather_sheet(character, app_state)`
does the extraction from an already-loaded Character.

CLI entry point: `uv run charsheet input.char.yaml`
prints YAML to stdout; `-o file.yaml` writes to file.

The output dict includes: identity, abilities (base +
typed bonuses + score + mod), combat stats (base + typed
bonuses + total for AC, saves, attacks, grapple, HP,
initiative, speed, SR), per-weapon attacks with
weapon-specific bonuses, skills (ranks + ability_mod +
typed bonuses), carrying capacity, feats, class features,
spellcasting (slots, DCs, spells known), and resources.

Zero-value bonuses are omitted from the output.

## Layer 11: Equipment (`engine/equipment.py`)

`ArmorDefinition` and `WeaponDefinition` are frozen
dataclasses with all SRD stats. `ArmorRegistry` and
`WeaponRegistry` provide name-based lookup.

`equip_armor()` / `equip_shield()` push armor/shield
bonuses into AC pool and armor check penalties into
skill pools. `unequip_armor()` / `unequip_shield()`
reverse these. Source keys (`"equip:armor"`,
`"equip:shield"`) keep equipment bonuses separate from
buff bonuses.

## Layer 12: Spellcasting (`engine/spellcasting.py`)

Complete spell slot tables for all 7 casting classes
(Wizard, Sorcerer, Cleric, Druid, Bard, Paladin,
Ranger). `base_slots_per_day()`, `bonus_spells()`,
`slots_per_day()`, `spells_known()`, `spell_save_dc()`.

## Layer 13: Spell compendium (`engine/spells.py`)

`SpellEntry` holds metadata for any SRD spell (name,
school, level dict, duration, etc.). `SpellCompendium`
is a registry of all 601 non-epic SRD spells, loaded
from three YAML files. Provides `by_class()`,
`by_class_and_level()` queries.

## Layer 14: Resources (`engine/resources.py`)

`ResourceTracker` for uses-per-day class abilities
(Rage, Turn Undead, Bardic Music, Wild Shape). Tracks
max uses (formula), current uses, use/reset/exhaust.

---

## Rules layer (`rules/`)

`rules/schema.py` defines a pre-configured `cattrs.Converter`
with `forbid_extra_keys=True` and custom structure hooks for
all enums plus frozen dataclasses that need type coercion
(ClassDefinition, DomainDefinition, ArmorDefinition,
WeaponDefinition, SkillDefinition, SpellEntry). Also exports
`_forbid_extra()` for manual key validation in complex
builder functions.

`rules/loader.py` contains one Loader class per data domain
(StatsLoader, ConditionLoader, FeatsLoader,
SkillsLoader, TemplatesLoader, ClassesLoader, RacesLoader,
EquipmentLoader, DomainsLoader, SpellCompendiumLoader).
Each reads its YAML file and populates the corresponding
registry. Simple loaders (Classes, Skills, Domains,
Equipment, SpellCompendium, Conditions) use
`converter.structure(decl, DataClass)` for declarative
YAML-to-dataclass mapping. Complex loaders (Feats,
Templates) still use `build_*_from_yaml()` builders but
delegate key validation to `_forbid_extra()`.

Conditions have their own domain: `ConditionDefinition`
and `ConditionRegistry` live in `engine/conditions.py`.
The `ConditionLoader` reads `conditions_srd.yaml` (which
uses a `conditions:` top-level key, not `spells:`),
structures each entry as a `ConditionDefinition`, and
also registers a `BuffDefinition` in the `BuffRegistry`
via `build_buff_from_effects()` so the buff-toggle UI
keeps working.

Magic items have their own domain:
`MagicItemDefinition` and `MagicItemRegistry` live in
`engine/magic_items.py`. The `MagicItemLoader` reads
`magic_items.yaml` (which uses a `magic_items:`
top-level key), structures each entry as a
`MagicItemDefinition`, and also registers a
`BuffDefinition` in the `BuffRegistry` via
`build_buff_from_effects()` so the buff-toggle UI
keeps working.

YAML files under `rules/core/` contain full SRD data:
- 16 base classes (11 PHB + 5 NPC) + 15 prestige classes
- 7 races, 36 skills
- 110 feats (alphabetically sorted in feats.yaml)
- 601 spell compendium entries (with inline buff effects)
- 22 cleric domains
- 18 armor/shields, 63 weapons
- ~70 magic items
- 12 creature templates
- ~15 class feature buffs (rage, inspire courage, etc.)

`classes/` directory has one YAML per class. Base/NPC
classes use a `classes:` key; prestige classes use
`prestige_classes:`. The design supports additional
sourcebook directories with override semantics.

---

## Export layer (`export/`)

`sheet_data.py` defines `SheetData` and component dataclasses
(`IdentityData`, `AbilityData`, `CombatData`, `SkillRow`,
`FeatRow`, `BuffRow`). `gather()` extracts a complete
display-ready snapshot from a Character.

`renderer.py` takes a `SheetData` and writes a PDF via
ReportLab.

---

## UI layer (`ui/`)

### AppState (`app_state.py`)

Single object holding all registries and the active
`Character`. Created by `MainWindow`. Methods: `load_rules()`,
`new_character()`, `set_character()`, `skill_total()`.

Registries:
`buff_registry` (BuffRegistry),
`condition_registry` (ConditionRegistry),
`magic_item_registry` (MagicItemRegistry),
`spell_compendium` (SpellCompendium),
`feat_registry` (FeatRegistry),
`armor_registry` (ArmorRegistry),
`weapon_registry` (WeaponRegistry),
`domain_registry` (DomainRegistry),
`skill_registry` (SkillRegistry),
`template_registry` (TemplateRegistry),
`class_registry` (ClassRegistry),
`race_registry` (RaceRegistry).

### MainWindow (`main_window.py`)

Top-level `QMainWindow` with a tab widget. Owns the
`AppState`. Subscribes to `character.on_change` and routes
notifications to the active sheet tab.

Tabs: Summary, Race, Class, Skills, Feats, Spells,
Equipment, Notes.

File menu: New, Open, Save, Save As, Export PDF.

`closeEvent` prompts to save if modified.

### Sheets

Each sheet takes an `AppState` reference. A `_building` flag
suppresses signal feedback during construction.

- **Sheet1Summary** — three-column layout: identity
  fields, ability block + combat stats + validation
  warnings, buff panel. Shows iterative attack bonuses.
- **SheetRace** — race selection tab: filterable list
  (left) + detail panel (right). Immediate apply.
- **SheetClass** — per-level class tab: level
  progression table, add/remove level buttons, class
  combo (base + prestige with availability), HP roll
  spinbox, per-level skill allocation panel.
- **Sheet2Skills** — table widget with columns for
  class-skill marker, name, ability, ranks, misc, total.
- **Sheet3Feats** — splitter with taken-feats list
  (left) and filterable available-feats picker (right)
  with color-coded availability.
- **SheetSpells** — spell buff toggles with CL spinbox.
- **SheetEquipment** — table of equipment slots with
  editable Item Name and Notes columns.
- **SheetNotes** — free-form text editor bound to
  `character.notes`.

### Dialogs (legacy, unused)

- **ClassDialog** — set class levels via combo + spinbox.
- **RaceDialog** — pick a race from a filterable list.

### Widgets

Reusable components in `widgets/`: `LabeledField`,
`StatDisplay`, `CompactSpinBox`, `ModifierLabel`,
`SectionHeader`, `HRule`, `AbilityBlock`, `CombatStats`,
`BuffPanel`.

---

## Key design constraints

- `engine/` has **zero imports from `ui/`**. The engine is
  testable headlessly.
- `export/` has **zero imports from `ui/`**. PDF output
  matches UI display because both use the same Character data.
- YAML data files contain **no Python code**. Formulas are
  strings evaluated in a sandboxed context.
- Adding a new sourcebook = adding YAML files. No Python
  changes unless the book introduces a genuinely new kind of
  mechanic.

---

## Not yet implemented

- Remove `_forbid_extra` from schema.py — it's a
  private function used only by feats.py, templates.py,
  and loader.py (stats). cattrs `forbid_extra_keys=True`
  handles this for structured types; remaining callers
  should migrate to cattrs or move the function to where
  it's used.
- Per-weapon attack breakdowns in sheet extraction
- Resources (uses/day) in sheet extraction
  (ResourceTracker not yet wired to Character)
- Companion/familiar sub-objects (placeholder fields
  exist on Character but no logic)
- Armor/shield/weapon proficiency checks (nonproficiency
  attack penalties not applied; tower shield proficiency
  not distinguished from regular shield proficiency)
- Two-weapon fighting penalty tables
- Splatbook YAML files beyond SRD core
- Equipment persistence (equip/unequip saves)
- Wild Shape form mechanics
