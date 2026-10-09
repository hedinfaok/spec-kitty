---
work_package_id: WP04
title: Machine gates
dependencies:
- WP01
requirement_refs:
- FR-004
- NFR-005
- SC-003
planning_base_branch: feat/context-lean-steering
merge_target_branch: feat/context-lean-steering
branch_strategy: Planning artifacts for this mission were generated on feat/context-lean-steering. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/context-lean-steering unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-context-lean-steering-01M4F5GH
base_commit: a3fb9bc17cb347f5709dc2a69819c2033f347d23
created_at: '2026-10-09T02:44:05.169420+00:00'
subtasks:
- T014
- T015
- T016
- T017
- T018
history: []
agent_profile: python-pedro
authoritative_surface: src/specify_cli/steering/
create_intent:
- src/specify_cli/steering/gates.py
- tests/specify_cli/steering/test_gates.py
execution_mode: code_change
owned_files:
- src/specify_cli/steering/gates.py
- tests/specify_cli/steering/test_gates.py
role: implementer
tags: []
tracker_refs: []
---

# WP04 — Machine gates

## ⚡ Do This First: Load Agent Profile

Use the `/ad-hoc-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## Objective

Provide the runtime **gate** surface the agent runs mid-loop: a set of deterministic checks that **refuse** on violation, reusing the repository's existing checks and adding the mission's own. A refusal is binding on the agent.

## Context

- Spec: `FR-004`, `NFR-005`, `SC-003`. Plan: IC-04; research D-02 (reuse + new surface).
- A gate that cannot fail is worthless: every gate ships a planted-violation test that fails without it (NFR-005).
- Validated pattern: `research-outputs/lean-steering-spike/lean_loop.py` (`run_gate`) and `research-outputs/context-format-experiment/check_policy.py`.

## Subtask T014: Gate registry

**Purpose**: one place to register and run gates.

**Steps**:
1. In `src/specify_cli/steering/gates.py`, define a `Gate` (id, check callable returning a list of problems, binding flag) and a registry.
2. `run_gates(target) -> list[str]` runs all gates and aggregates problems.
**Files**: `src/specify_cli/steering/gates.py` (new).
**Validation**: an empty registry returns clean; a registered failing gate returns its problem.

## Subtask T015: Adapt the existing checks [P]

**Purpose**: reuse what already exists rather than reinventing.

**Steps**:
1. Wrap the repository's existing checks where they can run cheaply and locally: formatting/lint (`ruff`), a terminology check, and the architectural layer rules — as gates, invoked through their existing entry points (do not copy their logic).
2. Keep each wrapper thin and defensive: if a check tool is unavailable, fail loudly rather than silently passing.
**Files**: `src/specify_cli/steering/gates.py` (edit).
**Validation**: each wrapped check returns a problem list; an unavailable tool produces a loud error, not a pass.

## Subtask T016: New gates (protected branch, engine guard failures) [P]

**Purpose**: the invariants that are not covered by an existing check.

**Steps**:
1. Add a protected-branch gate (refuse when the current branch is `main`/`master`).
2. Add an engine-guard gate: refuse when `spec-kitty next --mission <handle> --json` reports `guard_failures`.
**Files**: `src/specify_cli/steering/gates.py` (edit).
**Validation**: each new gate refuses on a planted condition.

## Subtask T017: Wire `steer check`

**Purpose**: expose the gates on the CLI.

**Steps**:
1. Implement the `check` handler (lazy import) → run gates; print problems; `--json` `{clean, problems}`; exit non-zero on any problem.
**Files**: no CLI edit (WP01 owns `steer.py`).
**Validation**: `spec-kitty steer check --mission <handle>` exits 0 when clean and non-zero with a violation, printing the failing gate ids.

## Subtask T018: Planted-violation tests per gate

**Purpose**: make every gate falsifiable (NFR-005).

**Steps**:
1. For each gate, a test that plants the violation and asserts refusal; and a clean case that asserts pass.
2. Assert a gate with no failing case is treated as unverified.
**Files**: `tests/specify_cli/steering/test_gates.py` (new).
**Validation**: `python -m pytest tests/specify_cli/steering/test_gates.py -q` passes; removing a gate flips its test red.

## Branch Strategy

Planning artifacts were generated on `feat/context-lean-steering`. Execution worktrees are allocated per computed lane from `lanes.json`; completed changes must merge back into `feat/context-lean-steering`.

## Definition of Done

- A gate registry runs the reused checks plus the new gates; `steer check` refuses on violation with a non-zero exit.
- Every gate has a planted-violation test; a gate without one is reported unverified.
- An unavailable check tool fails loudly, never silently passes.
- `python -m pytest tests/specify_cli/steering/test_gates.py -q` passes.
- Subtask completion recorded via `spec-kitty agent tasks mark-status <Txxx> --status done`.

Implement with: `spec-kitty agent action implement WP04 --agent claude`

## Risks

- **Silent pass**: a wrapper that swallows a missing-tool error gives false assurance; fail loudly.
- **Scope creep**: do not re-implement existing checks; wrap them.

## Reviewer Guidance

- Confirm each gate fails its planted violation and no gate passes vacuously.
- Confirm reused checks are invoked through their existing entry points, not copied.
- Confirm an unavailable tool surfaces an error.
