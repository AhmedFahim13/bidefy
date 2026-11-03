"""Fetch tender detail pages for a sample of ids; stores category tags and security amounts."""
from __future__ import annotations

import argparse
import json
import random
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from . import parse, store
from .session import EgpSession, HttpFailure, SessionExpired

ENDPOINT = "details"
FLUSH_EVERY = 100
MAX_CONSECUTIVE_FAILURES = 5


@dataclass
class Summary:
    fetched: int = 0
    failed: int = 0      # transport errors, which count toward the abort threshold
    empty: int = 0       # the portal served a stub: real data, not a fault
    status: str = "done"


def pick_ids(candidates: list[str], done: set[str], n: int, seed: int = 0) -> list[str]:
    pool = sorted(set(candidates) - set(done))
    rng = random.Random(seed)
    rng.shuffle(pool)
    return pool[:n]


def _archive_index(tenders: pl.DataFrame, contracts: pl.DataFrame) -> pl.DataFrame:
    """Every id in the tender index once, with whether it was awarded and its best-known date.

    Awards whose notice is missing from the tender index are left out: 27 of 30 sampled
    (2026-11-03) served an empty stub, so the 420,958 of them would cost five days of polite
    crawling for almost nothing.
    """
    if tenders.is_empty():
        return pl.DataFrame(schema={"tender_id": pl.Utf8, "at": pl.Utf8, "awarded": pl.Boolean})
    idx = tenders.select(pl.col("tender_id").cast(pl.Utf8),
                         pl.col("published_at").cast(pl.Utf8).alias("at")).unique("tender_id")
    if contracts.is_empty():
        return idx.with_columns(pl.lit(False).alias("awarded"))
    won = (contracts.select(pl.col("tender_id").cast(pl.Utf8),
                            pl.col("advertised_at").cast(pl.Utf8).alias("advertised"))
           .group_by("tender_id").agg(pl.col("advertised").drop_nulls().max())
           .with_columns(pl.lit(True).alias("awarded")))
    return (idx.join(won, on="tender_id", how="left")
            .with_columns(pl.col("awarded").fill_null(False),
                          pl.coalesce("at", "advertised").alias("at"))
            .drop("advertised"))


def archive_ids(tenders: pl.DataFrame, contracts: pl.DataFrame, done: set[str], n: int) -> list[str]:
    """Every tender in the index without a detail row: awarded ones first, then newest first.

    Awarded tenders come first because their pages feed both models: the category label for the
    classifier and the security amount the award model's best route is built on. Newest first
    because recent prices say more about today's than 2013's do. The order is fixed, so each run
    carries on where the last one stopped.
    """
    idx = _archive_index(tenders, contracts).filter(~pl.col("tender_id").is_in(sorted(done)))
    idx = idx.sort(["awarded", "at", "tender_id"], descending=True, nulls_last=True)
    return idx["tender_id"].head(n).to_list()


def archive_progress(tenders: pl.DataFrame, contracts: pl.DataFrame, done: set[str]) -> dict:
    ids = set(_archive_index(tenders, contracts)["tender_id"].to_list())
    fetched = len(ids & done)
    return {"indexed": len(ids), "fetched": fetched, "remaining": len(ids) - fetched}


def _write_archive_checkpoint(path: Path, progress: dict, summary: Summary) -> None:
    # same shape as a crawl checkpoint, so the command centre shows it as "fetched / indexed"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "endpoint": "details_archive",
        "next_page": progress["fetched"] + 1,
        "total_pages": progress["indexed"],
        "remaining": progress["remaining"],
        "updated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "last_run_status": summary.status,
        "last_run_fetched": summary.fetched,
        "last_run_empty": summary.empty,
        "last_run_failed": summary.failed,
    }, indent=2) + "\n", encoding="utf-8")


def _row(tender_id: str, d: dict) -> dict:
    return {
        "tender_id": tender_id or d.get("tender_id", ""),
        "categories": json.dumps(d.get("categories", []), ensure_ascii=False),
        "security_bdt": d.get("security_bdt"),
        "document_price_bdt": d.get("document_price_bdt"),
        "brief": d.get("brief", ""),
        "budget_type": d.get("budget_type", ""),
        "source_of_funds": d.get("source_of_funds", ""),
        "procuring_entity_district": d.get("procuring_entity_district", ""),
        "method": d.get("method", ""),
    }


