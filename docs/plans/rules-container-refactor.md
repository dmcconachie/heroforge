# Rules() container + get_rules() refactor

## Context / why

Today, `Character` reaches outward to three separately-attached
registry references (`_class_registry_ref`, `_feat_registry_ref`,
`_skill_registry`) to answer questions like "what's my BAB?",
"does this template grant a feat?", "what's the synergy bonus for
Tumble?". These refs are:

- Not declared consistently. Two (`_class_registry_ref`,
  `_feat_registry_ref`) are declared in `Character.__init__`
  (`src/heroforge/engine/character.py:256-257`); `_skill_registry`
  is injected dynamically by `register_skills_on_character`
  (`src/heroforge/engine/skills.py:216`).
- Wired from two places. `AppState._wire_character`
  (`src/heroforge/ui/app_state.py:230-241`) sets them when the UI
  flow creates or replaces a character. `persistence.py:426-427`
  sets them again when loading from YAML outside the UI. Two
  independent wiring paths means one can drift from the other.
- Used with `getattr(..., None)` fallbacks everywhere — implying
  Character can function without them, which is a lie. The
  fallbacks (e.g. `_cached_class_levels` in `_compute_bab` at
  character.py:627) are load-bearing only for edge tests.

The refactor collapses all rule-defining registries into one
container, exposes it via a lazy module-level `get_rules()` with
`set_rules` / `reset_rules` overrides for tests, and reduces the
three per-character refs to (at most) one.

## Current state — inventory

### All registries currently on AppState

From `ui/app_state.py:78-94`:

- `buff_registry: BuffRegistry`
- `condition_registry: ConditionRegistry`
- `magic_item_registry: MagicItemRegistry`
- `spell_compendium: SpellCompendium`
- `feat_registry: FeatRegistry`
- `armor_registry: ArmorRegistry`
- `weapon_registry: WeaponRegistry`
- `material_registry: MaterialRegistry`
- `domain_registry: DomainRegistry`
- `skill_registry: SkillRegistry`
- `template_registry: TemplateRegistry`
- `derived_pools: dict`
- `class_registry: ClassRegistry`
- `race_registry: RaceRegistry`
- `prereq_checker: PrerequisiteChecker` (set in `load_rules`, line 204)

All of these are rule-definition artifacts, loaded once from YAML
at startup, read-only thereafter. They all belong in `Rules`.

### What stays on AppState

- `character: Character` — mutable per-session state.
- `new_character()`, `set_character()` — character lifecycle.
- `_wire_character()` — becomes a one-liner (`character._rules =
  get_rules()`) or goes away entirely if Character doesn't hold
  a ref.

### Character's registry-touching methods

All in `src/heroforge/engine/character.py`:

- `_compute_bab` (line 617): reads `_class_registry_ref`
- `_compute_base_save` (line 630): reads `_class_registry_ref`
- `has_class_feature` (line 895): reads `_class_registry_ref`
- `_compute_max_dex_bonus` — check around line 644 (armour item
  lookup, may need material_registry)
- `_compute_flatfooted_ac` (around line 978): reads
  `_class_registry_ref`
- `_compute_touch_ac` / AC helpers (around line 1068): reads
  `_class_registry_ref`
- Effects-wiring pass (line 1601): reads `_class_registry_ref`
- `skill_points_at_level` (line 1708): reads `_class_registry_ref`
- `int_mod_at_level` — uses bumps + inherent, probably no registry

### Other reads of the registry refs

- `templates.py:273` — reads `_feat_registry_ref`
- `templates.py:353` — reads `_feat_registry_ref`
- `skills.py:235` — reads `_skill_registry` in `set_skill_ranks`
- `skills.py:366` — reads `_skill_registry` in
  `recompute_skills_from_levels` (will be deleted by the
  ranks-fix plan)
- `skills.py:418` — reads `_skill_registry` in
  `compute_skill_total`
- `persistence.py:487` — calls `set_skill_ranks(c, ...)` during
  load

## Proposed design

### The Rules class

Location: new module `src/heroforge/rules/rules.py` (or
`src/heroforge/engine/rules.py` — decide based on layering in
ARCHITECTURE.md).

