# Removing the PyQt6 UI

The desktop UI was deleted on 2026-09-21 to leave a clean
slate for a future front end. `charsheet` is the front end
now: a CLI that reads a `.char.yaml` and emits the computed
sheet as YAML.

19 modules under `src/heroforge/ui/` went, along with the
`app` script entry, the `pyqt6` dependency, the pytest
`xdist_group` marker and `--dist=loadgroup` (which existed
only to keep the Qt smoke test on one worker), and the
pyright `exclude` that had been carrying the UI's errors.

## What the UI was holding that wasn't UI

Three things had to move or die first. Each was a layering
violation `ARCHITECTURE.md` already claimed did not exist.

### `AppState` was the session, not the GUI

`ui/app_state.py` imported no Qt. It owned the active
`Character`, wired skills and derived-pool consumers onto
it, and exposed ~14 properties forwarding to `get_rules()`.
Nine non-UI test files used it.

With no app there is no app state, so it went. Its parts
had clean homes already:

- the registry properties were shims its own docstring
  called "a migration aid ... new code should call
  `get_rules()` directly" — call sites now do
- `load_rules()` was a no-op in tests, because the autouse
  fixture in the root `conftest.py` already installs a
  cached `Rules` around every test
- `new_character()` was `Character()` plus
  `register_skills_on_character` and `install_consumers`.
  `load_character` already does both, so only tests that
  build a character by hand need it; each such test file
  has a small local `new_character()`, matching the
  repo's per-file helper convention
- `skill_total()` was a one-line wrapper over
  `compute_skill_total`

This completes `rules-container-refactor.md`, whose last
step was deleting those shims.

### `export/` computed AC from a widget, and got it wrong

`export/sheet_data.py` imported `_compute_touch` and
`_compute_flatfooted` from `ui/widgets/combat_stats.py` at
runtime. `Character.touch_ac()` and `.flatfooted_ac()`
already existed and `engine/sheet.py` used them, so the
widget held a second implementation — and the two
disagreed:

- the widget's flat-footed AC ignored Uncanny Dodge. A
  5th-level barbarian with Dex 14 rendered 12 on the sheet
  and 10 in the PDF. DMG p. 195: "She retains her Dexterity
  bonus to AC (if any) regardless of being caught
  flat-footed."
- the widget's touch AC hardcoded `{DODGE, UNTYPED}` as the
  stacking types where the engine uses `ALWAYS_STACKING`,
  which also contains `RACIAL`.

Deleting the duplicate fixed the export. A regression test
pins the sheet and the PDF to the same numbers.

### `engine/sheet.py` imported `AppState` to load rules

`main()` built an `AppState` solely to call `load_rules()`.
That is `get_rules()`, which the module already defers-
imports elsewhere for the engine ← rules cycle.

## Left behind deliberately

`templates.py` still documents partially-applicable
templates and `TemplateDefinition` still lacks the
`partially_applicable` and `max_level` fields the deleted
`sheet_race.py` read. Nothing in the engine needs them; a
rebuilt front end that wants a level spinner for templates
will need the dataclass and `build_template_from_yaml`
finished first.
