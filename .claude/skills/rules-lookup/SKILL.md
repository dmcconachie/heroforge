---
name: rules-lookup
description: Search D&D 3.5 rulebook PDFs at ~/DnD/3.5 Books/ for a named item, feat, spell, monster, or other term. Returns matched text snippets with book and page. Use when the user asks to look up, verify, or cite any D&D 3.5 rules content — e.g. "look up X in the MIC", "verify this item against the book", "what does the PHB say about Y". First call per book extracts text to a cache (~/.cache/heroforge-rules-lookup/); subsequent calls are fast.
argument-hint: "<term> [--book <substring>] [--max N]"
allowed-tools: Bash
---

# rules-lookup

Look up a term across D&D 3.5 rulebook PDFs. Invoke the helper
script from this skill's scripts directory.

## How to invoke

Use Bash to run:

```
${CLAUDE_SKILL_DIR}/scripts/lookup.py "<term>" [flags]
```

If the user passed arguments after `/rules-lookup`, pass them
straight through to the script.

## Flags

- `--book <substring>` — only search PDFs whose filename contains
  this substring (e.g. `--book "Magic Item Compendium"`). Greatly
  speeds up lookups when you already know which book to read.
- `--context N` — lines of context around each match (default 3).
- `--max N` — stop after N hits (default 10).
- `--list-books` — list every PDF under `~/DnD/3.5 Books/`.

## When to narrow with `--book`

- Magic items → `--book "Magic Item Compendium"`
- Feats/classes/spells from core → `--book "Player's Handbook"` or
  `--book "Dungeon Masters Guide"`
- Splatbook content → the splatbook filename (e.g.
  `--book "Complete Scoundrel"`, `--book "Complete Arcane"`)

Use `--list-books` first if unsure what's available.

## Output format

Each match prints:

```
=== <book filename> · page <N> ===
  ...lines of context around the match...
```

## What to do with the output

- Quote the relevant text back to the user with a page citation.
- If you're verifying an existing rules entry (YAML, note,
  effect numbers), compare every stat to what the book says and
  flag discrepancies explicitly.
- The extractor is text-based; some PDFs have layout quirks that
  split words across lines. If a match looks truncated, read
  more context with `--context 8`.

## Apostrophe matching

Searches are case-insensitive and apostrophe-fuzzy: the term and
the page text are both lowercased and have apostrophe-like
characters (`'`, `‘`, `’`, `ʼ`) stripped before matching. So all
of these queries find the same entry:

- `"Lion's Pounce"` (ASCII)
- `"Lion’s Pounce"` (curly — what most PDFs actually contain)
- `"Lions Pounce"` (no apostrophe — extraction sometimes drops it)

A "no matches" result is a real absence, not an apostrophe
mismatch. If you still want to be paranoid, also try the bare
non-possessive root (e.g. `"Lion"`, `"Murlynd"`) once.

## First-call cost

Extracting a full sourcebook takes 10–30 seconds. Extraction is
cached per PDF under `~/.cache/heroforge-rules-lookup/`; later
calls against the same book are nearly instant.
