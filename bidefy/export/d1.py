"""Plan and execute capped, resumable loads from data/clean into D1 through wrangler."""
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
DEFAULT_MAX_ROWS = 90_000
TABLES = {
    "tenders": ["tender_id", "reference", "status", "note", "nature", "title", "ministry", "organization",
                "procuring_entity", "pe_id", "procurement_type", "method", "published_at", "closing_at", "fetched_at"],
    "contracts": ["tender_id", "reference", "title", "advertised_at", "ministry", "procuring_entity", "pe_id",
                  "method", "district", "signed_on", "awardee", "bidder_id", "value_crore", "fetched_at"],
    "bidders": ["bidder_id", "canonical_name", "variants", "n_awards", "total_value_crore", "first_award", "last_award"],
    "procuring_entities": ["pe_id", "name", "ministry", "n_contracts", "n_tenders"],
}


@dataclass
class Watermark:
    tenders: str = ""
    contracts: str = ""
    loaded_rows_today: int = 0
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
        return cls(**json.loads(Path(path).read_text(encoding="utf-8")))


@dataclass
class Plan:
    statements: list[str] = field(default_factory=list)
    rows: int = 0
    watermark: Watermark = field(default_factory=Watermark)


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


def plan_load(root: Path, watermark: Watermark, max_rows: int = DEFAULT_MAX_ROWS, today: str | None = None) -> Plan:
    """Recent tenders and contracts newer than the watermark (by fetched_at), then all bidders and entities."""
    today_d = date.fromisoformat(today) if today else date.today()
    window_start = (today_d - timedelta(days=30 * WINDOW_MONTHS)).isoformat()
    plan = Plan(watermark=Watermark(tenders=watermark.tenders, contracts=watermark.contracts, day=today_d.isoformat()))
    budget = max_rows

    for table, date_col in (("tenders", "published_at"), ("contracts", "signed_on")):
        df = _read(root, table)
        if df.is_empty() or budget <= 0:
            continue
        if "fetched_at" not in df.columns:
            df = df.with_columns(pl.lit("").alias("fetched_at"))
        mark = getattr(watermark, table)
        recent = df.filter(pl.col(date_col).fill_null("") >= window_start) if date_col in df.columns else df
        if table == "tenders" and "status" in df.columns:
            recent = pl.concat([recent, df.filter(pl.col("status") == "Live")]).unique(subset=["tender_id"], keep="last")
        pending = recent.filter(pl.col("fetched_at").cast(pl.Utf8) > mark).sort("fetched_at")
        take = pending.head(budget)
        if take.is_empty():
            continue
        plan.statements += _inserts(table, take)
        plan.rows += take.height
        budget -= take.height
        setattr(plan.watermark, table, str(take["fetched_at"][-1]))

    for table in ("bidders", "procuring_entities"):
        df = _read(root, table)
        if df.is_empty() or budget <= 0:
            continue
        take = df.head(budget)
        plan.statements += _inserts(table, take)
        plan.rows += take.height
        budget -= take.height
    plan.watermark.loaded_rows_today = plan.rows
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
    ap.add_argument("--max-rows", type=int, default=DEFAULT_MAX_ROWS)
    ap.add_argument("--database", default="bidefy")
    ap.add_argument("--local", action="store_true", help="load the local wrangler D1 instead of remote")
    ap.add_argument("--dry-run", action="store_true", help="write SQL files, do not execute")
    a = ap.parse_args(argv)
    wm = Watermark.load(Path(a.watermark))
    plan = plan_load(Path(a.data_root), wm, max_rows=a.max_rows)
    files = write_sql(plan, Path("build") / "d1")
    print(f"d1 load: {plan.rows} rows in {len(plan.statements)} statements across {len(files)} files")
    if a.dry_run or not files:
        return 0
    execute(files, a.database, remote=not a.local)
    plan.watermark.save(Path(a.watermark))
    print(f"d1 load: done, watermark tenders={plan.watermark.tenders} contracts={plan.watermark.contracts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
