"""Country/UTC-year summaries of detected stop episodes."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from shapely.geometry import Point, shape
from shapely.prepared import prep

from .duration import _identity_table, vessel_loitering_hours


def assign_countries(rows: pd.DataFrame, boundaries: dict) -> pd.Series:
    """Assign centroids without duplicating hours in overlapping/joint areas."""
    areas = [(f['properties']['country'], prep(shape(f['geometry'])))
             for f in boundaries['features']]
    def locate(lat, lon):
        if pd.isna(lat) or pd.isna(lon):
            return 'Unassigned'
        point = Point(float(lon), float(lat))
        matches = sorted({country for name, area in areas if area.covers(point)
                          for country in name.split(' / ')})
        return ' / '.join(matches) if matches else 'Unassigned'
    return pd.Series([locate(lat, lon) for lat, lon in zip(rows.lat, rows.lon)],
                     index=rows.index, dtype='str')


def country_year_hours(stops, presence, events, boundaries, start, end, offshore_km=20):
    """Allocate each episode to its centroid's maritime area, then clip by year.

    Stop end timestamps denote the last hourly cell; event ends are exclusive.
    Countries are geographic attribution, independent of the vessel flag.
    """
    t0, t1 = pd.to_datetime(start, utc=True), pd.to_datetime(end, utc=True)
    if t1 <= t0:
        raise ValueError('end must be later than start')
    if stops.empty:
        return pd.DataFrame(columns=['country', 'year', 'vessel_id', 'total_stop_hours'])
    x = stops.copy()
    x['country'] = assign_countries(x, boundaries)
    x['start'] = pd.to_datetime(x.start, utc=True)
    x['end'] = pd.to_datetime(x.end, utc=True)
    ev = events.copy() if events is not None else pd.DataFrame()
    if not ev.empty:
        ev['country'] = assign_countries(ev, boundaries)
    identities = _identity_table(presence)
    outputs = []
    for year in range(t0.year, (t1 - pd.Timedelta(nanoseconds=1)).year + 1):
        year_start = pd.Timestamp(f'{year}-01-01', tz='UTC')
        year_end = pd.Timestamp(f'{year+1}-01-01', tz='UTC')
        a, b = max(t0, year_start), min(t1, year_end)
        part = x[(x.start < b) & (x.end + pd.Timedelta(hours=1) > a)].copy()
        part['start'] = part.start.clip(lower=a)
        exclusive_end = (part.end + pd.Timedelta(hours=1)).clip(upper=b)
        part['duration_hours'] = (exclusive_end - part.start).dt.total_seconds() / 3600
        part['end'] = exclusive_end - pd.Timedelta(hours=1)
        for country, group in part.groupby('country', sort=True):
            country_events = ev[ev.country == country] if not ev.empty else ev
            result = vessel_loitering_hours(group, identities, country_events, offshore_km,
                                           window_start=a, window_end=b)
            if events is not None:
                for col in ['gfw_loitering_hours', 'gfw_loitering_events']:
                    if col not in result:
                        result[col] = 0
            result.insert(0, 'year', year)
            result.insert(0, 'country', country)
            result['complete_calendar_year'] = a == year_start and b == year_end
            result['country_assignment'] = 'stop centroid / event representative position'
            outputs.append(result)
    return pd.concat(outputs, ignore_index=True) if outputs else pd.DataFrame(
        columns=['country', 'year', 'vessel_id', 'total_stop_hours'])


def write_breakdown(stops, presence, events, boundaries_path, start, end, output_dir,
                    offshore_km=20):
    boundaries = json.loads(Path(boundaries_path).read_text())
    result = country_year_hours(stops, presence, events, boundaries, start, end, offshore_km)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_dir / 'vessel_loitering_hours_by_country_year.csv', index=False)
    for year, group in result.groupby('year'):
        group.to_csv(output_dir / f'vessel_loitering_hours_by_country_{year}.csv', index=False)
    return result
