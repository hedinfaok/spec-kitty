"""Local execution tiers (WP06 / IC-06, FR-006, NFR-006, C-004, SC-004).

Route a step across the local execution tiers -- **T0 retrieval** (deterministic,
always local, never a model call), **T1 routing**, **T2 drafting** and **T3 full
loop** -- and talk to a local OpenAI-compatible model server without ever failing
silently.

The two defects this module exists to prevent (``lean-loop-test.md``):

* a step routed to the wrong tier (retrieval that secretly calls a model, or a
  full loop silently downgraded to a single draft);
* a provider quirk -- an unreachable server, an unloaded model, an empty or
  malformed completion -- swallowed into an empty string.

The tier policy is data-driven and inspectable: :data:`NATURE_TIERS` and
:data:`STEP_NATURES` are the whole policy and :func:`policy_table` renders it, so
there is no hidden behaviour to reverse-engineer. The provider reuses WP05's
:class:`~specify_cli.steering.driver.HttpModelClient` for the OpenAI-compatible
call (stdlib ``urllib`` only -- no new third-party dependency) and adds a loud
unloaded-model probe on top; it never returns an empty string.

The endpoint shape is pinned to the OpenAI-compatible contract
(``POST /v1/chat/completions``; ``GET /v1/models`` for the loaded-model probe).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum

from specify_cli.steering.driver import HttpModelClient, ModelUnavailableError

# ``src/specify_cli/`` modules are not required to declare ``__all__`` (C-007
# binds ``src/charter/`` and ``src/kernel/`` only). The public surface here is
# :func:`resolve_tier`, :func:`policy_table`, :class:`Tier`, :class:`StepNature`
# and :class:`LocalProvider`.

#: Stable error code: the endpoint answered, but the configured model is absent.
STEER_MODEL_NOT_LOADED = "STEER_MODEL_NOT_LOADED"

#: Stable error code: a step was routed to a tier that never calls a model.
STEER_TIER_NO_MODEL = "STEER_TIER_NO_MODEL"


class ModelNotLoadedError(RuntimeError):
    """The endpoint is reachable, but the configured model is not loaded.

    Carries :data:`STEER_MODEL_NOT_LOADED` as :attr:`code` so the failure is
    machine-checkable, matching WP05's typed provider errors.
    """

    code = STEER_MODEL_NOT_LOADED

    def __init__(self, message: str) -> None:
        super().__init__(f"{STEER_MODEL_NOT_LOADED}: {message}")


class TierPolicyError(RuntimeError):
    """A step was routed to a tier that cannot serve it.

    T0 retrieval is deterministic and local; it never calls a model, so asking
    the provider to complete a T0 step is a programming error, not a silent no-op.
    """

    code = STEER_TIER_NO_MODEL

    def __init__(self, message: str) -> None:
        super().__init__(f"{STEER_TIER_NO_MODEL}: {message}")


# ---------------------------------------------------------------------------
# The tier vocabulary and the inspectable policy (T023)
# ---------------------------------------------------------------------------


class Tier(IntEnum):
    """The four local execution tiers, cheapest first.

    The integer value is the escalation order, so ``Tier.T0_RETRIEVAL <
    Tier.T3_FULL_LOOP`` holds and a caller can compare tiers without a lookup.
    """

    T0_RETRIEVAL = 0
    T1_ROUTING = 1
    T2_DRAFTING = 2
    T3_FULL_LOOP = 3

    @property
    def label(self) -> str:
        """The operator-facing name, e.g. ``"T0"``."""
        return f"T{int(self)}"

    @property
    def uses_model(self) -> bool:
        """Whether the tier calls the local model.

        T0 retrieval is deterministic (the doctrine index); T1-T3 all call the
        local OpenAI-compatible model.
        """
        return self is not Tier.T0_RETRIEVAL


class StepNature(StrEnum):
    """What a step *does* -- the axis the tier policy actually keys on.

    A step name is a human handle; its nature is the stable routing fact. An
    explicit nature can route a step the name table does not know.
    """

    RETRIEVAL = "retrieval"
    ROUTING = "routing"
    DRAFTING = "drafting"
    FULL_LOOP = "full_loop"


#: The data-driven core of the policy: what each nature costs.
NATURE_TIERS: dict[StepNature, Tier] = {
    StepNature.RETRIEVAL: Tier.T0_RETRIEVAL,
    StepNature.ROUTING: Tier.T1_ROUTING,
    StepNature.DRAFTING: Tier.T2_DRAFTING,
    StepNature.FULL_LOOP: Tier.T3_FULL_LOOP,
}

#: Step name -> nature. Keys are step *bases* (the token before any ``:reason``
#: suffix), matching the per-step capsule's convention. A step name that is not
#: here falls back to :data:`DEFAULT_TIER`.
STEP_NATURES: dict[str, StepNature] = {
    # T0 -- deterministic retrieval, always local, never a model call.
    "retrieve": StepNature.RETRIEVAL,
    "fetch": StepNature.RETRIEVAL,
    "capsule": StepNature.RETRIEVAL,
    "kernel": StepNature.RETRIEVAL,
    "measure": StepNature.RETRIEVAL,
    # T1 -- routing: which step comes next.
    "route": StepNature.ROUTING,
    "next": StepNature.ROUTING,
    "status": StepNature.ROUTING,
    # T2 -- drafting: one-shot artifact authoring.
    "specify": StepNature.DRAFTING,
    "plan": StepNature.DRAFTING,
    "tasks": StepNature.DRAFTING,
    "research": StepNature.DRAFTING,
    # T3 -- full loop: multi-turn tool use under the binding gates.
    "implement": StepNature.FULL_LOOP,
    "review": StepNature.FULL_LOOP,
    "accept": StepNature.FULL_LOOP,
    "merge": StepNature.FULL_LOOP,
    "consolidate": StepNature.FULL_LOOP,
}

#: Tier for a step the policy does not recognise. The full loop is the most
#: capable local tier, so an unknown step is never silently under-served (a
#: silent downgrade to retrieval is the failure this mission removes).
DEFAULT_TIER: Tier = Tier.T3_FULL_LOOP


def _step_base(step: str) -> str:
    """Return the step's base: the token before any ``:reason`` suffix."""
    return step.split(":", 1)[0].strip().lower()


