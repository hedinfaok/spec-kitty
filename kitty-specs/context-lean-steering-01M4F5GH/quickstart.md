# Quickstart: Context-lean steering

A minimal walkthrough once the lean steering layer is implemented.

## 1. Inspect the standing kernel

```bash
spec-kitty steer kernel
# -> the ≤ 1 KB standing instruction set (protocol + judgment residue)
```

## 2. Emit a per-step capsule for a mission

```bash
spec-kitty steer capsule --mission <handle>
# -> step, work package facts, doctrine pointers, and the binding gate
#    (≤ 2 KB; doctrine bodies are referenced, not inlined)
```

## 3. Fetch doctrine only when a pointer says so

```bash
spec-kitty steer fetch directive:DIRECTIVE_030
# -> the canonical body, on demand
```

## 4. Run the binding gate

```bash
spec-kitty steer check --mission <handle>
# -> clean, or a refusal the agent must fix before proceeding
```

## 5. Measure the reduction

```bash
spec-kitty steer measure --mission <handle>
# -> standing and per-step steering sizes vs the ~101 KB / 81-95 KB baseline
```

## 6. Drive the loop on a local model

```bash
spec-kitty steer loop --mission <handle> --model <local-model-id> --turns 12
# -> a scored transcript; the driver executes every action in each reply
```

## Expected outcome

- Standing steering text per turn ≤ 1 KB (from ~101 KB).
- Per-step payload ≤ 2 KB (from 81–95 KB first load).
- Every gate refuses its planted violation.
- A 9B-class Q4 local model completes a work package through the loop within the turn budget.
