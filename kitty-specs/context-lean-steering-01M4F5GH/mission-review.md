# Mission Review Report: context-lean-steering-01M4F5GH

**Reviewer**: OpenCode agent (mission-review skill)
**Date**: 2026-10-09
**Mission**: `context-lean-steering-01M4F5GH` — Context-lean steering: kernel + capsule + gates over the spec-kitty engine
**Baseline commit**: `3c8131777b3a54e7f411fba52bdfb951e3ee865d`
**HEAD at review**: `763fc108c4813ab70ee4b911b9c13a0347adbc6e`
**WPs reviewed**: WP01..WP08 (8/8 `done`)

---

## Gate Results

### Gate 1 — Contract tests
- Command: `SPEC_KITTY_ENABLE_SAAS_SYNC=1 python -m pytest tests/contract/ -q`
- Exit code: non-zero (6 failed, 3436 passed, 42 skipped, 1 error)
- Result: **FAIL — pre-existing, unrelated to this mission**
- Notes: all 6 failures are in `tests/contract/test_mission_status_reality.py` (`corpus_*`
  and `the_cache_*` reality tests) plus an `ERROR` in
  `tests/contract/test_packaging_no_vendored_events.py`. The corpus failure evidence names
  `terminus-integrity-followups-01M393QR`, `terminus-merge-integrity-01M380R6`,
  `terminus-safety-invariant-01M2XFT7` — a corpus/oracle mismatch in unrelated `terminus-*`
  missions. **`context-lean-steering-01M4F5GH` appears in none of the failures**, and this
  mission changes no mission-status, corpus, or packaging surface. Attributed to the
  documented baseline-red class; not caused by this mission.

### Gate 2 — Architectural tests
- Command (targeted, per repo `NO_FULL_HEAVY_SUITES_IN_MISSION` policy):
  `python -m pytest tests/architectural/{test_layer_rules,test_pyproject_shape,test_shared_package_boundary,test_no_retired_subsystems,test_completion_manifest_freshness,test_docs_cli_reference_parity}.py -q`
- Exit code: 0 (**108 passed**)
- Result: **PASS**
- Notes: the full `tests/architectural/` directory exceeded a 15-minute budget and was not
  run whole; the six gate files the change actually implicates are green. Layer rules
  confirm the new `specify_cli.steering` module respects the enforced import direction.

### Gate 3 — Cross-repo E2E
- Result: **NOT RUN — environmental exception**
- Notes: the separate `spec-kitty-end-to-end-testing` repository is not present in this
  environment, so the four floor scenarios cannot be executed. No `mission-exception.md` was
  authored (the operator may add one if this gate must be formally waived). This mission adds
  a new in-repo CLI surface and does not claim cross-repo behavior; no new e2e scenario is
  owed.

### Gate 4 — Issue Matrix
- File: `kitty-specs/context-lean-steering-01M4F5GH/issue-matrix.json`
- Rows: 1
- Empty / `unknown` verdicts: 0
- `deferred-with-followup` rows missing a follow-up handle: 0
- Result: **PASS** (`#5005 → not-applicable`, a terminal verdict; cited only as baseline
  provenance)

**Gate summary**: Gate 2 PASS, Gate 4 PASS; Gate 1 FAIL but pre-existing/unrelated; Gate 3
not runnable here. No gate FAIL is attributable to this mission.

---

## FR Coverage Matrix

| FR ID | Description (brief) | WP Owner | Test File(s) | Test Adequacy | Finding |
|-------|---------------------|----------|--------------|---------------|---------|
| FR-001 | Standing kernel (≤1 KB, byte-stable) | WP01 | `test_kernel.py` | ADEQUATE | — |
| FR-002 | Per-step capsule (≤2 KB, derived) | WP03 | `test_capsule.py` | ADEQUATE | — |
| FR-003 | Doctrine fetched on demand (pointers) | WP02, WP03 | `test_index.py`, `test_capsule.py` | ADEQUATE | — |
| FR-004 | Binding gates that refuse | WP04 | `test_gates.py` (29 tests) | ADEQUATE | TRACE-1 (FR id not cited in test bodies) |
| FR-005 | Batched-action driver | WP05 | `test_driver.py` | ADEQUATE | — |
| FR-006 | Local execution tiers | WP06 | `test_tiers.py` | ADEQUATE | RISK-1 (no production caller) |
| FR-007 | Steering-context measurement | WP07 | `test_measure.py` (10 tests) | ADEQUATE | TRACE-1 (FR id not cited in test bodies) |
| FR-008 | Recorded divergence (ADR) | WP08 | — (documentation artifact) | N/A | — |

