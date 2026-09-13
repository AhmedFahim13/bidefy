"""Fetch tender detail pages for a sample of ids; stores category tags and security amounts."""
from __future__ import annotations

import argparse
import json
import random
import time
from dataclasses import dataclass
from pathlib import Path

from . import parse, store
from .session import EgpSession, HttpFailure, SessionExpired

ENDPOINT = "details"
FLUSH_EVERY = 100


@dataclass
class Summary:
    fetched: int = 0
    failed: int = 0
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
            d = parse.parse_detail(html)
            if not d.get("procuring_entity"):
                raise RuntimeError("empty detail")
            buffer.append(_row(tender_id, d))
            summary.fetched += 1
            consecutive = 0
        except (HttpFailure, SessionExpired, RuntimeError) as e:
            summary.failed += 1
            consecutive += 1
            log(f"detail {tender_id}: {e}")
            if consecutive >= 3:
                summary.status = "aborted"
                break
        if len(buffer) >= FLUSH_EVERY:
            store.append_rows(buffer, data_root, ENDPOINT)
            buffer = []
    if buffer:
        store.append_rows(buffer, data_root, ENDPOINT)
    log(f"details: {summary.status}, fetched {summary.fetched}, failed {summary.failed}")
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fetch a sample of tender detail pages")
    ap.add_argument("--data-root", default="data")
    ap.add_argument("--n", type=int, default=3000)
    ap.add_argument("--budget-min", type=float, default=30)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--interval", type=float, default=1.0)
    a = ap.parse_args(argv)
    root = Path(a.data_root)
    tenders = store.load_all(root, "tenders")
    if tenders.is_empty():
        print("no tenders yet")
        return 0
    done = store.known_ids(root, ENDPOINT)
    ids = pick_ids(tenders["tender_id"].cast(str).to_list(), done, a.n, a.seed)
    summary = fetch(EgpSession(min_interval=a.interval), ids, root, a.budget_min * 60)
    return 0 if summary.status != "aborted" else 1


if __name__ == "__main__":
    raise SystemExit(main())
