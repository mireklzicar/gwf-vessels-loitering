"""Benchmark lossless CSV compression and typed Parquet; retain the winners."""
import argparse
import gzip
import hashlib
import json
import lzma
from pathlib import Path
import shutil
import tempfile
import time

import pyarrow as pa
import pyarrow.csv as csv
import pyarrow.parquet as pq

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('output_dir', type=Path)
args = parser.parse_args()
report = []
identifiers = ['imo', 'mmsi', 'callsign', 'vessel_id', 'ship_name', 'flag',
               'vessel_type', 'geartype', 'ship_names_seen', 'flags_seen']
for name in ['vessel_loitering_hours_by_country_year',
             'vessel_loitering_hours_by_country_all_years']:
    source = args.output_dir / f'{name}.csv'
    data = source.read_bytes()
    table = csv.read_csv(source, convert_options=csv.ConvertOptions(
        column_types={c: pa.string() for c in identifiers},
        null_values=[''], strings_can_be_null=False))
    # Parquet supports millisecond/microsecond timestamps, not second precision.
    schema = pa.schema([pa.field(f.name, pa.timestamp('us', tz=f.type.tz))
                        if pa.types.is_timestamp(f.type) else f for f in table.schema])
    table = table.cast(schema)
    results = []
    with tempfile.TemporaryDirectory(prefix='loitering-compression-') as temp:
        temp = Path(temp)
        for codec in ['gzip-9', 'xz-9', 'zstd-19', 'zstd-22']:
            start = time.monotonic()
            if codec == 'gzip-9':
                compressed = gzip.compress(data, compresslevel=9, mtime=0)
                assert gzip.decompress(compressed) == data
                suffix = '.gz'
            elif codec == 'xz-9':
                compressed = lzma.compress(data, preset=9)
                assert lzma.decompress(compressed) == data
                suffix = '.xz'
            else:
                c = pa.Codec('zstd', compression_level=int(codec.split('-')[1]))
                compressed = c.compress(data).to_pybytes()
                assert c.decompress(compressed, len(data)).to_pybytes() == data
                suffix = '.zst'
            path = temp / (codec + suffix)
            path.write_bytes(compressed)
            results.append(dict(format='CSV', codec=codec, bytes=len(compressed),
                                seconds=round(time.monotonic()-start, 2),
                                path=str(path), suffix='.csv'+suffix, verified=True))
            print(name, codec, len(compressed), 'bytes', flush=True)
        for codec, level in [('zstd', 3), ('zstd', 19), ('zstd', 22), ('brotli', 11)]:
            for group_size in [65536, len(table)]:
                start = time.monotonic()
                path = temp / f'{codec}-{level}-{group_size}.parquet'
                pq.write_table(table, path, compression=codec, compression_level=level,
                               row_group_size=group_size, version='2.6',
                               dictionary_pagesize_limit=8*1024*1024)
                assert table.equals(pq.read_table(path)), str(path)
                results.append(dict(format='Parquet', codec=f'{codec}-{level}',
                                    row_group_size=group_size, bytes=path.stat().st_size,
                                    seconds=round(time.monotonic()-start, 2),
                                    path=str(path), suffix='.parquet', verified=True))
                print(name, codec, level, group_size, path.stat().st_size, 'bytes', flush=True)
        winners = [min((r for r in results if r['format'] == kind), key=lambda r:r['bytes'])
                   for kind in ['CSV', 'Parquet']]
        # Also retain widely supported gzip even if another CSV codec wins.
        winners.append(next(r for r in results if r['codec'] == 'gzip-9'))
        saved = set()
        for winner in winners:
            dest = args.output_dir / (name + winner['suffix'])
            if dest not in saved:
                shutil.copyfile(winner['path'], dest)
                saved.add(dest)
        for r in results:
            r.pop('path')
            r.update(source=source.name, original_bytes=len(data),
                     reduction_percent=round(100*(1-r['bytes']/len(data)), 2),
                     source_sha256=hashlib.sha256(data).hexdigest(),
                     rows=len(table), columns=table.num_columns)
        report.extend(results)
(args.output_dir / 'compression_report.json').write_text(json.dumps(report, indent=2))
print('All compressed CSVs restore identical bytes; all Parquet files restore identical typed tables.')
