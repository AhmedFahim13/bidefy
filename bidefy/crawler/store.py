"""Append-only Parquet store under data/raw/<endpoint>/. Dedupe happens on read."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import polars as pl

ID_COLUMN = "tender_id"


def _dir(root: Path, endpoint: str) -> Path:
    return Path(root) / "raw" / endpoint


def append_rows(rows: list[dict], root: Path, endpoint: str) -> Path | None:
    """Write rows to a new part file. Returns the path, or None if rows is empty."""
    if not rows:
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    df = pl.DataFrame(rows).with_columns(pl.lit(stamp).alias("fetched_at"))
    out = _dir(root, endpoint)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"part-{stamp}.parquet"
    df.write_parquet(path, compression="zstd")
    return path


def _parts(root: Path, endpoint: str) -> list[Path]:
    d = _dir(root, endpoint)
    return sorted(d.glob("part-*.parquet")) if d.exists() else []


def known_ids(root: Path, endpoint: str) -> set[str]:
    parts = _parts(root, endpoint)
    if not parts:
        return set()
    ids = pl.concat([pl.read_parquet(p, columns=[ID_COLUMN]) for p in parts])
    return set(ids[ID_COLUMN].cast(pl.Utf8).to_list())


def load_all(root: Path, endpoint: str) -> pl.DataFrame:
    """All rows, one per id, keeping the most recently fetched copy."""
    parts = _parts(root, endpoint)
    if not parts:
        return pl.DataFrame()
    df = pl.concat([pl.read_parquet(p) for p in parts], how="diagonal_relaxed")
    return df.sort("fetched_at").unique(subset=[ID_COLUMN], keep="last").sort(ID_COLUMN)
