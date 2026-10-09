"""Driver-loop tests (WP05 / T019, T020, T021, T022).

Pins the two failure modes the spike found:

* a reply carrying **two** tool calls executes **both**, in order (SC-005) --
  this is the test that goes red if the parser keeps only the first object;
* a reply with no action is a *counted* format error and an unreachable model
  fails **loudly**, never silently.

The loop is exercised through its two seams -- a scripted ``ModelCall`` and a
recording ``Toolbox`` -- so no live model or network is involved.
"""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from typer.testing import CliRunner

from specify_cli.cli.commands import steer as steer_module
from specify_cli.steering import driver
from specify_cli.steering.driver import (
    STEER_MODEL_EMPTY,
    STEER_MODEL_UNAVAILABLE,
    Action,
    EmptyModelResponseError,
    HttpModelClient,
    ModelUnavailableError,
    SandboxToolbox,
    ToolResult,
    drive,
    parse_reply,
)
from specify_cli.steering.kernel import render_kernel

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class ScriptedModel:
    """A ``ModelCall`` that returns a fixed list of replies, in order."""

    def __init__(self, replies: Sequence[str]) -> None:
        self._replies = list(replies)
        self.seen: list[list[dict[str, str]]] = []

    def __call__(self, messages: Sequence[dict[str, str]]) -> str:
        self.seen.append([dict(message) for message in messages])
        if not self._replies:
            raise AssertionError("ScriptedModel ran out of replies")
        return self._replies.pop(0)


@dataclass
class RecordingToolbox:
    """A ``Toolbox`` that records every tool name and answers ``run_gate`` from a queue."""

    gate_results: list[bool] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    task_ok_result: bool = True

    def execute(self, action: Action) -> ToolResult:
        self.calls.append(action.tool)
        if action.tool == "run_gate":
            refused = self.gate_results.pop(0) if self.gate_results else False
            return ToolResult("REFUSED" if refused else "clean", refused=refused)
        return ToolResult(f"ok:{action.tool}")

    def task_ok(self) -> bool:
        return self.task_ok_result


def _tool(tool: str, **args: object) -> str:
    return json.dumps({"tool": tool, "args": args})


