"""Measure the three encodings and demonstrate the enforcement difference.

Run from this directory: ``python3 run_experiment.py``.
"""

from __future__ import annotations

from pathlib import Path

import check_policy

HERE = Path(__file__).resolve().parent
ENCODINGS = HERE / "encodings"
FIXTURES = HERE / "fixtures"

# The text that actually enters the model's context for each encoding.
MODEL_CONTEXT = {
    "A. Markdown prose": ENCODINGS / "rules.md",
    "B. JSON config": ENCODINGS / "rules.json",
    "C. Gate + kernel": ENCODINGS / "kernel.md",
}

CHECKABLE_RULES = 6  # R1-R6 (R6 via an external tool)
TOTAL_RULES = 8  # R1-R8


def size_report() -> list[tuple[str, int, int, int, int]]:
    """Return (encoding, bytes, lines, words, approx_tokens) per encoding."""
    rows: list[tuple[str, int, int, int, int]] = []
    for name, path in MODEL_CONTEXT.items():
        text = path.read_text(encoding="utf-8")
        raw = text.encode("utf-8")
        rows.append((name, len(raw), len(text.splitlines()), len(text.split()), round(len(raw) / 4)))
    return rows


def enforcement_report() -> list[tuple[str, str]]:
    """State how many rules each encoding actually enforces."""
    rows: list[tuple[str, str]] = []
    for name in MODEL_CONTEXT:
        if name.startswith("C."):
            rows.append((name, f"{CHECKABLE_RULES}/{TOTAL_RULES} enforced by construction, 0 tokens"))
        else:
            rows.append((name, f"0/{TOTAL_RULES} enforced (advisory only)"))
    return rows


def gate_demo() -> None:
    """Show the gate catching planted violations, and passing a clean tree."""
    for fixture in ("clean", "violating"):
        target = FIXTURES / fixture
        problems = check_policy.check_target(target, branch="work/example", subject="docs(research): example")
        verdict = "REFUSED" if problems else "pass"
        print(f"  gate on {fixture:9s} fixture: {verdict}")
        for problem in problems:
            print(f"    {problem}")


def main() -> None:
    """Print the size table, the enforcement table, and the gate demonstration."""
    print("== What enters the model's context ==")
    print(f"{'encoding':20s} {'bytes':>7s} {'lines':>6s} {'words':>6s} {'~tokens':>8s}")
    for name, size, lines, words, tokens in size_report():
        print(f"{name:20s} {size:7d} {lines:6d} {words:6d} {tokens:8d}")

    print("\n== Rules enforced, by encoding ==")
    for name, verdict in enforcement_report():
        print(f"  {name:20s} {verdict}")

    print("\n== Gate demonstration (the gate itself costs the model 0 tokens) ==")
    gate_demo()


if __name__ == "__main__":
    main()
