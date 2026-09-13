import pandas as pd
import pytest

from gfw_anomaly.collapse import collapse_country_years


def row(vessel, year, hours, country='A', end=None):
    return dict(country=country, vessel_id=vessel, year=year,
        ship_name=vessel, flag='TST', vessel_type='FISHING', geartype='test',
        imo='1234567', mmsi='123456789', callsign='ABC',
        window_start=f'{year}-01-01', window_end=end or f'{year+1}-01-01',
        first_seen=f'{year}-02-01', last_seen=f'{year}-02-02',
        longest_stop_start=f'{year}-02-01', longest_stop_end=f'{year}-02-02',
        total_stop_hours=hours, offshore_stop_hours=hours/2, stop_episodes=2,
        gfw_loitering_hours=10, nearby_encounters=1, nearby_gaps=0,
        distinct_locations=2, max_port_km=30, shared_location_max_vessels=2,
        likely_fixed_installation=False, gfw_loitering_events=1,
        longest_stop_hours=25, longest_stop_lat=1, longest_stop_lon=2,
        longest_stop_port_km=30)


def test_normalized_ranking_and_no_stop_year_exposure():
    annual = pd.DataFrame([row('old', 2019, 4000), row('old', 2020, 4000),
                           row('new', 2020, 6000), row('old', 2019, 100, country='B')])
    observed = pd.DataFrame({'vessel_id': ['old', 'old', 'new'], 'year': [2019, 2020, 2020]})
    result = collapse_country_years(annual, observed)
    assert result.iloc[0].vessel_id == 'new'
    old = result[(result.vessel_id == 'old') & (result.country == 'A')].iloc[0]
    assert old.total_stop_hours == 8000
    assert old.observed_year_equivalents == pytest.approx(731/365.25, abs=1e-6)
    other = result[result.country == 'B'].iloc[0]
    assert other.years_with_stops_in_country == 1
    assert other.observed_calendar_years == 2
    assert other.stop_hours_per_observed_year == round(100/(731/365.25), 2)
    assert result.total_stop_hours.sum() == annual.total_stop_hours.sum()


def test_partial_year_and_longest_stop_metadata():
    a = row('v', 2025, 100)
    b = row('v', 2026, 200, end='2026-09-01')
    b.update(ship_name='renamed', longest_stop_hours=50, longest_stop_lat=7)
    annual = pd.DataFrame([a, b])
    observed = pd.DataFrame({'vessel_id': ['v', 'v'], 'year': [2025, 2026]})
    r = collapse_country_years(annual, observed).iloc[0]
    assert r.observed_period_days == 365+243
    assert r.stop_hours_per_observed_year == round(300/((365+243)/365.25), 2)
    assert r.ship_name == 'renamed'
    assert r.longest_stop_lat == 7
    assert r.max_annual_distinct_locations == 2  # yearly cluster IDs cannot be summed


def test_missing_observation_membership_is_rejected():
    with pytest.raises(ValueError, match='Missing observed-year'):
        collapse_country_years(pd.DataFrame([row('v', 2020, 10)]),
                               pd.DataFrame({'vessel_id': ['other'], 'year': [2020]}))
