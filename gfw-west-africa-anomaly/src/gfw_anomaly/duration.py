from __future__ import annotations

import numpy as np
import pandas as pd


def _first_non_null(s: pd.Series):
    s = s.dropna()
    s = s[s.astype(str).str.strip() != ""]
    return s.iloc[0] if len(s) else None


def _identity_table(presence: pd.DataFrame) -> pd.DataFrame:
    """One row per GFW vessel_id with the identity fields the 4Wings rows carry."""
    if presence.empty or "vessel_id" not in presence.columns:
        return pd.DataFrame(columns=["vessel_id"])
    cols = [c for c in ["ship_name", "flag", "vessel_type", "geartype", "imo", "mmsi", "callsign"] if c in presence.columns]
    if not cols:
        return presence[["vessel_id"]].drop_duplicates()
    return presence.groupby("vessel_id")[cols].agg(_first_non_null).reset_index()


def _clipped_hours(start: pd.Series, end: pd.Series, t0: pd.Timestamp, t1: pd.Timestamp) -> pd.Series:
    s = pd.to_datetime(start, utc=True, errors="coerce").clip(lower=t0, upper=t1)
    e = pd.to_datetime(end, utc=True, errors="coerce").fillna(t1).clip(lower=t0, upper=t1)
    return ((e - s).dt.total_seconds() / 3600).clip(lower=0)


def vessel_loitering_hours(
    stops: pd.DataFrame,
    presence: pd.DataFrame,
    loitering_events: pd.DataFrame | None = None,
    offshore_km: float = 20.0,
    *,
    window_start=None,
    window_end=None,
) -> pd.DataFrame:
    """Rank vessels by *cumulative* stationary time rather than by event counts.

    For every vessel: total hours across all detected stop episodes, the share of
    that time spent at least `offshore_km` from an inferred port/anchorage, the
    longest single episode, how many distinct spots were used, and (if available)
    the hours GFW's own loitering-event product assigns to the vessel inside the
    same window. GFW loitering events can span years, so they are clipped to the
    window covered by the presence data.
    """
    if stops.empty:
        return pd.DataFrame()

    x = stops.copy()
    x["start"] = pd.to_datetime(x["start"], utc=True)
    x["end"] = pd.to_datetime(x["end"], utc=True)
    ts = pd.to_datetime(presence["date"], utc=True, errors="coerce") if "date" in presence.columns else x["start"]
    t0, t1 = ts.min(), ts.max() + pd.Timedelta(hours=1)
    if window_start is not None:
        t0 = pd.to_datetime(window_start, utc=True)
    if window_end is not None:
        t1 = pd.to_datetime(window_end, utc=True)
    window_hours = max((t1 - t0).total_seconds() / 3600, 1.0)

    port_km = pd.to_numeric(x.get("nearest_port_km"), errors="coerce")
    x["offshore_hours"] = np.where(port_km.fillna(np.inf) >= offshore_km, x["duration_hours"], 0.0)
    x["cell"] = x["lat"].round(1).astype(str) + "," + x["lon"].round(1).astype(str)
    x["cluster_key"] = np.where(x["cluster_id"] >= 0, "C" + x["cluster_id"].astype(str), "noise:" + x["cell"])

    agg = (
        x.groupby("vessel_id")
        .agg(
            stop_episodes=("stop_id", "count"),
            total_stop_hours=("duration_hours", "sum"),
            offshore_stop_hours=("offshore_hours", "sum"),
            longest_stop_hours=("duration_hours", "max"),
            distinct_locations=("cluster_key", "nunique"),
            median_port_km=("nearest_port_km", "median"),
            max_port_km=("nearest_port_km", "max"),
            first_seen=("start", "min"),
            last_seen=("end", "max"),
            nearby_encounters=("nearby_encounters", "sum"),
            nearby_gaps=("nearby_gaps", "sum"),
            shared_location_max_vessels=("cluster_unique_vessels", "max"),
        )
        .reset_index()
    )
    longest = x.sort_values("duration_hours", ascending=False).drop_duplicates("vessel_id")[
        ["vessel_id", "lat", "lon", "start", "end", "nearest_port_km"]
    ].rename(
        columns={
            "lat": "longest_stop_lat",
            "lon": "longest_stop_lon",
            "start": "longest_stop_start",
            "end": "longest_stop_end",
            "nearest_port_km": "longest_stop_port_km",
        }
    )
    agg = agg.merge(longest, on="vessel_id", how="left")
    agg["share_of_window"] = (agg["total_stop_hours"] / window_hours).round(3)
    agg["offshore_share"] = (agg["offshore_stop_hours"] / agg["total_stop_hours"].replace(0, np.nan)).round(3)
    # Parked at one spot for essentially the whole window: FPSOs, FLNG units, moored
    # storage barges, rigs. Useful to filter out, but kept in the table for transparency.
    agg["likely_fixed_installation"] = (agg["share_of_window"] >= 0.95) & (agg["distinct_locations"] == 1)

    if loitering_events is not None and not loitering_events.empty and "vessel_id" in loitering_events.columns:
        ev = loitering_events.dropna(subset=["vessel_id"]).copy()
        if "event_id" in ev.columns:
            # An event spanning several fetch chunks is returned once per chunk.
            ev = ev.drop_duplicates("event_id")
        ev["hours_in_window"] = _clipped_hours(ev["start"], ev["end"], t0, t1)
        ev = ev[ev["hours_in_window"] > 0]
        g = ev.groupby("vessel_id").agg(gfw_loitering_events=("event_id", "count"), gfw_loitering_hours=("hours_in_window", "sum")).reset_index()
        agg = agg.merge(g, on="vessel_id", how="left")
        agg["gfw_loitering_events"] = agg["gfw_loitering_events"].fillna(0).astype(int)
        agg["gfw_loitering_hours"] = agg["gfw_loitering_hours"].fillna(0.0)

    agg = agg.merge(_identity_table(presence), on="vessel_id", how="left")

    for c in ["total_stop_hours", "offshore_stop_hours", "longest_stop_hours", "median_port_km", "max_port_km", "longest_stop_port_km", "gfw_loitering_hours"]:
        if c in agg.columns:
            agg[c] = pd.to_numeric(agg[c], errors="coerce").round(1)

    front = [c for c in ["ship_name", "flag", "vessel_type", "geartype", "imo", "mmsi", "callsign", "vessel_id"] if c in agg.columns]
    rest = [c for c in agg.columns if c not in front]
    agg = agg[front + rest]
    agg["window_start"] = t0
    agg["window_end"] = t1
    return agg.sort_values(["offshore_stop_hours", "total_stop_hours"], ascending=False).reset_index(drop=True)
