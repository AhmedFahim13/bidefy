"""Plan and execute capped, resumable loads from data/clean into D1 through wrangler.

D1's free tier counts every index entry as a row write, so the budget is measured in writes:
rows multiplied by one plus the table's index count. The budget is per UTC day and survives
across the two nightly runs through the watermark file. Contract awards are not loaded as rows;
bidder and entity profiles carry precomputed JSON aggregates instead.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path

import polars as pl

WINDOW_MONTHS = 12
BATCH_ROWS = 200                 # upper bound on rows per INSERT
MAX_STATEMENT_BYTES = 90_000     # D1 rejects statements near 100 KB with SQLITE_TOOBIG
DEFAULT_MAX_WRITES = 80_000      # per UTC day, leaving headroom under the 100,000 cap
BIDDER_LOOKBACK_DAYS = 3         # bidders whose latest award is this recent get re-written
TABLES = {
    "tenders": ["tender_id", "reference", "status", "note", "nature", "title", "ministry", "organization",
                "procuring_entity", "pe_id", "procurement_type", "method", "published_at", "closing_at", "fetched_at",
                "category", "category_confidence"],
    "bidders": ["bidder_id", "canonical_name", "variants", "n_awards", "total_value_crore", "first_award", "last_award", "recent_awards", "flags"],
    "procuring_entities": ["pe_id", "name", "ministry", "n_contracts", "n_tenders", "recent_awards", "top_bidders", "flags"],
    "predictions": ["tender_id", "q10_lakh", "q50_lakh", "q90_lakh", "deferred", "model_version"],
}
# one row write per row plus one per index on the table (see worker/schema.sql and migrations)
WRITE_WEIGHT = {"tenders": 5, "bidders": 1, "procuring_entities": 1, "predictions": 1}


@dataclass
class Watermark:
    tenders: str = ""
    contracts: str = ""          # kept for older files; unused
    bidders: str = ""            # last_award date loaded through
    loaded_rows_today: int = 0
    writes_today: int = 0
    day: str = ""

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path) -> "Watermark":
        if not Path(path).exists():
            return cls()
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)


@dataclass
class Plan:
    statements: list[str] = field(default_factory=list)
    rows: int = 0
    writes: int = 0
    watermark: Watermark = field(default_factory=Watermark)
    skipped: dict[str, int] = field(default_factory=dict)   # table -> rows left for another day


def _sql_value(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return repr(v)
    return "'" + str(v).replace("'", "''") + "'"


def _inserts(table: str, df: pl.DataFrame) -> list[str]:
    """Multi-row INSERT OR REPLACE statements, each under BATCH_ROWS rows and MAX_STATEMENT_BYTES bytes."""
    cols = [c for c in TABLES[table] if c in df.columns]
    head = f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) VALUES\n"
    out: list[str] = []
    chunk: list[str] = []
    size = len(head.encode("utf-8"))
    for row in df.select(cols).rows():
        value = "(" + ", ".join(_sql_value(v) for v in row) + ")"
        vbytes = len(value.encode("utf-8")) + 2
        if chunk and (len(chunk) >= BATCH_ROWS or size + vbytes > MAX_STATEMENT_BYTES):
            out.append(head + ",\n".join(chunk) + ";")
            chunk, size = [], len(head.encode("utf-8"))
        chunk.append(value)
        size += vbytes
    if chunk:
        out.append(head + ",\n".join(chunk) + ";")
    return out


def _read(root: Path, name: str) -> pl.DataFrame:
    path = Path(root) / "clean" / f"{name}.parquet"
    return pl.read_parquet(path) if path.exists() else pl.DataFrame()


def _take(plan: Plan, table: str, df: pl.DataFrame, budget: int) -> tuple[pl.DataFrame, int]:
    """Take as many rows as the write budget allows; record what was left."""
    weight = WRITE_WEIGHT[table]
    n = min(df.height, budget // weight)
    take = df.head(n)
    if n < df.height:
        plan.skipped[table] = df.height - n
    if n:
        plan.statements += _inserts(table, take)
        plan.rows += n
        plan.writes += n * weight
    return take, budget - n * weight


def plan_load(root: Path, watermark: Watermark, max_writes: int = DEFAULT_MAX_WRITES, today: str | None = None) -> Plan:
    """Tenders newer than the watermark, bidders with recent awards, all entities, all predictions."""
    today_d = date.fromisoformat(today) if today else date.today()
    today_s = today_d.isoformat()
    window_start = (today_d - timedelta(days=30 * WINDOW_MONTHS)).isoformat()
    used = watermark.writes_today if watermark.day == today_s else 0
    plan = Plan(watermark=Watermark(tenders=watermark.tenders, bidders=watermark.bidders, day=today_s, writes_today=used))
    budget = max(0, max_writes - used)

    tenders = _read(root, "tenders")
    if not tenders.is_empty() and budget > 0:
        if "fetched_at" not in tenders.columns:
            tenders = tenders.with_columns(pl.lit("").alias("fetched_at"))
        recent = tenders.filter(pl.col("published_at").fill_null("") >= window_start) if "published_at" in tenders.columns else tenders
        if "status" in tenders.columns:
            recent = pl.concat([recent, tenders.filter(pl.col("status") == "Live")]).unique(subset=["tender_id"], keep="last")
        pending = recent.filter(pl.col("fetched_at").cast(pl.Utf8) > watermark.tenders).sort("fetched_at")
        take, budget = _take(plan, "tenders", pending, budget)
        if take.height:
            plan.watermark.tenders = str(take["fetched_at"][-1])

    bidders = _read(root, "bidders")
    if not bidders.is_empty() and budget > 0:
        if watermark.bidders and "last_award" in bidders.columns:
            since = (date.fromisoformat(watermark.bidders) - timedelta(days=BIDDER_LOOKBACK_DAYS)).isoformat()
            pending = bidders.filter(pl.col("last_award").fill_null("") >= since)
        else:
            pending = bidders
        pending = pending.sort("last_award", descending=True, nulls_last=True)
        take, budget = _take(plan, "bidders", pending, budget)
        if take.height and "last_award" in take.columns:
            newest = take["last_award"].drop_nulls()
            if newest.len() and not plan.skipped.get("bidders"):
                plan.watermark.bidders = str(newest.max())
            elif watermark.bidders:
                plan.watermark.bidders = watermark.bidders

    for table in ("procuring_entities", "predictions"):
        df = _read(root, table)
        if df.is_empty() or budget <= 0:
            continue
        _, budget = _take(plan, table, df, budget)

    plan.watermark.loaded_rows_today = plan.rows
    plan.watermark.writes_today = used + plan.writes
    return plan


def write_sql(plan: Plan, out_dir: Path, statements_per_file: int = 20) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("batch-*.sql"):
        old.unlink()
    files = []
    for i in range(0, len(plan.statements), statements_per_file):
        path = out_dir / f"batch-{i // statements_per_file:04d}.sql"
        path.write_text("\n".join(plan.statements[i:i + statements_per_file]) + "\n", encoding="utf-8")
        files.append(path)
    return files


def execute(files: list[Path], database: str, remote: bool, runner=subprocess.run) -> None:
    for path in files:
        cmd = ["npx", "wrangler", "d1", "execute", database, "--remote" if remote else "--local",
               "--file", str(Path(path).resolve()), "--yes"]
        result = runner(cmd, cwd="worker", shell=True, capture_output=True, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            detail = ((result.stderr or "") + (result.stdout or ""))[-2000:]
            raise RuntimeError(f"wrangler failed on {Path(path).name}: {detail}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Load clean tables into D1 within the daily write cap")
    ap.add_argument("--data-root", default="data")
    ap.add_argument("--watermark", default="checkpoints/d1_load.json")
    ap.add_argument("--max-writes", type=int, default=DEFAULT_MAX_WRITES, help="per UTC day, counting index entries")
    ap.add_argument("--database", default="bidefy")
    ap.add_argument("--local", action="store_true", help="load the local wrangler D1 instead of remote")
    ap.add_argument("--dry-run", action="store_true", help="write SQL files, do not execute")
    a = ap.parse_args(argv)
    wm = Watermark.load(Path(a.watermark))
    plan = plan_load(Path(a.data_root), wm, max_writes=a.max_writes)
    files = write_sql(plan, Path("build") / "d1")
    left = ", ".join(f"{k} {v} rows deferred" for k, v in plan.skipped.items()) or "nothing deferred"
    print(f"d1 load: {plan.rows} rows, about {plan.writes} writes ({plan.watermark.writes_today} today), "
          f"{len(plan.statements)} statements across {len(files)} files; {left}")
    if a.dry_run or not files:
        return 0
    try:
        execute(files, a.database, remote=not a.local)
    except RuntimeError as e:
        # A blocked or failed load must not fail the nightly job or move the watermark.
        print(f"d1 load: skipped, {str(e)[:300]}")
        return 0
    plan.watermark.save(Path(a.watermark))
    print(f"d1 load: done, watermark tenders={plan.watermark.tenders} bidders={plan.watermark.bidders}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
