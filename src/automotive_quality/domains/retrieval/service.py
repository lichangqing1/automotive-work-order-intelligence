from __future__ import annotations

import pandas as pd

from automotive_quality.baselines.lexical_retrieval import TfidfRetriever
from automotive_quality.infrastructure.database.case_repository import PostgresCaseRepository

from .models import SimilarCase


class RetrievalIndexNotReady(RuntimeError):
    pass


class RetrievalService:
    def __init__(self, repository: PostgresCaseRepository) -> None:
        self.repository = repository

    def search(self, dataset_version: str, query: str, top_k: int = 5) -> list[SimilarCase]:
        cases = self.repository.list_cases(dataset_version)
        if not cases:
            raise RetrievalIndexNotReady(f"No retrieval cases for dataset version '{dataset_version}'")
        return TfidfRetriever.build(pd.DataFrame(cases)).search(query, top_k=top_k)
