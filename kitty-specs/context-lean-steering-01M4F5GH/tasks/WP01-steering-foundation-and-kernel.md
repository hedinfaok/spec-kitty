---
work_package_id: WP01
title: Steering foundation and the standing kernel
dependencies: []
requirement_refs:
- FR-001
- NFR-001
- NFR-002
- NFR-004
- C-001
- C-003
planning_base_branch: feat/context-lean-steering
merge_target_branch: feat/context-lean-steering
branch_strategy: Planning artifacts for this mission were generated on feat/context-lean-steering. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/context-lean-steering unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
history: []
agent_profile: python-pedro
authoritative_surface: src/specify_cli/steering/
create_intent:
- src/specify_cli/steering/__init__.py
- src/specify_cli/steering/kernel.py
- src/specify_cli/cli/commands/steer.py
- tests/specify_cli/steering/__init__.py
- tests/specify_cli/steering/test_kernel.py
execution_mode: code_change
owned_files:
- src/specify_cli/steering/__init__.py
- src/specify_cli/steering/kernel.py
- src/specify_cli/cli/commands/steer.py
- tests/specify_cli/steering/__init__.py
- tests/specify_cli/steering/test_kernel.py
role: implementer
tags: []
tracker_refs: []
---

# WP01 — Steering foundation and the standing kernel

## ⚡ Do This First: Load Agent Profile

Use the `/ad-hoc-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

If no profile is specified, run `spec-kitty agent profile list` and select the best match for this work package's `task_type` and `authoritative_surface`.

---

## Objective

Create the `specify_cli.steering` package and the `spec-kitty steer` command group, then ship the **standing kernel**: the small, byte-stable instruction set that states the protocol (state is authoritative, doctrine is fetched, gates are binding) plus the short judgment residue that no gate can check. The kernel is the only standing text the harness injects per turn; it must stay ≤ 1024 bytes and be stable across calls.

## Context

- Spec: `FR-001`, `NFR-001`, and C-003 (Mission terminology). Plan: IC-01.
- The kernel is a constant artifact with **no mission-specific state**. Everything mission-specific belongs to the capsule (WP03).
- The `steer` command group is the single, additive CLI surface (Q1 = A). It must not modify any existing command. Later WPs add their subcommands; to keep `owned_files` non-overlapping, this WP owns `steer.py` and wires **every** subcommand with a **lazy import inside the handler**, so the module imports cleanly before the other modules exist. A subcommand whose module is absent fails only when invoked.

## Subtask T001: Create the `steering` package and the `steer` command group skeleton

**Purpose**: establish the package and the additive CLI surface.

**Steps**:
1. Create `src/specify_cli/steering/__init__.py` (empty, or with a short docstring; no heavy imports).
2. Create `src/specify_cli/cli/commands/steer.py` exposing a Typer `app` (follow the existing command-module pattern; register it in the CLI like the sibling command modules — a single additive registration).
3. Declare subcommands `kernel`, `capsule --mission`, `fetch <selector>`, `check --mission`, `measure --mission`, `loop --mission --model --turns`. The `kernel` handler is fully wired; every other handler performs a lazy `from specify_cli.steering import <module>` inside the function body and delegates.
4. Do not import the not-yet-existing modules at module import time.

**Files**: `src/specify_cli/steering/__init__.py` (new), `src/specify_cli/cli/commands/steer.py` (new).

**Validation**: `spec-kitty steer --help` lists the subcommands; `spec-kitty --help` is unchanged for existing commands.

## Subtask T002: Implement the standing kernel artifact

**Purpose**: provide the kernel text as a single canonical constant.

**Steps**:
1. In `src/specify_cli/steering/kernel.py`, define the kernel text. Content (adapt the spike's `research-outputs/lean-steering-spike/kernel.md`, which is the validated artifact): the three protocol rules — (1) state is authoritative and lives in the Mission; never guess the step, WP, or branch; ask `steer capsule`; (2) doctrine is fetched, not inlined; fetch a pointer before "when doing X"; (3) invariants are machine gates; `steer check` is binding — plus the judgment residue (prefer durable fixes; read the charter before changing code; write for the next maintainer).
2. Expose `KERNEL_TEXT: str` and a `render_kernel() -> str` returning it unchanged.
3. Keep it ≤ 1024 bytes; do not add mission-specific content.

**Files**: `src/specify_cli/steering/kernel.py` (new, ~40 lines).

**Validation**: `len(render_kernel().encode("utf-8")) <= 1024`.

## Subtask T003: Wire `steer kernel`

**Purpose**: expose the kernel on the CLI.

**Steps**:
1. Implement the `kernel` handler in `steer.py`: print `render_kernel()`; with `--json`, print `{"bytes": <int>, "text": "<text>"}`.
**Files**: `src/specify_cli/cli/commands/steer.py` (edit).
**Validation**: `spec-kitty steer kernel` prints the kernel; `--json` parses and reports the byte count.

## Subtask T004: Kernel invariants test

**Purpose**: pin the invariants with non-vacuous tests.

**Steps**:
1. In `tests/specify_cli/steering/test_kernel.py`, assert: byte length ≤ 1024; two calls are byte-identical (stability); the text contains the three protocol markers and no mission-specific token (e.g. no mission slug).
2. Ensure a do-nothing change cannot pass: assert the size bound is actually near the limit (e.g. `> 200`), so an empty kernel fails.

**Files**: `tests/specify_cli/steering/test_kernel.py` (new, ~40 lines), `tests/specify_cli/steering/__init__.py` (new, empty).
**Validation**: `python -m pytest tests/specify_cli/steering/test_kernel.py -q` passes; the size assertion is two-sided.

## Branch Strategy

Planning artifacts were generated on `feat/context-lean-steering`. Execution worktrees are allocated per computed lane from `lanes.json`; completed changes must merge back into `feat/context-lean-steering`.

## Definition of Done

- `spec-kitty steer --help` works; `spec-kitty steer kernel` prints the kernel.
- The kernel is ≤ 1024 bytes and byte-stable across calls.
- No existing CLI command or contract changed (NFR-002, C-001).
- Terminology is Mission, never "feature" (C-003).
- `python -m pytest tests/specify_cli/steering/test_kernel.py -q` passes.
- Subtask completion recorded via `spec-kitty agent tasks mark-status <Txxx> --status done`.

Implement with: `spec-kitty agent action implement WP01 --agent claude`

## Risks

- **Kernel regrowth**: nothing else may be added to the kernel; subsequent WPs must not append to it. Reviewers should reject any growth.
- **CLI registration**: follow the existing command-module registration pattern exactly; a wrong registration can break unrelated commands.

## Reviewer Guidance

- Confirm the kernel states all three protocol rules and stays ≤ 1024 bytes.
- Confirm `steer.py` imports no not-yet-existing module at import time (all later subcommands lazy-import).
- Confirm no existing command changed.
