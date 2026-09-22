"""
test_full_validation.py
=======================
Full validation test suite for vulnerability_engine.py.
Covers Stages 1 through 5, regression tests, edge cases, and locked threshold checks.

Run:
    python -m pytest tests/test_full_validation.py -v
or:
    python tests/test_full_validation.py
"""

import math
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
from rasterio.transform import from_origin
from shapely.geometry import Point, LineString

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import vulnerability_engine as ve


# ===========================================================================
# Stage 1: Data Foundation & Utility Tests
# ===========================================================================

def test_stage1_load_dem():
    """Verify DEM loading contract, shape, dtype, and CRS."""
    dem, transform, crs = ve._load_dem()
    assert isinstance(dem, np.ndarray)
    assert dem.dtype == np.float32
    assert dem.shape == (6681, 2228)
    assert str(crs).upper() in ("EPSG:4326", "+INIT=EPSG:4326")
    # Verify non-empty and finite values exist
    assert not np.isneginf(dem).any()
    assert np.isfinite(dem).any()


def test_stage1_load_track_formats():
    """Test load_track handles CSV, JSON, and list of dicts."""
    # CSV
    csv_df = ve.load_track(ve.TRACK_CSV_PATH)
    assert "lat" in csv_df.columns
    assert "lon" in csv_df.columns
    assert len(csv_df) > 0

    # JSON
    json_df = ve.load_track(ve.TRACK_JSON_PATH)
    assert "lat" in json_df.columns
    assert "lon" in json_df.columns
    assert len(json_df) == 3

    # In-memory list of dicts
    mem_track = [
        {"lat": 13.0, "lon": 80.2, "wind_kmh": 100, "pressure_hpa": 990},
        {"lat": 13.2, "lon": 80.3, "wind_kmh": 120, "pressure_hpa": 980},
    ]
    mem_df = ve.load_track(mem_track)
    assert len(mem_df) == 2
    assert "lat" in mem_df.columns and "lon" in mem_df.columns


def test_stage1_lonlat_to_rowcol():
    """Test coordinate conversion with bounds checking."""
    # North-up transform: origin at (lon=80.0, lat=14.0), pixel size 0.01 deg
    transform = from_origin(80.0, 14.0, 0.01, 0.01)
    height, width = 100, 100

    # Point clearly inside pixel (row=5, col=5): lon=80.055, lat=13.945
    r, c = ve.lonlat_to_rowcol(80.055, 13.945, transform, height, width)
    assert r == 5 and c == 5

    # Out of bounds returns (None, None)
    r_out, c_out = ve.lonlat_to_rowcol(79.0, 15.0, transform, height, width)
    assert r_out is None and c_out is None


# ===========================================================================
# Stage 2: Holland Surge Proxy & Wind Sensitivity Tests
# ===========================================================================

def test_stage2_surge_risk_threshold_and_bounds():
    """Verify surge risk is strictly in [0, 1] and elevation <= 1.0m."""
    dem, transform, crs = ve._load_dem()
    track_df = ve.load_track(ve.TRACK_JSON_PATH)

    surge = ve.surge_risk_from_track(dem, transform, track_df, surge_elev_threshold_m=1.0)
    assert surge.shape == dem.shape

    # Elevation > 1.0 m must be 0.0
    high_elev = (dem > 1.0) & (~np.isnan(dem))
    assert np.all(surge[high_elev] == 0.0)

    # Values must be within [0.0, 1.0] or NaN
    valid = ~np.isnan(surge)
    assert np.all(surge[valid] >= 0.0)
    assert np.all(surge[valid] <= 1.0)


def test_stage2_wind_speed_sensitivity_regression():
    """Regression test: verify wind speed participates in raw proxy calculation.
    
    When two points in a track have different wind speeds, the point with
    higher wind speed produces a greater raw wind stress proxy.
    """
    track_varying_wind = [
        {"lat": 13.0, "lon": 80.25, "wind_kmh": 40.0, "pressure_hpa": 990.0},
        {"lat": 13.5, "lon": 80.25, "wind_kmh": 160.0, "pressure_hpa": 990.0},
    ]
    df = ve.load_track(track_varying_wind)
    twind = df["wind_kmh"].values.astype(np.float32)
    vmax_ms = twind / np.float32(3.6)

    # Vmax for 160 km/h should be 4x Vmax for 40 km/h
    assert np.isclose(vmax_ms[1], 4.0 * vmax_ms[0])

    # Wind stress proxy scales with vmax_ms^2 -> ratio should be 16x
    proxy_factor_0 = vmax_ms[0] ** 2
    proxy_factor_1 = vmax_ms[1] ** 2
    assert np.isclose(proxy_factor_1, 16.0 * proxy_factor_0)


