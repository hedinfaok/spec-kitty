# Experiment: does the *format* reduce steering context, or the *mechanism*?

A small, reproducible experiment behind the "Format is not the lever" section of
[`../context-lean-steering.md`](../context-lean-steering.md).

**Question.** If you must steer an agent with a fixed set of rules, does the encoding
(Markdown vs JSON) reduce cost, or is the reduction from *what you do with the rules*
(text to read vs. a gate the model never sees)?

**Method.** One rule set (eight representative rules R1–R8 drawn from this repository's
own policy). The same rules are encoded three ways. For each, we measure the bytes that
actually enter the model's context, and separately how many rules are *enforced by
construction*. No model is called; the enforcement axis is demonstrated with a real
gate run against planted violations.

| Encoding | What enters the model's context |
|---|---|
| A. Markdown prose | `encodings/rules.md` — headings + prose paragraphs (status-quo `AGENTS.md` style) |
| B. JSON config | `encodings/rules.json` — the same eight rules as an array of objects |
| C. Gate + kernel | `encodings/kernel.md` — a ~3-line kernel. The six checkable rules live in `check_policy.py`, which the model never reads |

Run it yourself:

```bash
cd research-outputs/context-format-experiment
python3 run_experiment.py
python3 check_policy.py fixtures/violating   # exits 1
```

## Results

What enters the model's context:

| Encoding | bytes | lines | words | ~tokens (bytes/4) |
|---|---:|---:|---:|---:|
| A. Markdown prose | 2,372 | 53 | 362 | 593 |
| B. JSON config | 3,035 | 69 | 368 | 759 |
| C. Gate + kernel | 499 | 9 | 84 | 125 |

Rules actually enforced:

| Encoding | Enforced |
|---|---|
| A. Markdown prose | 0/8 (advisory only) |
| B. JSON config | 0/8 (advisory only) |
| C. Gate + kernel | 6/8 by construction; the other 2 are judgment/process |

Gate run against planted violations (fixture `fixtures/violating/`):

| Rule | Result |
|---|---|
| R2 forbidden term | caught |
| R3 blanket `# noqa` | caught |
| R4 missing/extra final newline | caught |
| R4 trailing whitespace | caught |
| R1 protected branch (`--branch main`) | caught, exit 1 |
| R5 bad commit subject | caught, exit 1 |
| clean fixture | pass, exit 0 |

## Interpretation

1. **JSON is not smaller here — it is ~28% bigger than Markdown** (3,035 vs 2,372 bytes).
   For rule-shaped, natural-language content, JSON's keys, braces, and quotes add tokens
   rather than remove them. Migrating a prose corpus to JSON would cost more per turn,
   not less.
2. **The win is the mechanism, not the format.** Encoding C is ~4.75× smaller than
   Markdown and ~6× smaller than JSON — because the seven checkable rules left the
   prompt entirely and became a program. Format is second-order; *whether the content is
   in the prompt at all* is first-order.
3. **Enforcement is the other axis, and it inverts.** A and B pay tokens and enforce
   nothing (compliance is a hope, checkable only by another model). C pays ~125 tokens
   and enforces six of eight rules by construction. A gate costs 0 tokens/turn and cannot
   be misread.

## Caveats

- **~tokens is a chars/4 estimate**, not a tokenizer count. It is adequate for the
  order-of-magnitude comparison and is labelled as a proxy.
- **The rule set is a sample, not the full policy.** The proportion that is checkable
  (6/8 here) is optimistic; real policy has a larger judgment share, which is exactly why
  the kernel keeps a short prose residue.
- **The forbidden-term check is a word-boundary grep**, a deliberately simple proxy for a
  human review. It is here to make the gate's behaviour falsifiable, not to be shipped.
- **No LLM was called.** This experiment measures cost and enforceability, not the
  compliance rate of a model reading prose. That is the natural follow-up.
