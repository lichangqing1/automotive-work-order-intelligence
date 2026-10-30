from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from automotive_quality.domains.retrieval.models import SimilarCase


@dataclass
class TfidfRetriever:
    cases: pd.DataFrame
    vectorizer: TfidfVectorizer
    matrix: object

    @classmethod
    def build(cls, work_orders: pd.DataFrame) -> TfidfRetriever:
        cases = work_orders[work_orders["resolution"].notna()].copy().reset_index(drop=True)
        cases["search_text"] = (
            cases["error_code"].fillna("") + " " + cases["description"].fillna("")
        )
        vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True)
        matrix = vectorizer.fit_transform(cases["search_text"])
        return cls(cases, vectorizer, matrix)

    def search(self, query: str, top_k: int = 5, exclude_id: str | None = None, min_score: float = 0.0) -> list[SimilarCase]:
        scores = cosine_similarity(self.vectorizer.transform([query]), self.matrix).ravel()
        order = np.argsort(-scores)
        results: list[SimilarCase] = []
        for idx in order:
            row = self.cases.iloc[int(idx)]
            if exclude_id and row["work_order_id"] == exclude_id:
                continue
            if scores[idx] < min_score:
                continue
            results.append(SimilarCase(
                work_order_id=str(row["work_order_id"]), score=float(np.clip(scores[idx], 0, 1)),
                category=str(row["category"]), description=str(row["description"]),
                resolution=str(row["resolution"]),
            ))
            if len(results) == top_k:
                break
        return results


def evaluate_retrieval(index: CaseIndex, sample_size: int = 100, top_k: int = 5, seed: int = 42) -> dict[str, float]:
    sample = index.cases.sample(min(sample_size, len(index.cases)), random_state=seed)
    hits, reciprocal_ranks, recalls, precisions = [], [], [], []
    for _, row in sample.iterrows():
        query = f"{row['error_code']} {row['description']}"
        results = index.search(query, top_k=top_k, exclude_id=str(row["work_order_id"]))
        relevant_ids = set(index.cases.loc[
            (index.cases["error_code"] == row["error_code"]) & (index.cases["work_order_id"] != row["work_order_id"]),
            "work_order_id",
        ].astype(str))
        relevant = [result.work_order_id in relevant_ids for result in results]
        hits.append(float(any(relevant)))
        retrieved_relevant = sum(relevant)
        recalls.append(retrieved_relevant / len(relevant_ids) if relevant_ids else 0.0)
        precisions.append(retrieved_relevant / len(results) if results else 0.0)
        reciprocal_ranks.append(next((1 / (i + 1) for i, hit in enumerate(relevant) if hit), 0.0))
    return {
        f"hit_rate_at_{top_k}": float(np.mean(hits)),
        f"recall_at_{top_k}": float(np.mean(recalls)),
        f"precision_at_{top_k}": float(np.mean(precisions)),
        "mrr": float(np.mean(reciprocal_ranks)),
    }


# Compatibility name for historical benchmark imports.
CaseIndex = TfidfRetriever
