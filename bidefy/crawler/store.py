"""Append-only Parquet store under data/raw/<endpoint>/. Dedupe happens on read."""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

ID_COLUMN = "tender_id"
DEFAULT_MIN_PARTS = 20


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


def _loose_parts(root: Path, endpoint: str) -> list[Path]:
    """Part files that are not themselves the product of a previous compact."""
    return [p for p in _parts(root, endpoint) if not p.name.endswith("-compact.parquet")]


def compact(root: Path, endpoint: str, min_parts: int = DEFAULT_MIN_PARTS) -> Path | None:
    """Merge loose parts into one new compact file, deduped by id keeping the latest fetch.

    Only part files that are not already the output of an earlier compact are
    consumed, so a previous compact file is never rewritten. If fewer than
    min_parts such loose parts exist, nothing is done and None is returned.
    The old parts are only deleted after the new compact file has been fully
    written, so a crash mid-compact never loses data.
    """
    loose = _loose_parts(root, endpoint)
    if len(loose) < min_parts:
        return None
    frames = []
    consumed = []
    for p in loose:
        try:
            frames.append(pl.read_parquet(p))
            consumed.append(p)
        except Exception as e:  # noqa: BLE001 - a bad part must never break compaction
            _warn(f"store: skipping unreadable part {p.name}: {e}")
    if not frames:
        return None
    frames = [f.with_columns(pl.col(ID_COLUMN).cast(pl.Utf8)) for f in frames]
    df = pl.concat(frames, how="diagonal_relaxed").sort("fetched_at").unique(subset=[ID_COLUMN], keep="last").sort(ID_COLUMN)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    out = _dir(root, endpoint)
    new_path = out / f"part-{stamp}-compact.parquet"
    tmp = new_path.with_suffix(".parquet.tmp")
    df.write_parquet(tmp, compression="zstd")
    os.replace(tmp, new_path)
    for p in consumed:
        p.unlink(missing_ok=True)
    return new_path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Bidefy crawler store maintenance")
    sub = ap.add_subparsers(dest="command", required=True)
    compact_ap = sub.add_parser("compact", help="merge loose parts into one compact file")
    compact_ap.add_argument("--endpoint", required=True)
    compact_ap.add_argument("--data-root", default="data")
    compact_ap.add_argument("--min-parts", type=int, default=DEFAULT_MIN_PARTS)
    a = ap.parse_args(argv)

    if a.command == "compact":
        root = Path(a.data_root)
        loose_count = len(_loose_parts(root, a.endpoint))
        result = compact(root, a.endpoint, min_parts=a.min_parts)
        if result is not None:
            print(f"compact: {a.endpoint}: merged {loose_count} parts into {result}")
        else:
            print(f"compact: {a.endpoint}: {loose_count} parts, below threshold, nothing done")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
