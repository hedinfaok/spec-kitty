# Mission Specification: Context-lean steering — kernel + capsule + gates over the spec-kitty engine

**Mission Branch**: `feat/context-lean-steering`
**Created**: 2026-10-09
**Status**: Draft
**Input**: User description: `research-outputs/lean-steering-spike/spec-draft.md` (context-lean steering)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Steer a Mission with a tiny standing instruction set on a local model (Priority: P1)

A developer on consumer hardware drives a Spec Kitty Mission with a local model. Today the
agent receives a standing prose corpus (~101 KB) plus an 81–95 KB action payload on every
turn. With this mission, the agent receives a tiny standing kernel plus a bounded per-step
capsule, and the local model stays on rails across a multi-turn work package.

**Why this priority**: this is the whole point — it converts Spec Kitty from a
context-heavy steering regime to a context-lean one, and it is the only slice that alone
delivers user value.

**Independent Test**: point an agent at a scratch project, drive one work package through
the loop on a 9B-class local model, and confirm the work package completes within the turn
budget with the gates green.

**Acceptance Scenarios**:

1. **Given** a mission with a pending work package, **When** the agent is steered with the kernel + capsule, **Then** it performs the work package and finishes only after the binding gate returns clean.
2. **Given** a proxy server that measures the steering text, **When** a turn is rendered, **Then** the standing text is ≤ 1 KB and the per-step text is ≤ 2 KB.
3. **Given** a local 9B-class model, **When** the loop runs a work package, **Then** it completes without an API call.

---

### User Story 2 - Land the change as a normal pull request (Priority: P2)

A maintainer receives the lean steering layer as a standard pull request. Nothing in the
engine is forked; the delivery layer reuses the existing CLI. The one behavioural
divergence from ADR 2026-07-28-1 is resolved by an explicit, recorded decision rather than
silently.

**Why this priority**: upstream-friendliness is a stated goal, but it depends on P1 existing
first.

**Independent Test**: review the diff and confirm no engine module was rewritten and that the
divergence is recorded in a durable decision artifact.

**Acceptance Scenarios**:

1. **Given** the completed change, **When** the diff is inspected, **Then** no state-machine, reducer, or gate module is rewritten (additions only).
2. **Given** the requires-inline divergence, **When** a reviewer looks for it, **Then** they find one explicit decision record describing it.

---

### User Story 3 - Verify safety did not regress (Priority: P3)

A governance reviewer confirms that the machine-checkable invariants are still enforced, not
merely described, and that the reduction is measured and reproducible.

**Why this priority**: it protects the P1 win from silently trading safety for size.

**Independent Test**: run the gate test suite with planted violations and confirm each gate
refuses; run the measurement command and confirm the reported reduction.

**Acceptance Scenarios**:

1. **Given** each gate, **When** its planted-violation test runs, **Then** the gate refuses.
2. **Given** the measurement command, **When** it runs, **Then** it reports standing and per-step steering sizes reproducibly.

---

### Edge Cases

- A model emits **multiple tool calls in one reply**. The driver must execute every action, not only the first.
- A "when doing X" doctrine pointer is **never followed**. Safety-critical invariants must still be caught by a gate, not by the unfetched text.
- The local provider **auto-compacts and replaces the prompt** with a summary (observed on a small-context local provider). The loop must not depend on the raw prompt persisting verbatim across turns.
- The **local model server is unreachable** or the model is unloaded.
- The action's `requires`-closure **exceeds the capsule budget**.

## Requirements *(mandatory)*

### Functional Requirements

| ID | Title | User Story | Priority | Status | Delivery | No-op passable? |
|----|-------|------------|----------|--------|----------|-----------------|
| FR-001 | Standing kernel | As an operator, I want a tiny standing instruction set that states the protocol (state is authoritative, doctrine is fetched, gates are binding) and the judgment residue, so that steering does not consume the context budget every turn. | High | Open | [build] | no |
| FR-002 | Per-step capsule | As an operator, I want a bounded per-step steering capsule derived from current mission state, so that the agent knows exactly its current step without a standing corpus. | High | Open | [build] | no |
| FR-003 | Fetched doctrine | As a governance author, I want required guidance delivered as fetchable references whose bodies are retrieved from canonical sources on demand, so that no drift-prone copies are inlined. | High | Open | [build] | no |
| FR-004 | Binding gates | As a reviewer, I want deterministic gates that refuse violations and that an agent treats as binding, so that safety does not depend on the model reading prose. | High | Open | [build] | no |
| FR-005 | Batched-action driver | As an operator, I want the driver loop to execute every action in a model reply, including multiple actions in one reply, so that a valid multi-action turn is not silently dropped. | High | Open | [build] | no |
| FR-006 | Local execution tiers | As a consumer-hardware operator, I want the loop to run on local models across all tiers (retrieval, routing, drafting, full loop), so that I can work without a remote API. | Medium | Open | [build] | no |
| FR-007 | Steering-context measurement | As a maintainer, I want a command that reports standing and per-step steering sizes against a baseline, so that the reduction is verifiable. | Medium | Open | [build] | no |
| FR-008 | Recorded divergence | As a maintainer, I want the requires-inline divergence from ADR 2026-07-28-1 recorded as an explicit durable decision, so that it is a known, reviewable choice rather than silent drift. | Medium | Open | [build] | no |

