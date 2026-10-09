"""Steering-context measurement: liveness, reproducibility, CLI surface (WP07 / T026-T028).

These tests pin the three contracts ``measure.py`` owns:

* **live** -- ``standing_bytes`` is derived from the kernel and ``capsule_bytes``
  from a rendered capsule, so changing either changes the measurement (T026);
* **reproducible** -- two runs agree and each reported reduction equals the ratio
  computed from its own measurement (T028);
* **exposed** -- ``steer measure --json`` returns exactly the contract keys, with
  the two cited baselines labelled (T027).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from specify_cli.cli.commands import steer as steer_module
from specify_cli.steering import capsule as capsule_module
from specify_cli.steering import measure
from specify_cli.steering.capsule import Capsule, SteerCapsuleError
from specify_cli.task_utils import find_repo_root

MISSION_SLUG = "context-lean-steering-01M4F5GH"

#: A fixed engine decision so the tests never depend on the live board
#: (the real query may report ``wp_id: null`` or a different step).
FIXED_DECISION: dict[str, object] = {
    "preview_step": "implement",
    "mission_state": "implement",
    "mission_slug": MISSION_SLUG,
    "wp_id": "WP07",
}

#: The exact JSON contract keys (contracts/steering-cli.md).
EXPECTED_KEYS = {
    "standing_bytes",
    "capsule_bytes",
    "baseline_standing_bytes",
    "baseline_payload_bytes",
    "reduction",
}


@pytest.fixture(scope="module")
def repo_root() -> Path:
    return find_repo_root()


@pytest.fixture(scope="module")
def fixed_capsule(repo_root: Path) -> Capsule:
    return capsule_module.build_capsule(MISSION_SLUG, repo_root=repo_root, decision=FIXED_DECISION)


def _patch_build_capsule(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    """Route ``measure.build_capsule`` to a capsule built from the fixed decision."""

    def _build(mission: str | None, *, repo_root: Path | None = None, decision: dict[str, object] | None = None) -> Capsule:
        return capsule_module.build_capsule(MISSION_SLUG, repo_root=root, decision=FIXED_DECISION)

    monkeypatch.setattr(measure, "build_capsule", _build)


# ---------------------------------------------------------------------------
# T026 -- live measurement, cited baselines
# ---------------------------------------------------------------------------


def test_standing_bytes_is_the_live_kernel_size() -> None:
    assert measure.standing_bytes() == len(measure.render_kernel().encode("utf-8"))
    assert measure.standing_bytes() > 0


def test_capsule_bytes_is_the_live_rendered_size(fixed_capsule: Capsule) -> None:
    assert measure.capsule_bytes(fixed_capsule) == len(capsule_module.render(fixed_capsule).encode("utf-8"))
    assert measure.capsule_bytes(fixed_capsule) > 0


def test_measure_reports_the_live_sizes(repo_root: Path, fixed_capsule: Capsule, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_build_capsule(monkeypatch, repo_root)
    measurement = measure.measure(MISSION_SLUG)
    assert measurement.standing_bytes == measure.standing_bytes()
    assert measurement.capsule_bytes == measure.capsule_bytes(fixed_capsule)
    assert measurement.baseline_standing_bytes == measure.BASELINE_STANDING_BYTES
    assert measurement.baseline_payload_bytes == measure.BASELINE_PAYLOAD_BYTES


def test_baselines_are_the_cited_constants() -> None:
    # 101,438 bytes is the ~101 KB standing corpus (AGENTS.md + overrides, #5005);
    # the payload baseline is the 81-95 KB first-load action payload (#5005 section 9.2).
    assert measure.BASELINE_STANDING_BYTES == 101_438
    assert 81_000 <= measure.BASELINE_PAYLOAD_BYTES <= 96_000  # the cited 81-95 KB band, rounded up
    assert measure.BASELINE_PAYLOAD_BYTES == 95_139


# ---------------------------------------------------------------------------
# T028 -- reproducibility and reduction arithmetic
# ---------------------------------------------------------------------------


def test_two_runs_agree(repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_build_capsule(monkeypatch, repo_root)
    first = measure.measure(MISSION_SLUG).to_payload()
    second = measure.measure(MISSION_SLUG).to_payload()
    assert first == second


def test_reduction_equals_the_computed_ratio(repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_build_capsule(monkeypatch, repo_root)
    measurement = measure.measure(MISSION_SLUG)
    assert measurement.reduction["standing"] == measure.BASELINE_STANDING_BYTES / measurement.standing_bytes
    assert measurement.reduction["payload"] == measure.BASELINE_PAYLOAD_BYTES / measurement.capsule_bytes
    # The lean artifacts must actually reduce (SC-001 / SC-002 are >= 90x / >= 40x).
    assert measurement.reduction["standing"] > 1.0
    assert measurement.reduction["payload"] > 1.0


def test_standing_measurement_reflects_the_kernel(monkeypatch: pytest.MonkeyPatch) -> None:
    original = measure.standing_bytes()
    grown = "x" * (original + 5_000)
    monkeypatch.setattr(measure, "render_kernel", lambda: grown)
    assert measure.standing_bytes() == len(grown.encode("utf-8"))
    assert measure.standing_bytes() != original


def test_reduction_never_divides_by_zero() -> None:
    assert measure._ratio(101_438, 0) == 101_438.0


# ---------------------------------------------------------------------------
# T027 -- the CLI surface
# ---------------------------------------------------------------------------


def test_steer_measure_json_matches_the_contract(repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_build_capsule(monkeypatch, repo_root)
    result = CliRunner().invoke(steer_module.app, ["measure", "--mission", MISSION_SLUG, "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert set(payload) == EXPECTED_KEYS
    measurement = measure.measure(MISSION_SLUG)
    assert payload["standing_bytes"] == measurement.standing_bytes
    assert payload["capsule_bytes"] == measurement.capsule_bytes
    assert payload["baseline_standing_bytes"] == measure.BASELINE_STANDING_BYTES
    assert payload["baseline_payload_bytes"] == measure.BASELINE_PAYLOAD_BYTES
    assert set(payload["reduction"]) == {"standing", "payload"}


def test_steer_measure_prints_the_report(repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_build_capsule(monkeypatch, repo_root)
    result = CliRunner().invoke(steer_module.app, ["measure", "--mission", MISSION_SLUG])
    assert result.exit_code == 0
    assert "kernel" in result.stdout
    assert "capsule" in result.stdout
    assert "reduction" in result.stdout
    assert f"{measure.standing_bytes():8d} bytes" in result.stdout


def test_steer_measure_reports_a_bad_mission(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(mission: str | None, *, repo_root: Path | None = None, decision: dict[str, object] | None = None) -> Capsule:
        raise SteerCapsuleError(f"{capsule_module.STEER_CAPSULE_ERROR}: no such mission")

    monkeypatch.setattr(measure, "build_capsule", _boom)
    result = CliRunner().invoke(steer_module.app, ["measure", "--mission", "nope", "--json"])
    assert result.exit_code == 1
    assert measure.STEER_MEASURE_ERROR in result.stderr
