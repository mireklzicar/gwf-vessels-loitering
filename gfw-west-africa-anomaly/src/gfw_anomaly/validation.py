from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class KnownVessel:
    label: str
    imo: str
    notes: str = ""


JOSEF_FISHMEAL_CASE = [
    KnownVessel(
        label="TIAN YI HE 6",
        imo="8698633",
        notes="Floating fishmeal factory vessel reported in Guinea-Bissau and later Sierra Leone.",
    ),
    KnownVessel(
        label="HUA XIN 17",
        imo="1049962",
        notes="Floating fishmeal factory vessel; use IMO because AIS MMSI/flag changed over time.",
    ),
]


def _iter_self_reported_ids(payload: dict) -> list[dict]:
    """Extract GFW vessel IDs from vessel-search responses across minor schema variants."""
    found: list[dict] = []
    for entry in payload.get("entries", []) or []:
        infos = entry.get("selfReportedInfo") or []
        if isinstance(infos, dict):
            infos = [infos]
        for info in infos:
            if not isinstance(info, dict) or not info.get("id"):
                continue
            found.append(
                {
                    "vessel_id": str(info.get("id")),
                    "ship_name": info.get("shipname") or info.get("shipName"),
                    "imo": str(info.get("imo")) if info.get("imo") is not None else None,
                    "mmsi": str(info.get("ssvid")) if info.get("ssvid") is not None else None,
                    "flag": info.get("flag"),
                    "from": info.get("transmissionDateFrom"),
                    "to": info.get("transmissionDateTo"),
                }
            )
    # Stable de-duplication by GFW vessel id.
    dedup = {}
    for row in found:
        dedup[row["vessel_id"]] = row
    return list(dedup.values())


def resolve_gfw_vessel_ids(client, query: str) -> list[dict]:
    payload = client.search_vessels(query)
    return _iter_self_reported_ids(payload)


def _read_if_exists(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path) if path.exists() else pd.DataFrame()


def summarize_detection(root: str | Path, vessel_ids: Iterable[str], label: str, imo: str | None = None) -> dict:
    root = Path(root)
    pdir = root / "data" / "processed"
    vids = {str(v) for v in vessel_ids}

    presence = _read_if_exists(pdir / "presence.parquet")
    stops = _read_if_exists(pdir / "stops_scored.parquet")
    hosts = _read_if_exists(pdir / "candidate_hosts.parquet")

    def filt(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or "vessel_id" not in df.columns:
            return df.iloc[0:0].copy()
        return df[df["vessel_id"].astype(str).isin(vids)].copy()

    p = filt(presence)
    s = filt(stops)
    h = filt(hosts)

    # Fallback for identity resolution edge cases: the 4Wings response can contain IMO directly.
    if p.empty and imo and not presence.empty and "imo" in presence.columns:
        p = presence[presence["imo"].astype(str) == str(imo)].copy()
        if "vessel_id" in p.columns:
            vids |= set(p["vessel_id"].astype(str).dropna())
            s = filt(stops)
            h = filt(hosts)

    best_stop = float(s["suspicion_score"].max()) if not s.empty and "suspicion_score" in s else None
    best_host = float(h["host_score"].max()) if not h.empty and "host_score" in h else None

    stop_rank = None
    stop_pct = None
    if best_stop is not None and not stops.empty and "suspicion_score" in stops:
        vals = pd.to_numeric(stops["suspicion_score"], errors="coerce").dropna().sort_values(ascending=False)
        if len(vals):
            stop_rank = int((vals > best_stop).sum()) + 1
            stop_pct = round(100.0 * (vals <= best_stop).sum() / len(vals), 2)

    host_rank = None
    host_pct = None
    if best_host is not None and not hosts.empty and "host_score" in hosts:
        vals = pd.to_numeric(hosts["host_score"], errors="coerce").dropna().sort_values(ascending=False)
        if len(vals):
            host_rank = int((vals > best_host).sum()) + 1
            host_pct = round(100.0 * (vals <= best_host).sum() / len(vals), 2)

    return {
        "label": label,
        "imo": imo,
        "gfw_vessel_ids": ";".join(sorted(vids)),
        "presence_rows": int(len(p)),
        "stop_episodes": int(len(s)),
        "total_stop_hours": round(float(pd.to_numeric(s.get("duration_hours", pd.Series(dtype=float)), errors="coerce").sum()), 2) if not s.empty else 0.0,
        "best_stop_score": best_stop,
        "best_stop_rank": stop_rank,
        "best_stop_percentile": stop_pct,
        "host_rows": int(len(h)),
        "best_host_score": best_host,
        "best_host_rank": host_rank,
        "best_host_percentile": host_pct,
        "detected_as_stop": bool(len(s)),
        "detected_as_host": bool(len(h)),
    }


def validation_detail(root: str | Path, vessel_ids: Iterable[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    root = Path(root)
    vids = {str(v) for v in vessel_ids}
    stops = _read_if_exists(root / "data" / "processed" / "stops_scored.parquet")
    hosts = _read_if_exists(root / "data" / "processed" / "candidate_hosts.parquet")
    if not stops.empty and "vessel_id" in stops:
        stops = stops[stops["vessel_id"].astype(str).isin(vids)].sort_values("suspicion_score", ascending=False)
    if not hosts.empty and "vessel_id" in hosts:
        hosts = hosts[hosts["vessel_id"].astype(str).isin(vids)].sort_values("host_score", ascending=False)
    return stops, hosts
