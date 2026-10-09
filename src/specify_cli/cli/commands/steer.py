"""``spec-kitty steer`` -- the additive lean-steering CLI surface (WP01 / T001, T003).

This module owns the whole ``steer`` command group. Only ``steer kernel`` is
fully wired here (T003). Every other subcommand delegates to a module that a
later work package adds, and therefore lazy-imports that module *inside the
handler* so this module imports cleanly before those modules exist; a
subcommand whose module is absent fails only when it is invoked.

Delegate convention (each later module exposes ``run(...)``):

* ``steering.capsule.run(mission, json_output)``                 -> ``steer capsule --mission``
* ``steering.index.run(selector, json_output)``                  -> ``steer fetch <selector>``
* ``steering.gates.run(mission, json_output)``                   -> ``steer check --mission``
* ``steering.measure.run(mission, json_output)``                 -> ``steer measure --mission``
* ``steering.driver.run(mission, model, turns, json_output)``    -> ``steer loop``

This is a purely additive surface: no existing command or contract is changed
(NFR-002, C-001).
"""

from __future__ import annotations

import json
from typing import Annotated

import typer

app = typer.Typer(help="Lean steering: standing kernel, per-step capsule and binding gates.")


@app.command("kernel")
def kernel_command(
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON {bytes, text}.")] = False,
) -> None:
    """Print the standing steering kernel (<= 1024 bytes; byte-stable across calls)."""
    from specify_cli.steering.kernel import render_kernel

    text = render_kernel()
    if json_output:
        print(json.dumps({"bytes": len(text.encode("utf-8")), "text": text}))
        return
    print(text)


@app.command("capsule")
def capsule_command(
    mission: Annotated[str | None, typer.Option("--mission", help="Mission handle (mission_id / mid8 / slug).")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = False,
) -> None:
    """Emit the bounded per-step capsule derived from Mission state (WP03)."""
    from specify_cli.steering import capsule

    capsule.run(mission, json_output=json_output)


@app.command("fetch")
def fetch_command(
    selector: Annotated[str, typer.Argument(help="Doctrine selector, e.g. directive:DIRECTIVE_030.")],
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = False,
) -> None:
    """Fetch one doctrine body on demand from canonical sources (WP02)."""
    from specify_cli.steering import index

    index.run(selector, json_output=json_output)


@app.command("check")
def check_command(
    mission: Annotated[str | None, typer.Option("--mission", help="Mission handle (mission_id / mid8 / slug).")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = False,
) -> None:
    """Run the binding machine gates; any problem exits non-zero (WP04)."""
    from specify_cli.steering import gates

    gates.run(mission, json_output=json_output)


@app.command("measure")
def measure_command(
    mission: Annotated[str | None, typer.Option("--mission", help="Mission handle (mission_id / mid8 / slug).")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = False,
) -> None:
    """Report standing and per-step steering sizes against a baseline (WP07)."""
    from specify_cli.steering import measure

    measure.run(mission, json_output=json_output)


@app.command("loop")
def loop_command(
    mission: Annotated[str | None, typer.Option("--mission", help="Mission handle (mission_id / mid8 / slug).")] = None,
    model: Annotated[str | None, typer.Option("--model", help="Model id to drive.")] = None,
    turns: Annotated[int, typer.Option("--turns", help="Maximum number of driver turns.")] = 1,
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = False,
) -> None:
    """Run the driver loop: render kernel + capsule, execute each action (WP05)."""
    from specify_cli.steering import driver

    driver.run(mission, model=model, turns=turns, json_output=json_output)
