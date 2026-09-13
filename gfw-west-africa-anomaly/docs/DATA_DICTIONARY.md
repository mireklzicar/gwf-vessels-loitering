# Release v0.2.0: dataset and column guide

Coverage: **2019-01-01 inclusive to 2026-09-01 exclusive (UTC)**. Full years
2019–2025 and January–August 2026. The annual table has **104,386 rows and 36
columns**; the collapsed table has **62,057 rows and 45 columns**. Both represent
24,761 distinct GFW vessel IDs, not necessarily that many physical ships.

## Files and interpretation

- `vessel_loitering_hours_by_country_year.parquet`: one row per `country`,
  `vessel_id`, `year`. Retains country/year order and the original annual rankings.
- `vessel_loitering_hours_by_country_all_years.parquet`: one row per `country`,
  `vessel_id`, sorted by normalized custom stop hours per observed year.

The preset is a union of broad search rectangles, not national borders. A frozen
Marine Regions maritime-boundary snapshot assigns stops by median location and
GFW loitering events by representative position. Joint/overlapping areas retain
combined labels. `Unassigned` may include high seas, coastline/grid artefacts and
boundary gaps; do not interpret it exclusively as high seas. Boundaries are static
across all years. Vessel flags are a separate attribute.

Only country/year pairs with detected custom stops receive rows. GFW event-only
pairs are omitted, so GFW event totals need not match a separate regional report.
Cross-year stop detection is independent; allowed gaps are counted in estimated
stop durations. The final hourly stop cell is included. Inferred ports and clusters
are rebuilt per year. This is a lead-generation dataset, not evidence of illegality.

## Normalized metric

`stop_hours_per_observed_year = total_stop_hours / (observed_period_days / 365.25)`

A year contributes its entire requested window if the vessel has **any** low-speed
presence anywhere in the study region. Full years contribute 365/366 days; 2026
contributes 243 days. A regionally observed year with no stops in a particular
country still contributes to that country's denominator. A year with no regional
low-speed presence contributes nothing. All country rows for an ID share this
denominator. This prevents a long detected history alone from dominating ranking,
without extrapolating a short stop into a full year of continuous loitering.

This is an **annualized detection rate**, not vessel age, percentage of time at sea,
or loitering conditional on hours spent in national waters. The downloaded presence
is already filtered to speeds below 2 knots, and cannot establish complete AIS
exposure. A short visit can still cause a full sampled year to count. AIS reception,
missing years, changing vessel IDs and differences in regional activity affect rates.
Fixed installations can rank highly; use the supplied heuristic flag when relevant.

## Storage

Parquet 2.6, Brotli level 11, dictionaries and one row group per file. Dates are
UTC microsecond timestamps. Numbers are stored as integers or float64; identifiers
remain strings (including inherited textual suffixes). Empty numeric CSV fields
become nulls; empty string fields remain empty strings. No rows/columns were
removed or reordered and no additional numerical rounding was introduced during
Parquet export. All stored values were compared with their typed CSV inputs.

## Annual columns