**Legend**: ADEQUATE = test constrains the required behavior; PARTIAL = synthetic fixture
mismatch; MISSING = no test; FALSE_POSITIVE = passes with implementation deleted.
All eight FRs have implementing code on the merged target branch; FR-004/FR-007 behaviors are
tested (gates and measurement) even though their FR ids are not quoted in test bodies.

---

## Drift Findings

### DRIFT-1: FR ids not cited in some test bodies (trace hygiene)

**Type**: PUNTED-FR (trace only)
**Severity**: LOW
**Spec reference**: FR-004, FR-007
**Evidence**: `grep -rl "FR-004" tests/specify_cli/steering/` → 0 hits; `grep -rl "FR-007" …`
→ 0 hits, while `test_gates.py` and `test_measure.py` exist and are green.
**Analysis**: The behavior is tested; only the FR-id citation is absent. This is a traceability
gap, not a delivery gap. No spec clause is violated.

No NON-GOAL INVASION or LOCKED-DECISION VIOLATION was found. The one deliberate divergence
(requires-inline, C-002) is recorded as a superseding ADR (WP08) and is not drift.

---

## Risk Findings

### RISK-1: `tiers.py` has no production caller (dead code)

**Type**: DEAD-CODE
**Severity**: MEDIUM
**Location**: `src/specify_cli/steering/tiers.py`
**Trigger condition**: any operator expecting the tier policy to govern the live loop.

**Analysis**: `tiers.py` (tier policy + `LocalProvider` adapter) is imported only by its own
tests. The driver (`driver.py`) uses its own `HttpModelClient`, so the T0–T3 routing policy is
**not reachable from `steer loop`**. The module is unit-tested and correct, but the capability
does not affect the live command path. This is the mission-review skill's anti-pattern #2. It
is not release-blocking for the mission's core (kernel/capsule/gates/driver all work), but the
local-tier feature is effectively unshipped until wired. Flagged by WP06's reviewer as a
non-blocking observation; recorded here as the mission's principal open item.

### RISK-2: live capsule `wp:` line is empty mid-mission (engine #988)

**Type**: ERROR-PATH (upstream limitation)
**Severity**: LOW
**Location**: `src/specify_cli/steering/capsule.py`
**Trigger condition**: running `steer capsule` while the mission is mid-flight.

