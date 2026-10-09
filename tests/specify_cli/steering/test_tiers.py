"""Local-execution-tier tests (WP06 / T025, FR-006, NFR-006, C-004, SC-004).

Pins the two defects the tier layer exists to prevent:

* a step routed to the wrong tier -- in particular T0 retrieval (deterministic,
  always local) silently escalating to a model call, or an unknown step being
  silently downgraded;
* a provider quirk swallowed into an empty string -- an unreachable server, an
  unloaded model, or an empty/malformed completion must raise loudly.

The provider is exercised through its HTTP seam (``urllib.request.urlopen`` is
monkeypatched), so no live model or network is involved.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from specify_cli.steering.driver import (
    DEFAULT_ENDPOINT,
    DEFAULT_MODEL,
    STEER_MODEL_EMPTY,
    STEER_MODEL_UNAVAILABLE,
    EmptyModelResponseError,
    HttpModelClient,
    ModelUnavailableError,
)
from specify_cli.steering.tiers import (
    DEFAULT_TIER,
    NATURE_TIERS,
    STEP_NATURES,
    STEER_MODEL_NOT_LOADED,
    STEER_TIER_NO_MODEL,
    LocalProvider,
    ModelNotLoadedError,
    StepNature,
    Tier,
    TierPolicyError,
    models_endpoint,
    policy_table,
    resolve_tier,
)

# ---------------------------------------------------------------------------
# Test doubles -- a URL-dispatching stand-in for the local server
# ---------------------------------------------------------------------------


class _FakeResponse:
    """A minimal ``urlopen`` context manager over a fixed payload."""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def read(self) -> bytes:
        return self._payload


def _models_payload(*ids: str) -> bytes:
    return json.dumps({"object": "list", "data": [{"id": model_id} for model_id in ids]}).encode("utf-8")


def _chat_payload(content: str) -> bytes:
    return json.dumps({"choices": [{"message": {"content": content}}]}).encode("utf-8")


def _route(monkeypatch: pytest.MonkeyPatch, routes: dict[str, bytes], *, error: Exception | None = None) -> None:
    """Point ``urlopen`` at *routes* (URL substring -> payload), or raise *error*."""

    def fake_urlopen(request: object, timeout: float | None = None) -> _FakeResponse:
        if error is not None:
            raise error
        url = getattr(request, "full_url", str(request))
        for needle, payload in routes.items():
            if needle in url:
                return _FakeResponse(payload)
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)


# ---------------------------------------------------------------------------
# T023 -- the tier policy is deterministic and inspectable
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("step", "tier"),
    [
        ("retrieve", Tier.T0_RETRIEVAL),
        ("fetch", Tier.T0_RETRIEVAL),
        ("capsule", Tier.T0_RETRIEVAL),
        ("next", Tier.T1_ROUTING),
        ("route", Tier.T1_ROUTING),
        ("specify", Tier.T2_DRAFTING),
        ("plan", Tier.T2_DRAFTING),
        ("tasks", Tier.T2_DRAFTING),
        ("implement", Tier.T3_FULL_LOOP),
        ("review", Tier.T3_FULL_LOOP),
    ],
)
def test_resolve_tier_maps_representative_steps(step: str, tier: Tier) -> None:
    assert resolve_tier(step) is tier


def test_resolve_tier_is_deterministic() -> None:
    assert resolve_tier("implement") == resolve_tier("implement")


def test_resolve_tier_uses_the_base_before_a_reason_suffix() -> None:
    assert resolve_tier("implement:rework") is Tier.T3_FULL_LOOP


def test_resolve_tier_ignores_case_and_surrounding_space() -> None:
    assert resolve_tier("  Implement ") is Tier.T3_FULL_LOOP


def test_resolve_tier_falls_back_to_the_full_loop_for_an_unknown_step() -> None:
    assert resolve_tier("unknown-step") is DEFAULT_TIER is Tier.T3_FULL_LOOP


def test_an_explicit_nature_overrides_the_step_table() -> None:
    assert resolve_tier("implement", nature=StepNature.RETRIEVAL) is Tier.T0_RETRIEVAL


def test_an_explicit_nature_routes_a_step_the_table_does_not_know() -> None:
    assert resolve_tier("brand-new-step", nature=StepNature.DRAFTING) is Tier.T2_DRAFTING


def test_t0_is_the_only_tier_that_never_calls_a_model() -> None:
    assert Tier.T0_RETRIEVAL.uses_model is False
    assert all(tier.uses_model for tier in Tier if tier is not Tier.T0_RETRIEVAL)


def test_tier_order_escalates_from_retrieval_to_full_loop() -> None:
    assert Tier.T0_RETRIEVAL < Tier.T1_ROUTING < Tier.T2_DRAFTING < Tier.T3_FULL_LOOP


def test_tier_labels_are_stable() -> None:
    assert [tier.label for tier in Tier] == ["T0", "T1", "T2", "T3"]


def test_every_nature_has_a_tier() -> None:
    assert set(NATURE_TIERS) == set(StepNature)


def test_policy_table_covers_every_step_and_matches_resolve_tier() -> None:
    table = policy_table()
    assert set(table) == set(STEP_NATURES)
    for step, entry in table.items():
        assert entry["tier"] == resolve_tier(step).label
        assert entry["nature"] == STEP_NATURES[step].value


# ---------------------------------------------------------------------------
# T024 -- the local provider adapter fails loudly
# ---------------------------------------------------------------------------


def test_models_endpoint_is_derived_from_the_chat_endpoint() -> None:
    assert models_endpoint("http://127.0.0.1:8888/v1/chat/completions") == "http://127.0.0.1:8888/v1/models"


def test_models_endpoint_falls_back_to_the_host_root() -> None:
    assert models_endpoint("http://127.0.0.1:8888") == "http://127.0.0.1:8888/v1/models"


def test_provider_defaults_to_the_driver_client_defaults() -> None:
    provider = LocalProvider()
    assert provider.client.endpoint == DEFAULT_ENDPOINT
    assert provider.client.model == DEFAULT_MODEL


def test_provider_resolve_delegates_to_the_policy() -> None:
    provider = LocalProvider()
    assert provider.resolve("review") is Tier.T3_FULL_LOOP
    assert provider.resolve("whatever", nature=StepNature.ROUTING) is Tier.T1_ROUTING


def test_complete_returns_the_reply_text(monkeypatch: pytest.MonkeyPatch) -> None:
    _route(
        monkeypatch,
        {"/v1/models": _models_payload(DEFAULT_MODEL), "/v1/chat/completions": _chat_payload('{"tool": "finish", "args": {}}')},
    )
    provider = LocalProvider()
    assert provider.complete("implement", [{"role": "user", "content": "hi"}]) == '{"tool": "finish", "args": {}}'


def test_complete_rejects_a_t0_step_without_calling_a_model(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(request: object, timeout: float | None = None) -> object:
        raise AssertionError("a T0 step must not touch the network")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    provider = LocalProvider()

    with pytest.raises(TierPolicyError, match=STEER_TIER_NO_MODEL):
        provider.complete("retrieve", [{"role": "user", "content": "hi"}])


def test_complete_reports_an_unreachable_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    _route(monkeypatch, {}, error=urllib.error.URLError("connection refused"))
    provider = LocalProvider(client=HttpModelClient(endpoint="http://127.0.0.1:1/v1/chat/completions"))

    with pytest.raises(ModelUnavailableError, match=STEER_MODEL_UNAVAILABLE):
        provider.complete("implement", [{"role": "user", "content": "hi"}])


def test_complete_reports_an_unloaded_model(monkeypatch: pytest.MonkeyPatch) -> None:
    # Only /v1/models is routed: reaching the completion endpoint would fail the test.
    _route(monkeypatch, {"/v1/models": _models_payload("some-other-model")})
    provider = LocalProvider(client=HttpModelClient(model=DEFAULT_MODEL))

    with pytest.raises(ModelNotLoadedError, match=STEER_MODEL_NOT_LOADED):
        provider.complete("implement", [{"role": "user", "content": "hi"}])


def test_complete_rejects_an_empty_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    _route(monkeypatch, {"/v1/models": _models_payload(DEFAULT_MODEL), "/v1/chat/completions": _chat_payload("   ")})
    provider = LocalProvider()

    with pytest.raises(EmptyModelResponseError, match=STEER_MODEL_EMPTY):
        provider.complete("implement", [{"role": "user", "content": "hi"}])


def test_complete_rejects_a_malformed_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    _route(monkeypatch, {"/v1/models": _models_payload(DEFAULT_MODEL), "/v1/chat/completions": json.dumps({"unexpected": True}).encode("utf-8")})
    provider = LocalProvider()

    with pytest.raises(EmptyModelResponseError, match=STEER_MODEL_EMPTY):
        provider.complete("implement", [{"role": "user", "content": "hi"}])


def test_ensure_model_loaded_passes_when_the_model_is_listed(monkeypatch: pytest.MonkeyPatch) -> None:
    _route(monkeypatch, {"/v1/models": _models_payload(DEFAULT_MODEL)})
    LocalProvider().ensure_model_loaded()  # a listed model raises nothing


def test_ensure_model_loaded_steps_aside_when_the_endpoint_has_no_models_route(monkeypatch: pytest.MonkeyPatch) -> None:
    _route(monkeypatch, {}, error=urllib.error.HTTPError("http://model/v1/models", 404, "not found", {}, None))
    LocalProvider().ensure_model_loaded()  # a missing /v1/models is not an unloaded model


def test_ensure_model_loaded_steps_aside_when_the_body_is_unreadable(monkeypatch: pytest.MonkeyPatch) -> None:
    _route(monkeypatch, {"/v1/models": b"not json"})
    LocalProvider().ensure_model_loaded()  # an unreadable list is not evidence of an unloaded model
