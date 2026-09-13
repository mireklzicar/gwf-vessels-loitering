from __future__ import annotations

import numpy as np
import pandas as pd


def _sat_log(x, scale):
    if not isinstance(x, pd.Series):
        x = pd.Series(x, dtype=float)
    x = np.maximum(pd.to_numeric(x, errors="coerce").fillna(0).to_numpy(float), 0)
    return np.log1p(x) / np.log1p(scale)


def _col(df: pd.DataFrame, name: str) -> pd.Series:
    """Return a numeric column, or a zero series if the enrichment step never produced it."""
    if name in df.columns:
        return df[name]
    return pd.Series(0.0, index=df.index)


def score_stops(stops: pd.DataFrame, clusters: pd.DataFrame, port_distance_cap_km: float = 100.0) -> pd.DataFrame:
    if stops.empty:
        return stops.copy()
    out = stops.merge(clusters, on="cluster_id", how="left") if not clusters.empty else stops.copy()
    duration = np.clip(_sat_log(out["duration_hours"], 72), 0, 1.5)
    port = np.clip(pd.to_numeric(_col(out, "nearest_port_km"), errors="coerce").fillna(0).to_numpy(float) / port_distance_cap_km, 0, 1)
    gaps = np.clip(_sat_log(_col(out, "nearby_gaps"), 3), 0, 1.5)
    encounters = np.clip(_sat_log(_col(out, "nearby_encounters"), 3), 0, 1.5)
    hub_vessels = np.clip(_sat_log(_col(out, "cluster_unique_vessels"), 10), 0, 1.5)
    hub_hours = np.clip(_sat_log(_col(out, "cluster_total_stop_hours"), 500), 0, 1.5)
    # Transparent heuristic, not a legal/illegality classifier.
    out["suspicion_score"] = 100 * (
        0.28 * duration + 0.22 * port + 0.18 * gaps + 0.14 * encounters + 0.10 * hub_vessels + 0.08 * hub_hours
    )
    out["suspicion_score"] = out["suspicion_score"].round(2)
    return out.sort_values("suspicion_score", ascending=False).reset_index(drop=True)


def candidate_hosts(scored_stops: pd.DataFrame, min_host_hours: float = 8.0) -> pd.DataFrame:
    x = scored_stops[scored_stops["cluster_id"] >= 0].copy()
    if x.empty:
        return pd.DataFrame()
    host = (
        x.groupby(["cluster_id", "vessel_id"], dropna=False)
        .agg(
            ship_name=("ship_name", "first"),
            flag=("flag", "first"),
            vessel_type=("vessel_type", "first"),
            host_stop_hours=("duration_hours", "sum"),
            host_episodes=("stop_id", "count"),
            lat=("lat", "median"),
            lon=("lon", "median"),
            nearest_port_km=("nearest_port_km", "median"),
            nearby_gaps=("nearby_gaps", "sum"),
            nearby_encounters=("nearby_encounters", "sum"),
            cluster_total_stop_hours=("cluster_total_stop_hours", "first"),
            cluster_unique_vessels=("cluster_unique_vessels", "first"),
        )
        .reset_index()
    )
    host = host[host["host_stop_hours"] >= min_host_hours].copy()
    host["other_vessels"] = (host["cluster_unique_vessels"] - 1).clip(lower=0)
    host["host_share"] = host["host_stop_hours"] / host["cluster_total_stop_hours"].replace(0, np.nan)
    host["host_score"] = 100 * (
        0.38 * np.clip(_sat_log(host["host_stop_hours"], 1000), 0, 1.5)
        + 0.28 * np.clip(_sat_log(host["other_vessels"], 10), 0, 1.5)
        + 0.14 * np.clip(_sat_log(host["nearby_encounters"], 5), 0, 1.5)
        + 0.10 * np.clip(_sat_log(host["nearby_gaps"], 5), 0, 1.5)
        + 0.10 * np.clip(host["nearest_port_km"].fillna(0).to_numpy(float) / 100, 0, 1)
    )
    host["host_score"] = host["host_score"].round(2)
    return host.sort_values("host_score", ascending=False).reset_index(drop=True)
