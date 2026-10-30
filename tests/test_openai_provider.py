from __future__ import annotations

import sys
from types import SimpleNamespace

import httpx
import pytest
from pydantic import BaseModel, model_validator

from automotive_quality.domains.ai.providers.openai import OpenAIProvider


class ExampleOutput(BaseModel):
    value: str


class ValidatedExampleOutput(BaseModel):
    value: str
    valid: bool

    @model_validator(mode="after")
    def require_valid(self):
        if not self.valid:
            raise ValueError("valid must be true")
        return self


def test_openai_provider_configures_resilient_request_defaults(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_openai(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=fake_openai))

    provider = OpenAIProvider("test-model", api_key="test-key")

    assert provider.model == "test-model"
    assert captured == {"api_key": "test-key", "max_retries": 5, "timeout": 120.0}


def test_openai_provider_streams_structured_output_to_keep_connection_active() -> None:
    captured: dict[str, object] = {}
    expected = ExampleOutput(value="complete")

    class FakeStream:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get_final_response(self):
            return SimpleNamespace(output_parsed=expected)

    def stream(**kwargs):
        captured.update(kwargs)
        return FakeStream()

    provider = object.__new__(OpenAIProvider)
    provider.model = "test-model"
    provider._stream_read_retries = 0
    provider._client = SimpleNamespace(responses=SimpleNamespace(stream=stream))

    result = provider.generate_structured(prompt="Generate", response_model=ExampleOutput)

    assert result == expected
    assert captured["model"] == "test-model"
    assert captured["text_format"] is ExampleOutput
    assert captured["input"][1] == {"role": "user", "content": "Generate"}


def test_openai_provider_retries_incomplete_stream_reads(monkeypatch) -> None:
    attempts = 0
    expected = ExampleOutput(value="complete")

    class FakeStream:
        def __init__(self, should_fail: bool):
            self.should_fail = should_fail

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get_final_response(self):
            if self.should_fail:
                request = httpx.Request("POST", "https://api.openai.com/v1/responses")
                raise httpx.RemoteProtocolError("incomplete chunked read", request=request)
            return SimpleNamespace(output_parsed=expected)

    def stream(**_kwargs):
        nonlocal attempts
        attempts += 1
        return FakeStream(should_fail=attempts == 1)

    monkeypatch.setattr("automotive_quality.domains.ai.providers.openai.time.sleep", lambda _seconds: None)
    provider = object.__new__(OpenAIProvider)
    provider.model = "test-model"
    provider._stream_read_retries = 1
    provider._client = SimpleNamespace(responses=SimpleNamespace(stream=stream))

    assert provider.generate_structured(prompt="Generate", response_model=ExampleOutput) == expected
    assert attempts == 2


def test_openai_provider_retries_schema_validation_failures_with_feedback(monkeypatch) -> None:
    attempts = 0
    requests: list[dict[str, object]] = []
    expected = ValidatedExampleOutput(value="corrected", valid=True)

    class FakeStream:
        def __init__(self, should_fail: bool):
            self.should_fail = should_fail

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get_final_response(self):
            if self.should_fail:
                ValidatedExampleOutput.model_validate({"value": "invalid", "valid": False})
            return SimpleNamespace(output_parsed=expected)

    def stream(**kwargs):
        nonlocal attempts
        attempts += 1
        requests.append(kwargs)
        return FakeStream(should_fail=attempts == 1)

    monkeypatch.setattr("automotive_quality.domains.ai.providers.openai.time.sleep", lambda _seconds: None)
    provider = object.__new__(OpenAIProvider)
    provider.model = "test-model"
    provider._stream_read_retries = 1
    provider._client = SimpleNamespace(responses=SimpleNamespace(stream=stream))

    assert provider.generate_structured(prompt="Generate", response_model=ValidatedExampleOutput) == expected
    assert attempts == 2
    assert len(requests[0]["input"]) == 2
    assert len(requests[1]["input"]) == 3
    assert "failed schema validation" in requests[1]["input"][2]["content"]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"max_retries": -1}, "max_retries"),
        ({"timeout_seconds": 0}, "timeout_seconds"),
    ],
)
def test_openai_provider_rejects_invalid_resilience_settings(kwargs, message) -> None:
    with pytest.raises(ValueError, match=message):
        OpenAIProvider("test-model", **kwargs)
