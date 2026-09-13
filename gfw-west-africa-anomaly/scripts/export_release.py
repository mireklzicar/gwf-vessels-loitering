"""Export and verify the two curated release Parquet datasets from a completed run."""
import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.csv as csv
import pyarrow.parquet as pq

from gfw_anomaly.gfw import EVENT_DATASETS

NAMES = ['vessel_loitering_hours_by_country_year',
         'vessel_loitering_hours_by_country_all_years']
IDENTIFIERS = ['imo', 'mmsi', 'callsign', 'vessel_id', 'ship_name', 'flag',
               'vessel_type', 'geartype', 'ship_names_seen', 'flags_seen']


def read_csv(path):
    table = csv.read_csv(path, convert_options=csv.ConvertOptions(
        column_types={c: pa.string() for c in IDENTIFIERS},
        null_values=[''], strings_can_be_null=False))
    return table.cast(pa.schema([
        pa.field(f.name, pa.timestamp('us', tz=f.type.tz))
        if pa.types.is_timestamp(f.type) else f for f in table.schema]))


def validate(annual, collapsed):
    keys = ['country', 'vessel_id']
    if annual.duplicated(keys + ['year']).any() or collapsed.duplicated(keys).any():
        raise ValueError('Duplicate dataset keys')
    annual_totals = annual.groupby(keys)[['total_stop_hours', 'offshore_stop_hours',
                                         'gfw_loitering_hours']].sum().sort_index()
    collapsed_totals = collapsed.set_index(keys)[annual_totals.columns].sort_index()
    pd.testing.assert_frame_equal(annual_totals, collapsed_totals, check_dtype=False,
                                  check_exact=False, atol=1e-6, rtol=0)
    if not collapsed.stop_hours_per_observed_year.is_monotonic_decreasing:
        raise ValueError('Normalized ranking is not descending')
    for year, group in annual.groupby('year'):
        if not group.window_start.eq(pd.Timestamp(f'{year}-01-01', tz='UTC')).all():
            raise ValueError('Unexpected annual window start')
        if group.window_end.nunique() != 1:
            raise ValueError('Inconsistent annual window end')
        expected_full = group.window_end.iloc[0] == pd.Timestamp(f'{year+1}-01-01', tz='UTC')
        if not group.complete_calendar_year.eq(expected_full).all():
            raise ValueError('Incorrect complete-calendar-year label')
    if (collapsed.observed_year_equivalents <= 0).any():
        raise ValueError('Invalid normalization denominator')
    expected = (collapsed.total_stop_hours / (collapsed.observed_period_days / 365.25)).round(2)
    if not expected.sub(collapsed.stop_hours_per_observed_year).abs().lt(0.011).all():
        raise ValueError('Incorrect normalized rate')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_root', type=Path)
    parser.add_argument('--output-dir', type=Path, default=Path('outputs'))
    args = parser.parse_args()
    source_dir = args.run_root / 'outputs'
    source_manifest = json.loads((source_dir / 'manifest.json').read_text())
    tables = {name: read_csv(source_dir / f'{name}.csv') for name in NAMES}
    validate(*(tables[name].to_pandas() for name in NAMES))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for name, table in tables.items():
        dest = args.output_dir / f'{name}.parquet'
        pq.write_table(table, dest, compression='brotli', compression_level=11,
                       version='2.6', row_group_size=len(table),
                       dictionary_pagesize_limit=8*1024*1024)
        if not table.equals(pq.read_table(dest)):
            raise ValueError(f'Parquet round-trip failed: {dest}')
        files.append(dict(file=dest.name, rows=len(table), columns=table.num_columns,
                          bytes=dest.stat().st_size,
                          sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),
                          source_csv_sha256=hashlib.sha256(
                              (source_dir / f'{name}.csv').read_bytes()).hexdigest()))
        print(f'Verified {len(table):,} rows: {dest}', flush=True)
    manifest = dict(release='v0.2.0', window_start='2019-01-01',
                    window_end_exclusive='2026-09-01',
                    completed_years=source_manifest['completed_years'],
                    partial_year=source_manifest.get('partial_year'),
                    config=source_manifest['config'], event_datasets=EVENT_DATASETS,
                    boundaries='config/presets/west_africa_maritime.geojson',
                    boundary_sha256=source_manifest['boundary_sha256'],
                    query_geometry=source_manifest['geometry'],
                    source_snapshot='Fetched 2026-09-12 through 2026-09-13 UTC',
                    reproduction='API latest aliases may change; retain raw caches for exact source replay.',
                    parquet=dict(version='2.6', compression='BROTLI', compression_level=11),
                    files=files)
    (args.output_dir / 'release_manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    (args.output_dir / 'SHA256SUMS').write_text(''.join(
        f"{f['sha256']}  {f['file']}\n" for f in files))


if __name__ == '__main__':
    main()
