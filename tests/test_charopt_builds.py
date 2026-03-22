"""
tests/test_charopt_builds.py
-----------------------------
End-to-end math verification using example character
builds checked against the d20 SRD progression tables.

Reference tables (d20srd.org):

Fighter (full BAB, good Fort):
  Lvl  BAB  Fort  Ref  Will
   8    8    6     2    2
  10   10    7     3    3

Rogue (medium BAB, good Ref):
  Lvl  BAB  Fort  Ref  Will
   2    1    0     3    0
   4    3    1     4    1
   8    6    2     6    2

Wizard (poor BAB, good Will):
  Lvl  BAB  Fort  Ref  Will
   4    2    1     1    4
  10    5    3     3    7

Cleric (medium BAB, good Fort+Will):
  Lvl  BAB  Fort  Ref  Will
   8    6    6     2    6

Barbarian (full BAB, good Fort):
  Lvl  BAB  Fort  Ref  Will
  10   10    7     3    3

Races (d20srd.org):
  Human:    no mods, Medium, 30ft
  Dwarf:    +2 CON -2 CHA, Medium, 20ft
  Elf:      +2 DEX -2 CON, Medium, 30ft
  Half-Orc: +2 STR -2 INT -2 CHA, Medium, 30ft
  Halfling: +2 DEX -2 STR, Small, 20ft
"""

from __future__ import annotations

from pathlib import Path

from heroforge.engine.character import Character
from heroforge.engine.classes_races import (
    apply_race,
    remove_race,
)
from heroforge.ui.app_state import AppState

RULES_DIR = Path(__file__).parent.parent / "src" / "heroforge" / "rules"


def make_state() -> AppState:
    s = AppState()
    s.load_rules()
    s.new_character()
    return s


def build_char(
    state: AppState,
    race: str,
    abilities: dict[str, int],
    class_levels: list[tuple[str, int]],
) -> Character:
    """
    Build a character with the given setup.

    class_levels: list of (class_name, num_levels)
    """
    c = state.character
    # Set abilities BEFORE race (race adds bonuses)
    for ab, val in abilities.items():
        c.set_ability_score(ab, val)
    # Apply race
    race_defn = state.race_registry.require(race)
    if c.race:
        old_defn = state.race_registry.get(c.race)
        if old_defn:
            remove_race(old_defn, c)
    apply_race(race_defn, c)
    # Add class levels one at a time
    for class_name, count in class_levels:
        defn = state.class_registry.require(class_name)
        for _ in range(count):
            c.add_level(class_name, defn.hit_die)
    return c


# ===================================================
# Build 1: Human Fighter 8
# Straightforward full BAB build
# ===================================================


class TestHumanFighter8:
    """
    Human Fighter 8: STR 16 DEX 14 CON 14
    INT 10 WIS 12 CHA 8.

    Expected (from SRD):
      BAB: 8
      Fort: 6 + CON mod(2) = 8
      Ref: 2 + DEX mod(2) = 4
      Will: 2 + WIS mod(1) = 3
      AC: 10 + DEX mod(2) = 12
      HP: 10*8 + CON mod(2)*8 = 96
      Attack melee: BAB(8) + STR mod(3) = 11
      Attack ranged: BAB(8) + DEX mod(2) = 10
      Initiative: DEX mod(2) = 2
      Speed: 30
    """

    def setup_method(self) -> None:
        self.state = make_state()
        self.c = build_char(
            self.state,
            race="Human",
            abilities={
                "str": 16,
                "dex": 14,
                "con": 14,
                "int": 10,
                "wis": 12,
                "cha": 8,
            },
            class_levels=[("Fighter", 8)],
        )

    def test_bab(self) -> None:
        assert self.c.bab == 8

    def test_fort(self) -> None:
        # Good Fort(8 levels) = 6, + CON mod 2
        assert self.c.fort == 8

    def test_ref(self) -> None:
        # Poor Ref(8 levels) = 2, + DEX mod 2
        assert self.c.ref == 4

    def test_will(self) -> None:
        # Poor Will(8 levels) = 2, + WIS mod 1
        assert self.c.will == 3

    def test_ac(self) -> None:
        # 10 + DEX mod 2 = 12
        assert self.c.ac == 12

    def test_hp(self) -> None:
        # 8 * d10(max=10) + 8 * CON mod(2) = 96
        assert self.c.hp_max == 96

    def test_attack_melee(self) -> None:
        # BAB 8 + STR mod 3 = 11
        assert self.c.get("attack_melee") == 11

    def test_attack_ranged(self) -> None:
        # BAB 8 + DEX mod 2 = 10
        assert self.c.get("attack_ranged") == 10

    def test_initiative(self) -> None:
        assert self.c.get("initiative") == 2

    def test_speed(self) -> None:
        assert self.c.get("speed") == 30

    def test_iteratives(self) -> None:
        # BAB 8 -> +11/+6
        iters = self.c.attack_iteratives(melee=True)
        assert iters == [11, 6]

    def test_total_level(self) -> None:
        assert self.c.total_level == 8

    def test_class_level_map(self) -> None:
        assert self.c.class_level_map == {"Fighter": 8}

    def test_toughness_adds_hp(self) -> None:
        base_hp = self.c.hp_max
        defn = self.state.feat_registry.require("Toughness")
        self.c.add_feat("Toughness", defn)
        assert self.c.hp_max == base_hp + 3

    def test_iron_will_adds_will(self) -> None:
        base_will = self.c.will
        defn = self.state.feat_registry.require("Iron Will")
        self.c.add_feat("Iron Will", defn)
        assert self.c.will == base_will + 2