def _seed_complete_sandbox(root: Path) -> None:
    """Seed a sandbox whose task is already complete (test passes, test file unmodified)."""
    (root / "test_app.py").write_text(driver._SANDBOX_TEST, encoding="utf-8")
    (root / "app.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# T019 -- the lenient, batched parser
# ---------------------------------------------------------------------------


def test_parse_reply_extracts_a_single_action() -> None:
    parsed = parse_reply('{"tool": "read_file", "args": {"path": "app.py"}}')
    assert [action.tool for action in parsed.actions] == ["read_file"]
    assert parsed.actions[0].args == {"path": "app.py"}
    assert parsed.format_errors == 0


def test_parse_reply_extracts_every_batched_object_in_order() -> None:
    reply = _tool("write_file", path="app.py", content="x") + "\n" + _tool("run_tests")
    parsed = parse_reply(reply)
    assert [action.tool for action in parsed.actions] == ["write_file", "run_tests"]
    assert parsed.format_errors == 0


def test_parse_reply_handles_nested_objects() -> None:
    reply = _tool("write_file", path="app.py", content='def f():\n    return {"k": 1}\n')
    parsed = parse_reply(reply)
    assert len(parsed.actions) == 1
    assert parsed.actions[0].args["content"] == 'def f():\n    return {"k": 1}\n'


def test_parse_reply_ignores_only_trailing_non_action_text() -> None:
    parsed = parse_reply(_tool("read_file", path="app.py") + "\nAll done, reading now.")
    assert [action.tool for action in parsed.actions] == ["read_file"]
    assert parsed.format_errors == 0


def test_parse_reply_counts_a_prose_reply_as_one_format_error() -> None:
    parsed = parse_reply("I will think about it first, no tool call here.")
    assert parsed.actions == ()
    assert parsed.format_errors == 1


def test_parse_reply_counts_an_object_without_a_tool() -> None:
    parsed = parse_reply('{"note": "this is not an action"}')
    assert parsed.actions == ()
    assert parsed.format_errors == 1


def test_parse_reply_does_not_silently_drop_a_bad_object_beside_a_good_one() -> None:
    parsed = parse_reply(_tool("read_file", path="app.py") + ' {"oops": 1}')
    assert [action.tool for action in parsed.actions] == ["read_file"]
    assert parsed.format_errors == 1


def test_parse_reply_recovers_a_valid_object_after_a_malformed_brace() -> None:
    parsed = parse_reply("{not valid json} " + _tool("finish"))
    assert [action.tool for action in parsed.actions] == ["finish"]


# ---------------------------------------------------------------------------
# T020/T022 -- the loop executes every action, bounds by turns, surfaces violations
# ---------------------------------------------------------------------------


def test_batched_reply_executes_both_actions_in_order() -> None:
    # SC-005: the 9B emitted write_file followed by run_tests in one reply. A
    # first-only parser would record just write_file, so this assertion fails.
    reply = _tool("write_file", path="app.py", content="def add(a, b):\n    return a + b\n") + "\n" + _tool("run_tests")
    model = ScriptedModel([reply, _tool("finish")])
    toolbox = RecordingToolbox()

    report = drive(mission="m", model="scripted", ask=model, toolbox=toolbox, seed="seed", turns=3)

    assert toolbox.calls == ["write_file", "run_tests"], "every action in a batched reply must run"
    assert [record.tool for record in report.actions] == ["write_file", "run_tests", "finish"]
    assert report.finished is True
    assert report.format_errors == 0


def test_a_three_action_batch_runs_all_three() -> None:
    reply = "\n".join([_tool("read_file", path="a"), _tool("read_file", path="b"), _tool("run_tests")])
    model = ScriptedModel([reply, _tool("finish")])
    toolbox = RecordingToolbox()

    report = drive(mission="m", model="scripted", ask=model, toolbox=toolbox, seed="seed", turns=2)

    assert toolbox.calls == ["read_file", "read_file", "run_tests"]
    assert report.finished is True


def test_finish_on_a_refused_gate_is_a_surfaced_protocol_violation() -> None:
    model = ScriptedModel([_tool("run_gate"), _tool("finish")])
    toolbox = RecordingToolbox(gate_results=[True])

    report = drive(mission="m", model="scripted", ask=model, toolbox=toolbox, seed="seed", turns=2)

    assert report.finished is False, "a refused gate must not be accepted as a finish"
    assert report.protocol_violations == 1
    assert any(record.tool == "finish" and record.refused for record in report.actions)


def test_finish_on_an_incomplete_task_is_a_surfaced_protocol_violation() -> None:
    model = ScriptedModel([_tool("finish"), _tool("finish")])
    toolbox = RecordingToolbox(task_ok_result=False)

    report = drive(mission="m", model="scripted", ask=model, toolbox=toolbox, seed="seed", turns=2)

    assert report.finished is False, "finish must be refused while the task is incomplete"
    assert report.protocol_violations >= 1
    assert any(record.tool == "finish" and record.refused for record in report.actions)


def test_finish_in_the_same_batch_as_a_refused_gate_is_a_violation() -> None:
    reply = _tool("run_gate") + "\n" + _tool("finish")
    model = ScriptedModel([reply])
    toolbox = RecordingToolbox(gate_results=[True])

    report = drive(mission="m", model="scripted", ask=model, toolbox=toolbox, seed="seed", turns=1)

    assert report.finished is False
    assert report.protocol_violations == 1


def test_finish_after_fixing_a_refused_gate_is_accepted() -> None:
    model = ScriptedModel([_tool("run_gate"), _tool("finish"), _tool("run_gate"), _tool("finish")])
    toolbox = RecordingToolbox(gate_results=[True, False])

    report = drive(mission="m", model="scripted", ask=model, toolbox=toolbox, seed="seed", turns=4)

    assert report.protocol_violations == 1
    assert report.finished is True


def test_finish_after_a_clean_gate_is_accepted() -> None:
    model = ScriptedModel([_tool("run_gate"), _tool("finish")])
    toolbox = RecordingToolbox(gate_results=[False])

    report = drive(mission="m", model="scripted", ask=model, toolbox=toolbox, seed="seed", turns=2)

    assert report.finished is True
    assert report.protocol_violations == 0


def test_a_prose_reply_is_counted_and_the_loop_continues() -> None:
    model = ScriptedModel(["Let me think about this.", _tool("finish")])
    toolbox = RecordingToolbox()

    report = drive(mission="m", model="scripted", ask=model, toolbox=toolbox, seed="seed", turns=2)

    assert report.format_errors == 1
    assert report.finished is True, "a format error must not stop the loop"


def test_the_turn_budget_bounds_the_loop() -> None:
    model = ScriptedModel([_tool("read_file", path="a")] * 3)
    toolbox = RecordingToolbox()

    report = drive(mission="m", model="scripted", ask=model, toolbox=toolbox, seed="seed", turns=2)

    assert report.turns_used == 2
    assert report.turn_budget == 2
    assert report.finished is False
    assert toolbox.calls == ["read_file", "read_file"]


def test_drive_propagates_a_model_failure_loudly() -> None:
    class Boom:
        def __call__(self, messages: Sequence[dict[str, str]]) -> str:
            raise ModelUnavailableError("connection refused")

    with pytest.raises(ModelUnavailableError, match=STEER_MODEL_UNAVAILABLE):
        drive(mission="m", model="boom", ask=Boom(), toolbox=RecordingToolbox(), seed="seed", turns=1)


# ---------------------------------------------------------------------------
# T022 -- the local adapter fails loudly
# ---------------------------------------------------------------------------


def test_http_client_reports_an_unreachable_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(request: object, timeout: float | None = None) -> object:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    client = HttpModelClient(endpoint="http://127.0.0.1:1/v1/chat/completions")

    with pytest.raises(ModelUnavailableError, match=STEER_MODEL_UNAVAILABLE):
        client([{"role": "user", "content": "hi"}])


def test_http_client_rejects_an_empty_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.dumps({"choices": [{"message": {"content": "   "}}]}).encode("utf-8")

    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *exc: object) -> bool:
            return False

        def read(self) -> bytes:
            return payload

    monkeypatch.setattr(urllib.request, "urlopen", lambda request, timeout=None: FakeResponse())
    client = HttpModelClient(endpoint="http://model/v1/chat/completions")

    with pytest.raises(EmptyModelResponseError, match=STEER_MODEL_EMPTY):
        client([{"role": "user", "content": "hi"}])


