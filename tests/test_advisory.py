from advisory_service import compute_risk_level, call_with_timeout, generate_risk_map, infer_hotspots_from_map


def test_compute_risk_level():
    assert compute_risk_level({"max_surge_m": 1.8, "max_wind_kmh": 125}) == "high"
    assert compute_risk_level({"max_surge_m": 1.0, "max_wind_kmh": 110}) == "medium"
    assert compute_risk_level({"max_surge_m": 0.5, "max_wind_kmh": 40}) == "low"


def test_call_with_timeout_fallback():
    def slow_fn():
        import time
        time.sleep(0.5)
        return "never"

    assert call_with_timeout(slow_fn, timeout=0.05, cached_fallback="fallback") == "fallback"


def test_risk_map_hotspots_change():
    map_a = generate_risk_map(seed=7)
    map_b = generate_risk_map(seed=22)
    zones_a = infer_hotspots_from_map(map_a)
    zones_b = infer_hotspots_from_map(map_b)
    assert zones_a != zones_b
