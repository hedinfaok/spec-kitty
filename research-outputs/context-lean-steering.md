# Research: A context-lean, local-capable alternative to statute-stuffing

**Branch:** `research/context-lean-steering`
**Op:** `01M4F0SF732J47E3V5GYG56DRQ` (profile `researcher-robbie`)
**Date:** 2026-10-08
**Status:** Research finding. **No plan committed** — this document maps the design space and the decision points, per operator direction ("just a research doc; I'm not sure what the plan should be yet").
**Scope:** How to steer an LLM agent with far less standing context than Spec Kitty sends today, in a way that is *also* able to run against local models on an AMD Ryzen AI Max+ 395 (Strix Halo, 128 GB unified).

> **Method.** All internal figures are either (a) measured on this checkout, (b) cited to a file in this repo with line numbers, or (c) cited to a prior Spec Kitty mission's reviewed research. External claims carry links. Where a number is an estimate it is labelled "est." Nothing here is a proposal to implement; it is a map.

---

## TL;DR

1. **Spec Kitty steers by statute.** Every rule is written as prose and pushed into the model on every turn, in two separate channels: a **standing corpus** (`AGENTS.md` and friends) and a **per-action governance payload** (the charter/doctrine render). None of it is pruned to what the current turn needs.
2. **The standing instruction files are ~101 KB (~25k tokens) re-sent every turn before the task starts** (`AGENTS.md` + the overrides file), and one third of `AGENTS.md` is a single reference section that is irrelevant to almost every turn.
3. **The per-action payload was already measured at 81–95 KB for `specify`/`plan`/`tasks`/`implement`/`review`** by mission `analyze-prompt-context-load` (issue #5005), and the fix was deferred to the maintainer. 71–75% of it lives in an "Action Doctrine" block that the existing 40k-char budget enforcer structurally cannot see.
4. **The alternative is not "a smaller constitution".** It is a change of mechanism: a **tiny invariant kernel + a bounded per-turn capsule + just-in-time retrieval + machine gates**. Every invariant a tool can *check* should be deleted from the prompt, because a gate costs **0 tokens/turn** and is **100% reliable**, while prose costs every turn and is advisory.
5. **Local-capability is a second, independent lever.** The Ryzen box can host the retrieval index, a router/compressor, a drafting model, or the whole loop — which either removes API tokens entirely or cuts them to "hard judgment only".
6. **Seven levers exist; they compose.** They differ mainly in blast radius, reversibility, and how much they depend on the harness vs. the CLI. Sections 5–6 grade them; Section 9 lists the open questions a plan would have to answer.
7. **Format is second-order; the mechanism is first-order.** Models read JSON/config perfectly well, but format only primes a *mode* — the win is *what is in the prompt at all*. Measured on this repo's own rules: Markdown 593 est. tokens, JSON 759, gate + kernel 125 — with enforcement going from 0/8 to 6/8 (§4).

---

## 1. The problem, measured

There are two distinct context channels. They have different lifecycles and different fixes, and today they are conflated.

### 1.1 Standing context — paid on *every* turn

The harness (OpenCode, Claude Code, Codex…) reads project instruction files at session start and re-sends them in every request. In this repo:

| Artifact | Bytes | ~Tokens (est. ÷4) | Lifecycle |
|---|---:|---:|---|
| `AGENTS.md` (identical content served as `CLAUDE.md` via symlink) | 93,899 | ~23,500 | every turn |
| `.kittify/overrides/AGENTS.md` | 7,539 | ~1,900 | every turn |
| Skill catalog (51 skills; name + description only) | — | ~3,000–5,000 (est.) | every turn |
| Orientation block + tool catalog + harness preamble | — | ~2,000–4,000 (est.) | every turn |
| **Standing subtotal** | | **~30,000–35,000** | **every turn** |

Measured facts:
- `AGENTS.md` is 93,899 bytes, 771 lines.
- Its single largest section is **"Consolidation & Preflight Patterns" at ~30,711 bytes — roughly one third of the whole file** — a dense reference for merge-integrity edge cases that is relevant to one phase of one mission type and irrelevant to almost every other turn.
- For comparison, the project charter (`charter.md`, 44,001 bytes) is *smaller* than the standing agent file; the machine charter (`charter.yaml`, 154,952 bytes) is far larger but is only pulled on demand through the CLI.

The design intent behind a large `AGENTS.md` is defensible — "the agent must never miss a rule." But it is exactly the strategy Anthropic's context-engineering guidance argues against: aim for *the smallest set of high-signal tokens*, not the most tokens.

### 1.2 Per-action governance payload — paid per step

Independently, the runtime splices a charter/doctrine payload into each action prompt. Mission `analyze-prompt-context-load-01M3F4BV` measured this through the real render entry point (`charter.activation.scope_router.build_with_scope`), with first-load state cleared:

| Action | Render mode | Bytes | % in "Action Doctrine" block |
|---|---|---:|---:|
| `implement` | bootstrap | 95,139 | ~75% |
| `review` | bootstrap | 93,799 | ~74% |
| `tasks` | bootstrap | 83,431 | ~72% |
| `plan` | bootstrap | 82,707 | ~71% |
| `specify` | bootstrap | 81,476 | ~71% |
| `analyze` / `accept` / `research` | compact | 4,571 | — |

Source: `kitty-specs/analyze-prompt-context-load-01M3F4BV/research.md` §9.2.

Three structural findings from that mission matter here:

1. **It is a first-load spike per checkout, but it recurs.** `.kittify/charter/context-state.json` is local and gitignored (`.gitignore:90`), so every fresh clone, every new lane worktree, and every CI checkout pays the bootstrap render again the first time each of the five actions is touched.
2. **The budget enforcer runs but cannot see the problem.** `BUDGET_DEFAULT = 40_000` chars (`src/charter/activation/context_renderers/token_budget.py:63`) is enforced by `_enforce_token_budget`, whose candidates come only from the *section*, *profile*, and *selection* blocks — **never from the Action Doctrine block**, which is 71–75% of the bytes. The render lands at 1.9–2.4× its own budget.
3. **Progressive disclosure already bounds the block to its `requires`-closure** — so the 58–71 KB measured is *already* the cheap subset. The `software-dev` action nodes simply have large unconditional closures.

The fix for (2) was **deferred to the maintainer** by operator decision and is tracked on #5005; it is not implemented.

### 1.3 What a fresh work package actually pays

Combining the two channels: a fresh lane worktree beginning `implement` starts around **~101 KB standing + ~95 KB governance ≈ 196 KB (~49k tokens) of steering context before the task content** — and the standing half is re-paid on every subsequent turn.

> **Measurement caveat (documented by the #5005 mission, and reproduced here).** The `charter context` CLI is *destructive to the state it measures*: the first run pays bootstrap and then marks the action loaded, so a second run is compact. My own ad-hoc CLI readings varied between ~238 KB, ~7 KB, and ~2 KB depending on prior state and flags. **Do not cite ad-hoc CLI byte counts**; cite the §9.2 render-path numbers or clear/restore `context-state.json` deliberately. This is itself evidence for the point in §5-L4: state that affects the prompt should be explicit and inspectable, not an invisible side effect.

### 1.4 Prior art *inside this repo*

- **`docs/adr/3.x/2026-07-28-1-progressive-disclosure-of-doctrine-context.md`** — decided doctrine ships as *navigable links* (`requires` inline, `suggests` as `when`/`reason` fetch stanzas) with an `--include-all` hatch. This is the right instinct, applied only to *rendered doctrine*.
- **`docs/adr/2.x/2026-02-11-2-fresh-context-execution-mode.md`** — "Fresh Context Execution Mode" (Ralph-style per-subtask reset). Status: **Proposed**, no implementation found.
- **`docs/adr/3.x/2026-03-09-1-prompts-do-not-discover-context-commands-do.md`** — context resolution belongs to commands, not to prompt-side discovery.
- **`src/charter/activation/compact.py`**, `progressive_disclosure.py` — a compact view and link-emission already exist.
- **`spec-kitty next`** already returns a small *decision record* (a query response is ~600 bytes of JSON with `action`, `wp_id`, `prompt_file`, `reason`, `progress`). The heavy part is the `prompt_file` it points at.

So the repo already contains most of the *mechanisms*; what it lacks is a decision to make them the **only** channel, and to apply them to the **standing** corpus, not just the doctrine render.

---

## 2. Diagnosis: the pattern, not the file

"Make `AGENTS.md` smaller" is a symptom fix. The underlying pattern is:

**P1 — Steering is treated as statute.** Correct behavior is believed to come from the model *reading a rule*. Therefore every rule must be present every turn. The cost is `turns × corpus`, nearly independent of the task.

**P2 — Prose is used as the enforcement mechanism.** A rule in prose is (a) re-paid every turn, (b) advisory — the model can ignore or misread it, and (c) duplicated across `AGENTS.md`, `charter.md`, directive YAML, mission-step prompts, and skills, where copies drift.

**P3 — Reference is confused with instruction.** Deep, phase-specific reference (merge integrity, copy-on-write adjudication, evidence gates) is inlined into the always-on file. A human would not put the appendices of a manual in the greeting.

**P4 — Lossy summarisation was explicitly rejected.** ADR 2026-07-28-1 rejected "summarise bodies instead of linking" because *"a summary is a lossy copy that drifts from its source."* That is correct — and it is why the only sound levers are **retrieval** (fetch the canonical source) and **deletion** (remove from the prompt entirely), never paraphrase.

The alternative thesis, in one line:

> **Steer by state machine + just-in-time retrieval + machine gates, not by a standing body of prose.**

---

## 3. First principles

1. **Context is finite and rivalrous.** Every steering token is a token unavailable to the task *and* paid on every request. This is the framing in Anthropic's *Effective context engineering for AI agents*: find the *smallest possible set of high-signal tokens* that still produces the outcome.
2. **Context rot is real.** Recall degrades as the window fills; irrelevant content actively increases error. More window does not fix it.
3. **Keep the prefix stable.** Providers cache a stable prompt prefix at a large discount; a harness that rebuilds the whole prompt each turn (as the structural-codebase-index literature notes of Aider) forfeits that. → Put the *invariant kernel* first and make it byte-stable; put the *volatile capsule* last.
4. **Prefer the smallest mechanism that is verifiable.** A rule that a hook, linter, or gate can *check* should not be prose at all. Deletion is strictly better than summarisation (no drift) and than prose (no per-turn cost, no ambiguity).
5. **Determinism beats discovery.** Spec Kitty already ruled (ADR 2026-03-09-1) that commands resolve context, not prompts. The alternative pushes that to its conclusion: the *only* per-turn steering the model receives should be what a deterministic command emitted for this exact step.

---

## 4. Format is not the lever: Markdown vs JSON vs gates

A natural question: if the standing corpus is the problem, do we even need to render it
as Markdown — are models smart enough to be steered by JSON or config? The answer is that
**comprehension was never the constraint**, and format is the wrong axis.

### 4.1 Models can be steered by any format — but format is not inert

Same content under a different wrapper produces measurably different behaviour. In *Does
Prompt Formatting Have Any Impact on LLM Performance?* ([arXiv 2411.10541](https://arxiv.org/html/2411.10541v1)),
identical content across plain-text/Markdown/YAML/JSON swings accuracy widely and
**model-dependently** — e.g. GPT-4-1106 HumanEval scores Markdown 86.6 vs JSON 21.95,
while GPT-3.5 can go the other way. The format primes a *mode*: JSON context reads as
schema-extraction/completion, Markdown reads as hierarchical synthesis (and is the register
models were trained on most heavily), terse imperatives read as direct instruction. A
behavioural rule buried in a JSON string is more likely to be treated as *data to complete*
than an *instruction to obey*.

Structured output is a separate reliability story: **schema validity is easy, semantic
correctness is not** ([arXiv 2607.18261](https://arxiv.org/html/2607.18261v1) — a 120B model
hits 100% schema validity but ~81–83% semantic success; a 30B model is 100% schema-valid and
~31% semantically correct). Constraining the *shape* does not constrain the *judgment*.

### 4.2 JSON is usually *bigger* for prose-shaped content

For natural-language rules, JSON adds tokens (keys, braces, quotes) rather than removing
them. Measured on this repo's own eight-rule sample: Markdown 2,372 bytes vs JSON 3,035
bytes — **JSON is ~28% larger**. Migrating an instruction corpus Markdown→JSON would cost
more per turn and, per §4.1, reduce salience.

### 4.3 The real axis: three kinds of content, three homes

| Kind of content | Home | Does the model read it? | Example |
|---|---|---|---|
| Checkable invariant | a **gate** (hook / linter / CI / config) | **no** | "never push to `main`" |
| Fact / state / enum | **structured query** on demand | only the slice asked for | the lane state machine |
| Behavioural judgment | a small **prose kernel** | yes | "prefer a durable fix over a shim" |
| Deep reference | **retrieved canonical text** | on demand | merge-integrity edge cases |

So the move is not Markdown→JSON. It is **delete most of the prompt** by moving checkable
rules into gates and state into queries, leaving a tiny prose kernel for what is genuinely
behavioural. Markdown's role shrinks to the kernel and to retrievable reference.

### 4.4 The measured result

[`context-format-experiment/`](context-format-experiment/) encodes the same eight rules
three ways and measures what enters the model's context:

| Encoding | ~tokens in context | Rules enforced |
|---|---:|---|
| A. Markdown prose | 593 | 0/8 (advisory) |
| B. JSON config | 759 | 0/8 (advisory) |
| C. Gate + kernel | 125 | 6/8 by construction |

Encoding C is ~4.75× smaller than Markdown and ~6× smaller than JSON — because six of eight
rules left the prompt and became a program (`check_policy.py`) the model never reads and
cannot misread. A gate costs **0 tokens/turn**; the kernel pays only for the judgment
residue. The experiment also demonstrates the gate catching planted violations (forbidden
term, blanket `# noqa`, trailing whitespace, protected branch, bad commit subject) that the
prose and JSON encodings would only advise against.

### 4.5 Nuance for the local tier

Small models (the local offload on the Ryzen) are the *most* format-sensitive and the
*least* semantically reliable under constraint. Use grammar-constrained structured output
for mechanical steps (routing, classification, extraction) — it removes format errors by
construction — but keep verification/gates for judgment. The API model carries the prose
kernel's judgment calls.

**Net:** terse prose for the behavioural kernel, structured queries for state, gates for
invariants — do not migrate prose policy to JSON.

---

## 5. The design space — seven levers

These are **grades**, not a menu; they compose. Each is scored on impact, effort, reversibility, and whether it lives in the CLI or the harness.

### L1 — Trim and restructure the standing corpus
Move phase-specific reference (e.g. "Consolidation & Preflight Patterns") out of `AGENTS.md` and behind an on-demand fetch; keep only invariants that apply to *every* turn.
- **Impact:** medium (≈ −1/3 of standing bytes here). **Effort:** low. **Reversible:** yes (git).
- **Limitation:** it is trimming, not a mechanism. The file regrows because nothing forces the boundary. Needs a rule (or a gate) that says "this prose may not live in the always-on file."

### L2 — Compile doctrine into an index + just-in-time retrieval
Build a versioned, queryable index over `AGENTS.md`, `charter.md`, `charter.yaml`, the 3.2 MB `packs/built-in/` doctrine, and the Mission specs. Retrieve by keyword (FTS/deterministic) and/or embedding. The agent fetches the slice it needs; the full corpus never enters context.
- **Impact:** high. **Effort:** medium–high. **Reversible:** yes.
- **Prior art:** Aider's PageRank repo-map (tree-sitter symbols fitted to a ~1k-token budget); Agent Skills progressive disclosure (metadata always, instructions on activation, resources on execution); `llms.txt`.
- **Constraint:** retrieval must be **canonical** (fetch the source file, never a paraphrase) or it reintroduces P4's drift.

### L3 — State-machine capsules + stable-prefix caching
Define a **kernel** (tiny, invariant, cacheable) and a **capsule** (per-step, bounded, emitted by `spec-kitty next`). The kernel says only: identity, the state machine, "state is authoritative — ask the CLI", and "obey gate refusals". The capsule carries the current step, its acceptance criteria, the doctrine that is `requires` (inline, because unconditional), and `suggests` as one-line pointers.
- **Impact:** high; turns steering into a bounded function of state. **Effort:** medium. **Reversible:** yes.
- **Illustrative sizes (not commitments):** kernel ≲ 1 KB; capsule ~1–3 KB vs. today's ~26 KB standing + up-to-95 KB payload.
- **Enabler already present:** `spec-kitty next` returns a compact decision record today; the work is to make its *pointed-to* payload equally lean and to stop shipping a standing corpus alongside it.

### L4 — Move enforcement from prose to gates (policy-as-code)
For every invariant that can be *checked*, delete the prose and replace it with a deterministic check: pre-commit hook, `spec-kitty doctor`, a linter, a CI gate. Examples already in the repo's spirit: `ruff`, the architectural layer rules, the retired-subsystem scan, the terminology guard, the git/workflow guards.
- **Impact:** high on safety-per-token, and the only lever that *increases* reliability while cutting cost. **Effort:** medium–high (one check per invariant). **Reversible:** each check independently.
- **Key property:** a gate costs 0 tokens/turn and cannot be "misread." The kernel only needs "if a gate refuses, follow its message."
- **Boundary:** not everything is checkable (judgement calls, design intent). Those stay as retrieval-linked guidance, not standing prose.

### L5 — Sub-agent context isolation (and fresh-context)
Route heavy reading to sub-agents that return only a summary; reset context at step boundaries (the unimplemented ADR 2026-02-11-2). The orchestrator's own context stays tiny.
- **Impact:** medium–high on the *main loop*; trades spawn latency for a smaller, less-rotted window. **Effort:** medium. **Reversible:** yes.
- **Caution:** summaries *are* lossy (P4). Use them to isolate work, not to replace canonical sources the agent must act on.

### L6 — Local-capable execution (the Ryzen lever)
Make every layer above able to run locally, in tiers:
- **T0 Retrieval (always local):** embeddings + FTS + a tiny classifier on the NPU/iGPU. No API cost, no privacy leak.
- **T1 Router/compressor (local):** a small model decides *which* doctrine slice / which model handles a step.
- **T2 Draft tier (local):** a 30–35B MoE model does mechanical work (summarise a diff, draft a commit message, route) at usable speed; the API is called only for hard judgment/verification.
- **T3 Fully local:** run the loop on a 120B-class model; zero API tokens.
- **Impact:** the only lever that can cut *total* cost to near zero. **Effort:** medium–high (runtime + model management). **Reversible:** yes.

### L7 — Harness shape: thin driver vs. context shim
- **Thin driver (new harness):** a loop that reads durable state, asks the CLI for the next capsule, calls the model with *only* kernel + capsule + tool results, applies the tool call, reports the result, repeats. The CLI stays the brain; the harness is a few hundred lines.
- **Context shim/proxy:** sit between an existing harness (OpenCode, Claude Code, Codex) and the API; strip the standing corpus from the outgoing request and inject a retrieved slice. Works with off-the-shelf agents, but fights the harness's own prompt assembly and may break caching.
- **Impact:** the thin driver is the clean realisation of L3/L4; the shim is a faster stopgap. **Effort:** driver medium; shim low–medium. **Reversible:** yes.
- **Note:** "harness" already has two meanings in this repo (session-presence writers; tool-surface profiles); a *context* harness would be a third, and the operator anticipated "we'll need to plan for that."

---

## 6. Comparison

| Lever | Token impact | Reliability | Effort | Reversibility | Lives in |
|---|---|---|---|---|---|
| L1 Trim standing corpus | Medium | Neutral | Low | High | CLI / repo |
| L2 Doctrine index + retrieval | High | Neutral–up | Medium–High | High | CLI |
| L3 Kernel + capsule + caching | High | Up (bounded, stable) | Medium | High | CLI + harness |
| L4 Gates (policy-as-code) | High (removes prose) | **Up** | Medium–High | Per-check | CLI / CI / hooks |
| L5 Sub-agent isolation | Medium–High (main loop) | Mixed | Medium | High | Harness |
| L6 Local tiers | **Highest (cost → ~0)** | Neutral–up | Medium–High | High | Runtime |
| L7 Thin driver / shim | Enables L3–L4 | Up | Med / Low-Med | High | Harness |

**Composition that is most coherent with Spec Kitty's own doctrine:** L4 (make invariants checkable) + L3 (emit only the step capsule) + L2 (retrieve the rest canonically) + L6 (run retrieval and, optionally, the loop locally). L1 falls out of L2 automatically; L5 is a scaling refinement; L7 is the delivery vehicle.

---

## 7. Hardware: what the Ryzen AI Max+ 395 can carry

| Property | Value | Implication |
|---|---|---|
| Memory | up to 128 GB unified LPDDR5X-8000; ~110 GB GPU-addressable on Linux | Holds a 70B dense (~42 GB Q4) or a 120B MoE (~65 GB) with room to spare |
| Bandwidth | 256 GB/s nominal, ~210–220 GB/s real | Sets the tokens/s ceiling; no software trick bypasses it |
| Compute | Radeon 8060S (~40 CU, ~60 TFLOPS FP16) + XDNA2 NPU (~50 TOPS INT8) | GPU for LLM inference; NPU for embeddings/classifiers/small models |
| Well-supported models | GPT-OSS-120B ~11–30 t/s; 35B MoE (3B active) ~50–75 t/s; 9B dense ~40 t/s; 70B dense ~5 t/s | MoE is the sweet spot; dense 70B is latency-poor |
| Software | llama.cpp / Ollama / ROCm; AMD "Lemonade" for NPU+GPU hybrid | Workable today; ROCm rough edges are the main risk |

**Read:** the box is excellent as a **retrieval/index host (T0)** and a **draft/router tier (T1/T2)**; a **fully local loop (T3)** is viable where latency is tolerable, best with a MoE model. Treat local as an *offload tier*, with the API for hard judgment, unless the priority is data sovereignty over latency.

---

## 8. Prior art (external)

- **Anthropic — Effective context engineering for AI agents**: smallest high-signal token set; context rot; compaction, note-taking, sub-agents. <https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents>
- **Agent Skills / progressive disclosure** (Anthropic, Microsoft, LangChain): metadata always, instructions on activation, resources on execution — the canonical "advertise → load → read resources" pattern. <https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview> · <https://learn.microsoft.com/en-us/agent-framework/agents/skills>
- **Aider repo-map**: tree-sitter symbol graph + PageRank, fitted to a ~1k-token budget — token-lean structural context. <https://aider.chat/docs/repomap.html>
- **Structural codebase index / stable-prefix caching**: notes that rebuilding the full prompt each turn forfeits prompt caching. <https://arxiv.org/html/2606.22417v1>
- **Prompt-format sensitivity**: *Does Prompt Formatting Have Any Impact on LLM Performance?* (arXiv 2411.10541) and schema-validity-vs-semantic-reliability (arXiv 2607.18261) — the evidence behind §4.
- **Sourcegraph / Sentra context-engineering surveys** (2026): the "seven techniques" framing; context as a scarce, rivalrous resource.
- **Strix Halo local-LLM figures**: ModelFit and Compute Market hardware reviews, 2026. <https://modelfit.io/gpu/ryzen-ai-max-395>

**Internal:** ADR 2026-07-28-1 (progressive disclosure); ADR 2026-02-11-2 (fresh context, Proposed); ADR 2026-03-09-1 (commands own context); mission `analyze-prompt-context-load-01M3F4BV` `research.md` §9; `src/charter/activation/context_renderers/token_budget.py`; `src/runtime/next/prompt_builder.py`; `src/specify_cli/session_presence/writers/registry.py`.

---

## 9. Decision points before any plan

These are the questions a plan would have to answer. They are listed, not resolved.

1. **Which channel first?** Standing corpus (L1/L2) or per-action payload (#5005 deferred fix)? They are independent; the standing corpus recurs *every turn*, the payload recurs *once per checkout per action*.
2. **Retrieval mechanism:** deterministic (FTS/keyword, reproducible, no model) vs. embedding (semantic, needs a local model) vs. hybrid? Determinism aligns with Spec Kitty's "commands resolve context" doctrine.
3. **What may remain standing?** Define the *criteria* for "always-on" text. Proposal to test: it must be (a) true for every action, (b) not machine-checkable, and (c) short. Everything else is retrieved or gated.
4. **How much enforcement moves to gates?** Which invariants are worth a check, and who owns the checks (CLI `doctor`, pre-commit, CI)?
5. **Harness posture:** new thin driver, a shim over existing harnesses, or both? This is the "new harness" the operator flagged.
6. **Local tier target:** T0 only (retrieval), T2 (draft offload), or T3 (fully local)? This determines the runtime/model-management work.
7. **Caching strategy:** what is the stable prefix, and how do we keep it byte-stable across sessions and versions?
8. **Measurement + acceptance:** what is the target (e.g. "standing steering < 2 KB/turn", "per-action payload ≤ budget"), and how is it measured without the stateful-CLI hazard of §1.3?

---

## 10. Non-goals

- This document proposes **no plan and no schedule**. It is a map.
- It does **not** propose deleting doctrine content — only changing *when* it is paid for.
- It does **not** propose summarising canonical sources (rejected by ADR 2026-07-28-1 for drift).
- It does **not** reopen the deferred #5005 budget fix; it records it as prior evidence.

---

## 11. Honest residuals and uncertainties

- **Standing-context token estimates are estimates.** File byte sizes are measured; the skill-catalog and tool-catalog sizes are order-of-magnitude only, since they depend on the harness.
- **The CLI's own byte counts are unreliable** (stateful, flag-dependent — §1.3). Only the `build_with_scope` render-path numbers (§1.2) are vetted.
- **Whether a thin kernel is *sufficient* steering is unproven here.** It is the central risk: a rule that is retrieved-but-never-fetched "reaches nobody" — the same defect class ADR 2026-07-28-1 names. The counterweight is L4: anything that matters for safety should be a gate, not a fetch.
- **Local-model agentic quality at 35B MoE is promising but not verified for Spec Kitty's workload**; the 5–30 t/s band is latency-bound.
- **Prompt-caching economics vary by provider and TTL** and were not measured here.

---

*Prepared under Op `01M4F0SF732J47E3V5GYG56DRQ`, profile `researcher-robbie`. Decision documentation per DIRECTIVE_003.*
