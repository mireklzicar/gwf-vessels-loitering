from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import typer

from .config import load_config
from .demo import synthetic_presence, synthetic_events
from .duration import vessel_loitering_hours
from .gfw import GFWClient, fetch_all
from .pipeline import analyze
from .storage import write_parquet
from .utils import load_geojson_geometry
from .validation import JOSEF_FISHMEAL_CASE, resolve_gfw_vessel_ids, summarize_detection, validation_detail

app = typer.Typer(pretty_exceptions_show_locals=False, no_args_is_help=True, help="Find unusual offshore stationary-vessel patterns in GFW data.")


def _token(token: str | None) -> str:
    t = token or os.environ.get("GFW_API_TOKEN")
    if not t:
        raise typer.BadParameter("Pass --token or set GFW_API_TOKEN")
    return t


@app.command()
def fetch(
    start: str = typer.Option(..., help="Inclusive YYYY-MM-DD"),
    end: str = typer.Option(..., help="Exclusive YYYY-MM-DD"),
    region: Path = typer.Option(Path("config/presets/west_africa_core.geojson")),
    config: Path = typer.Option(Path("config/default.yaml")),
    token: str | None = typer.Option(None, envvar="GFW_API_TOKEN", help="GFW bearer token"),
    root: Path = typer.Option(Path(".")),
):
    """Download/cache hourly low-speed presence and GFW event enrichments."""
    cfg = load_config(config)
    geometry = load_geojson_geometry(region)
    c = GFWClient(
        token=_token(token),
        base_url=cfg["api"]["base_url"],
        timeout_seconds=cfg["api"]["timeout_seconds"],
        last_report_poll_seconds=cfg["api"]["last_report_poll_seconds"],
        last_report_max_polls=cfg["api"]["last_report_max_polls"],
    )
    presence, events = fetch_all(c, geometry, start, end, root / "data" / "raw", cfg)
    write_parquet(presence, root / "data" / "processed" / "presence.parquet")
    for kind, df in events.items():
        write_parquet(df, root / "data" / "processed" / f"events_{kind}.parquet")
    typer.echo(f"presence rows: {len(presence):,}")
    for k, v in events.items():
        typer.echo(f"{k}: {len(v):,}")


@app.command("analyze")
def analyze_cmd(
    config: Path = typer.Option(Path("config/default.yaml")),
    root: Path = typer.Option(Path(".")),
):
    """Analyze already-downloaded Parquet files."""
    cfg = load_config(config)
    pdir = root / "data" / "processed"
    presence = pd.read_parquet(pdir / "presence.parquet")
    events = {}
    for kind in ["loitering", "encounters", "gaps", "port_visits"]:
        p = pdir / f"events_{kind}.parquet"
        events[kind] = pd.read_parquet(p) if p.exists() else pd.DataFrame()
    scored, hosts = analyze(presence, events, cfg, root)
    typer.echo(f"stop episodes: {len(scored):,}")
    typer.echo(f"candidate hosts: {len(hosts):,}")
    typer.echo(f"map: {root / 'outputs' / 'suspicious_map.html'}")


@app.command()
def all(
    start: str = typer.Option(...),
    end: str = typer.Option(...),
    region: Path = typer.Option(Path("config/presets/west_africa_core.geojson")),
    config: Path = typer.Option(Path("config/default.yaml")),
    token: str | None = typer.Option(None, envvar="GFW_API_TOKEN"),
    root: Path = typer.Option(Path(".")),
):
    """Fetch then analyze in one command."""
    cfg = load_config(config)
    geometry = load_geojson_geometry(region)
    c = GFWClient(
        token=_token(token), base_url=cfg["api"]["base_url"],
        timeout_seconds=cfg["api"]["timeout_seconds"],
        last_report_poll_seconds=cfg["api"]["last_report_poll_seconds"],
        last_report_max_polls=cfg["api"]["last_report_max_polls"],
    )
    presence, events = fetch_all(c, geometry, start, end, root / "data" / "raw", cfg)
    scored, hosts = analyze(presence, events, cfg, root)
    typer.echo(f"Wrote {len(scored):,} ranked stops and {len(hosts):,} host candidates")


