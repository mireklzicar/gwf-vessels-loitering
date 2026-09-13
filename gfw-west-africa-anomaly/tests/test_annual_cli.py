import json

import pandas as pd
from typer.testing import CliRunner

from gfw_anomaly import cli


def test_annual_rejects_unfinished_year_before_api_call(tmp_path):
    year = pd.Timestamp.now(tz='UTC').year
    result = CliRunner().invoke(cli.app, ['annual-loitering', '--end-year', str(year)])
    assert result.exit_code != 0
    assert 'completed calendar years' in result.output


def test_annual_isolates_years_and_writes_manifest(tmp_path, monkeypatch):
    calls = []
    def fetch(client, geometry, start, end, raw_dir, cfg):
        calls.append((start, end, raw_dir))
        return pd.DataFrame({'date': [start], 'vessel_id': ['v']}), {}
    monkeypatch.setattr(cli, 'fetch_all', fetch)
    monkeypatch.setattr(cli, 'analyze', lambda *args: (pd.DataFrame(), pd.DataFrame()))
    result = CliRunner().invoke(cli.app, ['annual-loitering', '--start-year', '2019',
        '--end-year', '2020', '--root', str(tmp_path), '--token', 'test-token'])
    assert result.exit_code == 0, result.output
    assert [(a,b) for a,b,_ in calls] == [('2019-01-01','2020-01-01'),
                                         ('2020-01-01','2021-01-01')]
    assert calls[0][2] != calls[1][2]
    manifest = json.loads(next(tmp_path.glob('*/outputs/manifest.json')).read_text())
    assert manifest['completed_years'] == [2019, 2020]


def test_partial_year_extension_preserves_previous_results(tmp_path, monkeypatch):
    from gfw_anomaly import breakdown
    calls = []
    def fetch(client, geometry, start, end, raw_dir, cfg):
        calls.append((start, end))
        return pd.DataFrame({'date': [start], 'vessel_id': ['v']}), {}
    def write(stops, presence, events, boundaries, start, end, outdir, offshore):
        year = int(start[:4])
        return pd.DataFrame({'year': [year], 'vessel_id': ['v'],
                             'window_end': [end],
                             'complete_calendar_year': [end == f'{year+1}-01-01']})
    monkeypatch.setattr(cli, 'fetch_all', fetch)
    monkeypatch.setattr(cli, 'analyze', lambda *args: (pd.DataFrame(), pd.DataFrame()))
    monkeypatch.setattr(breakdown, 'write_breakdown', write)
    runner = CliRunner()
    common = ['--root', str(tmp_path), '--token', 'test-token']
    first = runner.invoke(cli.app, ['annual-loitering', '--start-year', '2019',
                                    '--end-year', '2019', *common])
    assert first.exit_code == 0, first.output
    second = runner.invoke(cli.app, ['annual-loitering', '--start-year', '2020',
                                     '--end-date', '2020-09-01', *common])
    assert second.exit_code == 0, second.output
    assert calls[-1] == ('2020-01-01', '2020-09-01')
    result = pd.read_csv(next(tmp_path.glob('*/outputs/*.csv')))
    assert result.year.tolist() == [2019, 2020]
    assert result.complete_calendar_year.tolist() == [True, False]
    manifest = json.loads(next(tmp_path.glob('*/outputs/manifest.json')).read_text())
    assert manifest['completed_years'] == [2019]
    assert manifest['partial_year'] == 2020
    assert manifest['start_year'] == 2019


def test_incomplete_month_is_rejected():
    result = CliRunner().invoke(cli.app, ['annual-loitering', '--end-date', '2026-08-15'])
    assert result.exit_code != 0
    assert 'completed month boundary' in result.output
