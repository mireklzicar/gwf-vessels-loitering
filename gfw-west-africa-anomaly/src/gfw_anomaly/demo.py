from __future__ import annotations

import numpy as np
import pandas as pd


def synthetic_presence(seed: int = 7) -> pd.DataFrame:
    """Synthetic low-speed hourly AIS-like data with one offshore hub and background stops."""
    rng = np.random.default_rng(seed)
    rows = []
    base = pd.Timestamp("2026-01-01", tz="UTC")
    vessels = ["factory_A", "visitor_B", "visitor_C", "visitor_D", "background_E"]
    centers = {
        "factory_A": (13.0, -17.8),
        "visitor_B": (13.01, -17.79),
        "visitor_C": (12.99, -17.82),
        "visitor_D": (13.02, -17.81),
        "background_E": (5.1, -1.5),
    }
    durations = {"factory_A": 120, "visitor_B": 12, "visitor_C": 9, "visitor_D": 7, "background_E": 6}
    offsets = {"factory_A": 0, "visitor_B": 25, "visitor_C": 60, "visitor_D": 90, "background_E": 20}
    for v in vessels:
        lat0, lon0 = centers[v]
        for h in range(durations[v]):
            rows.append({
                "vessel_id": v,
                "ship_name": v,
                "vessel_type": "carrier" if v == "factory_A" else "fishing",
                "flag": "UNK",
                "date": base + pd.Timedelta(hours=offsets[v] + h),
                "lat": lat0 + rng.normal(0, 0.003),
                "lon": lon0 + rng.normal(0, 0.003),
                "hours": 1.0,
            })
    return pd.DataFrame(rows)


def synthetic_events():
    base = pd.Timestamp("2026-01-01", tz="UTC")
    def df(kind, coords, hours):
        rows = []
        for i, ((lat, lon), h) in enumerate(zip(coords, hours)):
            rows.append({"event_kind": kind, "event_id": f"{kind}_{i}", "start": base + pd.Timedelta(hours=h), "end": base + pd.Timedelta(hours=h+2), "lat": lat, "lon": lon, "vessel_id": None})
        return pd.DataFrame(rows)
    return {
        "port_visits": df("port_visits", [(14.67, -17.43), (5.55, -0.20), (4.9, -1.75)], [1, 10, 20]),
        "gaps": df("gaps", [(13.0, -17.8), (13.02, -17.81)], [23, 88]),
        "encounters": df("encounters", [(13.01, -17.79), (13.0, -17.8)], [30, 63]),
        "loitering": df("loitering", [(13.0, -17.8)], [5]),
    }
