"""Download maritime areas intersecting the preset from the Marine Regions WFS."""
import json
from datetime import datetime, timezone
from pathlib import Path

import requests
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

root = Path(__file__).resolve().parents[1]
preset = json.loads((root / 'config/presets/west_africa_core.geojson').read_text())
region = unary_union([shape(f['geometry']) for f in preset['features']])
url = 'https://geo.vliz.be/geoserver/MarineRegions/wfs'
params = {'service': 'WFS', 'version': '1.0.0', 'request': 'GetFeature',
          'typeName': 'MarineRegions:eez', 'outputFormat': 'application/json',
          'bbox': ','.join(map(str, region.bounds))}
r = requests.get(url, params=params, timeout=120)
r.raise_for_status()
source = r.json()
if source.get('numberReturned', len(source['features'])) >= 1000:
    raise RuntimeError('Check WFS pagination before using these boundaries')
features = []
for f in source['features']:
    geom = shape(f['geometry']).intersection(region)
    if geom.is_empty or geom.area == 0:
        continue
    props = f['properties']
    names = sorted({props[f'territory{i}'] for i in (1, 2, 3) if props.get(f'territory{i}')})
    features.append({'type': 'Feature', 'properties': {
        'country': ' / '.join(names), 'source_properties': props}, 'geometry': mapping(geom)})
result = {'type': 'FeatureCollection', 'source': url, 'query': params,
          'retrieved_at': datetime.now(timezone.utc).isoformat(),
          'attribution': 'Flanders Marine Institute, Marine Regions. https://www.marineregions.org/',
          'notes': 'Static maritime areas clipped to the analysis preset; not historical boundaries.',
          'features': features}
path = root / 'config/presets/west_africa_maritime.geojson'
path.write_text(json.dumps(result, ensure_ascii=False))
print(f'Wrote {len(features)} maritime areas: {path}')
