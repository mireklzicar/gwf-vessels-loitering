# West Africa vessel loitering, 2019–August 2026

Country-level estimates of stationary vessel activity from Global Fishing Watch
(GFW) hourly low-speed presence and event data. The repository includes two
ready-to-use Parquet datasets, the frozen maritime boundaries, and the Python
pipeline used to produce them.

## Download the data

The [first release, v0.2.0](https://github.com/mireklzicar/gwf-vessels-loitering/releases/tag/v0.2.0)
contains both Parquet files, column documentation, reproduction instructions,
provenance and SHA-256 checksums. The files are also committed in the repository:

| Dataset | Rows | Size | Grain |
|---|---:|---:|---|
| [Annual Parquet](gfw-west-africa-anomaly/outputs/vessel_loitering_hours_by_country_year.parquet) | 104,386 | 4.80 MB | Vessel ID × maritime country × year |
| [All-years Parquet](gfw-west-africa-anomaly/outputs/vessel_loitering_hours_by_country_all_years.parquet) | 62,057 | 4.25 MB | Vessel ID × maritime country |

Coverage is **1 January 2019 through 31 August 2026**, UTC. Years 2019–2025 are
complete calendar windows; **2026 covers January–August** and is explicitly
labelled partial. Both files contain 24,761 distinct GFW vessel IDs, which are
not necessarily distinct physical ships. No columns or rows were dropped during
Parquet conversion. The two files total about 9.05 MB, versus 70.33 MB as CSV.

- [Every column, units, types and caveats](gfw-west-africa-anomaly/docs/DATA_DICTIONARY.md)
- [Reproduction and verification instructions](gfw-west-africa-anomaly/docs/REPRODUCING.md)
- [Query configuration and release provenance](gfw-west-africa-anomaly/outputs/release_manifest.json)
- [Checksums](gfw-west-africa-anomaly/outputs/SHA256SUMS)

## What the ranking means

`total_stop_hours` estimates cumulative hours in custom stationary episodes.
`offshore_stop_hours` retains episodes at least 20 km from inferred ports or
anchorages. The independent GFW loitering-event measures are also included.

The all-years file is sorted by **`stop_hours_per_observed_year`**, not lifetime
hours alone:

```text
stop_hours_per_observed_year = total_stop_hours / (observed_period_days / 365.25)
```

An observed year is a year in which the vessel has any low-speed presence anywhere
in the study region. Its whole requested window counts: 365/366 days for full
years or 243 days for January–August 2026. Regionally observed years with no stops
in a given country still count in that country's denominator. Years with no
regional low-speed presence do not count. The table exposes the denominator,
number of years, short-history flag, and an equivalent offshore rate.

This is an annualized detection rate, **not a percentage of time at sea**. Sparse
AIS coverage, short regional visits and changing vessel IDs can affect it. Fixed
installations may still rank highly; a heuristic flag is included for filtering.

Country means the maritime area containing a stop's centroid, independently of
vessel flag. [Marine Regions boundaries](gfw-west-africa-anomaly/config/presets/west_africa_maritime.geojson)
are clipped to the [original broad search region](gfw-west-africa-anomaly/config/presets/west_africa_core.geojson).
Joint areas retain combined labels. `Unassigned` is retained and is not necessarily
high seas. Boundaries are a static snapshot applied to all years. These are
investigative leads, not classifications of illegal activity.

## Use the files

```bash
cd gfw-west-africa-anomaly
python -m pip install pandas pyarrow
```

```python
import pandas as pd

annual = pd.read_parquet('outputs/vessel_loitering_hours_by_country_year.parquet')
collapsed = pd.read_parquet('outputs/vessel_loitering_hours_by_country_all_years.parquet')
print(collapsed[['ship_name', 'country', 'stop_hours_per_observed_year']].head(20))
```

## Reproduce the processing

The [detailed guide](gfw-west-africa-anomaly/docs/REPRODUCING.md) covers setup,
credentials, caching, versions and validation. With the project installed and
`GFW_API_TOKEN` set, run from `gfw-west-africa-anomaly/`:

```bash
gfw-anomaly annual-loitering --start-year 2019 --end-date 2026-09-01
python scripts/collapse_loitering.py annual_run/3b6264c81a14053b
python scripts/export_release.py annual_run/3b6264c81a14053b --output-dir outputs
pytest -q
```

Use the run directory printed by the command if you change inputs. A full fetch
takes hours; completed raw chunks are reused. GFW's `:latest` aliases can change,
so fresh downloads may differ from this frozen release. Raw JSON caches, working
CSVs, credentials and intermediate data are not committed.

The [pipeline README](gfw-west-africa-anomaly/README.md) documents stop detection,
clustering, inferred ports, event matching, maps and validation commands.

## Sources and license

Source activity data: [Global Fishing Watch](https://globalfishingwatch.org/our-apis/),
queried 12–13 September 2026. Maritime geometry: Flanders Marine Institute,
[Marine Regions WFS](https://www.marineregions.org/webservices.php), retrieved
12 September 2026; query and original attributes are embedded in the GeoJSON.
Code is [MIT licensed](gfw-west-africa-anomaly/LICENSE). Source data remain subject
to their providers' applicable terms, licenses and attribution requirements.
