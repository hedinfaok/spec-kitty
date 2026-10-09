"""Context-lean steering layer (FR-001..FR-007).

Additive over the existing ``spec-kitty`` engine: the standing kernel
(:mod:`specify_cli.steering.kernel`), the per-step capsule, the doctrine index,
the machine gates, the driver loop and the steering-context measurement. No
engine module is modified; the CLI surface is ``spec-kitty steer``.

This package ``__init__`` stays deliberately light -- no heavy imports -- so
importing :mod:`specify_cli.steering` never drags a submodule graph into a
command that does not need it.
"""
