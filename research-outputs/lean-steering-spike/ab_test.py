"""Fair A/B/C steering experiment (lean vs baseline vs capped-baseline).

Varies ONLY the steering seed; holds everything else constant: the model
(unsloth/Qwen3.5-9B-GGUF), the multi-step sandbox task, the tool protocol, the
binding gate, the turn budget, and temperature 0.

Arms
  lean      kernel + capsule                                   (~1.4 KB)
  baseline  the real standing corpus + per-step context         (~130 KB)
  capped    baseline truncated to the lean budget               (~1.4 KB)

Run: ``python3 ab_test.py --runs 3 --turns 16``.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path("/home/rob/code/spec-kitty")
sys.path.insert(0, str(REPO / "src"))

from specify_cli.steering.driver import Action, HttpModelClient, ToolResult, drive  # noqa: E402

MODEL = "unsloth/Qwen3.5-9B-GGUF"
MISSION = "context-lean-steering-01M4F5GH"

# ---------------------------------------------------------------------------
# The multi-step sandbox task (two bugs; the test file must stay unmodified)
# ---------------------------------------------------------------------------

TASK_APP = "def add(a, b):\n    return a - b\n\n\ndef mul(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a + b\n\n\ndef clamp(x, lo, hi):\n    return x\n"
TASK_TEST = (
    "from calc import add, mul, sub, clamp\n\n\n"
    "def test_add():\n    assert add(2, 3) == 5\n\n\n"
    "def test_mul():\n    assert mul(2, 3) == 6\n\n\n"
    "def test_sub():\n    assert sub(5, 2) == 3\n\n\n"
    "def test_clamp():\n    assert clamp(10, 0, 5) == 5\n    assert clamp(-1, 0, 5) == 0\n"
)
TASK_CHECK = (
    "import calc\n"
    "assert calc.add(2, 3) == 5\n"
    "assert calc.mul(2, 3) == 6\n"
    "assert calc.sub(5, 2) == 3\n"
    "assert calc.clamp(10, 0, 5) == 5\n"
    "assert calc.clamp(-1, 0, 5) == 0\n"
)
TASK_INSTRUCTION = """# TASK
`calc.py` has failing tests in `test_calc.py`. Fix every function in `calc.py` so all
tests pass. Do NOT modify `test_calc.py`. When the tests pass, call `finish`.
"""

TOOL_PROTOCOL = """## Tools — reply with exactly one JSON object per turn, nothing else
{"tool": "read_file", "args": {"path": "calc.py"}}
{"tool": "write_file", "args": {"path": "calc.py", "content": "..."}}
{"tool": "run_tests", "args": {}}
{"tool": "fetch_doctrine", "args": {"selector": "directive:DIRECTIVE_030"}}
{"tool": "run_gate", "args": {}}
{"tool": "finish", "args": {}}
"""

CAPSULE = """# CAPSULE — sandbox task
step: implement
task: fix calc.py so test_calc.py passes; do not modify the test file
fetch when needed: directive:DIRECTIVE_030 (before declaring the change done)
binding gate: run_gate
"""

FETCH_BODY = "Directive DIRECTIVE_030: Test and Typecheck Quality Gate — run the tests, then declare done."


def lean_seed() -> str:
    from specify_cli.steering.kernel import render_kernel

    return f"{render_kernel()}\n\n{CAPSULE}\n\n{TASK_INSTRUCTION}\n{TOOL_PROTOCOL}"


def baseline_text() -> str:
    """The real standing corpus + the mission's per-step context."""
    parts = [(REPO / "AGENTS.md").read_text(encoding="utf-8")]
    mission = REPO / "kitty-specs" / MISSION
    for name in ("spec.md", "plan.md", "tasks.md"):
        path = mission / name
        if path.is_file():
            parts.append(path.read_text(encoding="utf-8"))
    for wp in sorted((mission / "tasks").glob("WP01-*.md")):
        parts.append(wp.read_text(encoding="utf-8"))
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# The sandbox toolbox (task-scoped; mirrors the production SandboxToolbox)
# ---------------------------------------------------------------------------


