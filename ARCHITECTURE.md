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
│   │                       #   CharacterLevel, BuffState,
│   │                       #   DmOverride, grapple,
│   │                       #   carrying capacity
│   ├── enums.py            # Ability, Alignment, Save, Size
│   ├── size.py             # Size ladder, step_size(),
│   │                       #   PHB Table 7-4 damage steps
│   ├── proficiency.py      # Proficiencies, nonproficiency
│   │                       #   penalties
│   ├── item_properties.py  # Armour/shield/weapon special
│   │                       #   properties
│   ├── defenses.py         # Damage reduction, energy
│   │                       #   resistance, immunity
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
│   ├── sheet_schema.py     # Sheet + sub-section
│   │                       #   dataclasses (typed output)
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
│   ├── deities.py          # DeityDefinition,
│   │                       #   DeityRegistry
│   └── resources.py        # ResourceTracker (uses/day)
│
├── rules/
│   ├── rules.py            # Rules dataclass, get_rules(),
│   │                       #   set_rules(), reset_rules()
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
│   ├── _gen_common.py      # enum_ident(), emit_member()
│   │                       #   shared by YAML→StrEnum tools
│   ├── _gen_magic_item_enums.py  # check-magic-items CLI
│   ├── _gen_pool_keys.py   # check-pool-keys CLI
│   └── core/               # YAML data files
│       ├── stats.yaml
│       ├── skills.yaml
│       ├── pool_keys.py    # PoolKey StrEnum (generated)
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
│       ├── deities.yaml      # 194 LG deities
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

Tests co-locate with the package they cover, under a
per-subpackage `test/` directory (`foo_test.py`, Go-
style). The legacy top-level `tests/` directory still
hosts cross-cutting and integration tests pending
placement decisions.

src/heroforge/engine/test/      # unit tests for engine/
  bonus_test.py
  stat_test.py
  character_test.py
  effects_test.py
  skills_test.py
  feats_test.py
  prerequisites_test.py
  templates_test.py
  persistence_test.py
  equipment_test.py
  spellcasting_test.py
  domains_test.py
  magic_items_test.py
  races_test.py
  classes_test.py
  charopt_builds_test.py     # end-to-end character math
  yaml_errors_test.py        # malformed-YAML error cases
  bad_yaml/                  # fixtures for yaml_errors_test

src/heroforge/rules/test/       # unit tests for rules/
  gen_common_test.py
  magic_item_enums_test.py
  pool_keys_test.py
  known_test.py              # KnownXxx enum congruence

src/heroforge/ui/test/          # unit tests for ui/
  conftest.py                # QT_QPA_PLATFORM=offscreen, qapp
  ui_smoke_test.py           # TODO: split per sheet/widget

tests/                          # pending placement / integration
  test_combat.py             # grapple/carrying capacity
  test_skill_allocation.py   # per-level skill budget
  test_class_features.py     # rage, inspire courage
  test_export.py             # sheet_data + renderer
  test_stats_yaml.py
  test_spells_yaml.py
  test_spells_srd_yaml.py
  test_conditions_srd_yaml.py
  test_feats_srd_yaml.py
  integration/
    test_full_builds.py      # charsheet CLI subprocess
    base_characters/         # 28 .char.yaml + .expected.yaml
    custom_characters/       # drufus, farzin, barzay
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

Every `BonusPool` is identified by a `PoolKey` StrEnum member
(`rules/core/pool_keys.py`, generated from `stats.yaml` and
`skills.yaml` via `uv run check-pool-keys --fix`). Effect
declarations targeting unknown pool keys fail at load time
(cattrs-style coercion in `BonusEffect.__post_init__` and a
`PoolKey` check in `StatsLoader`).

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
  per-level skill point allocation, feats acquired
  at that level (with source tag), an optional
  `ability_bump` (every-4th-level +1), and
  `inherent_bumps` (consumed Tomes/Manuals).
- `BuffState` — per-buff persistent state: active flag,
  optional caster level, optional parameter value.
- `DmOverride` — a DM-granted override: target name + note.

Per-level methods: `add_level()`, `remove_last_level()`,
`set_level_class()`, `set_level_hp()`,
`set_level_skill_ranks()`, `skill_points_for_level()`,
`set_level_ability_bump()`, `add_inherent_bump()`,
`remove_inherent_bump()`.

Ability bump helpers: `_level_bump_total(ability)` counts
every-4th-level bumps; `_inherent_bonus_total(ability)`
returns the highest inherent bonus (capped at +5, per 3.5e
non-stacking rules); `int_mod_at_level(char_level)` gives
the INT modifier using only base + bumps/inherent up to
that level (skill-point budgets are not retroactive).

Computed properties: `class_level_map` (cumulative levels
per class), `total_level`, `attack_iteratives()`,
`multiclass_xp_penalty()`, `validate()`.

Combat helpers: `_compute_size_mod_grapple()`,
`_compute_size_mod_hide()`, `carrying_capacity()`.

