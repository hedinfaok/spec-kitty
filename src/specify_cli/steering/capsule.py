"""Per-step steering capsule (WP03 / T009-T013).

The capsule is the *only* per-step steering text the harness delivers: it states
the current step, the work package it applies to, the work package facts the old
action payload carried, the doctrine **pointers** (never bodies) that apply, and
the binding gate command. It is derived from real engine state -- the read-only
``spec-kitty next --mission <handle>`` decision plus the work package frontmatter
-- and is bounded to :data:`CAPSULE_MAX_BYTES`.

Doctrine is a pointer, not a body (D-05, the recorded divergence): the capsule
emits ``{selector, when}`` pairs whose selectors are validated against the WP02
doctrine index (:mod:`specify_cli.steering.index`) and whose bodies the agent
fetches on demand with ``spec-kitty steer fetch <selector>``. Inlining the
``requires``-closure is 58-71 KB per action -- the bloat this Mission removes.

Adapted from the validated spike artifact
(``research-outputs/lean-steering-spike/sk.py``, ``render_capsule``).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import only for type checkers
    from specify_cli.steering.index import DoctrineIndex

#: Hard per-step budget (NFR-001); the rendered capsule never exceeds it.
CAPSULE_MAX_BYTES = 2048

#: Stable error code for a capsule that cannot be derived (missing/ambiguous handle).
STEER_CAPSULE_ERROR = "STEER_CAPSULE_ERROR"

#: The work-package frontmatter facts the old action payload carried (T013).
FACT_KEYS: tuple[str, ...] = ("owned_files", "subtasks", "requirement_refs", "dependencies")

#: Relative location of a Mission's work-package task files under the repo root.
_TASKS_RELATIVE = ("kitty-specs",)
_TASKS_SUBDIR = "tasks"

#: The binding gate text every capsule carries (the agent runs ``steer check``).
_GATE_TEMPLATE = "spec-kitty steer check --mission {mission}"

#: Default doctrine pointers, used for any step without a specific set. Each
#: entry is ``(selector, when)``; the selector is validated against the index and
#: the ``when`` is the short applicability clause (never a doctrine body).
DEFAULT_POINTERS: tuple[tuple[str, str], ...] = (
    ("directive:DIRECTIVE_044", "when choosing a template/command or tempted to improvise a substitute"),
    ("directive:DIRECTIVE_030", "before declaring the change done (test + typecheck gate)"),
)

#: Per-step doctrine pointers. Keyed by the step's *base* (the token before any
#: ``:reason`` suffix); an unknown step uses :data:`DEFAULT_POINTERS`.
STEP_POINTERS: dict[str, tuple[tuple[str, str], ...]] = {
    "implement": (
        ("directive:DIRECTIVE_044", "when choosing a template/command or tempted to improvise a substitute"),
        ("directive:DIRECTIVE_030", "before declaring the change done (test + typecheck gate)"),
        ("directive:DIRECTIVE_025", "when the change touches more than the target file"),
        ("directive:DIRECTIVE_031", "when designing an interface or a seam"),
    ),
    "review": (
        ("directive:DIRECTIVE_010", "when checking the diff against the spec"),
        ("directive:DIRECTIVE_032", "when the diff renames or redefines terms"),
        ("directive:DIRECTIVE_036", "when judging test quality"),
    ),
}


class SteerCapsuleError(RuntimeError):
    """Raised when a capsule cannot be derived from engine state.

    Carries :data:`STEER_CAPSULE_ERROR` as :attr:`code` so the CLI error surface
    is machine-checkable.
    """

    code = STEER_CAPSULE_ERROR

    def __init__(self, message: str) -> None:
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class Pointer:
    """One doctrine pointer: a validated selector plus its short applicability clause."""

    selector: str
    when: str


@dataclass(frozen=True, slots=True)
class Capsule:
    """The bounded per-step steering value object (T009)."""

    mission: str
    step: str
    wp: str
    facts: dict[str, tuple[str, ...]]
    pointers: tuple[Pointer, ...]
    gate: str

    def to_payload(self) -> dict[str, object]:
        """Return the JSON-persistable form of the capsule (the ``--json`` contract)."""
        return {
            "mission": self.mission,
            "step": self.step,
            "wp": self.wp,
            "facts": {key: list(values) for key, values in self.facts.items()},
            "pointers": [{"selector": pointer.selector, "when": pointer.when} for pointer in self.pointers],
            "gate": self.gate,
        }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render(capsule: Capsule) -> str:
    """Render the compact text form of *capsule* (mirrors the spike)."""
    lines = [f"# CAPSULE — {capsule.mission}", f"step: {capsule.step}"]
    if capsule.wp:
        lines.append(f"wp: {capsule.wp}")
    for key in FACT_KEYS:
        joined = ", ".join(capsule.facts.get(key, ()))
        if joined:
            lines.append(f"{key}: {joined}")
    lines.append("")
    lines.append("## Fetch when needed (do not request all of it)")
    for pointer in capsule.pointers:
        lines.append(f"- `spec-kitty steer fetch {pointer.selector}` — {pointer.when}")
    lines.append("")
    lines.append("## Binding gate")
    lines.append(f"- run `{capsule.gate}`; a refusal is binding — fix its cause")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Derivation from engine state
# ---------------------------------------------------------------------------


def next_decision(mission: str, repo_root: Path) -> dict[str, object]:
    """Ask the engine for the current step (the authoritative decision).

    This is the same read-only engine surface the ``spec-kitty next --mission
    <handle> --json`` query path calls: :func:`runtime.next.runtime_bridge.query_current_state`.
    The capsule never guesses the step or the work package.
    """
    from runtime.next.runtime_bridge import query_current_state

    payload = query_current_state(None, mission, repo_root).to_dict()
    return payload if isinstance(payload, dict) else {}


def parse_frontmatter(text: str) -> dict[str, list[str] | str]:
    """Minimal frontmatter reader for the fields the capsule needs (no YAML dependency)."""
    if not text.startswith("---"):
        return {}
    _, _, body = text.partition("---")
    front, _, _ = body.partition("---")
    facts: dict[str, list[str] | str] = {}
    current: str | None = None
    for line in front.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        if line.startswith("- "):
            value = facts.get(current) if current else None
            items = value if isinstance(value, list) else []
            items.append(line[2:].strip())
            if current:
                facts[current] = items
        elif ":" in line:
            key, _, raw = line.partition(":")
            current = key.strip()
            facts[current] = raw.strip()
    return facts


def wp_facts(repo_root: Path, mission: str, wp_id: str | None) -> dict[str, list[str] | str]:
    """Read the work package's own frontmatter (title, owned files, subtasks, refs)."""
    if not wp_id:
        return {}
    tasks_dir = repo_root.joinpath(*_TASKS_RELATIVE, mission, _TASKS_SUBDIR)
    matches = sorted(tasks_dir.glob(f"{wp_id}-*.md")) if tasks_dir.is_dir() else []
    if not matches:
        return {}
    return parse_frontmatter(matches[0].read_text(encoding="utf-8"))


