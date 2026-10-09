#!/usr/bin/env python3
"""Lean-steering spike: a tiny kernel + a bounded per-step capsule over the engine.

This prototype reuses the existing ``spec-kitty`` CLI (``next``, ``charter context``) as
the engine and never forks it. It changes only *what text reaches the model*: instead of
a standing corpus (~101 KB every turn) plus an action payload (81-95 KB on first load),
the model receives a static kernel (``kernel.md``) and a ~1-2 KB per-step capsule.

Subcommands:
  kernel                 print the standing kernel (the only per-turn text)
  capsule --mission M    print the per-step capsule for mission M
  fetch SELECTOR         fetch one doctrine body on demand (engine reuse)
  check --mission M      run the binding machine gates
  measure --mission M    print the size comparison against today's flow

Run ``python3 sk.py --help``.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KERNEL_PATH = HERE / "kernel.md"
REPO_ROOT = HERE.parent.parent  # research-outputs/<this-dir>/ -> repository root

# Historical measurements from mission analyze-prompt-context-load-01M3F4BV (#5005),
# research.md section 9.2: the engine's rendered action payload for `implement`.
ENGINE_PAYLOAD_BOOTSTRAP_BYTES = 95_139
ENGINE_PAYLOAD_COMPACT_BYTES = 12_614

# Illustrative action -> doctrine pointers. Production wiring should derive these from
# the engine's DRG / the work package's agent profile, not a static map; the spike shows
# the *shape* and the fetch workflow, not the final mapping.
POINTERS: dict[str, list[tuple[str, str]]] = {
    "implement": [
        ("directive:DIRECTIVE_044", "when choosing a template/command or tempted to improvise a substitute"),
        ("directive:DIRECTIVE_030", "before declaring the change done (test + typecheck gate)"),
        ("directive:DIRECTIVE_025", "when the change touches more than the target file"),
        ("directive:DIRECTIVE_031", "when designing an interface or a seam"),
    ],
    "review": [
        ("directive:DIRECTIVE_010", "when checking the diff against the spec"),
        ("directive:DIRECTIVE_032", "when the diff renames or redefines terms"),
        ("directive:DIRECTIVE_036", "when judging test quality"),
    ],
}
DEFAULT_POINTERS = [("directive:DIRECTIVE_044", "when tempted to improvise a substitute")]

AUTHORITY_PATHS = ["docs/context/ (canonical terminology)", "docs/adr/ (architectural intent)"]


def run_cmd(argv: list[str]) -> str:
    """Run a fixed argv (no shell, no user input) and return stdout."""
    completed = subprocess.run(argv, cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    return completed.stdout


def run_cli(args: list[str]) -> str:
    """Call the spec-kitty engine."""
    return run_cmd(["spec-kitty", *args])


def load_kernel() -> str:
    """Return the standing kernel text."""
    return KERNEL_PATH.read_text(encoding="utf-8")


def next_decision(mission: str) -> dict:
    """Ask the engine for the current step (the authoritative decision)."""
    out = run_cli(["next", "--mission", mission, "--json"])
    try:
        parsed = json.loads(out)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def parse_frontmatter(text: str) -> dict[str, list[str] | str]:
    """Minimal YAML frontmatter reader for the fields the capsule needs (no dependency)."""
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


def wp_facts(mission: str, wp_id: str | None) -> dict[str, list[str] | str]:
    """Read the work package's own frontmatter (title, owned files, subtasks, refs)."""
    if not wp_id:
        return {}
    tasks_dir = REPO_ROOT / "kitty-specs" / mission / "tasks"
    matches = sorted(tasks_dir.glob(f"{wp_id}-*.md")) if tasks_dir.is_dir() else []
    if not matches:
        return {}
    return parse_frontmatter(matches[0].read_text(encoding="utf-8"))


def _joined(facts: dict[str, list[str] | str], key: str) -> str:
    value = facts.get(key)
    if isinstance(value, list):
        return ", ".join(value)
    text = (value or "").strip()
    return "" if text in {"[]", "null"} else text