# ===================================================
# Build 2: Elf Wizard 10
# Poor BAB, good Will, racial mods
# ===================================================


class TestElfWizard10:
    """
    Elf Wizard 10: STR 8 DEX 14(+2=16) CON 14(-2=12)
    INT 18 WIS 10 CHA 10.

    Base scores set: STR 8, DEX 14, CON 14, INT 18,
    WIS 10, CHA 10.  Elf adds +2 DEX, -2 CON.

    Expected (from SRD):
      BAB: 5  (poor, 10 levels)
      Fort: 3 + CON mod(1) = 4
      Ref: 3 + DEX mod(3) = 6
      Will: 7 + WIS mod(0) = 7
      AC: 10 + DEX mod(3) = 13
      HP: 4*10 + CON mod(1)*10 = 50
      Attack melee: BAB(5) + STR mod(-1) = 4
      Attack ranged: BAB(5) + DEX mod(3) = 8
      Initiative: DEX mod(3) = 3
      Speed: 30
    """

    def setup_method(self) -> None:
        self.state = make_state()
        self.c = build_char(
            self.state,
            race="Elf",
            abilities={
                "str": 8,
                "dex": 14,
                "con": 14,
                "int": 18,
                "wis": 10,
                "cha": 10,
            },
            class_levels=[("Wizard", 10)],
        )

    def test_ability_scores_with_racial(self) -> None:
        # DEX 14 + 2 racial = 16
        assert self.c.dex_score == 16
        # CON 14 - 2 racial = 12
        assert self.c.con_score == 12

    def test_bab(self) -> None:
        assert self.c.bab == 5

    def test_fort(self) -> None:
        # Poor Fort(10) = 3, + CON mod(1)
        assert self.c.fort == 4

    def test_ref(self) -> None:
        # Poor Ref(10) = 3, + DEX mod(3)
        assert self.c.ref == 6

    def test_will(self) -> None:
        # Good Will(10) = 7, + WIS mod(0)
        assert self.c.will == 7

    def test_ac(self) -> None:
        assert self.c.ac == 13

    def test_hp(self) -> None:
        # 10 * d4(4) + 10 * CON mod(1) = 50
        assert self.c.hp_max == 50

    def test_attack_melee(self) -> None:
        # BAB 5 + STR mod(-1) = 4
        assert self.c.get("attack_melee") == 4

    def test_attack_ranged(self) -> None:
        # BAB 5 + DEX mod(3) = 8
        assert self.c.get("attack_ranged") == 8

    def test_initiative(self) -> None:
        assert self.c.get("initiative") == 3

    def test_speed(self) -> None:
        assert self.c.get("speed") == 30

    def test_no_iteratives(self) -> None:
        # BAB 5 -> only one attack
        iters = self.c.attack_iteratives(melee=True)
        assert iters == [4]


# ===================================================
# Build 3: Dwarf Fighter 6 / Rogue 4
# Multiclass BAB stacking, mixed saves
# ===================================================


