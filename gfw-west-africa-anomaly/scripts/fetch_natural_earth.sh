#!/usr/bin/env bash
set -euo pipefail
# Optional convenience only. The pipeline does not require these files.
# Natural Earth is public domain: https://www.naturalearthdata.com/about/terms-of-use/
mkdir -p data/static
curl -L -o data/static/ne_50m_land.geojson \
  https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_land.geojson
curl -L -o data/static/ne_10m_ports.geojson \
  https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_ports.geojson