def configured_pointers(step: str) -> tuple[tuple[str, str], ...]:
    """Return the ``(selector, when)`` pointers configured for *step* (default otherwise)."""
    base = step.split(":", 1)[0].strip().lower()
    return STEP_POINTERS.get(base, DEFAULT_POINTERS)


def build_pointers(step: str, repo_root: Path, *, index: DoctrineIndex | None = None) -> tuple[Pointer, ...]:
    """Resolve the step's configured pointers against the doctrine index (T011).

    Every emitted selector is validated against the WP02 index so the capsule
    never ships a dangling pointer. A selector the index cannot resolve is
    dropped; if none resolve, the step's first configured pointer is kept so the
    capsule still carries at least one steering reference. No doctrine body is
    read here -- resolution is a lookup, not a fetch.
    """
    configured = configured_pointers(step)
    active = index if index is not None else _safe_index(repo_root)
    if active is None:
        return tuple(Pointer(selector, when) for selector, when in configured)
    resolved: list[Pointer] = []
    for selector, when in configured:
        entry = active.resolve(selector)
        if entry is not None:
            resolved.append(Pointer(selector=entry.selector, when=entry.when.strip() or when))
    if resolved:
        return tuple(resolved)
    selector, when = configured[0]
    return (Pointer(selector=selector, when=when),)


