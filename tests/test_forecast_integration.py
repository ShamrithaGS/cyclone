"""
test_forecast_integration.py
=============================
Integration test suite for the /forecast API and forecast_service.
Validates:
  - GET /forecast endpoint (default demo track and historical CSV track)
  - POST /forecast endpoint with custom JSON track points
  - Track adapter validation and error handling for missing/invalid fields
  - Graceful degradation on empty infrastructure layers (data_available=False, at_risk=None)
  - Demo infrastructure fallback path
  - SAR validation blocked status disclosure
  - In-memory caching behavior (cache hit and sub-millisecond response)
  - Compatibility with /advisory
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import app
import forecast_service as fs

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_cache():
    """Ensure cache is reset between tests."""
    fs.clear_forecast_cache()
    yield
    fs.clear_forecast_cache()


# ===========================================================================
# 1. Endpoint & Schema Tests
# ===========================================================================

def test_get_forecast_default_demo():
    """Verify GET /forecast with default parameters returns 200 and expected schema."""
    response = client.get("/forecast")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "success"
    assert data["cyclone_id"] == "demo"
    assert data["cache_hit"] is False

    # Track summary
    assert "track_summary" in data
    assert data["track_summary"]["points_count"] == 3

    # Hazard sections
    hazards = data["hazards"]
    assert "surge" in hazards
    assert "rainfall" in hazards
    assert "slope" in hazards
    assert "compound_rainfall_slope" in hazards

    assert hazards["surge"]["elevation_threshold_m"] == 1.0
    assert hazards["rainfall"]["threshold_mm"] == 200.0
    assert hazards["slope"]["threshold_deg"] == 15.0
    assert "unconfirmed" in hazards["rainfall"]["data_limitation"].lower()

    # Exposure section
    exposure = data["exposure"]
    assert "substations" in exposure
    assert "hospitals" in exposure
    assert "shelters" in exposure
    assert "roads" in exposure

    # Validation & Limitations
    validation = data["validation"]
    assert validation["sar_validation"]["status"] == "BLOCKED"
    assert validation["sar_validation"]["sar_available"] is False
    assert "sar_after.tif" in validation["sar_validation"]["reason"]

    assert len(data["limitations"]) >= 4


def test_get_forecast_michaung_csv():
    """Verify GET /forecast?cyclone_id=michaung loads historical CSV track."""
    response = client.get("/forecast?cyclone_id=michaung")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "success"
    assert data["cyclone_id"] == "michaung"
    assert data["track_summary"]["points_count"] == 34


def test_post_forecast_custom_json_track():
    """Verify POST /forecast with custom JSON track points."""
    payload = {
        "cyclone_id": "custom_cyclone_2026",
        "track_source": "json",
        "track_points": [
            {"time": "2026-10-01T00:00:00Z", "lat": 13.0, "lon": 80.25, "wind_kmh": 90.0, "pressure_hpa": 985.0},
            {"time": "2026-10-01T06:00:00Z", "lat": 13.3, "lon": 80.30, "wind_kmh": 140.0, "pressure_hpa": 965.0},
        ],
        "use_demo_infra": False,
    }
    response = client.post("/forecast", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "success"
    assert data["cyclone_id"] == "custom_cyclone_2026"
    assert data["track_summary"]["points_count"] == 2
    assert data["track_summary"]["max_wind_kmh"] == 140.0
    assert data["track_summary"]["min_pressure_hpa"] == 965.0


# ===========================================================================
# 2. Track Adapter Validation & Error Handling
# ===========================================================================

def test_post_forecast_missing_required_lat():
    """Track point missing required 'lat' field must return HTTP 422 Unprocessable Entity."""
    invalid_payload = {
        "cyclone_id": "bad_track",
        "track_source": "json",
        "track_points": [
            {"lon": 80.25, "wind_kmh": 100.0}  # missing lat
        ],
    }
    response = client.post("/forecast", json=invalid_payload)
    assert response.status_code == 422


def test_post_forecast_invalid_csv_path():
    """Non-existent CSV track file must return HTTP 404 Not Found."""
    payload = {
        "cyclone_id": "missing_csv",
        "track_source": "csv",
        "track_csv_path": "non_existent_file_xyz.csv",
    }
    response = client.post("/forecast", json=payload)
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_post_forecast_unsupported_track_source():
    """Unsupported track source must return HTTP 400 Bad Request."""
    payload = {
        "cyclone_id": "bad_source",
        "track_source": "xml_feed",
    }
    response = client.post("/forecast", json=payload)
    assert response.status_code == 400
    assert "unsupported track_source" in response.json()["detail"].lower()


# ===========================================================================
# 3. Missing Data & Graceful Degradation Contracts
# ===========================================================================

def test_empty_infrastructure_graceful_degradation():
    """When real infrastructure GeoJSON layers are empty, data_available must be False and at_risk must be None."""
    response = client.get("/forecast?cyclone_id=demo&use_demo_infra=false")
    assert response.status_code == 200
    exp = response.json()["exposure"]

    # All real layers in the repo currently have 0 features due to upstream OSM failure
    for layer in ("substations", "hospitals", "shelters", "roads"):
        assert exp[layer]["data_available"] is False
        if layer == "roads":
            assert exp[layer]["exposed_road_km"] is None
        else:
            assert exp[layer]["at_risk"] is None


def test_demo_infrastructure_fallback_mode():
    """When use_demo_infra=True, synthetic demo infrastructure is evaluated cleanly."""
    response = client.get("/forecast?cyclone_id=demo&use_demo_infra=true")
    assert response.status_code == 200
    data = response.json()

    assert "DEMO FALLBACK" in data["infrastructure_mode"]
    exp = data["exposure"]
    assert exp["substations"]["data_available"] is True
    assert exp["substations"]["total_features"] == 3
    assert exp["substations"]["at_risk"] is not None


def test_sar_validation_explicit_blocked_status():
    """SAR validation must be explicitly marked BLOCKED, never claiming successful validation."""
    response = client.get("/forecast")
    sar_val = response.json()["validation"]["sar_validation"]
    assert sar_val["status"] == "BLOCKED"
    assert sar_val["sar_available"] is False
    assert "missing" in sar_val["reason"].lower() or "unavailable" in sar_val["reason"].lower()


# ===========================================================================
# 4. Performance & In-Memory Caching
# ===========================================================================

def test_in_memory_caching_performance():
    """Second request for identical track must hit cache and return in under 50ms."""
    # First request: computes rasters
    r1 = client.get("/forecast?cyclone_id=demo")
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["cache_hit"] is False

    # Second request: must hit cache
    r2 = client.get("/forecast?cyclone_id=demo")
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["cache_hit"] is True
    assert d2["execution_time_seconds"] < 0.05
    assert d1["hazards"]["surge"]["high_risk_pixels_score_gt_0_5"] == d2["hazards"]["surge"]["high_risk_pixels_score_gt_0_5"]


# ===========================================================================
# 5. Advisory Service Integration
# ===========================================================================

def test_advisory_endpoint_integration():
    """Verify GET /advisory consumes forecast exposure seamlessly."""
    response = client.get("/advisory?cyclone_id=demo")
    assert response.status_code == 200
    data = response.json()
    assert "zones" in data
    assert "advisory_en" in data
    assert "advisory_ta" in data
    assert data["risk_level"] in ("low", "medium", "high")
