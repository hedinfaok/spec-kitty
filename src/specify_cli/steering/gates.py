"""The binding machine gates (IC-04 / FR-004, NFR-005, SC-003).

``spec-kitty steer check`` runs a small, deterministic set of checks the agent
treats as binding: a refusal stops the loop, the agent fixes the cause and
re-runs. This is the runtime mirror of ``steer kernel``'s third protocol rule
("invariants are machine gates").

**Portability (this is the point).** A gate is only *applicable* when the
repository actually has the thing it checks. A repo that does not use ``ruff``,
or does not ship the canonical architectural nodes, is **skipped** — not
refused. A repo that *has* a check but whose tool is missing or misbehaving is
**refused** (fail loudly, never a silent pass). This lets ``steer`` run in any
repository, not only the spec-kitty checkout.

The registry:

* *protected branch* -- refuse on a branch the repo **explicitly** declares
  protected (``protection.protected_branches`` in ``.kittify/config.yaml``).
  Opt-in: when the key is absent the gate is skipped, because the authoritative
  protection is ``ProtectionPolicy`` at commit time, not this mirror.
* *engine guard* -- refuse when ``spec-kitty next --mission <handle> --json``
  reports ``guard_failures`` (skipped when no Mission handle is given).
* *repo gate* -- run the command the repo declares in
  ``steer.gate_command`` (``.kittify/config.yaml``), so any repository can plug
  in its own enforcement.
* *ruff* -- ``ruff check`` + ``ruff format --check``, the CI entry points,
  **only when the repo has a ruff config** (``ruff.toml`` / ``.ruff.toml`` /
  ``[tool.ruff]`` in ``pyproject.toml``).
* *terminology* / *architectural* -- the canonical spec-kitty architectural
  nodes, **only when the repo ships them** (``tests/architectural/...``).

Every wrapper is thin and fails loudly. A gate with no planted-violation case is
reported by :func:`unverified_gate_ids` (NFR-005).
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import typer

#: The lint/format tool, invoked as the ``ruff`` CLI (the CI entry point).
_RUFF = "ruff"

#: The engine entry point whose JSON decision carries ``guard_failures``.
_SPEC_KITTY = "spec-kitty"

#: The canonical terminology check (a fast, narrow architectural node).
_TERMINOLOGY_CHECK = "tests/architectural/test_no_legacy_terminology.py::test_forbidden_term_does_not_appear"
_TERMINOLOGY_FILE = "tests/architectural/test_no_legacy_terminology.py"

#: The canonical architectural layer-rule check.
_ARCHITECTURAL_CHECK = "tests/architectural/test_layer_rules.py"

#: The repository config that declares protected branches and a repo gate.
_CONFIG = ".kittify/config.yaml"

#: How many output lines a single refusal echoes back before summarising.
_MAX_PROBLEM_LINES = 5

#: Ceiling on one wrapped subprocess, so a hung check cannot stall the loop.
_TOOL_TIMEOUT_SECONDS = 600


class ToolUnavailableError(RuntimeError):
    """A gate's underlying tool could not be executed at all."""


class EngineQueryError(RuntimeError):
    """``spec-kitty next --json`` failed to produce a usable decision."""


class GateConfigError(RuntimeError):
    """``.kittify/config.yaml`` could not be read for gate configuration."""


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


def _load_config(root: Path) -> Mapping[str, object]:
    """Load ``.kittify/config.yaml``; ``{}`` when absent, loud on malformed YAML."""
    path = root / _CONFIG
    if not path.is_file():
        return {}
    try:
        from ruamel.yaml import YAML

        data = YAML(typ="safe").load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - any parse failure is a loud refusal
        raise GateConfigError(f"cannot read {_CONFIG}: {exc}") from exc
    return data if isinstance(data, Mapping) else {}


def _declared_protected_branches(root: Path) -> frozenset[str] | None:
    """The repo's explicitly declared protected branches, or ``None`` when unset."""
    config = _load_config(root)
    protection = config.get("protection")
    if not isinstance(protection, Mapping):
        return None
    branches = protection.get("protected_branches")
    if not isinstance(branches, Sequence) or isinstance(branches, (str, bytes)):
        return None
    return frozenset(str(name) for name in branches)


