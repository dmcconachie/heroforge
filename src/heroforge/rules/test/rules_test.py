"""Tests for the Rules container and module-level accessor."""

import re
from pathlib import Path

import pytest

from heroforge.engine.enums import Alignment
from heroforge.rules import rules as rules_module
from heroforge.rules.rules import (
    Rules,
    book_dirs,
    get_rules,
    reset_rules,
    set_rules,
)


def test_rules_class_instantiable() -> None:
    """Rules() builds with empty registries (no load)."""
    r = Rules()
    assert r.feats is not None
    assert r.classes is not None
    assert r.prereq_checker is None


@pytest.mark.no_cached_rules
def test_get_rules_returns_same_object() -> None:
    sentinel = Rules()
    set_rules(sentinel)
    assert get_rules() is sentinel
    assert get_rules() is sentinel


@pytest.mark.no_cached_rules
def test_set_rules_overrides() -> None:
    r1 = Rules()
    r2 = Rules()
    set_rules(r1)
    assert get_rules() is r1
    set_rules(r2)
    assert get_rules() is r2


@pytest.mark.no_cached_rules
def test_reset_rules_forces_rebuild(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    reset_rules clears the cache; next get_rules triggers
    a fresh Rules + load()."""
    call_count = {"n": 0}

    def counting_load(
        self: Rules,  # noqa: ARG001
        rules_dir: object = None,  # noqa: ARG001
    ) -> None:
        call_count["n"] += 1

    monkeypatch.setattr(Rules, "load", counting_load)
    reset_rules()
    r1 = get_rules()
    assert call_count["n"] == 1
    r2 = get_rules()
    assert call_count["n"] == 1
    assert r1 is r2
    reset_rules()
    r3 = get_rules()
    assert call_count["n"] == 2
    assert r3 is not r1


def test_autouse_installs_cached_rules(_cached_rules: Rules) -> None:
    assert get_rules() is _cached_rules


def test_cached_rules_has_real_yaml_data(
    _cached_rules: Rules,
) -> None:
    assert _cached_rules.feats.get("Power Attack") is not None
    assert _cached_rules.classes.get("Fighter") is not None
    assert _cached_rules.skills.get("Tumble") is not None


def test_set_rules_from_prior_test_does_not_leak(
    _cached_rules: Rules,
) -> None:
    """
    Autouse teardown must clear any prior set_rules call so
    this test sees the cached Rules, not a leaked custom one."""
    assert get_rules() is _cached_rules


@pytest.mark.no_cached_rules
def test_load_validates_domain_spells(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """load() cross-checks domain spells against the compendium."""
    seen: dict[str, object] = {}

    def fake_validate(domains: object, spells: object) -> None:
        seen["domains"] = domains
        seen["spells"] = spells

    monkeypatch.setattr(rules_module, "validate_domain_spells", fake_validate)
    rules = Rules()
    rules.load()
    # Identity, not counts: the check must receive the registries
    # load() populated, and the assertion must not rot every time
    # a spell is added to the compendium.
    assert seen["domains"] is rules.domains
    assert seen["spells"] is rules.spells
    assert len(rules.domains) == 22
    assert len(rules.spells) > 0


# --- book_dirs ----------------------------------------------


def _mk_dirs(parent: Path, names: list[str]) -> None:
    for n in names:
        (parent / n).mkdir()


def test_book_dirs_orders_core_first_custom_last(tmp_path: Path) -> None:
    _mk_dirs(
        tmp_path,
        ["custom", "magic_item_compendium", "complete_warrior", "core"],
    )
    assert book_dirs(tmp_path) == [
        "core",
        "complete_warrior",
        "magic_item_compendium",
        "custom",
    ]


def test_book_dirs_alphabetises_middle(tmp_path: Path) -> None:
    _mk_dirs(
        tmp_path,
        ["core", "spell_compendium", "complete_mage", "custom", "draconomicon"],
    )
    assert book_dirs(tmp_path) == [
        "core",
        "complete_mage",
        "draconomicon",
        "spell_compendium",
        "custom",
    ]


def test_book_dirs_skips_hidden_dunder_and_test(tmp_path: Path) -> None:
    _mk_dirs(
        tmp_path,
        ["core", "custom", "__pycache__", ".git", "_private", "test"],
    )
    assert book_dirs(tmp_path) == ["core", "custom"]


def test_book_dirs_ignores_files(tmp_path: Path) -> None:
    _mk_dirs(tmp_path, ["core", "custom"])
    (tmp_path / "README.md").write_text("hi")
    (tmp_path / "rules.py").write_text("x = 1")
    assert book_dirs(tmp_path) == ["core", "custom"]


def test_book_dirs_handles_missing_core_or_custom(tmp_path: Path) -> None:
    _mk_dirs(tmp_path, ["complete_warrior", "spell_compendium"])
    assert book_dirs(tmp_path) == ["complete_warrior", "spell_compendium"]


def test_book_dirs_real_rules_dir_includes_core_and_custom() -> None:
    """Sanity check against the actual rules directory."""
    books = book_dirs()
    assert books[0] == "core"
    assert books[-1] == "custom"


def test_every_alignment_in_the_rules_is_a_valid_enum_member() -> None:
    """
    Regression for D3: two class files spelled alignments
    "Chaotic Good" where Alignment is "chaotic_good", so
    Wild Mage's and Hospitaler's entry requirements could
    never be met. The builder now coerces, which turns a
    misspelling into a load error — this catches it in the
    data instead.
    """
    bad: list[str] = []
    valid = {a.value for a in Alignment}
    for path in (Path(rules_module.__file__).parent).rglob("*.yaml"):
        for n, line in enumerate(path.read_text().split("\n"), start=1):
            m = re.match(r"\s*(?:-\s*)?alignment:\s*(\S.*)$", line)
            if m and m.group(1) not in valid:
                bad.append(f"{path.name}:{n} {m.group(1)!r}")
    assert bad == []


def test_alignment_prereq_lists_are_valid_enum_members() -> None:
    """The list form, as used by entry_prerequisites."""
    valid = {a.value for a in Alignment}
    bad: list[str] = []
    for path in (Path(rules_module.__file__).parent).rglob("*.yaml"):
        lines = path.read_text().split("\n")
        for i, line in enumerate(lines):
            if not re.match(r"\s*-?\s*alignment:\s*$", line):
                continue
            indent = len(line) - len(line.lstrip())
            for nxt in lines[i + 1 :]:
                if not nxt.strip():
                    continue
                if len(nxt) - len(nxt.lstrip()) <= indent:
                    break
                item = nxt.strip()
                if item.startswith("- ") and item[2:] not in valid:
                    bad.append(f"{path.name} {item[2:]!r}")
    assert bad == []
