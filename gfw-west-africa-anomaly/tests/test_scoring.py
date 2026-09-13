from gfw_anomaly.demo import synthetic_presence, synthetic_events
from gfw_anomaly.stops import detect_stops
from gfw_anomaly.clustering import cluster_stops, cluster_summary
from gfw_anomaly.enrich import infer_ports, add_nearest_port, add_event_matches
from gfw_anomaly.scoring import score_stops, candidate_hosts


def test_factory_is_host_candidate():
    stops = detect_stops(synthetic_presence(), min_duration_hours=4)
    stops = cluster_stops(stops, min_cluster_size=3, min_samples=2)
    clusters = cluster_summary(stops)
    ev = synthetic_events()
    stops = add_nearest_port(stops, infer_ports(ev["port_visits"]))
    stops = add_event_matches(stops, ev, 20, 24)
    scored = score_stops(stops, clusters)
    hosts = candidate_hosts(scored, min_host_hours=8)
    assert "factory_A" in set(hosts.vessel_id)
