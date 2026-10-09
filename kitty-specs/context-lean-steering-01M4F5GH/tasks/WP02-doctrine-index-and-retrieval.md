---
work_package_id: WP02
title: Deterministic doctrine index and retrieval
dependencies:
- WP01
requirement_refs:
- FR-003
- NFR-003
- C-005
planning_base_branch: feat/context-lean-steering
merge_target_branch: feat/context-lean-steering
branch_strategy: Planning artifacts for this mission were generated on feat/context-lean-steering. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/context-lean-steering unless the human explicitly redirects the landing branch.
base_branch: kitty/mission-context-lean-steering-01M4F5GH
base_commit: a3fb9bc17cb347f5709dc2a69819c2033f347d23
created_at: '2026-10-09T02:40:59.686528+00:00'
subtasks:
- T005
- T006
- T007
- T008
history: []
agent_profile: python-pedro
authoritative_surface: src/specify_cli/steering/
create_intent:
- src/specify_cli/steering/index.py
- tests/specify_cli/steering/test_index.py
execution_mode: code_change
owned_files:
- src/specify_cli/steering/index.py
- tests/specify_cli/steering/test_index.py
role: implementer
tags: []
tracker_refs: []
---

# WP02 — Deterministic doctrine index and retrieval

## ⚡ Do This First: Load Agent Profile

Use the `/ad-hoc-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## Objective

Build a deterministic index mapping doctrine selectors (e.g. `directive:DIRECTIVE_030`) to their canonical source files, and expose on-demand retrieval through `steer fetch`. No embedding model (C-005); the index is built at install or first use and stored under `.kittify/` (gitignored runtime).

## Context

- Spec: `FR-003`, `NFR-003`, `C-005`. Plan: IC-03; research D-03.
- Retrieval must return the **canonical source** body — never a paraphrase (NFR-003). The existing engine already renders bodies via `spec-kitty charter context --include <selector>`; reuse that surface where possible rather than re-parsing doctrine, and use the index only to resolve selector → source/anchor.
- Storage: SQLite **FTS5** when available; a plain-JSON fallback otherwise (stdlib only).

## Subtask T005: Build the deterministic doctrine index

**Purpose**: resolve a selector to its canonical source without a model.

**Steps**:
1. In `src/specify_cli/steering/index.py`, scan the canonical doctrine roots (directives, tactics, sections under `packs/built-in/` and the project’s `.kittify/doctrine/`) and build entries `{selector, source_path, when}`.
2. Derive `selector` from the artifact id/kind (e.g. `directive:DIRECTIVE_030`). Capture `when` from the source metadata when present.
3. Persist the index under `.kittify/` (gitignored), rebuilt when the source set changes (mtime or content hash).
**Files**: `src/specify_cli/steering/index.py` (new).
**Validation**: building over the doctrine corpus yields a non-empty index; counts match the source file counts.

## Subtask T006: FTS5 backend with a JSON fallback [P]

**Purpose**: deterministic, dependency-free querying.

**Steps**:
1. Use `sqlite3` FTS5 for keyword queries when the module supports it; detect availability and fall back to a plain in-memory/JSON scan otherwise.
2. Keep the query surface identical across both backends.
**Files**: `src/specify_cli/steering/index.py` (edit).
**Validation**: both paths return the same result for a known selector; the fallback is exercised by a test that forces it.

## Subtask T007: Wire `steer fetch`

**Purpose**: expose retrieval on the CLI.

**Steps**:
1. Implement the `fetch` handler: resolve the selector via the index, return the **canonical body** (reuse `spec-kitty charter context --include <selector>` output where available), and with `--json` return `{selector, source_path, body}`.
2. An unknown selector must be an explicit error (`STEER_SELECTOR_UNKNOWN`), never an empty result.
**Files**: `src/specify_cli/steering/index.py` (edit), `src/specify_cli/cli/commands/steer.py` is owned by WP01 — do **not** edit it; the lazy import in its `fetch` handler already points at this module. If a signature mismatch exists, note it for WP01 review rather than editing the file.
**Validation**: `spec-kitty steer fetch directive:DIRECTIVE_030` returns a body; an unknown selector exits non-zero with a clear code.

## Subtask T008: Index/retrieval tests

**Purpose**: prove determinism and canonical fidelity.

**Steps**:
1. Test: a known selector resolves to the expected source; an unknown selector raises `STEER_SELECTOR_UNKNOWN`; the returned body contains no paraphrase marker (assert it matches the canonical source bytes).
2. Test: the JSON fallback and the FTS5 path agree.
**Files**: `tests/specify_cli/steering/test_index.py` (new).
**Validation**: `python -m pytest tests/specify_cli/steering/test_index.py -q` passes.

## Branch Strategy

Planning artifacts were generated on `feat/context-lean-steering`. Execution worktrees are allocated per computed lane from `lanes.json`; completed changes must merge back into `feat/context-lean-steering`.

## Definition of Done

- An index resolves selectors to canonical sources deterministically; FTS5 + fallback both work.
- `steer fetch` returns the canonical body; unknown selectors error explicitly.
- No new third-party dependency (stdlib only).
- `python -m pytest tests/specify_cli/steering/test_index.py -q` passes.
- Subtask completion recorded via `spec-kitty agent tasks mark-status <Txxx> --status done`.

Implement with: `spec-kitty agent action implement WP02 --agent claude`

## Risks

- **Canonical fidelity**: returning a reformatted or summarised body violates NFR-003; return the source verbatim.
- **Index staleness**: a stale index can resolve a selector to a moved file; rebuild on source change.

## Reviewer Guidance

- Confirm the fetched body is the canonical source, not a paraphrase.
- Confirm the fallback path is genuinely tested, not just present.
- Confirm no third-party dependency was added.
