from gfw_anomaly.demo import synthetic_presence
from gfw_anomaly.stops import detect_stops


def test_factory_stop_detected():
    stops = detect_stops(synthetic_presence(), min_duration_hours=4, max_gap_hours=2.25, max_step_km=5, max_radius_km=5)
    factory = stops[stops.vessel_id == "factory_A"]
    assert len(factory) == 1
    assert factory.iloc[0].duration_hours >= 100