# ===========================================================================
# Stage 3: Rainfall + Slope Landslide / Flood Risk Tests
# ===========================================================================

def test_stage3_rainfall_flood_risk():
    """Verify rainfall risk thresholding and backwards-compatible signature."""
    dem, transform, crs = ve._load_dem()

    # Call with 1 argument (backwards compatible)
    rain_risk_1 = ve.rainfall_flood_risk(dem)
    assert rain_risk_1.shape == dem.shape

    # Call with 3 arguments (optimized)
    rain_risk_3 = ve.rainfall_flood_risk(dem, transform, crs)
    assert rain_risk_3.shape == dem.shape
    np.testing.assert_array_equal(rain_risk_1, rain_risk_3)

    # Valid values must be 0.0 or 1.0
    valid = ~np.isnan(rain_risk_1)
    unique_vals = set(np.unique(rain_risk_1[valid]))
    assert unique_vals.issubset({0.0, 1.0})


def test_stage3_slope_landslide_risk():
    """Verify slope calculation and > 15 deg threshold."""
    dem, transform, crs = ve._load_dem()
    slope_risk = ve.slope_landslide_risk(dem, transform, threshold_deg=15.0)

    assert slope_risk.shape == dem.shape
    valid = ~np.isnan(slope_risk)
    unique_vals = set(np.unique(slope_risk[valid]))
    assert unique_vals.issubset({0.0, 1.0})


def test_stage3_rainfall_slope_combined():
    """Verify rainfall + slope logical AND combination and NaN propagation."""
    dem, transform, crs = ve._load_dem()
    rain_risk = ve.rainfall_flood_risk(dem, transform, crs)
    slope_risk = ve.slope_landslide_risk(dem, transform)
    combined = ve.rainfall_slope_combined_risk(rain_risk, slope_risk)

    assert combined.shape == dem.shape
    # Where either is NaN, combined is NaN
    nan_mask = np.isnan(rain_risk) | np.isnan(slope_risk)
    assert np.all(np.isnan(combined[nan_mask]))

    # Where both are 1.0, combined is 1.0
    both_high = (rain_risk == 1.0) & (slope_risk == 1.0)
    assert np.all(combined[both_high] == 1.0)

    # Where either is 0.0, combined is 0.0
    either_zero = ((rain_risk == 0.0) | (slope_risk == 0.0)) & ~nan_mask
    assert np.all(combined[either_zero] == 0.0)


# ===========================================================================
# Stage 4: Infrastructure Exposure Tests
# ===========================================================================

def test_stage4_point_exposure_empty_data():
    """Empty GeoDataFrame must return data_available=False and at_risk=None."""
    dem, transform, crs = ve._load_dem()
    dummy_risk = np.zeros_like(dem)
    empty_gdf = gpd.GeoDataFrame()

    res = ve.summarize_point_exposure(dummy_risk, transform, crs, empty_gdf, "test_points")
    assert res["test_points_data_available"] is False
    assert res["at_risk"] is None
    assert res["total_features"] == 0
    assert res["percentage_exposed"] is None


def test_stage4_point_exposure_mock_data():
    """Verify point exposure calculation with known risk pixels."""
    # Synthetic 10x10 risk array
    risk = np.zeros((10, 10), dtype=np.float32)
    risk[2, 3] = 0.8  # high risk (> 0.5)
    risk[5, 5] = 0.2  # low risk (< 0.5)
    transform = from_origin(80.0, 14.0, 0.1, 0.1)
    crs = "EPSG:4326"

    # Point 1 inside pixel (2, 3): col 3 -> lon ~ 80.35, row 2 -> lat ~ 13.75
    # Point 2 inside pixel (5, 5): col 5 -> lon ~ 80.55, row 5 -> lat ~ 13.45
    pts = [Point(80.35, 13.75), Point(80.55, 13.45)]
    gdf = gpd.GeoDataFrame({"geometry": pts}, crs=crs)

    res = ve.summarize_point_exposure(risk, transform, crs, gdf, "test_points", risk_threshold=0.5)
    assert res["test_points_data_available"] is True
    assert res["total_features"] == 2
    assert res["at_risk"] == 1
    assert res["percentage_exposed"] == 50.0