def render_capsule(mission: str) -> str:
    """Render the bounded per-step capsule from engine state + WP facts."""
    decision = next_decision(mission)
    step = decision.get("preview_step") or decision.get("mission_state") or "unknown"
    wp_id = decision.get("wp_id")
    progress = decision.get("progress") or {}
    facts = wp_facts(mission, wp_id)

    lines = [f"# CAPSULE — {mission}", f"step: {step}", f"mission_type: {decision.get('mission_type', '?')}"]
    if wp_id:
        lines.append(f"wp: {wp_id} — {facts.get('title', '(title unavailable)')}")
    lines.append(f"progress: {progress.get('done_wps', 0)}/{progress.get('total_wps', '?')} done, {progress.get('planned_wps', 0)} planned")
    if _joined(facts, "owned_files"):
        lines.append("owned_files: " + _joined(facts, "owned_files"))
    if _joined(facts, "subtasks"):
        lines.append("subtasks: " + _joined(facts, "subtasks"))
    if _joined(facts, "requirement_refs"):
        lines.append("requirement_refs: " + _joined(facts, "requirement_refs"))
    if _joined(facts, "dependencies"):
        lines.append("dependencies: " + _joined(facts, "dependencies"))

    lines.append("")
    lines.append("## Fetch when needed (do not request all of it)")
    for selector, when in POINTERS.get(step, DEFAULT_POINTERS):
        lines.append(f"- `spec-kitty charter context --include {selector}` — {when}")
    for path in AUTHORITY_PATHS:
        lines.append(f"- {path}")

    lines.append("")
    lines.append("## Binding gate")
    lines.append(f"- run `python3 sk.py check --mission {mission}`; a refusal is binding — fix its cause")
    return "\n".join(lines) + "\n"


def run_gates(mission: str) -> list[str]:
    """The binding machine gates. Each is deterministic and costs the model 0 tokens."""
    problems: list[str] = []
    branch = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"]).strip()
    if branch in {"main", "master"}:
        problems.append(f"G1: refusing to work on protected branch {branch!r}")
    decision = next_decision(mission)
    guard_failures = decision.get("guard_failures") or []
    if guard_failures:
        problems.append(f"G2: engine reports guard failures: {guard_failures}")
    return problems


def _tokens(text: str) -> int:
    return round(len(text.encode("utf-8")) / 4)


def measure(mission: str) -> None:
    """Print what enters the model's context today versus under the spike."""
    kernel = load_kernel()
    capsule = render_capsule(mission)
    standing = 0
    for relative in ("AGENTS.md", ".kittify/overrides/AGENTS.md"):
        path = REPO_ROOT / relative
        if path.exists():
            standing += path.stat().st_size

    print("== Per turn (standing steering text) ==")
    print(f"{'today: standing corpus':32s} {standing:8d} bytes  ~{standing // 4:6d} tokens")
    print(f"{'spike: kernel':32s} {len(kernel.encode()):8d} bytes  ~{_tokens(kernel):6d} tokens")
    print(f"{'reduction':32s} {'':8s}          {standing / max(len(kernel.encode()), 1):5.1f}x")

    print("\n== Per step (action payload) ==")
    print(f"{'today: payload (first load)':32s} {ENGINE_PAYLOAD_BOOTSTRAP_BYTES:8d} bytes  ~{ENGINE_PAYLOAD_BOOTSTRAP_BYTES // 4:6d} tokens  (#5005)")
    print(f"{'today: payload (compact)':32s} {ENGINE_PAYLOAD_COMPACT_BYTES:8d} bytes  ~{ENGINE_PAYLOAD_COMPACT_BYTES // 4:6d} tokens  (#5005)")
    print(f"{'spike: capsule':32s} {len(capsule.encode()):8d} bytes  ~{_tokens(capsule):6d} tokens")
    print(f"{'reduction vs first-load':32s} {'':8s}          {ENGINE_PAYLOAD_BOOTSTRAP_BYTES / max(len(capsule.encode()), 1):5.1f}x")

    print("\n== Capsule preview ==")
    print(capsule)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Lean-steering spike over the spec-kitty engine.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("kernel", help="print the standing kernel")

    capsule = sub.add_parser("capsule", help="print the per-step capsule")
    capsule.add_argument("--mission", required=True)

    fetch = sub.add_parser("fetch", help="fetch one doctrine body on demand")
    fetch.add_argument("selector")

    check = sub.add_parser("check", help="run the binding machine gates")
    check.add_argument("--mission", required=True)

    measure_cmd = sub.add_parser("measure", help="print the size comparison")
    measure_cmd.add_argument("--mission", required=True)

    args = parser.parse_args(argv)
    if args.command == "kernel":
        print(load_kernel())
    elif args.command == "capsule":
        print(render_capsule(args.mission))
    elif args.command == "fetch":
        print(run_cli(["charter", "context", "--include", args.selector]))
    elif args.command == "check":
        problems = run_gates(args.mission)
        if problems:
            print("\n".join(problems))
            print(f"\ngate: {len(problems)} violation(s); refusing.")
            return 1
        print("gate: clean")
    elif args.command == "measure":
        measure(args.mission)
    return 0


if __name__ == "__main__":
    sys.exit(main())
