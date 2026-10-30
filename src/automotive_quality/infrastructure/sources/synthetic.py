from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

MODELS = ["Model-X", "Model-Y", "Model-S", "Model-C"]
OTA_VERSIONS = ["5.9.3", "6.0.0", "6.1.2", "6.2.1", "6.2.2"]
TEAMS = ["Infotainment", "Powertrain", "Charging", "ADAS", "Field Service"]
CENTERS = [f"SC-{i:03d}" for i in range(1, 21)]

CASE_LIBRARY = {
    "OTA_FAILURE": [
        ("OTA upgrade failed at verification stage", "OTA_E201", "Re-download package and verify checksum"),
        ("Vehicle repeatedly retries software update", "OTA_E208", "Clear update cache and retry on stable network"),
    ],
    "INFOTAINMENT": [
        ("Central display intermittently black after OTA", "IVI_E104", "Reflash IVI firmware and reset initialization state"),
        ("Audio and navigation freeze after startup", "IVI_E117", "Apply IVI hotfix and cold reboot head unit"),
    ],
    "CHARGING": [
        ("DC fast charging stops before target state of charge", "BMS_E310", "Calibrate BMS and inspect charge-port temperature sensor"),
        ("AC charger is connected but session does not start", "OBC_E044", "Inspect pilot signal and update OBC firmware"),
    ],
    "HVAC": [
        ("Cabin does not cool in automatic mode", "HVAC_E052", "Recalibrate blend-door actuator"),
        ("Heat pump makes noise at low temperature", "HVAC_E071", "Inspect compressor mounts and apply controller update"),
    ],
    "SENSOR": [
        ("Parking sensor reports obstacle with clear path", "ADAS_E088", "Clean and recalibrate ultrasonic sensors"),
        ("Lane camera unavailable after windshield replacement", "ADAS_E121", "Perform static and dynamic camera calibration"),
    ],
}


@dataclass(frozen=True)
class WorkOrderDataset:
    work_orders: pd.DataFrame
    vehicles: pd.DataFrame
    ota_releases: pd.DataFrame
    diagnostic_events: pd.DataFrame
    injected_defect_rows: set[int]