def test_http_client_rejects_a_malformed_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.dumps({"unexpected": True}).encode("utf-8")

    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *exc: object) -> bool:
            return False

        def read(self) -> bytes:
            return payload

    monkeypatch.setattr(urllib.request, "urlopen", lambda request, timeout=None: FakeResponse())
    client = HttpModelClient(endpoint="http://model/v1/chat/completions")

    with pytest.raises(EmptyModelResponseError, match=STEER_MODEL_EMPTY):
        client([{"role": "user", "content": "hi"}])


def test_http_client_returns_the_reply_text(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.dumps({"choices": [{"message": {"content": '{"tool": "finish", "args": {}}'}}]}).encode("utf-8")

    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *exc: object) -> bool:
            return False

        def read(self) -> bytes:
            return payload

    monkeypatch.setattr(urllib.request, "urlopen", lambda request, timeout=None: FakeResponse())
    client = HttpModelClient(endpoint="http://model/v1/chat/completions")

    assert client([{"role": "user", "content": "hi"}]) == '{"tool": "finish", "args": {}}'


# ---------------------------------------------------------------------------
# Toolbox -- sandbox confinement, gates and fetches
# ---------------------------------------------------------------------------


def _box(tmp_path: Path, *, gate_problems: list[str] | None = None) -> SandboxToolbox:
    return SandboxToolbox(root=tmp_path, gate=lambda: list(gate_problems or []), fetch=lambda selector: f"body:{selector}")


def test_sandbox_write_then_read_round_trips(tmp_path: Path) -> None:
    box = _box(tmp_path)
    assert box.execute(Action("write_file", {"path": "app.py", "content": "x = 1\n"})).output == "ok"
    assert box.execute(Action("read_file", {"path": "app.py"})).output == "x = 1\n"
    assert box.writes == ["app.py"]


def test_sandbox_refuses_to_write_outside_the_root(tmp_path: Path) -> None:
    box = _box(tmp_path)
    result = box.execute(Action("write_file", {"path": "../escape.py", "content": "x"}))
    assert result.output.startswith("ERROR: refusing to write outside the sandbox")
    assert not (tmp_path.parent / "escape.py").exists()


def test_sandbox_reports_a_missing_file(tmp_path: Path) -> None:
    assert _box(tmp_path).execute(Action("read_file", {"path": "nope.py"})).output.startswith("ERROR: no such file")


def test_sandbox_gate_refusal_is_flagged(tmp_path: Path) -> None:
    box = _box(tmp_path, gate_problems=["ruff: boom"])
    result = box.execute(Action("run_gate", {}))
    assert result.refused is True
    assert "REFUSED" in result.output
    assert box.gate_calls == 1


