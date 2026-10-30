from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field


class SimilarCase(BaseModel):
    work_order_id: str
    score: float = Field(ge=0, le=1)
    category: str
    description: str
    resolution: str | None = None


class CaseRetriever(Protocol):
    def search(self, query: str, top_k: int = 5) -> list[SimilarCase]: ...