@app.command("loitering-hours")
def loitering_hours(
    config: Path = typer.Option(Path("config/default.yaml")),
    root: Path = typer.Option(Path(".")),
    top: int = typer.Option(25, help="Rows to print"),
):
    """Rank vessels by cumulative stationary hours (not event counts) from an existing analysis."""
    cfg = load_config(config)
    pdir = root / "data" / "processed"
    stops = pd.read_parquet(pdir / "stops_scored.parquet")
    presence = pd.read_parquet(pdir / "presence.parquet")
    lp = pdir / "events_loitering.parquet"
    loitering = pd.read_parquet(lp) if lp.exists() else None
    out = vessel_loitering_hours(stops, presence, loitering, cfg["ranking"].get("offshore_km", 20.0))
    write_parquet(out, pdir / "vessel_loitering_hours.parquet")
    outdir = root / "outputs"
    outdir.mkdir(parents=True, exist_ok=True)
    out.to_csv(outdir / "vessel_loitering_hours.csv", index=False)
    cols = [c for c in ["ship_name", "flag", "vessel_type", "imo", "total_stop_hours", "offshore_stop_hours", "longest_stop_hours", "distinct_locations", "median_port_km", "gfw_loitering_hours", "nearby_encounters"] if c in out.columns]
    typer.echo(out[cols].head(top).to_string(index=False))
    typer.echo(f"\n{len(out):,} vessels. Saved: {outdir / 'vessel_loitering_hours.csv'}")


@app.command("loitering-breakdown")
def loitering_breakdown(
    root: Path = typer.Option(Path(".")),
    boundaries: Path = typer.Option(Path("config/presets/west_africa_maritime.geojson")),
    config: Path = typer.Option(Path("config/default.yaml")),
):
    """Split cached stop hours by coastal country and year (observed window only)."""
    from .breakdown import write_breakdown
    cfg = load_config(config)
    pdir = root / "data" / "processed"
    presence = pd.read_parquet(pdir / "presence.parquet")
    stops = pd.read_parquet(pdir / "stops_scored.parquet")
    lp = pdir / "events_loitering.parquet"
    events = pd.read_parquet(lp) if lp.exists() else pd.DataFrame()
    from .utils import normalize_timestamp_column
    dates = normalize_timestamp_column(presence).timestamp
    result = write_breakdown(stops, presence, events, boundaries, dates.min(),
                             dates.max() + pd.Timedelta(hours=1), root / "outputs",
                             cfg["ranking"].get("offshore_km", 20))
    typer.echo(f"Saved {len(result):,} vessel/country/year rows to {root / 'outputs'}")


