---
work_package_id: WP05
title: Driver loop with batched-action handling
dependencies:
- WP01
- WP03
- WP04
requirement_refs:
- FR-005
- SC-005
planning_base_branch: feat/context-lean-steering
merge_target_branch: feat/context-lean-steering
branch_strategy: Planning artifacts for this mission were generated on feat/context-lean-steering. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/context-lean-steering unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-context-lean-steering-01M4F5GH
base_commit: a3fb9bc17cb347f5709dc2a69819c2033f347d23
created_at: '2026-10-09T03:33:44.245980+00:00'
subtasks:
- T019
- T020
- T021
- T022
history: []
agent_profile: python-pedro
authoritative_surface: src/specify_cli/steering/
create_intent:
- src/specify_cli/steering/driver.py
- tests/specify_cli/steering/test_driver.py
execution_mode: code_change
owned_files:
- src/specify_cli/steering/driver.py
- tests/specify_cli/steering/test_driver.py
role: implementer
tags: []
tracker_refs: []
---

# WP05 — Driver loop with batched-action handling

## ⚡ Do This First: Load Agent Profile

Use the `/ad-hoc-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## Objective

Drive a model through the lean loop: render kernel + capsule, call the model, execute **every** action in each reply (including multiple actions batched in one reply), append results, and report a scored transcript.

## Context

- Spec: `FR-005`, `SC-005`. Plan: IC-05; research D-06.
- **The critical defect to avoid**: the spike (`lean-loop-test.md`) proved that a strict single-JSON parser turns a passing run into a **false failure** — the 9B emitted `write_file` followed by `run_tests` in one turn; the parser kept only the first and the run was mis-scored. The driver must execute all actions in a reply, in order.
- Reuse `research-outputs/lean-steering-spike/lean_loop.py` as the reference implementation (tool protocol, lenient parse via `json.JSONDecoder().raw_decode`, sandboxed execution).

## Subtask T019: Tool protocol and lenient parser

**Purpose**: parse every action, ignore only trailing non-action text.

**Steps**:
1. Define the tool protocol (JSON object per action) and a lenient parser that extracts the **first** object, then continues to parse subsequent objects in the same reply.
2. A reply with no parseable object is a counted **format error** (never dropped silently).
**Files**: `src/specify_cli/steering/driver.py` (new).
**Validation**: a two-object reply yields two actions; a prose reply yields a counted format error.

## Subtask T020: Driver loop

**Purpose**: the render → call → execute → report cycle.

**Steps**:
1. Assemble the initial context: kernel (WP01) + capsule (WP03) + the tool protocol.
2. Each turn: call the model, parse **all** actions, execute each in order (respecting the gate from WP04 and the sandboxed target), append results.
3. Bound the loop by the turn budget; a `finish` on a refused gate is a protocol violation, surfaced — not silently accepted.
**Files**: `src/specify_cli/steering/driver.py` (edit).
**Validation**: a scripted two-action reply executes both and records them.

## Subtask T021: Wire `steer loop`

**Purpose**: expose the driver on the CLI.

**Steps**:
1. Implement the `loop` handler (lazy import) → run the loop against `--model <id>` for `--turns N`; print a scored transcript; `--json` a structured report.
**Files**: no CLI edit (WP01 owns `steer.py`).
**Validation**: `spec-kitty steer loop --mission <handle> --model <id> --turns 4` runs and reports.

## Subtask T022: Batched-action and loud-failure tests

**Purpose**: pin the two failure modes the spike found.

**Steps**:
1. Test: a reply containing two tool calls results in **both** being executed (SC-005) — this test must be red if the parser only keeps the first.
2. Test: an unreachable model server / non-JSON reply fails loudly and is counted, never silently ignored.
**Files**: `tests/specify_cli/steering/test_driver.py` (new).
**Validation**: `python -m pytest tests/specify_cli/steering/test_driver.py -q` passes; the batched test fails under a first-only parser.

## Branch Strategy

Planning artifacts were generated on `feat/context-lean-steering`. Execution worktrees are allocated per computed lane from `lanes.json`; completed changes must merge back into `feat/context-lean-steering`.

## Definition of Done

- The driver executes every action in every reply, in order (SC-005), proven by a test that fails under a first-only parser.
- A non-JSON reply is a counted format error; an unreachable model fails loudly.
- `python -m pytest tests/specify_cli/steering/test_driver.py -q` passes.
- Subtask completion recorded via `spec-kitty agent tasks mark-status <Txxx> --status done`.

Implement with: `spec-kitty agent action implement WP05 --agent claude`

## Risks

- **Batched-action regression**: the whole point of this WP; the test must be genuinely discriminating.
- **Sandbox safety**: the driver must never mutate the repository outside an explicit target.

## Reviewer Guidance

- Confirm the batched-action test fails if the parser is made single-action.
- Confirm no silent drop of actions or format errors.
