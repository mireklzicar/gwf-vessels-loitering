import pandas as pd
from shapely.geometry import box, mapping

from gfw_anomaly.breakdown import assign_countries, country_year_hours


def boundaries():
    return {'features': [
        {'properties': {'country': name}, 'geometry': mapping(box(*bounds))}
        for name, bounds in [('A', (0, 0, 2, 2)), ('B', (2, 0, 4, 2))]]}


def test_assignment_including_shared_boundary_and_unassigned():
    points = pd.DataFrame({'lat': [1, 1, 1, 1, None], 'lon': [1, 3, 2, 5, 1]})
    assert assign_countries(points, boundaries()).tolist() == [
        'A', 'B', 'A / B', 'Unassigned', 'Unassigned']


def test_year_clipping_preserves_hours_and_uses_full_leap_year_denominator():
    stops = pd.DataFrame([dict(vessel_id='v', stop_id='s',
        start='2019-12-31T22:00Z', end='2020-01-01T03:00Z', duration_hours=6,
        lat=1, lon=1, nearest_port_km=30, cluster_id=0, nearby_encounters=0,
        nearby_gaps=0, cluster_unique_vessels=1)])
    presence = pd.DataFrame({'vessel_id': ['v'], 'date': ['2019-12-31T22:00Z']})
    events = pd.DataFrame([dict(vessel_id='v', event_id='e', lat=1, lon=1,
                               start='2019-12-31T23:00Z', end='2020-01-01T02:00Z')]*2)
    result = country_year_hours(stops, presence, events, boundaries(), '2019-01-01', '2021-01-01')
    assert result.total_stop_hours.tolist() == [2, 4]
    assert result.gfw_loitering_hours.tolist() == [1, 2]
    assert result.gfw_loitering_events.tolist() == [1, 1]
    assert result.complete_calendar_year.all()
    assert (result.window_end.iloc[1] - result.window_start.iloc[1]).total_seconds()/3600 == 8784
    assert not result.likely_fixed_installation.any()


def test_country_specific_event_hours():
    stops = pd.DataFrame([dict(vessel_id='v', stop_id=str(lon),
        start='2026-06-01T00:00Z', end='2026-06-01T03:00Z', duration_hours=4,
        lat=1, lon=lon, nearest_port_km=30, cluster_id=0, nearby_encounters=0,
        nearby_gaps=0, cluster_unique_vessels=1) for lon in [1, 3]])
    presence = pd.DataFrame({'vessel_id': ['v'], 'date': ['2026-06-01T00:00Z']})
    events = pd.DataFrame([dict(vessel_id='v', event_id='e', lat=1, lon=1,
                               start='2026-06-01T00:00Z', end='2026-06-01T02:00Z')])
    result = country_year_hours(stops, presence, events, boundaries(), '2026-06-01', '2026-08-01')
    assert result.gfw_loitering_hours.tolist() == [2, 0]
    assert not result.complete_calendar_year.any()
