# GFW West Africa Anomaly Finder

## Released datasets (v0.2.0)

The first release covers **2019–August 2026**. Ready-to-use, verified Parquet files
are committed at [outputs/](outputs/): the annual country table (104,386 rows) and
the normalized all-years country table (62,057 rows). See the
[column dictionary](docs/DATA_DICTIONARY.md), [reproduction guide](docs/REPRODUCING.md),
[release manifest](outputs/release_manifest.json), and [repository overview](../README.md).
The rest of this README describes the underlying analysis pipeline and working CSVs.


A small investigative-analysis pipeline for finding **unusual offshore stationary vessel behavior** in [Global Fishing Watch](https://globalfishingwatch.org/our-apis/) data.

It is aimed at questions such as:

- Which vessels spend many hours/days nearly stationary offshore, away from empirical port/anchorage locations?
- Which offshore spots are repeatedly used by several vessels?
- Is one vessel acting like a long-lived "host" while other vessels visit the same location?
- Are AIS gap events or GFW encounter events concentrated around those stops?

The output is a ranked table of stop episodes, a ranked table of candidate stationary hosts, a DuckDB database, Parquet files, and an interactive HTML map.

> **Important:** this is a lead-generation tool, not an illegality classifier. A high anomaly score can have benign explanations (waiting for orders, weather, maintenance, bunkering, port congestion, anchorage behavior, AIS artifacts, etc.). Verify interesting cases independently before publication.

## Why this design

GFW's `public-global-presence:latest` product selects roughly one AIS position per vessel per hour and can be queried at HIGH (0.01-degree) spatial resolution. The pipeline requests the **`<2` knots speed bucket** (`filters[0]=speed = '<2'`; GFW stores presence speed as a bucket label, not a number), grouped by `VESSEL_ID`, and detects consecutive low-speed episodes itself. This intentionally catches near-shore stationary behavior that may fall outside GFW's own loitering-event definition.

It also downloads GFW event products for:

- loitering
- encounters
- AIS gaps
- port visits

Port-visit event positions are spatially deduplicated to create an **empirical local port/anchorage catalogue**. This avoids depending on a separate proprietary port database and is usually more useful than a tiny hand-maintained list of major ports.

GFW explicitly describes AIS Vessel Presence as a *presence* product rather than a canonical raw vessel track. Treat the reconstructed sequences here as an investigative approximation based on hourly gridded positions, not as raw AIS telemetry.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .

export GFW_API_TOKEN='YOUR_TOKEN'

gfw-anomaly all \
  --start 2026-01-01 \
  --end 2026-03-01 \
  --region config/presets/west_africa_core.geojson
```

Then open:

```text
outputs/suspicious_map.html
```

and inspect:

```text
outputs/suspicious_stops.csv
outputs/candidate_hosts.csv
data/processed/analysis.duckdb
```

For a first real run, **1-2 months** is a sensible test window before pulling years of data.

## No-token demo

The repo contains a synthetic scenario with a vessel that remains stationary offshore while three other vessels visit its location and gap/encounter events occur nearby.

```bash
gfw-anomaly demo
open demo_run/outputs/suspicious_map.html   # macOS
```

This exercises the whole analysis pipeline without calling GFW.

## Commands

### Fetch only

```bash
gfw-anomaly fetch \
  --start 2026-01-01 \
  --end 2026-02-01 \
  --region config/presets/west_africa_core.geojson
```

Raw API JSON responses are cached under `data/raw/`. Re-running the same chunks reuses them rather than burning API quota.

### Analyze cached data

```bash
gfw-anomaly analyze
```

### Fetch + analyze

```bash
gfw-anomaly all --start 2026-01-01 --end 2026-02-01
```

## Region preset

`config/presets/west_africa_core.geojson` contains three deliberately broad coastal polygons covering roughly:

1. Senegal / Gambia / Guinea-Bissau
2. Guinea / Sierra Leone / Liberia
3. Côte d'Ivoire / Ghana / Togo / Benin

These are **analysis windows, not maritime-boundary definitions**. Replace the file with a tighter polygon or EEZ-derived geometry for a publication-grade investigation.

A useful workflow is to start broad, discover recurrent hotspots, then rerun much smaller polygons around those hotspots for longer periods.

## Detection logic

### 1. Low-speed hourly presence

The downloader asks GFW 4Wings Report for:

```text
dataset: public-global-presence:latest
spatial resolution: HIGH
temporal resolution: HOURLY
group by: VESSEL_ID
filter: speed = '<2'   # speed is a bucket label in this dataset
spatial aggregation: false
```

The date range is chunked sequentially because GFW normally permits only one concurrent report per token. A 504/524-style long-report timeout is recovered using `/v3/4wings/last-report`.

### 2. Stop episodes

Consecutive low-speed hourly cells are joined only if:

- time gap <= `2.25 h`
- spatial step <= `5 km`

An episode is retained by default when:

- duration >= `4 h`
- maximum radius around its median position <= `5 km`

All thresholds are in `config/default.yaml`.

### 3. Spatial clustering

Stop centroids are projected to local kilometre coordinates and clustered with **HDBSCAN**. If `hdbscan` is unavailable, the library code has a DBSCAN fallback, although the package normally installs HDBSCAN.

The resulting clusters answer a different question from vessel trajectories: **where do vessels repeatedly stop offshore?**

### 4. Port/anchorage suppression

GFW port-visit positions in the same region/time window are clustered into empirical port/anchorage points. Each stop gets `nearest_port_km`.

For a more stable catalogue on a serious investigation, fetch port visits over a longer period (e.g. a year) even if the target stop analysis covers only a month.

### 5. Event enrichment

For each custom stop, the pipeline counts nearby GFW:

- AIS gap events
- encounter events
- GFW loitering events

using both a spatial window and a temporal window.

### 6. Two rankings

`suspicious_stops.csv` ranks individual stationary episodes using a transparent heuristic combining:

- duration
- distance from inferred port/anchorage
- nearby gap events
- nearby encounter events
- number of vessels using the same stop cluster
- total stop-hours at that cluster

`candidate_hosts.csv` instead asks: **is there a vessel that accounts for many stationary hours at a recurrent offshore cluster while other vessels also use that location?** This is closer to the "stationary factory / mothership / offshore hub" hypothesis.

Scores are intentionally simple and inspectable. They are prioritization scores, not probabilities.

### 7. Cumulative loitering hours per vessel

`vessel_loitering_hours.csv` answers a different question from the two rankings above: **which vessels spent the most cumulative time stationary**, regardless of how many separate events that produced. One row per vessel with:

- `total_stop_hours` / `offshore_stop_hours` (stops at least `ranking.offshore_km` from an inferred port)
- `longest_stop_hours` plus where/when that longest stop happened
- `distinct_locations` (a vessel parked at one spot all window looks like an installation; one that stops at many spots is moving around)
- `share_of_window` (1.0 = stationary for the entire analysis window)
- `gfw_loitering_hours` / `gfw_loitering_events` from GFW's own loitering-event product, clipped to the window
- `imo`, `mmsi`, `callsign` for registry look-ups

It is written by `analyze`/`all`, and can be regenerated from cached data with:

```bash
gfw-anomaly loitering-hours --top 50
```

## DuckDB examples

```bash
duckdb data/processed/analysis.duckdb
```

```sql
-- Highest-ranked stops at least 20 km from inferred ports
SELECT
  vessel_id, ship_name, vessel_type, start, end,
  duration_hours, nearest_port_km,
  nearby_gaps, nearby_encounters,
  cluster_unique_vessels, suspicion_score
FROM stops
WHERE nearest_port_km >= 20
ORDER BY suspicion_score DESC
LIMIT 50;
```

```sql
-- Candidate long-lived offshore hosts
SELECT *
FROM candidate_hosts
WHERE other_vessels >= 2
ORDER BY host_score DESC
LIMIT 50;
```

```sql
-- Offshore clusters that attract multiple vessels
SELECT
  cluster_id,
  count(*) AS stop_episodes,
  count(DISTINCT vessel_id) AS vessels,
  sum(duration_hours) AS stop_hours,
  median(nearest_port_km) AS median_port_km
FROM stops
WHERE cluster_id >= 0
GROUP BY cluster_id
HAVING vessels >= 3
ORDER BY stop_hours DESC;
```

## Suggested investigative workflow

Start with one or two months and inspect the map manually. For a hotspot that looks interesting:

1. rerun a tight polygon around it over 1-3 years;
2. inspect `candidate_hosts.csv` for persistent vessels;
3. query vessel identity/registry details in GFW;
4. inspect the vessel's port history and encounter partners;
5. compare AIS gaps before/after visits;
6. cross-check satellite imagery / SAR where available;
7. verify against known anchorages, offshore infrastructure, weather, and legitimate shipping operations;
8. only then treat it as a reporting lead.

A useful next extension is an unmatched-SAR layer using `public-global-sar-presence:latest` with `matched='false'`; the GFW API supports this directly. It is deliberately not mixed into the v0.1 score because SAR coverage is intermittent and absence of a detection is not evidence of absence.

## Data volume / API notes

- Keep report requests **sequential**; GFW documents a one-concurrent-report limit for normal tokens.
- The report endpoint may exceed the gateway timeout; the code polls `last-report` in that case.
- Responses are cached as JSON before conversion to Parquet.
- HIGH spatial resolution is approximately a 0.01-degree grid. That places a hard floor on how precisely "stationary" can be inferred from this product.
- GFW AIS data has reception, identity, spoofing/noise, and coverage caveats. Read GFW's current dataset caveats before publication.

## Project layout

```text
config/default.yaml
config/presets/west_africa_core.geojson
src/gfw_anomaly/
  gfw.py          # API downloader + cache flattening
  stops.py        # custom stop segmentation
  clustering.py   # HDBSCAN hotspot discovery
  enrich.py       # inferred ports + event matching
  scoring.py      # transparent ranking heuristics
  mapviz.py       # Folium investigative map
  storage.py      # Parquet + DuckDB
  pipeline.py     # orchestration
  demo.py         # synthetic validation scenario
  cli.py
tests/
```

## Tests

```bash
pip install -e '.[dev]'
pytest -q
```

## Current GFW API assumptions

The code targets GFW API v3 and the API behavior documented in September 2026:

- `public-global-presence:latest`
- 4Wings `/v3/4wings/report`
- `/v3/4wings/last-report`
- `/v3/events`
- event datasets using the `:latest` aliases

GFW changes datasets/API versions over time; `:latest` is intentional, but if a response schema changes, the cached raw JSON makes debugging/reprocessing possible without redownloading everything.

## Ethics / publication caution

Do not label a vessel, crew, company, or country as criminal because it ranks highly here. The model is explicitly optimized to surface **unusual behavior worth checking**. For journalism, preserve the raw query parameters, API responses, timestamps, and manual verification notes for every published case.

## Ground-truth validation: Josef Skrdlik fishmeal-factory case

A good way to evaluate the detector is to check whether it rediscovers already-investigated vessels rather than judging only synthetic examples.

The built-in `validate-josef` command uses IMO numbers (more stable than names/MMSIs) to resolve these two reported floating fishmeal factories through the GFW Vessels API:

- `TIAN YI HE 6` — IMO `8698633`
- `HUA XIN 17` — IMO `1049962`

After running `gfw-anomaly all ...`, run:

```bash
gfw-anomaly validate-josef
```

It writes `outputs/validation_josef_fishmeal.csv` and reports, for each known vessel:

- whether it existed in the downloaded GFW presence rows;
- number and total hours of custom stop episodes;
- best stop anomaly score and global rank/percentile;
- whether it qualified as a recurrent offshore host;
- best host score and global rank/percentile.

You can inspect any other known vessel with:

```bash
gfw-anomaly validate-vessel 8698633
gfw-anomaly validate-vessel 1049962
# names/MMSIs also work, but IMO is preferable when available
gfw-anomaly validate-vessel "TIAN YI HE 6"
```

Interpret a failed validation stage-by-stage. `presence_rows=0` means the vessel was not represented in this downloaded AIS-presence window/geometry (or identity resolution missed it), not that the detector judged it normal. Presence but `stop_episodes=0` indicates the stop thresholds/filter are the likely issue. Stops but no host row means the recurrent-location/HDBSCAN or host thresholds filtered it out. A host row with a weak percentile means ranking features/weights need work.

## Country and calendar-year loitering tables

```bash
# Reuse the existing analysis (labels its actual observed window):
gfw-anomaly loitering-breakdown

# Download complete years, with the 1Password reference in .env:
op run --env-file=.env -- .venv/bin/gfw-anomaly annual-loitering \
  --start-year 2019 --end-year 2025
```

The first command writes `outputs/vessel_loitering_hours_by_country_year.csv`
and a CSV per year. The annual command writes the combined table under
`annual_run/<configuration-hash>/outputs/`, plus each year's original analysis
and country table under `<year>/outputs/`. Downloads run sequentially and raw
chunks are reused on restart. The manifest records completed years; an interrupted
run's combined table contains only the years completed so far. Annual runs have
separate caches keyed by geometry, configuration and boundary content and do not
overwrite the original analysis. The default end year is the last completed UTC
year. To include a partial final year, use `--end-date` instead of `--end-year`;
the date is an exclusive completed-month boundary. For example, `--end-date
2026-09-01` includes data through 31 August 2026 and marks 2026 as partial.
Extending a run preserves previous years in the combined CSV.

Country means the maritime area containing the stop's median location, **not the
vessel flag**. Boundaries in `config/presets/west_africa_maritime.geojson` come
from the [Marine Regions WFS](https://www.marineregions.org/webservices.php),
clipped to the union of the original preset. Refresh them with
`python scripts/fetch_maritime_boundaries.py`. Source query, retrieval time and
original attributes are embedded in the GeoJSON. This is a static boundary
snapshot applied to every year, not a reconstruction of historical boundaries.
The broad preset includes some additional countries. Joint or overlapping areas
use a combined country label; unmatched points use `Unassigned` (which can include
high seas, land/grid artefacts or boundary gaps). No nearest-country guess is made.

Each row is one vessel/country/year, with the original loitering metrics.
Detected episodes crossing New Year are clipped, including their final hourly
cell. `share_of_window` uses the explicit analysis interval (8,784 hours in a
full leap year). `complete_calendar_year` describes the requested time interval,
not a guarantee of uninterrupted AIS reception. Cached data's first/last observed
hours supply its interval, so the existing June–July 2026 data remains partial.
GFW loitering events are deduplicated, clipped and assigned independently using
their representative position; their geography is an approximation too. As in
the original report, only vessels with detected custom stops appear. Within each
country/year, a vessel must have a detected stop there to receive a row; event-only
country/year pairs are omitted, so GFW event totals need not sum to the regional
report.
Stop locations and enrichment counts describe the parent stop; a cross-year
stop can therefore contribute to event counts in both years. Country allocation
is by whole stop centroid, not hour-by-hour border crossing. Annual detection
runs independently per year, so episodes at the year edge must meet the stop
threshold within that year's data.

For a long backfill that continues independently of the terminal:

```bash
op run --env-file=.env -- .venv/bin/python scripts/run_annual_background.py \
  --start-year 2019 --end-year 2025
```

Follow `annual_run/download.log`; `annual_run/status.json` records the worker PID
and `running`, `completed` or `failed` status. The machine must remain running.
A failed run can be relaunched with the same command to reuse cached chunks.

To queue January–August 2026 after an already-running 2019–2025 backfill:

```bash
op run --env-file=.env -- .venv/bin/python scripts/run_annual_background.py \
  --after-current --start-year 2026 --end-date 2026-09-01
```

The extension waits for the original worker to complete successfully, then appends
the 2026 result to the same combined table. Its status is in
`annual_run/extension_status.json`, and it uses the same `download.log`.

## All-years country totals and normalized ranking

```bash
python scripts/collapse_loitering.py annual_run/3b6264c81a14053b
```

This writes `outputs/vessel_loitering_hours_by_country_all_years.csv` within that
run. It contains one row per GFW vessel ID and maritime country, summed over
2019–August 2026, sorted by `stop_hours_per_observed_year` descending. An offshore
version of the rate is also included as `offshore_stop_hours_per_observed_year`.

The normalized rate is total detected stop hours in that country divided by
`observed_year_equivalents`. The denominator sums the sampled calendar-window days
for every year in which that vessel has any low-speed presence anywhere in the
study region, then divides by 365.25. Full years contribute 365 or 366 days;
January–August 2026 contributes 243 days. Years with regional presence but no
stops in that country still count. Missing years with no regional low-speed
presence do not count. A full year counts even if the vessel was detected for
only a short visit, avoiding annualizing a few stationary hours into a whole year.
This is an annualized regional detection rate, not vessel age, a percentage of
time at sea, or a rate conditional on time spent in the country's waters. The
input has already been filtered to speeds below 2 knots; it cannot establish
complete AIS exposure. Rates remain sensitive to AIS coverage and vessel-ID changes.

`observed_calendar_years`, `observed_period_days`, `observed_year_equivalents`
and `years_with_stops_in_country` make the denominator inspectable.
`short_observation_history` flags fewer than 365 sampled-window days. Fixed
installations can still rank highly: `likely_fixed_installation_in_any_year`
retains the annual indicator for filtering. Names/flags use the latest nonempty
annual value, with historical names/flags preserved. Different GFW IDs are not
merged based on names or IMO alone.

Stop and event hours are additive and reconcile with the source annual CSV.
The longest stop retains that episode's coordinates and dates (annual detection
can split an episode at New Year). `gfw_loitering_event_years` sums annual event
counts and can count a cross-year event more than once. Annual cluster IDs are
not comparable: `max_annual_distinct_locations` is the maximum annual count,
not a claimed count of unique locations over all years. Annual medians and
shares are not naively summed or averaged.