| Column | Parquet / Arrow type | Meaning |
|---|---|---|
| `country` | `string` | Maritime area containing the stop centroid. Independent of vessel flag. Joint areas retain combined names; Unassigned is retained. |
| `year` | `int64` | UTC calendar year; 2026 covers January–August only. |
| `ship_name` | `string` | Reported ship name. Annual: first nonempty regional presence value in the year. Collapsed: latest nonempty annual value for this vessel/country. |
| `flag` | `string` | Reported vessel flag, not coastal country. Selected like ship_name. |
| `vessel_type` | `string` | GFW vessel-type label. Selected like ship_name. |
| `geartype` | `string` | GFW gear-type label. Selected like ship_name. |
| `imo` | `string` | Reported IMO identifier, stored as a string. Empty means unavailable. Inherited decimal suffixes, if present in CSV, are preserved. |
| `mmsi` | `string` | Reported MMSI identifier, stored as a string; not the grouping key. Empty means unavailable. Inherited decimal suffixes are preserved. |
| `callsign` | `string` | Reported callsign, stored as a string; empty means unavailable. |
| `vessel_id` | `string` | GFW vessel ID; the grouping key. Different IDs are not merged by name, IMO or MMSI, so rows need not represent distinct physical ships. |
| `stop_episodes` | `int64` | Number of detected custom stop episodes. Collapsed: sum of annual counts; detection is independent per year. |
| `total_stop_hours` | `double` | Estimated cumulative custom stop hours, including allowed gaps between low-speed hourly positions. Minimum stop duration 4 hours; maximum gap 2.25 hours; maximum step and radius 5 km. Collapsed: sum across years. |
| `offshore_stop_hours` | `double` | Estimated stop hours at least 20 km from an inferred port/anchorage, summed across years in collapsed data. Unknown port distances are treated as offshore by the original implementation. |
| `longest_stop_hours` | `double` | Duration in hours of the longest retained stop in the row. Collapsed: maximum annual longest stop, not a reconstructed cross-year episode. |
| `distinct_locations` | `int64` | Annual distinct location keys: regional stop cluster IDs, with rounded 0.1-degree cells for noise stops. Not a count of exact physical facilities. |
| `median_port_km` | `double` | Median stop-centroid distance to the nearest inferred port/anchorage, in km, across stop episodes (not duration-weighted). |
| `max_port_km` | `double` | Maximum stop-centroid distance to the nearest inferred port/anchorage, in km. |
| `first_seen` | `timestamp[us, tz=UTC]` | Start of the first detected stop in this country/year, not first AIS observation. |
| `last_seen` | `timestamp[us, tz=UTC]` | Last hourly cell of the last detected stop in this country/year, not last AIS observation. |
| `nearby_encounters` | `int64` | Sum of encounter matches near custom stops (20 km and 24-hour matching windows). An event can match several stops; not necessarily unique encounters. |
| `nearby_gaps` | `int64` | Sum of AIS-gap matches near custom stops, with the same matching windows. Not necessarily unique events. |
| `shared_location_max_vessels` | `double` | Maximum regional cluster vessel count among this row’s stops; collapsed: maximum annual value. Regional clusters are recomputed each year. |
| `longest_stop_lat` | `double` | Latitude of the longest stop centroid, decimal degrees (WGS84). |
| `longest_stop_lon` | `double` | Longitude of the longest stop centroid, decimal degrees (WGS84). |
| `longest_stop_start` | `timestamp[us, tz=UTC]` | Start of the longest retained stop (UTC). |
| `longest_stop_end` | `timestamp[us, tz=UTC]` | Last hourly cell of the longest retained stop (UTC), not an exclusive interval end. |
| `longest_stop_port_km` | `double` | Nearest inferred port/anchorage distance for the longest stop, in km. |
| `share_of_window` | `double` | Total custom stop hours divided by the full requested annual window hours, rounded to three decimals. Does not adjust for vessel-specific observation history. |
| `offshore_share` | `double` | Offshore custom stop hours / all custom stop hours. Annual rounded to three decimals; collapsed recomputed from summed hours and rounded to four. |
| `likely_fixed_installation` | `bool` | Annual heuristic: share_of_window >= 0.95 and distinct_locations == 1. An investigative filter, not a confirmed vessel classification. |
| `gfw_loitering_events` | `int64` | GFW loitering events overlapping the country/year window, deduplicated by event ID within the year. An event crossing New Year can occur in more than one annual row. |
| `gfw_loitering_hours` | `double` | GFW loitering-event durations clipped to the requested window, allocated by representative event position. Distinct from custom stop hours. Collapsed: sum of annual hours. |
| `window_start` | `timestamp[us, tz=UTC]` | Inclusive UTC start of the analysis period: 1 January of the row’s year, or 2019-01-01 for collapsed rows. |
| `window_end` | `timestamp[us, tz=UTC]` | Exclusive UTC end of the analysis period: next 1 January for full years, 2026-09-01 for 2026 and collapsed rows. |
| `complete_calendar_year` | `bool` | True for 2019–2025; false for January–August 2026. Describes the requested interval, not uninterrupted AIS coverage. |
| `country_assignment` | `string` | Text describing the allocation method: stop centroid / event representative position. |