def test_sandbox_gate_is_clean_without_problems(tmp_path: Path) -> None:
    result = _box(tmp_path).execute(Action("run_gate", {}))
    assert result.refused is False
    assert result.output == "clean"


def test_sandbox_fetch_returns_the_body(tmp_path: Path) -> None:
    box = _box(tmp_path)
    result = box.execute(Action("fetch_doctrine", {"selector": "directive:X"}))
    assert result.output == "body:directive:X"
    assert box.fetches == ["directive:X"]


def test_sandbox_fetch_reports_an_unknown_selector(tmp_path: Path) -> None:
    def boom(selector: str) -> str:
        raise LookupError("unknown selector")

    box = SandboxToolbox(root=tmp_path, gate=lambda: [], fetch=boom)
    assert box.execute(Action("fetch_doctrine", {"selector": "directive:X"})).output.startswith("ERROR: cannot fetch")


def test_sandbox_rejects_an_unknown_tool(tmp_path: Path) -> None:
    assert _box(tmp_path).execute(Action("nope", {})).output.startswith("ERROR: unknown tool")


def test_sandbox_run_tests_reports_pass_then_fail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    box = _box(tmp_path)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, "1 passed", ""))
    assert box.execute(Action("run_tests", {})).output == "PASS"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, "1 failed", ""))
    assert box.execute(Action("run_tests", {})).output.startswith("FAIL")


def test_sandbox_run_tests_reports_a_missing_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*a: object, **k: object) -> object:
        raise FileNotFoundError("pytest")

    monkeypatch.setattr(subprocess, "run", boom)
    box = _box(tmp_path)
    assert box.execute(Action("run_tests", {})).output.startswith("ERROR: test command unavailable")


# ---------------------------------------------------------------------------
# T021 -- the CLI entry point
# ---------------------------------------------------------------------------


def test_build_seed_carries_kernel_capsule_and_protocol(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from specify_cli.steering import capsule as capsule_module

    monkeypatch.setattr(capsule_module, "build_capsule", lambda mission, *, repo_root: object())
    monkeypatch.setattr(capsule_module, "render", lambda capsule: "# CAPSULE\nstep: implement\n")
    seed = driver.build_seed("demo", repo_root=tmp_path)
    assert render_kernel() in seed
    assert "# CAPSULE" in seed
    assert '"tool": "finish"' in seed


class _FakeClient:
    model = "fake-model"

    def __init__(self, **_kwargs: object) -> None:
        pass

    def __call__(self, messages: Sequence[dict[str, str]]) -> str:
        return _tool("finish")


def test_run_reports_a_scored_json_transcript(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(driver, "build_seed", lambda mission, *, repo_root: "seed")
    monkeypatch.setattr(driver, "_prepare_sandbox", lambda: tmp_path)
    monkeypatch.setattr(driver, "_default_gate", lambda root, mission: [])
    monkeypatch.setattr(driver, "_default_fetch", lambda root, selector: "body")
    monkeypatch.setattr(driver, "HttpModelClient", _FakeClient)
    _seed_complete_sandbox(tmp_path)

    driver.run("demo", model="x", turns=2, json_output=True)

    payload = json.loads(capsys.readouterr().out)
    assert payload["mission"] == "demo"
    assert payload["model"] == "fake-model"
    assert payload["finished"] is True


def test_run_prints_a_human_score_card(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(driver, "build_seed", lambda mission, *, repo_root: "seed")
    monkeypatch.setattr(driver, "_prepare_sandbox", lambda: tmp_path)
    monkeypatch.setattr(driver, "_default_gate", lambda root, mission: [])
    monkeypatch.setattr(driver, "_default_fetch", lambda root, selector: "body")
    monkeypatch.setattr(driver, "HttpModelClient", _FakeClient)
    _seed_complete_sandbox(tmp_path)

    driver.run("demo", model="x", turns=1, json_output=False)

    out = capsys.readouterr().out
    assert "===== SCORE =====" in out
    assert "finished     : True" in out


def test_steer_loop_forwards_its_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(mission: str | None, *, model: str | None = None, turns: int = 1, json_output: bool = False) -> None:
        captured.update(mission=mission, model=model, turns=turns, json_output=json_output)

    monkeypatch.setattr(driver, "run", fake_run)
    result = CliRunner().invoke(steer_module.app, ["loop", "--mission", "demo", "--model", "m", "--turns", "3", "--json"])

    assert result.exit_code == 0
    assert captured == {"mission": "demo", "model": "m", "turns": 3, "json_output": True}
