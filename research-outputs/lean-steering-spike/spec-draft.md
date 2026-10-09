# Spec draft — Context-lean steering (kernel + capsule + gates over the engine)

> **Input draft for `/spec-kitty.specify`.** Not the mission `spec.md`; feed this in and let
> specify produce the canonical spec. Mission scaffold already exists:
> `kitty-specs/context-lean-steering-01M4F5GH/` (slug `context-lean-steering-01M4F5GH`,
> target `feat/context-lean-steering`).

---

## Overview

Spec Kitty steers an agent by **statute**: rules are written as prose and pushed into the
model on every turn, plus a large per-action governance payload. Both are paid on every
turn regardless of what the turn needs. This Mission delivers an **upstream-friendly,
context-lean steering layer over the existing engine** — a tiny standing **kernel**, a
bounded per-step **capsule**, and machine **gates** — without forking the engine.

The layer is additive: the state machine, the status reducer, the reconciliation/merge
gates, doctrine resolution and the CLI all stay where they are. Only *what text reaches the
model* changes.

## Problem & measured evidence

Two independent context channels are unpruned:

- **Standing corpus** re-sent every turn — `AGENTS.md` (93,899 B) + overrides
  (`7,539 B`) ≈ **101 KB/turn**; one third of `AGENTS.md` is a single phase-specific
  reference section.
