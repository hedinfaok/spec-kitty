# Compliance experiment: is a ~1.4 KB capsule enough to orient a fresh agent?

**Branch:** `spike/context-lean-steering`
**Op:** `01M4F306FG8MSNBPZPGFAD1FAA` (profile `researcher-robbie`)
**Date:** 2026-10-08
**Question:** The spike proved the *size* reduction. This experiment asks whether the text
is *sufficient* — can a fresh agent, handed only the kernel + capsule, correctly orient
itself on a real mission step?

## Method

Four fresh agents (no shared context between them), each given only text from this
message, each instructed **not to use tools, read files, or run commands**, and to echo
"NOT IN CAPSULE" where the text lacks an answer.

**Model under test:** all four runs used `opencode-go/deepseek-v4.1-flash` (variant
`high`) — the harness default. Recorded because it is material: the result describes
*this* model, not every model. Total cost of the four runs was ~5,400 tokens (~$0.0019).

| Run | Condition | Text given |
|---|---|---|
| B1 | kernel + capsule | ~1.4 KB |
| B2 | kernel + capsule (repeat) | ~1.4 KB |
| A1 | **kernel only** (control) | ~1.0 KB, no capsule |
| C1 | kernel + **degraded** capsule (control) | capsule with the WP/files/subtasks lines removed |

Scoring is against ground truth taken from the engine (`spec-kitty next`, the WP
frontmatter) — facts that appear **nowhere in `AGENTS.md`**, so a correct answer can only
come from the capsule.

Ground truth: step `implement` · WP01 "next --json claimability parity" · owned files
`src/specify_cli/next/**`, `src/specify_cli/cli/commands/next_cmd.py`,
`tests/next/test_next_claimable_payload.py` · subtasks T001–T003 · slug
`workflow-parity-988-989-991-01KRKTT5` · gate `python3 sk.py check --mission …` (refusal
binding) · refs FR-001/002/003/010, C-001 · fetch a pointer before "when doing X".

## Results

| Run | Condition | Score |
|---|---|---|
| B1 | kernel + capsule | **8 / 8 correct** |
| B2 | kernel + capsule | **8 / 8 correct** |
| A1 | kernel only | **3 / 3 correct** (protocol held) |
| C1 | degraded capsule | 2 answered; 3 correctly reported "NOT IN CAPSULE" |

**B1** answered every question correctly and gave `FIRST ACTION: ask the engine for
authoritative state, then read the charter`. **B2** answered every question correctly and
gave `FIRST ACTION: run the binding gate`. Both correctly described pointer handling
("fetch it before doing X") and the binding meaning of a gate refusal.

**A1 (kernel-only control):** correctly *declined to guess* ("No. Protocol rule 1 is
explicit: never guess the step, the work package, or the branch"), named the exact command
`python3 sk.py capsule --mission <slug>`, and named the one required input — the mission
slug. The kernel's protocol works without the capsule.

**C1 (degraded-capsule control):** answered `implement` and the slug, and returned "NOT IN
CAPSULE" for the work package, editable files, and subtasks. The test discriminates: it
does not reward guessing.

## Findings

1. **A ~1.4 KB kernel + capsule is sufficient to orient a fresh agent** on a real step:
   step, work package and title, editable files, subtasks, requirement refs, the binding
   gate, and the fetch protocol — all recovered correctly, twice.
2. **The kernel alone steers the protocol, not just the content.** With no capsule, the
   control did the *right* thing — ask the engine, do not guess — which is the behaviour
   the "state is authoritative" rule is for.
3. **The test has signal.** The degraded control failed exactly where content was removed
   and nowhere else.

## Caveats

- **One model only — and a frontier-tier one.** Every run used
  `opencode-go/deepseek-v4.1-flash` (high). A capable model orienting itself from 1.4 KB
  does **not** prove a small local model can; the community's 30B-MoE target needs its own
  run. This is the single most important limit for the consumer-hardware goal.
- **Isolation is not absolute.** The sub-agents ran inside a harness that may inject its
  own system prompt/`AGENTS.md`. But every scored fact is mission-specific and absent from
  the standing corpus, so correct answers demonstrate the capsule carried them; and the
  agents were instructed to use no tools. It is a *sufficiency* test, not a proof of
  airtight isolation.
- **N = 2 for the main condition.** Directional, not a distribution. A larger run would
  firm it up.
- **Orientation ≠ multi-turn compliance.** This measures whether an agent can *read* the
  steering correctly, not whether it obeys every rule across a long edit/verify loop.
- **No work was actually performed** (no files changed), by design.

## Verdict

The capsule is **sufficient for orientation** and the kernel is **sufficient for
protocol**, at ~99× and ~85× less context respectively. Combined with the spike's size
result, the lean-steering shape is viable. The remaining risk is no longer orientation; it
is long-horizon behavioural compliance — which needs a task-level trial, not this test.
