from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Iterable, Iterator

import numpy as np
import pandas as pd
from shapely.geometry import shape, mapping
from shapely.ops import unary_union

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1, lon1, lat2, lon2):
    """Vector-friendly great-circle distance in km."""
    lat1 = np.radians(lat1)
    lon1 = np.radians(lon1)
    lat2 = np.radians(lat2)
    lon2 = np.radians(lon2)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def local_xy_km(lat: Iterable[float], lon: Iterable[float], lat0: float | None = None):
    lat = np.asarray(list(lat), dtype=float)
    lon = np.asarray(list(lon), dtype=float)
    if lat0 is None:
        lat0 = float(np.nanmean(lat)) if len(lat) else 0.0
    x = lon * 111.320 * math.cos(math.radians(lat0))
    y = lat * 110.574
    return np.column_stack([x, y]), lat0


def monthish_chunks(start: str, end: str, chunk_days: int = 31) -> Iterator[tuple[str, str]]:
    """Yield half-open date chunks [start, end)."""
    s = pd.Timestamp(start, tz="UTC")
    e = pd.Timestamp(end, tz="UTC")
    while s < e:
        n = min(s + pd.Timedelta(days=chunk_days), e)
        yield s.strftime("%Y-%m-%d"), n.strftime("%Y-%m-%d")
        s = n


def load_geojson_geometry(path: str | Path) -> dict:
    obj = json.loads(Path(path).read_text())
    if obj["type"] == "FeatureCollection":
        geom = unary_union([shape(f["geometry"]) for f in obj["features"]])
        return mapping(geom)
    if obj["type"] == "Feature":
        return obj["geometry"]
    return obj


def normalize_timestamp_column(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    candidates = ["date", "timestamp", "entryTimestamp", "entry_timestamp"]
    src = next((c for c in candidates if c in out.columns), None)
    if src is None:
        raise ValueError(f"Could not find timestamp column; columns={list(out.columns)}")
    out["timestamp"] = pd.to_datetime(out[src], utc=True, errors="coerce")
    return out
