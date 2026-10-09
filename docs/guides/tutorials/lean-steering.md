---
title: Getting started with lean steering
description: Steer an agent with a ~1 KB kernel and a per-step capsule instead of the full standing corpus, using the lean steering commands.
doc_status: active
updated: '2026-10-09'
audience: docs/context/audience/external/project-owner.md
type: tutorial
related:
- docs/guides/tutorials/getting-started.md
- docs/guides/tutorials/your-first-mission.md
---
# Getting started with lean steering

**Divio type**: Tutorial

Spec Kitty normally steers an agent by pushing a large standing corpus (a ~94 KB
`AGENTS.md`) plus a per-action governance payload (81-95 KB) into **every** turn. **Lean
steering** replaces that with a small **kernel** (the standing protocol, <= 1 KB) and a
bounded per-step **capsule** (~0.5 KB), with doctrine fetched on demand and invariants
enforced by machine **gates**.

**Time**: ~10 minutes
**Prerequisites**: this fork installed, Python 3.11+, Git, an AI coding agent (opencode,
Claude Code, Codex, ...).

## What you get

| Layer | Command | Replaces |
| --- | --- | --- |
| Standing prompt | `spec-kitty steer kernel` | the ~94 KB `AGENTS.md` |
| Per-step | `spec-kitty steer capsule --mission <handle>` | the 81-95 KB action payload |
| On demand | `spec-kitty steer fetch <selector>` | inlined doctrine bodies |
| Finish gate | `spec-kitty steer check --mission <handle>` | nothing (new enforcement) |

## Step 1: Install the fork

```bash
git clone git@github.com:hedinfaok/spec-kitty.git
cd spec-kitty && git checkout feat/portable-steer-gates
pipx install --editable .
spec-kitty steer kernel        # prints the ~1 KB kernel
```

> The released `spec-kitty` (3.x) does not have `steer`. Use this fork.

## Step 2: Initialize (or reuse) a repository

```bash
cd ~/your-repo
spec-kitty init --ai opencode        # only if it is not already a Spec Kitty project
```

## Step 3: Make the kernel the standing prompt

The harness injects a project instruction file on every turn. Point it at the kernel:

```bash
spec-kitty steer kernel > AGENTS.md
```

Keep any repo essentials (source of truth, conventions) in a short header above it. On a
repository whose `AGENTS.md` is ~94 KB, this cuts the standing text ~100x.

## Step 4: Let the agent fetch the per-step capsule

The kernel tells the agent to ask for its step rather than carry it:

```bash
spec-kitty steer capsule --mission <handle>   # omit --mission if the repo has one mission
```

It prints the step, the work package facts, doctrine **pointers**, and the binding gate. No
doctrine bodies are inlined.

## Step 5: Fetch doctrine only when pointed

```bash
spec-kitty steer fetch directive:DIRECTIVE_030
```

## Step 6: Enforce with a gate

`steer check` runs the **repository's own** check, never spec-kitty's. Declare it in
`.kittify/config.yaml`:

```yaml
steer:
  gate_command: "make check"        # a string, an argv list, or a list of argv commands
protection:
  protected_branches: [main]        # opt-in
```

```bash
spec-kitty steer check --mission <handle>   # exits non-zero on a refusal
```

**Declaration implies obligation.** A gate you declare must be verified; if its tool is
missing or the command fails, `steer check` refuses. It never skips a gate you declared. If
you declare nothing, it discovers `make check` / `npm run check`; failing that, it skips.

## Step 7: Measure the reduction

```bash
spec-kitty steer measure --mission <handle>
# standing 101438 B -> kernel 883 B (115x); payload 95139 B -> capsule ~471 B (202x)
```

## Does it actually work?

A fair A/B on a consumer 9B (Qwen3.5-9B, local), same task, same loop, with **only** the
steering text differing:

| Arm | Steering text | Success |
| --- | --- | --- |
| lean | 409 tokens | **5/5** |
| baseline | 32,246 tokens | 5/5 |
| capped baseline | 545 tokens | 5/5 |

Lean steering matched the full corpus at **~79x less context**, with no quality loss. A
*quality benefit* (avoiding context rot) is not shown by that task; see
`research-outputs/lean-steering-spike/ab-results.md`.

## Limits (read these)

- **The capsule is not auto-injected.** The agent runs `steer capsule` because the kernel
  says to. If the model ignores the kernel, it will not fetch.
- **The harness injects more than `AGENTS.md`** — tool definitions, its own preamble, a
  skill catalog. The kernel is the biggest single lever, not the only context.
- **Planning phases are coarse.** The capsule is keyed on the runtime step
  (`implement`/`review`); during `specify`/`plan`/`tasks` it renders `step: discovery`. The
  kernel is the win there.
- **Move prose rules into gates.** The kernel drops spec-kitty's statute; anything that
  matters should be a gate, or you have traded statute for nothing.

## Command reference

| Command | Purpose |
| --- | --- |
| `spec-kitty steer kernel` | print the standing kernel (<= 1024 B) |
| `spec-kitty steer capsule --mission <handle>` | per-step capsule |
| `spec-kitty steer fetch <selector>` | fetch one doctrine body |
| `spec-kitty steer check --mission <handle>` | run the binding gates |
| `spec-kitty steer measure --mission <handle>` | steering-size report |
| `spec-kitty steer loop --mission <handle> --model <id> --turns N` | standalone loop validator (sandboxed) |
