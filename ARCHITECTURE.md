# HeroForge Anew — Architecture

A PyQt6 desktop application for D&D 3.5e character management. Clean separation
between the **rules engine** (pure Python, no GUI), the **data layer** (YAML
rulebook definitions), the **export layer** (PDF via ReportLab), and the
**presentation layer** (PyQt6 widgets).

---

## Directory layout

```
src/heroforge/
├── engine/                 # Pure Python, zero GUI dependencies
│   ├── bonus.py            # BonusType enum, BonusEntry, BonusPool, aggregate()
│   ├── stat.py             # StatNode, StatGraph: reactive lazy-eval DAG
│   ├── character.py        # Character, ChangeNotifier, ClassLevel, BuffState
│   ├── effects.py          # BuffDefinition, BuffCategory, formula evaluation
│   ├── classes_races.py    # ClassDefinition, RaceDefinition, apply_race()
│   ├── skills.py           # SkillDefinition, register_skills_on_character()
│   ├── feats.py            # FeatDefinition, FeatKind, FeatRegistry
│   ├── prerequisites.py    # PrerequisiteChecker, FeatAvailability
│   ├── templates.py        # TemplateDefinition, apply_template()
│   └── persistence.py      # save/load character YAML
│
├── rules/
│   ├── loader.py           # StatsLoader, SpellsLoader, FeatsLoader, etc.
│   └── core/               # One YAML file per data domain
│       ├── stats.yaml
│       ├── skills.yaml
│       ├── classes.yaml
│       ├── races.yaml
│       ├── feats_phb.yaml
│       ├── spells_phb.yaml
│       └── templates.yaml
│
├── export/
│   ├── sheet_data.py       # gather(): Character → SheetData
│   └── renderer.py         # render_pdf(): SheetData → PDF via ReportLab
│
└── ui/                     # PyQt6 — never imported by engine/ or export/
    ├── app.py              # QApplication entry point, Ctrl+C handling
    ├── app_state.py        # AppState: holds all registries + active Character
    ├── main_window.py      # MainWindow: tabs, menus, file I/O
    ├── sheets/
    │   ├── sheet1_summary.py   # Identity, abilities, combat stats, buffs
    │   ├── sheet2_skills.py    # Full skill table
    │   └── sheet3_feats.py     # Taken feats + feat picker
    ├── dialogs/
    │   ├── class_dialog.py     # Class/level selection
    │   └── race_dialog.py      # Race selection
    └── widgets/
        ├── common.py           # LabeledField, StatDisplay, SectionHeader, etc.
        ├── ability_block.py    # Six ability score rows
        ├── combat_stats.py     # AC, saves, BAB, HP, initiative, speed
        └── buff_panel.py       # Scrollable buff toggle list

tests/
├── conftest.py             # QT_QPA_PLATFORM=offscreen, qapp fixture
├── test_bonus.py
├── test_stat.py
├── test_character.py
├── test_effects.py
├── test_classes_races.py
├── test_skills.py
├── test_feats.py
├── test_prerequisites.py
├── test_templates.py
├── test_persistence.py
├── test_stats_yaml.py
├── test_spells_yaml.py
├── test_export.py
└── test_ui_smoke.py
```

---

## Layer 1: Bonus system (`engine/bonus.py`)

`BonusType` enum covers all 3.5e bonus types. `BonusEntry` is a frozen value
object (value, type, source, optional condition lambda). `BonusPool` collects
entries keyed by source name — `set_source` / `clear_source` are idempotent.

`aggregate()` implements the core stacking rules: dodge, racial, and untyped
always stack; all other types take highest only; penalties always stack.

## Layer 2: Stat graph (`engine/stat.py`)

`StatNode` is a single computable stat (key, base value, input dependencies,
pool keys, compute function). `StatGraph` is the DAG registry with lazy
evaluation and dirty-cascade invalidation. Nodes are computed on first access
after invalidation.

Helper compute functions: `compute_ability_modifier`, `compute_sum`,
`compute_capped_dex`, `compute_save`.

## Layer 3: Character (`engine/character.py`)

The central mutable object. Holds identity fields, raw ability scores, class
levels, race, feats, skills, equipment, buff states, and DM overrides. Owns a
`StatGraph` and a dict of `BonusPool`s.

`_bootstrap_stat_graph()` wires up all standard 3.5e stat nodes (ability
scores → modifiers → saves/attacks/AC/HP/etc.).

All mutations go through public methods (`set_ability_score`, `toggle_buff`,
`set_class_levels`, `add_feat`, etc.) which handle pool updates, stat
invalidation, and change notification via `ChangeNotifier`.

`ChangeNotifier` is a simple observer list — the UI subscribes callbacks; the
Character calls `notify(changed_keys)` on mutation. Keeps the engine decoupled
from Qt signals.

## Layer 4: Effects (`engine/effects.py`)

`BuffDefinition` models any source of stat bonuses: spells, feats, conditions,
items. Each has a list of `BonusEffect` (target pool, bonus type, value or
CL-scaling formula string, optional condition). `BuffCategory` enum tags the
source kind.

`evaluate_formula()` safely evaluates CL-scaling expressions like
`"2 + caster_level // 6"` in a restricted namespace.

`BuffRegistry` provides name-based lookup.

## Layer 5: Classes and races (`engine/classes_races.py`)

