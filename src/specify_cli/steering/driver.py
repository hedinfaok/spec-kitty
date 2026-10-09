"""Driver loop with batched-action handling (WP05 / IC-05, FR-005, SC-005).

The driver feeds the standing kernel (WP01) plus the per-step capsule (WP03)
and a small JSON tool protocol to a model, then executes the actions the model
returns. The one defect it exists to prevent is the one the spike proved:
a strict single-JSON parser silently drops the second action of a batched reply
and turns a genuine pass into a false failure (``lean-loop-test.md``). So the
loop **executes every action in every reply, in order** -- and a reply that
carries no action is a *counted* format error, never a silent no-op.

Design (mirrors ``research-outputs/lean-steering-spike/lean_loop.py``):

* :func:`parse_reply` is the lenient parser: it decodes the first JSON object
  and keeps decoding subsequent objects in the same reply (``raw_decode`` at a
  moving index), so a batched reply yields every action. Objects that are not
  actions and replies with no object at all are counted as format errors.
* :func:`drive` is the render -> call -> execute -> report cycle. It is pure
  about its dependencies: the model is a callable (:class:`ModelCall`) and the
  tools are a :class:`Toolbox`, so the loop is testable without a live model.
* :class:`HttpModelClient` is the local OpenAI-compatible adapter (stdlib
  ``urllib`` only) -- the same shape the spike used and the seam WP06's tier
  policy builds on. It fails **loudly**: an unreachable endpoint raises
  :class:`ModelUnavailableError`, an empty/malformed completion raises
  :class:`EmptyModelResponseError`; it never returns an empty string.
* :class:`SandboxToolbox` is the default tool surface. File tools are confined
  to an explicit sandbox root (never the repository); ``run_gate`` reuses the
  WP04 gate registry; ``fetch_doctrine`` reuses the WP02 index. A ``finish``
  attempted while the binding gate is refused is a *surfaced protocol
  violation*, not an accepted exit.

The CLI entry point is :func:`run`, reached by ``spec-kitty steer loop`` via the
lazy import in :mod:`specify_cli.cli.commands.steer`.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Default OpenAI-compatible endpoint and model id (the spike's local target).
DEFAULT_ENDPOINT = "http://127.0.0.1:8888/v1/chat/completions"
DEFAULT_MODEL = "unsloth/Qwen3.5-9B-GGUF"

#: Default turn budget when the caller does not set ``--turns``.
DEFAULT_TURNS = 1

#: Stable error codes for the driver's two loud model failures.
STEER_MODEL_UNAVAILABLE = "STEER_MODEL_UNAVAILABLE"
STEER_MODEL_EMPTY = "STEER_MODEL_EMPTY"

#: The tool protocol appended to the kernel and the capsule. One JSON object per
#: action; several objects in one reply are a batch and all of them are run.
TOOL_PROTOCOL = """## Tools -- reply with one JSON object per action; batch actions when you can

