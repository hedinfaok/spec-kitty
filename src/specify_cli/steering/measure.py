"""Steering-context measurement (WP07 / T026-T028).

Reports the *lean* steering sizes -- the standing kernel (WP01) and a rendered
per-step capsule (WP03) -- against the baseline corpus they replace, so the
reduction required by SC-001 (standing <= 1 KB from ~101 KB) and SC-002 (payload
<= 2 KB from 81-95 KB first load) is verifiable and reproducible.

**Everything measured here is derived from the live artifacts**, never hardcoded:
``standing_bytes`` is the byte length of :func:`specify_cli.steering.kernel.render_kernel`
and ``capsule_bytes`` is the byte length of :func:`specify_cli.steering.capsule.render`
applied to a capsule built from real engine state for the requested Mission. Only
the *baseline* is a constant, because it is a citation from a past measurement,
not a value this repository can recompute:

* :data:`BASELINE_STANDING_BYTES` -- the standing corpus (``AGENTS.md`` plus
  ``.kittify/overrides/AGENTS.md``) measured at 101,438 bytes (~101 KB), from the
  validated lean-steering spike (``research-outputs/lean-steering-spike/README.md``)
  and mission ``analyze-prompt-context-load-01M3F4BV`` (#5005).
* :data:`BASELINE_PAYLOAD_BYTES` -- the engine's rendered action payload for
  ``implement``, 95,139 bytes at first load (#5005 section 9.2; the range is
  81-95 KB).

The reduction is reported per axis (:attr:`Measurement.reduction`), because the
standing text is paid every turn and the action payload once per step; they are
not summed.

Adapted from the spike's ``measure`` (``research-outputs/lean-steering-spike/sk.py``).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from specify_cli.steering.capsule import SteerCapsuleError, build_capsule, render
from specify_cli.steering.kernel import render_kernel

if TYPE_CHECKING:  # pragma: no cover - import only for type checkers
    from specify_cli.steering.capsule import Capsule

#: Standing corpus the kernel replaces (~101 KB): ``AGENTS.md`` +
#: ``.kittify/overrides/AGENTS.md``, measured at 101,438 bytes (#5005;
#: ``research-outputs/lean-steering-spike/README.md``).
BASELINE_STANDING_BYTES: int = 101_438

#: Engine action payload the capsule replaces (81-95 KB at first load); the
#: cited number is 95,139 bytes for ``implement`` (#5005 section 9.2).
BASELINE_PAYLOAD_BYTES: int = 95_139

#: Stable error code for a measurement that cannot be derived (bad Mission handle).
STEER_MEASURE_ERROR = "STEER_MEASURE_ERROR"

#: Approximate bytes-per-token used only for the human-readable report.
_BYTES_PER_TOKEN = 4


@dataclass(frozen=True, slots=True)
class Measurement:
    """The measured steering sizes plus the cited baseline (T026)."""

    standing_bytes: int
    capsule_bytes: int
    baseline_standing_bytes: int
    baseline_payload_bytes: int

    @property
    def reduction(self) -> dict[str, float]:
        """The reduction ratio per axis, as ``{standing, payload}``.

        Each value is ``baseline_bytes / measured_bytes`` -- the factor by which
        the lean artifact shrinks the baseline it replaces. A larger value is a
        larger reduction.
        """
        return {
            "standing": _ratio(self.baseline_standing_bytes, self.standing_bytes),
            "payload": _ratio(self.baseline_payload_bytes, self.capsule_bytes),
        }

    def to_payload(self) -> dict[str, object]:
        """Return the JSON-persistable form (the ``steer measure --json`` contract)."""
        return {
            "standing_bytes": self.standing_bytes,
            "capsule_bytes": self.capsule_bytes,
            "baseline_standing_bytes": self.baseline_standing_bytes,
            "baseline_payload_bytes": self.baseline_payload_bytes,
            "reduction": self.reduction,
        }


# ---------------------------------------------------------------------------
# Live measurement
# ---------------------------------------------------------------------------


def standing_bytes() -> int:
    """Return the live standing size: the UTF-8 byte length of the kernel (WP01)."""
    return len(render_kernel().encode("utf-8"))


def capsule_bytes(capsule: Capsule) -> int:
    """Return the live per-step size: the UTF-8 byte length of the rendered capsule (WP03)."""
    return len(render(capsule).encode("utf-8"))


def measure(mission: str | None, *, repo_root: Path | None = None, decision: dict[str, object] | None = None) -> Measurement:
    """Measure the standing and per-step steering sizes against the cited baseline (T026).

    The per-step size is a capsule rendered for *mission*; *decision* may be
    injected (tests, or a caller that already holds the engine decision) exactly
    as :func:`specify_cli.steering.capsule.build_capsule` accepts it. Nothing is
    hardcoded: the standing bytes come from the kernel and the capsule bytes
    come from the rendered capsule for this Mission.
    """
    root = repo_root if repo_root is not None else _default_repo_root()
    capsule = build_capsule(mission, repo_root=root, decision=decision)
    return Measurement(
        standing_bytes=standing_bytes(),
        capsule_bytes=capsule_bytes(capsule),
        baseline_standing_bytes=BASELINE_STANDING_BYTES,
        baseline_payload_bytes=BASELINE_PAYLOAD_BYTES,
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_report(measurement: Measurement) -> str:
    """Render the human-readable size comparison (the non-``--json`` form)."""
    reduction = measurement.reduction
    standing = measurement.standing_bytes
    capsule = measurement.capsule_bytes
    lines = [
        "== Per turn (standing steering text) ==",
        f"{'today: standing corpus':32s} {measurement.baseline_standing_bytes:8d} bytes  ~{_tokens(measurement.baseline_standing_bytes):6d} tokens",
        f"{'lean: kernel':32s} {standing:8d} bytes  ~{_tokens(standing):6d} tokens",
        f"{'reduction':32s} {reduction['standing']:8.1f}x",
        "",
        "== Per step (action payload, first load) ==",
        f"{'today: payload (first load)':32s} {measurement.baseline_payload_bytes:8d} bytes  ~{_tokens(measurement.baseline_payload_bytes):6d} tokens  (#5005)",
        f"{'lean: capsule':32s} {capsule:8d} bytes  ~{_tokens(capsule):6d} tokens",
        f"{'reduction':32s} {reduction['payload']:8.1f}x",
    ]
    return "\n".join(lines) + "\n"


def run(mission: str | None, *, json_output: bool = False) -> None:
    """CLI entry point for ``spec-kitty steer measure --mission <handle>`` (WP01 lazy import)."""
    import typer

    try:
        measurement = measure(mission)
    except SteerCapsuleError as exc:
        _emit_error(exc, json_output=json_output)
        raise typer.Exit(code=1) from exc
    if json_output:
        print(json.dumps(measurement.to_payload(), indent=2))
        return
    print(render_report(measurement), end="")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ratio(baseline: int, measured: int) -> float:
    """Return ``baseline / measured``; a zero measurement never divides by zero."""
    return baseline / max(measured, 1)


def _tokens(size: int) -> int:
    return round(size / _BYTES_PER_TOKEN)


def _default_repo_root() -> Path:
    from specify_cli.task_utils import find_repo_root

    return find_repo_root()


def _emit_error(exc: SteerCapsuleError, *, json_output: bool) -> None:
    message = str(exc)
    if json_output:
        print(json.dumps({"success": False, "error": STEER_MEASURE_ERROR, "message": message}), file=sys.stderr)
    else:
        print(f"Error: {message}", file=sys.stderr)
