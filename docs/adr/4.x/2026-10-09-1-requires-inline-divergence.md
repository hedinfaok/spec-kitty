---
title: 'ADR: inside a budget-constrained capsule, `requires` doctrine ships as fetch pointers, not inline bodies'
description: 'The lean steering capsule names each `requires`-closure artefact as a `{selector, when}` fetch pointer and retrieves bodies on demand through `charter context --include`; this partially supersedes the requires-eager inline clause of ADR 2026-07-28-1 while preserving fetchability, link-only `suggests`, and canonical retrieval.'
status: Accepted
date: '2026-10-09'
---

**Status:** Accepted

**Date:** 2026-10-09

**Deciders:** Operator (Stijn Dejongh). Resolved in the specification and plan interviews of Mission
`context-lean-steering-01M4F5GH` (Decision Moments `01M4F5S7X15RATYMKWZCAV8CWN` and
`01M4F6770GPKE0HZ3CCTN906P9`).

**Technical Story:** Mission `context-lean-steering-01M4F5GH` (`FR-008`, `C-002`; plan `IC-08`;
research `D-04`). Partially supersedes Decision item 2 of
[ADR 2026-07-28-1](../3.x/2026-07-28-1-progressive-disclosure-of-doctrine-context.md).

**Reader:** a maintainer of the lean steering layer (`src/specify_cli/steering/`) or of the charter
context renderers who needs to know why a `requires` target is named rather than inlined, and which
guarantees of ADR 2026-07-28-1 still bind.

---

## Context and Problem Statement

ADR [2026-07-28-1](../3.x/2026-07-28-1-progressive-disclosure-of-doctrine-context.md) made doctrine
context a **navigable link set**. Its Decision item 2 states that `requires` edges are *followed
eagerly* and their targets delivered *inline*: a required artefact is unconditional, has no `when`
to evaluate, and is therefore inlined rather than linked. Fetch-stanza treatment was reserved, by
name, for `suggests`.

That cadence is correct for a full charter-context load whose budget is 32,000 tokens. It does not
survive a **budget-constrained capsule**. Mission `context-lean-steering-01M4F5GH` assembles a
per-step capsule of **≤ 2 KB** so that a 9B-class local model can be steered on consumer hardware.
Measured against the doctrine corpus, inlining the `requires`-closure alone is **58–71 KB per
action** — the exact bloat the mission exists to remove, and 29–35× the entire capsule budget. A
capsule cannot inline even one step of the closure.

The two guarantees cannot both hold inside the capsule: **deliver every `requires` body inline** and
**stay under 2 KB**. The mission must choose which to relax, and it must record the choice rather
than let it drift silently.

## Decision

**Inside the lean capsule, `requires` doctrine is delivered as fetch pointers, not inline bodies.**

1. The capsule emits every `requires`-closure artefact as a `{selector, when}` **pointer** — its
   canonical selector plus its applicability guidance — and does not embed the artefact body.
2. Bodies are retrieved **on demand** through the existing canonical fetch surface,
   `spec-kitty charter context --include <selector>`. No new retrieval mechanism is built; the same
   surface ADR 2026-07-28-1 named as the fetch verb is the fetch verb here.
3. A pointer keeps every required artefact **addressable**: it names the artefact and how to reach
   it. It is not a summary, and it is not an omission.

This is the delivery cadence of the capsule only. It does not change DRG resolution, the
`references[]` DTO, the `suggests` link-only rule, or the `--include-all` escape hatch.

## Supersession boundary

### What is superseded

One clause, and only one: **Decision item 2 of ADR 2026-07-28-1** — the requires-eager **inline**
guarantee — and only **under a budget-constrained capsule**. Where the charter context is rendered
at full budget, the eager-inline cadence and everything else ADR 2026-07-28-1 decided remain in
force. Nothing else in that ADR is superseded or amended.

Specifically, this ADR does **not** supersede:

- the `references[]` element and its `{id, relation, when, reason}` shape (Decision item 1);
- the `suggests`-as-links rule and its `when` fetch guidance (Decision item 3);
- `charter context --include` as the fetch verb (Decision item 4);
- the `--include-all` escape hatch (Decision item 5);
- the default-cadence ordering constraint, or any of the "what this ADR does not decide" items.

### What still holds

- **Artefacts remain fetchable — nothing is omitted.** Every `requires`-closure artefact is named
  in the capsule and retrievable from canonical sources. Truncation removes an artefact from an
  agent's awareness; a pointer keeps it addressable. The NFR-003 property ADR 2026-07-28-1 protects
  — *delivery is complete, not truncated* — is preserved.
- **`suggests` stays link-only.** Unchanged; this ADR does not touch the `suggests` cadence.
- **Canonical retrieval is preserved — no paraphrase.** Bodies are fetched verbatim through
  `charter context --include`; the capsule never substitutes a lossy copy. This is the same reason
  ADR 2026-07-28-1 rejected summarising (a summary is a lossy copy that drifts from its source).
- **The `--include-all` escape hatch still materialises the whole closure inline**, for harnesses
  that ignore fetch instructions and for operators who want the entire chain.

## Rationale

