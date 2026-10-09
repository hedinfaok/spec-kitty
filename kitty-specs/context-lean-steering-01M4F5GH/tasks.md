# Tasks: Context-lean steering — kernel + capsule + gates over the spec-kitty engine

**Mission**: `context-lean-steering-01M4F5GH` | **Branch**: `feat/context-lean-steering` | **Date**: 2026-10-09
**Spec**: [`spec.md`](spec.md) · **Plan**: [`plan.md`](plan.md)

## Overview

Eight work packages translating the plan's Implementation Concern Map (IC-01…IC-08) into
executable units. All new source lives under `src/specify_cli/steering/`; the CLI surface is
`src/specify_cli/cli/commands/steer.py`. No engine module is modified.

## Subtask Index

| ID | Description | WP | Parallel |
|----|-------------|----|----------|
| T001 | Create the `steering` package + `steer` command group skeleton | WP01 | |
| T002 | Implement the standing kernel artifact (≤ 1 KB) | WP01 | |
| T003 | Wire `steer kernel` | WP01 | |
| T004 | Kernel invariants test (size + byte-stability) | WP01 | |
| T005 | Build the deterministic doctrine index (selector → source) | WP02 | |
| T006 | FTS5 backend + JSON fallback | WP02 | [P] |
| T007 | Wire `steer fetch` with unknown-selector error | WP02 | |
| T008 | Index/retrieval tests | WP02 | |
| T009 | Capsule model + renderer (≤ 2 KB) | WP03 | |
| T010 | Derive capsule from engine state (next + WP frontmatter) | WP03 | |
| T011 | Doctrine pointers (no bodies) | WP03 | |
| T012 | Wire `steer capsule` | WP03 | |
| T013 | Capsule budget + completeness tests | WP03 | |
| T014 | Gate registry | WP04 | |
| T015 | Adapt existing checks (ruff / architectural / terminology) | WP04 | [P] |
| T016 | New gates (protected branch, engine guard failures) | WP04 | [P] |
| T017 | Wire `steer check` (binding refusal, exit code) | WP04 | |
| T018 | Planted-violation tests per gate | WP04 | |
| T019 | Tool protocol + lenient parser (batched actions) | WP05 | |
| T020 | Driver loop (render → model → execute each action → report) | WP05 | |
| T021 | Wire `steer loop` | WP05 | |
| T022 | Batched-action + loud-failure tests | WP05 | |
| T023 | Tier policy (T0–T3) | WP06 | |
| T024 | Local provider adapter (OpenAI-compatible), loud errors | WP06 | |
| T025 | Tier/error tests | WP06 | |
| T026 | Steering-size computation | WP07 | |
| T027 | Wire `steer measure` | WP07 | |
| T028 | Reproducibility test | WP07 | |
| T029 | Write the requires-inline divergence ADR | WP08 | |
| T030 | Cross-link the ADR from the capsule code | WP08 | |
| T031 | Record the supersession explicitly | WP08 | |

## Work Packages

### WP01 — Steering foundation and the standing kernel (IC-01)

**Goal**: create the `steering` package and the `steer` command group, and ship the standing
kernel (≤ 1 KB, byte-stable).
**Priority**: P1 (foundation — everything else imports the package).
**Independent test**: `spec-kitty steer kernel` prints the kernel; `len(kernel.encode()) <= 1024`; two calls are byte-identical.
**Included subtasks**

T001 Create the `steering` package + `steer` command group skeleton (WP01)
T002 Implement the standing kernel artifact (≤ 1 KB) (WP01)
T003 Wire `steer kernel` (WP01)
T004 Kernel invariants test (size + byte-stability) (WP01)

**Dependencies**: none
**Estimated prompt size**: ~180 lines

### WP02 — Deterministic doctrine index and retrieval (IC-03)

**Goal**: build the selector → canonical-source index and expose `steer fetch`.
**Priority**: P1 (capsule references depend on it).
**Independent test**: an index builds over the doctrine corpus; `steer fetch directive:DIRECTIVE_030` returns the body; an unknown selector errors.
**Included subtasks**

