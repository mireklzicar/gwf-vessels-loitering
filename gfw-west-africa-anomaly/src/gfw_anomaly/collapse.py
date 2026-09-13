"""Combine country/year results, normalized by years represented in regional data."""
from pathlib import Path

import duckdb
import pandas as pd


IDENTITY = ['ship_name', 'flag', 'vessel_type', 'geartype', 'imo', 'mmsi', 'callsign']


def observed_vessel_years(run_root: Path, years) -> pd.DataFrame:
    frames = []
    with duckdb.connect() as db:
        for year in sorted(years):
            path = run_root / str(year) / 'data/processed/presence.parquet'
            frame = db.execute('SELECT DISTINCT vessel_id FROM read_parquet(?) '
                               'WHERE vessel_id IS NOT NULL', [str(path)]).df()
            frame['year'] = year
            frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def collapse_country_years(annual: pd.DataFrame, observed: pd.DataFrame) -> pd.DataFrame:
    """One row per vessel/country; use full sampled-year windows, not stop spans.

    The denominator counts each year in which the vessel has any low-speed
    presence anywhere in the study region, including years with no country stop.
    Partial-year windows count proportionally. One equivalent year = 365.25 days.
    This is an annualized detection rate, not a fraction of observed AIS hours.
    """
    x = annual.copy()
    keys = ['country', 'vessel_id']
    if x.duplicated(keys + ['year']).any():
        raise ValueError('Duplicate vessel/country/year rows')
    windows = x[['year', 'window_start', 'window_end']].drop_duplicates()
    if windows.year.duplicated().any():
        raise ValueError('Conflicting windows within a year')
    windows['days'] = (pd.to_datetime(windows.window_end, utc=True) -
                       pd.to_datetime(windows.window_start, utc=True)).dt.total_seconds()/86400
    if (windows.days <= 0).any():
        raise ValueError('Invalid observation window')
    obs = observed[['vessel_id', 'year']].drop_duplicates().merge(windows, on='year')
    membership = x[['vessel_id', 'year']].merge(obs[['vessel_id', 'year']],
                                              on=['vessel_id', 'year'], how='left', indicator=True)
    if membership['_merge'].ne('both').any():
        raise ValueError('Missing observed-year membership for a detected vessel')
    exposure = obs.groupby('vessel_id').agg(
        observed_calendar_years=('year', 'nunique'),
        observed_period_days=('days', 'sum'),
        first_observed_year=('year', 'min'), last_observed_year=('year', 'max'))
    exposure['observed_year_equivalents'] = exposure.observed_period_days / 365.25
    for col in ['first_seen', 'last_seen', 'longest_stop_start', 'longest_stop_end']:
        x[col] = pd.to_datetime(x[col], utc=True)
    sums = ['total_stop_hours', 'offshore_stop_hours', 'stop_episodes',
            'gfw_loitering_hours', 'nearby_encounters', 'nearby_gaps']
    result = x.groupby(keys)[sums].sum(min_count=1)
    extra = x.groupby(keys).agg(
        years_with_stops_in_country=('year', 'nunique'),
        first_stop=('first_seen', 'min'), last_stop=('last_seen', 'max'),
        max_annual_distinct_locations=('distinct_locations', 'max'),
        max_port_km=('max_port_km', 'max'),
        shared_location_max_vessels=('shared_location_max_vessels', 'max'),
        likely_fixed_installation_in_any_year=('likely_fixed_installation', 'any'),
        gfw_loitering_event_years=('gfw_loitering_events', 'sum'))
    result = result.join(extra).reset_index().merge(exposure, on='vessel_id', validate='many_to_one')
    # Metadata may change: most recent nonempty value; retain historical flags/names.
    identity = x.sort_values('year').groupby(keys)[IDENTITY].last().reset_index()
    result = result.merge(identity, on=keys, validate='one_to_one')
    history = x.groupby(keys).agg(
        ship_names_seen=('ship_name', lambda s: ' | '.join(sorted(set(s.dropna().astype(str))))),
        flags_seen=('flag', lambda s: ' | '.join(sorted(set(s.dropna().astype(str)))))).reset_index()
    result = result.merge(history, on=keys, validate='one_to_one')
    longest_cols = ['longest_stop_hours', 'longest_stop_lat', 'longest_stop_lon',
                    'longest_stop_start', 'longest_stop_end', 'longest_stop_port_km']
    longest = x.sort_values('longest_stop_hours', ascending=False).drop_duplicates(keys)
    result = result.merge(longest[keys + longest_cols], on=keys, validate='one_to_one')
    for source, name in [('total_stop_hours', 'stop_hours_per_observed_year'),
                         ('offshore_stop_hours', 'offshore_stop_hours_per_observed_year'),
                         ('gfw_loitering_hours', 'gfw_loitering_hours_per_observed_year')]:
        result[name] = (result[source] / result.observed_year_equivalents).round(2)
    result['offshore_share'] = (result.offshore_stop_hours / result.total_stop_hours).round(4)
    result['short_observation_history'] = result.observed_period_days < 365
    result['window_start'] = pd.to_datetime(windows.window_start, utc=True).min()
    result['window_end'] = pd.to_datetime(windows.window_end, utc=True).max()
    result['normalization_basis'] = 'regional low-speed-presence years; 365.25-day equivalent'
    result['observed_year_equivalents'] = result.observed_year_equivalents.round(6)
    result = result.sort_values(['stop_hours_per_observed_year',
                                  'offshore_stop_hours_per_observed_year', 'total_stop_hours'],
                                 ascending=False).reset_index(drop=True)
    result.insert(0, 'normalized_rank', range(1, len(result)+1))
    front = ['normalized_rank', 'country', *IDENTITY, 'vessel_id',
             'stop_hours_per_observed_year', 'offshore_stop_hours_per_observed_year',
             'total_stop_hours', 'offshore_stop_hours', 'observed_year_equivalents',
             'observed_calendar_years', 'years_with_stops_in_country',
             'short_observation_history']
    return result[front + [c for c in result if c not in front]]