### Non-Functional Requirements

| ID | Title | Requirement | Category | Priority | Status |
|----|-------|-------------|----------|----------|--------|
| NFR-001 | Steering budget | Standing kernel ≤ 1024 bytes; per-step capsule ≤ 2048 bytes; measured per rendered action. | Performance | High | Open |
| NFR-002 | No engine fork | The layer rewrites 0 engine modules (state machine, reducer, reconciliation, CLI); all changes are additive seams. | Maintainability | High | Open |
| NFR-003 | Canonical retrieval | 100% of doctrine that reaches the model is fetched from canonical sources; 0 paraphrased summaries. | Correctness | High | Open |
| NFR-004 | Upstream-friendly | Landable as a single standard pull request; no private credentials, forks, or hosted services required. | Process | High | Open |
| NFR-005 | Gate verification | Every gate ships at least one planted-violation test that fails when the gate is removed. | Quality | High | Open |
| NFR-006 | Consumer-hardware bar | A 9B-class Q4 local model completes a real work package through the loop within a ≤ 12-turn budget. | Portability | Medium | Open |

### Constraints

| ID | Title | Constraint | Category | Priority | Status |
|----|-------|------------|----------|----------|--------|
| C-001 | Engine reuse | Reuse the existing CLI as the engine; do not rewrite the state machine, reducer, or gates. | Technical | High | Open |
| C-002 | Documented divergence | The ADR 2026-07-28-1 requires-inline guarantee is carried as a single, explicitly recorded divergence (operator decision, 2026-10-09). | Governance | High | Open |
| C-003 | Canonical terminology | The product term is Mission; "feature" is not used for the domain object. | Business | Medium | Open |
| C-004 | Local bar | Must work on a 9B-class Q4 local model. | Technical | Medium | Open |
| C-005 | Deterministic retrieval | Retrieval is deterministic (keyword/full-text); no embedding-model dependency is introduced. | Technical | Medium | Open |

### Key Entities *(include if the mission involves data)*

- **Kernel**: the small standing instruction set; states the protocol and the judgment residue, and is stable across turns.
- **Capsule**: the bounded per-step steering artifact, derived from mission state; carries the step, its work package facts, doctrine references, and the binding gate.
- **Gate**: a deterministic check over a target; refuses on violation and is binding on the agent.
- **Driver**: the loop that renders kernel + capsule to a model, executes the model's actions (including batched actions), and reports results.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Standing steering text per turn falls from ~101 KB to ≤ 1 KB (≥ 90× reduction), reproduced by the measurement command — [build] · no-op passable: no
- **SC-002**: Per-step steering payload falls from 81–95 KB (first load) to ≤ 2 KB (≥ 40× reduction), reproduced by the measurement command — [build] · no-op passable: no
- **SC-003**: Every gate refuses its planted violation (100% of the gate test set) — [build] · no-op passable: no
- **SC-004**: A 9B-class Q4 local model completes a real work package through the loop within the ≤ 12-turn budget — [build] · no-op passable: no
- **SC-005**: A model reply containing two tool calls results in both actions being executed (no silent drop) — [build] · no-op passable: no

## Assumptions & Dependencies

- **Dependencies**: the engine surfaces `spec-kitty next` and `spec-kitty charter context --include <selector>`; the operator configures a local model provider.
- **Resolved decision (2026-10-09)**: ADR 2026-07-28-1 requires-inline is carried as the single documented divergence.
- **Known external issue**: `charter context --mission-type <type> --json` fails on this checkout (the internal org pack declares an unknown `skills` node kind); unrelated to this mission, but it blocks one code path and should be reported separately.
