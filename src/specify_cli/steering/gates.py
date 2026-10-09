"""The binding machine gates (IC-04 / FR-004, NFR-005, SC-003).

``spec-kitty steer check`` runs a small, deterministic set of checks the agent
treats as binding: a refusal stops the loop, the agent fixes the cause and
re-runs. This is the runtime mirror of ``steer kernel``'s third protocol rule
("invariants are machine gates").

The registry **reuses the repository's existing checks through their existing
entry points** rather than copying their logic:

* *ruff* -- the ``ruff`` CLI (``check`` + ``format --check``), the same
  command CI runs;
* *terminology* -- the canonical architectural node
  ``tests/architectural/test_no_legacy_terminology.py::test_forbidden_term_does_not_appear``;
* *architectural layer rules* -- ``tests/architectural/test_layer_rules.py``.

It adds the two invariants no existing check owns:

* *protected branch* -- refuse to work when the current branch is ``main`` or
  ``master``;
* *engine guard* -- refuse when ``spec-kitty next --mission <handle> --json``
  reports ``guard_failures``.

Every wrapper is thin and **fails loudly**: a missing or misbehaving tool
becomes a refusal, never a silent pass (the mission's central risk). A gate
with no planted-violation case is reported by :func:`unverified_gate_ids`
(NFR-005).
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from pathlib import Path

import typer

#: Branches on which a gate refuses to let work proceed.
_PROTECTED_BRANCHES = frozenset({"main", "master"})

#: The lint/format tool, invoked as the ``ruff`` CLI (the CI entry point).
_RUFF = "ruff"

#: The engine entry point whose JSON decision carries ``guard_failures``.
_SPEC_KITTY = "spec-kitty"

#: The canonical terminology check (a fast, narrow architectural node).
_TERMINOLOGY_CHECK = "tests/architectural/test_no_legacy_terminology.py::test_forbidden_term_does_not_appear"

#: The canonical architectural layer-rule check.
_ARCHITECTURAL_CHECK = "tests/architectural/test_layer_rules.py"

#: How many output lines a single refusal echoes back before summarising.
_MAX_PROBLEM_LINES = 5

#: Ceiling on one wrapped subprocess, so a hung check cannot stall the loop.
_TOOL_TIMEOUT_SECONDS = 600


class ToolUnavailableError(RuntimeError):
    """A gate's underlying tool could not be executed at all."""


class EngineQueryError(RuntimeError):
    """``spec-kitty next --json`` failed to produce a usable decision."""


@dataclass(frozen=True)
class GateTarget:
    """What the gates run against: a repository root and an optional Mission."""

    root: Path
    mission: str | None = None


@dataclass(frozen=True)
class Gate:
    """One deterministic check. ``check`` returns problems; empty means clean."""

    id: str
    check: Callable[[GateTarget], list[str]]
    binding: bool = True


