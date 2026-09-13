from __future__ import annotations

from pathlib import Path
import html
import folium
import pandas as pd


def _popup(row, fields):
    bits = []
    for f in fields:
        if hasattr(row, f):
            bits.append(f"<b>{html.escape(f)}</b>: {html.escape(str(getattr(row, f)))}")
    return "<br>".join(bits)


def make_map(scored: pd.DataFrame, hosts: pd.DataFrame, output: str | Path, top_n_stops=500, top_n_hosts=100):
    if scored.empty:
        center = [8.0, -10.0]
    else:
        center = [float(scored["lat"].median()), float(scored["lon"].median())]
    m = folium.Map(location=center, zoom_start=5, control_scale=True, tiles="CartoDB positron")

    stop_layer = folium.FeatureGroup(name="Ranked stop episodes", show=True)
    for r in scored.head(top_n_stops).itertuples():
        folium.CircleMarker(
            location=[r.lat, r.lon],
            radius=4 + min(float(getattr(r, "suspicion_score", 0)) / 25, 5),
            weight=1,
            fill=True,
            fill_opacity=0.65,
            popup=folium.Popup(_popup(r, ["stop_id", "vessel_id", "ship_name", "vessel_type", "duration_hours", "nearest_port_km", "nearby_gaps", "nearby_encounters", "cluster_id", "suspicion_score"]), max_width=420),
        ).add_to(stop_layer)
    stop_layer.add_to(m)

    host_layer = folium.FeatureGroup(name="Candidate stationary hosts", show=True)
    for r in hosts.head(top_n_hosts).itertuples():
        folium.Marker(
            location=[r.lat, r.lon],
            tooltip=f"Host candidate {r.vessel_id} score={r.host_score}",
            popup=folium.Popup(_popup(r, ["vessel_id", "ship_name", "flag", "vessel_type", "cluster_id", "host_stop_hours", "host_episodes", "other_vessels", "nearest_port_km", "nearby_gaps", "nearby_encounters", "host_score"]), max_width=450),
        ).add_to(host_layer)
    host_layer.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(output))
