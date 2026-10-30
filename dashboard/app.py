from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
ROOT = Path(__file__).resolve().parents[1]


def api(path: str, method: str = "GET", payload: dict[str, object] | None = None) -> object:
    body = json.dumps(payload).encode() if payload is not None else None
    request = Request(f"{API_BASE_URL}{path}", data=body, method=method, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=15) as response:
        return json.loads(response.read())


def published_ai_value_evidence() -> list[dict[str, object]]:
    reports = []
    for filename in ("test_generation_report.json", "rca_report.json"):
        path = ROOT / "artifacts/ai_value" / filename
        if not path.exists():
            continue
        summary = json.loads(path.read_text(encoding="utf-8"))
        experiment = summary["experiment"]
        reports.append({
            "experiment_id": experiment["experiment_id"], "experiment": experiment["experiment"],
            "provider": experiment["provider"], "model": experiment["model"],
            "dataset_version": experiment["dataset_version"], "summary": summary,
        })
    return reports


st.set_page_config(page_title="Automotive Quality Platform", page_icon="🚗", layout="wide")
st.title("Automotive Quality Platform")
st.caption("FastAPI-backed quality, testing, retrieval, and AI workflows")

try:
    metrics = api("/api/v1/metrics/overview")
except (HTTPError, URLError, TimeoutError) as exc:
    st.error(f"Platform API unavailable at {API_BASE_URL}: {exc}")
    st.stop()

cols = st.columns(3)
for col, label, key in zip(cols, ["Work orders", "Open backlog", "OTA work orders"], ["total_work_orders", "open_backlog", "ota_work_orders"]):
    col.metric(label, f"{metrics[key]:,}")

overview, runs, retrieval, ai_value = st.tabs(["Quality overview", "Test runs", "Case retrieval", "AI Value"])
with overview:
    st.json(metrics)
with runs:
    st.dataframe(pd.DataFrame(api("/api/v1/test-runs")), width="stretch")
with retrieval:
    dataset_version = st.text_input("Dataset version", "local-v1")
    description = st.text_area("Issue description", "Central display intermittently black after OTA")
    error_code = st.text_input("Error code", "IVI_E104")
    ota_version = st.text_input("OTA version", "6.2.1")
    if st.button("Retrieve authoritative evidence", type="primary"):
        payload = {"dataset_version": dataset_version, "vehicle_model": "Model-X", "description": description, "error_code": error_code, "ota_version": ota_version}
        try:
            matches = api("/api/v1/retrieval/search?top_k=5", "POST", payload)
            st.dataframe(pd.DataFrame(matches), width="stretch")
        except HTTPError as exc:
            st.error(exc.read().decode())
with ai_value:
    st.subheader("Measured AI value")
    st.caption("Publishable means the evidence is complete. Policy status determines whether the evaluated configuration is approved.")
    experiments = api("/api/v1/ai-value/experiments")
    if not experiments:
        experiments = published_ai_value_evidence()
        if experiments:
            st.info("Showing the committed, sanitized real-provider evidence artifacts. Runtime persistence is currently empty.")
        else:
            st.info("No persisted real-provider benchmark exists. Mock runs are regression-only and must not be presented as AI value.")
    publishable_experiments = [
        experiment for experiment in experiments
        if (experiment.get("summary") or {}).get("experiment", {}).get("publishable")
    ]
    if publishable_experiments:
        st.markdown("#### Current policy decisions")
        decision_columns = st.columns(len(publishable_experiments))
        for column, experiment in zip(decision_columns, publishable_experiments):
            summary = experiment.get("summary") or {}
            status = summary.get("quality_gates", {}).get("status", "UNKNOWN")
            with column:
                if status == "PASS":
                    st.success(f"{experiment['experiment'].upper()} — PASS")
                else:
                    st.error(f"{experiment['experiment'].upper()} — {status}")
                st.caption("Publishable evidence; autonomous promotion remains blocked." if status != "PASS" else "Publishable evidence; policy thresholds passed.")
    for experiment in experiments:
        st.markdown(f"### {experiment['experiment_id']} — {experiment['experiment']}")
        st.caption(f"Provider: {experiment['provider']} · Model: {experiment['model']} · Dataset: {experiment['dataset_version']}")
        summary = experiment.get("summary") or {}
        if summary.get("experiment", {}).get("publishable"):
            gate_status = summary.get("quality_gates", {}).get("status", "UNKNOWN")
            if gate_status == "PASS":
                st.success(f"{experiment['experiment'].upper()} POLICY — PASS")
            else:
                st.error(f"{experiment['experiment'].upper()} POLICY — {gate_status}")

            improved, failed = st.columns(2)
            differences = summary.get("difference_ai_minus_baseline", {})
            ai_metrics = summary.get("ai_assisted", {})
            if experiment["experiment"] == "test-generation":
                with improved:
                    st.markdown("#### What AI improved")
                    st.metric("Requirement coverage vs deterministic", f"{ai_metrics['requirement_coverage']['mean']:.1%}", f"{differences['requirement_coverage']:+.1%}")
                    st.metric("Negative coverage", f"{ai_metrics['negative_coverage']['mean']:.1%}", f"{differences['negative_coverage']:+.1%}")
                    st.metric("Human effort saving", f"{summary['efficiency']['human_effort_saving_rate']:.1%}")
                with failed:
                    st.markdown("#### Where AI failed")
                    st.metric("Unsupported assumptions", f"{ai_metrics['unsupported_assumption_rate']['mean']:.1%}", delta_color="inverse")
                    st.metric("Approval rate", f"{ai_metrics['approval_rate']['mean']:.1%}")
                    human_coverage = summary.get("human_only", {}).get("requirement_coverage", {}).get("mean")
                    if human_coverage is not None:
                        st.metric("Human-only coverage", f"{human_coverage:.1%}", f"AI {ai_metrics['requirement_coverage']['mean'] - human_coverage:+.1%}")
            else:
                with improved:
                    st.markdown("#### What AI improved")
                    st.metric("Investigation time", f"{ai_metrics['active_investigation_seconds']['mean']:.1f} s", f"{differences['active_investigation_seconds']:+.1f} s", delta_color="inverse")
                    st.metric("Recommended-check usefulness", f"{ai_metrics['recommended_check_usefulness']['mean']:.1%}")
                    st.metric("Evidence support", f"{ai_metrics['evidence_support_rate']['mean']:.1%}")
                with failed:
                    st.markdown("#### Where AI failed")
                    st.metric("Root-cause accuracy", f"{ai_metrics['root_cause_accuracy']['mean']:.1%}")
                    st.metric("Correct abstention", f"{ai_metrics['correct_abstention']['mean']:.1%}")
                    st.metric("Unsupported claims", f"{ai_metrics['unsupported_claim_rate']['mean']:.1%}", delta_color="inverse")

            st.warning("Decision: AI provides measurable productivity value but is not approved for autonomous use.")
            with st.expander("Detailed metrics and policy evaluations"):
                st.json(summary)
        else:
            st.warning("Not publishable: a real-provider run and required human review are incomplete.")
            with st.expander("Incomplete experiment details"):
                st.json(summary)
