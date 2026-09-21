# Known defects

Open defects, newest first within each area. A defect is
something the code gets *wrong*, as distinct from something
it does not do yet; design cleanups live in `docs/plans/`.

Each entry names how it was found and what it costs, so the
severity can be judged without re-deriving it. When one is
fixed, add the regression test and delete the entry.

---

## `engine/prerequisites.py`

Design discussion and the proposed cleanup:
`docs/plans/prerequisites-hardcoded-tables.md`. These are
the concrete wrong answers that cleanup would remove.

### D1 — `spellcasting` prerequisites are silently dropped

`build_prereq_from_yaml` handles `can_cast` but not
`spellcasting`. Eleven declarations across the prestige
classes use `spellcasting`, and every one of them is
discarded:

```python
>>> build_prereq_from_yaml(
...     {"spellcasting": {"cast_type": "arcane", "min_level": 7}})
None
```

Two classes have *only* `spellcasting` prerequisites, so
their entry requirements collapse to nothing and any
character may enter them at once:

- **Hierophant** — should need 7th-level divine spells.
- **Mystic Theurge** — should need 2nd-level arcane *and*
  2nd-level divine.

Loremaster, Archmage and Wild Mage keep their other
prerequisites but lose the casting requirement.

Two spellings of one prerequisite are in use, and they
differ inside as well as out:

| Key | Inner keys | Where | Handled |
|---|---|---|---|
| `can_cast` | `spell_level`, `type` | `core/feats.yaml`, 8x | yes |
| `spellcasting` | `min_level`, `cast_type` | `*/classes/*.yaml`, 11x | no |

Pick one canonical form, migrate the data, and make the
other a load error.

### D2 — unknown prerequisite keys are skipped silently

The last line of `build_prereq_from_yaml` is `# Unknown key
— skip silently`, returning `None`. A misspelled key does
not fail the load; it produces a target with *no*
prerequisites, permanently available. D1 is this defect
firing for real. The rules files are our own data, not a
system boundary, so this should raise.

### D4 — racial weapon familiarity contradicts `races.yaml`

`CapabilityChecker._RACIAL_MARTIAL` disagrees with the
rules data on five of its seven rows:

- **Half-Elf** carries the elf weapon list. This is the bug
  that was found and fixed in `races.yaml` — a line wrap
  had granted half-elves a list the PHB does not give them.
  The fix never reached this copy.
- **Halfling** has Sling and Halfling Skiprock; the data
  has none.
- **Orc** appears here but is not a race in `races.yaml`.
- **Half-Orc** has Orc Double Axe; the data has none.
- **Elf** lists six weapons as *familiarity*; the data has
  the same six as `weapon_proficiencies`, which grants them
  outright rather than reclassifying them.

Gnome and Dwarf agree.

### D5 — familiarity is treated as proficiency

`is_proficient` returns `True` from racial familiarity
alone. Familiarity only reclassifies an exotic weapon as
martial — the character still needs martial proficiency to
use it. A dwarf wizard is not proficient with a dwarven
waraxe, but this says they are.

### D6 — the weapon category tables are wrong and partial

`weapons.yaml` holds all 68 SRD weapons with a `category`.
`_SIMPLE_WEAPONS` and `_MARTIAL_WEAPONS` hold 10 and 21.

- 13 of the 30 martial weapons are absent.
- All 19 exotic weapons are absent; there is no exotic set,
  so exotic proficiency rests on feat name alone.
- `Morningstar` is listed as martial. `weapons.yaml`, built
  from the SRD table, has it as simple.
- `Shortsword`, `Longbow, Composite` and `Shortbow,
  Composite` are not the canonical names (`Short Sword`,
  `Composite Longbow`, `Composite Shortbow`), so those
  three entries can never match a weapon.

### D7 — 25 classes grant no weapon proficiency

`_MARTIAL_CLASSES` and `_SIMPLE_CLASSES` name 17 classes.
Twenty-five loaded classes are in neither — among them
Swashbuckler, Duelist, Assassin, Blackguard, Dwarven
Defender, Occult Slayer and every NPC class. A pure
Swashbuckler is therefore not proficient with a rapier.

Six classes named in those sets do not exist in the data at
all: Crusader, Swordsage, Warblade, Psion, Psychic Warrior,
Wilder.

### D8 — `can_cast` misses real casters and invents others

It names 18 caster classes, of which seven exist in the
data. `Adept` and `Blackguard` carry spellcasting data and
appear in none of its sets, so neither can satisfy a
casting prerequisite. Progression is computed as
`(level + 1) // 2` rather than read from the class's own
table.

### D9 — `has_class_feature` hardcodes six features

Sneak attack is Rogue-only ("Also Assassin, Ninja, etc. —
simplified here"), rage is `Barbarian >= 1`, wild shape is
`Druid >= 5`. The class features are in the data with their
real progressions; these branches are a second, coarser
copy.

### D10 — `RACE_TYPES` duplicates `races.yaml`

`effective_creature_type` reads a Python table rather than
`RaceDefinition.creature_type`. It covers the seven core
races redundantly and adds seven the rules files do not
define.

### D11 — `effective_subtypes` has a condition that cancels

```python
if race in {..., "Half-Elf", "Half-Orc", ...} and race not in {
    "Half-Elf", "Half-Orc"
}:
```

The two halves cancel, so those two races can never take
the branch. Whatever was intended, this is not it.
