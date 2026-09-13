"""Crawl policy: backfill walks pages from the checkpoint; delta walks newest-first until nothing is new."""
from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import parse, store
from .checkpoint import Checkpoint
from .session import EgpSession, HttpFailure, SessionExpired

MAX_CONSECUTIVE_FAILURES = 3
PAGE_SIZE = 200
PARSERS: dict[str, Callable[[str], tuple[list[dict], int]]] = {
    "tenders": parse.parse_tender_rows,
    "contracts": parse.parse_contract_rows,
}


@dataclass
class Summary:
    endpoint: str
    mode: str
    pages: int = 0
    rows: int = 0
    status: str = "running"     # done | budget | aborted


def _fetch(session, endpoint: str, page: int, parser, log) -> tuple[list[dict], int] | None:
    """One page with the failure policy applied by the caller. Returns None on failure."""
    try:
        html = session.list_page(endpoint, page, PAGE_SIZE)
    except (HttpFailure, SessionExpired) as e:
        log(f"page {page}: {type(e).__name__}: {e}")
        return None
    rows, total = parser(html)
    if not rows:
        log(f"page {page}: zero rows")
        return None
    return rows, total


def crawl(
    session: EgpSession,
    endpoint: str,
    mode: str,
    data_root: Path,
    checkpoint_path: Path,
    time_budget_s: float,
    now: Callable[[], float] = time.monotonic,
    log: Callable[[str], None] = print,
) -> Summary:
    parser = PARSERS[endpoint]
    cp = Checkpoint.load(checkpoint_path, endpoint=endpoint)
    summary = Summary(endpoint=endpoint, mode=mode)
    started = now()
    failures = 0

    if mode == "backfill":
        page = cp.next_page
        while True:
            if cp.total_pages and page > cp.total_pages:
                summary.status = "done"
                break
            if now() - started > time_budget_s:
                summary.status = "budget"
                break
            got = _fetch(session, endpoint, page, parser, log)
            if got is None:
                failures += 1
                if failures >= MAX_CONSECUTIVE_FAILURES:
                    summary.status = "aborted"
                    break
                continue
            failures = 0
            rows, total = got
            store.append_rows(rows, data_root, endpoint)
            summary.pages += 1
            summary.rows += len(rows)
            cp.total_pages = total or cp.total_pages
            cp.next_page = page + 1
            cp.mode = "backfill"
            cp.save(checkpoint_path)
            page += 1

    elif mode == "delta":
        known = store.known_ids(data_root, endpoint)
        page = 1
        newest = cp.newest_id_seen
        while True:
            if now() - started > time_budget_s:
                summary.status = "budget"
                break
            got = _fetch(session, endpoint, page, parser, log)
            if got is None:
                failures += 1
                if failures >= MAX_CONSECUTIVE_FAILURES:
                    summary.status = "aborted"
                    break
                continue
            failures = 0
            rows, total = got
            new_rows = [r for r in rows if r["tender_id"] not in known]
            summary.pages += 1
            if new_rows:
                store.append_rows(new_rows, data_root, endpoint)
                summary.rows += len(new_rows)
                known.update(r["tender_id"] for r in new_rows)
                newest = max([newest] + [r["tender_id"] for r in new_rows], key=lambda s: int(s or 0))
            if len(new_rows) < len(rows) or (total and page >= total):
                summary.status = "done"
                break
            page += 1
        cp.mode = "delta"
        cp.newest_id_seen = newest
        cp.save(checkpoint_path)
    else:
        raise ValueError(f"unknown mode {mode}")

    cp.last_run_pages, cp.last_run_rows, cp.last_run_status = summary.pages, summary.rows, summary.status
    cp.save(checkpoint_path)
    log(f"{endpoint} {mode}: {summary.status}, {summary.pages} pages, {summary.rows} rows")
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Crawl the e-GP public index")
    ap.add_argument("--endpoint", choices=list(PARSERS), required=True)
    ap.add_argument("--mode", choices=["backfill", "delta"], required=True)
    ap.add_argument("--budget-min", type=float, default=300)
    ap.add_argument("--data-root", default="data")
    ap.add_argument("--checkpoints", default="checkpoints")
    ap.add_argument("--interval", type=float, default=1.0, help="seconds between requests")
    a = ap.parse_args(argv)
    session = EgpSession(min_interval=a.interval)
    summary = crawl(
        session, a.endpoint, a.mode, Path(a.data_root), Path(a.checkpoints) / f"{a.endpoint}.json",
        time_budget_s=a.budget_min * 60,
    )
    return 0 if summary.status in ("done", "budget") else 1


if __name__ == "__main__":
    raise SystemExit(main())
