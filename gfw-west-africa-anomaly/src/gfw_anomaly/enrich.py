from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN

from .utils import haversine_km, local_xy_km


def infer_ports(port_visits: pd.DataFrame, dedup_radius_km: float = 3.0) -> pd.DataFrame:
    """Infer an empirical port/anchorage catalogue from GFW port-visit event positions."""
    if port_visits.empty or not {"lat", "lon"}.issubset(port_visits.columns):
        return pd.DataFrame(columns=["port_id", "lat", "lon", "n_visits"])
    x = port_visits.dropna(subset=["lat", "lon"]).copy()
    if x.empty:
        return pd.DataFrame(columns=["port_id", "lat", "lon", "n_visits"])
    xy, _ = local_xy_km(x["lat"], x["lon"])
    labels = DBSCAN(eps=dedup_radius_km, min_samples=1).fit_predict(xy)
    x["port_id"] = labels
    return (
        x.groupby("port_id")
        .agg(lat=("lat", "median"), lon=("lon", "median"), n_visits=("event_id", "count"))
        .reset_index()
    )


def add_nearest_port(stops: pd.DataFrame, ports: pd.DataFrame) -> pd.DataFrame:
    out = stops.copy()
    if out.empty:
        return out
    if ports.empty:
        out["nearest_port_km"] = np.nan
        out["nearest_port_id"] = np.nan
        return out
    dists = []
    pids = []
    plat = ports["lat"].to_numpy()
    plon = ports["lon"].to_numpy()
    for row in out.itertuples():
        d = haversine_km(plat, plon, row.lat, row.lon)
        i = int(np.argmin(d))
        dists.append(float(d[i]))
        pids.append(ports.iloc[i]["port_id"])
    out["nearest_port_km"] = dists
    out["nearest_port_id"] = pids
    return out


def _event_match_counts(stops: pd.DataFrame, events: pd.DataFrame, prefix: str, space_km: float, time_hours: float):
    counts = np.zeros(len(stops), dtype=int)
    if events.empty or stops.empty:
        return counts
    ev = events.dropna(subset=["lat", "lon", "start"]).copy()
    if ev.empty:
        return counts
    for i, s in enumerate(stops.itertuples()):
        t0 = pd.Timestamp(s.start) - pd.Timedelta(hours=time_hours)
        t1 = pd.Timestamp(s.end) + pd.Timedelta(hours=time_hours)
        cand = ev[(ev["start"] <= t1) & (ev.get("end", ev["start"]).fillna(ev["start"]) >= t0)]
        if cand.empty:
            continue
        d = haversine_km(cand["lat"].to_numpy(), cand["lon"].to_numpy(), s.lat, s.lon)
        counts[i] = int(np.sum(d <= space_km))
    return counts


def add_event_matches(
    stops: pd.DataFrame,
    events: dict[str, pd.DataFrame],
    space_km: float = 20.0,
    time_hours: float = 24.0,
) -> pd.DataFrame:
    out = stops.copy()
    for kind in ["gaps", "encounters", "loitering"]:
        out[f"nearby_{kind}"] = _event_match_counts(
            out, events.get(kind, pd.DataFrame()), kind, space_km, time_hours
        )
    return out
