# The engine ↔ rules import cycle

Found while hoisting function-local imports to module scope
per the project convention. Written down rather than papered
over, because the inline imports are a symptom.

## The cycle

```
heroforge.rules.rules
    → heroforge.engine.classes        (ClassRegistry)
        → heroforge.engine.proficiency
            → heroforge.rules.rules   ← closes the loop
```

Reproduce by hoisting `get_rules` to the top of
`engine/proficiency.py` and running `python -c "import
heroforge.rules.rules"`:

```
ImportError: cannot import name 'get_rules' from partially
initialized module 'heroforge.rules.rules' (most likely due
to a circular import)
```

`engine.proficiency` is only the most recent participant.
`rules/rules.py` imports ten `engine` modules at module
scope (`acfs`, `classes`, `conditions`, `deities`, `domains`,
`effects`, `equipment`, `feats`, `magic_items`,
`prerequisites`, `races`, `skills`, `spells`, `templates`),
and any of those reaching back for `get_rules()` closes a
loop.

## Why it exists

The rules-container refactor (see
`rules-container-refactor.md`, now landed) deliberately chose
"each method that needs rules calls `get_rules()` directly"
over threading a `Rules` reference through `Character`. That
was the right call for wiring, but it inverted the layering:

- `engine/` is meant to be the lower layer — pure Python,
  no knowledge of where rule data comes from.
- `rules/` is the upper layer that reads YAML and builds
  registries out of `engine/` dataclasses.
- But `engine/` now *calls up* into `rules/` for
  `get_rules()`, while `rules/` still imports `engine/`
  downward for the types.

The deferred import is what keeps that working: by the time
any function body runs, both modules are fully initialised.

Ten engine modules currently do this, 27 call sites in all:

| module          | deferred `get_rules` imports |
|-----------------|------------------------------|
| `weapons.py`    | 6 |
| `sheet.py`      | 5 |
| `skills.py`     | 5 |
| `proficiency.py`| 3 |
| `persistence.py`| 2 |
| `templates.py`  | 2 |
| `acfs.py`       | 1 |
| `domains.py`    | 1 |
| `equipment.py`  | 1 |
| `feats.py`      | 1 |

## Options

1. **Move the accessor down.** Put `get_rules`/`set_rules`/
   `reset_rules` in a leaf module that imports nothing from
   `engine/` or `rules/` — e.g. `heroforge/registry.py`
   holding only the singleton slot. `rules/rules.py` would
   populate it; `engine/` would read it. The cycle
   disappears and all 27 imports hoist to module scope.
   Cheapest fix; keeps the current call style.

2. **Inject instead of reaching.** Pass `Rules` into the
   functions that need it. Honest layering, no singleton, but
   it is exactly the threading the earlier refactor removed,
   and it touches every signature.

3. **Split the types out of `engine/`.** A `heroforge/model/`
   layer holding the pure dataclasses, with `engine/` for
   behaviour and `rules/` for loading. Biggest change,
   clearest result.

**Recommendation: option 1.** It is a file move plus an
import rewrite, needs no signature changes, and turns a
convention violation enforced by 27 scattered comments into
a rule the linter can check.

## Done meanwhile

`Proficiencies` moved from `engine/proficiency.py` to
`engine/classes.py`, so `ClassDefinition` no longer has to
import the module that resolves proficiency against the
whole registry. That removes the newest edge; the underlying
inversion stands.

## Audit, 2026-09-20

A sweep hoisted every function-scope import the project could
take: **293 down to 48**. Each survivor was tested on its
own, and every one is genuinely cycle-bound.

- **30x `rules.rules.get_rules`.** `rules.rules` imports all
  18 engine registries at module level, so no engine module
  can name the accessor at the top of the file.
- **15x `rules.schema.converter`.** Two loops:
  `loader -> schema -> known -> rules -> loader`, and
  `persistence -> schema -> persistence`.
- **1x `engine.effects` and 1x `engine.gates`**, both in
  `equipment`: `equipment -> gates -> equipment`.
- **1x `engine.derived_pools`** in `effects`:
  `effects -> derived_pools -> effects`.

Everything else now imports at the top, including all 21
test files. The three non-`get_rules` groups each carry a
comment naming their cycle.

The `get_rules` group is what option 1 fixes: moving the
accessor into a leaf module clears 30 of the 48 in one
change.
