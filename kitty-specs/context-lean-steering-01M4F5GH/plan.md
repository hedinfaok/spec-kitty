# Implementation Plan: Context-lean steering — kernel + capsule + gates over the spec-kitty engine

**Branch**: `feat/context-lean-steering` | **Date**: 2026-10-09 | **Spec**: [`kitty-specs/context-lean-steering-01M4F5GH/spec.md`](spec.md)
**Input**: Mission specification from `kitty-specs/context-lean-steering-01M4F5GH/spec.md`

## Summary

Deliver an additive, upstream-friendly lean steering layer over the existing `spec-kitty`
engine: a small standing **kernel**, a bounded per-step **capsule** derived from mission
state, a deterministic **doctrine index** for on-demand retrieval, a **gate** surface the
agent runs mid-loop, a **driver** that executes every action in a model reply (including
batched actions), **local execution tiers** (T0–T3), and a **measurement** command. No
engine module is rewritten; the one behavioural divergence (ADR 2026-07-28-1 requires-inline)
is recorded as a new ADR (IC-08).

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: the existing `spec-kitty` CLI (`next`, `charter context`) and the Python standard library (`sqlite3`, `json`, `subprocess`, `argparse`); **no new third-party runtime dependency**
**Storage**: on-disk doctrine index built at install/first use, under `.kittify/` (runtime, gitignored); SQLite **FTS5** with a plain-JSON fallback
**Testing**: `pytest` (existing suite) + planted-violation gate tests + an end-to-end loop test against a local OpenAI-compatible server
**Target Platform**: Linux (development) and consumer x86-64 unified-memory hardware (validated on an AMD Ryzen AI Max+ 395); local OpenAI-compatible inference server
**Project Type**: single project — additive module in the existing `spec-kitty` repository
**Performance Goals**: standing kernel ≤ 1 KB; per-step capsule ≤ 2 KB; the driver completes a work package within a ≤ 12-turn budget on a 9B-class Q4 local model
**Constraints**: reuse the engine (no fork); retrieval is deterministic (no embedding model); landable as one standard pull request; terminology is Mission (never "feature")
**Scale/Scope**: one mission; 8 functional requirements; the new surface is a small set of CLI subcommands plus one module

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Single canonical authority / canonical sources** — PASS. Doctrine reaching the model is fetched from canonical sources on demand (NFR-003); no paraphrased copies are inlined.
- **Architectural alignment** — PASS. Additive seams only (`src/specify_cli/steering/` + CLI commands); the state machine, reducer, and reconciliation gates are untouched (C-001, NFR-002).
- **Terminology adherence** — PASS. Mission, never "feature" (C-003).
- **ATDD-first / quality gates** — PASS. Every gate ships a planted-violation test that fails without it (NFR-005).
- **Conflict to record (not a violation to hide)** — The capsule delivers `requires` doctrine as fetch pointers rather than inline bodies, diverging from ADR 2026-07-28-1. Operator decision (2026-10-09): carry it as the **single documented divergence**; IC-08 produces a new superseding ADR. This is tracked in Complexity Tracking.

*Re-check after Phase 1 design:* design artifacts below keep the divergence confined to the capsule's rendering contract and do not touch engine resolution.

## Project Structure

### Documentation (this mission)

```
kitty-specs/context-lean-steering-01M4F5GH/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── steering-cli.md
└── tasks.md             # Phase 2 output (/spec-kitty.tasks — NOT created here)
```

### Source Code (repository root)

```
src/specify_cli/
├── steering/                       # NEW module (additive)
│   ├── __init__.py
│   ├── kernel.py                   # IC-01 — the standing kernel artifact
│   ├── capsule.py                  # IC-02 — per-step capsule emitter
│   ├── index.py                    # IC-03 — deterministic doctrine index + retrieval
│   ├── gates.py                    # IC-04 — runtime gate surface
│   ├── driver.py                   # IC-05 — driver loop (batched-action aware)
│   ├── tiers.py                    # IC-06 — local execution tier policy
│   └── measure.py                  # IC-07 — steering-context measurement
└── cli/commands/
    └── steer.py                    # NEW subcommands: steer kernel|capsule|fetch|check|measure|loop

docs/adr/4.x/
└── 2026-10-09-1-requires-inline-divergence.md   # IC-08 — new superseding ADR

tests/specify_cli/steering/         # NEW — unit + planted-violation + loop tests
├── test_kernel.py
├── test_capsule.py
├── test_index.py
├── test_gates.py
├── test_driver.py
└── test_measure.py
```