`size` is a computed property, not stored state: race sets
the base, a template overrides it, and active effects move it
by whole categories on top (`_active_size_steps()`). Because a
size change is not a pool entry, nothing in the pool cascade
sees it, so `toggle_buff` invalidates `SIZE_DEPENDENT_NODES`
(`ac`, `attack_melee`, `attack_ranged`, `grapple`) by hand.

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

## Layer 3b: Size (`engine/size.py`)

`SIZE_ORDER` is the Fine..Colossal ladder; `step_size()` moves
a category along it, clamped at both ends. `net_size_steps()`
combines competing effects the way `bonus.aggregate()` treats
a size-typed bonus — largest increase plus largest decrease —
so two +1 effects are one category and Enlarge Person cancels
Reduce Person. The PHB states no general rule for stacking
size changes; this is an engine decision, chosen to match how
the same spells' size bonuses to STR and DEX already combine.

An effect declares `size_steps:` on its YAML entry, which
becomes `BuffDefinition.size_steps` and is handed to
`Character.register_buff_definition()`. Enlarge Person is
`+1`, Reduce Person `-1`, Righteous Might `+1`. The `-1` (or
`+1`) those spells print for attack rolls and AC is *not* in
their effects list: it falls out of the size table, and
listing it as well would count it twice.

Weapon damage by size is deliberately two mechanisms, because
PHB p. 114 is:

- Small and Medium are printed per weapon in Table 7-5 and are
  not derivable from one another (heavy crossbow 1d8 -> 1d10,
  greatsword 1d10 -> 2d6), so `WeaponDefinition` carries both
  `damage_dice` and `damage_dice_small`.
- Large and Tiny are the two columns of Table 7-4, keyed by
  the Medium value, via `large_damage_dice()` and
  `tiny_damage_dice()`.

The two Table 7-4 columns are **not** symmetric about Medium.
Large is one size category up. Tiny is *two* down, because
Small sits between Medium and Tiny and has its own printed
column in Table 7-5 — so a weapon's Tiny damage is one step
below its **Small** damage, not one step below its Medium
damage. An API taking a signed `steps` would have to make -1
mean two categories, so the columns are named lookups
instead. `size_test.py` checks the two printed tables agree,
asserting for every weapon in the data that the Tiny value is
exactly one rung below the Small value on `DAMAGE_LADDER`.

`damage_dice_for_size()` picks between them; sizes outside
Tiny..Large raise rather than extrapolate. `weapons.damage_dice()`
applies it per equipped weapon, and an explicit `damage_dice`
on the equipment entry still wins as an author override.

A monk's unarmed strike *replaces* that lookup rather than
modifying it: `weapons.monk_unarmed_damage()` is PHB Table
3-10 (Medium) and Table 3-11 (Small and Large), indexed by
the `effective_monk_level_damage` derived pool. The Monk
class contributes its level and the Monk's Belt contributes
5, so DMG p. 248's two cases — "five levels higher" for a
monk and "a 5th-level monk" for anyone else — both fall out
of the pool with no special casing. Only Small, Medium and
Large are printed, so anything else raises. Levels past 20
hold at the last row.

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
info, `proficiencies`, and prestige class fields
(`max_level`, `is_prestige`, `entry_prerequisites`,
`ongoing_prerequisites`). `SpellcastingInfo` records cast
type (arcane/divine), key ability, preparation mode, max
spell level, and starting level. `ClassFeature` records a
feature gained at a specific class level, and carries the
numbers that feature is worth: `uses` (a formula for uses
per day plus a unit) and `values` (named formulas — smite's
`attack` and `damage`, a turning check, sneak attack dice).
Both are evaluated per character by `evaluate_formula`, so a
feature that scales with level or an ability is **one**
entry whose formulas do the scaling rather than one entry
per tier.

Two kinds of feature deliberately keep their per-tier
entries instead:

- Those that define a toggleable buff. A bard's Inspire
  Courage +1..+4 and a barbarian's rage / greater rage /
  mighty rage are separate `BuffDefinition`s with mutual
  exclusion between them; folding them together would
  delete that wiring. They keep their tiers and each gains
  its own number.
- Those an ACF names. Fighter and wizard bonus feat slots
  are keyed `bonus_feat_1..20` and `bonus_feat_wizard_{level}`
  precisely so `replaces:` can target one, so they stay.

`when` records a condition the engine cannot evaluate
because it is about the *target* rather than the character —
insightful strike applies only to creatures that can be
critically hit, sneak attack only when the target is denied
its DEX bonus. It is text, not a predicate, until the
conditional-effects panel lands. `gate` remains for
conditions that *are* about the character (armor worn, load
carried) and is evaluated.

Consolidating these tiers corrected several progressions
that had drifted from the book: paladin smite evil was at
levels 1/5/8/11/14/17/20 rather than PHB Table 3-12's
1/5/10/15/20; barbarian rage at 1/4/7/10/13/16/19 rather
than Table 3-3's 1/4/8/12/16/20; druid wild shape at 4-10
rather than Table 3-8's 5/6/7/10/14/18; and monk slow fall
at 4/5/8 rather than Table 3-10's every second level from
4th.