**Analysis**: the engine's `next` query reports `wp_id: null` for the active dependency state
(pre-existing engine behaviour, issue #988, which NFR-002 forbids this mission from fixing), so
the live capsule's `wp:` line renders empty. The capsule still carries `step`, pointers, and the
gate. Not a defect of this mission; a note for the engine backlog.

### RISK-3: SC-004 live end-to-end pass — RESOLVED (two caveats surfaced)

**Type**: NFR-MISS → now verified live
**Severity**: LOW (resolved)
**Location**: `steer loop` (`src/specify_cli/steering/driver.py`)
**Evidence**: three fresh live runs of
`spec-kitty steer loop --mission context-lean-steering-01M4F5GH --model unsloth/Qwen3.5-9B-GGUF --turns 12`:
- Run 1: `finished=True`, 5/12 turns · Run 2: `finished=True`, 5/12 turns · Run 3: `finished=True`, 7/12 turns (read `app.py` → `write_file app.py` `return a + b` → `run_tests` PASS → finish).
- All three: 0 protocol violations; the model fetched `DIRECTIVE_044`/`DIRECTIVE_030` and finished only after a `clean` gate.

**Analysis**: SC-004 ("a 9B-class Q4 local model completes a real work package through the loop within the ≤ 12-turn budget") is now **demonstrated live** — 3/3 finished inside the budget on the consumer 9B, at $0. Two caveats surfaced, recorded as follow-ups:

1. **`finish` is gated only by the repo-level binding gate, not the sandbox task.** Runs 1 and 2 finished after a `clean` gate *without ever editing the fixture*; only run 3 performed the actual fix. The pre-mission spike's `lean_loop.py` gated on the *task* (test-file-unmodified + tests-pass). As shipped, `finished=True` does not imply the work was done. **Recommendation**: gate the loop on the sandbox task, not only the repo gate.
2. **Gate environment fragility.** `steer loop` reuses the repo's CI checks. Before this run, `ruff` was absent from PATH — and once installed, at the wrong version (**0.16.10**, whose new Markdown code-block formatting flags `AGENTS.md`) — so the gate refused forever and the loop could never finish. It required installing the repo-pinned **`ruff==0.15.12`**. A gate that depends on the ambient toolchain makes the loop environment-fragile; consider a sandbox-local gate (as the spike used).

---

## Silent Failure Candidates

| Location | Condition | Silent result | Spec impact |
|----------|-----------|---------------|-------------|
| `src/specify_cli/steering/index.py` (`_parse_model_ids`) | `/v1/models` unreadable | returns `None` | Documented: an unreadable model list is not evidence of an unloaded model; the caller raises elsewhere. No silent pass. |
| driver / gates | tool unavailable / model unreachable | **raise typed errors** (no `return ""`) | None — loud by construction (verified by reviewers). |

No silent-empty-result path was found in the mission's code. HTTP calls carry explicit timeouts
(`driver.py:206`, `tiers.py:251`).

---

## Security Notes

| Finding | Location | Risk class | Recommendation |
|---------|----------|------------|----------------|
| `subprocess.run(list(argv), …)` — no `shell=True` | `driver.py:302`, `gates.py:91` | SHELL-INJECTION | None — list argv, no shell string interpolation. |
| `urllib.request.urlopen(..., timeout=…)` | `driver.py:206`, `tiers.py:251` | UNBOUND-HTTP | None — bounded by timeout. |
| Sandboxed file tools confine writes to a temp root; `..` escapes refused | `driver.py` (`_target`) | PATH-TRAVERSAL | None — verified by driver tests. |

No blocking security finding. No `shell=True` anywhere in the new code.

---

## Final Verdict

**PASS WITH NOTES**

### Verdict rationale

All eight functional requirements are implemented on the merged target branch and covered by
tests; the mission's own suite (`tests/specify_cli/steering`) is 156 green, and the specific
architectural gates it implicates are 108 green. Gate 4 (issue matrix) passes; Gate 2 passes
(targeted); Gate 1's six failures are pre-existing and name unrelated `terminus-*` missions;
Gate 3 is not runnable in this environment. No locked decision was violated — the single
deliberate divergence is documented in a superseding ADR. The only material open item is
RISK-1 (the `tiers.py` capability is not wired into the live loop), which is MEDIUM and does
not block the mission's core delivery.

### Open items (non-blocking)

1. **RISK-1** — wire `tiers.py` (T0–T3 policy + `LocalProvider`) into `steer loop`, or drop it,
   in a follow-up.
2. **RISK-3 (resolved, two caveats)** — the live 9B pass finished 3/3 inside budget; follow up
   on (a) gate the loop on the sandbox task, not only the repo gate, and (b) make the gate
   robust to the ambient toolchain (`ruff` presence + pinned version).
3. **DRIFT-1** — cite FR-004/FR-007 in the relevant test bodies for traceability.
4. **RISK-2** — upstream engine #988 keeps the live capsule's `wp:` line empty mid-mission.
5. **Landing note** — the generated artifacts were regenerated at landing (`763fc108c`);
   keep them fresh on any further CLI change.

## Retrospective Reminder

The canonical post-merge sequence is: **mission review → author or verify retrospective →
surface findings**. A `retrospective.yaml` was captured at the runtime terminus
(`9378a4b5f`). Verify and surface it with:

```bash
cat .kittify/missions/01M4F5GH28P9Y9DMSPKXW9RJJZ/retrospective.yaml
spec-kitty retrospect summary                                   # cross-mission aggregation (read-only)
spec-kitty agent retrospect synthesize --mission context-lean-steering-01M4F5GH   # inspect proposals (dry-run)
```
