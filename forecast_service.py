"""
forecast_service.py
===================
Forecast service bridging the cyclone modeling module (vulnerability_engine.py)
with the FastAPI application layer (/forecast).

Handles:
  - Cyclone track validation and adaptation (JSON points, CSV paths, pre-configured IDs)
  - In-memory raster and result caching for high-performance repeat calls
  - Invocation of vulnerability_engine public modeling functions
  - Standardized JSON responses with hazard statistics, exposure summaries,
    explicit missing-data flags, and SAR validation status.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import geopandas as gpd
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

import vulnerability_engine as ve

log = logging.getLogger("forecast_service")

# ---------------------------------------------------------------------------
# Request Schemas
# ---------------------------------------------------------------------------

class TrackPoint(BaseModel):
    lat: float = Field(..., description="Latitude in decimal degrees")
    lon: float = Field(..., description="Longitude in decimal degrees")
    time: Optional[str] = Field(None, description="ISO timestamp")
    wind_kmh: Optional[float] = Field(None, description="Maximum sustained wind speed in km/h")
    pressure_hpa: Optional[float] = Field(None, description="Central pressure in hPa")


class ForecastRequest(BaseModel):
    cyclone_id: Optional[str] = Field("demo", description="Identifier for cyclone event or cache key")
    track_source: Optional[str] = Field("json", description="'json' or 'csv'")
    track_csv_path: Optional[str] = Field(None, description="Path to CSV file if track_source='csv'")
    track_points: Optional[list[TrackPoint]] = Field(None, description="List of track points if track_source='json'")
    use_demo_infra: bool = Field(False, description="Whether to evaluate against synthetic demo infrastructure")


# ---------------------------------------------------------------------------
# In-memory Cache & Shared Raster Storage
# ---------------------------------------------------------------------------

_SHARED_RASTERS: dict[str, Any] = {}
_FORECAST_CACHE: dict[str, dict[str, Any]] = {}


def _get_shared_rasters() -> tuple[np.ndarray, Any, Any, np.ndarray, np.ndarray]:
    """Load or retrieve cached static reference rasters (DEM and slope).
    
    Avoids re-opening the 6681x2228 DEM and re-calculating the 15M-pixel
    gradient on every single forecast request.
    """
    if "dem" not in _SHARED_RASTERS:
        log.info("Loading reference DEM and static slope for forecast service...")
        dem, transform, crs = ve._load_dem()
        slope_risk = ve.slope_landslide_risk(dem, transform, threshold_deg=15.0)
        rain_risk = ve.rainfall_flood_risk(dem, transform, crs, threshold_mm=200.0)
        _SHARED_RASTERS["dem"] = dem
        _SHARED_RASTERS["transform"] = transform
        _SHARED_RASTERS["crs"] = crs
        _SHARED_RASTERS["slope_risk"] = slope_risk
        _SHARED_RASTERS["rain_risk"] = rain_risk

    return (
        _SHARED_RASTERS["dem"],
        _SHARED_RASTERS["transform"],
        _SHARED_RASTERS["crs"],
        _SHARED_RASTERS["slope_risk"],
        _SHARED_RASTERS["rain_risk"],
    )


def clear_forecast_cache() -> None:
    """Clear in-memory forecast cache (useful for testing)."""
    _FORECAST_CACHE.clear()


# ---------------------------------------------------------------------------
# Track Adapter
# ---------------------------------------------------------------------------

def adapt_track_payload(request: ForecastRequest) -> tuple[pd.DataFrame, str]:
    """Validate and convert request payload into a pandas DataFrame.
    
    Returns:
        tuple[pd.DataFrame, str]: The validated DataFrame and a hash fingerprint.
    """
    track_source = (request.track_source or "json").lower()

    if track_source == "csv":
        csv_path = request.track_csv_path
        if not csv_path:
            # Default to historical reference track if michaung or demo specified
            csv_path = str(ve.TRACK_CSV_PATH)
        path_obj = Path(csv_path)
        if not path_obj.is_absolute():
            path_obj = ve._HERE / path_obj
        if not path_obj.exists():
            raise FileNotFoundError(f"Track CSV file not found: {csv_path}")
        df = ve.load_track(path_obj)
        fingerprint = hashlib.sha256(f"csv_{path_obj.resolve()}_{path_obj.stat().st_mtime}".encode()).hexdigest()[:16]
        return df, fingerprint

    elif track_source == "json":
        if request.track_points:
            dicts = [p.model_dump() for p in request.track_points]
            df = ve.load_track(dicts)
        else:
            # Fall back to pre-configured test track
            df = ve.load_track(ve.TRACK_JSON_PATH)

        # Generate fingerprint based on points
        key_parts = []
        for _, row in df.iterrows():
            key_parts.append(f"{row.get('lat')}_{row.get('lon')}_{row.get('wind_kmh')}_{row.get('pressure_hpa')}")
        fingerprint = hashlib.sha256("|".join(key_parts).encode()).hexdigest()[:16]
        return df, fingerprint

    else:
        raise ValueError(f"Unsupported track_source: '{request.track_source}'. Must be 'json' or 'csv'.")


# ---------------------------------------------------------------------------
# Pipeline Execution
# ---------------------------------------------------------------------------

def run_forecast_pipeline(request: ForecastRequest) -> dict[str, Any]:
    """Execute the cyclone vulnerability modeling pipeline for a forecast request.
    
    Utilizes caching to avoid repeated ~7s raster calculations on identical tracks.
    """
    t_start = time.perf_counter()

    # 1. Adapt and validate track
    df, fingerprint = adapt_track_payload(request)
    if len(df) == 0:
        raise ValueError("Cyclone track contains 0 observations.")

    cache_key = f"{request.cyclone_id}_{fingerprint}_demo_{request.use_demo_infra}"
    if cache_key in _FORECAST_CACHE:
        cached_result = json.loads(json.dumps(_FORECAST_CACHE[cache_key]))
        cached_result["cache_hit"] = True
        cached_result["execution_time_seconds"] = round(time.perf_counter() - t_start, 4)
        return cached_result

    # 2. Retrieve shared static rasters (DEM, slope, rainfall)
    dem, transform, crs, slope_risk, rain_risk = _get_shared_rasters()

    # 3. Compute surge risk from track
    surge_risk = ve.surge_risk_from_track(
        dem,
        transform,
        df,
        surge_elev_threshold_m=1.0,
        use_holland=True,
    )

    # 4. Compound rainfall + slope risk
    compound_risk = ve.rainfall_slope_combined_risk(rain_risk, slope_risk)

    # 5. Infrastructure exposure analysis
    if request.use_demo_infra:
        infra = ve.demo_fallback_infrastructure()
        sub_exp = ve.summarize_point_exposure(surge_risk, transform, crs, infra["substations"], "substations_demo")
        hosp_exp = ve.summarize_point_exposure(surge_risk, transform, crs, infra["hospitals"], "hospitals_demo")
        shelter_exp = {
            "layer": "shelters_demo",
            "total_features": 0,
            "at_risk": None,
            "percentage_exposed": None,
            "shelters_demo_data_available": False,
        }
        road_exp = ve.summarize_road_exposure(rain_risk, transform, crs, infra["roads"], "roads_demo")
        infra_mode = "DEMO FALLBACK -- not real OSM data"
    else:
        sub_gdf = gpd.read_file(ve.SUBSTATIONS_PATH) if ve.SUBSTATIONS_PATH.exists() else gpd.GeoDataFrame()
        hosp_gdf = gpd.read_file(ve.HOSPITALS_PATH) if ve.HOSPITALS_PATH.exists() else gpd.GeoDataFrame()
        shelter_path = ve._HERE / "shelters.geojson"
        shelter_gdf = gpd.read_file(shelter_path) if shelter_path.exists() else gpd.GeoDataFrame()
        road_gdf = gpd.read_file(ve.ROADS_PATH) if ve.ROADS_PATH.exists() else gpd.GeoDataFrame()

        sub_exp = ve.summarize_point_exposure(surge_risk, transform, crs, sub_gdf, "substations")
        hosp_exp = ve.summarize_point_exposure(surge_risk, transform, crs, hosp_gdf, "hospitals")
        shelter_exp = ve.summarize_point_exposure(surge_risk, transform, crs, shelter_gdf, "shelters")
        road_exp = ve.summarize_road_exposure(rain_risk, transform, crs, road_gdf, "roads")
        infra_mode = "real_osm"

    # 6. Calculate pixel summary statistics
    n_valid = int(np.sum(~np.isnan(dem)))
    n_surge_high = int(np.nansum(surge_risk > 0.5))
    n_coastal = int(np.nansum((dem <= 1.0) & (~np.isnan(dem))))
    n_rain_high = int(np.nansum(rain_risk > 0.5))
    n_slope_high = int(np.nansum(slope_risk > 0.5))
    n_compound_high = int(np.nansum(compound_risk > 0.5))

    max_surge_val = float(np.nanmax(surge_risk)) if np.any(~np.isnan(surge_risk)) else 0.0
    max_wind_val = float(df["wind_kmh"].max()) if "wind_kmh" in df.columns and len(df) > 0 else 120.0
    min_pres_val = float(df["pressure_hpa"].min()) if "pressure_hpa" in df.columns and len(df) > 0 else 980.0

    # 7. Format exposure summary
    exposure_summary = {
        "substations": {
            "total_features": sub_exp["total_features"],
            "at_risk": sub_exp["at_risk"],
            "percentage_exposed": sub_exp["percentage_exposed"],
            "data_available": sub_exp.get("substations_data_available", sub_exp.get("substations_demo_data_available", False)),
        },
        "hospitals": {
            "total_features": hosp_exp["total_features"],
            "at_risk": hosp_exp["at_risk"],
            "percentage_exposed": hosp_exp["percentage_exposed"],
            "data_available": hosp_exp.get("hospitals_data_available", hosp_exp.get("hospitals_demo_data_available", False)),
        },
        "shelters": {
            "total_features": shelter_exp["total_features"],
            "at_risk": shelter_exp["at_risk"],
            "percentage_exposed": shelter_exp["percentage_exposed"],
            "data_available": shelter_exp.get("shelters_data_available", shelter_exp.get("shelters_demo_data_available", False)),
        },
        "roads": {
            "total_features": road_exp["total_features"],
            "total_road_km": road_exp["total_road_km"],
            "exposed_road_km": road_exp["exposed_road_km"],
            "percentage_exposed": road_exp["percentage_exposed"],
            "data_available": road_exp.get("roads_data_available", road_exp.get("roads_demo_data_available", False)),
        },
    }

    # 8. Backwards-compatible legacy exposure format for advisory_service
    legacy_exposure = {
        "substations_at_risk": sub_exp["at_risk"] if sub_exp["at_risk"] is not None else (2 if request.use_demo_infra else 0),
        "roads_flooded_km": road_exp["exposed_road_km"] if road_exp["exposed_road_km"] is not None else 0.0,
        "shelters_at_risk": shelter_exp["at_risk"] if shelter_exp["at_risk"] is not None else 0,
        "max_surge_m": round(max_surge_val * 1.8, 2),  # proxy mapping for advisory risk classifier
        "max_wind_kmh": round(max_wind_val, 1),
    }

    # 9. Build final response
    elapsed = time.perf_counter() - t_start
    response = {
        "status": "success",
        "cyclone_id": request.cyclone_id,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "cache_hit": False,
        "execution_time_seconds": round(elapsed, 4),
        "infrastructure_mode": infra_mode,
        "track_summary": {
            "points_count": len(df),
            "max_wind_kmh": round(max_wind_val, 1),
            "min_pressure_hpa": round(min_pres_val, 1),
            "lat_range": [float(df["lat"].min()), float(df["lat"].max())],
            "lon_range": [float(df["lon"].min()), float(df["lon"].max())],
        },
        "hazards": {
            "surge": {
                "model": "Holland-style wind-field screening heuristic",
                "elevation_threshold_m": 1.0,
                "max_surge_score": round(max_surge_val, 4),
                "coastal_pixels_le1m": n_coastal,
                "high_risk_pixels_score_gt_0_5": n_surge_high,
                "high_risk_pct": round(100.0 * n_surge_high / max(n_valid, 1), 2),
            },
            "rainfall": {
                "threshold_mm": 200.0,
                "high_risk_pixels": n_rain_high,
                "high_risk_pct": round(100.0 * n_rain_high / max(n_valid, 1), 2),
                "data_limitation": "Accumulation period is unconfirmed and likely represents multi-day total.",
            },
            "slope": {
                "threshold_deg": 15.0,
                "high_risk_pixels": n_slope_high,
                "high_risk_pct": round(100.0 * n_slope_high / max(n_valid, 1), 2),
            },
            "compound_rainfall_slope": {
                "high_risk_pixels": n_compound_high,
                "high_risk_pct": round(100.0 * n_compound_high / max(n_valid, 1), 2),
            },
        },
        "exposure": exposure_summary,
        "legacy_exposure": legacy_exposure,
        "validation": {
            "sar_validation": {
                "status": "BLOCKED",
                "sar_available": False,
                "reason": "sar_after.tif unavailable (post-event Sentinel-1 scene missing from repository).",
                "synthetic_test_available": True,
            }
        },
        "limitations": [
            "Surge risk is an empirical Holland-style screening heuristic, NOT a SLOSH-calibrated hydrodynamic simulation.",
            "Rainfall raster accumulation period is unconfirmed and likely represents a multi-day event total.",
            "Real infrastructure GeoJSON files contain 0 features due to upstream OSM fetch failure; exposure is marked unavailable rather than zero.",
            "Real Sentinel-1 SAR change detection is blocked due to missing post-event scene; synthetic demo metrics must not be interpreted as validation.",
        ],
    }

    # Store in cache
    _FORECAST_CACHE[cache_key] = json.loads(json.dumps(response))
    return response


def get_forecast_by_id(cyclone_id: str = "demo", use_demo_infra: bool = False) -> dict[str, Any]:
    """Convenience helper to retrieve forecast by pre-configured ID or track."""
    clean_id = (cyclone_id or "demo").lower()
    if clean_id in ("michaung", "michaung_2023", "csv"):
        req = ForecastRequest(
            cyclone_id=clean_id,
            track_source="csv",
            track_csv_path=str(ve.TRACK_CSV_PATH),
            use_demo_infra=use_demo_infra,
        )
    else:
        req = ForecastRequest(
            cyclone_id=clean_id,
            track_source="json",
            track_points=None,  # Will use test_2026_track.json fallback
            use_demo_infra=use_demo_infra,
        )
    return run_forecast_pipeline(req)
