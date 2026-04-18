"""
_gen_common.py
---------------
Shared helpers for YAML-to-StrEnum code generators
(_gen_magic_item_enums, _gen_pool_keys, etc.).
"""

from __future__ import annotations

import re


def enum_ident(name: str) -> str:
    """
    Convert a display name into an enum identifier
    (UPPER_SNAKE, ASCII only)."""
    s = name
    s = s.replace("+", "plus ")
    s = s.replace("'", "")
    s = s.replace("(", " ").replace(")", " ")
    s = s.replace("/", " ")
    s = s.replace(",", " ")
    s = s.replace(".", " ")
    s = s.replace("-", " ")
    s = s.replace("&", " and ")
    s = re.sub(r"\s+", " ", s).strip()
    return s.replace(" ", "_").upper()


def emit_member(lines: list[str], ident: str, val: str) -> None:
    """
    Append a StrEnum member line to ``lines``.
    Wraps long single-line members onto three lines
    to keep the 80-column limit.
    """
    single = f'    {ident} = "{val}"'
    if len(single) <= 80:
        lines.append(single)
        return
    lines.append(f"    {ident} = (")
    lines.append(f'        "{val}"')
    lines.append("    )")
