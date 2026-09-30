from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from vulnerability_engine import (
    RAINFALL_PATH,
    TRACK_JSON_PATH,
    _load_dem,
    align_to_reference,
    load_track,
    rainfall_flood_risk,
    rainfall_slope_combined_risk,
    slope_landslide_risk,
    surge_risk_from_track,
)

FEATURE_COLUMNS = [
    "elevation_m",
    "rainfall_mm",
    "slope_deg",
    "surge_risk",
    "coastal_flag",
]


def build_feature_table(
    track_path: str | Path | None = None,
    sample_step: int = 30,
    include_label: bool = True,
) -> pd.DataFrame:
    """Build a tabular feature matrix for model training.

    This module is intentionally data-driven and keeps all feature generation in
    one place. It can consume the repo's real rasters and track files, and it can
    also be swapped to a real externally labeled dataset once one is available.
    """
    dem, transform, crs = _load_dem()
    track_df = load_track(track_path or TRACK_JSON_PATH)

    surge_risk = surge_risk_from_track(
        dem,
        transform,
        track_df,
        surge_elev_threshold_m=1.0,
        use_holland=True,
    )
    rainfall_aligned = align_to_reference(RAINFALL_PATH, transform, crs, dem.shape)

    lat_center = transform.f + transform.e * dem.shape[0] / 2
    deg_to_m_lon = 111_320 * np.cos(np.radians(lat_center))
    deg_to_m_lat = 111_320
    dx_m = abs(transform.a) * deg_to_m_lon
    dy_m = abs(transform.e) * deg_to_m_lat
    gy, gx = np.gradient(dem, dy_m, dx_m)
    slope_deg = np.degrees(np.arctan(np.sqrt(gx**2 + gy**2))).astype(np.float32)

    rain_risk = rainfall_flood_risk(dem, transform, crs, threshold_mm=200.0)
    slope_risk = slope_landslide_risk(dem, transform, threshold_deg=15.0)
    combined_risk = rainfall_slope_combined_risk(rain_risk, slope_risk)
    coastal_mask = ((dem <= 1.0) & (~np.isnan(dem)))

    rows = np.arange(0, dem.shape[0], sample_step)
    cols = np.arange(0, dem.shape[1], sample_step)
    row_idx, col_idx = np.meshgrid(rows, cols, indexing="ij")

    elevations = dem[row_idx, col_idx]
    rainfall_vals = rainfall_aligned[row_idx, col_idx]
    slope_vals = slope_deg[row_idx, col_idx]
    surge_vals = surge_risk[row_idx, col_idx]
    combined_vals = combined_risk[row_idx, col_idx]
    coastal_vals = coastal_mask[row_idx, col_idx]

    valid = ~np.isnan(elevations) & ~np.isnan(rainfall_vals)
    table = pd.DataFrame(
        {
            "elevation_m": elevations[valid].astype(np.float32),
            "rainfall_mm": rainfall_vals[valid].astype(np.float32),
            "slope_deg": slope_vals[valid].astype(np.float32),
            "surge_risk": surge_vals[valid].astype(np.float32),
            "coastal_flag": coastal_vals[valid].astype(np.int8),
            "combined_risk": combined_vals[valid].astype(np.float32),
        }
    )

    if include_label:
        table["label"] = ((table["combined_risk"] > 0.5) | (table["surge_risk"] > 0.5)).astype(np.int8)

    return table


def load_labeled_dataset(dataset_path: str | Path | None = None) -> pd.DataFrame:
    """Load a real labeled disaster dataset if one exists.

    This function expects a CSV with the feature columns and a binary `label`
    column. If no file is present, it falls back to the project's generated
    heuristic labels so the training API still works in this repo.
    """
    if dataset_path is not None:
        dataset_path = Path(dataset_path)
        if dataset_path.exists():
            df = pd.read_csv(dataset_path)
            required = FEATURE_COLUMNS + ["label"]
            missing = [c for c in required if c not in df.columns]
            if missing:
                raise ValueError(f"Dataset is missing required columns: {missing}")
            return df[required].copy()

    return build_feature_table(include_label=True)


def validate_feature_frame(df: pd.DataFrame) -> None:
    expected = FEATURE_COLUMNS + ["label"]
    missing = [c for c in expected if c not in df.columns]
    if missing:
        raise ValueError(f"Feature frame is missing required columns: {missing}")

    if df.empty:
        raise ValueError("Feature frame is empty.")
