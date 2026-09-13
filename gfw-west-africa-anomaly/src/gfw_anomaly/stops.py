from __future__ import annotations

import numpy as np
import pandas as pd

from .utils import haversine_km, normalize_timestamp_column


def _standardize_presence(df: pd.DataFrame) -> pd.DataFrame:
    x = normalize_timestamp_column(df)
    if "vessel_id" not in x.columns:
        raise ValueError("Presence data has no vessel_id column; cannot form trajectories")
    for c in ["lat", "lon"]:
        x[c] = pd.to_numeric(x[c], errors="coerce")
    x = x.dropna(subset=["vessel_id", "timestamp", "lat", "lon"]).copy()
    x = x.sort_values(["vessel_id", "timestamp"]).reset_index(drop=True)
    return x


def detect_stops(
    presence: pd.DataFrame,
    min_duration_hours: float = 4.0,
    max_gap_hours: float = 2.25,
    max_step_km: float = 5.0,
    max_radius_km: float = 5.0,
) -> pd.DataFrame:
    """Turn consecutive low-speed hourly presence cells into stop episodes.

    The caller is expected to fetch AIS presence using GFW's `speed = '<2'` bucket filter.
    A new episode begins after a temporal gap or a spatial jump.
    """
    x = _standardize_presence(presence)
    out = []
    stop_counter = 0

    for vessel_id, g in x.groupby("vessel_id", sort=False):
        g = g.reset_index(drop=True)
        if len(g) < 2:
            continue
        dt_h = g["timestamp"].diff().dt.total_seconds().div(3600)
        step = np.full(len(g), np.nan)
        if len(g) > 1:
            lat = g["lat"].to_numpy()
            lon = g["lon"].to_numpy()
            step[1:] = haversine_km(lat[1:], lon[1:], lat[:-1], lon[:-1])
        breaks = (dt_h > max_gap_hours) | (pd.Series(step) > max_step_km)
        episode_id = breaks.fillna(False).cumsum()

        for _, e in g.groupby(episode_id):
            if len(e) < 2:
                continue
            start = e["timestamp"].iloc[0]
            end = e["timestamp"].iloc[-1]
            duration = (end - start).total_seconds() / 3600 + 1.0
            if duration < min_duration_hours:
                continue
            clat = float(e["lat"].median())
            clon = float(e["lon"].median())
            radii = haversine_km(e["lat"].to_numpy(), e["lon"].to_numpy(), clat, clon)
            radius = float(np.nanmax(radii)) if len(radii) else 0.0
            if radius > max_radius_km:
                continue
            stop_counter += 1
            first = e.iloc[0]
            out.append(
                {
                    "stop_id": f"S{stop_counter:08d}",
                    "vessel_id": vessel_id,
                    "ship_name": first.get("ship_name"),
                    "flag": first.get("flag"),
                    "vessel_type": first.get("vessel_type"),
                    "start": start,
                    "end": end,
                    "duration_hours": duration,
                    "n_hourly_points": len(e),
                    "lat": clat,
                    "lon": clon,
                    "radius_km": radius,
                    "mean_presence_hours": pd.to_numeric(e.get("hours", pd.Series([1] * len(e))), errors="coerce").mean(),
                }
            )

    return pd.DataFrame(out)
