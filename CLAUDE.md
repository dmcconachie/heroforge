# CLAUDE.md

All files have an 80 character limit; including this one.

ASCII only. No unicode anywhere: no em dashes (write `--`), no curly
quotes, no ellipsis character, no arrows, no box drawing. This covers
code, comments, YAML, documentation and commit messages, and it covers
this file.

Everytime a bug is found; a regression test should be added if practical. A
small bug is worth a small regression test. A big bug is worth a large
regression test.

When rules items are added they must be part of the persistance layer to count
as finished. I.e.; if you can't put it in the input YAML and see it in the
output YAML then you're not done.

## Project

HeroForge Anew -- a D&D 3.5e character engine in Python 3.12. The
front end is the `charsheet` CLI. The rules for D&D 3.5e can be
found at https://www.d20srd.org/

## Build & Run

- **Build a sheet:** `uv run charsheet <file>.char.yaml`
- **Run all python tests:** `uv run pytest`
- **Run specific tests:** 
  - `uv run pytest tests/test_foo.py`
  - `uv run pytest -k TestClassName`
- **Test (and fix) lint errors** (use all):
  - `uv run ruff format`
  - `uv run ruff check --fix`
  - `uv run yamllint .`

## Workflow

- **Test first, always.** Before implementing any feature, gate, bug fix
  or new behaviour, write the failing test and confirm it fails for the
  right reason, then write the minimum code that passes it. A multi-part
  change interleaves test-then-code per part; it does not batch the
  tests at the end. Skip TDD only where there is genuinely no testable
  contract, and say so when you do.
- **Verify every rules claim before writing it down.** Run the
  `/rules-lookup` skill before citing any D&D 3.5 item -- spell effect,
  feat prerequisite, class feature level, PrC progression table, item
  power. Memory has been wrong often enough to derail design work: the
  Cloak of Chaos, and the Eldritch Knight and Hospitaler caster level
  progressions, were all misremembered here. Do the lookups before
  writing a plan that rests on them, not after the mistakes surface.
  Something looked up earlier in the same conversation stays trusted,
  and a trivially canonical fact (a d20 rolls 1-20) needs no lookup --
  but anything with a table or a specific number does.
- **Use a task list for more than three steps.** Create it up front and
  update each item as it starts and finishes, rather than marking a
  batch complete at the end. A plan file does not replace it: the plan
  is the static reference, the task list is the live tracker.
- **Don't hack around an awkward decision -- raise it.** If the only way
  to make something work is code that compensates for an earlier
  modelling choice -- subtracting a value you just added, stripping a
  label that shouldn't be there, special-casing a type that should have
  been its own thing -- stop and ask what the right shape is. The skill
  ranks double-count is the example: ranks went into the UNTYPED bucket
  and `sheet.py` peeled them back out again, when they should never
  have gone in. Fix the root, or ask. Only write the compensation if
  the answer is to write it.
- **Commit straight to `main`.** No feature branch first. Run
  `./test_all.sh` green before committing, match the repo's message
  style (imperative subject, prose body wrapped near 66 characters,
  `--` for em dashes), and never push unless asked.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full directory layout, layer
descriptions, and design constraints. When work has been completed update
ARCHITECTURE.md

## Conventions

- All imports are at the top of the file. This includes test files, and it
  includes an import needed by exactly one new test -- `pytest`, `yaml`, `re`
  and the like are never deferred. The only import allowed in a function body
  is one that provably forms a circular import, and it carries a comment
  naming the cycle: today that is `get_rules` (engine <- rules),
  `rules.schema.converter` inside `persistence`, and `effects`/`gates` inside
  `equipment`. Anything else goes at the top.
- A new import that forms a cycle is a design finding, not a mechanics
  problem to route around. Trace the loop, name the edge that is the
  real smell -- usually a leaf type living in a heavy module, or engine
  code reaching up into loading code -- and raise it with a concrete
  fix (e.g. "move `Ability` to its own module") before going further.
  Demoting the import into a function body preserves the bad layering
  forever; take that path only when told to.
- Never use `sys.path` hacks. The project is properly configured via 
  `pyproject.toml`; `uv run` handles everything.
- Use `uv run pytest` to run tests -- do not set env vars like `QT_QPA_PLATFORM`
  on the command line.
- Closed sets of values are a `StrEnum`, never bare strings. When adding a
  field -- especially one loaded from YAML -- ask whether the value set is
  closed. If it is (a wield class, a stance, a body slot, an energy type, a
  size), define the enum beside the dataclass that owns it and type the field
  with it. cattrs then rejects a bad value at load time instead of letting a
  typo compare unequal forever. Bare `str` is for genuinely open text: names,
  notes, descriptions, formulas, source books.
