"""Kernel invariants and the ``steer kernel`` CLI surface (WP01 / T004).

The kernel is the only standing steering text injected per turn, so these tests
pin the invariants that keep it lean, stable and Mission-agnostic. The size
bound is deliberately **two-sided**: an empty or gutted kernel fails the lower
bound, and silent growth past the standing budget fails the upper bound.
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from specify_cli.cli.commands import steer as steer_module
from specify_cli.steering.kernel import KERNEL_TEXT, render_kernel

#: The three protocol rules the kernel must state (FR-001).
PROTOCOL_MARKERS = (
    "State is authoritative",
    "Doctrine is fetched, not inlined",
    "Invariants are machine gates",
)

#: This Mission's slug -- the kernel must carry no mission-specific token.
MISSION_SLUG = "context-lean-steering-01M4F5GH"

#: Standing budget: <= 1 KB, and (non-vacuity) a kernel that is not obviously
#: a real kernel fails the lower bound.
KERNEL_MIN_BYTES = 200
KERNEL_MAX_BYTES = 1024


def test_kernel_size_is_two_sided() -> None:
    size = len(render_kernel().encode("utf-8"))
    assert size > KERNEL_MIN_BYTES
    assert size <= KERNEL_MAX_BYTES


def test_kernel_is_byte_stable_across_calls() -> None:
    assert render_kernel() == render_kernel() == KERNEL_TEXT


def test_kernel_states_three_protocol_rules() -> None:
    text = render_kernel()
    for marker in PROTOCOL_MARKERS:
        assert marker in text


def test_kernel_carries_no_mission_specific_content() -> None:
    assert MISSION_SLUG not in render_kernel()


def test_steer_kernel_prints_the_kernel() -> None:
    result = CliRunner().invoke(steer_module.app, ["kernel"])
    assert result.exit_code == 0
    assert result.stdout.strip() == render_kernel().strip()


def test_steer_kernel_json_reports_byte_count() -> None:
    result = CliRunner().invoke(steer_module.app, ["kernel", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["bytes"] == len(render_kernel().encode("utf-8"))
    assert payload["text"] == render_kernel()


def test_steer_help_lists_every_subcommand() -> None:
    result = CliRunner().invoke(steer_module.app, ["--help"])
    assert result.exit_code == 0
    for name in ("kernel", "capsule", "fetch", "check", "measure", "loop"):
        assert name in result.stdout
