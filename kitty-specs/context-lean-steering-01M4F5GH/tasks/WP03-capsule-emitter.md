---
work_package_id: WP03
title: Per-step capsule emitter
dependencies:
- WP01
- WP02
requirement_refs:
- FR-002
- FR-003
- NFR-001
planning_base_branch: feat/context-lean-steering
merge_target_branch: feat/context-lean-steering
branch_strategy: Planning artifacts for this mission were generated on feat/context-lean-steering. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/context-lean-steering unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-context-lean-steering-01M4F5GH
base_commit: a3fb9bc17cb347f5709dc2a69819c2033f347d23
created_at: '2026-10-09T03:17:24.657077+00:00'
subtasks:
- T009
- T010
- T011
- T012
- T013
history: []
agent_profile: python-pedro
authoritative_surface: src/specify_cli/steering/
create_intent:
- src/specify_cli/steering/capsule.py
- tests/specify_cli/steering/test_capsule.py
execution_mode: code_change
owned_files:
- src/specify_cli/steering/capsule.py
- tests/specify_cli/steering/test_capsule.py
role: implementer
tags: []
tracker_refs: []
---

# WP03 — Per-step capsule emitter

## ⚡ Do This First: Load Agent Profile

Use the `/ad-hoc-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## Objective

Emit the bounded per-step **capsule** — step, work package facts, doctrine **pointers**, and the binding gate — derived from real engine state, at ≤ 2048 bytes. This is the mission's core steering artifact.

## Context

- Spec: `FR-002`, `FR-003`, `NFR-001`. Plan: IC-02; research D-05 (pointers) and D-04 (the recorded divergence).
- The capsule is the only per-step steering text; it must be derived from the engine (`spec-kitty next --mission <handle> --json` plus the work package frontmatter), never hardcoded.
- **Pointers, not bodies**: the capsule lists `{selector, when}` and the agent fetches bodies on demand (WP02). This is the divergence recorded in WP08's ADR — do not inline doctrine bodies.
- Validated shape: see `research-outputs/lean-steering-spike/sk.py` (`render_capsule`) and `lean-steering-spike/README.md`, which measured 84.9× reduction on a real mission.

## Subtask T009: Capsule model + renderer

**Purpose**: a bounded, well-formed capsule.

**Steps**:
1. In `src/specify_cli/steering/capsule.py`, define a `Capsule` value object with fields `mission, step, wp, facts, pointers, gate`.
2. Implement `render(capsule) -> str` producing the compact text form (mirror `sk.py`).
**Files**: `src/specify_cli/steering/capsule.py` (new).
**Validation**: a sample capsule renders; `len(render(c).encode()) <= 2048`.

## Subtask T010: Derive the capsule from engine state

**Purpose**: never hardcode; always reflect current state.

**Steps**:
1. Call the engine: `spec-kitty next --mission <handle> --json` for the step and work package.
2. Read the work package frontmatter (title, dependencies, subtasks, owned files, requirement refs) — reuse the minimal parser from `sk.py` rather than adding a YAML dependency.
**Files**: `src/specify_cli/steering/capsule.py` (edit).
**Validation**: for a real in-progress mission, the capsule’s `step` and `wp` match `spec-kitty next --json`.

## Subtask T011: Doctrine pointers (no bodies)

**Purpose**: deliver doctrine as fetch references.

**Steps**:
1. Emit pointers `{selector, when}` (e.g. `directive:DIRECTIVE_030 — before declaring the change done`) using the WP02 index to validate that each selector resolves.
2. Inline **no** doctrine body.
**Files**: `src/specify_cli/steering/capsule.py` (edit).
**Validation**: the rendered capsule contains ≥ 1 pointer and 0 inlined doctrine bodies.

## Subtask T012: Wire `steer capsule`

**Purpose**: expose it on the CLI.

**Steps**:
1. Implement the `capsule` handler (lazy import of this module) → text or `--json` `{mission, step, wp, facts, pointers, gate}`.
**Files**: no CLI edit (WP01 owns `steer.py`; the handler already lazy-imports this module).
**Validation**: `spec-kitty steer capsule --mission <handle>` prints a ≤ 2 KB capsule.

## Subtask T013: Capsule budget + completeness tests

**Purpose**: prove it is small *and* complete.

**Steps**:
1. Test: ≤ 2048 bytes; contains step, wp, ≥ 1 pointer, gate; contains **no** doctrine body.
2. Completeness test: for a real mission, every field the old payload carried (step, wp title, owned files, subtasks, refs, gate) is present — none silently dropped.
**Files**: `tests/specify_cli/steering/test_capsule.py` (new).
**Validation**: `python -m pytest tests/specify_cli/steering/test_capsule.py -q` passes.

## Branch Strategy

Planning artifacts were generated on `feat/context-lean-steering`. Execution worktrees are allocated per computed lane from `lanes.json`; completed changes must merge back into `feat/context-lean-steering`.

## Definition of Done

- Capsule is derived from engine state; ≤ 2048 bytes; doctrine as pointers only.
- Completeness test proves no required field is dropped.
- `python -m pytest tests/specify_cli/steering/test_capsule.py -q` passes.
- Subtask completion recorded via `spec-kitty agent tasks mark-status <Txxx> --status done`.

Implement with: `spec-kitty agent action implement WP03 --agent claude`

## Risks

- **Completeness**: dropping a field the old payload carried silently reduces steering quality; the completeness test is the guard.
- **Budget creep**: adding rationales will blow the 2048-byte budget; keep it to ids + short `when` text.

## Reviewer Guidance

- Confirm the capsule is state-derived (re-run it and see the step change), ≤ 2048 bytes, and contains no inlined doctrine body.
- Confirm the completeness test is non-vacuous (it fails if a field is removed).