def generate_dataset(rows: int = 30_000, seed: int = 42, defect_rate: float = 0.04) -> WorkOrderDataset:
    """Create relational, reproducible data and inject traceable defects."""
    if rows < 100:
        raise ValueError("rows must be at least 100")
    rng = np.random.default_rng(seed)
    vehicle_count = max(500, rows // 3)
    vehicles = pd.DataFrame({
        "vehicle_id": [f"VIN{i:08d}" for i in range(vehicle_count)],
        "vehicle_model": rng.choice(MODELS, vehicle_count, p=[0.34, 0.28, 0.22, 0.16]),
        "production_year": rng.integers(2019, 2027, vehicle_count),
        "hardware_version": rng.choice(["HW2.0", "HW2.5", "HW3.0"], vehicle_count),
        "software_version": rng.choice(["2025.12", "2025.24", "2026.4", "2026.8"], vehicle_count),
        "ota_version": rng.choice(OTA_VERSIONS, vehicle_count),
        "region": rng.choice(["East", "North", "South", "West"], vehicle_count),
    })
    categories = np.array(list(CASE_LIBRARY))
    selected_categories = rng.choice(categories, rows, p=[0.18, 0.27, 0.22, 0.14, 0.19])
    created = pd.Timestamp("2025-01-01") + pd.to_timedelta(rng.integers(0, 540 * 24, rows), unit="h")
    priority = rng.choice(["P0", "P1", "P2", "P3"], rows, p=[0.03, 0.17, 0.53, 0.27])
    status = rng.choice(["OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED"], rows, p=[0.08, 0.12, 0.48, 0.32])
    vehicle_idx = rng.integers(0, vehicle_count, rows)
    descriptions, codes, resolutions = [], [], []
    for category in selected_categories:
        case = CASE_LIBRARY[category][int(rng.integers(0, len(CASE_LIBRARY[category])))]
        descriptions.append(case[0])
        codes.append(case[1])
        resolutions.append(case[2])
    base_hours = np.select(
        [priority == "P0", priority == "P1", priority == "P2"], [6, 18, 40], default=72
    )
    category_multiplier = pd.Series(selected_categories).map({
        "OTA_FAILURE": 1.55, "INFOTAINMENT": 1.30, "CHARGING": 1.12, "HVAC": 0.82, "SENSOR": 0.72,
    }).to_numpy()
    vehicle_models = vehicles.iloc[vehicle_idx]["vehicle_model"].to_numpy()
    model_multiplier = pd.Series(vehicle_models).map({
        "Model-X": 1.18, "Model-Y": 1.05, "Model-S": 0.92, "Model-C": 0.80,
    }).to_numpy()
    actual_hours = np.maximum(
        1, rng.lognormal(np.log(base_hours * category_multiplier * model_multiplier), 0.42)
    ).round(1)
    is_resolved = np.isin(status, ["RESOLVED", "CLOSED"])
    resolved_at = pd.Series(created + pd.to_timedelta(actual_hours, unit="h")).where(is_resolved)
    work_orders = pd.DataFrame({
        "work_order_id": [f"WO-{i:07d}" for i in range(rows)],
        "vehicle_id": vehicles.iloc[vehicle_idx]["vehicle_id"].to_numpy(),
        "service_type": np.where(np.isin(selected_categories, ["OTA_FAILURE", "INFOTAINMENT"]), "OTA", "AFTER_SALES"),
        "category": selected_categories,
        "priority": priority,
        "status": status,
        "description": descriptions,
        "error_code": codes,
        "created_at": created,
        "resolved_at": resolved_at,
        "assigned_team": [TEAMS[list(categories).index(c)] for c in selected_categories],
        "service_center_id": rng.choice(CENTERS, rows),
        "resolution": pd.Series(resolutions).where(is_resolved),
        "sla_hours": base_hours,
        "resolution_hours": pd.Series(actual_hours).where(is_resolved),
        "sla_breach": ((actual_hours > base_hours) & is_resolved).astype(int),
    })
    work_orders["_injected_defect"] = False
    work_orders["_injected_duplicate"] = False
    defect_rows: set[int] = set()
    defect_count = 0 if defect_rate <= 0 else max(5, int(rows * defect_rate))
    chunks = np.array_split(rng.choice(rows, defect_count, replace=False), 5)
    for indices in chunks:
        defect_rows.update(int(i) for i in indices)
    if defect_count:
        work_orders.loc[list(defect_rows), "_injected_defect"] = True
        work_orders.loc[chunks[0], "vehicle_id"] = None
        work_orders.loc[chunks[1], "status"] = "INVALID"
        work_orders.loc[chunks[2], "priority"] = "URGENT"
        chronology_rows = chunks[3].tolist()
        for row_index in chronology_rows:
            created_at_value = pd.Timestamp(work_orders.at[int(row_index), "created_at"])
            work_orders.at[int(row_index), "resolved_at"] = created_at_value - pd.Timedelta(hours=2)
        source_rows = chunks[4]
        safe_targets = np.setdiff1d(np.arange(rows), np.fromiter(defect_rows, dtype=int))
        duplicate_targets = rng.choice(safe_targets, len(source_rows), replace=False)
        work_orders.loc[source_rows, "work_order_id"] = work_orders.loc[duplicate_targets, "work_order_id"].to_numpy()
        work_orders.loc[source_rows, "_injected_duplicate"] = True

    # A controlled benchmark must make the known injected duplicate the row
    # rejected by keep="first", independent of its original random position.
    work_orders = work_orders.sort_values(["work_order_id", "_injected_duplicate"], kind="stable").reset_index(drop=True)
    defect_rows = set(work_orders.index[work_orders.pop("_injected_defect")].tolist())
    work_orders.pop("_injected_duplicate")

    ota_releases = pd.DataFrame({
        "ota_version": OTA_VERSIONS,
        "release_date": pd.date_range("2025-02-01", periods=len(OTA_VERSIONS), freq="90D"),
        "release_notes": ["Stability and compatibility improvements"] * len(OTA_VERSIONS),
        "known_issue": [None, None, "OBC session retry", "IVI black screen on HW2.0", None],
    })
    diagnostic_events = work_orders[["work_order_id", "vehicle_id", "error_code", "created_at"]].copy()
    diagnostic_events.insert(0, "event_id", [f"EV-{i:08d}" for i in range(rows)])
    return WorkOrderDataset(work_orders, vehicles, ota_releases, diagnostic_events, defect_rows)


def write_raw_data(data: WorkOrderDataset, output_dir: str | Path) -> None:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    for name in ("work_orders", "vehicles", "ota_releases", "diagnostic_events"):
        getattr(data, name).to_csv(path / f"{name}.csv", index=False)
