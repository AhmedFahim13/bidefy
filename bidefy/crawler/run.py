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
DELTA_MAX_PAGES = 50
FLUSH_EVERY_PAGES = 50
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
    """One page. Returns (rows, total) from the parser, or None on a transport failure."""
    try:
        html = session.list_page(endpoint, page, PAGE_SIZE)
    except (HttpFailure, SessionExpired) as e:
        log(f"page {page}: {type(e).__name__}: {e}")
        return None
    return parser(html)


def _zero_rows_is_end_of_data(cp: Checkpoint, page: int) -> bool:
    """A page with zero rows is the end of the data once we know its number is
    at or past the last known page. Otherwise it looks like a bad response."""
    return bool(cp.total_pages) and page >= cp.total_pages


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
    buffer: list[dict] = []

    def flush() -> None:
        """Write whatever has accumulated in the buffer, then save the checkpoint,
        so a crash can never leave the checkpoint ahead of the data. The
        checkpoint is saved even when the buffer is empty, so mode switches and
        the run summary always reach disk at a flush point."""
        nonlocal buffer
        if buffer:
            store.append_rows(buffer, data_root, endpoint)
            buffer = []
        cp.save(checkpoint_path)

    if mode == "backfill":
        cp.mode = "backfill"
        page = cp.next_page
        buffered_pages = 0
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
            rows, total = got
            if total > 0:
                cp.total_pages = total
            if not rows:
                if _zero_rows_is_end_of_data(cp, page):
                    log(f"page {page}: zero rows, end of data (total_pages={cp.total_pages})")
                    summary.status = "done"
                    break
                log(f"page {page}: zero rows")
                failures += 1
                if failures >= MAX_CONSECUTIVE_FAILURES:
                    summary.status = "aborted"
                    break
                continue
            failures = 0
            buffer.extend(rows)
            buffered_pages += 1
            summary.pages += 1
            summary.rows += len(rows)
            cp.next_page = page + 1
            if buffered_pages >= FLUSH_EVERY_PAGES:
                flush()
                buffered_pages = 0
            page += 1
        cp.last_run_pages, cp.last_run_rows, cp.last_run_status = summary.pages, summary.rows, summary.status
        flush()

    elif mode == "delta":
        cp.mode = "delta"
        known = store.known_ids(data_root, endpoint)
        page = 1
        newest = cp.newest_id_seen
        buffered_pages = 0
        while True:
            if now() - started > time_budget_s:
                summary.status = "budget"
                break
            if page > DELTA_MAX_PAGES:
                log(f"page {page}: exceeded DELTA_MAX_PAGES ({DELTA_MAX_PAGES}), stopping")
                summary.status = "done"
                break
            got = _fetch(session, endpoint, page, parser, log)
            if got is None:
                failures += 1
                if failures >= MAX_CONSECUTIVE_FAILURES:
                    summary.status = "aborted"
                    break
                continue
            rows, total = got
            if total > 0:
                cp.total_pages = total
            if not rows:
                if _zero_rows_is_end_of_data(cp, page):
                    log(f"page {page}: zero rows, end of data (total_pages={cp.total_pages})")
                    summary.status = "done"
                    break
                log(f"page {page}: zero rows")
                failures += 1
                if failures >= MAX_CONSECUTIVE_FAILURES:
                    summary.status = "aborted"
                    break
                continue
            failures = 0
            new_rows = [r for r in rows if r["tender_id"] not in known]
            summary.pages += 1
            buffered_pages += 1
            if new_rows:
                buffer.extend(new_rows)
                summary.rows += len(new_rows)
                known.update(r["tender_id"] for r in new_rows)
                newest = max([newest] + [r["tender_id"] for r in new_rows], key=lambda s: int(s or 0))
            cp.newest_id_seen = newest
            if buffered_pages >= FLUSH_EVERY_PAGES:
                flush()
                buffered_pages = 0
            if not new_rows:
                log(f"page {page}: no new ids, stopping")
                summary.status = "done"
                break
            if total and page >= total:
                log(f"page {page}: reached last page ({total})")
                summary.status = "done"
                break
            page += 1
        cp.last_run_pages, cp.last_run_rows, cp.last_run_status = summary.pages, summary.rows, summary.status
        flush()
    else:
        raise ValueError(f"unknown mode {mode}")

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
