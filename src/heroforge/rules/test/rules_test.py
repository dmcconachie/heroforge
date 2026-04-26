"""Tests for the Rules container and module-level accessor."""

from pathlib import Path

import pytest

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
