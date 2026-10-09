"""Per-step capsule: budget, state-derivation, pointers-only, completeness (WP03 / T013).

These tests pin the two contracts the capsule owns:

* **bounded** -- the rendered capsule is non-vacuous and ``<= 2048`` bytes (NFR-001);
* **complete and derived** -- it is derived from real engine state, carries every field
  the old action payload carried (step, wp title, owned files, subtasks, refs, gate),
  and delivers doctrine as validated **pointers** with no inlined body (FR-002/FR-003).

The completeness guard is deliberately non-vacuous: the work-package facts are asserted
non-empty *and* present, so removing a field from the renderer fails the suite.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from typer.testing import CliRunner

from specify_cli.cli.commands import steer as steer_module
from specify_cli.steering import capsule
from specify_cli.steering.capsule import DEFAULT_POINTERS, STEP_POINTERS, Capsule, Pointer
from specify_cli.steering.index import JsonScanIndex, IndexEntry, build_index, fetch
from specify_cli.task_utils import find_repo_root

MISSION_SLUG = "context-lean-steering-01M4F5GH"
WP_ID = "WP03"
WP_TITLE = "Per-step capsule emitter"
OWNED_FILES = (
    "src/specify_cli/steering/capsule.py",
    "tests/specify_cli/steering/test_capsule.py",
)
SUBTASKS = ("T009", "T010", "T011", "T012", "T013")
REQUIREMENT_REFS = ("FR-002", "FR-003", "NFR-001")

#: A fixed engine decision with a resolved work package, injected where a test
#: must not depend on the live board (the real query may report ``wp_id: null``).
FIXED_DECISION: dict[str, object] = {
    "preview_step": "implement",
    "mission_state": "implement",
    "mission_slug": MISSION_SLUG,
    "wp_id": WP_ID,
}


@pytest.fixture(scope="module")
def repo_root() -> Path:
    return find_repo_root()


@pytest.fixture(scope="module")
def capsule_with_wp(repo_root: Path) -> Capsule:
    return capsule.build_capsule(MISSION_SLUG, repo_root=repo_root, decision=FIXED_DECISION)


# ---------------------------------------------------------------------------
# T009 -- the model renders a bounded, well-formed capsule
# ---------------------------------------------------------------------------


def test_render_is_non_vacuous_and_within_budget(capsule_with_wp: Capsule) -> None:
    text = capsule.render(capsule_with_wp)
    size = len(text.encode("utf-8"))
    assert size > 0
    assert size <= capsule.CAPSULE_MAX_BYTES


def test_render_is_deterministic(capsule_with_wp: Capsule) -> None:
    assert capsule.render(capsule_with_wp) == capsule.render(capsule_with_wp)


def test_render_contains_step_wp_pointer_and_gate(capsule_with_wp: Capsule) -> None:
    text = capsule.render(capsule_with_wp)
    assert f"step: {capsule_with_wp.step}" in text
    assert f"wp: {WP_ID} — {WP_TITLE}" in text
    assert capsule_with_wp.pointers, "the capsule must carry at least one doctrine pointer"
    assert "spec-kitty steer fetch " in text
    assert capsule_with_wp.gate in text
    assert "steer check" in text


# ---------------------------------------------------------------------------
# T010 -- derived from real engine state, never hardcoded
# ---------------------------------------------------------------------------


def test_capsule_step_and_mission_match_engine(repo_root: Path) -> None:
    decision = capsule.next_decision(MISSION_SLUG, repo_root)
    derived = capsule.build_capsule(MISSION_SLUG, repo_root=repo_root)
    expected_step = decision.get("preview_step") or decision.get("mission_state")
    assert derived.step == expected_step
    assert derived.mission == decision.get("mission_slug")
    wp_id = decision.get("wp_id")
    if isinstance(wp_id, str) and wp_id:
        assert derived.wp.startswith(wp_id)


def test_capsule_step_tracks_the_engine_decision(repo_root: Path) -> None:
    implementing = capsule.build_capsule(MISSION_SLUG, repo_root=repo_root, decision=FIXED_DECISION)
    reviewing = capsule.build_capsule(
        MISSION_SLUG,
        repo_root=repo_root,
        decision={**FIXED_DECISION, "preview_step": "review", "mission_state": "review"},
    )
    assert implementing.step == "implement"
    assert reviewing.step == "review"
    assert implementing.pointers != reviewing.pointers, "the pointer set follows the step"


def test_wp_facts_come_from_the_work_package_frontmatter(repo_root: Path) -> None:
    facts = capsule.wp_facts(repo_root, MISSION_SLUG, WP_ID)
    assert facts.get("title") == WP_TITLE
    assert facts.get("owned_files") == list(OWNED_FILES)
    assert facts.get("subtasks") == list(SUBTASKS)
    assert facts.get("requirement_refs") == list(REQUIREMENT_REFS)


def test_parse_frontmatter_reads_scalars_and_lists() -> None:
    text = "---\ntitle: Example\nlist:\n- a\n- b\nempty: []\n---\nbody\n"
    parsed = capsule.parse_frontmatter(text)
    assert parsed["title"] == "Example"
    assert parsed["list"] == ["a", "b"]
    assert capsule.parse_frontmatter("no frontmatter") == {}


# ---------------------------------------------------------------------------
# T011 -- doctrine as pointers only (no bodies)
# ---------------------------------------------------------------------------


def test_pointers_resolve_through_the_wp02_index(repo_root: Path) -> None:
    index = build_index(repo_root)
    derived = capsule.build_capsule(MISSION_SLUG, repo_root=repo_root, decision=FIXED_DECISION)
    assert derived.pointers
    for pointer in derived.pointers:
        assert index.resolve(pointer.selector) is not None, pointer.selector


def test_dangling_selectors_are_dropped() -> None:
    kept = "directive:DIRECTIVE_044"
    index = JsonScanIndex((IndexEntry(selector=kept, source_path="x.yaml", when="kept"),))
    pointers = capsule.build_pointers("implement", Path("."), index=index)
    assert [pointer.selector for pointer in pointers] == [kept]


def test_no_pointer_resolves_falls_back_to_first_configured() -> None:
    pointers = capsule.build_pointers("implement", Path("."), index=JsonScanIndex(()))
    assert len(pointers) == 1
    assert pointers[0].selector == STEP_POINTERS["implement"][0][0]


def test_unknown_step_uses_default_pointers() -> None:
    assert capsule.configured_pointers("blocked:no_actionable_wp") == DEFAULT_POINTERS
    assert capsule.configured_pointers("not_started") == DEFAULT_POINTERS
    assert capsule.configured_pointers("review") == STEP_POINTERS["review"]


def test_capsule_inlines_no_doctrine_body(repo_root: Path, capsule_with_wp: Capsule) -> None:
    text = capsule.render(capsule_with_wp)
    assert capsule_with_wp.pointers
    for pointer in capsule_with_wp.pointers:
        body = fetch(repo_root, pointer.selector).body.strip()
        assert body, "each pointer must resolve to a canonical body"
        prefix = body[:80]
        assert prefix not in text, f"doctrine body for {pointer.selector} must not be inlined"


# ---------------------------------------------------------------------------
# T013 -- completeness: no field the old payload carried is silently dropped
# ---------------------------------------------------------------------------


def test_completeness_every_required_field_is_present(capsule_with_wp: Capsule) -> None:
    text = capsule.render(capsule_with_wp)
    # Non-vacuity: each field source is populated before we assert it survives.
    assert capsule_with_wp.step
    assert capsule_with_wp.facts["owned_files"] == OWNED_FILES
    assert capsule_with_wp.facts["subtasks"] == SUBTASKS
    assert capsule_with_wp.facts["requirement_refs"] == REQUIREMENT_REFS
    assert capsule_with_wp.gate

    assert f"step: {capsule_with_wp.step}" in text
    assert WP_TITLE in text
    for owned in OWNED_FILES:
        assert owned in text
    for subtask in SUBTASKS:
        assert subtask in text
    for ref in REQUIREMENT_REFS:
        assert ref in text
    assert capsule_with_wp.gate in text


def test_completeness_guard_is_non_vacuous(capsule_with_wp: Capsule) -> None:
    """Removing a fact from the capsule removes it from the render -- the guard bites."""
    assert "requirement_refs:" in capsule.render(capsule_with_wp)
    stripped = replace(capsule_with_wp, facts={**capsule_with_wp.facts, "requirement_refs": ()})
    assert "requirement_refs:" not in capsule.render(stripped)


# ---------------------------------------------------------------------------
# T012 -- the CLI surface
# ---------------------------------------------------------------------------


def test_steer_capsule_prints_the_text_form(monkeypatch: pytest.MonkeyPatch, repo_root: Path) -> None:
    monkeypatch.setattr(capsule, "next_decision", lambda mission, root: dict(FIXED_DECISION))
    result = CliRunner().invoke(steer_module.app, ["capsule", "--mission", MISSION_SLUG])
    assert result.exit_code == 0
    expected = capsule.render(capsule.build_capsule(MISSION_SLUG, repo_root=repo_root, decision=FIXED_DECISION))
    assert result.stdout == expected
    assert "step: implement" in result.stdout


def test_steer_capsule_json_matches_the_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(capsule, "next_decision", lambda mission, root: dict(FIXED_DECISION))
    result = CliRunner().invoke(steer_module.app, ["capsule", "--mission", MISSION_SLUG, "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert set(payload) == {"mission", "step", "wp", "facts", "pointers", "gate"}
    assert payload["mission"] == MISSION_SLUG
    assert payload["step"] == "implement"
    assert payload["wp"] == f"{WP_ID} — {WP_TITLE}"
    assert payload["pointers"]
    assert payload["gate"] == f"spec-kitty steer check --mission {MISSION_SLUG}"


def test_pointer_payload_shape() -> None:
    pointer = Pointer(selector="directive:DIRECTIVE_030", when="before declaring done")
    capsule_obj = Capsule(mission="m", step="implement", wp="", facts={}, pointers=(pointer,), gate="g")
    assert capsule_obj.to_payload()["pointers"] == [{"selector": pointer.selector, "when": pointer.when}]
