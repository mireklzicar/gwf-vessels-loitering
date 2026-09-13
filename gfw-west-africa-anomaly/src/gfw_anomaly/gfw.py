from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from .utils import monthish_chunks

EVENT_DATASETS = {
    "loitering": "public-global-loitering-events:latest",
    "encounters": "public-global-encounters-events:latest",
    "gaps": "public-global-gaps-events:latest",
    "port_visits": "public-global-port-visits-events:latest",
}


@dataclass
class GFWClient:
    token: str
    base_url: str = "https://gateway.api.globalfishingwatch.org"
    timeout_seconds: int = 110
    last_report_poll_seconds: int = 5
    last_report_max_polls: int = 36

    @classmethod
    def from_env(cls, **kwargs):
        token = os.environ.get("GFW_API_TOKEN")
        if not token:
            raise RuntimeError("Set GFW_API_TOKEN or pass --token")
        return cls(token=token, **kwargs)

    @property
    def headers(self):
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def _raise(self, response: requests.Response):
        if response.ok:
            return
        try:
            detail = response.json()
        except Exception:
            detail = response.text[:1000]
        raise RuntimeError(f"GFW API {response.status_code}: {detail}")

    def _recover_last_report(self) -> dict:
        url = f"{self.base_url}/v3/4wings/last-report"
        for _ in range(self.last_report_max_polls):
            r = requests.get(url, headers=self.headers, timeout=30)
            if r.status_code == 404:
                time.sleep(self.last_report_poll_seconds)
                continue
            self._raise(r)
            payload = r.json()
            if payload.get("status") == "running":
                time.sleep(self.last_report_poll_seconds)
                continue
            if isinstance(payload.get("status"), int) and payload["status"] >= 400:
                raise RuntimeError(f"GFW last-report failed: {payload}")
            return payload
        raise TimeoutError("GFW report remained 'running' past polling limit")

    def presence_report(
        self,
        geometry: dict,
        start: str,
        end: str,
        dataset: str = "public-global-presence:latest",
        spatial_resolution: str = "HIGH",
        temporal_resolution: str = "HOURLY",
        group_by: str = "VESSEL_ID",
        presence_filter: str | None = "speed = '<2'",
    ) -> dict:
        params = {
            "spatial-resolution": spatial_resolution,
            "temporal-resolution": temporal_resolution,
            "group-by": group_by,
            "datasets[0]": dataset,
            "date-range": f"{start},{end}",
            "format": "JSON",
            "spatial-aggregation": "false",
        }
        if presence_filter:
            params["filters[0]"] = presence_filter
        # The v3 report endpoint expects the geometry as a JSON object under "geojson";
        # a stringified FeatureCollection is rejected with 422 "body malformed".
        body = {"geojson": geometry}
        url = f"{self.base_url}/v3/4wings/report"
        try:
            r = requests.post(url, params=params, headers=self.headers, json=body, timeout=self.timeout_seconds)
        except requests.Timeout:
            return self._recover_last_report()
        if r.status_code in (524, 504):
            return self._recover_last_report()
        if r.status_code == 429:
            # A previous report may still be running; recover it rather than launching another.
            return self._recover_last_report()
        self._raise(r)
        return r.json()

    def search_vessels(self, query: str, limit: int = 50) -> dict:
        """Resolve a ship name, IMO, MMSI or callsign to GFW vessel identity records."""
        url = f"{self.base_url}/v3/vessels/search"
        params = {
            "query": query,
            "datasets[0]": "public-global-vessel-identity:latest",
            "limit": limit,
            "includes[0]": "MATCH_CRITERIA",
        }
        r = requests.get(url, params=params, headers=self.headers, timeout=60)
        self._raise(r)
        return r.json()

    def event_pages(
        self,
        geometry: dict,
        start: str,
        end: str,
        dataset: str,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        url = f"{self.base_url}/v3/events"
        body = {"datasets": [dataset], "startDate": start, "endDate": end, "geometry": geometry}
        offset = 0
        rows: list[dict[str, Any]] = []
        while True:
            # Event POSTs are read-only queries: retry the same page without
            # advancing its offset or duplicating rows on transient failures.
            for attempt in range(5):
                try:
                    r = requests.post(
                        url,
                        params={"offset": offset, "limit": limit},
                        headers=self.headers,
                        json=body,
                        timeout=120,
                    )
                except (requests.Timeout, requests.ConnectionError):
                    if attempt == 4:
                        raise
                    reason = "connection/timeout"
                else:
                    if r.status_code not in (408, 429, 500, 502, 503, 504, 524):
                        self._raise(r)
                        break
                    if attempt == 4:
                        self._raise(r)
                    reason = f"HTTP {r.status_code}"
                delay = min(10 * 2**attempt, 60)
                print(f"  {dataset}: {reason}; retry {attempt + 1}/4 "
                      f"at offset {offset} in {delay}s", flush=True)
                time.sleep(delay)
            payload = r.json()
            rows.extend(payload.get("entries", []))
            print(f"  {dataset}: {len(rows):,}/{payload.get('total', '?')} events", flush=True)
            nxt = payload.get("nextOffset")
            if nxt is None or nxt == offset:
                break
            offset = int(nxt)
        return rows


def flatten_presence_payload(payload: dict) -> pd.DataFrame:
    """Flatten either current nested report JSON or a flat entries response."""
    entries = payload.get("entries", [])
    rows: list[dict] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        nested_lists = [v for v in entry.values() if isinstance(v, list)]
        if nested_lists:
            for lst in nested_lists:
                rows.extend([x for x in lst if isinstance(x, dict)])
        else:
            rows.append(entry)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    ren = {
        "vesselId": "vessel_id",
        "vessel_id": "vessel_id",
        "shipName": "ship_name",
        "vesselType": "vessel_type",
    }
    df = df.rename(columns={k: v for k, v in ren.items() if k in df.columns})
    if "vessel_id" not in df.columns:
        # Some API versions have emitted vessel_id only as the group name.
        possible = [c for c in df.columns if c.lower().replace("_", "") == "vesselid"]
        if possible:
            df = df.rename(columns={possible[0]: "vessel_id"})
    return df


def flatten_events(rows: list[dict], kind: str) -> pd.DataFrame:
    flat = []
    for e in rows:
        vessel = e.get("vessel") or {}
        pos = e.get("position") or {}
        distances = e.get("distances") or {}
        flat.append(
            {
                "event_kind": kind,
                "event_id": e.get("id"),
                "type": e.get("type"),
                "start": e.get("start"),
                "end": e.get("end"),
                "lat": pos.get("lat"),
                "lon": pos.get("lon"),
                "vessel_id": vessel.get("id"),
                "vessel_name": vessel.get("name"),
                "vessel_flag": vessel.get("flag"),
                "vessel_type": vessel.get("type"),
                "start_distance_from_port_km": distances.get("startDistanceFromPortKm"),
                "start_distance_from_shore_km": distances.get("startDistanceFromShoreKm"),
                "end_distance_from_port_km": distances.get("endDistanceFromPortKm"),
                "end_distance_from_shore_km": distances.get("endDistanceFromShoreKm"),
                "raw": json.dumps(e, separators=(",", ":")),
            }
        )
    df = pd.DataFrame(flat)
    for c in ["lat", "lon", "start_distance_from_port_km", "start_distance_from_shore_km", "end_distance_from_port_km", "end_distance_from_shore_km"]:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ["start", "end"]:
        if c in df:
            df[c] = pd.to_datetime(df[c], utc=True, errors="coerce")
    return df


def fetch_all(
    client: GFWClient,
    geometry: dict,
    start: str,
    end: str,
    raw_dir: str | Path,
    cfg: dict,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    chunks = list(monthish_chunks(start, end, cfg["api"].get("chunk_days", 31)))

    presence_frames = []
    event_frames: dict[str, list[pd.DataFrame]] = {k: [] for k in EVENT_DATASETS}

    for a, b in chunks:
        print(f"Fetching/caching {a} to {b}", flush=True)
        tag = f"{a}_{b}"
        presence_json = raw_dir / f"presence_{tag}.json"
        if presence_json.exists():
            payload = json.loads(presence_json.read_text())
        else:
            payload = client.presence_report(
                geometry=geometry,
                start=a,
                end=b,
                dataset=cfg["api"]["presence_dataset"],
                spatial_resolution=cfg["api"]["spatial_resolution"],
                temporal_resolution=cfg["api"]["temporal_resolution"],
                group_by=cfg["api"]["group_by"],
                presence_filter=cfg["api"].get("presence_filter"),
            )
            presence_json.write_text(json.dumps(payload))
        presence_frames.append(flatten_presence_payload(payload))

        for kind, dataset in EVENT_DATASETS.items():
            event_json = raw_dir / f"events_{kind}_{tag}.json"
            if event_json.exists():
                rows = json.loads(event_json.read_text())
            else:
                rows = client.event_pages(
                    geometry=geometry,
                    start=a,
                    end=b,
                    dataset=dataset,
                    limit=cfg["api"].get("events_limit", 500),
                )
                event_json.write_text(json.dumps(rows))
            event_frames[kind].append(flatten_events(rows, kind))

    presence = pd.concat(presence_frames, ignore_index=True) if presence_frames else pd.DataFrame()
    events = {
        k: pd.concat(v, ignore_index=True) if v else pd.DataFrame()
        for k, v in event_frames.items()
    }
    return presence, events
