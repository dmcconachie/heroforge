# CLAUDE.md

All files have an 80 character limit; including this one.

Everytime a bug is found; a regression test should be added if practical. A
small bug is worth a small regression test. A big bug is worth a large
regression test.

When rules items are added they must be part of the persistance layer to count
as finished. I.e.; if you can't put it in the input YAML and see it in the
output YAML then you're not done.

## Project

HeroForge Anew — a D&D 3.5e character sheet application built with PyQt6 and 
Python 3.12. The rules for D&D 3.5e can be found at https://www.d20srd.org/

## Build & Run

- **Run the app:** `uv run app`
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

- All imports are at the top of the file unless there are very specific and
  local reasons for doing otherwise.
- Never use `sys.path` hacks. The project is properly configured via 
  `pyproject.toml`; `uv run` handles everything.
- Use `uv run pytest` to run tests — do not set env vars like `QT_QPA_PLATFORM` 
  on the command line.