def fetch(session, ids: list[str], data_root: Path, time_budget_s: float, now=time.monotonic, log=print) -> Summary:
    started = now()
    summary = Summary()
    buffer: list[dict] = []
    consecutive = 0
    for tender_id in ids:
        if now() - started > time_budget_s:
            summary.status = "budget"
            break
        try:
            html = session.detail(tender_id)
        except (HttpFailure, SessionExpired) as e:
            summary.failed += 1
            consecutive += 1
            log(f"detail {tender_id}: {e}")
            if consecutive >= MAX_CONSECUTIVE_FAILURES:
                summary.status = "aborted"
                break
            continue
        consecutive = 0
        d = parse.parse_detail(html)
        if not d.get("procuring_entity"):
            # The portal serves a stub for some archived tenders. Record it so the id is not
            # re-fetched every night, and move on; it is not a transport fault.
            summary.empty += 1
            buffer.append(_row(tender_id, d))
            continue
        buffer.append(_row(tender_id, d))
        summary.fetched += 1
        if len(buffer) >= FLUSH_EVERY:
            store.append_rows(buffer, data_root, ENDPOINT)
            buffer = []
    if buffer:
        store.append_rows(buffer, data_root, ENDPOINT)
    log(f"details: {summary.status}, fetched {summary.fetched}, empty {summary.empty}, failed {summary.failed}")
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fetch a sample of tender detail pages")
    ap.add_argument("--data-root", default="data")
    ap.add_argument("--n", type=int, default=3000)
    ap.add_argument("--budget-min", type=float, default=30)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--source", choices=["tenders", "contracts", "both", "live", "archive"], default="tenders",
                    help="live fetches every open tender that has no detail row yet: the security amount is "
                         "the strongest predictor of the award value, so the band depends on it. "
                         "contracts gives detail pages for awarded tenders, which is how the model learns the link. "
                         "archive works through every indexed tender still missing a detail row, awarded "
                         "first and newest first, so repeated runs label the whole archive.")
    ap.add_argument("--checkpoint", default="checkpoints/details_archive.json",
                    help="archive only: progress file, which the command centre shows beside the crawls")
    ap.add_argument("--since", default="", help="only ids advertised or published on or after this date")
    ap.add_argument("--signed-since", default="", help="contracts only: awards signed on or after this date")
    a = ap.parse_args(argv)
    root = Path(a.data_root)
    if a.source == "archive":
        tenders, contracts = store.load_all(root, "tenders"), store.load_all(root, "contracts")
        done = store.known_ids(root, ENDPOINT)
        print(f"archive: {archive_progress(tenders, contracts, done)}")
        ids = archive_ids(tenders, contracts, done, a.n)
        summary = fetch(EgpSession(min_interval=a.interval), ids, root, a.budget_min * 60) if ids else Summary()
        progress = archive_progress(tenders, contracts, store.known_ids(root, ENDPOINT))
        _write_archive_checkpoint(Path(a.checkpoint), progress, summary)
        print(f"archive: {progress}" if ids else "archive: every indexed tender has a detail row")
        return 0 if summary.status != "aborted" else 1
    sources = ("tenders", "contracts") if a.source == "both" else (("tenders",) if a.source == "live" else (a.source,))
    pool: list[str] = []
    for name in sources:
        df = store.load_all(root, name)
        if df.is_empty():
            continue
        if a.source == "live" and "status" in df.columns:
            df = df.filter(pl.col("status") == "Live")
        if a.since:
            col = "advertised_at" if "advertised_at" in df.columns else "published_at"
            if col in df.columns:
                df = df.filter(pl.col(col).fill_null("") >= a.since)
        if a.signed_since and "signed_on" in df.columns:
            df = df.filter(pl.col("signed_on").fill_null("") >= a.signed_since)
        pool += df["tender_id"].cast(str).to_list()
    if not pool:
        print("nothing to sample from")
        return 0
    done = store.known_ids(root, ENDPOINT)
    if a.source == "live":
        seen = set()
        ids = [i for i in reversed(pool) if i not in done and not (i in seen or seen.add(i))][: a.n]
    else:
        ids = pick_ids(pool, done, a.n, a.seed)
    summary = fetch(EgpSession(min_interval=a.interval), ids, root, a.budget_min * 60)
    return 0 if summary.status != "aborted" else 1


if __name__ == "__main__":
    raise SystemExit(main())
