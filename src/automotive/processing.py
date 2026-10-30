from __future__ import annotations

import pandas as pd


def clean_work_orders(df: pd.DataFrame) -> pd.DataFrame:
    clean = df.copy()
    clean["created_at"] = pd.to_datetime(clean["created_at"], errors="coerce", utc=True)
    clean["resolved_at"] = pd.to_datetime(clean["resolved_at"], errors="coerce", utc=True)
    for col in ["status", "priority", "category", "service_type"]:
        clean[col] = clean[col].astype("string").str.strip().str.upper()
    clean = clean.drop_duplicates("work_order_id", keep="first")
    return clean.reset_index(drop=True)


def add_features(work_orders: pd.DataFrame, vehicles: pd.DataFrame) -> pd.DataFrame:
    frame = work_orders.merge(vehicles, on="vehicle_id", how="left", validate="many_to_one")
    reference_year = pd.to_datetime(frame["created_at"], utc=True).dt.year
    frame["vehicle_age"] = (reference_year - frame["production_year"]).clip(lower=0)
    frame["historical_issue_count"] = frame.groupby("vehicle_id").cumcount()
    frame["same_version_issue_count"] = frame.groupby("ota_version")["work_order_id"].transform("count")
    frame["service_center_load"] = frame.groupby(["service_center_id", frame["created_at"].dt.date])["work_order_id"].transform("count")
    frame["description_length"] = frame["description"].str.len()
    return frame


def build_marts(features: pd.DataFrame) -> dict[str, pd.DataFrame]:
    closed = features[features["resolved_at"].notna()].copy()
    daily = features.assign(date=features["created_at"].dt.date).groupby("date", as_index=False).agg(
        total_work_orders=("work_order_id", "count"),
        open_backlog=("status", lambda s: int(s.isin(["OPEN", "IN_PROGRESS"]).sum())),
        sla_breach_rate=("sla_breach", "mean"),
    )
    ota = features.groupby("ota_version", dropna=False, as_index=False).agg(
        total_issues=("work_order_id", "count"),
        sla_breach_rate=("sla_breach", "mean"),
        avg_resolution_hours=("resolution_hours", "mean"),
    )
    models = features.groupby(["vehicle_model", "category"], as_index=False).agg(
        issue_count=("work_order_id", "count"),
        sla_breach_rate=("sla_breach", "mean"),
        avg_resolution_hours=("resolution_hours", "mean"),
    )
    teams = closed.groupby("assigned_team", as_index=False).agg(
        resolved_orders=("work_order_id", "count"),
        avg_resolution_hours=("resolution_hours", "mean"),
        sla_breach_rate=("sla_breach", "mean"),
    )
    return {
        "daily_work_order_metrics": daily,
        "ota_issue_summary": ota,
        "vehicle_model_issue_summary": models,
        "team_resolution_performance": teams,
    }
