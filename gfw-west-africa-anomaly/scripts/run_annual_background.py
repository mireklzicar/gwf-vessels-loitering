"""Launch the full-year backfill independently; run via op run --env-file=.env."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone

project = Path(__file__).resolve().parents[1]
os.chdir(project)
root = project / 'annual_run'
root.mkdir(exist_ok=True)
after_current = '--after-current' in sys.argv
if after_current:
    sys.argv.remove('--after-current')
status = root / ('extension_status.json' if after_current else 'status.json')

if '--worker' not in sys.argv:
    if status.exists():
        prior = json.loads(status.read_text())
        if prior.get('state') in ('running', 'queued'):
            try:
                os.kill(prior['pid'], 0)
            except ProcessLookupError:
                pass
            else:
                raise SystemExit('A backfill is already running')
    with (root / 'download.log').open('a') as log:
        child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()),
                                  '--worker', *(['--after-current'] if after_current else []), *sys.argv[1:]],
                                 stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                 start_new_session=True)
    print(f'Background PID: {child.pid}; log: {root / "download.log"}')
else:
    data = {'state': 'queued' if after_current else 'running', 'pid': os.getpid(),
            'arguments': sys.argv[1:],
            'started_at': datetime.now(timezone.utc).isoformat()}
    status.write_text(json.dumps(data, indent=2))
    if after_current:
        while True:
            previous = json.loads((root / 'status.json').read_text())
            if previous['state'] == 'completed':
                break
            if previous['state'] != 'running':
                data.update(state='blocked', reason='Previous backfill did not complete')
                status.write_text(json.dumps(data, indent=2))
                sys.exit(1)
            try:
                os.kill(previous['pid'], 0)
            except ProcessLookupError:
                data.update(state='blocked', reason='Previous worker is no longer running')
                status.write_text(json.dumps(data, indent=2))
                sys.exit(1)
            time.sleep(30)
        data.update(state='running')
        status.write_text(json.dumps(data, indent=2))
    command = [sys.executable, '-m', 'gfw_anomaly.cli', 'annual-loitering',
               *[a for a in sys.argv[1:] if a != '--worker']]
    result = subprocess.run(command, check=False)
    data.update(state='completed' if result.returncode == 0 else 'failed',
                exit_code=result.returncode,
                finished_at=datetime.now(timezone.utc).isoformat())
    status.write_text(json.dumps(data, indent=2))
    sys.exit(result.returncode)