@app.command("annual-loitering")
def annual_loitering(
    start_year: int = typer.Option(2019),
    end_year: int | None = typer.Option(None, help="Last complete year by default"),
    end_date: str | None = typer.Option(None, help="Exclusive month boundary, e.g. 2026-09-01; includes a partial final year"),
    region: Path = typer.Option(Path("config/presets/west_africa_core.geojson")),
    boundaries: Path = typer.Option(Path("config/presets/west_africa_maritime.geojson")),
    config: Path = typer.Option(Path("config/default.yaml")),
    root: Path = typer.Option(Path("annual_run")),
    token: str | None = typer.Option(None, envvar="GFW_API_TOKEN"),
):
    """Fetch/analyze complete UTC years sequentially, with isolated resumable caches."""
    import hashlib
    import json
    from .breakdown import write_breakdown
    now = pd.Timestamp.now(tz="UTC")
    current_year = now.year
    cutoff = None
    if end_date is not None:
        if end_year is not None:
            raise typer.BadParameter("Use either end-year or end-date")
        try:
            cutoff = pd.to_datetime(end_date, utc=True)
        except (ValueError, TypeError) as exc:
            raise typer.BadParameter("end-date must be a valid date") from exc
        last_month_end = pd.Timestamp(f"{now.year}-{now.month:02d}-01", tz="UTC")
        if pd.isna(cutoff) or cutoff.day != 1 or cutoff != cutoff.normalize() or cutoff > last_month_end:
            raise typer.BadParameter("end-date must be a completed month boundary (exclusive)")
        final_year = (cutoff - pd.Timedelta(days=1)).year
    else:
        final_year = end_year if end_year is not None else current_year - 1
    if start_year > final_year or (cutoff is None and final_year >= current_year):
        raise typer.BadParameter("Choose completed calendar years, start-year <= end-year; use end-date for a partial year")
    cfg = load_config(config)
    geometry = load_geojson_geometry(region)
    cfg["api"]["events_limit"] = 5000
    # Validate before spending API quota; changes get separate cache directories.
    boundary_data = json.loads(boundaries.read_text())
    if not boundary_data.get("features") or any(
        "country" not in f.get("properties", {}) for f in boundary_data["features"]
    ):
        raise typer.BadParameter("Boundaries need features with a country property")
    signature = hashlib.sha256(json.dumps(
        {"geometry": geometry, "config": cfg, "boundaries": boundary_data},
        sort_keys=True).encode()).hexdigest()[:16]
    run_root = root / signature
    client = GFWClient(token=_token(token), base_url=cfg["api"]["base_url"],
                       timeout_seconds=cfg["api"]["timeout_seconds"],
                       last_report_poll_seconds=cfg["api"]["last_report_poll_seconds"],
                       last_report_max_polls=cfg["api"]["last_report_max_polls"])
    outdir = run_root / "outputs"
    combined_path = outdir / "vessel_loitering_hours_by_country_year.csv"
    manifest_path = outdir / "manifest.json"
    previous = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    completed_years = set(previous.get("completed_years", []))
    tables = [pd.read_csv(combined_path)] if combined_path.exists() else []
    for year in range(start_year, final_year + 1):
        year_root = run_root / str(year)
        start, end = f"{year}-01-01", f"{year+1}-01-01"
        if cutoff is not None and year == final_year:
            end = cutoff.strftime("%Y-%m-%d")
        typer.echo(f"{year}: fetching {start} to {end} (exclusive)")
        presence, events = fetch_all(client, geometry, start, end,
                                     year_root / "data" / "raw", cfg)
        if presence.empty:
            raise RuntimeError(f"No presence returned for {year}; annual coverage unverified")
        from .utils import normalize_timestamp_column
        dates = normalize_timestamp_column(presence).timestamp
        presence = presence[(dates >= pd.Timestamp(start, tz="UTC")) &
                            (dates < pd.Timestamp(end, tz="UTC"))].copy()
        scored, _ = analyze(presence, events, cfg, year_root)
        table = write_breakdown(scored, presence, events.get("loitering"), boundaries,
                                start, end, year_root / "outputs",
                                cfg["ranking"].get("offshore_km", 20))
        tables = [t[t.year != year] for t in tables]
        tables.append(table)
        if end == f"{year+1}-01-01":
            completed_years.add(year)
        else:
            completed_years.discard(year)
        outdir = run_root / "outputs"
        outdir.mkdir(parents=True, exist_ok=True)
        pd.concat(tables, ignore_index=True).to_csv(
            outdir / "vessel_loitering_hours_by_country_year.csv", index=False)
        manifest = {"start_year": min(start_year, previous.get("start_year", start_year)),
                    "requested_end_year": final_year,
                    "requested_end_date_exclusive": cutoff.strftime("%Y-%m-%d") if cutoff is not None else f"{final_year+1}-01-01",
                    "completed_years": sorted(completed_years),
                    "partial_year": year if end != f"{year+1}-01-01" else None,
                    "latest_completed_period_end_exclusive": end,
                    "geometry": geometry, "config": cfg,
                    "boundary_file": str(boundaries.resolve()),
                    "boundary_sha256": hashlib.sha256(boundaries.read_bytes()).hexdigest()}
        (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2))
        typer.echo(f"{year}: saved {len(table):,} rows. Combined CSV: {outdir}")


