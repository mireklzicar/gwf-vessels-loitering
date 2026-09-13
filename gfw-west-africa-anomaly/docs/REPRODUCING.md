# Reproducing the v0.2.0 datasets

The committed release files cover 2019-01-01 through 2026-08-31 UTC. The full
pipeline, frozen query and maritime GeoJSONs, configuration, tests, aggregation,
and Parquet export scripts are included in the repository. You do not need API
credentials to read or verify the released Parquet files.

## Read and verify the release

From the repository root:

```bash
cd gfw-west-africa-anomaly
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements-release.txt
pip install --no-deps -e .
```

Verify checksums from their directory:

```bash
(cd outputs && shasum -a 256 -c SHA256SUMS)
python - <<'PY'
import pandas as pd
annual = pd.read_parquet('outputs/vessel_loitering_hours_by_country_year.parquet')
collapsed = pd.read_parquet('outputs/vessel_loitering_hours_by_country_all_years.parquet')
print(annual.groupby('year').size())
print(collapsed[['ship_name', 'country', 'stop_hours_per_observed_year']].head(20))
PY
```

`requirements-release.txt` records the Python packages installed for this release
(Python 3.13 on macOS). It is an environment snapshot, not a promise of identical
binary results on every platform. For a standard installation with dependency
resolution instead, use `pip install -e '.[dev]'`.

## Download and analyze all periods

Obtain a GFW API token and set `GFW_API_TOKEN` in the environment. Never commit
resolved credentials. `.env.example` documents both a token placeholder and the
1Password secret-reference option used for this run. The CLI reads the environment;
it does not automatically load `.env`.

```bash
gfw-anomaly annual-loitering --start-year 2019 --end-date 2026-09-01
```

Alternatively, with 1Password CLI and the reference in `.env`:

```bash
op run --env-file=.env -- .venv/bin/gfw-anomaly annual-loitering \
  --start-year 2019 --end-date 2026-09-01
```

The default region and maritime boundaries are the checked-in GeoJSONs. Keep the
frozen boundary file for this release; `scripts/fetch_maritime_boundaries.py`
refreshes it from the live WFS and therefore changes the input snapshot.

Raw JSON is cached in `annual_run/<configuration-hash>/<year>/data/raw/`;
processed Parquet, annual CSVs and a combined CSV are written in the same run tree.
The command prints the run directory. With the checked-in inputs, the release run
is `annual_run/3b6264c81a14053b`. Downloading is sequential to respect the report
API's concurrency limit. Event requests retry transient failures up to five
attempts. Rerunning uses complete cached chunks and replaces each processed year
in the combined table without deleting other years. Plan for several hours and
tens of gigabytes of working storage. Current-year data are requested only through
a completed month; the end date is exclusive.

The original run used full years 2019–2025 and then extended through August 2026.
The single command above expresses the same final date coverage. Original source
rows came from GFW's `:latest` aliases; neither API snapshots nor original raw
caches are included in Git. Fresh API data and dependency changes can alter
results. The release manifest freezes the query/configuration and input boundary
checksum, while the checksums identify the exact published artifacts.

## Collapse and export

After the annual pipeline has completed:

```bash
python scripts/collapse_loitering.py annual_run/3b6264c81a14053b
python scripts/export_release.py annual_run/3b6264c81a14053b --output-dir outputs
```

Use the printed hash if you intentionally changed the configuration or boundaries.
The collapse step reads the annual CSV and per-year `presence.parquet` files to
count every vessel's regionally observed years, including years with no detected
stop in a particular country. Those exposure denominators cannot be recovered
from the annual stop CSV alone. It then sums country/vessel hours and ranks by
hours per observed 365.25-day equivalent year. See `DATA_DICTIONARY.md` for the
formula, limitations and every column.

The export step verifies grouping keys, annual/collapsed totals, normalized rates,
window labels, sort order and full typed Parquet round trips. It writes the two
Parquet files, `release_manifest.json` and `SHA256SUMS` to the selected directory.
It performs no fresh API calls.

To repeat the broader CSV/Parquet compression comparison (optional):

```bash
python scripts/compress_loitering.py annual_run/3b6264c81a14053b/outputs
```

## Reanalyze cached raw JSON

With the original raw cache still in place, rerun `annual-loitering` with the same
inputs to reconstruct processed data without fetching cached chunks again. To
reanalyze an already processed year directly:

```bash
gfw-anomaly analyze --root annual_run/3b6264c81a14053b/2020
gfw-anomaly loitering-breakdown --root annual_run/3b6264c81a14053b/2020
```

`loitering-breakdown` infers its window from the observed data. Use the annual
command for the release's explicit calendar-window denominators and combined file.

## Tests

```bash
pytest -q
```

Tests cover stop/scoring logic, year clipping and leap years, joint maritime
assignment, event retry pagination, appending a partial year, preserving existing
results, observation-normalized ranking and exposure validation.
