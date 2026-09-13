from __future__ import annotations

from pathlib import Path
import pandas as pd


def write_parquet(df: pd.DataFrame, path: str | Path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def build_duckdb(db_path: str | Path, parquet_paths: dict[str, str | Path]):
    import duckdb
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    try:
        for name, path in parquet_paths.items():
            p = Path(path)
            if not p.exists():
                continue
            con.execute(f'CREATE OR REPLACE TABLE "{name}" AS SELECT * FROM read_parquet(?)', [str(p)])
    finally:
        con.close()
