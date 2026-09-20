"""
engine/size.py
--------------
Creature size: the category ladder, stepping up and down it,
and the weapon damage that follows from it.

Size is not a bonus, so it cannot live in a BonusPool. It is a
category a creature occupies, which race sets, templates
override, and effects such as Enlarge Person move by whole
steps.

Weapon damage by size (PHB p. 114) is deliberately two
mechanisms, because the book is:

  * Small and Medium are printed per weapon in Table 7-5, and
    are not derivable from one another — a heavy crossbow goes
    1d8 -> 1d10 where a longsword goes 1d6 -> 1d8, but a
    greatsword goes 1d10 -> 2d6. So both are stored on the
    WeaponDefinition.
  * Tiny and Large are Table 7-4, keyed by the Medium value.
    They are not symmetric about Medium: Large is one category
    up, while Tiny is two categories down, because Small sits
    between Medium and Tiny. Tiny is therefore one step below
    *Small*, which `size_test.py` checks against the ladder for
    every weapon in the data.

Public API:
  SIZE_ORDER           -- Fine .. Colossal, ascending
  size_index()         -- position on that ladder
  step_size()          -- move a category by N steps, clamped
  net_size_steps()     -- aggregate competing size effects
  large_damage_dice()  -- Table 7-4's Large column
  tiny_damage_dice()   -- Table 7-4's Tiny column
  step_down_ladder()   -- one rung down the single-die ladder
  damage_dice_for_size() -- a weapon's damage at a given size
"""

from __future__ import annotations

from collections.abc import Iterable

from heroforge.engine.enums import Size

SIZE_ORDER: tuple[Size, ...] = (
    Size.FINE,
    Size.DIMINUTIVE,
    Size.TINY,
    Size.SMALL,
    Size.MEDIUM,
    Size.LARGE,
    Size.HUGE,
    Size.GARGANTUAN,
    Size.COLOSSAL,
)

# "No damage" — the net, and the result of shrinking a 1d2
# weapon, which Table 7-4 prints as an em dash.
NO_DAMAGE = "0"


def size_index(size: Size | str) -> int:
    """Position of *size* on SIZE_ORDER."""
    return SIZE_ORDER.index(Size(size))


def step_size(size: Size | str, steps: int) -> Size:
    """
    Move *size* by *steps* categories, clamped to the ladder.

    A creature cannot grow past Colossal or shrink past Fine.
    """
    idx = size_index(size) + steps
    idx = max(0, min(idx, len(SIZE_ORDER) - 1))
    return SIZE_ORDER[idx]


def net_size_steps(steps: Iterable[int]) -> int:
    """
    Combine competing size-changing effects into one step.

    Mirrors ``bonus.aggregate()`` for a size-typed bonus: the
    largest increase applies, the largest decrease applies, and
    the two sum. Two effects that each grow a creature one
    category therefore grow it one category, not two, and
    Enlarge Person cancels Reduce Person.

    The PHB states no general rule for stacking size changes.
    This is an engine decision, chosen so a size *category*
    behaves the way the same spells' size *bonuses* to STR and
    DEX already do.
    """
    values = list(steps)
    up = max((s for s in values if s > 0), default=0)
    down = min((s for s in values if s < 0), default=0)
    return up + down


# The single-die damage ladder. Every Small and Tiny value
# in the weapon tables sits on it, which is what makes "one
# size step" a meaningful operation down at that end.
DAMAGE_LADDER: tuple[str, ...] = (
    NO_DAMAGE,
    "1",
    "1d2",
    "1d3",
    "1d4",
    "1d6",
    "1d8",
    "1d10",
    "1d12",
)

# PHB Table 7-4, p. 114, keyed by the weapon's Medium damage.
#
# Note the two columns are not symmetric about Medium. Large
# is one size category up. Tiny is *two* categories down,
# because Small sits between Medium and Tiny and has its own
# printed column in Table 7-5 — so the Tiny value is one step
# below the Small one, not one step below the Medium one. A
# `steps`-style API would have to make -1 mean two categories,
# so the columns are exposed as named lookups instead.
_TABLE_7_4: dict[str, tuple[str, str]] = {
    # medium:   (large, tiny)
    "1d2": ("1d3", NO_DAMAGE),
    "1d3": ("1d4", "1"),
    "1d4": ("1d6", "1d2"),
    "1d6": ("1d8", "1d3"),
    "1d8": ("2d6", "1d4"),
    "1d10": ("2d8", "1d6"),
    "1d12": ("3d6", "1d8"),
    "2d4": ("2d6", "1d4"),
    "2d6": ("3d6", "1d8"),
    "2d8": ("3d8", "1d10"),
    "2d10": ("4d8", "2d6"),
}


def _column(medium: str, index: int) -> str:
    """One column of Table 7-4, keyed by the Medium value."""
    if medium in (NO_DAMAGE, ""):
        return medium
    return _TABLE_7_4[medium][index]


def large_damage_dice(medium: str) -> str:
    """
    A weapon's damage at Large — one category above Medium.
    """
    return _column(medium, 0)


def tiny_damage_dice(medium: str) -> str:
    """
    A weapon's damage at Tiny — one step below its *Small*
    value, which is two categories below Medium.
    """
    return _column(medium, 1)


def step_down_ladder(dice: str) -> str:
    """
    One rung down the single-die ladder.

    Only meaningful for the small end of the range, where
    every printed value is a single die (or a flat 1). Used to
    check that the two printed tables agree: Tiny should
    always be one rung below Small.
    """
    idx = DAMAGE_LADDER.index(dice)
    return DAMAGE_LADDER[max(0, idx - 1)]


def damage_dice_for_size(
    medium: str,
    small: str,
    size: Size | str,
) -> str:
    """
    A weapon's damage dice when wielded by a *size* creature.

    Small and Medium come straight off the weapon (Table 7-5);
    Large and Tiny are the two columns of Table 7-4. Sizes
    outside that range are not modelled — the PHB defers them
    to the DMG, which defers back to the PHB — so they raise
    rather than guess.
    """
    size = Size(size)
    if size is Size.MEDIUM:
        return medium
    if size is Size.SMALL:
        return small
    if size is Size.LARGE:
        return large_damage_dice(medium)
    if size is Size.TINY:
        return tiny_damage_dice(medium)
    raise ValueError(
        f"Weapon damage for a {size.value} wielder is not modelled "
        f"(PHB Tables 7-4 and 7-5 cover Tiny through Large)."
    )
