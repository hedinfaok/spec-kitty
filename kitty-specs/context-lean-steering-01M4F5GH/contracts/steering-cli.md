# Contract: `spec-kitty steer` CLI surface

The lean steering layer's externally visible interface. All commands are additive to the
existing `spec-kitty` CLI and reuse the engine (`next`, `charter context`).

## Commands

### `spec-kitty steer kernel [--json]`

Prints the standing kernel text (or its JSON form `{ "bytes": <int>, "text": "<...>" }`).

- **Guarantees**: ≤ 1024 bytes; byte-stable across invocations with no mission state.

### `spec-kitty steer capsule --mission <handle> [--json]`

Emits the bounded per-step capsule derived from mission state.

- **Input**: a mission handle (`mission_id` / `mid8` / `mission_slug`).
- **Output (JSON)**: `{ "mission", "step", "wp", "facts", "pointers", "gate" }`.
- **Guarantees**: ≤ 2048 bytes; derived from engine state; pointers only (no doctrine bodies).

### `spec-kitty steer fetch <selector> [--json]`

Fetches one doctrine body on demand from canonical sources via the doctrine index.

- **Input**: a selector, e.g. `directive:DIRECTIVE_030` or `section:<slug>`.
- **Output**: the canonical body (or JSON `{ "selector", "source_path", "body" }`).
- **Errors**: an unknown selector is an explicit error (`STEER_SELECTOR_UNKNOWN`), never an
  empty result.

### `spec-kitty steer check --mission <handle> [--json]`

Runs the binding gates.

- **Output (JSON)**: `{ "clean": <bool>, "problems": [ ... ] }`.
- **Exit code**: `0` when clean, non-zero on any problem. A refusal is binding on the agent.

### `spec-kitty steer measure --mission <handle> [--json]`

Reports standing and per-step steering sizes against a baseline.

- **Output (JSON)**: `{ "standing_bytes", "capsule_bytes", "baseline_standing_bytes",
  "baseline_payload_bytes", "reduction" }`.

### `spec-kitty steer loop --mission <handle> --model <id> [--turns N] [--json]`

Runs the driver loop: renders kernel + capsule to a model, executes every action in each
reply (including batched actions), and reports a score.

- **Guarantees**: executes all actions per reply; counts non-JSON replies as format errors;
  never mutates the repository outside an explicit target.

## Compatibility

- No existing command, flag, or JSON contract changes.
- The engine surfaces used (`next`, `charter context --include`) are unchanged.
- The contract is additive: removing the `steer` command returns the CLI to its prior
  behaviour.