def build_capsule(mission: str | None, *, repo_root: Path | None = None, decision: dict[str, object] | None = None) -> Capsule:
    """Derive the capsule from engine state plus the work package frontmatter (T010).

    *decision* may be injected (tests, or a caller that already holds the engine
    decision); otherwise the engine is asked directly. The mission handle is
    resolved to its canonical slug (the engine's own ``mission_slug``) so the
    capsule always names the Mission the same way the engine does.
    """
    root = repo_root if repo_root is not None else _default_repo_root()
    handle = _resolve_mission(mission, root)
    state = decision if decision is not None else next_decision(handle, root)
    canonical = _canonical_slug(state, handle)
    step = _step_of(state)
    wp_id = _wp_id_of(state)
    raw_facts = wp_facts(root, canonical, wp_id)
    facts = {key: _fact_values(raw_facts, key) for key in FACT_KEYS}
    return Capsule(
        mission=canonical,
        step=step,
        wp=_wp_label(wp_id, raw_facts.get("title")),
        facts=facts,
        pointers=build_pointers(step, root),
        gate=_GATE_TEMPLATE.format(mission=canonical),
    )


def run(mission: str | None, *, json_output: bool = False) -> None:
    """CLI entry point for ``spec-kitty steer capsule --mission <handle>`` (WP01 lazy import)."""
    import typer

    try:
        capsule = build_capsule(mission)
    except SteerCapsuleError as exc:
        _emit_error(exc, json_output=json_output)
        raise typer.Exit(code=1) from exc
    if json_output:
        print(json.dumps(capsule.to_payload(), indent=2))
        return
    print(render(capsule), end="")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _step_of(state: dict[str, object]) -> str:
    value = state.get("preview_step") or state.get("mission_state")
    return str(value) if value else "unknown"


def _wp_id_of(state: dict[str, object]) -> str | None:
    value = state.get("wp_id")
    return value if isinstance(value, str) and value else None


def _canonical_slug(state: dict[str, object], handle: str) -> str:
    value = state.get("mission_slug")
    return value if isinstance(value, str) and value else handle


def _wp_label(wp_id: str | None, title: object) -> str:
    if not wp_id:
        return ""
    clean_title = title.strip() if isinstance(title, str) else ""
    return f"{wp_id} — {clean_title}" if clean_title else wp_id


def _fact_values(raw_facts: dict[str, list[str] | str], key: str) -> tuple[str, ...]:
    value = raw_facts.get(key)
    if isinstance(value, list):
        return tuple(item for item in value if item)
    if isinstance(value, str) and value.strip() not in {"", "[]", "null"}:
        return (value.strip(),)
    return ()


def _resolve_mission(mission: str | None, repo_root: Path) -> str:
    if isinstance(mission, str) and mission.strip():
        return mission.strip()
    from specify_cli.context.mission_resolver import sole_mission_for_selection
    from specify_cli.core.paths import get_main_repo_root

    sole = sole_mission_for_selection(get_main_repo_root(repo_root))
    if sole is None:
        raise SteerCapsuleError(f"{STEER_CAPSULE_ERROR}: no --mission given and no sole mission to auto-select.")
    return sole


def _safe_index(repo_root: Path) -> DoctrineIndex | None:
    """Build the doctrine index for pointer validation, or ``None`` when it cannot.

    Pointer validation is a best-effort enrichment: a capsule must still render
    (with the configured pointers) in a repository whose index cannot be built,
    rather than fail the whole steering step.
    """
    from specify_cli.steering.index import build_index

    try:
        return build_index(repo_root)
    except Exception:  # best-effort fallback: a capsule must always render, even with no usable index.
        return None


def _default_repo_root() -> Path:
    from specify_cli.task_utils import find_repo_root

    return find_repo_root()


def _emit_error(exc: SteerCapsuleError, *, json_output: bool) -> None:
    message = str(exc)
    if json_output:
        print(json.dumps({"success": False, "error": STEER_CAPSULE_ERROR, "message": message}), file=sys.stderr)
    else:
        print(f"Error: {message}", file=sys.stderr)