`RaceDefinition` holds ability modifiers, size, speed,
subtypes, and racial features.

`DomainDefinition` holds name, granted power text, and
domain spells (levels 1-9). `DomainRegistry` provides
name-based lookup for all 22 SRD cleric domains.

`DeityDefinition` (`engine/deities.py`) holds a deity's
alignment, favored weapon, and available domains;
`DeityRegistry` provides name-based lookup over the full
Living Greyhawk roster (194 deities, `core/deities.yaml`).
The War domain consults it: a War-domain cleric's deity's
favored weapon drives a granted Weapon Focus. A character's
`deity:` is validated against `KnownDeity` on load (empty
is allowed); the `KnownCoreDeity` enum (`core/deities.py`)
mirrors the YAML keys and the congruence test enforces
parity.

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
`compute_skill_total()` returns a full breakdown, including
the two modifiers that are neither ranks nor pool entries:
Jump's speed modifier and Hide's size modifier (PHB Table
8-1), which a Small race and Enlarge/Reduce Person both move.

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
`"feat:<instance key>"` — they never appear in the buff
panel.

A feat's *instance key* (`character.feat_instance_key()`)
is its name, plus the selection for selection feats:
`Weapon Focus (Longsword)` and `Weapon Focus (Greatsword)`
are two distinct feats, each with its own entry, its own
pool source and its own removal. Feats with a numeric
parameter (Power Attack) are one feat whose parameter
varies, so the parameter is not part of their identity.
`remove_feat(..., selection=...)` targets one instance;
without a selection it removes every instance of the name.
Conditional feats register their buff for user toggling
via the buffs panel. Dodge is conditional (per 3.5e rules
the player designates one opponent per action).

Selection feats (Skill Focus, Weapon Focus) carry a
`parameterized_selection` block describing the choice
(weapon/skill) the player makes. The chosen name is stored
on the feat entry's `parameter:` field and substituted into
effect *targets*: `resolve_feat_effects(..., selection=...)`
replaces `$selection` in a target with the pool-key form of
the choice (e.g. `skill_$selection` + "Knowledge (Religion)"
→ `skill_knowledge_religion`, matching
`SkillDefinition.pool_key`). These feats build their buff
per-character once the choice is known, so the cached
`buff_definition` is skipped at load (`has_selection`).

## Layer 7b: Proficiency (`engine/proficiency.py`)

A character's proficiencies are derived, never stored: the
union of every class they have levels in, their race, and the
proficiency feats they hold. Dropping a class or a feat drops
the proficiency with it.

`Proficiencies` names whole categories (`weapons: [simple,
martial]`, `armor: [light, medium, heavy]`, `shields`,
`tower_shields`) plus `weapon_names` for the individual
weapons that the wizard's short list, the monk's special
weapons and the bard's and rogue's extras are printed as.

`ClassDefinition.proficiencies` is `None` for a class that
does not state a block. Prestige classes normally grant
nothing and leave it unset; every *base* class must declare
one, which `proficiency_test.py` enforces — an omission would
silently make every character of that class nonproficient
with everything, which is a much worse failure than a loud
missing-data test.

Races contribute through two different fields because they
are two different rules: `weapon_proficiencies` is outright
proficiency (an elf's Martial Weapon Proficiency bonus feats,
PHB p. 16), while `weapon_familiarity` only moves an exotic
weapon into the martial category (a dwarf's waraxe, PHB
p. 15) — a dwarf still needs martial proficiency to use it.

Penalties:

- Armor or a shield the character is not proficient with
  applies **its own armor check penalty** to attack rolls and
  to every STR- and DEX-based ability and skill check (PHB
  p. 122). Armor and shield nonproficiency stack, and they
  reach skills that carry no armor check penalty of their own
  — Ride takes the hit here and nowhere else.
  `refresh_proficiency_penalties()` installs both from
  scratch, so it is idempotent and safe to call on any
  equipment, feat or level change.
- A weapon the character is not proficient with costs -4 on
  attack rolls with that weapon (PHB p. 113). That one is
  applied per weapon in `engine/weapons.py`, where the
  weapon's own pool lives.

All three appear in the sheet's breakdowns as
`nonproficient_armor`, `nonproficient_shield` and
`nonproficient`.

## Layer 7c: Item properties (`engine/item_properties.py`)

The `properties:` list on an equipment entry, loaded from a
per-book `item_properties.yaml` into `Rules.item_properties`.

Both SRD lists are covered in full (magicArmor.htm and
magicWeapons.htm; the specific named items belong under
`magic_items/`, not here). Entries fall into three groups,
distinguished in their notes:

**Wired** — permanent, and the stat exists: the shadow,
silent moves and slick families (+5/+10/+15 competence on
Hide, Move Silently and Escape Artist), spell resistance
13/15/17/19, blueshine, speed and distance.