@app.command()
def demo(
    config: Path = typer.Option(Path("config/default.yaml")),
    root: Path = typer.Option(Path("demo_run")),
):
    """Run the full analysis on synthetic AIS-like data; no GFW token required."""
    cfg = load_config(config)
    scored, hosts = analyze(synthetic_presence(), synthetic_events(), cfg, root)
    typer.echo(f"demo ranked stops: {len(scored)}")
    typer.echo(f"demo host candidates: {len(hosts)}")
    typer.echo(f"open: {root / 'outputs' / 'suspicious_map.html'}")


@app.command("validate-vessel")
def validate_vessel(
    query: str = typer.Argument(..., help="Ship name, IMO, MMSI, or callsign"),
    label: str | None = typer.Option(None, help="Human-readable label"),
    config: Path = typer.Option(Path("config/default.yaml")),
    token: str | None = typer.Option(None, envvar="GFW_API_TOKEN"),
    root: Path = typer.Option(Path(".")),
):
    """Resolve a known vessel in GFW and report whether/rank where this run detected it."""
    cfg = load_config(config)
    c = GFWClient(token=_token(token), base_url=cfg["api"]["base_url"])
    identities = resolve_gfw_vessel_ids(c, query)
    if not identities:
        typer.echo(f"No GFW vessel identity found for: {query}")
        raise typer.Exit(code=2)
    ids = [x["vessel_id"] for x in identities]
    imo = next((x.get("imo") for x in identities if x.get("imo")), None)
    summary = summarize_detection(root, ids, label or query, imo=imo)
    typer.echo(pd.DataFrame([summary]).to_string(index=False))
    typer.echo("\nResolved GFW identities:")
    typer.echo(pd.DataFrame(identities).to_string(index=False))
    stops, hosts = validation_detail(root, ids)
    if not stops.empty:
        cols = [c for c in ["vessel_id", "ship_name", "start", "end", "duration_hours", "lat", "lon", "cluster_id", "nearby_gaps", "nearby_encounters", "suspicion_score"] if c in stops.columns]
        typer.echo("\nTop matching stop episodes:")
        typer.echo(stops[cols].head(20).to_string(index=False))
    if not hosts.empty:
        cols = [c for c in ["vessel_id", "ship_name", "cluster_id", "host_stop_hours", "other_vessels", "nearby_gaps", "nearby_encounters", "host_score"] if c in hosts.columns]
        typer.echo("\nMatching host candidates:")
        typer.echo(hosts[cols].head(20).to_string(index=False))


@app.command("validate-josef")
def validate_josef(
    config: Path = typer.Option(Path("config/default.yaml")),
    token: str | None = typer.Option(None, envvar="GFW_API_TOKEN"),
    root: Path = typer.Option(Path(".")),
):
    """Ground-truth check against the two floating fishmeal factory vessels in Josef Skrdlik's reporting."""
    cfg = load_config(config)
    c = GFWClient(token=_token(token), base_url=cfg["api"]["base_url"])
    rows = []
    all_identities = []
    for vessel in JOSEF_FISHMEAL_CASE:
        identities = resolve_gfw_vessel_ids(c, vessel.imo)
        ids = [x["vessel_id"] for x in identities]
        rows.append(summarize_detection(root, ids, vessel.label, imo=vessel.imo))
        for x in identities:
            all_identities.append({"label": vessel.label, **x})
    out = pd.DataFrame(rows)
    outdir = root / "outputs"
    outdir.mkdir(parents=True, exist_ok=True)
    out.to_csv(outdir / "validation_josef_fishmeal.csv", index=False)
    typer.echo(out.to_string(index=False))
    typer.echo(f"\nSaved: {outdir / 'validation_josef_fishmeal.csv'}")
    if all_identities:
        pd.DataFrame(all_identities).to_csv(outdir / "validation_josef_identities.csv", index=False)


if __name__ == "__main__":
    app()
