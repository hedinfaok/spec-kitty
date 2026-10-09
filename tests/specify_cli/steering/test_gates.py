"""Planted-violation tests for the binding machine gates (WP04 / T018, NFR-005).

Every registered gate ships a planted violation that must refuse, plus a clean
case that must pass. A gate with no failing case is reported unverified by
:func:`specify_cli.steering.gates.unverified_gate_ids`, and adding a gate to the
registry without a test here turns the suite red. That is the falsifiability
NFR-005 demands: a gate that cannot fail is worth nothing.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable, Sequence

import pytest
from typer.testing import CliRunner

from specify_cli.cli.commands import steer as steer_module
from specify_cli.steering import gates as gates_module
from specify_cli.steering.gates import (
    Gate,
    GateTarget,
    ToolUnavailableError,
    run_gates,
    unverified_gate_ids,
)

CLEAN_BRANCH = "kitty/mission-demo-01ABC-lane-a"


def _completed(
    argv: Sequence[str],
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(list(argv), returncode, stdout, stderr)


def _install_run(monkeypatch: pytest.MonkeyPatch, handler: Callable[..., object]) -> None:
    """Replace the single subprocess seam all wrapped checks flow through."""
    monkeypatch.setattr(gates_module, "_run", handler)


def _seed_file(root, rel: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def _seed_ruff(root) -> None:
    (root / "ruff.toml").write_text("line-length = 164\n", encoding="utf-8")


def _seed_protection(root, branches: list[str]) -> None:
    path = root / ".kittify" / "config.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    joined = ", ".join(f'"{b}"' for b in branches)
    path.write_text(f"protection:\n  protected_branches: [{joined}]\n", encoding="utf-8")


def _seed_repo_gate(root, command: str) -> None:
    path = root / ".kittify" / "config.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    path.write_text(existing + f'steer:\n  gate_command: "{command}"\n', encoding="utf-8")


# ---------------------------------------------------------------------------
# T014 -- registry and aggregator
# ---------------------------------------------------------------------------


def test_empty_registry_is_clean(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(gates_module, "GATES", ())
    assert run_gates(GateTarget(root=tmp_path)) == []


def test_registered_failing_gate_returns_its_problem(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    gate = Gate("boom", lambda _target: ["kaboom"])
    monkeypatch.setattr(gates_module, "GATES", (gate,))
    assert run_gates(GateTarget(root=tmp_path)) == ["boom: kaboom"]


def test_run_gates_prefixes_every_problem_with_the_gate_id(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    passing = Gate("passing", lambda _target: [])
    failing = Gate("failing", lambda _target: ["one", "two"])
    monkeypatch.setattr(gates_module, "GATES", (passing, failing))
    assert run_gates(GateTarget(root=tmp_path)) == ["failing: one", "failing: two"]


def test_registry_gate_ids_are_unique() -> None:
    ids = [gate.id for gate in gates_module.GATES]
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# T015 -- reused checks: ruff, terminology and architectural layer rules
# ---------------------------------------------------------------------------


def test_ruff_gate_refuses_on_a_lint_violation(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _seed_ruff(tmp_path)

    def fake_run(argv: Sequence[str], *, cwd) -> subprocess.CompletedProcess[str]:
        if list(argv[:2]) == ["ruff", "check"]:
            return _completed(argv, returncode=1, stdout="src/x.py:1:1: E501 line too long")
        return _completed(argv)

    _install_run(monkeypatch, fake_run)
    problems = gates_module._ruff_gate(GateTarget(root=tmp_path))
    assert any("lint refused" in problem for problem in problems)


def test_ruff_gate_refuses_on_a_format_violation(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _seed_ruff(tmp_path)

    def fake_run(argv: Sequence[str], *, cwd) -> subprocess.CompletedProcess[str]:
        if list(argv[:2]) == ["ruff", "format"]:
            return _completed(argv, returncode=1, stdout="Would reformat: src/x.py")
        return _completed(argv)

    _install_run(monkeypatch, fake_run)
    problems = gates_module._ruff_gate(GateTarget(root=tmp_path))
    assert any("format check refused" in problem for problem in problems)


def test_ruff_gate_is_clean_when_ruff_passes(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _seed_ruff(tmp_path)
    _install_run(monkeypatch, lambda argv, *, cwd: _completed(argv))
    assert gates_module._ruff_gate(GateTarget(root=tmp_path)) == []


def test_ruff_gate_is_skipped_without_ruff_config(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _install_run(monkeypatch, lambda argv, *, cwd: _completed(argv))
    assert gates_module._ruff_gate(GateTarget(root=tmp_path)) == [], "a repo without ruff config is not linted"


def test_ruff_gate_fails_loudly_when_ruff_is_unavailable(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _seed_ruff(tmp_path)

    def fake_run(argv: Sequence[str], *, cwd):
        raise ToolUnavailableError("command 'ruff' not found")

    _install_run(monkeypatch, fake_run)
    problems = gates_module._ruff_gate(GateTarget(root=tmp_path))
    assert problems, "a missing ruff must refuse, never pass silently"
    assert all("unavailable" in problem for problem in problems)


def test_terminology_gate_refuses_on_a_planted_term(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _seed_file(tmp_path, gates_module._TERMINOLOGY_FILE)

    def fake_run(argv: Sequence[str], *, cwd) -> subprocess.CompletedProcess[str]:
        return _completed(argv, returncode=1, stdout="forbidden term hit at src/x.py")

    _install_run(monkeypatch, fake_run)
    problems = gates_module._terminology_gate(GateTarget(root=tmp_path))
    assert any("check refused" in problem for problem in problems)


def test_terminology_gate_is_clean_when_the_check_passes(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _seed_file(tmp_path, gates_module._TERMINOLOGY_FILE)
    _install_run(monkeypatch, lambda argv, *, cwd: _completed(argv))
    assert gates_module._terminology_gate(GateTarget(root=tmp_path)) == []


def test_terminology_gate_is_skipped_without_the_check(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _install_run(monkeypatch, lambda argv, *, cwd: _completed(argv))
    assert gates_module._terminology_gate(GateTarget(root=tmp_path)) == [], "a repo without the node is not checked"


def test_architectural_gate_refuses_on_a_layer_violation(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _seed_file(tmp_path, gates_module._ARCHITECTURAL_CHECK)

    def fake_run(argv: Sequence[str], *, cwd) -> subprocess.CompletedProcess[str]:
        return _completed(argv, returncode=1, stdout="kernel imports specify_cli")

    _install_run(monkeypatch, fake_run)
    problems = gates_module._architectural_gate(GateTarget(root=tmp_path))
    assert any("check refused" in problem for problem in problems)


def test_architectural_gate_is_clean_when_the_check_passes(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _seed_file(tmp_path, gates_module._ARCHITECTURAL_CHECK)
    _install_run(monkeypatch, lambda argv, *, cwd: _completed(argv))
    assert gates_module._architectural_gate(GateTarget(root=tmp_path)) == []


def test_wrapped_checks_use_the_existing_entry_points(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _seed_file(tmp_path, gates_module._TERMINOLOGY_FILE)
    _seed_file(tmp_path, gates_module._ARCHITECTURAL_CHECK)
    seen: list[list[str]] = []

    def fake_run(argv: Sequence[str], *, cwd) -> subprocess.CompletedProcess[str]:
        seen.append(list(argv))
        return _completed(argv)

    _install_run(monkeypatch, fake_run)
    gates_module._terminology_gate(GateTarget(root=tmp_path))
    gates_module._architectural_gate(GateTarget(root=tmp_path))
    argv_text = "\n".join(" ".join(argv) for argv in seen)
    assert "tests/architectural/test_no_legacy_terminology.py" in argv_text
    assert "tests/architectural/test_layer_rules.py" in argv_text
    assert f"{sys.executable} -m pytest" in argv_text


# ---------------------------------------------------------------------------
# T016 -- new gates: protected branch and engine guard failures
# ---------------------------------------------------------------------------


def test_protected_branch_gate_refuses_on_main(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _seed_protection(tmp_path, ["main"])
    monkeypatch.setattr(gates_module, "_current_branch", lambda _root: "main")
    assert gates_module._protected_branch_gate(GateTarget(root=tmp_path))


def test_protected_branch_gate_refuses_on_master(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _seed_protection(tmp_path, ["master"])
    monkeypatch.setattr(gates_module, "_current_branch", lambda _root: "master")
    assert gates_module._protected_branch_gate(GateTarget(root=tmp_path))


def test_protected_branch_gate_is_clean_on_a_topic_branch(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _seed_protection(tmp_path, ["main"])
    monkeypatch.setattr(gates_module, "_current_branch", lambda _root: CLEAN_BRANCH)
    assert gates_module._protected_branch_gate(GateTarget(root=tmp_path)) == []


def test_protected_branch_gate_is_skipped_without_config(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(gates_module, "_current_branch", lambda _root: "main")
    assert gates_module._protected_branch_gate(GateTarget(root=tmp_path)) == [], "protection is opt-in"


def test_protected_branch_gate_fails_loudly_when_git_is_unavailable(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _seed_protection(tmp_path, ["main"])

    def fake_run(argv: Sequence[str], *, cwd):
        raise ToolUnavailableError("command 'git' not found")

    _install_run(monkeypatch, fake_run)
    problems = gates_module._protected_branch_gate(GateTarget(root=tmp_path))
    assert problems
    assert any("cannot determine the current branch" in problem for problem in problems)


def test_repo_gate_refuses_on_a_failing_command(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _seed_repo_gate(tmp_path, "make check")

    def fake_run(argv: Sequence[str], *, cwd) -> subprocess.CompletedProcess[str]:
        return _completed(argv, returncode=1, stdout="checks failed")

    _install_run(monkeypatch, fake_run)
    problems = gates_module._repo_gate(GateTarget(root=tmp_path))
    assert any("repo gate refused" in problem for problem in problems)


def test_repo_gate_is_clean_when_the_command_passes(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _seed_repo_gate(tmp_path, "make check")
    _install_run(monkeypatch, lambda argv, *, cwd: _completed(argv))
    assert gates_module._repo_gate(GateTarget(root=tmp_path)) == []


def test_repo_gate_is_skipped_without_config(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _install_run(monkeypatch, lambda argv, *, cwd: _completed(argv))
    assert gates_module._repo_gate(GateTarget(root=tmp_path)) == []


def test_engine_guard_gate_is_skipped_without_a_mission(tmp_path) -> None:
    assert gates_module._engine_guard_gate(GateTarget(root=tmp_path, mission=None)) == []


def test_engine_guard_gate_refuses_on_guard_failures(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(
        gates_module,
        "_next_decision",
        lambda _root, _mission: {"guard_failures": ["protected branch main"]},
    )
    problems = gates_module._engine_guard_gate(GateTarget(root=tmp_path, mission="demo"))
    assert any("guard failures" in problem for problem in problems)


def test_engine_guard_gate_is_clean_without_guard_failures(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(gates_module, "_next_decision", lambda _root, _mission: {"guard_failures": []})
    assert gates_module._engine_guard_gate(GateTarget(root=tmp_path, mission="demo")) == []


def test_engine_guard_gate_fails_loudly_when_the_query_fails(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    def boom(_root, _mission):
        raise gates_module.EngineQueryError("next --json emitted no usable JSON")

    monkeypatch.setattr(gates_module, "_next_decision", boom)
    problems = gates_module._engine_guard_gate(GateTarget(root=tmp_path, mission="demo"))
    assert any("engine guard query failed" in problem for problem in problems)


def test_next_decision_parses_the_engine_json(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    payload = {"guard_failures": ["x"], "kind": "blocked"}

    def fake_run(argv: Sequence[str], *, cwd) -> subprocess.CompletedProcess[str]:
        return _completed(argv, stdout=json.dumps(payload))

    _install_run(monkeypatch, fake_run)
    monkeypatch.setattr(gates_module, "_engine_working_root", lambda root: root)
    assert gates_module._next_decision(tmp_path, "demo") == payload


def test_next_decision_refuses_on_non_json_output(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _install_run(monkeypatch, lambda argv, *, cwd: _completed(argv, stdout="not json"))
    monkeypatch.setattr(gates_module, "_engine_working_root", lambda root: root)
    with pytest.raises(gates_module.EngineQueryError, match="no usable JSON"):
        gates_module._next_decision(tmp_path, "demo")


# ---------------------------------------------------------------------------
# T018 -- verification is itself falsifiable
# ---------------------------------------------------------------------------

#: Gate id -> the planted-violation test that proves it can refuse.
PLANTED_VIOLATIONS: dict[str, Callable[..., None]] = {
    "protected-branch": test_protected_branch_gate_refuses_on_main,
    "engine-guard": test_engine_guard_gate_refuses_on_guard_failures,
    "repo-gate": test_repo_gate_refuses_on_a_failing_command,
    "ruff": test_ruff_gate_refuses_on_a_lint_violation,
    "terminology": test_terminology_gate_refuses_on_a_planted_term,
    "architectural": test_architectural_gate_refuses_on_a_layer_violation,
}


def test_every_registered_gate_has_a_planted_violation() -> None:
    assert unverified_gate_ids(verified=PLANTED_VIOLATIONS) == ()


def test_a_gate_without_a_failing_case_is_unverified() -> None:
    unverified = unverified_gate_ids(verified=["protected-branch"])
    assert "engine-guard" in unverified
    assert "protected-branch" not in unverified


def test_unverified_is_empty_when_all_gates_are_covered() -> None:
    assert unverified_gate_ids(verified=[gate.id for gate in gates_module.GATES]) == ()


# ---------------------------------------------------------------------------
# T017 -- the ``steer check`` handler refuses with a non-zero exit
# ---------------------------------------------------------------------------


def test_steer_check_json_reports_clean(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(gates_module, "_repository_root", lambda: tmp_path)
    monkeypatch.setattr(gates_module, "run_gates", lambda _target: [])
    result = CliRunner().invoke(steer_module.app, ["check", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"clean": True, "problems": []}


def test_steer_check_refuses_with_a_non_zero_exit(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(gates_module, "_repository_root", lambda: tmp_path)
    monkeypatch.setattr(gates_module, "run_gates", lambda _target: ["ruff: boom"])
    result = CliRunner().invoke(steer_module.app, ["check", "--json"])
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["clean"] is False
    assert payload["problems"] == ["ruff: boom"]


def test_steer_check_prints_problems_for_humans(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(gates_module, "_repository_root", lambda: tmp_path)
    monkeypatch.setattr(gates_module, "run_gates", lambda _target: ["ruff: boom"])
    result = CliRunner().invoke(steer_module.app, ["check"])
    assert result.exit_code == 1
    assert "ruff: boom" in result.stdout