**Permanent but unmodelled** — the benefit is always on, but
the sheet has no such stat. Only fortification's chance to
negate a critical is left here; the energy resistances and
invulnerability's damage reduction now land in the defenses
section (Layer 7d).

**Conditional** — defined so the name is recognised and
described, and carrying no effects, because a number would be
wrong most of the time:

- activated — blinking (1/day), vanishing (2/day), mindarmor
  (3/day), deathward (1/day), animated (on command)
- reactive — arrow deflection
- conditional on the target — bane, fiendslayer, truedeath,
  illusion bane, revelation
- conditional on the roll or situation — wounding (on a hit),
  mind cloaking (only against mind-affecting effects), precise
  (only against cover and concealment)

Those belong in the conditional-effects panel, not a pool.

Lookup resolves the forms people actually write. The books
name grades with a trailing comma — `Shadow, Greater` — while
character files write `greater shadow`; parenthetical grades
and qualifiers appear too, as in `truedeath (greater)` and
`bane (undead)`. All of those reach the one definition.

An unrecognised name is deliberately **not** an error: the
vocabulary is open and books arrive piecemeal, so an unknown
property displays and does nothing. Making it an error needs
complete coverage across every book first.

`equipment._apply_properties()` installs an armour or
shield's effects under `<slot>:properties`, replacing the
whole set so re-equipping or unequipping drops the old one.
Two properties are not bonuses and so are resolved directly
rather than through a pool: speed adds an attack to the
weapon's iterative sequence, and distance doubles the
weapon's own range increment before any feat extends it.

## Layer 7d: Defenses (`engine/defenses.py`)

Damage reduction, resistance to energy and immunity. None of
them is a bonus, so none can live in a BonusPool: DR is keyed
by what bypasses it and resistance by which energy, and in
both cases the best single source applies rather than a sum
(DMG p. 291; Rules Compendium p. 48).

DR keeps **one entry per bypass** rather than collapsing to a
number, because "the best in a given situation" depends on
what is attacking — DR 2/- and DR 5/magic are both worth
knowing. The sheet prints them as `2/-` and `5/magic`.
Immunity to an energy type supersedes resistance to it, so
the resistance entry is dropped rather than shown beside it.

A source declares them with a `defenses:` block carrying
`damage_reduction`, `energy_resistance` and `immunities`; an
`amount` may be a formula, which is how the barbarian's
progression is written. `ItemPropertyDefinition` and
`ClassFeature` both accept one, and `collect_defenses()`
aggregates across everything equipped and every class feature
at level.

Four sources feed it: equipped item properties, worn magic
items, creature templates and class features. A worn item may
name something chosen when it was made — a ring of energy
resistance picks its energy — so a `worn:` entry can be
`{name, parameter}` instead of a bare name, and `$parameter`
in a defenses key is replaced with the choice. Template
amounts may be formulas, which is how the half-outsiders'
"5/magic at HD 11 or less, 10/magic at 12 or more" is
written.

Immunity to an energy type is listed in `combat.immunities`
and removes the matching resistance, so a red half-dragon
wearing a ring of fire resistance shows immunity alone rather
than both.

Not yet reaching it: the Celestial and Fiendish Creature
templates, whose resistance scales with Hit Dice on a table
that has not been verified, and adamantine or starmetal
armour, whose DR depends on the armour's category rather than
on the material alone.

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

### Gates (`engine/gates.py`)

A gate is a named `Callable[[Character], bool]` deciding
when an effect applies: `not_heavy_armor`, `not_heavy_load`,
`unarmored`, `no_shield`, `light_load_or_less` and
`light_armor_or_less` (the swashbuckler's grace, insightful
strike and dodge bonus are all lost in medium or heavy
armor). Each key is a `KnownCoreGate` member with a
predicate in `GATE_PREDICATES`; the congruence tests catch
drift between the two.

A gate answers a question about the *character*. A question
about the *target* — "is this creature subject to critical
hits?" — cannot be a gate, and is recorded as
`ClassFeature.when` text instead.

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
A top-level `domains:` list holds cleric domain choices
(validated against `KnownDomain`); the domains' granted
powers are display-only (not yet mechanically wired).
`load_character()` deserializes and re-applies race,
template, and feat effects through the normal engine
methods so all derived stats recompute correctly.

## Layer 10b: Sheet extraction (`engine/sheet.py`)

`extract_sheet(path, app_state)` loads a `.char.yaml` and
returns a typed `Sheet` (defined in
`engine/sheet_schema.py`) containing every numerical value
with full bonus-type breakdowns.
`gather_sheet(character, app_state)` does the same from an
already-loaded Character.

CLI entry points: `uv run charsheet input.char.yaml` and
`python -m heroforge.engine.sheet input.char.yaml` both
serialize the Sheet via the shared cattrs converter
(`rules/schema.py`) and print YAML to stdout; `-o file.yaml`
writes to file.

