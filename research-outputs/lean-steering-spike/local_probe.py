"""Direct probe of the local model (bypassing the opencode harness).

Calls the unsloth-studio OpenAI-compatible endpoint with the same four conditions used in
the subagent experiment, to remove the harness's auto-compaction from the measurement.

Run: ``python3 local_probe.py [--model <id>]`` (requires the local server on 127.0.0.1:8888).
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path

ENDPOINT = "http://127.0.0.1:8888/v1/chat/completions"
DEFAULT_MODEL = "unsloth/DeepSeek-V4-Flash-0731-GGUF"

KERNEL = (Path(__file__).resolve().parent / "kernel.md").read_text(encoding="utf-8").strip()

CAPSULE = """# CAPSULE — workflow-parity-988-989-991-01KRKTT5
step: implement
mission_type: software-dev
wp: WP01 — next --json claimability parity
progress: 0/3 done, 3 planned
owned_files: src/specify_cli/next/**, src/specify_cli/cli/commands/next_cmd.py, tests/next/test_next_claimable_payload.py
subtasks: T001, T002, T003
requirement_refs: FR-001, FR-002, FR-003, FR-010, C-001

## Fetch when needed (do not request all of it)
- `spec-kitty charter context --include directive:DIRECTIVE_044` — when choosing a template or tempted to improvise
- `spec-kitty charter context --include directive:DIRECTIVE_030` — before declaring the change done
- `spec-kitty charter context --include directive:DIRECTIVE_025` — when the change touches more than the target file
- `spec-kitty charter context --include directive:DIRECTIVE_031` — when designing an interface or a seam
- docs/context/ (canonical terminology)
- docs/adr/ (architectural intent)

## Binding gate
- run `python3 sk.py check --mission workflow-parity-988-989-991-01KRKTT5`; a refusal is binding — fix its cause"""

CAPSULE_PARTIAL = """# CAPSULE — workflow-parity-988-989-991-01KRKTT5
step: implement
mission_type: software-dev

## Binding gate
- run `python3 sk.py check --mission workflow-parity-988-989-991-01KRKTT5`; a refusal is binding — fix its cause"""

HEADER = "Answer only from the text in this message. Do NOT use any tools, read files, or run commands. Answer purely from the text below.\n\n"

B_QUESTIONS = (
    "\n\nAnswer as a compact numbered list. If the text does not contain an answer, write "
    'exactly "NOT IN CAPSULE".\n'
    "1. What is the current step?\n"
    "2. Which work package, and what is its title?\n"
    "3. Which files may you change?\n"
    "4. Which subtasks are in scope?\n"
    "5. What is the mission slug?\n"
    "6. What command must you run, and what does a refusal mean?\n"
    "7. Which requirement refs are in scope?\n"
    '8. If a doctrine pointer says "when doing X", what must you do?\n'
    'Then one final line exactly: "FIRST ACTION: <the first thing you would do for this step>".'
)

A_QUESTIONS = (
    "\n\nThis is the CONTROL condition: no capsule was provided. Answer as a compact numbered list:\n"
    "1. What is your current step? If you do not know, say so.\n"
    "2. What is the exact first command you would run to find it, and what input does it require?\n"
    "3. Would you guess the step or the work package if you did not know them? Yes or No and one short reason."
)

C_QUESTIONS = (
    "\n\nThis is the NEGATIVE CONTROL: the capsule is deliberately degraded. Answer as a compact numbered list. "
    'If the text does not contain an answer, write exactly "NOT IN CAPSULE".\n'
    "1. What is the current step?\n"
    "2. Which work package, and what is its title?\n"
    "3. Which files may you change?\n"
    "4. Which subtasks are in scope?\n"
    "5. What is the mission slug?"
)

CONDITIONS = {
    "B1 (kernel + capsule)": HEADER + "=== KERNEL ===\n" + KERNEL + "\n\n=== CAPSULE ===\n" + CAPSULE + B_QUESTIONS,
    "B2 (kernel + capsule)": HEADER + "=== KERNEL ===\n" + KERNEL + "\n\n=== CAPSULE ===\n" + CAPSULE + B_QUESTIONS,
    "A1 (kernel only)": HEADER + "=== KERNEL ===\n" + KERNEL + A_QUESTIONS,
    "C1 (degraded capsule)": HEADER + "=== KERNEL ===\n" + KERNEL + "\n\n=== PARTIAL CAPSULE ===\n" + CAPSULE_PARTIAL + C_QUESTIONS,
}


def ask(prompt: str, model: str) -> str:
    """Send one prompt to the local model and return its answer."""
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 700, "temperature": 0}
    body = json.dumps(payload).encode()
    request = urllib.request.Request(ENDPOINT, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=600) as response:
        result = json.loads(response.read())
    return result["choices"][0]["message"]["content"]


def main() -> None:
    """Run all four conditions against the chosen model and print the answers."""
    parser = argparse.ArgumentParser(description="Probe a local model with the four lean-steering conditions.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model id served by the local endpoint.")
    args = parser.parse_args()
    print(f"model: {args.model}")
    for name, prompt in CONDITIONS.items():
        start = time.time()
        print(f"\n{'=' * 70}\n{name}  (prompt {len(prompt)} chars)\n{'=' * 70}")
        try:
            print(ask(prompt, args.model).strip())
        except Exception as exc:
            print(f"ERROR: {type(exc).__name__}: {exc}")
        print(f"[{time.time() - start:.1f}s]")


if __name__ == "__main__":
    main()
