from __future__ import annotations

from pathlib import Path
import pandas as pd

from .clustering import cluster_stops, cluster_summary
from .duration import vessel_loitering_hours
from .enrich import infer_ports, add_nearest_port, add_event_matches
from .mapviz import make_map
from .scoring import score_stops, candidate_hosts
from .stops import detect_stops
from .storage import write_parquet, build_duckdb


def analyze(presence: pd.DataFrame, events: dict[str, pd.DataFrame], cfg: dict, root: str | Path = "."):
    root = Path(root)
    processed = root / "data" / "processed"
    outputs = root / "outputs"
    processed.mkdir(parents=True, exist_ok=True)
    outputs.mkdir(parents=True, exist_ok=True)

    # Events spanning several fetch chunks come back once per chunk; count each once.
    events = {
        k: (df.drop_duplicates("event_id") if not df.empty and "event_id" in df.columns else df)
        for k, df in events.items()
    }

    s_cfg = cfg["stops"]
    stops = detect_stops(
        presence,
        min_duration_hours=s_cfg["min_duration_hours"],
        max_gap_hours=s_cfg["max_gap_hours"],
        max_step_km=s_cfg["max_step_km"],
        max_radius_km=s_cfg["max_radius_km"],
    )
    c_cfg = cfg["clustering"]
    stops = cluster_stops(stops, c_cfg["min_cluster_size"], c_cfg["min_samples"])
    clusters = cluster_summary(stops)

    m_cfg = cfg["matching"]
    ports = infer_ports(events.get("port_visits", pd.DataFrame()), m_cfg["port_dedup_radius_km"])
    stops = add_nearest_port(stops, ports)
    stops = add_event_matches(stops, events, m_cfg["event_space_km"], m_cfg["event_time_hours"])

    scored = score_stops(stops, clusters, cfg["ranking"]["port_distance_cap_km"])
    hosts = candidate_hosts(scored, cfg["ranking"]["min_host_hours"])
    durations = vessel_loitering_hours(
        scored, presence, events.get("loitering"), cfg["ranking"].get("offshore_km", 20.0)
    )

    write_parquet(presence, processed / "presence.parquet")
    for kind, df in events.items():
        write_parquet(df, processed / f"events_{kind}.parquet")
    write_parquet(ports, processed / "ports_inferred.parquet")
    write_parquet(scored, processed / "stops_scored.parquet")
    write_parquet(hosts, processed / "candidate_hosts.parquet")
    write_parquet(durations, processed / "vessel_loitering_hours.parquet")
    scored.to_csv(outputs / "suspicious_stops.csv", index=False)
    hosts.to_csv(outputs / "candidate_hosts.csv", index=False)
    durations.to_csv(outputs / "vessel_loitering_hours.csv", index=False)

    make_map(
        scored,
        hosts,
        outputs / "suspicious_map.html",
        cfg["map"]["top_n_stops"],
        cfg["map"]["top_n_hosts"],
    )
    build_duckdb(
        processed / "analysis.duckdb",
        {
            "presence": processed / "presence.parquet",
            "stops": processed / "stops_scored.parquet",
            "candidate_hosts": processed / "candidate_hosts.parquet",
            "vessel_loitering_hours": processed / "vessel_loitering_hours.parquet",
            "ports_inferred": processed / "ports_inferred.parquet",
            **{f"events_{k}": processed / f"events_{k}.parquet" for k in events},
        },
    )
    return scored, hosts