def _declared_gate_command(root: Path) -> list[str] | None:
    """The repo's declared gate command (``steer.gate_command``), or ``None``."""
    config = _load_config(root)
    steer = config.get("steer")
    if not isinstance(steer, Mapping):
        return None
    command = steer.get("gate_command")
    if isinstance(command, str) and command.strip():
        return shlex.split(command)
    if isinstance(command, Sequence) and not isinstance(command, (str, bytes)) and command:
        return [str(part) for part in command]
    return None


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
    """Refuse only on a branch the repo explicitly declares protected (opt-in)."""
    try:
        declared = _declared_protected_branches(target.root)
    except GateConfigError as exc:
        return [f"cannot read protection config; cannot verify: {exc}"]
    if declared is None:
        return []
    try:
        branch = _current_branch(target.root)
    except ToolUnavailableError as exc:
        return [f"cannot determine the current branch; cannot verify: {exc}"]
    if branch in declared:
        return [f"refusing to work on protected branch {branch!r}"]
    return []


def _engine_guard_gate(target: GateTarget) -> list[str]:
    """Refuse when the engine reports guard failures for the Mission."""
    if target.mission is None:
        return []
    try:
        decision = _next_decision(target.root, target.mission)
    except (ToolUnavailableError, EngineQueryError) as exc:
        return [f"engine guard query failed; cannot verify: {exc}"]
    failures = decision.get("guard_failures")
    if failures:
        return [f"engine reports guard failures: {failures}"]
    return []


def _repo_gate(target: GateTarget) -> list[str]:
    """Run the command the repository declares in ``steer.gate_command``."""
    try:
        command = _declared_gate_command(target.root)
    except GateConfigError as exc:
        return [f"cannot read gate config; cannot verify: {exc}"]
    if not command:
        return []
    return _command_gate(command, target.root, "repo gate")


def _has_ruff_config(root: Path) -> bool:
    """True when the repository uses ruff (so the ruff gate is applicable)."""
    if (root / "ruff.toml").is_file() or (root / ".ruff.toml").is_file():
        return True
    pyproject = root / "pyproject.toml"
    return pyproject.is_file() and "[tool.ruff" in pyproject.read_text(encoding="utf-8", errors="replace")


def _ruff_gate(target: GateTarget) -> list[str]:
    """Reuse the CI ruff entry points, only when the repo uses ruff."""
    if not _has_ruff_config(target.root):
        return []
    problems = _command_gate([_RUFF, "check", "."], target.root, "lint")
    problems += _command_gate([_RUFF, "format", "--check", "."], target.root, "format check")
    return problems


def _pytest_argv(node: str) -> list[str]:
    """The existing entry point for an architectural pytest node."""
    return [sys.executable, "-m", "pytest", node, "-q", "-p", "no:cacheprovider"]


def _terminology_gate(target: GateTarget) -> list[str]:
    """Reuse the canonical terminology node, only when the repo ships it."""
    if not (target.root / _TERMINOLOGY_FILE).is_file():
        return []
    return _command_gate(_pytest_argv(_TERMINOLOGY_CHECK), target.root, "check")


def _architectural_gate(target: GateTarget) -> list[str]:
    """Reuse the canonical architectural node, only when the repo ships it."""
    if not (target.root / _ARCHITECTURAL_CHECK).is_file():
        return []
    return _command_gate(_pytest_argv(_ARCHITECTURAL_CHECK), target.root, "check")


#: The registry. Order is the order problems are reported in.
GATES: tuple[Gate, ...] = (
    Gate("protected-branch", _protected_branch_gate),
    Gate("engine-guard", _engine_guard_gate),
    Gate("repo-gate", _repo_gate),
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
    "GateConfigError",
    "GateTarget",
    "ToolUnavailableError",
    "run",
    "run_gates",
    "unverified_gate_ids",
]