**Structure Decision**: single project, additive. A new `src/specify_cli/steering/` module carries the layer's logic; a new `src/specify_cli/cli/commands/steer.py` exposes it on the existing CLI surface (Q1 = A). Tests mirror the source tree. No engine module is modified.

## Complexity Tracking

*Filled because Charter Check records a deliberate divergence from an Accepted ADR.*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Capsule delivers `requires` doctrine as fetch pointers, not inline bodies (ADR 2026-07-28-1 requires-eager inline) | Inlining the `requires`-closure is 58–71 KB per action — the exact bloat this mission exists to remove; pointers are the only way to reach the ≤ 2 KB capsule budget | Inlining (status quo) blows the budget; summarising bodies drifts from canonical sources (rejected by the ADR itself); the divergence is recorded in a new ADR (IC-08) per operator decision |

## Implementation Concern Map

### IC-01 — Standing kernel

- **Purpose**: Provide the small, stable standing instruction set the harness injects each turn.
- **Relevant requirements**: FR-001, NFR-001
- **Affected surfaces**: `src/specify_cli/steering/kernel.py`, `steer kernel`
- **Sequencing/depends-on**: none
- **Risks**: must stay byte-stable for prefix caching; resist regrowth (nothing else may be added to it).

### IC-02 — Per-step capsule

- **Purpose**: Emit a bounded capsule derived from mission state (step, work package facts, doctrine pointers, binding gate).
- **Relevant requirements**: FR-002, FR-003, NFR-001
- **Affected surfaces**: `src/specify_cli/steering/capsule.py`, `steer capsule`
- **Sequencing/depends-on**: IC-01
- **Risks**: completeness — nothing the old payload carried may be silently dropped; pointers must remain addressable.

### IC-03 — Deterministic doctrine retrieval

- **Purpose**: Build and query an on-disk index so doctrine bodies are fetched on demand without an embedding model.
- **Relevant requirements**: FR-003, C-005, NFR-003
- **Affected surfaces**: `src/specify_cli/steering/index.py`, `steer fetch`
- **Sequencing/depends-on**: none
- **Risks**: index staleness on doctrine change; canonical-source fidelity (fetch the source, never a paraphrase).

### IC-04 — Machine gates

- **Purpose**: Expose a runtime check surface the agent runs mid-loop, reusing the existing CI gate suite and adding the mission's own gates.
- **Relevant requirements**: FR-004, NFR-005
- **Affected surfaces**: `src/specify_cli/steering/gates.py`, `steer check`
- **Sequencing/depends-on**: none
- **Risks**: a gate that cannot fail is worthless — each ships a planted-violation test.

### IC-05 — Driver loop

- **Purpose**: Drive a model through the loop and execute **every** action in a reply, including batched actions.
- **Relevant requirements**: FR-005, SC-005
- **Affected surfaces**: `src/specify_cli/steering/driver.py`, `steer loop`
- **Sequencing/depends-on**: IC-01, IC-02, IC-04
- **Risks**: the spike proved a strict single-JSON parser turns a passing run into a false failure — batching must be handled and tested.

### IC-06 — Local execution tiers

- **Purpose**: Route a step across the tiers T0 retrieval, T1 routing, T2 drafting, T3 full loop, against a local model.
- **Relevant requirements**: FR-006, NFR-006
- **Affected surfaces**: `src/specify_cli/steering/tiers.py`
- **Sequencing/depends-on**: IC-05
- **Risks**: provider quirks (unreachable server, unloaded model, harness auto-compaction) must fail loudly, not silently.

### IC-07 — Steering-context measurement

- **Purpose**: Report standing and per-step steering sizes against a baseline so the reduction is verifiable.
- **Relevant requirements**: FR-007, SC-001, SC-002
- **Affected surfaces**: `src/specify_cli/steering/measure.py`, `steer measure`
- **Sequencing/depends-on**: IC-01, IC-02
- **Risks**: measurement must be reproducible and not depend on stateful side effects.

### IC-08 — Requires-inline divergence ADR

- **Purpose**: Record the divergence from ADR 2026-07-28-1 as a new superseding ADR so it is a reviewable decision.
- **Relevant requirements**: FR-008, C-002
- **Affected surfaces**: `docs/adr/4.x/2026-10-09-1-requires-inline-divergence.md`
- **Sequencing/depends-on**: none
- **Risks**: must state exactly what is superseded and what still holds (fetchability preserved; bodies retrieved, not omitted).
