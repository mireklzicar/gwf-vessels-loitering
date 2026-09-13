"""Usage: python scripts/collapse_loitering.py annual_run/<configuration-hash>"""
import argparse
from pathlib import Path

import pandas as pd

from gfw_anomaly.collapse import collapse_country_years, observed_vessel_years

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('run_root', type=Path)
args = parser.parse_args()
root = args.run_root
annual = pd.read_csv(root / 'outputs/vessel_loitering_hours_by_country_year.csv',
                     dtype={c: 'string' for c in ['imo', 'mmsi', 'callsign', 'vessel_id']})
observed = observed_vessel_years(root, annual.year.unique())
result = collapse_country_years(annual, observed)
path = root / 'outputs/vessel_loitering_hours_by_country_all_years.csv'
result.to_csv(path, index=False)
print(f'Saved {len(result):,} vessel/country rows: {path}')