{"tool": "read_file", "args": {"path": "app.py"}}
{"tool": "write_file", "args": {"path": "app.py", "content": "..."}}
{"tool": "run_tests", "args": {}}
{"tool": "fetch_doctrine", "args": {"selector": "directive:DIRECTIVE_030"}}
{"tool": "run_gate", "args": {}}
{"tool": "finish", "args": {}}
"""

#: Nudge appended when a reply carried no action (a counted format error).
_FORMAT_RETRY = 'No action found. Reply with at least one JSON object, for example {"tool": "read_file", "args": {"path": "app.py"}}.'

#: Result returned when ``finish`` is attempted on a refused gate.
_GATE_REFUSED_FINISH = "REFUSED: cannot finish while the binding gate is refused. Fix the cause, run the gate again, then finish."

#: The synthetic compliance target a bare ``steer loop`` runs against -- the
#: fixture the long-horizon spike validated. It lives only in a tempdir; the
#: repository is never mutated by the driver.
_SANDBOX_APP = "def add(a, b):\n    return a - b\n"
_SANDBOX_TEST = "from app import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"

_DECODER = json.JSONDecoder()


# ---------------------------------------------------------------------------
# Tool protocol and the lenient, batched parser (T019)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Action:
    """One tool call decoded from a model reply."""

    tool: str
    args: dict[str, object]


@dataclass(frozen=True, slots=True)
class ParsedReply:
    """Every action in one reply, plus the number of format errors it carried."""

    actions: tuple[Action, ...]
    format_errors: int


def _iter_json_objects(reply: str) -> Iterator[dict[str, object]]:
    """Yield every JSON object in *reply*, in order, tolerating surrounding text.

    ``raw_decode`` is applied at each ``{`` and the index advances past the
    decoded object, so nested braces inside a string or a sub-object are never
    mistaken for a new action boundary.
    """
    index = 0
    while True:
        start = reply.find("{", index)
        if start == -1:
            return
        try:
            obj, end = _DECODER.raw_decode(reply, start)
        except json.JSONDecodeError:
            index = start + 1  # a stray brace: keep scanning for a real object
            continue
        if isinstance(obj, dict):
            yield obj
        index = end


def parse_reply(reply: str) -> ParsedReply:
    """Parse *reply* into every action it carries, never silently dropping one.

    * A reply with no parseable object at all is one counted format error.
    * A parsed JSON object that is not an action (no non-empty string ``tool``)
      is one counted format error, even when it sits beside a valid action.
    * Trailing non-action text after a valid object is ignored, as the spike did.
    """
    actions: list[Action] = []
    format_errors = 0
    saw_object = False
    for obj in _iter_json_objects(reply):
        saw_object = True
        tool = obj.get("tool")
        if isinstance(tool, str) and tool.strip():
            args = obj.get("args")
            actions.append(Action(tool=tool.strip(), args=dict(args) if isinstance(args, dict) else {}))
        else:
            format_errors += 1
    if not saw_object:
        format_errors = 1
    return ParsedReply(actions=tuple(actions), format_errors=format_errors)


# ---------------------------------------------------------------------------
# The model seam (T019/T020) -- the local OpenAI-compatible adapter
# ---------------------------------------------------------------------------


class ModelUnavailableError(RuntimeError):
    """The model endpoint could not be reached or answered at the transport level."""

    code = STEER_MODEL_UNAVAILABLE

    def __init__(self, message: str) -> None:
        super().__init__(f"{STEER_MODEL_UNAVAILABLE}: {message}")


class EmptyModelResponseError(RuntimeError):
    """The model answered, but with no usable text (empty or malformed)."""

    code = STEER_MODEL_EMPTY

    def __init__(self, message: str) -> None:
        super().__init__(f"{STEER_MODEL_EMPTY}: {message}")


class ModelCall(Protocol):
    """A model call: given the conversation, return the next reply text."""

    def __call__(self, messages: Sequence[dict[str, str]]) -> str: ...


@dataclass(slots=True)
class HttpModelClient:
    """A stdlib-only client for an OpenAI-compatible ``/v1/chat/completions`` endpoint."""

    model: str = DEFAULT_MODEL
    endpoint: str = DEFAULT_ENDPOINT
    max_tokens: int = 400
    temperature: float = 0.0
    timeout: float = 300.0

    def __call__(self, messages: Sequence[dict[str, str]]) -> str:
        payload = {
            "model": self.model,
            "messages": list(messages),
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(self.endpoint, data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ModelUnavailableError(f"cannot reach {self.endpoint!r}: {exc}") from exc
        return _extract_content(raw, self.endpoint)


def _extract_content(raw: bytes, endpoint: str) -> str:
    """Pull the reply text out of an OpenAI-compatible completion, or fail loudly."""
    try:
        content = json.loads(raw)["choices"][0]["message"]["content"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise EmptyModelResponseError(f"malformed completion from {endpoint!r}: {exc}") from exc
    if not isinstance(content, str) or not content.strip():
        raise EmptyModelResponseError(f"the model at {endpoint!r} returned no text")
    return content


# ---------------------------------------------------------------------------
# The tool seam and the default sandbox toolbox
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ToolResult:
    """The outcome of one executed action."""

    output: str
    refused: bool = False


class Toolbox(Protocol):
    """Executes one non-terminal action and returns its textual result."""

    def execute(self, action: Action) -> ToolResult: ...


@dataclass(slots=True)
class SandboxToolbox:
    """The default tool surface: sandboxed file tools, WP04 gates, WP02 fetches.

    ``root`` is the only directory file tools may touch; ``gate`` returns the
    WP04 problems for the repository (empty means clean) and ``fetch`` returns a
    doctrine body for a selector. Both are injected so the toolbox is testable
    without shelling out.
    """

    root: Path
    gate: Callable[[], list[str]]
    fetch: Callable[[str], str]
    test_argv: tuple[str, ...] = (sys.executable, "-m", "pytest", "-q")
    writes: list[str] = field(default_factory=list)
    fetches: list[str] = field(default_factory=list)
    gate_calls: int = 0

    def execute(self, action: Action) -> ToolResult:
        handlers: dict[str, Callable[[dict[str, object]], ToolResult]] = {
            "read_file": self._read_file,
            "write_file": self._write_file,
            "run_tests": self._run_tests,
            "fetch_doctrine": self._fetch_doctrine,
            "run_gate": self._run_gate,
        }
        handler = handlers.get(action.tool)
        if handler is None:
            return ToolResult(f"ERROR: unknown tool {action.tool!r}")
        return handler(action.args)

    def _target(self, args: dict[str, object]) -> Path | None:
        """Resolve ``args['path']`` inside ``root``; ``None`` when it escapes it."""
        raw = args.get("path")
        if not isinstance(raw, str) or not raw.strip():
            return None
        root = self.root.resolve()
        candidate = (self.root / raw).resolve()
        if candidate != root and root not in candidate.parents:
            return None
        return candidate

    def _read_file(self, args: dict[str, object]) -> ToolResult:
        target = self._target(args)
        if target is None or not target.is_file():
            return ToolResult(f"ERROR: no such file: {args.get('path')!r}")
        return ToolResult(target.read_text(encoding="utf-8"))

    def _write_file(self, args: dict[str, object]) -> ToolResult:
        target = self._target(args)
        if target is None:
            return ToolResult(f"ERROR: refusing to write outside the sandbox: {args.get('path')!r}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(args.get("content", "")), encoding="utf-8")
        self.writes.append(str(target.relative_to(self.root.resolve())))
        return ToolResult("ok")

    def _run_tests(self, _args: dict[str, object]) -> ToolResult:
        try:
            result = subprocess.run(list(self.test_argv), cwd=self.root, capture_output=True, text=True, check=False)
        except FileNotFoundError as exc:
            return ToolResult(f"ERROR: test command unavailable: {exc}")
        if result.returncode == 0:
            return ToolResult("PASS")
        detail = result.stdout.strip() or result.stderr.strip() or f"exit {result.returncode}"
        return ToolResult(f"FAIL: {detail}")

    def _fetch_doctrine(self, args: dict[str, object]) -> ToolResult:
        selector = str(args.get("selector", ""))
        self.fetches.append(selector)
        try:
            body = self.fetch(selector)
        except (LookupError, OSError) as exc:
            return ToolResult(f"ERROR: cannot fetch {selector!r}: {exc}")
        return ToolResult(body)

    def _run_gate(self, _args: dict[str, object]) -> ToolResult:
        self.gate_calls += 1
        problems = self.gate()
        if not problems:
            return ToolResult("clean")
        return ToolResult("REFUSED:\n" + "\n".join(problems) + "\nFix the cause, then re-run the gate.", refused=True)


# ---------------------------------------------------------------------------
# The loop (T020)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExecutedAction:
    """One action the loop executed (or refused), recorded in order."""

    turn: int
    tool: str
    args: dict[str, object]
    output: str
    refused: bool = False

    def to_payload(self) -> dict[str, object]:
        """Return the JSON-persistable form of this record."""
        return {"turn": self.turn, "tool": self.tool, "args": self.args, "output": self.output, "refused": self.refused}


@dataclass(frozen=True, slots=True)
class LoopReport:
    """The scored transcript of one driver run."""

    mission: str
    model: str
    turn_budget: int
    turns_used: int
    finished: bool
    format_errors: int
    protocol_violations: int
    actions: tuple[ExecutedAction, ...]

    def to_payload(self) -> dict[str, object]:
        """Return the JSON report (the ``--json`` contract)."""
        return {
            "mission": self.mission,
            "model": self.model,
            "turn_budget": self.turn_budget,
            "turns_used": self.turns_used,
            "finished": self.finished,
            "format_errors": self.format_errors,
            "protocol_violations": self.protocol_violations,
            "actions": [record.to_payload() for record in self.actions],
        }


def drive(*, mission: str, model: str, ask: ModelCall, toolbox: Toolbox, seed: str, turns: int) -> LoopReport:
    """Run the render -> call -> execute -> report cycle, bounded by *turns*.

    Every action in a reply is executed in order (SC-005). A reply with no action
    is one counted format error; a ``finish`` while the binding gate is refused is
    one counted protocol violation and the loop continues, never exiting early.
    A model failure propagates: the loop never swallows it.
    """
    messages: list[dict[str, str]] = [{"role": "user", "content": seed}]
    records: list[ExecutedAction] = []
    format_errors = 0
    protocol_violations = 0
    gate_refused = False
    finished = False
    turns_used = 0
    for turn in range(1, turns + 1):
        turns_used = turn
        reply = ask(messages)
        messages.append({"role": "assistant", "content": reply})
        parsed = parse_reply(reply)
        format_errors += parsed.format_errors
        if not parsed.actions:
            messages.append({"role": "user", "content": _FORMAT_RETRY})
            continue
        for action in parsed.actions:
            if action.tool == "finish":
                if gate_refused:
                    protocol_violations += 1
                    records.append(ExecutedAction(turn, "finish", action.args, _GATE_REFUSED_FINISH, refused=True))
                    messages.append({"role": "user", "content": _GATE_REFUSED_FINISH})
                    continue
                records.append(ExecutedAction(turn, "finish", action.args, "FINISHED"))
                finished = True
                break
            outcome = toolbox.execute(action)
            if action.tool == "run_gate":
                gate_refused = outcome.refused
            records.append(ExecutedAction(turn, action.tool, action.args, outcome.output, refused=outcome.refused))
            messages.append({"role": "user", "content": f"Result: {outcome.output}"})
        if finished:
            break
    return LoopReport(
        mission=mission,
        model=model,
        turn_budget=turns,
        turns_used=turns_used,
        finished=finished,
        format_errors=format_errors,
        protocol_violations=protocol_violations,
        actions=tuple(records),
    )


# ---------------------------------------------------------------------------
# CLI entry point (T021)
# ---------------------------------------------------------------------------


def build_seed(mission: str | None, *, repo_root: Path) -> str:
    """Assemble the initial context: kernel (WP01) + capsule (WP03) + protocol."""
    from specify_cli.steering.capsule import build_capsule, render
    from specify_cli.steering.kernel import render_kernel

    capsule_text = render(build_capsule(mission, repo_root=repo_root))
    return f"{render_kernel()}\n\n{capsule_text}\n\n{TOOL_PROTOCOL}"


def run(mission: str | None, *, model: str | None = None, turns: int = DEFAULT_TURNS, json_output: bool = False) -> None:
    """``steer loop`` handler: drive the model for *turns* and report the transcript."""
    repo_root = _default_repo_root()
    seed = build_seed(mission, repo_root=repo_root)
    sandbox = _prepare_sandbox()
    toolbox = SandboxToolbox(
        root=sandbox,
        gate=lambda: _default_gate(repo_root, mission),
        fetch=lambda selector: _default_fetch(repo_root, selector),
    )
    client = HttpModelClient(model=model or DEFAULT_MODEL)
    report = drive(mission=mission or "", model=client.model, ask=client, toolbox=toolbox, seed=seed, turns=turns)
    render_report(report, json_output=json_output)


def render_report(report: LoopReport, *, json_output: bool) -> None:
    """Print the transcript and score card, or the JSON report."""
    if json_output:
        print(json.dumps(report.to_payload(), indent=2))
        return
    for record in report.actions:
        print(f"[turn {record.turn}] {record.tool}({_short_args(record.args)}) -> {record.output[:90]!r}")
    print()
    print("===== SCORE =====")
    print(f"model        : {report.model}")
    print(f"finished     : {report.finished}")
    print(f"turns        : {report.turns_used}/{report.turn_budget}")
    print(f"format errs  : {report.format_errors}")
    print(f"protocol     : {report.protocol_violations} violation(s)")


def _short_args(args: dict[str, object]) -> str:
    return ", ".join(f"{key}={_short_value(value)}" for key, value in args.items())


def _short_value(value: object) -> str:
    text = str(value)
    return f"{text[:47]}..." if len(text) > 50 else text


# ---------------------------------------------------------------------------
# Engine wiring
# ---------------------------------------------------------------------------


def _prepare_sandbox() -> Path:
    """Create the per-run sandbox (a tempdir) seeded with the compliance fixture."""
    root = Path(tempfile.mkdtemp(prefix="steer-loop-sandbox-"))
    (root / "app.py").write_text(_SANDBOX_APP, encoding="utf-8")
    (root / "test_app.py").write_text(_SANDBOX_TEST, encoding="utf-8")
    return root


def _default_gate(repo_root: Path, mission: str | None) -> list[str]:
    """Run the WP04 binding machine gates against the repository."""
    from specify_cli.steering.gates import GateTarget, run_gates

    problems: list[str] = run_gates(GateTarget(root=repo_root, mission=mission))
    return problems


def _default_fetch(repo_root: Path, selector: str) -> str:
    """Fetch one doctrine body from the WP02 canonical index."""
    from specify_cli.steering.index import fetch

    body: str = fetch(repo_root, selector).body
    return body


def _default_repo_root() -> Path:
    from specify_cli.task_utils import find_repo_root

    root: Path = find_repo_root()
    return root
