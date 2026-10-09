# Spike: lean steering (kernel + capsule + gates) over the spec-kitty engine

**Branch:** `spike/context-lean-steering` (off `research/context-lean-steering`)
**Op:** `01M4F2P98PRK4JTY9CYTZYJZ0N` (profile `researcher-robbie`)
**Date:** 2026-10-08
**Status:** Spike complete — hypothesis largely confirmed; see decision and residuals.

This spike answers the question the research doc left open: *can a lean steering layer
reuse the existing spec-kitty engine, or does it need a fork?* It builds the smallest
credible thing — a static kernel, a per-step capsule, and gates — and measures it on a
real mission.

---

## Hypothesis

**H1.** A thin lean-steering layer that reuses the `spec-kitty` CLI as the engine —
emitting a ~1 KB **kernel** plus a bounded per-step **capsule** instead of the standing
corpus (~101 KB every turn) and the action payload (81–95 KB on first load) — can drive a
real Mission step with roughly two orders of magnitude less steering context, while
keeping machine-checkable invariants enforced by **gates**.

## Timebox and safety

One bounded session. Safe-to-fail: a dedicated branch, **no engine changes** — the
prototype only reads the engine (`spec-kitty next`, `spec-kitty charter context`) and emits
different text.

## Exit criteria and results

| # | Criterion | Result |
|---|---|---|
| E1 | A working prototype that reuses the engine | **Met** — `sk.py` (`kernel`, `capsule`, `fetch`, `check`, `measure`) |
| E2 | ≥10× steering-context reduction on a real mission | **Met** — 98.9× (standing), 84.9× (first-load payload), 11.3× (compact payload) |
| E3 | Gates enforce the machine-checkable invariants | **Met (thin)** — `sk check` refuses on a protected branch and on engine guard failures |
| E4 | Capsule completeness — no required field dropped | **Partial** — names step, WP, title, refs, owned files, subtasks; doctrine delivered as fetch pointers |
| E5 | A written finding | **This document** |

## Measurements

Command: `python3 sk.py measure --mission workflow-parity-988-989-991-01KRKTT5`.

Per turn (standing steering text):

| | bytes | ~tokens | reduction |
|---|---:|---:|---:|
| today: standing corpus (`AGENTS.md` + overrides) | 101,438 | 25,359 | — |
| spike: kernel | 1,026 | 256 | **98.9×** |

Per step (action payload):

| | bytes | ~tokens | reduction |
|---|---:|---:|---:|
| today: payload, first load (`#5005` §9.2) | 95,139 | 23,784 | — |
| today: payload, compact (`#5005`) | 12,614 | 3,153 | — |
| spike: capsule | 1,121 | 280 | **84.9×** vs first load, **11.3×** vs compact |

The capsule is emitted from real engine state (`spec-kitty next --mission … --json`) plus
the work package's own frontmatter — not hardcoded:

```
# CAPSULE — workflow-parity-988-989-991-01KRKTT5
step: implement
mission_type: software-dev
wp: WP01 — next --json claimability parity
progress: 0/3 done, 3 planned
owned_files: src/specify_cli/next/**, src/specify_cli/cli/commands/next_cmd.py, tests/next/test_next_claimable_payload.py
subtasks: T001, T002, T003
requirement_refs: FR-001, FR-002, FR-003, FR-010, C-001

## Fetch when needed (do not request all of it)
- `spec-kitty charter context --include directive:DIRECTIVE_044` — when choosing a template/command or tempted to improvise a substitute
- `spec-kitty charter context --include directive:DIRECTIVE_030` — before declaring the change done (test + typecheck gate)
...
## Binding gate
- run `python3 sk.py check --mission workflow-parity-988-989-991-01KRKTT5`; a refusal is binding — fix its cause
```

And the retrieval path is engine-provided and works on demand — for example
`python3 sk.py fetch directive:DIRECTIVE_030` returns the 4.6 KB body only when asked.

## What the spike proved

1. **The engine does not need forking for the delivery layer.** The prototype reads
   `spec-kitty next` and `spec-kitty charter context`; the state machine, mission files,
   and doctrine resolution all stay where they are. This is the central result: the
   context problem and the engine are separable.
2. **The reduction is real and large.** ~99× on the per-turn text and ~85× on the
   first-load payload, with the numbers reproducible from a one-line command.
3. **The wall is exactly where the research predicted.** To reach ~1 KB the capsule
   carries doctrine as **pointers**, not inlined bodies — the same collision with
   ADR 2026-07-28-1 ("`requires` edges are delivered inline") that blocked the deferred
   `#5005` fix. So this shape needs either an upstream ADR amendment or a deliberate
   divergence. **This is the one genuine fork-worthy question the spike surfaced.**

## What it did NOT prove (residuals)

- **No LLM was driven at task level.** The spike measures steering *size* and gate
  *enforcement*; the follow-up `compliance-experiment.md` shows a fresh agent can *orient*
  correctly from kernel + capsule, but long-horizon behavioural compliance (a full
  edit/verify loop) is still untested.
- **The pointer map is illustrative** (`POINTERS` in `sk.py`), not derived from the
  engine's DRG or the WP's agent profile. Production wiring must make it engine-derived.
- **The gate set is thin** (protected branch + engine guard failures). The full gate
  suite (architectural rules, ruff, terminology, merge integrity) already exists in CI;
  the spike shows the *pattern*, not the complete set.
- **Local/consumer-hardware routing is designed, not built** (see below).

## Consumer-hardware extension (design only)

For a community on consumer hardware, the kernel's protocol is deliberately
model-agnostic. A `sk route <step>` would pick a tier per step:

| Tier | Runs | For |
|---|---|---|
| T0 retrieval | local (NPU/iGPU) | index + fetch — no API cost |
| T1 router | local small model | which slice / which model |
| T2 draft | local 30–35B MoE | mechanical steps (summarise, draft, route) |
| T3 full loop | local 120B-class | latency-tolerant work, zero API |

## Decision

**Proceed.** The delivery layer is reusable over the engine, so the cost of a fork is not
justified by this spike. Recommended shape:

1. **Upstream-first:** prototype the kernel/capsule/gate delivery as an in-repo change (a
   Mission), reusing the engine — this is the "upstream-friendly" path.
2. **One explicit divergence to negotiate:** the requires-inline guarantee (ADR
   2026-07-28-1). Either amend the ADR upstream, or carry it as the single, documented
   divergence in a "friendly fork".
3. **Compliance experiment (done):** [`compliance-experiment.md`](compliance-experiment.md) —
   fresh agents oriented correctly from kernel + capsule (8/8, twice), with both controls
   holding. The open question is now long-horizon behavioural compliance, not orientation.

## Reproduce

```bash
cd research-outputs/lean-steering-spike
python3 sk.py kernel
python3 sk.py capsule --mission workflow-parity-988-989-991-01KRKTT5
python3 sk.py fetch directive:DIRECTIVE_030 | head
python3 sk.py check   --mission workflow-parity-988-989-991-01KRKTT5
python3 sk.py measure --mission workflow-parity-988-989-991-01KRKTT5
```

## Observation (out of scope, worth recording)

`spec-kitty charter context --action implement --mission-type software-dev --json` fails in
this checkout: the internal org pack (`packs/internal/drg/fragment.yaml`) has nodes with an
unknown kind `skills` (not in the canonical org-pack kind universe). This is a pre-existing
defect unrelated to the spike, but it blocks the `--mission-type` code path and is worth a
separate report.
