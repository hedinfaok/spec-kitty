# A/B/C steering experiment — results

**Date:** 2026-10-09
**Model:** `unsloth/Qwen3.5-9B-GGUF` (local, Ryzen AI Max+ 395, temperature 0)
**Harness:** `ab_test.py` — the production `driver` loop, same tool protocol, same binding
gate, same 20-turn budget; **only the seed differs.**
**Task:** a multi-step sandbox task — fix four functions in `calc.py` so `test_calc.py` passes,
without modifying the test file.

## Arms

| Arm | Seed | Seed size |
|---|---|---|
| `lean` | `steer kernel` + a task capsule | **1,638 B (~409 tok)** |
| `baseline` | the real standing corpus (`AGENTS.md`) + the mission's per-step context (spec/plan/tasks/WP) | **128,984 B (~32,246 tok)** |
| `capped` | baseline truncated to the lean budget | 2,180 B (~545 tok) |

## Results (5 runs per arm)

| Arm | Seed (~tok) | Success | Avg turns | Format errs | Protocol viol. |
|---|---:|---:|---:|---:|---:|
| `lean` | 409 | **5/5** | 6.0 | 0 | 0 |
| `baseline` | 32,246 | **5/5** | 5.0 | 0 | 0 |
| `capped` | 545 | **5/5** | 4.0 | 0 | 0 |

## Interpretation

**Supported: lean steering costs ~79× less steering context with no quality loss.**
`lean` (409 tok) matched `baseline` (32,246 tok) exactly — 5/5 success, 0 format errors, 0
protocol violations — and the task was completed (tests pass, test file unmodified) every run.
The ratio is **32,246 / 409 ≈ 78.8×**.

**Not shown: a quality *benefit*.** This is a **ceiling effect** — the task was within the 9B's
reach regardless of steering, so the baseline's 32k tokens of largely-irrelevant context
(spec-kitty's rules and an unrelated mission) did not degrade it. The 9B tolerated the noise.

**Steady-state latency did not differ** (lean ~3.6 s vs baseline ~3.8 s); the only notable
difference was cold-start (baseline 10.6 s vs lean 6.0 s on run 1).

## What this does and does not settle

- **Settled:** lean steering is **not worse**. A consumer 9B completes the same task at ~1/79th
  the steering context, with identical success. The thesis's *safety* half holds.
- **Open:** whether lean steering *improves* quality where the full context would cause context
  rot — a harder task, a longer horizon (so context accumulates), or a baseline context that is
  actively misleading. This experiment does not reach that regime.

## Threats (acknowledged)

- **Ceiling:** the task is within the 9B's ability in all arms — no discrimination on success.
- **Baseline proxy:** the baseline uses real spec-kitty content (AGENTS.md + a mission's
  spec/plan/tasks/WP, ~129 KB) rather than a freshly rendered action payload (~95 KB); it is a
  representative size, not a byte-exact capture.
- **Model robustness:** the 9B proved more tolerant of a large irrelevant context than assumed.
- **N = 5, temperature 0** — reliability under greedy decoding, not a distribution.
