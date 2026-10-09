---
work_package_id: WP06
title: Local execution tiers
dependencies:
- WP05
requirement_refs:
- FR-006
- NFR-006
- C-004
- SC-004
planning_base_branch: feat/context-lean-steering
merge_target_branch: feat/context-lean-steering
branch_strategy: Planning artifacts for this mission were generated on feat/context-lean-steering. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/context-lean-steering unless the human explicitly redirects the landing branch.
subtasks:
- T023
- T024
- T025
history: []
agent_profile: python-pedro
authoritative_surface: src/specify_cli/steering/
create_intent:
- src/specify_cli/steering/tiers.py
- tests/specify_cli/steering/test_tiers.py
execution_mode: code_change
owned_files:
- src/specify_cli/steering/tiers.py
- tests/specify_cli/steering/test_tiers.py
role: implementer
tags: []
tracker_refs: []
---

# WP06 — Local execution tiers

## ⚡ Do This First: Load Agent Profile

Use the `/ad-hoc-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## Objective

Route a step across the local execution tiers — T0 retrieval, T1 routing, T2 drafting, T3 full loop — against a local OpenAI-compatible model server, so the loop can run without a remote API.

## Context

- Spec: `FR-006`, `NFR-006`, `C-004`, `SC-004` (operator selected full tiers T0–T3). Plan: IC-06; research D-07.
- The validated target: a 9B-class Q4 local model completes a work package within a ≤ 12-turn budget (`lean-loop-test.md`).
- Provider quirks observed in the spike must fail **loudly**, never silently: an unreachable server, an unloaded model, and harness auto-compaction replacing the prompt with a summary.

## Subtask T023: Tier policy

**Purpose**: decide, per step, which tier applies.

**Steps**:
1. In `src/specify_cli/steering/tiers.py`, define the tiers and a policy mapping a step (and its nature) to a tier. T0 retrieval always local; T1/T2/T3 escalate.
2. Keep the policy data-driven and inspectable (no hidden behaviour).
**Files**: `src/specify_cli/steering/tiers.py` (new).
**Validation**: given a step, the policy returns a tier deterministically.

## Subtask T024: Local provider adapter with loud errors

**Purpose**: talk to the local model without silent failure.

**Steps**:
1. Implement an adapter for an OpenAI-compatible endpoint (`/v1/chat/completions`), reusing the spike's `local_probe.py` shape. No new third-party dependency (stdlib `urllib` or an existing HTTP client already in the repo).
2. On unreachable server, unloaded model, or an empty/malformed response: raise a clear, typed error — never return an empty string.
**Files**: `src/specify_cli/steering/tiers.py` (edit).
**Validation**: a bad endpoint raises a clear error; a good endpoint returns text.

## Subtask T025: Tier and error tests

**Purpose**: falsifiable behaviour.

**Steps**:
1. Test the tier policy for representative steps.
2. Test the adapter’s failure modes (unreachable, malformed) raise loud errors, not silent passes.
**Files**: `tests/specify_cli/steering/test_tiers.py` (new).
**Validation**: `python -m pytest tests/specify_cli/steering/test_tiers.py -q` passes.

## Branch Strategy

Planning artifacts were generated on `feat/context-lean-steering`. Execution worktrees are allocated per computed lane from `lanes.json`; completed changes must merge back into `feat/context-lean-steering`.

## Definition of Done

- A deterministic tier policy (T0–T3) exists.
- The local adapter fails loudly on unreachable/unloaded/malformed; never silent.
- No new third-party dependency.
- `python -m pytest tests/specify_cli/steering/test_tiers.py -q` passes.
- Subtask completion recorded via `spec-kitty agent tasks mark-status <Txxx> --status done`.

Implement with: `spec-kitty agent action implement WP06 --agent claude`

## Risks

- **Silent empty response**: the most dangerous failure; must raise.
- **Provider drift**: pin the endpoint shape to the OpenAI-compatible contract and document it.

## Reviewer Guidance

- Confirm failure modes raise loudly.
- Confirm the tier policy is deterministic and inspectable.