class TestDwarfFighter6Rogue4:
    """
    Dwarf Fighter 6 / Rogue 4:
    STR 14 DEX 14 CON 14(+2=16) INT 12 WIS 10
    CHA 10(-2=8).

    Expected (from SRD):
      Fighter 6: BAB 6, Fort 5, Ref 2, Will 2
      Rogue 4:   BAB 3, Fort 1, Ref 4, Will 1
      Total:     BAB 9, Fort 6, Ref 6, Will 3
      + ability mods:
        Fort 6 + CON mod(3) = 9
        Ref  6 + DEX mod(2) = 8
        Will 3 + WIS mod(0) = 3
      AC: 10 + DEX mod(2) = 12
      HP: 6*d10(10) + 4*d6(6) + 10*CON mod(3) = 114
      Attack melee: BAB(9) + STR mod(2) = 11
      Speed: 20 (dwarf)
    """

    def setup_method(self) -> None:
        self.state = make_state()
        self.c = build_char(
            self.state,
            race="Dwarf",
            abilities={
                "str": 14,
                "dex": 14,
                "con": 14,
                "int": 12,
                "wis": 10,
                "cha": 10,
            },
            class_levels=[
                ("Fighter", 6),
                ("Rogue", 4),
            ],
        )

    def test_ability_scores_with_racial(self) -> None:
        # CON 14 + 2 = 16
        assert self.c.con_score == 16
        # CHA 10 - 2 = 8
        assert self.c.cha_score == 8

    def test_bab(self) -> None:
        # Fighter 6 = 6, Rogue 4 = 3 → 9
        assert self.c.bab == 9

    def test_fort(self) -> None:
        # Fighter 6 Fort(good) = 5
        # Rogue 4 Fort(poor) = 1
        # Total 6 + CON mod(3) = 9
        assert self.c.fort == 9

    def test_ref(self) -> None:
        # Fighter 6 Ref(poor) = 2
        # Rogue 4 Ref(good) = 4
        # Total 6 + DEX mod(2) = 8
        assert self.c.ref == 8

    def test_will(self) -> None:
        # Fighter 6 Will(poor) = 2
        # Rogue 4 Will(poor) = 1
        # Total 3 + WIS mod(0) = 3
        assert self.c.will == 3

    def test_hp(self) -> None:
        # 6*10 + 4*6 + 10*3 = 60 + 24 + 30 = 114
        assert self.c.hp_max == 114

    def test_ac(self) -> None:
        assert self.c.ac == 12

    def test_attack_melee(self) -> None:
        # BAB 9 + STR mod 2 = 11
        assert self.c.get("attack_melee") == 11

    def test_speed(self) -> None:
        assert self.c.get("speed") == 20

    def test_total_level(self) -> None:
        assert self.c.total_level == 10

    def test_class_level_map(self) -> None:
        assert self.c.class_level_map == {
            "Fighter": 6,
            "Rogue": 4,
        }

    def test_iteratives(self) -> None:
        # BAB 9 → melee +11/+6
        iters = self.c.attack_iteratives(melee=True)
        assert iters == [11, 6]

    def test_no_xp_penalty(self) -> None:
        # Fighter 6 vs Rogue 4 = diff 2 > 1
        # BUT Human gets "any" favored class.
        # Dwarf favored class is Fighter.
        # So exclude Fighter → only Rogue 4.
        # Only one non-favored class → no penalty.
        assert not self.c.multiclass_xp_penalty()


# ===================================================
# Build 4: Half-Orc Barbarian 10
# Racial STR bonus, full BAB
# ===================================================


class TestHalfOrcBarbarian10:
    """
    Half-Orc Barbarian 10:
    STR 18(+2=20) DEX 12 CON 14 INT 10(-2=8)
    WIS 10 CHA 8(-2=6).

    Expected (from SRD):
      BAB: 10
      Fort: 7 + CON mod(2) = 9
      Ref: 3 + DEX mod(1) = 4
      Will: 3 + WIS mod(0) = 3
      AC: 10 + DEX mod(1) = 11
      HP: 12*10 + CON mod(2)*10 = 140
      Attack melee: BAB(10) + STR mod(5) = 15
      Attack ranged: BAB(10) + DEX mod(1) = 11
      Speed: 30 (Barbarian fast movement not modeled)
    """

    def setup_method(self) -> None:
        self.state = make_state()
        self.c = build_char(
            self.state,
            race="Half-Orc",
            abilities={
                "str": 18,
                "dex": 12,
                "con": 14,
                "int": 10,
                "wis": 10,
                "cha": 8,
            },
            class_levels=[("Barbarian", 10)],
        )

    def test_ability_scores_with_racial(self) -> None:
        assert self.c.str_score == 20  # 18 + 2
        assert self.c.int_score == 8  # 10 - 2
        assert self.c.cha_score == 6  # 8 - 2

    def test_bab(self) -> None:
        assert self.c.bab == 10

    def test_fort(self) -> None:
        assert self.c.fort == 9

    def test_ref(self) -> None:
        assert self.c.ref == 4

    def test_will(self) -> None:
        assert self.c.will == 3

    def test_hp(self) -> None:
        # 10*12 + 10*2 = 140
        assert self.c.hp_max == 140

    def test_ac(self) -> None:
        assert self.c.ac == 11

    def test_attack_melee(self) -> None:
        # BAB 10 + STR mod 5 = 15
        assert self.c.get("attack_melee") == 15

    def test_iteratives(self) -> None:
        # BAB 10 → +15/+10
        iters = self.c.attack_iteratives(melee=True)
        assert iters == [15, 10]


