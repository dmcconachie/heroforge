# Spellcasting: parked work

Parked deliberately. Nothing here is a bug in what exists — it
is work not yet started. Recorded so picking it up later is
cheap.

## Already in place (what unblocks the rest)

- Every spell carries `school`, `subschool` and `descriptor`
  (605/605), validated on load. This was the blocker for most
  of the items below.
- Domain spells are cross-checked against the compendium at
  dataset load, so a bad name fails loudly.
- The domain spell slot and the specialist's specialty slot are
  each modelled as their own restricted track, separate from
  the general allotment.
- `Specialization` (school + prohibited schools) is character
  state, validated against PHB p. 57 on load, and Focused
  Specialist works through the ACF mechanism.

## Parked items

1. **Prohibited-school enforcement.** A specialist cannot
   prepare or cast spells from a prohibited school. The data to
   check now exists (`SpellEntry.school` against
   `Specialization.prohibited`) but nothing enforces it, because
   nothing models a prepared-spell list for prepared casters.

2. **Restricted slots are not checked against what fills
   them.** A domain slot must be filled from one of the
   cleric's two domains; a specialty slot from the specialist's
   school. Both slots exist and are counted; what may go in
   them is unchecked, for the same reason as above.

3. **Domain spells are not added to the prepared-spell list.**
   The sheet lists each domain's nine spells under `domains:`,
   which is a reference table, not an allotment.

4. **The six +1-caster-level domains.** Chaos, Evil, Good, Law,
   Healing and Knowledge each raise caster level for a subset
   of spells — by descriptor for the alignment domains, by
   school for Knowledge's divinations. `SpellEntry.descriptor`
   now carries what is needed, but `SpellcastingEntry` has a
   single flat `caster_level` that cannot express "11th, but
   12th for good spells". This needs per-spell or per-category
   caster level before the domains can land.

5. **The specialist's +2 Spellcraft bonus.** Applies only when
   learning a spell of the specialty school (PHB p. 57), so a
   flat +2 on Spellcraft would be wrong. Needs conditional
   skill bonuses keyed on what is being attempted.

6. **Spell selection and spell sheets generally.** Choosing
   prepared spells, spellbooks, spells known for spontaneous
   casters beyond the current count, and the sheet layout for
   any of it.

## Related, parked elsewhere

Deity/domain validation — a cleric may currently take domains
their deity does not offer. Deferred to a general validation
pass rather than done piecemeal; the deity roster already
carries each deity's domain list.
