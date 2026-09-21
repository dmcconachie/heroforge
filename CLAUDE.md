# CLAUDE.md

All files have an 80 character limit; including this one.

Everytime a bug is found; a regression test should be added if practical. A
small bug is worth a small regression test. A big bug is worth a large
regression test.

When rules items are added they must be part of the persistance layer to count
as finished. I.e.; if you can't put it in the input YAML and see it in the
output YAML then you're not done.

## Project

HeroForge Anew — a D&D 3.5e character engine in Python 3.12. The
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

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full directory layout, layer
descriptions, and design constraints. When work has been completed update
ARCHITECTURE.md

## Conventions

- All imports are at the top of the file. This includes test files, and it
  includes an import needed by exactly one new test — `pytest`, `yaml`, `re`
  and the like are never deferred. The only import allowed in a function body
  is one that provably forms a circular import, and it carries a comment
  naming the cycle: today that is `get_rules` (engine <- rules),
  `rules.schema.converter` inside `persistence`, and `effects`/`gates` inside
  `equipment`. Anything else goes at the top.
- Never use `sys.path` hacks. The project is properly configured via 
  `pyproject.toml`; `uv run` handles everything.
- Use `uv run pytest` to run tests — do not set env vars like `QT_QPA_PLATFORM` 
  on the command line.
- Closed sets of values are a `StrEnum`, never bare strings. When adding a
  field — especially one loaded from YAML — ask whether the value set is
  closed. If it is (a wield class, a stance, a body slot, an energy type, a
  size), define the enum beside the dataclass that owns it and type the field
  with it. cattrs then rejects a bad value at load time instead of letting a
  typo compare unequal forever. Bare `str` is for genuinely open text: names,
  notes, descriptions, formulas, source books.