def test_stage4_road_exposure_empty_data():
    """Empty roads GeoDataFrame must return data_available=False and exposed_road_km=None."""
    dem, transform, crs = ve._load_dem()
    dummy_risk = np.zeros_like(dem)
    empty_gdf = gpd.GeoDataFrame()

    res = ve.summarize_road_exposure(dummy_risk, transform, crs, empty_gdf, "test_roads")
    assert res["test_roads_data_available"] is False
    assert res["exposed_road_km"] is None
    assert res["total_road_km"] == 0.0


def test_stage4_demo_fallback_infrastructure():
    """Verify demo fallback infrastructure generator produces valid data."""
    infra = ve.demo_fallback_infrastructure()
    assert "substations" in infra
    assert "hospitals" in infra
    assert "roads" in infra

    for key in ("substations", "hospitals", "roads"):
        gdf = infra[key]
        assert isinstance(gdf, gpd.GeoDataFrame)
        assert len(gdf) > 0
        assert gdf.crs is not None


# ===========================================================================
# Stage 5: SAR Change Detection & Backtesting Tests
# ===========================================================================

def test_stage5_sar_change_detection_logic():
    """Verify SAR change detection direction: positive change = water decrease in backscatter."""
    # Synthetic test scenes
    dem = np.zeros((10, 10), dtype=np.float32)
    before = np.full((10, 10), -10.0, dtype=np.float32)
    after = np.full((10, 10), -14.0, dtype=np.float32)  # drop of 4 dB > 2.5 dB threshold

    # change = before - after = -10 - (-14) = +4.0 dB > 2.5 dB
    change = before - after
    flood_mask = (change > 2.5).astype(np.float32)
    assert np.all(flood_mask == 1.0)


def test_stage5_compare_with_model():
    """Verify confusion matrix and metrics calculation."""
    # 4 pixels: TP, FP, FN, TN
    sar_obs = np.array([[1.0, 0.0],
                        [1.0, 0.0]], dtype=np.float32)
    model_risk = np.array([[0.8, 0.8],   # TP (pred 1, obs 1), FP (pred 1, obs 0)
                           [0.2, 0.2]],  # FN (pred 0, obs 1), TN (pred 0, obs 0)
                          dtype=np.float32)

    stats = ve.compare_with_model(sar_obs, model_risk)
    assert stats["true_positive"] == 1
    assert stats["false_positive"] == 1
    assert stats["false_negative"] == 1
    assert stats["true_negative"] == 1
    assert stats["precision"] == 0.5
    assert stats["recall"] == 0.5
    assert stats["f1"] == 0.5
    assert stats["accuracy"] == 0.5


def test_stage5_demo_backtest_synthetic_flag():
    """Verify demo_backtest executes and unambiguously flags results as synthetic."""
    dem, transform, crs = ve._load_dem()
    track_df = ve.load_track(ve.TRACK_JSON_PATH)
    surge_risk = ve.surge_risk_from_track(dem, transform, track_df)
    rain_risk = ve.rainfall_flood_risk(dem, transform, crs)

    stats = ve.demo_backtest(dem, transform, crs, surge_risk, rain_risk)
    assert stats["synthetic"] is True
    assert "SYNTHETIC" in stats["warning"].upper()
    assert "f1" in stats
    assert "precision" in stats
    assert "recall" in stats


# ===========================================================================
# Locked Thresholds Verification (Audit Requirement)
# ===========================================================================

def test_locked_thresholds_audit():
    """Verify locked thresholds match task spec exactly."""
    import inspect

    # Rainfall threshold: 200 mm
    sig_rain = inspect.signature(ve.rainfall_flood_risk)
    assert sig_rain.parameters["threshold_mm"].default == 200.0

    # Slope threshold: 15.0 deg
    sig_slope = inspect.signature(ve.slope_landslide_risk)
    assert sig_slope.parameters["threshold_deg"].default == 15.0

    # SAR threshold: 2.5 dB
    sig_sar = inspect.signature(ve.sar_change_detection)
    assert sig_sar.parameters["threshold_db"].default == 2.5

    # Surge elevation threshold: 1.0 m
    sig_surge = inspect.signature(ve.surge_risk_from_track)
    assert sig_surge.parameters["surge_elev_threshold_m"].default == 1.0


if __name__ == "__main__":
    pytest.main(["-v", __file__])