`Sheet` includes: identity, abilities (base + typed
bonuses + score + mod), combat stats (base + typed bonuses
+ total for AC, saves, attacks, grapple, HP, initiative,
speed, SR), attack iteratives, skills (ranks + ability_mod
+ typed bonuses), carrying capacity, feats, class
features (a mapping keyed by feature name, each with its
description and its resolved `uses` / `values` / `when` /
`gated_by`), spellcasting (slots, DCs, spells known),
domains (granted power + domain spells per chosen
domain), special qualities, and equipment.

The cattrs converter has per-class `omit_if_default`
unstructure hooks registered for every sheet dataclass,
so fields left at their default (None / empty dict /
empty list) disappear from the YAML. Required fields
(totals, scores) always emit.

Integration coverage lives in
`tests/integration/test_full_builds.py`, which invokes
the CLI as a subprocess and compares stdout byte-for-byte
against `*.expected.yaml` golden files under
`base_characters/` and `custom_characters/`.

## Layer 11: Equipment (`engine/equipment.py`)

`ArmorDefinition` and `WeaponDefinition` are frozen
dataclasses with all SRD stats. `ArmorRegistry` and
`WeaponRegistry` provide name-based lookup.

`equip_armor()` / `equip_shield()` push armor/shield
bonuses into AC pool and armor check penalties into
skill pools. Both accept an optional `material`
parameter; `adjust_for_material()` modifies ACP,
max DEX, and ASF for Mithral (-3 ACP, +2 DEX,
-10% ASF), Darkwood (-2 ACP), etc.

`equip_item()` / `unequip_item()` wire worn magic
item effects directly into pools via `set_source()`
(items are permanent, NOT buff-toggled). Source key
is `"item:{name}"`.

`equipment_display_name()` builds a display name
from base, enhancement, and material parts.

YAML format:
```yaml
equipment:
  armor:
    base: Full Plate
    enhancement: 1
    material: Mithral
  shield:
    base: Heavy Steel Shield
  worn:
    - Belt of Giant Strength +4
    - Periapt of Wisdom +4
  weapons:
    - base: Lance
      enhancement: 1
      material: Bronzewood
      properties: [Keen]
```

Weapons get per-weapon attack and damage lines — see
`engine/weapons.py` under "Not yet implemented" below for
what is and is not routed through them.

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

`rules/rules.py` defines the `Rules` dataclass — a single
container for every rule-definition registry
(feats, classes, races, skills, templates, buffs,
conditions, domains, magic items, spell compendium, armor,
weapons, materials, derived pools, and the
`PrerequisiteChecker`) plus a lazy module-level accessor:

- `get_rules()` returns the process-wide `Rules`, calling
  `Rules.load()` (which runs every loader in `rules/loader.py`
  against the YAML files under each book directory in
  `rules/`) on first access.
- `set_rules(r)` / `reset_rules()` let tests swap or clear
  the singleton.

Engine and export code reads rules via `get_rules()` — there
is no wiring of registry references onto `Character` or
`AppState`. Tests isolate via the autouse fixture in the
project-root `conftest.py`, which pointer-swaps a
session-scoped cached `Rules` around each test so YAML is
parsed once per test run.

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