# ===================================================
# Build 5: Halfling Rogue 8
# Small size, racial DEX, good Ref
# ===================================================


class TestHalflingRogue8:
    """
    Halfling Rogue 8:
    STR 10(-2=8) DEX 16(+2=18) CON 12 INT 14
    WIS 10 CHA 10.

    Expected (from SRD):
      BAB: 6 (medium, 8 levels)
      Fort: 2 + CON mod(1) = 3
      Ref: 6 + DEX mod(4) = 10
      Will: 2 + WIS mod(0) = 2
      AC: 10 + DEX mod(4) + size(1) = 15
      HP: 6*8 + CON mod(1)*8 = 56
      Attack melee: BAB(6) + STR mod(-1) + size(1) = 6
      Attack ranged: BAB(6) + DEX mod(4) + size(1) = 11
      Speed: 20
    """

    def setup_method(self) -> None:
        self.state = make_state()
        self.c = build_char(
            self.state,
            race="Halfling",
            abilities={
                "str": 10,
                "dex": 16,
                "con": 12,
                "int": 14,
                "wis": 10,
                "cha": 10,
            },
            class_levels=[("Rogue", 8)],
        )

    def test_ability_scores_with_racial(self) -> None:
        assert self.c.str_score == 8  # 10 - 2
        assert self.c.dex_score == 18  # 16 + 2

    def test_bab(self) -> None:
        assert self.c.bab == 6

    def test_fort(self) -> None:
        assert self.c.fort == 3

    def test_ref(self) -> None:
        # Rogue 8 Ref(good) = 6, + DEX mod(4) = 10
        assert self.c.ref == 10

    def test_will(self) -> None:
        assert self.c.will == 2

    def test_ac(self) -> None:
        # 10 + DEX(4) + size(1) = 15
        assert self.c.ac == 15

    def test_hp(self) -> None:
        # 8*6 + 8*1 = 56
        assert self.c.hp_max == 56

    def test_attack_melee(self) -> None:
        # BAB(6) + STR(-1) + size(1) = 6
        assert self.c.get("attack_melee") == 6

    def test_attack_ranged(self) -> None:
        # BAB(6) + DEX(4) + size(1) = 11
        assert self.c.get("attack_ranged") == 11

    def test_speed(self) -> None:
        assert self.c.get("speed") == 20

    def test_iteratives(self) -> None:
        # BAB 6 → melee +6/+1
        iters = self.c.attack_iteratives(melee=True)
        assert iters == [6, 1]

    def test_size_is_small(self) -> None:
        assert self.c.size == "Small"


# ===================================================
# Build 6: Cleric 8 with buff math
# Medium BAB, good Fort+Will, spell buffs
# ===================================================


