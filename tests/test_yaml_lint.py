"""
tests/test_yaml_lint.py
-----------------------
YAML formatting linter for rules/core/ YAML files.

Enforces:
  1. Every line is at most 80 characters.
  2. Flow mappings (``{...}``) must fit on a single
     line.  A flow mapping split across multiple lines
     is an error — use block-style mapping instead.

Run the auto-fixer to rewrite offending flow mappings
into block style::

    uv run pytest tests/test_yaml_lint.py

To apply fixes automatically::

    uv run python tests/test_yaml_lint.py --fix
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

RULES_DIR = (
    Path(__file__).parent.parent / "src" / "heroforge" / "rules" / "core"
)

MAX_LINE = 80


# ---------------------------------------------------------------
# Detection
# ---------------------------------------------------------------


def lint_file(
    path: Path,
) -> list[str]:
    """Return a list of error strings for *path*."""
    errors: list[str] = []
    lines = path.read_text().splitlines()
    name = path.name

    for i, line in enumerate(lines, 1):
        # Rule 1: line length
        if len(line) > MAX_LINE:
            errors.append(
                f"{name}:{i}: line is {len(line)} chars (max {MAX_LINE})"
            )

    # Rule 2: multi-line flow mappings
    # A flow mapping starts with `{` and ends with
    # `}`.  If we see a `{` that is not closed by `}`
    # on the same line, the mapping is split.
    for i, line in enumerate(lines, 1):
        stripped = line.lstrip()
        # Skip comment lines
        if stripped.startswith("#"):
            continue
        # Count unquoted braces (ignore braces inside
        # quoted strings).
        text = _strip_yaml_strings(stripped)
        opens = text.count("{")
        closes = text.count("}")
        if opens > closes:
            errors.append(
                f"{name}:{i}: flow mapping "
                f"split across lines — use block "
                f"style instead"
            )

    return errors


def _strip_yaml_strings(text: str) -> str:
    """
    Replace quoted strings with placeholder.

    This prevents brace characters inside strings
    from being counted as flow-mapping delimiters.
    """
    return re.sub(r'"[^"]*"', '""', text)


# ---------------------------------------------------------------
# Auto-fix
# ---------------------------------------------------------------


def fix_file(path: Path) -> int:
    """
    Rewrite split flow mappings to block style.

    Returns the number of fixes applied.
    """
    lines = path.read_text().splitlines()
    out: list[str] = []
    fixes = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()

        # Skip comments
        if stripped.startswith("#"):
            out.append(line)
            i += 1
            continue

        text = _strip_yaml_strings(stripped)
        opens = text.count("{")
        closes = text.count("}")

        if opens > closes:
            # Collect continuation lines until braces
            # balance.
            collected = line
            j = i + 1
            while j < len(lines):
                collected += "\n" + lines[j]
                t = _strip_yaml_strings(collected)
                if t.count("{") <= t.count("}"):
                    break
                j += 1

            block = _flow_to_block(collected, line, lines[i : j + 1])
            if block is not None:
                out.extend(block)
                fixes += 1
                i = j + 1
                continue

        # Single-line flow mapping that's too long
        if len(line) > MAX_LINE and opens == closes and opens > 0:
            block = _flow_to_block(line, line, [line])
            if block is not None:
                all_fit = all(len(b) <= MAX_LINE for b in block)
                if all_fit:
                    out.extend(block)
                    fixes += 1
                    i += 1
                    continue

        out.append(line)
        i += 1

    if fixes:
        path.write_text("\n".join(out) + "\n")
    return fixes


def _flow_to_block(
    collected: str,
    first_line: str,
    raw_lines: list[str],
) -> list[str] | None:
    """
    Convert a multi-line flow mapping to block.

    Handles the common pattern::

        - {key1: val1, key2: val2,
           key3: val3}

    Returns a list of block-style lines, or None if
    the pattern is not recognised.
    """
    indent = len(first_line) - len(first_line.lstrip())
    prefix = first_line[:indent]

    # Join all lines, strip the leading "- " if
    # present, and parse the flow mapping.
    joined = " ".join(ln.strip() for ln in raw_lines)

    # Check for list-item flow: "- {k: v, ...}"
    m = re.match(r"^- \{(.+)\}\s*$", joined.strip())
    if m:
        inner = m.group(1)
        pairs = _split_flow_pairs(inner)
        if pairs is None:
            return None
        result = [f"{prefix}- {pairs[0]}"]
        # Indent continuation keys under the dash
        cont_indent = prefix + "  "
        for pair in pairs[1:]:
            result.append(f"{cont_indent}{pair}")
        return result

    return None


def _split_flow_pairs(inner: str) -> list[str] | None:
    """
    Split ``key: val, key: val`` into pairs.

    Returns list of ``key: value`` strings, or None
    on parse failure.
    """
    pairs: list[str] = []
    depth = 0
    in_quote = False
    current = ""
    for ch in inner:
        if ch == '"' and not in_quote:
            in_quote = True
            current += ch
        elif ch == '"' and in_quote:
            in_quote = False
            current += ch
        elif in_quote:
            current += ch
        elif ch in "{[":
            depth += 1
            current += ch
        elif ch in "}]":
            depth -= 1
            current += ch
        elif ch == "," and depth == 0:
            pairs.append(current.strip())
            current = ""
        else:
            current += ch
    if current.strip():
        pairs.append(current.strip())
    return pairs if pairs else None


# ---------------------------------------------------------------
# Pytest entry point
# ---------------------------------------------------------------


def _all_yaml_files() -> list[Path]:
    return sorted(RULES_DIR.glob("*.yaml"))


class TestYamlLint:
    """Every YAML file must pass the linter."""

    def test_no_long_lines(self) -> None:
        errors: list[str] = []
        for path in _all_yaml_files():
            for err in lint_file(path):
                if "line is" in err:
                    errors.append(err)
        assert errors == [], "Lines exceeding 80 characters:\n" + "\n".join(
            errors
        )

    def test_no_split_flow_mappings(self) -> None:
        errors: list[str] = []
        for path in _all_yaml_files():
            for err in lint_file(path):
                if "flow mapping" in err:
                    errors.append(err)
        assert errors == [], "Flow mappings split across lines:\n" + "\n".join(
            errors
        )


# ---------------------------------------------------------------
# CLI: --fix mode
# ---------------------------------------------------------------

if __name__ == "__main__":
    do_fix = "--fix" in sys.argv
    total_errors = 0
    total_fixes = 0

    for path in _all_yaml_files():
        errs = lint_file(path)
        if errs:
            for e in errs:
                print(e)
            total_errors += len(errs)

        if do_fix:
            n = fix_file(path)
            if n:
                print(f"  Fixed {n} split flow mappings in {path.name}")
                total_fixes += n

    if total_errors and not do_fix:
        print(
            f"\n{total_errors} error(s). "
            f"Run with --fix to auto-repair "
            f"split flow mappings."
        )
        sys.exit(1)
    elif total_fixes:
        print(
            f"\nApplied {total_fixes} fix(es). "
            f"Re-run to check for remaining "
            f"issues."
        )
    else:
        print("All YAML files clean.")
