from __future__ import annotations

import time
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class OpenAIProvider:
    """Optional real provider using Responses API Structured Outputs."""

    name = "openai"

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        *,
        max_retries: int = 5,
        timeout_seconds: float = 120.0,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be at least 0")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than 0")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install the 'ai' extra to use OpenAIProvider") from exc
        self.model = model
        self._stream_read_retries = max_retries
        self._client = OpenAI(
            api_key=api_key,
            max_retries=max_retries,
            timeout=timeout_seconds,
        )

    def generate_structured(self, *, prompt: str, response_model: type[T]) -> T:
        base_input = [
            {"role": "developer", "content": "Return only evidence-conscious quality-engineering analysis in the requested schema."},
            {"role": "user", "content": prompt},
        ]
        request = {
            "model": self.model,
            "input": base_input,
            "text_format": response_model,
        }
        validation_feedback: str | None = None
        for attempt in range(self._stream_read_retries + 1):
            try:
                if validation_feedback:
                    request["input"] = [
                        *base_input,
                        {
                            "role": "developer",
                            "content": (
                                "Your previous structured response failed schema validation. "
                                "Return a corrected response that satisfies every invariant. "
                                f"Validation error: {validation_feedback}"
                            ),
                        },
                    ]
                with self._client.responses.stream(**request) as stream:
                    response = stream.get_final_response()
                if response.output_parsed is None:
                    raise ValueError("Model returned no parsed structured output")
                return response.output_parsed
            except ValidationError as exc:
                if attempt >= self._stream_read_retries:
                    raise
                validation_feedback = str(exc)
                time.sleep(min(2**attempt, 8))
            except (httpx.RemoteProtocolError, httpx.ReadTimeout):
                if attempt >= self._stream_read_retries:
                    raise
                time.sleep(min(2**attempt, 8))
        raise AssertionError("unreachable")