class TestCleric8WithBuffs:
    """
    Human Cleric 8: STR 14 DEX 10 CON 14
    INT 10 WIS 16 CHA 12.

    Expected (from SRD):
      BAB: 6
      Fort: 6 + CON mod(2) = 8
      Ref: 2 + DEX mod(0) = 2
      Will: 6 + WIS mod(3) = 9

    With Bless (morale +1 attack):
      Attack melee: BAB(6) + STR(2) + 1 = 9

    With Bull's Strength (+4 STR enhancement):
      STR mod: (14+4-10)/2 = 4
      Attack melee: BAB(6) + STR(4) = 10
    """

    def setup_method(self) -> None:
        self.state = make_state()
        self.c = build_char(
            self.state,
            race="Human",
            abilities={
                "str": 14,
                "dex": 10,
                "con": 14,
                "int": 10,
                "wis": 16,
                "cha": 12,
            },
            class_levels=[("Cleric", 8)],
        )

    def test_base_bab(self) -> None:
        assert self.c.bab == 6

    def test_base_fort(self) -> None:
        assert self.c.fort == 8

    def test_base_ref(self) -> None:
        assert self.c.ref == 2

    def test_base_will(self) -> None:
        assert self.c.will == 9

    def test_bless_attack_bonus(self) -> None:
        from heroforge.engine.effects import apply_buff

        base_atk = self.c.get("attack_melee")
        bless = self.state.spell_registry.require("Bless")
        apply_buff(bless, self.c, caster_level=8)
        # Bless: +1 morale to attack
        assert self.c.get("attack_melee") == base_atk + 1

    def test_bulls_strength_str_cascade(self) -> None:
        from heroforge.engine.effects import apply_buff

        bulls = self.state.spell_registry.require("Bull's Strength")
        apply_buff(bulls, self.c, caster_level=8)
        # +4 enhancement to STR → STR 18 → mod 4
        assert self.c.str_score == 18
        # Attack melee: BAB(6) + STR mod(4) = 10
        assert self.c.get("attack_melee") == 10


# ===================================================
# Build 7: Multiclass XP penalty check
# ===================================================


class TestMulticlassXPPenalty:
    """Test multiclass XP penalty detection."""

    def test_no_penalty_single_class(self) -> None:
        state = make_state()
        build_char(
            state,
            race="Human",
            abilities={
                "str": 10,
                "dex": 10,
                "con": 10,
                "int": 10,
                "wis": 10,
                "cha": 10,
            },
            class_levels=[("Fighter", 5)],
        )
        assert not state.character.multiclass_xp_penalty()

    def test_no_penalty_balanced(self) -> None:
        state = make_state()
        build_char(
            state,
            race="Human",
            abilities={
                "str": 10,
                "dex": 10,
                "con": 10,
                "int": 10,
                "wis": 10,
                "cha": 10,
            },
            class_levels=[
                ("Fighter", 5),
                ("Rogue", 4),
            ],
        )
        # Human: highest class is favored
        # Excluding Fighter(5), only Rogue(4)
        # Only one non-favored → no penalty
        assert not state.character.multiclass_xp_penalty()

    def test_penalty_when_unbalanced(self) -> None:
        state = make_state()
        build_char(
            state,
            race="Elf",
            abilities={
                "str": 10,
                "dex": 10,
                "con": 10,
                "int": 10,
                "wis": 10,
                "cha": 10,
            },
            class_levels=[
                ("Fighter", 6),
                ("Rogue", 2),
            ],
        )
        # Elf favored class is Wizard (not in build)
        # Fighter 6 vs Rogue 2 → diff 4 > 1
        assert state.character.multiclass_xp_penalty()


# ===================================================
# Build 8: Skill point budget verification
# ===================================================


class TestSkillPointBudgets:
    """Verify skill point calculations."""

    def test_fighter_skill_points_level_1(
        self,
    ) -> None:
        state = make_state()
        c = build_char(
            state,
            race="Human",
            abilities={
                "str": 14,
                "dex": 12,
                "con": 14,
                "int": 12,
                "wis": 10,
                "cha": 8,
            },
            class_levels=[("Fighter", 1)],
        )
        # Fighter: 2 skills/lvl + INT mod(1) + human(1)
        # Level 1: (2+1+1) * 4 = 16
        assert c.skill_points_for_level(1) == 16

    def test_rogue_skill_points_level_1(
        self,
    ) -> None:
        state = make_state()
        c = build_char(
            state,
            race="Human",
            abilities={
                "str": 10,
                "dex": 16,
                "con": 12,
                "int": 14,
                "wis": 10,
                "cha": 10,
            },
            class_levels=[("Rogue", 1)],
        )
        # Rogue: 8 skills/lvl + INT mod(2) + human(1)
        # Level 1: (8+2+1) * 4 = 44
        assert c.skill_points_for_level(1) == 44

    def test_wizard_skill_points_level_2(
        self,
    ) -> None:
        state = make_state()
        c = build_char(
            state,
            race="Elf",
            abilities={
                "str": 8,
                "dex": 14,
                "con": 14,
                "int": 18,
                "wis": 10,
                "cha": 10,
            },
            class_levels=[("Wizard", 2)],
        )
        # Wizard: 2 skills/lvl + INT mod(4)
        # Level 2: 2+4 = 6 (no x4, not human)
        assert c.skill_points_for_level(2) == 6