- **Per-action governance payload** — 81–95 KB for `specify`/`plan`/`tasks`/`implement`/
  `review` on first load (mission `analyze-prompt-context-load-01M3F4BV`, issue #5005);
  71–75% lives in an "Action Doctrine" block the 40k-char budget enforcer cannot see.

Investigations already completed on this branch (all reproducible):

| Artifact | Result |
|---|---|
| `research-outputs/context-lean-steering.md` | design space; seven levers; format-vs-mechanism finding |
| `research-outputs/context-format-experiment/` | Markdown 593 tok vs JSON 759 tok vs gate+kernel 125 tok; enforcement 0/8 → 6/8 |
| `research-outputs/lean-steering-spike/sk.py` + `README.md` | working prototype over the engine; **98.9×** standing reduction, **84.9×** payload reduction |
| `research-outputs/lean-steering-spike/compliance-experiment.md` | fresh agents orient correctly from kernel + capsule (8/8 twice), on remote **and** a typical 9B Q4 local model |
| `research-outputs/lean-steering-spike/lean-loop-test.md` | a consumer 9B completed a bounded WP end-to-end through the loop, 4/4, ~879 tok/episode |

## Goals

1. Productionise the lean steering layer over the engine: kernel + capsule + gates.
2. Make it **upstream-landable** (a normal Mission/PR; no private fork required).
3. Keep every machine-checkable invariant **enforced**, not merely described.
4. Work on **consumer hardware** (a 9B-class local model is the bar proven in the spike).

## Non-goals

- Forking or rewriting the engine (state machine, reducer, reconciliation gates, CLI).
- Summarising canonical doctrine (rejected by ADR 2026-07-28-1 for drift).
- A new product/brand, or hosted (Team Kitty) surfaces.

## User journeys

**Journey 1 — the consumer-hardware operator.** A developer on a 128 GB unified-memory box
runs a 9B–120B local model. They want Spec Kitty's governance *without* paying ~100 KB of
steering per turn. After this Mission they drive a Mission from the kernel + capsule and
the local model stays on rails across a multi-turn work package.

**Journey 2 — the upstream maintainer.** A maintainer receives the change as a normal PR.
Nothing in the engine is forked; the delivery layer reuses `spec-kitty next` and
`spec-kitty charter context`. The one behavioural divergence (requires-inline) is resolved
by an explicit ADR decision, not silently.

**Journey 3 — the governance reviewer.** A reviewer can see that safety did not regress: the
gates still refuse (planted-violation tests), and the reduction is measured and reproducible.

## Functional requirements

- **FR-001 Kernel.** A small, byte-stable standing steering artifact (protocol: state is
  authoritative, doctrine is fetched, gates are binding) plus the short judgment residue that
  no gate can check.
- **FR-002 Capsule emitter.** A surface that emits a bounded per-step capsule derived from
  engine state (`spec-kitty next --json` + the work package's own frontmatter) — never
  hardcoded.
- **FR-003 Pointers, not bodies.** The capsule carries required doctrine as fetch selectors
  with `when` guidance; bodies are retrieved on demand through the existing
  `spec-kitty charter context --include <selector>` surface.
- **FR-004 Gates.** A machine gate surface that runs the checkable invariants and **refuses**;
  the kernel defers to it. Gates are tested against planted violations.
- **FR-005 Lean driver.** A loop that feeds kernel + capsule to a model, executes its tool
  calls, and **tolerates batched tool calls** (multiple actions in one reply). The spike
  proved that a strict single-JSON parser turns a passing run into a false failure.
- **FR-006 Local-model routing.** The driver can route a step to the operator's configured
  model, with at least a retrieval tier (always local) and a draft tier (local model).
- **FR-007 Measurement.** A reproducible command reports standing and per-step steering sizes
  against a baseline.
- **FR-008 ADR resolution.** Resolve the tension with ADR 2026-07-28-1 (below) explicitly.

## Non-functional requirements

- **NFR-001 Budgets.** Kernel ≤ ~1 KB; capsule ≤ ~2 KB; measured, not asserted.
- **NFR-002 No engine fork.** Reuse the existing CLI; the change is additive.
- **NFR-003 Canonical retrieval.** Doctrine is fetched from canonical sources, never
  paraphrased.
- **NFR-004 Upstream-friendly.** Landable as a normal Mission/PR.
- **NFR-005 Verification.** The layer ships with tests; gates are falsifiable.

## Constraints

- **C-001** Reuse the engine; do not rewrite the state machine, reducer, or gates.
- **C-002** The requires-inline guarantee (ADR 2026-07-28-1) must be handled *explicitly* —
  amended upstream or documented as the single divergence. No silent erosion.
- **C-003** Canonical terminology: **Mission**, never "feature".
- **C-004** Must work on a 9B-class local model (proven bar).

## Out of scope

- Forking the engine; a standalone product; hosted surfaces; summarising canonical sources.

## Dependencies & sequencing

- Engine: `spec-kitty next`, `spec-kitty charter context` (present).
- **Blocking decision:** the ADR 2026-07-28-1 ruling (amendment vs divergence) — needed
  before the capsule can ship pointers in place of inlined `requires` bodies.
- Known issue surfaced by the spike: `charter context --mission-type <type> --json` fails in
  this checkout (internal org pack declares an unknown `skills` node kind) — unrelated to the
  Mission but blocking one code path; report separately.

## Success criteria

1. Measured ≥ 10× reduction on standing **and** per-step steering text, reproducible.
2. Gates preserve safety: planted-violation tests refuse; no invariant silently dropped.
3. A consumer 9B completes a real (not synthetic) work package through the loop.
4. The requires-inline tension is resolved by an explicit, recorded decision.

## Risks & open decisions

- **ADR 2026-07-28-1** — amend upstream, or carry as the single documented divergence?
- **Retrieval mechanism** — deterministic (FTS/keyword) vs embedding vs hybrid.
- **Tier defaults** — which steps route local vs remote.
- **Long-horizon robustness** — the loop test used a trivial task; a real multi-file WP is
  the true bar.

## Acceptance / how it is validated

- `make test-fast` plus the targeted tests of the touched modules (blast-radius rule).
- End-to-end on a scratch project: `spec-kitty init` in a temp dir, drive a Mission with the
  kernel + capsule + gates, on a local model.
- The measurement command reports the reduction.

## Evidence base (paths on this branch)

- `research-outputs/context-lean-steering.md`
- `research-outputs/context-format-experiment/`
- `research-outputs/lean-steering-spike/` (`sk.py`, `kernel.md`, `local_probe.py`,
  `lean_loop.py`, `README.md`, `compliance-experiment.md`, `lean-loop-test.md`)
