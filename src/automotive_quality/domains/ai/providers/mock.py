from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class MockProvider:
    name = "mock"
    model = "deterministic-fixture"

    def __init__(self, responses: dict[type[BaseModel], dict[str, Any] | BaseModel]) -> None:
        self.responses = responses

    def generate_structured(self, *, prompt: str, response_model: type[T]) -> T:
        del prompt
        if response_model not in self.responses:
            raise ValueError(f"No mock response configured for {response_model.__name__}")
        value = self.responses[response_model]
        return value if isinstance(value, response_model) else response_model.model_validate(value)