def _run(argv: Sequence[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a fixed argv (no shell) in ``cwd``; raise loudly when it is absent."""
    try:
        return subprocess.run(
            list(argv),
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=_TOOL_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise ToolUnavailableError(f"command {argv[0]!r} not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise ToolUnavailableError(f"command {argv[0]!r} exceeded {_TOOL_TIMEOUT_SECONDS}s") from exc


def _first_lines(text: str, limit: int = _MAX_PROBLEM_LINES) -> list[str]:
    """Return the first non-blank ``limit`` lines, then a count of the rest."""
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) <= limit:
        return lines
    return [*lines[:limit], f"... ({len(lines) - limit} more line(s))"]


def _command_gate(argv: Sequence[str], cwd: Path, action: str) -> list[str]:
    """Run an external check; refusal or unavailability both yield problems."""
    try:
        result = _run(argv, cwd=cwd)
    except ToolUnavailableError as exc:
        return [f"{action} unavailable; cannot verify: {exc}"]
    if result.returncode == 0:
        return []
    output = result.stdout.strip() or result.stderr.strip()
    return [f"{action} refused:", *(f"  {line}" for line in _first_lines(output))]


def _current_branch(root: Path) -> str:
    """Return the checked-out branch name, or ``""`` on a detached HEAD."""
    result = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root)
    if result.returncode != 0:
        raise EngineQueryError(_first_lines(result.stderr or "git rev-parse failed", 1)[0])
    return result.stdout.strip()


def _engine_working_root(root: Path) -> Path:
    """Resolve the main repository root -- ``next`` refuses inside a worktree."""
    try:
        result = _run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=root,
        )
    except ToolUnavailableError:
        return root
    if result.returncode != 0 or not result.stdout.strip():
        return root
    common = Path(result.stdout.strip())
    return common.parent if common.name == ".git" else root


def _next_decision(root: Path, mission: str) -> dict[str, object]:
    """Query the engine for the Mission's current decision (JSON)."""
    result = _run(
        [_SPEC_KITTY, "next", "--mission", mission, "--json"],
        cwd=_engine_working_root(root),
    )
    if result.returncode != 0:
        tail = _first_lines(result.stderr or result.stdout or "no output")
        raise EngineQueryError("; ".join(tail) or "non-zero exit")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise EngineQueryError(f"next --json emitted no usable JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise EngineQueryError("next --json emitted a non-object payload")
    return payload


def _protected_branch_gate(target: GateTarget) -> list[str]:
    """Refuse to work on ``main`` or ``master`` (validated spike rule R1)."""
    try:
        branch = _current_branch(target.root)
    except ToolUnavailableError as exc:
        return [f"cannot determine the current branch; cannot verify: {exc}"]
    if branch in _PROTECTED_BRANCHES:
        return [f"refusing to work on protected branch {branch!r}"]
    return []


def _engine_guard_gate(target: GateTarget) -> list[str]:
    """Refuse when the engine reports guard failures for the Mission."""
    if target.mission is None:
        return ["no Mission handle provided; cannot query the engine guards"]
    try:
        decision = _next_decision(target.root, target.mission)
    except (ToolUnavailableError, EngineQueryError) as exc:
        return [f"engine guard query failed; cannot verify: {exc}"]
    failures = decision.get("guard_failures")
    if failures:
        return [f"engine reports guard failures: {failures}"]
    return []


def _ruff_gate(target: GateTarget) -> list[str]:
    """Reuse the CI ruff entry points: ``check`` and ``format --check``."""
    problems = _command_gate([_RUFF, "check", "."], target.root, "lint")
    problems += _command_gate([_RUFF, "format", "--check", "."], target.root, "format check")
    return problems


def _pytest_argv(node: str) -> list[str]:
    """The existing entry point for an architectural pytest node."""
    return [sys.executable, "-m", "pytest", node, "-q", "-p", "no:cacheprovider"]


def _terminology_gate(target: GateTarget) -> list[str]:
    """Reuse the canonical forbidden-terminology architectural check."""
    return _command_gate(_pytest_argv(_TERMINOLOGY_CHECK), target.root, "check")


def _architectural_gate(target: GateTarget) -> list[str]:
    """Reuse the canonical architectural layer-rule check."""
    return _command_gate(_pytest_argv(_ARCHITECTURAL_CHECK), target.root, "check")


#: The registry. Order is the order problems are reported in.
GATES: tuple[Gate, ...] = (
    Gate("protected-branch", _protected_branch_gate),
    Gate("engine-guard", _engine_guard_gate),
    Gate("ruff", _ruff_gate),
    Gate("terminology", _terminology_gate),
    Gate("architectural", _architectural_gate),
)


def run_gates(target: GateTarget) -> list[str]:
    """Run every registered gate and aggregate the problems, prefixed by id."""
    problems: list[str] = []
    for gate in GATES:
        for message in gate.check(target):
            problems.append(f"{gate.id}: {message}")
    return problems


def unverified_gate_ids(*, verified: Collection[str]) -> tuple[str, ...]:
    """Registered gate ids with no planted-violation case (NFR-005)."""
    known = set(verified)
    return tuple(sorted(gate.id for gate in GATES if gate.id not in known))


def _repository_root() -> Path:
    """The working tree root, or the process cwd when git cannot answer."""
    try:
        result = _run(["git", "rev-parse", "--show-toplevel"], cwd=Path.cwd())
    except ToolUnavailableError:
        return Path.cwd()
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip())
    return Path.cwd()


def run(mission: str | None, *, json_output: bool = False) -> None:
    """``steer check`` handler: run the gates, report, exit non-zero on refusal."""
    problems = run_gates(GateTarget(root=_repository_root(), mission=mission))
    clean = not problems
    if json_output:
        print(json.dumps({"clean": clean, "problems": problems}))
    elif clean:
        print("steer check: clean")
    else:
        for problem in problems:
            print(problem)
        print(f"steer check: {len(problems)} problem(s); refusing")
    if problems:
        raise typer.Exit(code=1)


__all__ = [
    "GATES",
    "EngineQueryError",
    "Gate",
    "GateTarget",
    "ToolUnavailableError",
    "run",
    "run_gates",
    "unverified_gate_ids",
]
