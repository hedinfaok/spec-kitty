---
work_package_id: WP07
title: Steering-context measurement
dependencies:
- WP01
- WP03
requirement_refs:
- FR-007
- SC-001
- SC-002
planning_base_branch: feat/context-lean-steering
merge_target_branch: feat/context-lean-steering
branch_strategy: Planning artifacts for this mission were generated on feat/context-lean-steering. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/context-lean-steering unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-context-lean-steering-01M4F5GH
base_commit: a3fb9bc17cb347f5709dc2a69819c2033f347d23
created_at: '2026-10-09T03:36:47.164333+00:00'
subtasks:
- T026
- T027
- T028
history: []
agent_profile: python-pedro
authoritative_surface: src/specify_cli/steering/
create_intent:
- src/specify_cli/steering/measure.py
- tests/specify_cli/steering/test_measure.py
execution_mode: code_change
owned_files:
- src/specify_cli/steering/measure.py
- tests/specify_cli/steering/test_measure.py
role: implementer
tags: []
tracker_refs: []
---

# WP07 — Steering-context measurement

## ⚡ Do This First: Load Agent Profile

Use the `/ad-hoc-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## Objective

Report the standing and per-step steering sizes against the mission's baseline, so the reduction (SC-001, SC-002) is verifiable and reproducible.

## Context

- Spec: `FR-007`, `SC-001` (standing ≤ 1 KB from ~101 KB), `SC-002` (payload ≤ 2 KB from 81–95 KB). Plan: IC-07.
- Baseline constants come from vetted measurements: standing corpus ~101 KB (`AGENTS.md` + overrides); per-step payload 81–95 KB first load (`analyze-prompt-context-load-01M3F4BV`, #5005). Reproduce the shape of `research-outputs/lean-steering-spike/sk.py measure`.

## Subtask T026: Steering-size computation

**Purpose**: compute the real sizes.

**Steps**:
1. In `src/specify_cli/steering/measure.py`, compute the standing size (kernel bytes) and the per-step size (a rendered capsule for a given mission).
2. Hold the baseline as named constants with their provenance (cite #5005 in a comment).
**Files**: `src/specify_cli/steering/measure.py` (new).
**Validation**: sizes are computed from the live artifacts, not hardcoded.

## Subtask T027: Wire `steer measure`

**Purpose**: expose the measurement.

**Steps**:
1. Implement the `measure` handler (lazy import) → `--json` `{standing_bytes, capsule_bytes, baseline_standing_bytes, baseline_payload_bytes, reduction}`.
**Files**: no CLI edit (WP01 owns `steer.py`).
**Validation**: `spec-kitty steer measure --mission <handle>` prints the sizes and a reduction ratio.

## Subtask T028: Reproducibility test

**Purpose**: prove the measurement is stable.

**Steps**:
1. Test: two runs agree; the reported reduction matches the computed ratio (no drift); the standing measurement reflects the kernel (changing the kernel changes it).
**Files**: `tests/specify_cli/steering/test_measure.py` (new).
**Validation**: `python -m pytest tests/specify_cli/steering/test_measure.py -q` passes.

## Branch Strategy

Planning artifacts were generated on `feat/context-lean-steering`. Execution worktrees are allocated per computed lane from `lanes.json`; completed changes must merge back into `feat/context-lean-steering`.

## Definition of Done

- `steer measure` reports standing and per-step sizes and a reduction ratio vs the cited baseline.
- Repeated runs agree; the measurement is derived from the live artifacts.
- `python -m pytest tests/specify_cli/steering/test_measure.py -q` passes.
- Subtask completion recorded via `spec-kitty agent tasks mark-status <Txxx> --status done`.

Implement with: `spec-kitty agent action implement WP07 --agent claude`

## Risks

- **Baseline drift**: the baseline is a citation, not a live value; label it and cite #5005.

## Reviewer Guidance

- Confirm sizes are computed live, not hardcoded.
- Confirm the reduction ratio is reproducible.