## Collapsed columns

| Column | Parquet / Arrow type | Meaning |
|---|---|---|
| `normalized_rank` | `int64` | One-based global row ordering, descending by stop_hours_per_observed_year, then offshore normalized rate and total hours. Not a criminality/anomaly score. |
| `country` | `string` | Maritime area containing the stop centroid. Independent of vessel flag. Joint areas retain combined names; Unassigned is retained. |
| `ship_name` | `string` | Reported ship name. Annual: first nonempty regional presence value in the year. Collapsed: latest nonempty annual value for this vessel/country. |
| `flag` | `string` | Reported vessel flag, not coastal country. Selected like ship_name. |
| `vessel_type` | `string` | GFW vessel-type label. Selected like ship_name. |
| `geartype` | `string` | GFW gear-type label. Selected like ship_name. |
| `imo` | `string` | Reported IMO identifier, stored as a string. Empty means unavailable. Inherited decimal suffixes, if present in CSV, are preserved. |
| `mmsi` | `string` | Reported MMSI identifier, stored as a string; not the grouping key. Empty means unavailable. Inherited decimal suffixes are preserved. |
| `callsign` | `string` | Reported callsign, stored as a string; empty means unavailable. |
| `vessel_id` | `string` | GFW vessel ID; the grouping key. Different IDs are not merged by name, IMO or MMSI, so rows need not represent distinct physical ships. |
| `stop_hours_per_observed_year` | `double` | Total custom stop hours in this country / observed_year_equivalents, rounded to two decimals. Default collapsed ranking. |
| `offshore_stop_hours_per_observed_year` | `double` | Offshore custom stop hours in this country / observed_year_equivalents, rounded to two decimals. |
| `total_stop_hours` | `double` | Estimated cumulative custom stop hours, including allowed gaps between low-speed hourly positions. Minimum stop duration 4 hours; maximum gap 2.25 hours; maximum step and radius 5 km. Collapsed: sum across years. |
| `offshore_stop_hours` | `double` | Estimated stop hours at least 20 km from an inferred port/anchorage, summed across years in collapsed data. Unknown port distances are treated as offshore by the original implementation. |
| `observed_year_equivalents` | `double` | Sum of requested window days for vessel-observed years / 365.25, displayed to six decimals. Rates use the unrounded denominator. |
| `observed_calendar_years` | `int64` | Number of years in which this GFW vessel ID has any low-speed presence anywhere in the study region, whether or not it stops in this country. |
| `years_with_stops_in_country` | `int64` | Number of annual rows contributing detected stops for this vessel/country. |
| `short_observation_history` | `bool` | True if observed_period_days < 365. Flags a short sampled-window history; does not measure the number of actual AIS observations. |
| `stop_episodes` | `int64` | Number of detected custom stop episodes. Collapsed: sum of annual counts; detection is independent per year. |
| `gfw_loitering_hours` | `double` | GFW loitering-event durations clipped to the requested window, allocated by representative event position. Distinct from custom stop hours. Collapsed: sum of annual hours. |
| `nearby_encounters` | `int64` | Sum of encounter matches near custom stops (20 km and 24-hour matching windows). An event can match several stops; not necessarily unique encounters. |
| `nearby_gaps` | `int64` | Sum of AIS-gap matches near custom stops, with the same matching windows. Not necessarily unique events. |
| `first_stop` | `timestamp[us, tz=UTC]` | Earliest annual first_seen for the vessel/country (UTC). |
| `last_stop` | `timestamp[us, tz=UTC]` | Latest annual last_seen for the vessel/country (UTC); last hourly cell, not exclusive end. |
| `max_annual_distinct_locations` | `int64` | Maximum annual distinct_locations. Annual cluster IDs cannot be combined into a defensible all-years distinct-location count. |
| `max_port_km` | `double` | Maximum stop-centroid distance to the nearest inferred port/anchorage, in km. |
| `shared_location_max_vessels` | `double` | Maximum regional cluster vessel count among this row’s stops; collapsed: maximum annual value. Regional clusters are recomputed each year. |
| `likely_fixed_installation_in_any_year` | `bool` | True if any contributing annual row had likely_fixed_installation = true. |
| `gfw_loitering_event_years` | `int64` | Sum of annual gfw_loitering_events. A cross-year event can be counted repeatedly; not a count of globally unique events. |
| `observed_period_days` | `double` | Denominator support: sum of sampled window days for every regionally observed vessel-year (365/366 for full years, 243 for Jan–Aug 2026). Not actual days at sea or AIS-covered days. |
| `first_observed_year` | `int64` | First year with low-speed presence for this ID anywhere in the study region. |
| `last_observed_year` | `int64` | Last year with low-speed presence for this ID anywhere in the study region. |
| `ship_names_seen` | `string` | Distinct nonempty ship_name values from contributing annual country rows, joined by a pipe. Not an exhaustive AIS name history. |
| `flags_seen` | `string` | Distinct nonempty flag values from contributing annual country rows, joined by a pipe. Not an exhaustive flag history. |
| `longest_stop_hours` | `double` | Duration in hours of the longest retained stop in the row. Collapsed: maximum annual longest stop, not a reconstructed cross-year episode. |
| `longest_stop_lat` | `double` | Latitude of the longest stop centroid, decimal degrees (WGS84). |
| `longest_stop_lon` | `double` | Longitude of the longest stop centroid, decimal degrees (WGS84). |
| `longest_stop_start` | `timestamp[us, tz=UTC]` | Start of the longest retained stop (UTC). |
| `longest_stop_end` | `timestamp[us, tz=UTC]` | Last hourly cell of the longest retained stop (UTC), not an exclusive interval end. |
| `longest_stop_port_km` | `double` | Nearest inferred port/anchorage distance for the longest stop, in km. |
| `gfw_loitering_hours_per_observed_year` | `double` | Summed GFW loitering hours in this country / observed_year_equivalents, rounded to two decimals. |
| `offshore_share` | `double` | Offshore custom stop hours / all custom stop hours. Annual rounded to three decimals; collapsed recomputed from summed hours and rounded to four. |
| `window_start` | `timestamp[us, tz=UTC]` | Inclusive UTC start of the analysis period: 1 January of the row’s year, or 2019-01-01 for collapsed rows. |
| `window_end` | `timestamp[us, tz=UTC]` | Exclusive UTC end of the analysis period: next 1 January for full years, 2026-09-01 for 2026 and collapsed rows. |
| `normalization_basis` | `string` | Text label: regional low-speed-presence years; 365.25-day equivalent. |

## Attribution and provenance

Presence and events: [Global Fishing Watch](https://globalfishingwatch.org/our-apis/),
queried on 12–13 September 2026 using the dataset aliases and parameters recorded
in `release_manifest.json`. Boundaries: Flanders Marine Institute,
[Marine Regions WFS](https://www.marineregions.org/webservices.php), retrieved
12 September 2026; query and original attributes are embedded in the checked-in
`config/presets/west_africa_maritime.geojson`. Code is MIT licensed; source data
remain subject to their providers' terms and attribution requirements.

The source aliases end in `:latest`; a fresh download can differ from this release.
Retain raw JSON caches for exact source replay. See `REPRODUCING.md` for commands,
the release manifest for configuration, and `SHA256SUMS` to verify downloads.
