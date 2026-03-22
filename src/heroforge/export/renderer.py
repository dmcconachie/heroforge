"""
heroforge/export/renderer.py
-----------------------------
Renders a SheetData into a PDF character sheet using ReportLab.

Layout — two pages:
  Page 1: Identity block, ability scores, combat stats, saving throws,
           attack summary, active buffs.
  Page 2: Full skills table, feats list, templates/DM notes.

Design choices:
  - Letter size (8.5" × 11"), 0.5" margins.
  - Helvetica throughout — universally available, no font files to bundle.
  - Thin grid lines on tables; muted blue section headers.
  - Signed values ("+3" / "-1") for modifiers, bonuses, and totals.
  - Class-skill marker "●" in skills table.

Public API:
  render_pdf(sheet_data, path)   — write PDF to path
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

if TYPE_CHECKING:
    from reportlab.pdfgen.canvas import Canvas

    from heroforge.export.sheet_data import SheetData

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------

_HEADER_BG = colors.HexColor("#3949AB")  # indigo
_HEADER_FG = colors.white
_SUBHEAD_BG = colors.HexColor("#E8EAF6")  # light indigo
_GRID = colors.HexColor("#BDBDBD")
_POSITIVE = colors.HexColor("#1B5E20")
_NEGATIVE = colors.HexColor("#B71C1C")
_NEUTRAL = colors.HexColor("#424242")
_CS_BLUE = colors.HexColor("#1565C0")
_LIGHT_GREY = colors.HexColor("#F5F5F5")


# ---------------------------------------------------------------------------
# Dimensions
# ---------------------------------------------------------------------------

PAGE_W, PAGE_H = letter
MARGIN = 0.5 * inch
CONTENT_W = PAGE_W - 2 * MARGIN


# ---------------------------------------------------------------------------
# Style helpers
# ---------------------------------------------------------------------------


def _styles() -> dict[str, ParagraphStyle]:
    ss = getSampleStyleSheet()
    base = ss["Normal"]

    return {
        "h1": ParagraphStyle(
            "h1",
            parent=base,
            fontSize=16,
            leading=20,
            textColor=_HEADER_BG,
            fontName="Helvetica-Bold",
            alignment=TA_CENTER,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base,
            fontSize=9,
            leading=11,
            textColor=_HEADER_FG,
            fontName="Helvetica-Bold",
            alignment=TA_LEFT,
        ),
        "label": ParagraphStyle(
            "label",
            parent=base,
            fontSize=7,
            leading=9,
            textColor=colors.HexColor("#555555"),
            fontName="Helvetica",
        ),
        "value": ParagraphStyle(
            "value",
            parent=base,
            fontSize=9,
            leading=11,
            textColor=_NEUTRAL,
            fontName="Helvetica",
        ),
        "value_bold": ParagraphStyle(
            "value_bold",
            parent=base,
            fontSize=9,
            leading=11,
            textColor=_NEUTRAL,
            fontName="Helvetica-Bold",
        ),
        "big": ParagraphStyle(
            "big",
            parent=base,
            fontSize=13,
            leading=15,
            textColor=_NEUTRAL,
            fontName="Helvetica-Bold",
            alignment=TA_CENTER,
        ),
        "centered": ParagraphStyle(
            "centered",
            parent=base,
            fontSize=9,
            leading=11,
            textColor=_NEUTRAL,
            fontName="Helvetica",
            alignment=TA_CENTER,
        ),
        "small": ParagraphStyle(
            "small",
            parent=base,
            fontSize=7.5,
            leading=9,
            textColor=_NEUTRAL,
            fontName="Helvetica",
        ),
        "small_italic": ParagraphStyle(
            "small_italic",
            parent=base,
            fontSize=7.5,
            leading=9,
            textColor=colors.HexColor("#666666"),
            fontName="Helvetica-Oblique",
        ),
        "note": ParagraphStyle(
            "note",
            parent=base,
            fontSize=7,
            leading=9,
            textColor=colors.HexColor("#666666"),
            fontName="Helvetica-Oblique",
        ),
    }


# ---------------------------------------------------------------------------
# Signed value helper
# ---------------------------------------------------------------------------


def _signed(v: int) -> str:
    return f"+{v}" if v >= 0 else str(v)


def _signed_para(v: int, style: ParagraphStyle) -> Paragraph:
    color = _POSITIVE if v > 0 else (_NEGATIVE if v < 0 else _NEUTRAL)
    text = _signed(v)
    return Paragraph(f'<font color="{color.hexval()}">{text}</font>', style)


# ---------------------------------------------------------------------------
# Section header row (full-width coloured bar)
# ---------------------------------------------------------------------------


def _section_header(title: str, st: dict) -> Table:
    t = Table(
        [[Paragraph(title, st["h2"])]],
        colWidths=[CONTENT_W],
    )
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _HEADER_BG),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return t


# ---------------------------------------------------------------------------
# Identity block (two-column table of labeled fields)
# ---------------------------------------------------------------------------


def _identity_block(d: SheetData, st: dict) -> list:
    items = []
    items.append(_section_header("CHARACTER IDENTITY", st))

    rows = [
        [
            Paragraph("Character Name", st["label"]),
            Paragraph(d.identity.name or "—", st["value_bold"]),
            Paragraph("Player", st["label"]),
            Paragraph(d.identity.player or "—", st["value"]),
        ],
        [
            Paragraph("Race", st["label"]),
            Paragraph(d.identity.race or "—", st["value"]),
            Paragraph("Alignment", st["label"]),
            Paragraph(d.identity.alignment or "—", st["value"]),
        ],
        [
            Paragraph("Class / Level", st["label"]),
            Paragraph(d.identity.class_str, st["value"]),
            Paragraph("Deity", st["label"]),
            Paragraph(d.identity.deity or "—", st["value"]),
        ],
        [
            Paragraph("Total Level", st["label"]),
            Paragraph(str(d.identity.level), st["value"]),
            Paragraph("Size", st["label"]),
            Paragraph(d.identity.size, st["value"]),
        ],
    ]

    col_w = CONTENT_W / 4
    t = Table(
        rows, colWidths=[col_w * 0.6, col_w * 1.4, col_w * 0.6, col_w * 1.4]
    )
    t.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, _GRID),
                ("BACKGROUND", (0, 0), (-1, -1), _LIGHT_GREY),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    items.append(t)
    return items


# ---------------------------------------------------------------------------
# Ability scores block
# ---------------------------------------------------------------------------


def _ability_block(d: SheetData, st: dict) -> Table:
    header = [
        Paragraph("ABILITY", st["h2"]),
        Paragraph("SCORE", st["h2"]),
        Paragraph("MOD", st["h2"]),
    ]
    rows = [header]
    for ab in d.abilities:
        rows.append(
            [
                Paragraph(ab.name, st["value_bold"]),
                Paragraph(str(ab.score), st["centered"]),
                _signed_para(ab.mod, st["centered"]),
            ]
        )

    col_w = CONTENT_W * 0.22
    t = Table(rows, colWidths=[col_w, col_w * 0.7, col_w * 0.7])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _HEADER_BG),
                ("TEXTCOLOR", (0, 0), (-1, 0), _HEADER_FG),
                ("BACKGROUND", (0, 1), (-1, -1), _LIGHT_GREY),
                ("GRID", (0, 0), (-1, -1), 0.4, _GRID),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("ALIGN", (1, 1), (-1, -1), "CENTER"),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [_LIGHT_GREY, colors.white],
                ),
            ]
        )
    )
    return t


# ---------------------------------------------------------------------------
# Combat stats block
# ---------------------------------------------------------------------------


def _stat_cell(label: str, value: str, st: dict) -> list:
    """A vertically stacked label+value for display in combat grid."""
    return [Paragraph(label, st["label"]), Paragraph(value, st["big"])]


def _combat_block(d: SheetData, st: dict) -> list:
    items = []
    items.append(_section_header("COMBAT", st))
    c = d.combat

    # Row 1: AC / Touch / Flat-footed / HP / Init / Speed
    row1 = [
        _stat_cell("Armor Class", str(c.ac), st),
        _stat_cell("Touch AC", str(c.touch_ac), st),
        _stat_cell("Flat-footed AC", str(c.flatfooted_ac), st),
        _stat_cell("HP Max", str(c.hp_max), st),
        _stat_cell("Initiative", _signed(c.initiative), st),
        _stat_cell("Speed (ft)", str(c.speed), st),
    ]
    t1 = Table([row1], colWidths=[CONTENT_W / 6] * 6)
    t1.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, _GRID),
                ("BACKGROUND", (0, 0), (-1, -1), _LIGHT_GREY),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    items.append(t1)

    # Row 2: BAB / Fort / Ref / Will / SR / Damage bonus
    row2 = [
        _stat_cell("BAB", _signed(c.bab), st),
        _stat_cell("Fortitude", _signed(c.fort), st),
        _stat_cell("Reflex", _signed(c.ref), st),
        _stat_cell("Will", _signed(c.will), st),
        _stat_cell("Spell Resist", str(c.sr) if c.sr else "—", st),
        _stat_cell("Damage Bonus", _signed(c.damage_bonus), st),
    ]
    t2 = Table([row2], colWidths=[CONTENT_W / 6] * 6)
    t2.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, _GRID),
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    items.append(t2)

    # Attack row
    atk_data = [
        [
            Paragraph("Primary Melee Attack", st["label"]),
            Paragraph("Primary Ranged Attack", st["label"]),
        ],
        [
            Paragraph(_signed(c.attack_melee), st["big"]),
            Paragraph(_signed(c.attack_ranged), st["big"]),
        ],
    ]
    t3 = Table(atk_data, colWidths=[CONTENT_W / 2] * 2)
    t3.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, _GRID),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("BACKGROUND", (0, 0), (-1, 0), _SUBHEAD_BG),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    items.append(t3)
    return items


# ---------------------------------------------------------------------------
# Active buffs block (page 1 sidebar)
# ---------------------------------------------------------------------------


def _active_buffs_block(d: SheetData, st: dict) -> list:
    items = []
    items.append(_section_header("ACTIVE BUFFS", st))

    if not d.active_buffs:
        items.append(Paragraph("— No active buffs —", st["small_italic"]))
        return items

    rows = [
        [
            Paragraph("Buff Name", st["h2"]),
            Paragraph("CL", st["h2"]),
            Paragraph("Pts", st["h2"]),
        ]
    ]
    for b in d.active_buffs:
        cl_str = str(b.caster_level) if b.caster_level else "—"
        pts_str = str(b.parameter) if b.parameter else "—"
        rows.append(
            [
                Paragraph(b.name, st["small"]),
                Paragraph(cl_str, st["centered"]),
                Paragraph(pts_str, st["centered"]),
            ]
        )

    cw = [CONTENT_W * 0.65, CONTENT_W * 0.175, CONTENT_W * 0.175]
    t = Table(rows, colWidths=cw)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _HEADER_BG),
                ("TEXTCOLOR", (0, 0), (-1, 0), _HEADER_FG),
                ("GRID", (0, 0), (-1, -1), 0.4, _GRID),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [_LIGHT_GREY, colors.white],
                ),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    items.append(t)
    return items


# ---------------------------------------------------------------------------
# Skills table (page 2)
# ---------------------------------------------------------------------------


def _skills_table(d: SheetData, st: dict) -> list:
    items = []
    items.append(_section_header("SKILLS", st))

    header = [
        Paragraph("CS", st["h2"]),
        Paragraph("Skill", st["h2"]),
        Paragraph("Abil", st["h2"]),
        Paragraph("Ranks", st["h2"]),
        Paragraph("Misc", st["h2"]),
        Paragraph("Total", st["h2"]),
    ]
    rows = [header]

    for skill in d.skills:
        cs_mark = Paragraph(
            '<font color="#1565C0">●</font>' if skill.class_skill else "",
            st["centered"],
        )
        name_style = (
            st["small"] if not skill.trained_only else st["small_italic"]
        )
        total_col = _signed_para(skill.total, st["centered"])
        misc_text = _signed(skill.misc) if skill.misc else "—"

        rows.append(
            [
                cs_mark,
                Paragraph(skill.name, name_style),
                Paragraph(skill.ability, st["centered"]),
                Paragraph(
                    str(skill.ranks) if skill.ranks else "—", st["centered"]
                ),
                Paragraph(misc_text, st["centered"]),
                total_col,
            ]
        )

    cw = [
        CONTENT_W * 0.05,
        CONTENT_W * 0.46,
        CONTENT_W * 0.09,
        CONTENT_W * 0.10,
        CONTENT_W * 0.10,
        CONTENT_W * 0.10,
    ]
    t = Table(rows, colWidths=cw, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _HEADER_BG),
                ("TEXTCOLOR", (0, 0), (-1, 0), _HEADER_FG),
                ("GRID", (0, 0), (-1, -1), 0.3, _GRID),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [_LIGHT_GREY, colors.white],
                ),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("ALIGN", (2, 1), (-1, -1), "CENTER"),
            ]
        )
    )
    items.append(t)
    return items


# ---------------------------------------------------------------------------
# Feats table (page 2)
# ---------------------------------------------------------------------------


def _feats_table(d: SheetData, st: dict) -> list:
    items = []
    items.append(_section_header("FEATS", st))

    if not d.feats:
        items.append(Paragraph("— No feats recorded —", st["small_italic"]))
        return items

    header = [
        Paragraph("Feat Name", st["h2"]),
        Paragraph("Note", st["h2"]),
        Paragraph("Source", st["h2"]),
    ]
    rows = [header]
    for feat in d.feats:
        source_text = (
            feat.source.replace("template:", "Template: ")
            if feat.source
            else ""
        )
        rows.append(
            [
                Paragraph(feat.name, st["small"]),
                Paragraph(feat.note[:60] if feat.note else "", st["note"]),
                Paragraph(source_text[:30], st["note"]),
            ]
        )

    cw = [CONTENT_W * 0.35, CONTENT_W * 0.48, CONTENT_W * 0.17]
    t = Table(rows, colWidths=cw, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _HEADER_BG),
                ("TEXTCOLOR", (0, 0), (-1, 0), _HEADER_FG),
                ("GRID", (0, 0), (-1, -1), 0.3, _GRID),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [_LIGHT_GREY, colors.white],
                ),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    items.append(t)
    return items


# ---------------------------------------------------------------------------
# Notes block (templates, DM overrides)
# ---------------------------------------------------------------------------


def _notes_block(d: SheetData, st: dict) -> list:
    items = []
    if not d.templates and not d.dm_overrides:
        return items

    items.append(_section_header("NOTES & OVERRIDES", st))
    rows = []

    if d.templates:
        rows.append(
            [
                Paragraph("Templates:", st["value_bold"]),
                Paragraph(", ".join(d.templates), st["small"]),
            ]
        )
    for ov in d.dm_overrides:
        rows.append(
            [
                Paragraph("DM Override:", st["value_bold"]),
                Paragraph(ov, st["small"]),
            ]
        )

    if rows:
        t = Table(rows, colWidths=[CONTENT_W * 0.22, CONTENT_W * 0.78])
        t.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.3, _GRID),
                    ("BACKGROUND", (0, 0), (-1, -1), _LIGHT_GREY),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        items.append(t)
    return items


# ---------------------------------------------------------------------------
# Page-number footer
# ---------------------------------------------------------------------------


def _footer(
    canvas: Canvas,
    doc: SimpleDocTemplate,
) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#888888"))
    canvas.drawCentredString(
        PAGE_W / 2, 0.3 * inch, f"HeroForge Anew  |  Page {doc.page}"
    )
    canvas.restoreState()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def render_pdf(sheet_data: SheetData, path: Path | str) -> None:
    """
    Render a full character sheet PDF to *path*.

    Page 1: Identity, Abilities, Combat stats, Active buffs.
    Page 2: Skills, Feats, Notes.
    """
    path = Path(path)
    st = _styles()

    doc = SimpleDocTemplate(
        str(path),
        pagesize=letter,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=0.6 * inch,  # room for footer
    )

    story: list = []

    # ── Page 1 header ────────────────────────────────────────────────────
    char_name = sheet_data.identity.name or "Unnamed Character"
    story.append(Paragraph(char_name, st["h1"]))
    story.append(Spacer(1, 0.08 * inch))

    # Two-column layout: abilities (left) + combat (right)
    # We simulate two columns using a single-row Table
    left_col: list = []
    left_col += _identity_block(sheet_data, st)
    left_col.append(Spacer(1, 0.1 * inch))
    left_col.append(_ability_block(sheet_data, st))

    right_col: list = []
    right_col += _combat_block(sheet_data, st)
    right_col.append(Spacer(1, 0.1 * inch))
    right_col += _active_buffs_block(sheet_data, st)

    # Wrap each column in a sub-Table so they sit side by side
    from reportlab.platypus import KeepInFrame

    COL_W = CONTENT_W / 2 - 4  # 4pt gutter

    def _col_table(
        flowables: list,
        width: float,
    ) -> KeepInFrame:
        """Wrap flowables into a KeepInFrame."""
        frame = KeepInFrame(
            maxWidth=width,
            maxHeight=9 * inch,
            content=flowables,
            mode="shrink",
        )
        return frame

    page1_cols = Table(
        [[_col_table(left_col, COL_W), _col_table(right_col, COL_W)]],
        colWidths=[COL_W + 4, COL_W],
        hAlign="LEFT",
    )
    page1_cols.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(page1_cols)

    # ── Page 2 ───────────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph(f"{char_name} — Page 2", st["h1"]))
    story.append(Spacer(1, 0.08 * inch))

    story += _skills_table(sheet_data, st)
    story.append(Spacer(1, 0.15 * inch))
    story += _feats_table(sheet_data, st)
    story.append(Spacer(1, 0.15 * inch))
    story += _notes_block(sheet_data, st)

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
