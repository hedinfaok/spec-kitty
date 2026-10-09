# Phase 0 Research: Context-lean steering

This file resolves every open planning question for mission
`context-lean-steering-01M4F5GH`. All Decision Moments were resolved and verified
(`decision verify` → clean) before planning.

## Decisions

### D-01 — Delivery surface: new subcommands on the existing CLI surface (Q1 = A)

- **Decision**: the layer ships as new commands on the existing `spec-kitty` CLI
  (`steer kernel|capsule|fetch|check|measure|loop`), backed by a new
  `src/specify_cli/steering/` module. No new artifact class is introduced.
- **Rationale**: most upstream-friendly; reuses the engine's resolution and doctrine
  surfaces; keeps a single install/upgrade path.
- **Alternatives considered**: (B) a separate in-repo module with a standalone driver reusing
  the CLI — rejected as the *primary* surface because it adds a second entry point to
  maintain; the spike's standalone driver is retained only as a reference. (C) a
  character pack/skill — rejected: the layer is code and tests, not prompt content.

### D-02 — Gates: reuse the existing suite + add a runtime check surface (Q2 = C)

- **Decision**: `steer check` aggregates (a) the existing CI-relevant checks (ruff,
  architectural rules, terminology) and (b) the mission's own gates (protected-branch
  refusal, engine guard failures, capsule/doctrine integrity). A refusal is binding.
- **Rationale**: the spike showed the agent must be able to run a gate *mid-loop*; CI alone
  is too late. Reusing the existing suite avoids reinventing checks.
- **Alternatives considered**: (A) reuse only — the agent has no runtime entry point;
  (B) a wholly new surface — duplicates existing gates.

### D-03 — Retrieval: query-time scan over an index built at install/first use (Q3 = A)

- **Decision**: build an on-disk index of doctrine ids → canonical source paths/anchors at
  install or first use (under `.kittify/`, gitignored), and resolve fetches by a
  deterministic query-time scan. Use stdlib `sqlite3` **FTS5** with a plain-JSON fallback
  when FTS5 is unavailable.
- **Rationale**: deterministic; no embedding model (honours C-005); no new dependency;
  rebuildable and inspectable.
- **Alternatives considered**: (B) a committed build-time artifact — adds a generated file to
  review and goes stale silently; (C) plain search with no index — acceptable but slower and
  less precise on the 3.2 MB doctrine corpus.

### D-04 — Divergence artifact: a new superseding ADR (Q4 = A)

- **Decision**: `docs/adr/4.x/2026-10-09-1-requires-inline-divergence.md` records that the
  capsule delivers `requires` doctrine as fetch pointers rather than inline bodies, states
  exactly which clause of ADR 2026-07-28-1 is superseded, and confirms what still holds
  (bodies remain fetchable; nothing is omitted).
- **Rationale**: durable, reviewable, and discoverable from the code (the ADR cite rule).
- **Alternatives considered**: (B) an amendment note on the existing ADR — weaker provenance;
  (C) a research-output record only — not discoverable from the code.

### D-05 — The capsule carries doctrine as pointers (the core mechanism)

- **Decision**: the capsule emits doctrine as `{selector, when}` pointers; bodies are fetched
  on demand through `spec-kitty charter context --include <selector>`.
- **Rationale**: inlining the `requires`-closure is 58–71 KB per action; pointers are the only
  way to reach the ≤ 2 KB budget. This is the divergence recorded in D-04.
- **Alternatives considered**: inline (status quo — blows the budget); summarise (drifts from
  canonical sources; rejected by the ADR itself).

### D-06 — The driver executes batched actions

- **Decision**: the driver parses the first JSON object from a reply and, when more actions
  follow in the same reply, executes them in order.
- **Rationale**: the spike proved that a strict single-JSON parser turns a passing run into a
  false failure (the 9B emitted `write_file` followed by `run_tests` in one turn).
- **Alternatives considered**: require exactly one action per reply — brittle across models.

### D-07 — Local execution tiers T0–T3

- **Decision**: implement the tier policy: T0 retrieval (always local), T1 routing, T2
  drafting, T3 full loop, targeting a local OpenAI-compatible server.
- **Rationale**: operator selected full tiers (Q3 in specify); a 9B Q4 local model is the bar.
- **Alternatives considered**: retrieval-only or retrieval + draft — deferred value the
  operator asked to include.

### D-08 — Reuse the engine; additive seams only

- **Decision**: no state-machine, reducer, reconciliation, or gate module is rewritten.
- **Rationale**: C-001 / NFR-002; the engine is where the expensive correctness lives.
- **Alternatives considered**: forking the engine — explicitly out of scope.

## Open clarifications

None. All Decision Moments for this Mission are resolved; `decision verify` reports
`status: clean` with `marker_count: 0`.

## Supply-chain security

No dependency is added, upgraded, or removed: the layer uses the Python standard library
plus the existing engine. Per `DIRECTIVE_051` and the `supply-chain-install-safety` tactic,
there is no new install to vet; this is recorded as **N/A with rationale** rather than left
silent.

## Adversarial evidence

No security-impacting dependency decision was made (no new dependency), so the adversarial
dependency challenge in the `adversarial-squad-deployment` procedure is **deferred with this
rationale** and recorded here, not dropped. The mission's own riskiest decision — the
requires-inline divergence — is recorded as an explicit ADR (IC-08), not silently applied.
