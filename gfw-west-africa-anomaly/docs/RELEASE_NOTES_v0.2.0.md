# West Africa vessel loitering, 2019–August 2026

First published release of the data and reproducible Python processing pipeline.
Coverage: **2019-01-01 inclusive to 2026-09-01 exclusive, UTC**. Years 2019–2025
are complete calendar windows; 2026 is **January–August only**.

## Assets

| File | Rows | Columns | Size |
|---|---:|---:|---:|
| `vessel_loitering_hours_by_country_year.parquet` | 104,386 | 36 | 4.80 MB |
| `vessel_loitering_hours_by_country_all_years.parquet` | 62,057 | 45 | 4.25 MB |

Both datasets contain 24,761 distinct GFW vessel IDs. Parquet 2.6 uses Brotli
compression, typed numeric/boolean columns, UTC timestamps and string identifiers.
No columns or rows were removed during conversion. The files are also committed
under `gfw-west-africa-anomaly/outputs/`.

The attached **DATA_DICTIONARY.md** explains every column, unit, data type and
interpretation. **REPRODUCING.md** gives setup and processing commands.
**release_manifest.json** records the query configuration, boundary checksum,
source CSV hashes and artifact metadata. **SHA256SUMS** verifies the two Parquet
assets (`shasum -a 256 -c SHA256SUMS` from the download directory).

## Main measures

- `total_stop_hours`: cumulative detected stationary-episode hours.
- `offshore_stop_hours`: stop hours at least 20 km from inferred ports/anchorages.
- `gfw_loitering_hours`: separate GFW loitering-event hours clipped to the period.
- `stop_hours_per_observed_year`: the collapsed table's default ranking, total
  stop hours / (`observed_period_days` / 365.25).

The normalized denominator counts requested window days for every year with any
regional low-speed presence for the vessel, including years with no stops in a
particular country. It counts 243 days for January–August 2026. It is an annualized
detection rate, **not percentage of time at sea**. Observation-history fields,
a short-history flag, an offshore normalized rate and fixed-installation heuristic
help interpret the ranking. Different GFW IDs are not merged into physical ships.

## Geography and limitations

Countries refer to maritime areas containing stop centroids, not vessel flags.
The release includes the original regional GeoJSON and a frozen Marine Regions
maritime GeoJSON. Joint areas retain combined labels; `Unassigned` may include
high seas, coast/grid artefacts and boundary gaps. The same boundary snapshot is
used for all years. Only vessel/country/year pairs with detected custom stops
receive rows. These are investigative leads, not evidence of illegality.

Activity data: Global Fishing Watch, fetched 12–13 September 2026. Boundaries:
Flanders Marine Institute / Marine Regions WFS, retrieved 12 September 2026.
Provider terms and attribution requirements apply to data; the repository's MIT
license covers code. GFW `:latest` aliases can change, so a fresh fetch may differ
from this frozen snapshot. See the column guide for detailed methodological limits.

## Reproduction and checks

The tagged source contains the downloader, stop analysis, country/year allocation,
all-years normalization, Parquet exporter, tests, configuration, GeoJSONs and a
Python 3.13 package-version snapshot. Raw API caches and credentials are excluded.

All annual/collapsed custom and GFW loitering-hour totals reconcile by vessel and
country. Group keys, date windows, partial-year flags and normalized ordering were
verified; each Parquet file was compared with its complete typed CSV source.