```python
from dataclasses import dataclass, field

@dataclass
class Rules:
    buffs: BuffRegistry = field(default_factory=BuffRegistry)
    conditions: ConditionRegistry = field(
        default_factory=ConditionRegistry)
    magic_items: MagicItemRegistry = field(
        default_factory=MagicItemRegistry)
    spells: SpellCompendium = field(
        default_factory=SpellCompendium)
    feats: FeatRegistry = field(default_factory=FeatRegistry)
    armor: ArmorRegistry = field(default_factory=ArmorRegistry)
    weapons: WeaponRegistry = field(default_factory=WeaponRegistry)
    materials: MaterialRegistry = field(
        default_factory=MaterialRegistry)
    domains: DomainRegistry = field(default_factory=DomainRegistry)
    skills: SkillRegistry = field(default_factory=SkillRegistry)
    templates: TemplateRegistry = field(
        default_factory=TemplateRegistry)
    classes: ClassRegistry = field(default_factory=ClassRegistry)
    races: RaceRegistry = field(default_factory=RaceRegistry)
    prereq_checker: PrerequisiteChecker = field(
        default_factory=PrerequisiteChecker)
    derived_pools: dict = field(default_factory=dict)

    def load(self, rules_dir: Path | None = None) -> None:
        """Populate from YAML. Same logic currently in
        AppState.load_rules."""
        ...
```

Naming: shorten the registry attribute names (e.g. `buffs` not
`buff_registry`) since the class name provides the namespace.

### The module-level accessor

Same module:

```python
_rules: Rules | None = None

def get_rules() -> Rules:
    """Return the process-wide Rules, lazily loading on first
    call."""
    global _rules
    if _rules is None:
        r = Rules()
        r.load()
        _rules = r
    return _rules

def set_rules(rules: Rules) -> None:
    """Override the singleton. For tests and alternate
    rulesets."""
    global _rules
    _rules = rules

def reset_rules() -> None:
    """Forget the current singleton. Next get_rules()
    rebuilds."""
    global _rules
    _rules = None
```

### Character's relationship to Rules

**Recommended**: Character does NOT hold a `_rules` ref. Each
method that needs rules calls `get_rules()` directly.

Rationale: eliminates all wiring code. The `_wire_character` and
the `persistence.py:426-427` block both disappear. Tests that
need a custom ruleset override via `set_rules()` — Character
methods pick it up automatically.

Cost: methods that touch rules gain a `from
heroforge.rules.rules import get_rules` import and a `rules =
get_rules()` line. That's a good trade.

**Alternative if the above feels too implicit**: Character holds
`self._rules: Rules` set once in `__init__` (default
`get_rules()`) with an optional constructor arg for test
injection. Then methods use `self._rules` instead of calling
`get_rules()` every time. Slightly better ergonomics, slightly
more state. Pick one during implementation.

### Test isolation

Add a pytest fixture in `tests/conftest.py`:

```python
@pytest.fixture(autouse=True)
def _isolated_rules():
    reset_rules()
    yield
    reset_rules()
```

This resets the singleton before and after every test so no test
can poison the next via mutation. Tests that want a specific
ruleset build one and call `set_rules(r)`.

## Migration steps

1. **Create `Rules` + `get_rules`/`set_rules`/`reset_rules`.**
   Port `AppState.load_rules`'s loader sequence into
   `Rules.load`. `Rules.load` should be callable with no args
   (use default `RULES_DIR`) and should be idempotent.

2. **Add the pytest fixture** in `tests/conftest.py` that resets
   the singleton around every test.

3. **Update AppState**:
   - Remove all 15 registry attrs from `__init__`.
   - Replace `load_rules` with a call to `get_rules()` (just
     triggers the lazy load).
   - Add property shims that forward to the singleton during the
     migration: `self.class_registry` → `get_rules().classes`,
     etc. Delete the shims once all call sites are converted.

4. **Update Character**:
   - Remove `_class_registry_ref` and `_feat_registry_ref` from
     `__init__` (character.py:256-257).
   - Convert all 7 read sites in character.py to call
     `get_rules()`.
   - Remove the `_cached_class_levels` fallback paths — once the
     registry is always available, the fallback is dead code.

5. **Update templates.py**:
   - Replace `_feat_registry_ref` reads at lines 273 and 353
     with `get_rules().feats`.

