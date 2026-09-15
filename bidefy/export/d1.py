"""Plan and execute capped, resumable loads from data/clean into D1 through wrangler.

D1's free tier counts every index entry as a row write, so the budget is measured in writes:
rows multiplied by one plus the table's index count. The budget is per UTC day and survives
across the two nightly runs through the watermark file. Contract awards are not loaded as rows;
bidder and entity profiles carry precomputed JSON aggregates instead.

A load only counts once D1 proves it happened. Every load ends by writing a one-off marker row,
and the watermark moves only after that marker is read back from the database. An earlier version
trusted wrangler's exit code, and on Linux a quoting mistake ran bare `npx`, which exits cleanly
having done nothing: two nights of loads reported success and wrote not a single row.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import uuid
from dataclasses import asdict, dataclass, field, replace
from datetime import date, timedelta
from pathlib import Path

import polars as pl

WINDOW_MONTHS = 12
BATCH_ROWS = 200                 # upper bound on rows per INSERT
MAX_STATEMENT_BYTES = 90_000     # D1 rejects statements near 100 KB with SQLITE_TOOBIG
DEFAULT_MAX_WRITES = 80_000      # per UTC day, leaving headroom under the 100,000 cap
BIDDER_LOOKBACK_DAYS = 3         # bidders whose latest award is this recent get re-written
MARKER_KEY = "d1_last_load"      # meta row that proves a load reached the database
TABLES = {
    "tenders": ["tender_id", "reference", "status", "note", "nature", "title", "ministry", "organization",
                "procuring_entity", "pe_id", "procurement_type", "method", "published_at", "closing_at", "fetched_at",
                "category", "category_confidence"],
    "bidders": ["bidder_id", "canonical_name", "variants", "n_awards", "total_value_crore", "first_award", "last_award", "recent_awards", "flags"],
    "procuring_entities": ["pe_id", "name", "ministry", "n_contracts", "n_tenders", "recent_awards", "top_bidders", "flags"],
    "predictions": ["tender_id", "q10_lakh", "q50_lakh", "q90_lakh", "deferred", "basis", "model_version"],
}
# one row write per row plus one per index on the table (see worker/schema.sql and migrations)
WRITE_WEIGHT = {"tenders": 5, "bidders": 1, "procuring_entities": 1, "predictions": 1}


@dataclass
class Watermark:
    tenders: str = ""            # archive backlog: fetched_at loaded through
    contracts: str = ""          # kept for older files; unused
    bidders: str = ""            # last_award date loaded through, once the first full load is done
    loaded_rows_today: int = 0
    writes_today: int = 0
    day: str = ""
    live: str = ""               # live tenders: fetched_at loaded through
    bidders_after: str = ""      # first full bidder load: bidder_id loaded through

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
    skipped: dict[str, int] = field(default_factory=dict)   # part of the load -> rows left for another day


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


def _take(plan: Plan, table: str, df: pl.DataFrame, budget: int, part: str | None = None) -> tuple[pl.DataFrame, int]:
    """Take as many rows as the write budget allows; record what was left under `part`."""
    weight = WRITE_WEIGHT[table]
    n = min(df.height, max(budget, 0) // weight)
    take = df.head(n)
    if n < df.height:
        plan.skipped[part or table] = df.height - n
    if n:
        plan.statements += _inserts(table, take)
        plan.rows += n
        plan.writes += n * weight
    return take, budget - n * weight


def plan_load(root: Path, watermark: Watermark, max_writes: int = DEFAULT_MAX_WRITES, today: str | None = None) -> Plan:
    """Spend the day's write budget in the order a visitor would notice the gap.

    1. Live tenders fetched since the last load, on their own cursor. A notice crawled tonight must
       reach the site tonight, not after tens of thousands of archived notices queued ahead of it.
    2. Award bands, rewritten whole, because the model retrains every night.
    3. Buyer profiles, rewritten whole, for the same reason.
    4. Bidder profiles: every one once, resumably by id, then only those with a recent award.
    5. Whatever budget is left goes to the archive backlog, oldest fetched first.
    """
    today_d = date.fromisoformat(today) if today else date.today()
    today_s = today_d.isoformat()
    window_start = (today_d - timedelta(days=30 * WINDOW_MONTHS)).isoformat()
    used = watermark.writes_today if watermark.day == today_s else 0
    plan = Plan(watermark=replace(watermark, day=today_s, writes_today=used, loaded_rows_today=0))
    budget = max(0, max_writes - used)

    tenders = _read(root, "tenders")
    backlog = pl.DataFrame()
    if not tenders.is_empty():
        if "fetched_at" not in tenders.columns:
            tenders = tenders.with_columns(pl.lit("").alias("fetched_at"))
        tenders = tenders.with_columns(pl.col("fetched_at").cast(pl.Utf8).fill_null(""))
        is_live = (pl.col("status") == "Live") if "status" in tenders.columns else pl.lit(False)
        in_window = (pl.col("published_at").fill_null("") >= window_start) if "published_at" in tenders.columns else pl.lit(True)
        live = tenders.filter(is_live & (pl.col("fetched_at") > watermark.live)).sort("fetched_at")
        backlog = tenders.filter(in_window & ~is_live & (pl.col("fetched_at") > watermark.tenders)).sort("fetched_at")
        if live.height:
            take, budget = _take(plan, "tenders", live, budget, part="tenders_live")
            if take.height:
                plan.watermark.live = str(take["fetched_at"][-1])

    for table in ("predictions", "procuring_entities"):
        df = _read(root, table)
        if not df.is_empty():
            _, budget = _take(plan, table, df, budget)

    bidders = _read(root, "bidders")
    if not bidders.is_empty():
        bidders = bidders.with_columns(pl.col("bidder_id").cast(pl.Utf8))
        has_award = "last_award" in bidders.columns
        if not watermark.bidders:
            pending = bidders.filter(pl.col("bidder_id") > watermark.bidders_after).sort("bidder_id")
            take, budget = _take(plan, "bidders", pending, budget)
            if take.height < pending.height:
                if take.height:
                    plan.watermark.bidders_after = str(take["bidder_id"][-1])
            else:
                newest = bidders["last_award"].cast(pl.Utf8).drop_nulls() if has_award else pl.Series([], dtype=pl.Utf8)
                plan.watermark.bidders = str(newest.max()) if newest.len() else today_s
                plan.watermark.bidders_after = ""
        elif has_award:
            since = (date.fromisoformat(watermark.bidders) - timedelta(days=BIDDER_LOOKBACK_DAYS)).isoformat()
            pending = (bidders.filter(pl.col("last_award").cast(pl.Utf8).fill_null("") >= since)
                       .sort("last_award", descending=True, nulls_last=True))
            take, budget = _take(plan, "bidders", pending, budget)
            newest = take["last_award"].cast(pl.Utf8).drop_nulls()
            if take.height == pending.height and newest.len():
                plan.watermark.bidders = max(str(newest.max()), watermark.bidders)

    if backlog.height:
        take, budget = _take(plan, "tenders", backlog, budget, part="tenders_backlog")
        if take.height:
            plan.watermark.tenders = str(take["fetched_at"][-1])

    plan.watermark.loaded_rows_today = plan.rows
    plan.watermark.writes_today = used + plan.writes
    return plan


def add_marker(plan: Plan, token: str) -> None:
    """End the load with a row that can only exist in D1 if every statement before it ran."""
    plan.statements.append(f"INSERT OR REPLACE INTO meta (key, value) VALUES ('{MARKER_KEY}', {_sql_value(token)});")
    plan.writes += 1
    plan.watermark.writes_today += 1


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


def _wrangler(args: list[str], runner):
    """Run wrangler with every argument passed through intact.

    Never shell=True with a list: on Linux that runs only the first element, bare `npx`, and the
    shell swallows the rest. Resolving the executable instead works on Windows too, where npx is a
    .cmd file.
    """
    exe = shutil.which("npx") or "npx"
    return runner([exe, "wrangler", *args], cwd="worker", capture_output=True, encoding="utf-8", errors="replace")


def _results(stdout: str | None) -> list[dict]:
    """The JSON wrangler prints under --json, or an error if it printed none or reported a failure."""
    text = (stdout or "").strip()
    try:
        data = json.loads(text)
    except ValueError:
        start = text.find("\n[")
        try:
            data = json.loads(text[start + 1:]) if start >= 0 else None
        except ValueError:
            data = None
        if data is None:
            raise RuntimeError("wrangler printed no JSON result") from None
    if not isinstance(data, list) or not data or not all(isinstance(d, dict) and d.get("success") for d in data):
        raise RuntimeError("wrangler did not report success for every statement")
    return data


def execute(files: list[Path], database: str, remote: bool, marker: str = "", runner=subprocess.run) -> None:
    target = "--remote" if remote else "--local"
    for path in files:
        result = _wrangler(["d1", "execute", database, target, "--file", str(Path(path).resolve()), "--yes", "--json"], runner)
        if result.returncode != 0:
            detail = ((result.stderr or "") + (result.stdout or ""))[-2000:]
            raise RuntimeError(f"wrangler failed on {Path(path).name}: {detail}")
        try:
            _results(result.stdout)
        except RuntimeError as e:
            raise RuntimeError(f"wrangler did not confirm {Path(path).name}: {e}") from None
    if marker:
        result = _wrangler(["d1", "execute", database, target, "--command",
                            f"SELECT value FROM meta WHERE key = '{MARKER_KEY}'", "--yes", "--json"], runner)
        if result.returncode != 0:
            raise RuntimeError(f"could not read the load marker back: {((result.stderr or '') + (result.stdout or ''))[-500:]}")
        rows = _results(result.stdout)[0].get("results") or []
        if not rows or rows[0].get("value") != marker:
            raise RuntimeError("the load marker is not in D1, so the statements before it did not land")


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
    marker = ""
    if plan.statements:
        marker = f"{plan.watermark.day}-{uuid.uuid4().hex[:12]}"
        add_marker(plan, marker)
    files = write_sql(plan, Path("build") / "d1")
    left = ", ".join(f"{k} {v} rows deferred" for k, v in plan.skipped.items()) or "nothing deferred"
    print(f"d1 load: {plan.rows} rows, about {plan.writes} writes ({plan.watermark.writes_today} today), "
          f"{len(plan.statements)} statements across {len(files)} files; {left}")
    if a.dry_run or not files:
        return 0
    try:
        execute(files, a.database, remote=not a.local, marker=marker)
    except RuntimeError as e:
        # A blocked or failed load must not fail the nightly job or move the watermark.
        print(f"d1 load: skipped, {str(e)[:300]}")
        return 0
    plan.watermark.save(Path(a.watermark))
    bidders = plan.watermark.bidders or f"first load through {plan.watermark.bidders_after or 'none yet'}"
    print(f"d1 load: done and confirmed in D1, watermark live={plan.watermark.live} "
          f"tenders={plan.watermark.tenders} bidders={bidders}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
