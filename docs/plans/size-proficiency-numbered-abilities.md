# Size, proficiency, and numbered special abilities

Three related gaps, agreed as one program of work. Each step is
TDD: failing test first, then implementation, then the goldens.

## Step 0 — drufus golden (done)

Not a code regression. Commit `234e2af` moved the two-weapon
stance into the weapon's display name and deleted the
hand-written `TWF (...)` entries from `drufus.char.yaml` — but
deleted three of four, and regenerated the golden from the
half-edited input. Removed the stray `TWF (primary)` on the
first Dagger and regenerated. Suite green at 1446.

## Step 1 — Size as a real, changeable stat

Today `Character.size` is `_size_override or _race_size` with no
setter, so Enlarge Person applies only its ability deltas and
carries the note "size change handled separately".

- `engine/size.py`: `SIZE_ORDER`, `step_size()`, and PHB
  Table 7-4 (p. 114) damage stepping via `step_damage_dice()`.
- `BuffDefinition.size_steps: int` — Enlarge Person `+1`,
  Reduce Person `-1`, Righteous Might `+1`.
- Net step mirrors `bonus.aggregate()` semantics for a
  `size`-typed bonus: largest increase plus largest decrease,
  so two `+1` effects are one step and enlarge cancels reduce.
  The PHB states no general rule here; this is an engine
  decision, chosen for consistency with how the same spells'
  STR/DEX halves already aggregate.
- Cascade: AC, attack (melee/ranged), grapple, Hide, carrying
  capacity, and every weapon's damage dice.

Bugs to fix with regression tests:

- `sheet._identity()` reads size from the *race* definition, so
  a template that changes size never reaches the sheet.
- Enlarge/Reduce Person declare `enhancement` STR/DEX; PHB
  p. 226 says **size** bonus/penalty.
- The spells' "-1 on attack rolls and AC" must fall out of the
  size table, not be added a second time.

## Step 2 — Proficiency

- `proficiencies:` on `ClassDefinition` (armor categories,
  shields, tower shields, weapon categories, named weapons),
  plus race grants and the existing proficiency feats.
- Nonproficient armor/shield: that piece's armor check penalty
  applies to attack rolls and to every STR- and DEX-based
  ability and skill check; armor and shield stack (PHB p. 122).
- Nonproficient weapon: -4 on attack rolls with it.
- Surfaced per weapon and in the attack breakdown.

## Step 3 — Special abilities name their numbers

`Sheet.class_features` becomes a mapping keyed by feature key:
`{description, uses, values, when, gated_by}`. All goldens
regenerate.

`ClassFeature` gains `uses` (formula + unit) and `values`
(named formulas). Every class YAML in every book is covered.

Insightful Strike (Complete Warrior p. 12) is the worked case
for `when`: it applies the swashbuckler's INT bonus to damage
with Weapon Finesse-eligible weapons, but "targets immune to
sneak attacks or critical hits are immune", and it is lost in
medium/heavy armor or at medium/heavy load. The armor/load half
is a gate; the target half is not expressible as a
`Callable[[Character], bool]` and is recorded as `when` text
until the conditional-effects panel lands.

## Step 4 — ARCHITECTURE.md

Update as each step lands. Stale entries found during the
inventory and to be corrected regardless:

- Buff-registry reclassification is done; no item or tome
  entries remain in `KnownCoreBuff`.
- "Every spell in the compendium has an empty `school` field"
  is false; all 605 carry schools, validated on load.
- Layer 11's "Weapons are display-only (no stat wiring yet)"
  contradicts the per-weapon section below it.

## Status

Nothing is committed yet; all of the below is in the working
tree. Suite at 1547 passing, ruff and yamllint clean.

### Done

- **Step 0 — drufus golden.** Not a code regression: an
  incomplete fixture edit in `234e2af`.
- **Step 1 — size.** `engine/size.py`, `size_steps` on buffs,
  round-tripping through save/load and both UI paths,
  cascades into AC / attack / grapple / Hide / carrying
  capacity / weapon damage dice. `damage_dice_small` added
  for all 63 weapons from PHB Table 7-5, every Medium value
  cross-checked against the existing data.
- **Step 2 — proficiency.** `engine/proficiency.py`, blocks
  on all 17 base classes verified from PHB ch. 3 and DMG
  pp. 108-109, race grants split from weapon familiarity,
  nonproficiency penalties on attacks and the three skills
  the rule adds.
- **Step 3 — numbered abilities.** Mechanism complete;
  `Sheet.class_features` is a keyed mapping; 16 classes carry
  structured numbers; every `TODO: wire` marker in the class
  data is gone.
- **Step 4 — ARCHITECTURE.md** updated for each step, plus
  five stale entries corrected.

### Bugs found and fixed along the way

- Sheet read size off the *race*, so templates never reached
  it.
- `_compute_size_mod_hide()` had no production caller: Small
  races got no Hide bonus.
- Enlarge/Reduce Person used `enhancement` where PHB p. 226
  says **size**.
- Four class progressions drifted from their tables (paladin
  smite, barbarian rage, druid wild shape, monk slow fall).
- `evaluate_formula` built class variables with `.lower()`,
  so "Wild Mage" produced the unusable `wild mage_level`.
- Elf weapon list mangled by a YAML wrap; half-elf carried a
  copy of it the PHB does not grant.
- Nonproficiency applied the armor check penalty twice to
  skills that already carry one (Rules Compendium p. 14: it
  extends the list, it does not double).
- Ioun Stone (Pale Green Prism) was missing the skill half of
  its bonus; `skill_all` added as a target alias to express
  it.
- `_MULTI_TARGET_EXPANSIONS` was defined byte-identically in
  two modules; now defined once.

### Remaining

- **72 class features still state a number in prose** with no
  `values`, across 16 classes: Monk (9), Dragon Disciple (7),
  Arcane Archer (6), Dwarven Defender (6), then Swashbuckler,
  Arcane Trickster, Assassin, Barbarian, Blackguard and
  Duelist (5 each). The machinery needs no further change;
  each needs its book checked and a formula written.
- **The flurry attack-bonus column** of PHB Table 3-10 is
  still a per-level table with no consumer. Monk unarmed
  damage itself is done — see `weapons.monk_unarmed_damage()`
  and the `effective_monk_level_damage` pool.
- **The engine/rules import cycle** — see
  `engine-rules-import-cycle.md`. Deliberately deferred.
- **Ability checks** have no representation, so the Pale
  Green Prism's fourth clause is still unmodelled.
- **Conditional item properties.** Both SRD special-ability
  lists are defined in full; the permanent ones are wired.
  The activated, reactive and target-conditional ones carry
  no effects and want the conditional-effects panel.
- **Fortification's chance to negate a critical** is the last
  permanent property with nowhere to go. Energy resistance
  and damage reduction now have a home (`engine/defenses.py`).
- **Two defense sources are still unconnected**: creature
  templates keep theirs as display text in
  `special_qualities`, and a ring of energy resistance names
  its energy per item, which needs the parameter mechanism
  `Bane` uses.
  `Nimbleness` is defined without effects because its rules
  text could not be found in the MIC armour-property list —
  the only match is a body-slot item — and guessing seemed
  worse than recording the gap.
- **Unknown property names do nothing silently.** Validating
  them needs complete coverage across the books first.
