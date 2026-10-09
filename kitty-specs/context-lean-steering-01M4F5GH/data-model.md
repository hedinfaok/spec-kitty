# Phase 1 Data Model: Context-lean steering

Domain entities of the lean steering layer. This mission has no database; "entities" are
the value objects the layer renders and checks.

## Kernel

The small standing instruction set the harness injects each turn.

| Field | Type | Notes |
|---|---|---|
| protocol | ordered list of rules | state is authoritative; doctrine is fetched; gates are binding |
| judgment | list of short rules | the residue no gate can check (e.g. prefer durable fixes) |

**Invariants**: byte-stable across turns (prefix-cacheable); ≤ 1024 bytes; carries no
mission-specific state and no doctrine bodies.

## Capsule

The bounded per-step steering artifact, derived from mission state.

| Field | Type | Notes |
|---|---|---|
| mission | slug | from the engine |
| step | enum | current action (e.g. implement, review, accept) |
| wp | id + title | from the work package frontmatter when present |
| facts | owned files, subtasks, requirement refs, dependencies | from the work package frontmatter |
| pointers | list of `{selector, when}` | doctrine delivered as fetch references (D-05) |
| gate | command | the binding `steer check` invocation |

**Invariants**: ≤ 2048 bytes; derived from engine state, never hardcoded; every pointer
resolves through the canonical fetch surface; no doctrine *body* is inlined.

## DoctrineIndex

The deterministic retrieval index.

| Field | Type | Notes |
|---|---|---|
| selector | string | e.g. `directive:DIRECTIVE_030` |
| source_path | path | the canonical source file on disk |
| when | string | applicability guidance (from the source metadata) |

**Invariants**: built from canonical sources only; rebuilt when the source set changes;
resolvable without a model; a missing selector is an explicit error, not a silent empty
result.

## Gate

A deterministic check over a target.

| Field | Type | Notes |
|---|---|---|
| id | string | stable gate id |
| check | callable | returns a list of problems (empty = clean) |
| binding | bool | a refusal must stop the agent |

**Invariants**: each gate has ≥ 1 planted-violation test; a gate with no failing case is
considered unverified.

## LoopState (driver)

| Field | Type | Notes |
|---|---|---|
| turn | int | bounded by the turn budget |
| messages | transcript | kernel + capsule first, then tool results |
| actions_executed | list | every action from a reply, including batched actions (D-06) |

**State transitions**: `render → model → parse actions → execute each action → append results
→ (fetch | gate | write | finish)`. A `finish` on a refused gate is a protocol violation and
is surfaced, not silently accepted.

**Invariants**: the driver executes *all* actions in a reply; a non-JSON reply is a counted
format error, never dropped silently; the repository is never mutated outside an explicit
target.
