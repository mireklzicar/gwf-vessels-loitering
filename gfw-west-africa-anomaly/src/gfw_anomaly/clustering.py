from __future__ import annotations

import numpy as np
import pandas as pd

from .utils import local_xy_km


def cluster_stops(stops: pd.DataFrame, min_cluster_size: int = 3, min_samples: int = 2) -> pd.DataFrame:
    if stops.empty:
        out = stops.copy()
        out["cluster_id"] = pd.Series(dtype="int")
        return out
    xy, _ = local_xy_km(stops["lat"], stops["lon"])
    try:
        import hdbscan

        def _run(allow_single: bool):
            return hdbscan.HDBSCAN(
                min_cluster_size=min_cluster_size,
                min_samples=min_samples,
                metric="euclidean",
                cluster_selection_method="eom",
                allow_single_cluster=allow_single,
            ).fit_predict(xy)

        labels = _run(False)
        if (labels < 0).all():
            # HDBSCAN never returns the hierarchy root as a cluster by default, so a
            # dataset with a single genuine hotspot comes back as all noise. Retry
            # allowing a single cluster only in that degenerate case.
            labels = _run(True)
    except ImportError:
        from sklearn.cluster import DBSCAN
        labels = DBSCAN(eps=8.0, min_samples=max(2, min_samples)).fit_predict(xy)
    out = stops.copy()
    out["cluster_id"] = labels.astype(int)
    return out


def cluster_summary(stops: pd.DataFrame) -> pd.DataFrame:
    c = stops[stops["cluster_id"] >= 0].copy()
    if c.empty:
        return pd.DataFrame()
    summary = (
        c.groupby("cluster_id")
        .agg(
            cluster_lat=("lat", "median"),
            cluster_lon=("lon", "median"),
            cluster_total_stop_hours=("duration_hours", "sum"),
            cluster_unique_vessels=("vessel_id", "nunique"),
            cluster_stop_episodes=("stop_id", "count"),
            cluster_first_seen=("start", "min"),
            cluster_last_seen=("end", "max"),
        )
        .reset_index()
    )
    return summary
