"""Fetch tender detail pages for a sample of ids; stores category tags and security amounts."""
from __future__ import annotations

import argparse
import json
import random
import time
from dataclasses import dataclass
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
    ap.add_argument("--source", choices=["tenders", "contracts", "both", "live"], default="tenders",
                    help="live fetches every open tender that has no detail row yet: the security amount is "
                         "the strongest predictor of the award value, so the band depends on it. "
                         "contracts gives detail pages for awarded tenders, which is how the model learns the link.")
    ap.add_argument("--since", default="", help="only ids advertised or published on or after this date")
    ap.add_argument("--signed-since", default="", help="contracts only: awards signed on or after this date")
    a = ap.parse_args(argv)
    root = Path(a.data_root)
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