def resolve_tier(step: str, *, nature: StepNature | None = None) -> Tier:
    """Return the tier for *step*, deterministically.

    An explicit *nature* wins, so a caller that knows what a step does can route
    it even when the step name is not in :data:`STEP_NATURES`. Otherwise the
    step's base is looked up; an unknown step falls back to :data:`DEFAULT_TIER`.
    The same inputs always yield the same tier -- there is no state and no clock.
    """
    if nature is not None:
        return NATURE_TIERS[nature]
    step_nature = STEP_NATURES.get(_step_base(step))
    if step_nature is None:
        return DEFAULT_TIER
    return NATURE_TIERS[step_nature]


def policy_table() -> dict[str, dict[str, str]]:
    """Render the whole policy, inspectably.

    Returns ``step -> {"nature": <nature>, "tier": <label>}``. The table is
    derived from the two module constants, so it can never drift from the
    behaviour :func:`resolve_tier` applies.
    """
    return {step: {"nature": nature.value, "tier": NATURE_TIERS[nature].label} for step, nature in sorted(STEP_NATURES.items())}


# ---------------------------------------------------------------------------
# The local provider adapter with loud errors (T024)
# ---------------------------------------------------------------------------


def models_endpoint(endpoint: str) -> str:
    """Derive the ``/v1/models`` URL from a chat-completions endpoint."""
    base, sep, _ = endpoint.partition("/chat/completions")
    if sep:
        return f"{base}/models"
    parts = urllib.parse.urlsplit(endpoint)
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, "/v1/models", "", ""))


def _parse_model_ids(raw: bytes) -> frozenset[str] | None:
    """Return the model ids in an OpenAI ``/v1/models`` body.

    ``None`` means the body could not be read as a model list -- the probe then
    steps aside rather than inventing a failure, because an unreadable list is
    not evidence that the model is unloaded.
    """
    try:
        entries = json.loads(raw)["data"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return None
    if not isinstance(entries, list):
        return None
    return frozenset(entry["id"] for entry in entries if isinstance(entry, dict) and isinstance(entry.get("id"), str))


@dataclass(slots=True)
class LocalProvider:
    """A tier-aware local provider over an OpenAI-compatible endpoint.

    The transport is WP05's :class:`~specify_cli.steering.driver.HttpModelClient`,
    reused rather than re-implemented; this class adds the tier gate and a loud
    unloaded-model probe. Every provider quirk raises -- it never returns an
    empty string.
    """

    client: HttpModelClient = field(default_factory=HttpModelClient)

    def resolve(self, step: str, *, nature: StepNature | None = None) -> Tier:
        """Return the tier for *step* (delegates to :func:`resolve_tier`)."""
        return resolve_tier(step, nature=nature)

    def ensure_model_loaded(self) -> None:
        """Probe ``/v1/models`` and raise if the configured model is absent.

        * An unreachable server is :class:`ModelUnavailableError`.
        * A readable list that omits the configured model is
          :class:`ModelNotLoadedError`.
        * A server that exposes no ``/v1/models`` (HTTP 404) or returns an
          unreadable body cannot be checked here; the completion call still fails
          loudly, so the probe steps aside rather than inventing a failure.
        """
        request = urllib.request.Request(models_endpoint(self.client.endpoint), method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self.client.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return
            raise ModelUnavailableError(f"cannot reach {self.client.endpoint!r}: {exc}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ModelUnavailableError(f"cannot reach {self.client.endpoint!r}: {exc}") from exc
        loaded = _parse_model_ids(raw)
        if loaded is not None and self.client.model not in loaded:
            raise ModelNotLoadedError(f"model {self.client.model!r} is not loaded at {self.client.endpoint!r}; loaded: {sorted(loaded)}")

    def complete(self, step: str, messages: Sequence[dict[str, str]], *, nature: StepNature | None = None) -> str:
        """Route *step*, confirm the model is loaded, and return the reply text.

        T0 retrieval never calls a model, so routing a T0 step here is a
        :class:`TierPolicyError` -- a programming error, not a silent no-op. A
        provider failure propagates from the reused client unchanged.
        """
        tier = resolve_tier(step, nature=nature)
        if not tier.uses_model:
            raise TierPolicyError(f"step {step!r} routes to {tier.label} retrieval, which never calls a model")
        self.ensure_model_loaded()
        return self.client(list(messages))
