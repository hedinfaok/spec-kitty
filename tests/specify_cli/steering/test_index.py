"""Deterministic doctrine index and retrieval (WP02 / T005-T008).

These tests prove the three contracts the index owns:

* a known selector resolves to its **canonical source file** (T005);
* the FTS5 and JSON backends expose the *same* query surface (T006);
* ``steer fetch`` returns the canonical body and an unknown selector raises an
  explicit ``STEER_SELECTOR_UNKNOWN`` error, never an empty result (T007-T008).

The body-fidelity tests assert byte-identity against the canonical engine
surface -- ``charter context --include`` -- so a paraphrase or a reformatted
summary would fail them (NFR-003).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from specify_cli.cli.commands import steer as steer_module
from specify_cli.steering import index
from specify_cli.steering.index import (
    STEER_SELECTOR_UNKNOWN,
    Fts5Index,
    IndexEntry,
    JsonScanIndex,
    SteerSelectorUnknown,
    build_entries,
    build_index,
    canonical_source_text,
    fetch,
    index_path,
)
from specify_cli.task_utils import find_repo_root

KNOWN_SELECTOR = "directive:DIRECTIVE_030"
KNOWN_SOURCE_SUFFIX = "packs/built-in/directives/030-test-and-typecheck-quality-gate.directive.yaml"
UNKNOWN_SELECTOR = "directive:NOT_A_REAL_DIRECTIVE"
SECTION_SELECTOR = "section:terminology-canon"
SECTION_WHEN = "rename or introduce a term in the diff"


@pytest.fixture(scope="module")
def repo_root() -> Path:
    return find_repo_root()


@pytest.fixture(scope="module")
def entries(repo_root: Path) -> tuple[IndexEntry, ...]:
    return build_entries(repo_root)


# ---------------------------------------------------------------------------
# T005 -- the index maps selectors to canonical sources
# ---------------------------------------------------------------------------


def test_build_entries_is_non_empty_and_unique(entries: tuple[IndexEntry, ...]) -> None:
    assert entries, "the doctrine corpus must yield a non-empty index"
    selectors = [entry.selector for entry in entries]
    assert len(selectors) == len(set(selectors)), "each selector resolves to exactly one canonical source"


def test_build_entries_is_deterministic(repo_root: Path, entries: tuple[IndexEntry, ...]) -> None:
    assert build_entries(repo_root) == entries


def test_index_counts_match_builtin_source_files(repo_root: Path, entries: tuple[IndexEntry, ...]) -> None:
    from charter.offering.artifact_kinds import ArtifactKind
    from charter.offering.pack_paths import built_in_dir

    directive_dir = built_in_dir(ArtifactKind.DIRECTIVE)
    expected = len(list(directive_dir.rglob(ArtifactKind.DIRECTIVE.glob_pattern)))
    actual = sum(1 for entry in entries if directive_dir in Path(entry.source_path).parents)
    assert expected > 0
    assert actual == expected


def test_known_selector_resolves_to_expected_source(repo_root: Path, entries: tuple[IndexEntry, ...]) -> None:
    index = JsonScanIndex(entries)
    resolved = index.resolve(KNOWN_SELECTOR)
    assert resolved is not None
    assert resolved.source_path.endswith(KNOWN_SOURCE_SUFFIX)
    assert Path(resolved.source_path).is_file()


def test_operator_token_alias_resolves_to_canonical_kind(entries: tuple[IndexEntry, ...]) -> None:
    index = JsonScanIndex(entries)
    hyphenated = index.resolve("agent-profile:analyst-annie")
    underscore = index.resolve("agent_profile:analyst-annie")
    assert hyphenated is not None
    assert hyphenated == underscore


def test_section_selector_carries_its_when_clause(entries: tuple[IndexEntry, ...]) -> None:
    resolved = JsonScanIndex(entries).resolve(SECTION_SELECTOR)
    assert resolved is not None
    assert resolved.when == SECTION_WHEN
    assert resolved.source_path.endswith(".kittify/charter/charter.md")


def test_unknown_selector_is_not_in_the_index(entries: tuple[IndexEntry, ...]) -> None:
    assert JsonScanIndex(entries).resolve(UNKNOWN_SELECTOR) is None


# ---------------------------------------------------------------------------
# T007 -- fetch returns the canonical body; unknown selectors error explicitly
# ---------------------------------------------------------------------------


def test_fetch_matches_canonical_engine_surface(repo_root: Path) -> None:
    from charter.activation.context import build_charter_context_include

    result = fetch(repo_root, KNOWN_SELECTOR)
    canonical = build_charter_context_include(repo_root, KNOWN_SELECTOR, org_root=None)
    assert result.selector == KNOWN_SELECTOR
    assert result.body == canonical
    assert result.body.strip()


def test_fetch_is_deterministic(repo_root: Path) -> None:
    assert fetch(repo_root, KNOWN_SELECTOR).body == fetch(repo_root, KNOWN_SELECTOR).body


def test_canonical_source_text_is_verbatim(repo_root: Path, entries: tuple[IndexEntry, ...]) -> None:
    resolved = JsonScanIndex(entries).resolve(KNOWN_SELECTOR)
    assert resolved is not None
    assert canonical_source_text(repo_root, resolved) == Path(resolved.source_path).read_text(encoding="utf-8")


def test_unknown_selector_raises_explicit_code(repo_root: Path) -> None:
    with pytest.raises(SteerSelectorUnknown) as excinfo:
        fetch(repo_root, UNKNOWN_SELECTOR)
    assert excinfo.value.code == STEER_SELECTOR_UNKNOWN
    assert excinfo.value.selector == UNKNOWN_SELECTOR


# ---------------------------------------------------------------------------
# T006 -- FTS5 backend with a JSON fallback
# ---------------------------------------------------------------------------


def test_fts5_and_json_backends_agree(entries: tuple[IndexEntry, ...]) -> None:
    json_index = JsonScanIndex(entries)
    fts_index = Fts5Index(entries)
    for selector in (KNOWN_SELECTOR, SECTION_SELECTOR, "agent_profile:analyst-annie", UNKNOWN_SELECTOR):
        assert json_index.resolve(selector) == fts_index.resolve(selector)
    for query in ("directive:DIRECTIVE_030", "DIRECTIVE_030", "terminology canon"):
        assert json_index.search(query) == fts_index.search(query)
    assert [entry.selector for entry in fts_index.search(KNOWN_SELECTOR)] == [KNOWN_SELECTOR]


def test_json_fallback_when_fts5_unavailable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(index, "fts5_available", lambda: False)
    built = build_index(tmp_path)
    assert isinstance(built, JsonScanIndex)
    assert built.backend_name == "json"
    assert built.resolve(KNOWN_SELECTOR) is not None
    assert [entry.selector for entry in built.search("DIRECTIVE_030")] == [KNOWN_SELECTOR]


def test_explicit_fts5_backend_refuses_when_unavailable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(index, "fts5_available", lambda: False)
    with pytest.raises(RuntimeError, match="FTS5"):
        build_index(tmp_path, backend="fts5")


def test_fts5_available_returns_a_bool() -> None:
    assert isinstance(index.fts5_available(), bool)


# ---------------------------------------------------------------------------
# Persistence and rebuild-on-change
# ---------------------------------------------------------------------------


def test_build_index_persists_and_reuses_cache(tmp_path: Path) -> None:
    first = build_index(tmp_path)
    stored = index_path(tmp_path)
    assert stored.is_file()
    mtime_after_first_build = stored.stat().st_mtime_ns

    second = build_index(tmp_path)
    assert stored.stat().st_mtime_ns == mtime_after_first_build, "a fresh index is reused, not rewritten"
    assert [entry.selector for entry in second.entries] == [entry.selector for entry in first.entries]


def test_build_index_rebuilds_when_sources_change(tmp_path: Path) -> None:
    doctrine_dir = tmp_path / ".kittify" / "doctrine" / "directive"
    doctrine_dir.mkdir(parents=True)
    (doctrine_dir / "EXAMPLE_ONE.directive.yaml").write_text("id: EXAMPLE_ONE\nwhen: when reviewing\n", encoding="utf-8")

    first = build_index(tmp_path)
    assert "directive:EXAMPLE_ONE" in {entry.selector for entry in first.entries}

    (doctrine_dir / "EXAMPLE_TWO.directive.yaml").write_text("id: EXAMPLE_TWO\n", encoding="utf-8")
    second = build_index(tmp_path)

    assert "directive:EXAMPLE_TWO" in {entry.selector for entry in second.entries}


def test_project_overlay_takes_precedence(tmp_path: Path) -> None:
    doctrine_dir = tmp_path / ".kittify" / "doctrine" / "directive"
    doctrine_dir.mkdir(parents=True)
    overlay = doctrine_dir / "DIRECTIVE_030.directive.yaml"
    overlay.write_text("id: DIRECTIVE_030\nwhen: project override\n", encoding="utf-8")

    resolved = build_index(tmp_path).resolve("directive:DIRECTIVE_030")
    assert resolved is not None
    assert Path(resolved.source_path).resolve() == overlay.resolve()
    assert resolved.when == "project override"


def test_corrupt_index_is_rebuilt(tmp_path: Path) -> None:
    build_index(tmp_path)
    index_path(tmp_path).write_text("{not json", encoding="utf-8")
    rebuilt = build_index(tmp_path)
    assert rebuilt.resolve(KNOWN_SELECTOR) is not None


# ---------------------------------------------------------------------------
# T007 -- the CLI surface
# ---------------------------------------------------------------------------


def test_steer_fetch_prints_the_canonical_body(repo_root: Path) -> None:
    result = CliRunner().invoke(steer_module.app, ["fetch", KNOWN_SELECTOR])
    assert result.exit_code == 0
    assert result.stdout.strip() == fetch(repo_root, KNOWN_SELECTOR).body.strip()


def test_steer_fetch_json_reports_selector_source_and_body(repo_root: Path) -> None:
    result = CliRunner().invoke(steer_module.app, ["fetch", KNOWN_SELECTOR, "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert set(payload) == {"selector", "source_path", "body"}
    assert payload["selector"] == KNOWN_SELECTOR
    assert payload["source_path"].endswith(KNOWN_SOURCE_SUFFIX)
    assert payload["body"] == fetch(repo_root, KNOWN_SELECTOR).body


def test_steer_fetch_unknown_selector_exits_non_zero() -> None:
    result = CliRunner().invoke(steer_module.app, ["fetch", UNKNOWN_SELECTOR])
    assert result.exit_code != 0
    assert STEER_SELECTOR_UNKNOWN in result.output
    assert result.stdout.strip() == "", "an unknown selector must never print an empty body"


def test_steer_fetch_unknown_selector_json_emits_error_code() -> None:
    result = CliRunner().invoke(steer_module.app, ["fetch", UNKNOWN_SELECTOR, "--json"])
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["success"] is False
    assert payload["error"] == STEER_SELECTOR_UNKNOWN
    assert payload["selector"] == UNKNOWN_SELECTOR
