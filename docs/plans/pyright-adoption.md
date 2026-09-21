# Adopting pyright

`pyright` was added to the dev group and wired into
`test_all.sh`, with no configuration. On defaults it reports
**880 errors** across 169 files.

The errors are not 880 problems. They are six root causes,
and three of them are design questions the type checker
merely made visible.

## Configuration

There was none — no `pyrightconfig.json`, no
`[tool.pyright]`. The defaults happened to discover the
right 169 files (`.venv` and `__pycache__` fall out of the
dot-prefix and name excludes) and resolved the interpreter
through `uv run`, but nothing was pinned: `pythonVersion`
came from the live interpreter rather than
`requires-python`, the include set was "anything not
dot-prefixed", and `typeCheckingMode` was implicitly
`standard`.

Pinned in `pyproject.toml` beside the pytest config:

```toml
[tool.pyright]
include = ["src", "tests", "conftest.py"]
exclude = ["src/heroforge/ui"]
pythonVersion = "3.12"
typeCheckingMode = "standard"
venvPath = "."
venv = ".venv"
```

`ui/` is excluded because the PyQt6 layer is slated for
removal; the 13 errors left there were all one bug (below)
in code about to be deleted.

Measured: basic 878, standard 880, strict 3805. Standard
now; raising `src/heroforge` to strict is left for later —
the extra 2925 are dominated by `Unknown` leaking out of
`yaml.safe_load` and cattrs structure calls, which is its
own piece of work.

## The six root causes

| # | Cause | Errors |
|---|---|---|
| B | Bare `"str"` where a StrEnum param is declared | 325 |
| C | `None` passed to the unused `app_state` param | 151 |
| D | Optional member access | 109 |
| A | `PoolKey` built by `combine()` at import time | 102 |
| E | Undeclared attributes assigned from outside | 24 |
| F | Genuine one-offs | ~170 |

### A — `PoolKey` is not a type

`rules/core/pool_keys.py` ends with

```python
PoolKey = combine("PoolKey", _StatPoolKey, _SkillPoolKey)
```

so pyright sees a *variable* of type `type[StrEnum]`, not a
class. Every `PoolKey.STR_SCORE` is an unknown attribute and
every `list[PoolKey]` is "Variable not allowed in type
expression".

The file is already auto-generated, and generated code has
no reason to be dynamic. `_gen_pool_keys.py` now emits one
literal `class PoolKey(StrEnum)` with every member spelled
out, skill pools included.

`rules/known.py` keeps `combine()`. Its per-book
auto-discovery is the point of the module, and its enums are
used as constructors (`KnownSkill(name)`), not as member
accesses. The handful of `dict[KnownSkill, ...]` annotation
sites are handled individually.

### C — `app_state` is dead

`gather_sheet`, `load_character` and `extract_sheet` all
take `app_state`, all carry `# noqa: ARG001 # kept for API
compat`, and none reads it. 151 errors are callers passing
`None` to satisfy it.

`export.gather` carried the same dead parameter and the
same marker; it went too, which also removed `export/`'s
`AppState` import.

Deleted from every signature and all ~240 call sites. The
`noqa`s go with them.

### E — undeclared attributes, and a bug behind them

`_size_override`, `_race_size` and `_race_type` are never
set in `__init__`. They are assigned from `races.py` and
from tests, and read back through
`getattr(self, name, default)`.

Declaring them surfaced a name mismatch:

- `races.py:173` writes `character._race_creature_type`
- `effects.py:510` reads `char._race_type`

Nothing writes `_race_type`. The `humanoid_only` condition
therefore always sees its `"Humanoid"` default and is
unconditionally true, so *Enlarge Person* and *Reduce
Person* apply to any creature — verified against a Lich,
whose `effective_creature_type` is `Undead`. PHB p. 226
gives *Enlarge Person* "Target: One humanoid creature".

`_race_creature_type` was meanwhile write-only: declared
`str = "Humanoid"`, written by `races.py`, read by nothing.

Fix: `Character.creature_type` resolves override → race
type → `None`, `effects.py` consults it, and the phantom
`_race_type` goes away. `effective_creature_type` and its
hardcoded `RACE_TYPES` table are left alone — that is
**D10**, already parked in
`prerequisites-hardcoded-tables.md`.

Attributes are declared with their enums, and where no
correct value exists at construction the type says so
rather than inventing one:

```python
self._size_override: Size | None = None
self._race_size: Size | None = None
self._race_creature_type: CreatureType | None = None
self._creature_type_override: CreatureType | None = None
```

The documented "Medium until race is loaded" fallback stays
at the read site in `_base_size`, where it is visible.

### D3 and D12

Two pyright clusters land exactly on logged defects.
**D3** (the prereq builder does not coerce to `Alignment` /
`CreatureType`) and **D12** (`register_feat` stores `None`
in a `dict[str, Prerequisite]`) are both small, and both
defect entries already say the annotation is simply wrong.
Fixed here with regression tests; the entries are deleted
from `docs/defects.md`.

The rest of `prerequisites.py` is untouched.

## Order of work

Each step ends green before the next begins.

1. Pin `[tool.pyright]` → baseline still 880.
2. Static `PoolKey` from the generator → ~95 cleared,
   `uv run check-pool-keys` clean.
3. Delete `app_state` → 151 cleared.
4. Declare `Character` attributes, add `creature_type`,
   fix `humanoid_only` → 24 cleared + regression test for
   the Lich.
5. Bare strings → enum members in tests → 325 cleared.
6. Optional member access → 109 cleared.
7. D3, D12 + regression tests → ~25 cleared, entries
   deleted.
8. One-offs → remainder cleared.
9. `./test_all.sh` green; update `ARCHITECTURE.md`.

## Result

880 → **0**, with 1842 tests green and ruff/yamllint clean.
Eight new regression tests: six for the `humanoid_only`
bug, two for D3/D12.

## What this turned up

Type errors that were really defects, each fixed with a
test:

- **`humanoid_only` never said no.** `effects.py` read
  `_race_type`; `races.py` writes `_race_creature_type`.
  Enlarge and Reduce Person applied to a Lich.
- **Two classes had unmeetable alignment prerequisites.**
  `wild_mage.yaml` and `hospitaler.yaml` spelled alignments
  `Chaotic Good` where `Alignment` is `chaotic_good`. D3's
  coercion turned that into a load error, and
  `rules_test.py` now checks every alignment in the data.
- **A UI crash.** `sheet_race.py` reads
  `partially_applicable` and `max_level`, which
  `TemplateDefinition` has never had, so selecting any
  template raised `AttributeError`. Left alone: the UI is
  being removed.

## Still open

`ARCHITECTURE.md` says `engine/` and `export/` have zero
imports from `ui/`. Both do:

- `engine/sheet.py:95` imports `AppState`, used only in
  `main()` to force the rules load — `get_rules()` does the
  same thing.
- `export/sheet_data.py:29` imports `_compute_flatfooted`
  and `_compute_touch` from `ui/widgets/combat_stats.py`,
  at runtime. Two private UI helpers the PDF export needs.

Both break when the UI is purged, and the `charsheet`
entry point goes with them.