6. **Update skills.py**:
   - Remove the `character._skill_registry = skill_registry`
     stash at line 216.
   - Drop the `skill_registry` parameter from
     `register_skills_on_character` — it now pulls from
     `get_rules().skills` internally.
   - Update `set_skill_ranks`, `compute_skill_total` (and any
     survivors after the ranks-fix plan) to call
     `get_rules().skills` instead of reading off the character.

7. **Update persistence.py**:
   - Delete lines 426-427 (the registry ref wiring).
   - Anywhere it reads `app_state.feat_registry` /
     `app_state.skill_registry` / `app_state.buff_registry`,
     switch to `get_rules()`. If persistence doesn't need
     `app_state` anymore as a parameter, drop the parameter.

8. **Update app_state._wire_character**:
   - Collapse to just the `derived_pools` install and the
     `register_skills_on_character(character)` call. The three
     registry assignments at lines 233-235 disappear.

9. **Search-and-verify**:
   - `grep -r
     "_class_registry_ref\|_feat_registry_ref\|_skill_registry"`
     across the whole repo. Every hit should be gone except
     maybe comments or tests that we delete.
   - `grep -r "app_state\." | grep -i "registry"` — find
     anything still reaching for a registry through AppState and
     convert.

10. **Delete the property shims** on AppState from step 3.

## Test strategy

- **Existing tests should all pass.** No behaviour changes, only
  plumbing. The golden YAMLs are the strongest regression signal.
- **New unit tests** for `Rules` / `get_rules`:
  - `get_rules()` returns the same object on repeated calls
    (singleton).
  - `set_rules(r)` swaps; `get_rules()` returns `r`.
  - `reset_rules()` forces rebuild on next `get_rules()`.
  - Lazy: importing the module does NOT trigger load.
- **Test the conftest fixture works**: a test that mutates the
  rules (e.g. registers a fake feat) is isolated from the next
  test.

## Open questions to confirm before starting

1. **Module placement**: `heroforge.rules.rules` vs
   `heroforge.engine.rules` vs elsewhere? ARCHITECTURE.md should
   drive this.
2. **Character holds `_rules` or calls `get_rules()` per-use?**
   My recommendation: per-use (fewer moving parts). Confirm.
3. **AppState's lifetime**: does AppState even need to exist as
   a separate object after this? It becomes just `character +
   character lifecycle methods + convenience shims`. Maybe
   folding the character-management bits elsewhere and deleting
   AppState is a follow-up worth considering — but separate
   from this refactor.
4. **Thread safety**: PyQt is single-threaded main + Qt workers.
   Skip the lock for now. If ever needed, wrap `get_rules()`'s
   lazy-init in `threading.Lock`.
5. **What about
   `heroforge.engine.equipment.set_material_registry(...)`**
   at `app_state.py:190`? There's already a module-level
   registry pattern in equipment.py. This refactor should fold
   that into the `Rules` container and delete the module-global
   — no more than one singleton pattern per codebase.

## Key file:line reference table

For quick resumption in a clean context:

`src/heroforge/ui/app_state.py`
- 78-94: all 15 registries declared
- 100-214: `load_rules` (port this logic into `Rules.load`)
- 230-241: `_wire_character` (collapse)

`src/heroforge/engine/character.py`
- 256-257: `_class_registry_ref`, `_feat_registry_ref` (delete)
- 617-628: `_compute_bab` — registry read
- 630-642: `_compute_base_save` — registry read
- 895-907: `has_class_feature` — registry read
- 978: AC helper — registry read
- 1068: AC helper — registry read
- 1601: effects-wiring — registry read
- 1708-1722: `skill_points_at_level` — registry read

`src/heroforge/engine/templates.py`
- 273, 353: `_feat_registry_ref` reads

`src/heroforge/engine/skills.py`
- 216: `_skill_registry` stash (delete)
- 235, 366, 418: `_skill_registry` reads

`src/heroforge/engine/persistence.py`
- 426-427: wiring (delete)

`src/heroforge/engine/equipment.py`
- `set_material_registry` — existing singleton to consolidate

## Preconditions

- This refactor should be done AFTER the skill-ranks fix commit
  (see `sprightly-wandering-neumann.md` or the ranks fix in
  git history). The ranks fix deletes
  `recompute_skills_from_levels`, which reduces the number of
  `_skill_registry` read sites by one.
- No other in-flight refactors touching Character.
