# Spec Kitty — lean steering kernel

You drive a Spec Kitty Mission through a state machine. This file is the **entire**
standing steering text. Everything else is fetched on demand.

## Protocol

1. **State is authoritative and lives in the Mission.** Never guess the step, the work
   package, or the branch. Ask the engine: `python3 sk.py capsule --mission <slug>`
   (or `spec-kitty next --mission <slug> --json`).
2. **Doctrine is fetched, not inlined.** The capsule lists required doctrine ids. Fetch
   one with `spec-kitty charter context --include <selector>`. When a pointer says
   "when doing X", fetch it before doing X.
3. **Invariants are machine gates.** Run `python3 sk.py check --mission <slug>`. A
   refusal is binding: fix its cause, do not proceed past it.

## Judgment (no gate can check these)

- Prefer a durable fix over a shim; if a shim is genuinely unavoidable, say why.
- Read `.kittify/charter/charter.md` before planning or changing code.
- Write for the next maintainer, not for the grader.
