"""
ui/sheets/sheet1_summary.py
---------------------------
Sheet 1: The primary character summary.

Layout (three-column):
  Left:   Character info (name, race, class, alignment, etc.)
          Ability scores block
  Center: Combat stats (AC, saves, BAB, HP, initiative, speed)
          Attack bonuses
  Right:  Buffs panel
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from heroforge.ui.widgets.ability_block import AbilityBlock
from heroforge.ui.widgets.buff_panel import BuffPanel
from heroforge.ui.widgets.combat_stats import CombatStats
from heroforge.ui.widgets.common import HRule, LabeledField, SectionHeader

if TYPE_CHECKING:
    from heroforge.engine.character import Character
    from heroforge.ui.app_state import AppState


class Sheet1Summary(QWidget):
    """
    The main summary sheet tab.
    Wired to an AppState so it can read/write the active character.
    """

    def __init__(
        self, app_state: "AppState", parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._state = app_state
        self._building = True  # suppress feedback loops during init

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(10)

        # ── Left column ──────────────────────────────────────────────────
        left = QVBoxLayout()
        left.setSpacing(6)

        # Character identity fields
        identity_box = QGroupBox("Character")
        id_layout = QVBoxLayout(identity_box)
        id_layout.setSpacing(3)

        self._name_field = LabeledField("Name", label_width=70)
        self._player_field = LabeledField("Player", label_width=70)
        self._race_field = LabeledField("Race", label_width=70, read_only=True)
        self._class_field = LabeledField(
            "Class", label_width=70, read_only=True
        )
        self._align_field = LabeledField("Alignment", label_width=70)
        self._deity_field = LabeledField("Deity", label_width=70)
        self._level_field = LabeledField(
            "Level", label_width=70, read_only=True
        )

        for f in (
            self._name_field,
            self._player_field,
            self._race_field,
            self._class_field,
            self._align_field,
            self._deity_field,
            self._level_field,
        ):
            id_layout.addWidget(f)

        self._name_field.text_changed.connect(self._on_name_changed)
        self._align_field.text_changed.connect(self._on_alignment_changed)
        self._deity_field.text_changed.connect(self._on_deity_changed)

        left.addWidget(identity_box)

        # Ability scores
        self._abilities = AbilityBlock()
        self._abilities.ability_changed.connect(self._on_ability_changed)
        left.addWidget(self._abilities)
        left.addStretch()

        # ── Center column ────────────────────────────────────────────────
        center = QVBoxLayout()
        center.setSpacing(6)

        self._combat = CombatStats()
        center.addWidget(self._combat)

        # Attack summary
        atk_box = QGroupBox("Attacks")
        atk_layout = QVBoxLayout(atk_box)

        self._melee_field = LabeledField(
            "Melee", read_only=True, label_width=60
        )
        self._ranged_field = LabeledField(
            "Ranged", read_only=True, label_width=60
        )
        self._damage_field = LabeledField(
            "Dmg Bonus", read_only=True, label_width=60
        )

        atk_layout.addWidget(self._melee_field)
        atk_layout.addWidget(self._ranged_field)
        atk_layout.addWidget(self._damage_field)
        center.addWidget(atk_box)

        # Warnings / validation
        self._warnings = QLabel("")
        self._warnings.setWordWrap(True)
        self._warnings.setStyleSheet("color: #b71c1c; font-size: 11px;")
        center.addWidget(self._warnings)
        center.addStretch()

        # ── Right column — Buffs ─────────────────────────────────────────
        right = QVBoxLayout()
        right.setSpacing(4)
        right.addWidget(SectionHeader("Active Buffs"))
        right.addWidget(HRule())

        self._buff_panel = BuffPanel(
            app_state.buff_registry,
            app_state.character,
        )
        self._buff_panel.buffs_changed.connect(self._on_buffs_changed)
        right.addWidget(self._buff_panel, stretch=1)

        # ── Assemble ─────────────────────────────────────────────────────
        main_layout.addLayout(left, stretch=2)
        main_layout.addLayout(center, stretch=2)
        main_layout.addLayout(right, stretch=2)

        self._building = False
        self.refresh()

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Reload all displayed values from the character."""
        if self._building:
            return
        c = self._state.character

        # Identity
        self._name_field.value = c.name
        self._race_field.value = c.race
        self._class_field.value = _class_summary(c)
        self._align_field.value = c.alignment
        self._deity_field.value = c.deity
        self._level_field.value = str(c.total_level)

        # Abilities
        scores = {
            ab: c.get_ability_score(ab)
            for ab in ("str", "dex", "con", "int", "wis", "cha")
        }
        self._abilities.set_all_scores(scores)

        # Combat
        self._combat.refresh(c)

        # Attacks (with iteratives)
        iters = c.attack_iteratives(melee=True)
        self._melee_field.value = "/".join(_signed(a) for a in iters)
        iters_r = c.attack_iteratives(melee=False)
        self._ranged_field.value = "/".join(_signed(a) for a in iters_r)
        self._damage_field.value = _signed(c.get("damage_str_bonus"))

        # Warnings
        warnings = c.validate()
        chk = self._state.prereq_checker
        if chk is not None:
            for prc, _details in chk.ongoing_violations(c):
                warnings.append(f"{prc}: ongoing prereq unmet")
        self._warnings.setText("\n".join(warnings) if warnings else "")

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_name_changed(self, text: str) -> None:
        if not self._building:
            self._state.character.name = text
            # Notify so main window title updates
            self._state.character.on_change.notify({"identity:name"})

    def _on_alignment_changed(self, text: str) -> None:
        if not self._building:
            self._state.character.alignment = text

    def _on_deity_changed(self, text: str) -> None:
        if not self._building:
            self._state.character.deity = text

    def _on_ability_changed(self, ability: str, score: int) -> None:
        if not self._building:
            self._state.character.set_ability_score(ability, score)
            self._combat.refresh(self._state.character)
            self._melee_field.value = _signed(
                self._state.character.get("attack_melee")
            )
            self._ranged_field.value = _signed(
                self._state.character.get("attack_ranged")
            )
            self._damage_field.value = _signed(
                self._state.character.get("damage_str_bonus")
            )

    def _on_buffs_changed(self) -> None:
        if not self._building:
            self._combat.refresh(self._state.character)
            self._melee_field.value = _signed(
                self._state.character.get("attack_melee")
            )
            self._ranged_field.value = _signed(
                self._state.character.get("attack_ranged")
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _class_summary(character: Character) -> str:
    clm = character.class_level_map
    if not clm:
        return "—"
    return " / ".join(f"{cn} {lvl}" for cn, lvl in clm.items())


def _signed(value: int) -> str:
    return f"+{value}" if value >= 0 else str(value)