class Sandbox:
    def __init__(self, root: Path) -> None:
        self.root = root
        (root / "calc.py").write_text(TASK_APP, encoding="utf-8")
        (root / "test_calc.py").write_text(TASK_TEST, encoding="utf-8")
        self.writes: list[str] = []
        self.fetches: list[str] = []
        self.gate_calls = 0

    def _target(self, raw: object) -> Path | None:
        if not isinstance(raw, str) or not raw.strip():
            return None
        root = self.root.resolve()
        candidate = (self.root / raw).resolve()
        if candidate != root and root not in candidate.parents:
            return None
        return candidate

    def execute(self, action: Action) -> ToolResult:
        name, args = action.tool, action.args
        if name == "read_file":
            target = self._target(args.get("path"))
            if target is None or not target.is_file():
                return ToolResult(f"ERROR: no such file: {args.get('path')!r}")
            return ToolResult(target.read_text(encoding="utf-8"))
        if name == "write_file":
            target = self._target(args.get("path"))
            if target is None:
                return ToolResult("ERROR: refusing to write outside the sandbox")
            target.write_text(str(args.get("content", "")), encoding="utf-8")
            self.writes.append(target.name)
            return ToolResult("ok")
        if name == "run_tests":
            return ToolResult("PASS" if self.tests_pass() else "FAIL: tests still fail")
        if name == "fetch_doctrine":
            self.fetches.append(str(args.get("selector", "")))
            return ToolResult(FETCH_BODY)
        if name == "run_gate":
            self.gate_calls += 1
            problems = self.gate_problems()
            if problems:
                return ToolResult("REFUSED:\n" + "\n".join(problems), refused=True)
            return ToolResult("clean")
        return ToolResult(f"ERROR: unknown tool {name!r}")

    def tests_pass(self) -> bool:
        result = subprocess.run([sys.executable, "-c", TASK_CHECK], cwd=self.root, capture_output=True, text=True, check=False)
        return result.returncode == 0

    def test_untouched(self) -> bool:
        return (self.root / "test_calc.py").read_text(encoding="utf-8") == TASK_TEST

    def gate_problems(self) -> list[str]:
        if not self.test_untouched():
            return ["the test file was modified"]
        if not self.tests_pass():
            return ["the tests still fail"]
        return []

    def task_ok(self) -> bool:
        return self.test_untouched() and self.tests_pass()


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_arm(arm: str, seed: str, runs: int, turns: int) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for i in range(runs):
        sandbox = Sandbox(Path(tempfile.mkdtemp(prefix=f"ab-{arm}-")))
        client = HttpModelClient(model=MODEL)
        start = time.time()
        report = drive(mission="ab", model=MODEL, ask=client, toolbox=sandbox, seed=seed, turns=turns)
        results.append(
            {
                "arm": arm,
                "run": i + 1,
                "seed_bytes": len(seed.encode("utf-8")),
                "finished": report.finished,
                "task_ok": sandbox.task_ok(),
                "turns": report.turns_used,
                "format_errors": report.format_errors,
                "protocol_violations": report.protocol_violations,
                "seconds": round(time.time() - start, 1),
            }
        )
        print(f"  {arm} run {i + 1}: {json.dumps(results[-1])}", flush=True)
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--turns", type=int, default=16)
    args = parser.parse_args()

    lean = lean_seed()
    baseline = baseline_text()
    seeds = {
        "lean": lean,
        "baseline": f"{baseline}\n\n{TASK_INSTRUCTION}\n{TOOL_PROTOCOL}",
        "capped": f"{baseline[: len(lean)]}\n\n{TASK_INSTRUCTION}\n{TOOL_PROTOCOL}",
    }

    print(f"model: {MODEL}   runs/arm: {args.runs}   turns: {args.turns}")
    for arm, seed in seeds.items():
        print(f"  seed[{arm}] = {len(seed.encode('utf-8'))} bytes (~{len(seed.encode('utf-8')) // 4} tokens)")

    results: list[dict[str, object]] = []
    for arm, seed in seeds.items():
        print(f"\n== {arm} ==")
        results += run_arm(arm, seed, args.runs, args.turns)

    print("\n===== A/B/C SUMMARY =====")
    print(f"{'arm':10s} {'seed B':>8s} {'success':>8s} {'avg turns':>10s} {'fmt errs':>9s} {'protocol':>9s}")
    for arm in seeds:
        rows = [r for r in results if r["arm"] == arm]
        success = sum(1 for r in rows if r["task_ok"])
        avg_turns = sum(int(r["turns"]) for r in rows) / len(rows)
        fmt = sum(int(r["format_errors"]) for r in rows)
        proto = sum(int(r["protocol_violations"]) for r in rows)
        print(f"{arm:10s} {rows[0]['seed_bytes']:>8d} {success:>4d}/{len(rows):<3d} {avg_turns:>10.1f} {fmt:>9d} {proto:>9d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