**The pointer is the same shape the ADR already trusts.** ADR 2026-07-28-1 established that a link
keeps an artefact addressable and costs the same whether or not it is followed. Applying that shape
to the `requires` closure in the capsule is an extension of the ADR's own reasoning, not a departure
from it — the only change is *which* relation is linked when the budget is too small to inline it.

**It is the only way to hold the budget.** Inlining the closure is 58–71 KB per action; the capsule
budget is ≤ 2 KB. Pointers are the only representation of the closure small enough to fit.

**It keeps the divergence narrow and reviewable.** Relaxing one clause in one rendering context,
while naming that clause explicitly and preserving every other guarantee, is a smaller and more
honest change than inlining (blows the budget), summarising (drifts from canonical sources), or
silently dropping the closure (the defect class ADR 2026-07-28-1 exists to close).

## Alternatives considered

1. **Inline the `requires` closure in the capsule (status quo per ADR 2026-07-28-1).** Rejected: 58–71
   KB per action against a ≤ 2 KB budget. This is the bloat the mission removes.
2. **Summarise the closure into the capsule.** Rejected: a summary is a lossy copy that drifts from
   its source — the fresh instance of the defect class ADR 2026-07-28-1 rejected, relocated.
3. **Amend ADR 2026-07-28-1 in place.** Rejected: the ADR is Accepted and its eager-inline cadence is
   correct at full budget; editing it would misstate the general decision. A superseding ADR scoped
   to the constrained capsule records the divergence without rewriting history.
4. **Record the divergence in research output only.** Rejected: not discoverable from the code path it
   affects. The divergence must be reviewable from the capsule module.
5. **Pointers for the whole closure (chosen).** The closure is named as `{selector, when}` pointers and
   resolved on demand through the canonical fetch surface.

## Divergence

**This is the mission's single documented divergence.** Mission `context-lean-steering-01M4F5GH`
carries exactly one deliberate divergence from an Accepted ADR: the requires-inline erosion recorded
above. No other ADR or charter principle is diverged from, and the divergence is confined to the
capsule's rendering contract — it does not touch engine resolution (Charter Check re-check, plan).

- **Operator decision (2026-10-09):** *"Carry it as the single documented divergence (friendly
  fork)."* Recorded in Decision Moment `01M4F5S7X15RATYMKWZCAV8CWN` (specify
  `adr_requires_inline`); the recording shape — *a new ADR superseding the relevant clause* — is
  Decision Moment `01M4F6770GPKE0HZ3CCTN906P9` (plan `divergence_artifact`).
- **Constraint `C-002` (Documented divergence):** the ADR 2026-07-28-1 requires-inline guarantee is
  carried as a single, explicitly recorded divergence. This ADR is that record.
- **Cross-reference:** the mission plan's **Complexity Tracking** entry
  (`kitty-specs/context-lean-steering-01M4F5GH/plan.md` §Complexity Tracking) records the same
  divergence with its *Why Needed* and *Simpler Alternative Rejected Because* columns, and `IC-08`
  is the implementation concern that produces this ADR.

## Consequences

### Positive

- The capsule reaches its ≤ 2 KB budget while still naming the complete `requires` closure — the
  mission's token-pressure goal and ADR 2026-07-28-1's completeness property hold together.
- The `when` / `reason` edge data stays load-bearing: it is the pointer's guidance, exactly as it is
  for a `suggests` link.
- The divergence is discoverable from the code path (the capsule module cites this ADR) and from the
  mission plan, so a reviewer can find it without reading the whole history.

### Negative / risks

- **A pointer an agent never follows is a declaration that reaches nobody** — ADR 2026-07-28-1's own
  central risk, relocated onto the `requires` relation. The `--include-all` escape hatch remains the
  falsifiability backstop, and the agent-facing fetch instructions remain a quality concern (see
  ADR 2026-07-28-1, "what this ADR does not decide").
- **The capsule depends on a working fetch surface.** If `charter context --include` is unavailable,
  the closure is named but not reachable. The engine's fetch surface predates this mission and is
  unchanged.

### Neutral

- No change to the DRG schema, to `references[]`, or to the `suggests` cadence. This ADR changes the
  delivery cadence of one relation inside one rendering context.

## References

- Superseded (partially, one clause): [ADR 2026-07-28-1 — doctrine context is delivered as navigable
  links, not inlined bodies](../3.x/2026-07-28-1-progressive-disclosure-of-doctrine-context.md).
- Related: [ADR 2026-07-26-1 — DRG edges are the canonical relationship
  authority](../3.x/2026-07-26-1-drg-edges-are-the-canonical-relationship-authority.md).
- Mission `context-lean-steering-01M4F5GH`: [`spec.md`](../../../kitty-specs/context-lean-steering-01M4F5GH/spec.md)
  (`FR-008`, `C-002`), [`plan.md`](../../../kitty-specs/context-lean-steering-01M4F5GH/plan.md)
  (`IC-08`, Complexity Tracking), [`research.md`](../../../kitty-specs/context-lean-steering-01M4F5GH/research.md) (`D-04`, `D-05`).
- Operator decision record: Decision Moments `01M4F5S7X15RATYMKWZCAV8CWN` and
  `01M4F6770GPKE0HZ3CCTN906P9`
  ([`decisions/`](../../../kitty-specs/context-lean-steering-01M4F5GH/decisions/)).