`ClassDefinition` holds BAB/save progressions, hit die, class skills, features,
and optional spellcasting info. `RaceDefinition` holds ability modifiers, size,
speed, subtypes, and racial features.

`apply_race()` wires racial ability bonuses into the Character's pools.
`bab_at_level()` and `save_at_level()` compute progression values.

`ClassRegistry` and `RaceRegistry` provide name-based lookup.

## Layer 6: Skills (`engine/skills.py`)

`SkillDefinition` holds ability key, trained-only flag, armor check penalty
flag, and synergy declarations. `register_skills_on_character()` creates a
pool and stat node per skill on the Character. `set_skill_ranks()` updates
ranks. `compute_skill_total()` returns a full breakdown.

## Layer 7: Feats (`engine/feats.py`)

`FeatDefinition` has a `FeatKind` (ALWAYS_ON, CONDITIONAL, PASSIVE), optional
prerequisites, optional `BuffDefinition` for stat effects, and optional
`FeatParameterSpec` for parameterized feats (e.g. Power Attack amount).

Always-on feats auto-apply their buff on `Character.add_feat()`. Conditional
feats register their buff for user toggling via the buffs panel.

## Layer 8: Prerequisites (`engine/prerequisites.py`)

Prerequisite types: `StatPrereq`, `AbilityPrereq`, `FeatPrereq`, `SkillPrereq`,
plus compound `all_of` / `any_of` / `none_of`.

`PrerequisiteChecker` evaluates prereqs against a Character and classifies each
feat as one of `FeatAvailability`: AVAILABLE, TAKEN, OVERRIDE, UNAVAILABLE, or
CHAIN_PARTIAL. DM overrides short-circuit to OVERRIDE.

## Layer 9: Templates (`engine/templates.py`)

`TemplateDefinition` models creature templates (Half-Celestial, etc.) with
ability modifiers, type/subtype changes, natural armor, granted feats, and
partial-application support.

`apply_template()` / `remove_template()` wire effects into the Character.
`effective_type()` and `effective_subtypes()` resolve the final creature type
after all template layers.

## Layer 10: Persistence (`engine/persistence.py`)

`save_character()` serializes to `.char.yaml`. `load_character()` deserializes
and re-applies race, class, template, and feat effects through the normal
engine methods so all derived stats recompute correctly. Schema version checked
on load.

---

## Rules layer (`rules/`)

`rules/loader.py` contains one Loader class per data domain (StatsLoader,
SpellsLoader, FeatsLoader, SkillsLoader, TemplatesLoader, ClassesLoader,
RacesLoader). Each reads its YAML file, builds engine objects via the
`build_*_from_yaml()` functions, and populates the corresponding registry.

YAML files under `rules/core/` contain all PHB data. The design supports
additional sourcebook directories (e.g. `rules/spell_compendium/`) with
override semantics, though only core is currently populated.

---

## Export layer (`export/`)

`sheet_data.py` defines `SheetData` and component dataclasses (`IdentityData`,
`AbilityData`, `CombatData`, `SkillRow`, `FeatRow`, `BuffRow`). `gather()`
extracts a complete display-ready snapshot from a Character.

`renderer.py` takes a `SheetData` and writes a PDF via ReportLab.

---

## UI layer (`ui/`)

### AppState (`app_state.py`)

Single object holding all registries and the active `Character`. Created by
`MainWindow`. Methods: `load_rules()`, `new_character()`,
`set_character()`, `skill_total()`.

### MainWindow (`main_window.py`)

Top-level `QMainWindow` with a tab widget (Sheet1, Sheet2, Sheet3, plus
placeholder tabs for Spells, Equipment, Notes). Owns the `AppState`. Subscribes
to `character.on_change` and routes notifications to the active sheet tab.

File menu: New, Open, Save, Save As, Export PDF. Character menu: Change Race,
Change Class.

`closeEvent` prompts to save if modified.

### Sheets

Each sheet takes an `AppState` reference. A `_building` flag suppresses signal
feedback during construction.

- **Sheet1Summary** — three-column layout: identity fields, ability block +
  combat stats, buff panel. Ability changes cascade through the stat graph.
- **Sheet2Skills** — table widget with columns for class-skill marker, name,
  ability, ranks (editable), misc, total.
- **Sheet3Feats** — splitter with taken-feats list (left) and filterable
  available-feats picker (right) with color-coded availability.

### Widgets

Reusable components in `widgets/`: `LabeledField`, `StatDisplay`,
`CompactSpinBox`, `ModifierLabel`, `SectionHeader`, `HRule`, `AbilityBlock`,
`CombatStats`, `BuffPanel`.

---

## Key design constraints

- `engine/` has **zero imports from `ui/`**. The engine is testable headlessly.
- `export/` has **zero imports from `ui/`**. PDF output matches UI display
  because both use the same Character data.
- YAML data files contain **no Python code**. Formulas are strings evaluated
  in a sandboxed context.
- Adding a new sourcebook = adding YAML files. No Python changes unless the
  book introduces a genuinely new kind of mechanic.

---

## Not yet implemented

- Spells tab, Equipment tab, Notes tab (placeholder tabs exist)
- Companion/familiar sub-objects
- Combat iteratives and TWF
- Splatbook YAML files beyond core
- Ongoing prerequisite checking (snapshot only currently)
- Character validation / legality report
