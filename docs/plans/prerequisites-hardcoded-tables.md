# `engine/prerequisites.py` duplicates the rules data

Found during the enum sweep, while typing
`AlignmentPrereq.allowed` and `CreatureTypePrereq.allowed`.
The file is the last place in the engine that answers rules
questions from tables written in Python instead of from the
YAML, and those tables have drifted away from the YAML
everywhere they overlap.

Most of it is latent: the module is reached only through
`proficient_with`, `can_cast`, `has_class_feature`,
`alignment`, `race` and `creature_type_is` prerequisites,
and the rules files use those sparingly. One part is not
latent. `spellcasting` prerequisites are dropped on the
floor, which leaves Hierophant and Mystic Theurge with no
entry requirements at all — see **D1** in
`docs/defects.md`.

## The shape of the problem

`CapabilityChecker` answers six questions, and answers all
six from literals:

- `is_proficient` — 4 frozensets, where `weapons.yaml`,
  `Proficiencies` and `RaceDefinition` already hold it.
- `can_cast` — 4 sets and a formula, where
  `ClassDefinition.spellcasting` already holds it.
- `has_class_feature` — 6 `if` branches, where
  `ClassDefinition.class_features` already holds it.
- `effective_creature_type` — `RACE_TYPES`, where
  `RaceDefinition.creature_type` already holds it.
- `effective_subtypes` — an inline race set, where
  `RaceDefinition.subtypes` already holds it.

`engine/proficiency.py` already implements the proficiency
question properly, against the registries. So the codebase
has two answers to "is this character proficient with a
longsword", and they disagree.

## The drift, measured

Every wrong answer this produces is recorded individually
in `docs/defects.md` as **D1**-**D12**: familiarity that
contradicts `races.yaml` and still carries the half-elf bug
fixed in the data (D4), familiarity treated as proficiency
(D5), weapon tables missing 13 martial and all 19 exotic
weapons and miscategorising Morningstar (D6), 25 classes
that grant no proficiency at all (D7), `can_cast` missing
real casters (D8), six hardcoded class features (D9), a
duplicated race-type table (D10), a condition that cancels
itself (D11), and — the one with teeth — `spellcasting`
prerequisites silently discarded, leaving Hierophant and
Mystic Theurge with no entry requirements whatsoever
(D1, D2).

The pattern behind all of them is the same: the answer is
computed from a Python literal when the registries already
hold it, and the literal was last correct at the moment it
was written.

## Options

1. **Delete `CapabilityChecker`'s tables and delegate.**
   `is_proficient` calls
   `proficiency.is_proficient_with_weapon`; the creature
   type and subtype methods read `RaceDefinition`;
   `can_cast` reads `ClassDefinition.spellcasting`;
   `has_class_feature` reads `class_features`. Needs
   `get_rules`, which this module can already reach.
   Removes every table above.

2. **Keep the tables, add a test that they match the
   registries.** Cheaper, and would have caught all of the
   drift above, but keeps two sources of truth.

3. **Leave it and cap the blast radius** by making
   `build_prereq_from_yaml` raise on unknown keys, so at
   least nothing silently becomes unconditional.

**Recommendation: option 1**, with option 3 folded in. The
data these tables want already exists and is tested; the
only thing the tables add is a second answer. Option 2
keeps a copy of the rules alive for no benefit.

## Not to be forgotten

`effective_subtypes` has a condition that reads

```python
if race in {..., "Half-Elf", "Half-Orc", ...} and race not in {
    "Half-Elf", "Half-Orc"
}:
```

The two halves cancel, so the two races can never be
reached. Whatever it meant, it does not mean it now.
