"""LLM invocation: recorded parameters, thinking-mode control, error mapping."""

from __future__ import annotations

import json
from copy import deepcopy

import httpx
import pytest

from hedge_fund.agents import llm
from hedge_fund.agents.llm import LLMUnavailable, call_json, prompt_hash, sampling_params
from hedge_fund.settings import settings


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or json.dumps(self._payload)

    def json(self):
        return self._payload


class FakeClient:
    """Captures every request body so tests can assert on what was sent."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.requests: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None):
        # Snapshot the body: real httpx serializes at call time, so a retry that
        # mutates the payload must not rewrite what we recorded for attempt one.
        self.requests.append(deepcopy(json))
        return self._responses.pop(0)


def _ok_response(content='{"stance": "HOLD"}'):
    return FakeResponse(payload={"message": {"content": content}, "eval_count": 12})


@pytest.fixture
def ollama(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "ollama_model", "qwen3:30b")

    def install(responses):
        client = FakeClient(responses)
        monkeypatch.setattr(llm.httpx, "AsyncClient", lambda **kw: client)
        return client

    return install


# ----------------------------------------------------------------------
# Prompt identity
# ----------------------------------------------------------------------


def test_prompt_hash_is_stable():
    assert prompt_hash("sys", "user") == prompt_hash("sys", "user")


def test_prompt_hash_separates_the_two_halves():
    """Concatenation must not collide: ("ab","") is a different prompt to ("a","b")."""
    assert prompt_hash("ab", "") != prompt_hash("a", "b")


# ----------------------------------------------------------------------
# Sampling parameters
# ----------------------------------------------------------------------


def test_sampling_defaults_are_greedy_and_seeded():
    params = sampling_params()
    assert params["temperature"] == 0.0
    assert params["seed"] == 7


def test_think_is_recorded_on_the_run(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "ollama_think", False)
    assert sampling_params()["think"] is False


def test_think_is_omitted_when_unset(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "ollama_think", None)
    assert "think" not in sampling_params()


def test_think_is_not_recorded_for_openai(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "ollama_think", False)
    assert "think" not in sampling_params()


# ----------------------------------------------------------------------
# Request shape
# ----------------------------------------------------------------------


async def test_thinking_is_disabled_by_default(ollama, monkeypatch):
    """Reasoning traces cost budget without improving schema-constrained output."""
    monkeypatch.setattr(settings, "ollama_think", False)
    client = ollama([_ok_response()])

    await call_json("sys", "user")
    assert client.requests[0]["think"] is False


async def test_think_key_is_absent_when_unset(ollama, monkeypatch):
    monkeypatch.setattr(settings, "ollama_think", None)
    client = ollama([_ok_response()])

    await call_json("sys", "user")
    assert "think" not in client.requests[0]


async def test_sampling_options_are_sent(ollama, monkeypatch):
    monkeypatch.setattr(settings, "ollama_think", None)
    client = ollama([_ok_response()])

    await call_json("sys", "user")
    options = client.requests[0]["options"]
    assert options["temperature"] == 0.0
    assert options["seed"] == 7
    assert client.requests[0]["format"] == "json"


async def test_unsupported_think_key_is_dropped_and_retried(ollama, monkeypatch):
    """A model without a thinking mode must not fail over an unsupported option."""
    monkeypatch.setattr(settings, "ollama_think", False)
    client = ollama(
        [
            FakeResponse(status_code=400, text='{"error":"model does not support think"}'),
            _ok_response(),
        ]
    )

    result = await call_json("sys", "user")
    assert len(client.requests) == 2
    assert "think" in client.requests[0]
    assert "think" not in client.requests[1]
    assert result.content == '{"stance": "HOLD"}'


async def test_other_400s_are_not_retried(ollama, monkeypatch):
    monkeypatch.setattr(settings, "ollama_think", False)
    client = ollama([FakeResponse(status_code=400, text='{"error":"model not found"}')])

    with pytest.raises(RuntimeError, match="Ollama HTTP 400"):
        await call_json("sys", "user")
    assert len(client.requests) == 1


# ----------------------------------------------------------------------
# Result and errors
# ----------------------------------------------------------------------


async def test_result_records_everything_needed_to_replay(ollama, monkeypatch):
    monkeypatch.setattr(settings, "ollama_think", False)
    ollama([_ok_response()])

    result = await call_json("sys", "user")
    assert result.model == "ollama:qwen3:30b"
    assert result.prompt_sha256 == prompt_hash("sys", "user")
    assert result.params["seed"] == 7
    assert result.latency_ms is not None

    record = result.as_record()
    assert record["model"] and record["prompt_sha256"] and record["params"]


async def test_unreachable_daemon_raises_llm_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")

    class Dead:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None):
            raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(llm.httpx, "AsyncClient", lambda **kw: Dead())

    with pytest.raises(LLMUnavailable, match="Cannot reach Ollama"):
        await call_json("sys", "user")
