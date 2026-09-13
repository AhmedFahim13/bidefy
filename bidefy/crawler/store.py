"""Append-only Parquet store under data/raw/<endpoint>/. Dedupe happens on read."""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

ID_COLUMN = "tender_id"


def _dir(root: Path, endpoint: str) -> Path:
    return Path(root) / "raw" / endpoint


def _warn(message: str) -> None:
    print(message, file=sys.stderr)


def append_rows(rows: list[dict], root: Path, endpoint: str) -> Path | None:
    """Write rows to a new part file. Returns the path, or None if rows is empty.

    Writes to a temporary file in the same directory and atomically renames it
    into place, so a reader never sees a partially-written part file.
    """
    if not rows:
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    df = pl.DataFrame(rows).with_columns(pl.lit(stamp).alias("fetched_at"))
    out = _dir(root, endpoint)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"part-{stamp}-{uuid.uuid4().hex[:8]}.parquet"
    tmp = path.with_suffix(".parquet.tmp")
    df.write_parquet(tmp, compression="zstd")
    os.replace(tmp, path)
    return path


def _parts(root: Path, endpoint: str) -> list[Path]:
    d = _dir(root, endpoint)
    return sorted(d.glob("part-*.parquet")) if d.exists() else []


def _read_parts(parts: list[Path], columns: list[str] | None = None) -> list[pl.DataFrame]:
    """Read every readable part, skipping (and warning about) any that fail to read."""
    frames = []
    for p in parts:
        try:
            frames.append(pl.read_parquet(p, columns=columns))
        except Exception as e:  # noqa: BLE001 - a bad part must never break the crawl
            _warn(f"store: skipping unreadable part {p.name}: {e}")
    return frames


def known_ids(root: Path, endpoint: str) -> set[str]:
    parts = _parts(root, endpoint)
    if not parts:
        return set()
    frames = _read_parts(parts, columns=[ID_COLUMN])
    if not frames:
        return set()
    frames = [f.with_columns(pl.col(ID_COLUMN).cast(pl.Utf8)) for f in frames]
    ids = pl.concat(frames, how="vertical_relaxed")
    return set(ids[ID_COLUMN].to_list())


def load_all(root: Path, endpoint: str) -> pl.DataFrame:
    """All rows, one per id, keeping the most recently fetched copy."""
    parts = _parts(root, endpoint)
    if not parts:
        return pl.DataFrame()
    frames = _read_parts(parts)
    if not frames:
        return pl.DataFrame()
    frames = [f.with_columns(pl.col(ID_COLUMN).cast(pl.Utf8)) for f in frames]
    df = pl.concat(frames, how="diagonal_relaxed")
    return df.sort("fetched_at").unique(subset=[ID_COLUMN], keep="last").sort(ID_COLUMN)


def compact(root: Path, endpoint: str) -> Path | None:
    """Merge all readable parts into one file, deduped by id keeping the latest fetch.

    Returns the path of the new compact part, or None if there were fewer than
    two parts to merge. The old parts are only deleted after the compact file
    has been fully written, so a crash mid-compact never loses data.
    """
    parts = _parts(root, endpoint)
    if len(parts) < 2:
        return None
    df = load_all(root, endpoint)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    out = _dir(root, endpoint)
    new_path = out / f"part-{stamp}-compact.parquet"
    tmp = new_path.with_suffix(".parquet.tmp")
    df.write_parquet(tmp, compression="zstd")
    os.replace(tmp, new_path)
    for p in parts:
        p.unlink(missing_ok=True)
    return new_path