T005 Build the deterministic doctrine index (selector → source) (WP02)
T006 FTS5 backend + JSON fallback (WP02)
T007 Wire `steer fetch` with unknown-selector error (WP02)
T008 Index/retrieval tests (WP02)

**Dependencies**: WP01
**Estimated prompt size**: ~160 lines

### WP03 — Per-step capsule emitter (IC-02)

**Goal**: emit a bounded per-step capsule from engine state, with doctrine as pointers.
**Priority**: P1 (the core steering artifact).
**Independent test**: `steer capsule --mission <handle>` returns step, WP facts, pointers, gate; ≤ 2 KB; no doctrine body inlined.
**Included subtasks**

T009 Capsule model + renderer (≤ 2 KB) (WP03)
T010 Derive capsule from engine state (next + WP frontmatter) (WP03)
T011 Doctrine pointers (no bodies) (WP03)
T012 Wire `steer capsule` (WP03)
T013 Capsule budget + completeness tests (WP03)

**Dependencies**: WP01, WP02
**Estimated prompt size**: ~200 lines

### WP04 — Machine gates (IC-04)

**Goal**: a runtime gate surface that refuses, reusing existing checks plus new gates.
**Priority**: P1 (safety).
**Independent test**: `steer check` exits non-zero with problems on a violation; each gate has a planted-violation test.
**Included subtasks**

T014 Gate registry (WP04)
T015 Adapt existing checks (ruff / architectural / terminology) (WP04)
T016 New gates (protected branch, engine guard failures) (WP04)
T017 Wire `steer check` (binding refusal, exit code) (WP04)
T018 Planted-violation tests per gate (WP04)

**Dependencies**: WP01
**Estimated prompt size**: ~180 lines

### WP05 — Driver loop (IC-05)

**Goal**: drive a model through the loop, executing every action in a reply (batched-aware).
**Priority**: P2.
**Independent test**: a two-action reply executes both actions; a non-JSON reply is a counted format error.
**Included subtasks**

T019 Tool protocol + lenient parser (batched actions) (WP05)
T020 Driver loop (render → model → execute each action → report) (WP05)
T021 Wire `steer loop` (WP05)
T022 Batched-action + loud-failure tests (WP05)

**Dependencies**: WP01, WP03, WP04
**Estimated prompt size**: ~180 lines

### WP06 — Local execution tiers (IC-06)

**Goal**: route a step across T0–T3 against a local model, failing loudly.
**Priority**: P2.
**Independent test**: a tier is selected per step; an unreachable/unloaded local model fails loudly, not silently.
**Included subtasks**

T023 Tier policy (T0–T3) (WP06)
T024 Local provider adapter (OpenAI-compatible), loud errors (WP06)
T025 Tier/error tests (WP06)

**Dependencies**: WP05
**Estimated prompt size**: ~130 lines

### WP07 — Steering-context measurement (IC-07)

**Goal**: report standing and per-step steering sizes against a baseline.
**Priority**: P2.
**Independent test**: `steer measure` reports sizes and a reduction ratio; repeated runs agree.
**Included subtasks**

T026 Steering-size computation (WP07)
T027 Wire `steer measure` (WP07)
T028 Reproducibility test (WP07)

**Dependencies**: WP01, WP03
**Estimated prompt size**: ~120 lines

### WP08 — Requires-inline divergence ADR (IC-08)

**Goal**: record the divergence from ADR 2026-07-28-1 as a new superseding ADR.
**Priority**: P1 (the capsule's pointers depend on it being recorded).
**Independent test**: the new ADR exists, states exactly what is superseded, and is cited from the capsule code.
**Included subtasks**

T029 Write the requires-inline divergence ADR (WP08)
T030 Record precisely what is superseded and what still holds (WP08)
T031 State the divergence and the operator decision explicitly (WP08)

**Dependencies**: none
**Estimated prompt size**: ~110 lines

## Dependencies

```
WP01 ─┬─> WP02 ─> WP03 ─┬─> WP05 ─> WP06
      ├─> WP04 ────────┘
      └─> WP07
WP08 (independent; record the divergence early)
```

**MVP scope**: WP01 + WP03 + WP04 + WP08 (kernel, capsule, gates, divergence record) — the
smallest slice that delivers the P1 user story.
