# Skill points: cross-class cost, rank caps, and banking

Parked work item. Nothing here is implemented yet.

## Context / why

The engine does not model cross-class skills at all. Ranks are
stored per level in `CharacterLevel.skill_ranks` and summed raw:
one stored point becomes one rank, whatever the skill's status.
`ARCHITECTURE.md` already admits this ("Class-skill vs cross-class
is not modelled"), but the consequences are wider than that line
suggests, and they make the existing validator untrustworthy.

## What is missing

1. **Cross-class cost.** A cross-class rank costs 2 skill points,
   so 1 point buys half a rank. `validate_skill_allocation`
   (`src/heroforge/engine/skills.py:295`) computes
   `spent = sum(skill_ranks.values())`, charging 1 point per rank
   regardless. Cross-class spending is therefore under-counted.

2. **Half ranks.** Cross-class max ranks is `(level + 3) / 2`,
   which is frequently a half number, and a character may legally
   sit on a half rank. `max_skill_ranks`
   (`src/heroforge/engine/skills.py:282`) returns the float, but
   `skill_ranks` is typed `dict[KnownSkill, int]`, so a half rank
   cannot be stored.

3. **Banking unspent points across levels.** Wanted behaviour:
   points left over at one level carry forward and can be spent
   later. This is what makes half ranks tractable — 1 point into a
   cross-class skill now, 1 point next level to complete the rank.
   Nothing models a carried balance today; each level is validated
   against its own budget in isolation.

4. **Class-skill status is per class, not per character.** Whether
   a skill is a class skill depends on the class taken *at that
   level*, so cost and cap both change mid-build. Elbirg is the
   worked example: Use Magic Device is cross-class for Wizard
   1-5, then a class skill from Wild Mage 6-8
   (`src/heroforge/rules/complete_arcane/classes/wild_mage.yaml`).
   His 9 ranks at level 8 are legal for that reason; the *cost* of
   the two ranks bought at levels 3 and 5 is not what the engine
   charged. `validate_skill_allocation` resolves class skills from
   a single class definition and misses this.

5. **Nothing calls the validator.** `validate_skill_allocation`
   has no production callers — not the loader, not the UI. Only
   `compute_skill_budget` is exercised, and only from
   `tests/test_skill_allocation.py`. Bad fixture data loads
   silently.

## Related: class-skill status is derived in four places

Any fix touches all of these, which read
`ClassDefinition.class_skills` independently:

- `src/heroforge/engine/skills.py:326`
- `src/heroforge/export/sheet_data.py:261`
- `src/heroforge/ui/sheets/sheet2_skills.py:160`
- `src/heroforge/ui/sheets/sheet_class.py:196`

Worth consolidating before adding per-character inputs (domain
granted class skills need the same hook — see the domains work).

## Fixtures currently flagged

Running `validate_skill_allocation` over every integration fixture
flags four, all custom characters; every `base_characters` and PrC
fixture is clean:

| Fixture   | Worst reported violation |
|-----------|--------------------------|
| `barzay`  | L1: spent 36 of 20       |
| `farzin`  | L1: spent 28 of 24       |
| `drufus`  | L17: spent 16 of 11      |
| `elbirg`  | L3: spent 8 of 7         |

**Treat these as suspect, not as verdicts.** The validator has the
gaps above, so a flagged fixture may be bad data, a validator bug,
or both. Reconcile one by hand before trusting the list.

Unresolved on Elbirg specifically: at level 3 the file spends 8
points and the validator computes a budget of 7 (Wizard 2 +
INT mod 4 at base INT 18, +1 human). Expectation on the day was
5 ranks, which neither number matches — worth re-deriving from
the character sheet before acting.

## Not doing today

The YAML representer folds any string over 50 characters to `>-`
(`src/heroforge/engine/persistence.py:202`), which is why
hand-quoted strings in `.expected.yaml` files get reverted on
regeneration. Known, deliberately unaddressed.