`validate_domain_spells()` cross-checks every spell named in
`domains.yaml` against the loaded `SpellCompendium` and raises a
single `LoaderError` listing every unknown name. `Rules.load()`
calls it in the final-wiring step rather than inside
`DomainsLoader`, because domains load before the compendium.

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
`magic_items.yaml` (a flat mapping keyed by item name)
and structures each entry as a `MagicItemDefinition`.
Magic items are NOT buffs — when equipped, effects
flow into the character's BonusPools via
`engine.equipment.equip_item()`, not through the
buff-toggle system. Transitory item activations
(e.g. Boots of Speed's 10 rd/day haste) reuse the
corresponding spell buff where one exists, or are
tracked via `ResourceTracker` and handled manually
by the player.

YAML files under `rules/core/` contain full SRD data:
- 16 base classes (11 PHB + 5 NPC) + 15 prestige classes
- 7 races, 36 skills
- 110 feats (alphabetically sorted in feats.yaml)
- 601 spell compendium entries (with inline buff effects)
- 22 cleric domains, 194 deities
- 18 armor/shields, 63 weapons
- ~70 magic items
- 12 creature templates
- ~15 class feature buffs (rage, inspire courage, etc.)

`classes/` directory has one YAML per class. Each file is
a mapping keyed by the class name directly; prestige
classes are marked with `is_prestige: true` rather than
living under a separate top-level key. (`ClassesLoader`'s
docstring still describes an older `classes:` /
`prestige_classes:` layout that no file uses.)

### Per-book layout

Each top-level subdirectory of `rules/` is a "book":
`core/` holds the SRD, `custom/` holds homebrew, and one
folder per published splatbook holds its own content.
`Rules.load()` discovers books by globbing `rules/` —
adding a splatbook means dropping in a new folder; no
edits to `rules.py`, `known.py`, or
`_gen_magic_item_enums.py` are required.

Per-book file convention (all optional):
```
<book>/feats.yaml          + feats.py        (KnownXxxFeat)
<book>/classes/*.yaml      + classes.py      (KnownXxxClass)
<book>/magic_items.yaml    + magic_items.py  (KnownXxxMagicItem)
<book>/materials.yaml      + materials.py    (KnownXxxMaterial)
```
The Python StrEnum class is named
`Known<BookCamelCase><CategorySingular>` (e.g.
`KnownCompleteWarriorFeat`). `magic_items.py` files
across all books are auto-generated by
`_gen_magic_item_enums.py`; the others are written by hand.

Book load order: `core` first, `custom` last,
everything else alphabetical between. Custom is loaded
last so its entries override on name collision.

Currently populated splatbook directories:
`complete_adventurer/`, `complete_divine/`,
`complete_mage/`, `complete_scoundrel/`,
`complete_warrior/`, `draconomicon/`,
`dragon_magazine/`,
`dungeon_master_guide/`, `eberron_campaign_setting/`,
`heroes_of_battle/`, `magic_item_compendium/`,
`miniatures_handbook/`, `monster_manual/`,
`races_of_stone/`, `races_of_the_wild/`, `sandstorm/`,
`spell_compendium/`. Each was seeded with the items
needed by existing custom-character integration tests;
the rest of each book remains to be added when
demanded by a character.

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

Holds the active mutable `Character`. Created by
`MainWindow`. Methods: `load_rules()`, `new_character()`,
`set_character()`, `skill_total()`.

Rule-definition registries (feat, class, skill, etc.) live
on the process-wide `Rules` singleton in
`heroforge.rules.rules`; AppState exposes each one as a
`@property` shim that forwards to `get_rules()` so existing
UI code that reads `app_state.feat_registry` / etc.
continues to work. New code should call `get_rules()`
directly.

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

- Per-weapon attack breakdowns in sheet extraction
- Resources (uses/day) in sheet extraction
  (ResourceTracker not yet wired to Character)
- Companion/familiar sub-objects (placeholder fields
  exist on Character but no logic)
- Domain mechanical effects: cleric domains persist in
  `.char.yaml` and render in the sheet (granted-power text
  + domain spell list). The **War** domain is wired —
  it grants Weapon Focus with the deity's favored weapon
  (via `deities.yaml`) as a *derived* feat: added to
  `Character.feats` on load with source `domain:War` and
  `derived=True`, so it renders on the sheet as
  `Weapon Focus (<weapon>)` but is never written to
  `lv.feats` and so never saved. Changing deity changes the
  granted feat and cannot strand a stale one. The domain
  spell slot is modelled: `domain_slots_per_day` on the
  sheet's `SpellcastingEntry` carries one restricted slot
  per castable spell level from 1st up (PHB p. 32), kept
  apart from `slots_per_day` because it can only be filled
  from the character's domains. It is keyed off the
  `domains` class feature rather than the class name, so a
  PrC advancing domain casting picks it up by declaring the
  feature. The eight daily-limited granted powers are
  real `ResourceTracker`s, built by
  `domains.refresh_domain_resources()` and emitted as the
  sheet's `resources:` block: Animal, Death, Destruction,
  Luck, Protection, Strength and Sun are once per day,
  while Travel is a pool of 1 round per cleric level, so
  `ResourceTracker.unit` distinguishes rounds from uses.
  Trackers are derived, not saved — remaining uses do not
  round-trip yet. A resource that also declares `effects:`
  is registered as a toggleable buff under its own name,
  so Strength's feat of strength and Protection's ward
  apply their cleric-level-scaled bonus when the player
  activates them rather than always-on. Protective Ward is
  approximated: RAW it wards one touched creature's *next*
  save, so modelling it as a self-buff on all three saves
  is right only when the cleric wards himself. Still
  display-only: domain
  spells added to the prepared-spell list, and Knowledge's
  +1 caster level on divinations (and the other
  +1-CL-for-a-spell-subset domains, which the single flat
  `caster_level` field can't express). War's Martial Weapon
  Proficiency half is still a no-op: the domain does not yet
  add the deity's favored weapon to the cleric's
  proficiencies, though the machinery to honour it now
  exists.
- Cross-class skill *cost* is not modelled (a cross-class
  rank costs 2 points and caps at a half number); see
  `docs/plans/skill-points-and-cross-class.md`. Which
  skills *are* class skills is resolved by
  `skills.class_skills_for_character()`: the union across
  the character's classes (PHB p. 60) plus the grants from
  the Animal, Knowledge, Plant, Travel and Trickery domains
  (PHB p. 31). It expands umbrella entries, so a bare
  `Craft` covers `Craft (Conspiracy)` and `Knowledge (all)`
  covers every Knowledge skill. Note the per-level variant
  used by `validate_skill_allocation` and the class sheet
  answers a different question — the class taken *at that
  level*, which is what cost and cap depend on — and is
  deliberately left separate.
- Wizard school specialization is modelled as far as the
  data allows: `Specialization` (school + prohibited
  schools) is character state, validated on load against
  PHB p. 57 — divination can never be given up, the
  specialty cannot be prohibited, and a diviner gives up
  one school where everyone else gives up two. The
  specialty slot is a separate restricted track
  (`specialist_slots_per_day`), one per castable spell
  level including cantrips, alongside the general
  allotment rather than folded into it.
  **Not** enforced: which spells may fill a specialty slot,
  and the bar on preparing prohibited-school spells. The data
  is in place — every spell carries a validated `school` —
  but nothing models a prepared-spell list to check against.
  The +2 Spellcraft bonus is also absent: it applies only when
  learning specialty-school spells, and a flat +2 would be
  wrong.
- Alternative class features live in `engine/acfs.py` plus
  a per-book `acfs.yaml`, loaded into `Rules.acfs`. An
  entry carries `classes`, `levels`, `requires`,
  `replaces` and `grants`; a character selects them as
  `{name, level}` pairs, validated on load once class
  levels and race are known. `replaces: feature:` names a
  class feature key and may template the chosen level
  (`bonus_feat_wizard_{level}`), which works because every
  replaceable slot already has its own key in the class
  YAML — `bonus_feat_1..20` for fighters,
  `special_ability_2/3/4` for rogues. Suppressed features
  drop out of the sheet. Numeric forms
  (`spell_slots_per_level`, `prohibited_schools`,
  `specialty_slots_per_level`) cover what is not a class
  feature at all, which is what Focused Specialist needs.
  Racial substitution levels are the same shape with a
  `requires: race:` gate and need no separate subsystem;
  the predicate exists, the data does not yet.
  Proficiency and selection-style replacements (a ranger's
  favored enemy) appear in print but have no consumer, so
  they are absent rather than guessed.
- Feats granted by a class feature or a worn item are
  materialised by `feats.refresh_granted_feats()`: a
  `grants_feat:` key on a ClassFeature or
  MagicItemDefinition produces a derived feat, so a
  Swashbuckler's Weapon Finesse and the Two-Weapon Fighting
  from Gloves of the Balanced Hand satisfy prerequisites and
  reach per-weapon attack lines. Derived means recomputed on
  load and never written to the character file, so dropping
  the class or the item drops the feat. A grant may be
  conditional: Gloves of the Balanced Hand confer Two-Weapon
  Fighting, and Improved Two-Weapon Fighting as well when the
  wearer already had TWF of their own. The condition is judged
  against the feats held before that item granted anything, so
  the Gloves cannot bootstrap their own grant into the
  improved version.
- Splatbook YAML files beyond SRD core
- Per-weapon attack and damage lines live in
  `engine/weapons.py`. Each equipped weapon gets its own
  BonusPool and StatNode
  (`weapon_<i>_attack` / `weapon_<i>_damage`), registered by
  `register_weapons_on_character()` and rebuilt whenever the
  equipped set changes, so a Strength change cascades into
  every weapon line through the graph like any other stat.
  An attack line builds on the `attack_melee`/`attack_ranged`
  node; a damage line sums the `damage_str_bonus` node (melee
  only) with the damage pools, because damage has no single
  node of its own.
  Which feats reach a weapon is data: a `weapon_effects:`
  block declares `applies.match: name` (the selection names
  the weapon, as for Weapon Focus and Weapon Specialization
  and their Greater forms) or `applies.match: damage_type`,
  optionally constrained by `applies.ranged`. A feat with no
  such block never applies to a weapon. Melee and Ranged
  Weapon Mastery (PHB II) are the damage-type case: they
  reach every weapon of the chosen type on their own side
  of the melee/ranged divide. Ranged Weapon Mastery also
  extends the range increment, which is a weapon property
  rather than a bonus pool and so is resolved directly by
  `range_increment_bonus()`.
  A `weapon_effects` block may also declare
  `attack_ability:`, which substitutes an ability rather
  than adding a bonus: Weapon Finesse rolls Dexterity in
  place of Strength on a light weapon, rapier, whip or
  spiked chain (PHB p. 102), and only on attack rolls —
  damage keeps Strength. Because it is a swap rather than a
  bonus it cannot be a pool entry, so the weapon node takes
  the ability modifiers as graph inputs and exchanges them.
  Eligibility uses `WeaponDefinition.wield_class`
  (light / one_handed / two_handed / ranged, from the SRD
  weapons table); rapier, whip and spiked chain are not
  light, so the rule names them and the feat data lists
  them under `applies.also`.
  Critical threat ranges are resolved by
  `weapons.threat_range()`. Improved Critical (PHB p. 96)
  declares `doubles_threat_range` and the keen weapon
  property does the same; neither stacks with the other, so
  a range doubles at most once however many sources apply.
  Doubling widens the range and never touches the
  multiplier.
  Two-weapon fighting penalties follow PHB Table 8-10,
  keyed on whether the off-hand weapon is light (hence
  `wield_class`) and whether the character has the
  Two-Weapon Fighting feat. They apply only to weapons that
  declare `hand: primary` / `hand: off_hand`, because
  fighting with two weapons is a choice made per full attack
  rather than a property of carrying two. An off-hand weapon
  adds half Strength to damage. `off_hand` is spelled out
  because YAML reads a bare `off` as false.
  A character may declare more than one pairing and nothing
  records which weapon pairs with which, so a primary counts
  as light-handed only when every declared off-hand weapon
  is light.
  An off-hand weapon does not get the iterative sequence: it
  gets one extra attack, two with Improved Two-Weapon
  Fighting and three with Greater, each 5 lower than the last
  (PHB p. 160).
  Rapid Shot adds one ranged attack at the highest bonus and
  -2 on every ranged attack that round; the penalty sits on
  the weapon's line, and only the extra attack is added to
  the sequence.
  A weapon's `attack.total` is always the first entry of its
  `attack_iteratives`, and equals the sum of its breakdown.
  Anything that shapes the sequence therefore has to appear
  in the breakdown as well. The display name carries the
  stance the weapon is used in — "+5 Dagger (TWF: Primary)",
  "Longbow (Rapid Shot)", "+1 Greatsword (Power Attack: 5)" —
  since that is what explains the shape of the sequence.
  Weapon materials contribute through
  `MaterialDefinition.damage_adjust`, which only alchemical
  silver has (-1, DMG p. 285); its minimum-1-damage floor
  applies to a rolled total and is not modelled. Every other
  material bypasses damage reduction or changes hardness,
  neither of which moves a number here.
  Not yet routed per weapon: conditional weapon properties
  (bane, wounding, the augment crystals), which only apply
  against particular targets, and Power Attack.
- Template special qualities as mechanical effects: fly speed
  and spell resistance are still display-only text in
  `special_qualities`. Damage reduction, energy resistance and
  immunity now have a `defenses:` block and are wired for the
  half-outsiders and half-dragons.
- **Class features still describing numbers in prose** —
  72 features across 16 classes carry a number in their
  description but no structured `values`, so the sheet
  prints the sentence rather than the figure. Densest are
  Monk (9), Dragon Disciple (7), Arcane Archer (6) and
  Dwarven Defender (6). The mechanism is in place; these
  need the book checked and the formula written.
- **Monk unarmed damage and flurry** — the unarmed damage
  die and the flurry attack-bonus column of PHB Table 3-10
  are per-level tables rather than formulas, so they need
  the weapon-damage-table support noted below before they
  can become `values`.
- **Conditional effects sheet panel** — UI that
  surfaces effects which only apply under specific
  conditions (gate state, spell target alignment,
  creature type, one-shot activation). Two
  sub-sections: "currently applied" (gate on / buff
  active) and "not applied" (gate off / inactive).
  Gated passives whose gate is currently on still
  appear on the main stat sheet; everything appears
  in this panel regardless of state. Data sources:
  the gate system introduced alongside this panel,
  plus alignment-conditional spells (Magic Circle
  ×4, Protection from X ×4), one-shots (Smite Evil,
  Bless Weapon, Moment of Prescience), conditional
  feats (Dodge), ranger Favored Enemy tiers.
- **Attack-routine panel** — per-weapon attack
  breakdown hosting Flurry of Blows, Rapid Strike,
  Manyshot, Smite Evil, two-weapon fighting, and
  parameterized combat feats.
- **ResourceTracker wire-up** —
  `engine/resources.py` defines `ResourceTracker`
  but nothing consumes it yet. Needs to be attached
  to uses-per-day features (Rage, Turn Undead,
  Bardic Music, Wild Shape, Smite Evil, Stunning
  Fist). The Layer 14 description above overstates
  current functionality — correct when the wire-up
  lands.
- **Monk Stunning Fist** — L1 monk bonus feat (PHB).
  Activated attack with uses/day. Depends on the
  ResourceTracker wire-up and the attack-routine
  panel. The Monk's Belt's extra stunning attack per
  day *is* in the DMG entry (p. 248) — the earlier
  doubt here was unfounded — but it waits on the
  same uses tracking.
- **Gloves of the Balanced Hand** — grants
  TWF-like benefits. Gate semantics debatable (does
  it gate like TWF itself?) — rules decision needed
  before implementation.
- **Future derived pools** — the
  `derived_pools.yaml` mechanism landing alongside
  this work will also host:
  `effective_paladin_level_lay_on_hands` (paladin
  levels + hospitaler levels contribute per
  Complete Divine p.48; consumed by the
  healing-per-day formula) and
  `caster_level_<class>` pools (base casting class +
  PrCs that advance casting: Eldritch Knight skips
  only L1 per DMG p.187; Hospitaler skips L1/L5/L9
  per CDiv p.48; Mystic Theurge; etc.). When a
  character has multiple base casting classes and a
  PrC that could advance any of them, we'll need a
  per-level "which base caster does this level
  advance?" selector — not yet designed.
