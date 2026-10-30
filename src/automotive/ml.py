from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

CATEGORICAL = ["priority", "category", "service_type", "vehicle_model", "ota_version", "assigned_team"]
NUMERIC = ["vehicle_age", "historical_issue_count", "same_version_issue_count", "service_center_load"]


@dataclass
class ModelArtifact:
    model: Pipeline
    metrics: dict[str, float]
    test_predictions: pd.DataFrame


def train_sla_predictor(features: pd.DataFrame, seed: int = 42, threshold: float = 0.5) -> ModelArtifact:
    data = features[features["resolved_at"].notna()].copy()
    x, y = data[CATEGORICAL + NUMERIC], data["sla_breach"].astype(int)
    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=0.25, random_state=seed, stratify=y
    )
    transformer = ColumnTransformer([
        ("categorical", Pipeline([
            ("impute", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore")),
        ]), CATEGORICAL),
        ("numeric", Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
        ]), NUMERIC),
    ])
    model = Pipeline([("features", transformer), ("classifier", LogisticRegression(max_iter=800, class_weight="balanced"))])
    model.fit(x_train, y_train)
    probability = model.predict_proba(x_test)[:, 1]
    prediction = (probability >= threshold).astype(int)
    metrics = {
        "precision": float(precision_score(y_test, prediction, zero_division=0)),
        "recall": float(recall_score(y_test, prediction, zero_division=0)),
        "f1": float(f1_score(y_test, prediction, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_test, probability)),
    }
    scored = pd.DataFrame({"actual": y_test.to_numpy(), "probability": probability, "prediction": prediction})
    return ModelArtifact(model, metrics, scored)

