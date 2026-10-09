---
work_package_id: WP08
title: Requires-inline divergence ADR
dependencies: []
requirement_refs:
- FR-008
- C-002
planning_base_branch: feat/context-lean-steering
merge_target_branch: feat/context-lean-steering
branch_strategy: Planning artifacts for this mission were generated on feat/context-lean-steering. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/context-lean-steering unless the human explicitly redirects the landing branch.
subtasks:
- T029
- T030
- T031
history: []
agent_profile: doctrine-daphne
authoritative_surface: docs/adr/4.x/
create_intent:
- docs/adr/4.x/2026-10-09-1-requires-inline-divergence.md
execution_mode: planning_artifact
owned_files:
- docs/adr/4.x/2026-10-09-1-requires-inline-divergence.md
role: curator
tags: []
tracker_refs: []
---

# WP08 — Requires-inline divergence ADR

## ⚡ Do This First: Load Agent Profile

Use the `/ad-hoc-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `doctrine-daphne`
- **Role**: `curator`
- **Agent/tool**: `claude`

---

## Objective

Record, as a new Architecture Decision Record, that this mission's capsule delivers `requires` doctrine as fetch **pointers** rather than inline bodies — diverging from ADR 2026-07-28-1 — and state exactly what is superseded and what still holds.

## Context

- Spec: `FR-008`, `C-002`. Plan: IC-08; research D-04.
- Operator decision (2026-10-09): carry the requires-inline erosion as the mission's **single documented divergence**.
- ADR 2026-07-28-1 decided that `requires` edges are followed eagerly and delivered **inline** (a link keeps an artefact addressable, but `requires` is the inline body; fetch-stanza treatment is reserved by name for `suggests`). This mission moves `requires`-closure entries to fetch pointers to hit the ≤ 2 KB capsule budget.
- This WP is a **planning artifact** WP: every owned file is under `docs/` (or `kitty-specs/`); it changes no source code.

## Subtask T029: Write the ADR

**Purpose**: a durable, discoverable decision record.

**Steps**:
1. Create `docs/adr/4.x/2026-10-09-1-requires-inline-divergence.md` following the repository's ADR shape (title, status, date, context, decision, rationale, alternatives, consequences, references).
2. State the decision: the lean capsule delivers `requires` doctrine as `{selector, when}` pointers; bodies are fetched on demand through the canonical `charter context --include` surface.
3. Reference the mission `context-lean-steering-01M4F5GH` and the operator decision of 2026-10-09.
**Files**: `docs/adr/4.x/2026-10-09-1-requires-inline-divergence.md` (new).
**Validation**: the ADR renders and its frontmatter parses.

## Subtask T030: Record precisely what is superseded and what still holds

**Purpose**: a supersession is only safe if its boundary is explicit.

**Steps**:
1. State which clause of ADR 2026-07-28-1 is superseded (the requires-eager **inline** guarantee under a budget-constrained capsule).
2. State what still holds: artefacts remain **fetchable** (nothing is omitted); `suggests` remains link-only; canonical retrieval is preserved (no paraphrase).
**Files**: the ADR (edit).
**Validation**: the ADR names the superseded clause and the preserved guarantees explicitly.

## Subtask T031: State the divergence and the operator decision explicitly

**Purpose**: make the divergence reviewable, not silent.

**Steps**:
1. Add a short "Divergence" section naming this as the mission's single documented divergence, citing the operator decision (2026-10-09) and the constraint `C-002`.
2. Cross-reference the mission plan's Complexity Tracking entry.
**Files**: the ADR (edit).
**Validation**: the ADR contains a "Divergence" section with the operator decision and the C-002 citation.

## Branch Strategy

Planning artifacts were generated on `feat/context-lean-steering`. Execution worktrees are allocated per computed lane from `lanes.json`; completed changes must merge back into `feat/context-lean-steering`.

## Definition of Done

- The new ADR exists at `docs/adr/4.x/2026-10-09-1-requires-inline-divergence.md`.
- It states exactly what is superseded and what still holds (fetchability preserved, no omission).
- It explicitly records the divergence and the operator decision (C-002).
- No source file changed (planning_artifact WP).
- Subtask completion recorded via `spec-kitty agent tasks mark-status <Txxx> --status done`.

Implement with: `spec-kitty agent action implement WP08 --agent claude`

## Risks

- **Overstating the supersession**: the ADR must not claim more is superseded than the requires-inline guarantee.
- **Silence**: the divergence must be discoverable from the code path it affects; WP03's capsule module should cite this ADR (note for reviewers).

## Reviewer Guidance

- Confirm the supersession boundary is precise (requires-inline only; fetchability preserved).
- Confirm the ADR is a planning artifact and no source file changed.
