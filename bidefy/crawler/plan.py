"""Annual Procurement Plan estimates for live tenders, read while each tender is still open.

Every tender page names its plan (App ID) and package number, and the portal's public plan search
lists each package's estimated cost. On 119 of 120 awarded tenders probed on 2026-11-03 the estimate
sat close to the award: the median award was 0.91 of it on OTM and about all of it on RFQ, against a
7.6 percent error for the security route and 21 percent for the history route.

That probe read today's plans for past tenders, and a buyer can revise its plan after the award, so
the estimate may already have been moved toward the contract value. The honest test is forward: read
the estimate while the tender is open and compare it once the award comes in. That is what this
collects, and why every row keeps the time it was read. tools/plan_forward_test.py does the
comparison. Nothing here feeds a model yet.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from . import parse, store
from .session import EgpSession, HttpFailure, SessionExpired

ENDPOINT = "plan_estimates"
FLUSH_EVERY = 100
MAX_CONSECUTIVE_FAILURES = 5

_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_PKG_ID_RE = re.compile(r"pkgId=(\d+)")


@dataclass
class Summary:
    matched: int = 0
    unmatched: int = 0   # the plan page had no line for this package number: recorded, not guessed
    no_ref: int = 0      # the tender page named no plan
    failed: int = 0
    status: str = "done"


def _text(cell: str) -> str:
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", cell)).strip()


def _norm(package_no: str) -> str:
    return re.sub(r"\s+", "", package_no or "").strip(",").casefold()


def parse_plan_rows(html: str) -> list[dict]:
    """Package lines from a plan search page: S. No. | APP ID | entity | district | nature |
    package number and description | estimated cost (BDT) and method."""
    out = []
    for row in _ROW_RE.findall(html):
        cells = _CELL_RE.findall(row)
        if len(cells) < 7 or not _text(cells[1]).isdigit():
            continue
        package_no = _text(cells[5].split("<br", 1)[0]).rstrip(",").strip()
        cost, _, method = _text(cells[6]).partition(",")
        try:
            estimate = float(cost.replace(",", "").strip())
        except ValueError:
            estimate = None
        pkg = _PKG_ID_RE.search(cells[5])
        out.append({
            "app_id": _text(cells[1]),
            "nature": _text(cells[4]).rstrip(","),
            "package_no": package_no,
            "pkg_id": pkg.group(1) if pkg else "",
            "estimate_bdt": estimate,
            "plan_method": method.strip(),
        })
    return out


def match_package(rows: list[dict], package_no: str) -> dict | None:
    """The plan line for exactly this package. The portal's search matches by substring, so a
    near miss is a different package and does not count."""
    want = _norm(package_no)
    hits = [r for r in rows if want and _norm(r["package_no"]) == want]
    return hits[0] if len(hits) == 1 else None


def pick_live(tenders: pl.DataFrame, done: set[str], n: int) -> list[str]:
    """Live tenders with no plan row yet, newest first: the newest close last, so they are the
    ones still certain to be open when the estimate is read."""
    if tenders.is_empty() or "status" not in tenders.columns:
        return []
    live = tenders.filter((pl.col("status") == "Live")
                          & ~pl.col("tender_id").cast(pl.Utf8).is_in(sorted(done)))
    live = live.sort(["published_at", "tender_id"], descending=True, nulls_last=True)
    return live["tender_id"].cast(pl.Utf8).head(n).to_list()


def stored_refs(details: pl.DataFrame) -> dict[str, tuple[str, str]]:
    """Plan references already on file from detail pages, so those tenders need no second visit."""
    if details.is_empty() or "app_id" not in details.columns:
        return {}
    have = details.filter((pl.col("app_id").fill_null("") != "") & (pl.col("package_no").fill_null("") != ""))
    return {r["tender_id"]: (r["app_id"], r["package_no"])
            for r in have.select("tender_id", "app_id", "package_no").to_dicts()}


def collect(session, ids: list[str], refs: dict[str, tuple[str, str]], data_root: Path,
            time_budget_s: float, now=time.monotonic, log=print) -> Summary:
    started = now()
    summary = Summary()
    buffer: list[dict] = []
    consecutive = 0
    for tender_id in ids:
        if now() - started > time_budget_s:
            summary.status = "budget"
            break
        try:
            if tender_id in refs:
                app_id, package_no = refs[tender_id]
            else:
                d = parse.parse_detail(session.detail(tender_id))
                app_id, package_no = d.get("app_id", ""), d.get("package_no", "")
            hit, n_rows = None, 0
            if app_id and package_no:
                rows = parse_plan_rows(session.plan_search(app_id, package_no))
                n_rows, hit = len(rows), match_package(rows, package_no)
        except (HttpFailure, SessionExpired) as e:
            summary.failed += 1
            consecutive += 1
            log(f"plan {tender_id}: {e}")
            if consecutive >= MAX_CONSECUTIVE_FAILURES:
                summary.status = "aborted"
                break
            continue
        consecutive = 0
        if not (app_id and package_no):
            summary.no_ref += 1
        elif hit:
            summary.matched += 1
        else:
            summary.unmatched += 1
        buffer.append({
            "tender_id": tender_id, "app_id": app_id, "package_no": package_no,
            "matched": hit is not None, "plan_rows": n_rows,
            "estimate_bdt": hit["estimate_bdt"] if hit else None,
            "plan_method": hit["plan_method"] if hit else "",
            "plan_package_no": hit["package_no"] if hit else "",
            "pkg_id": hit["pkg_id"] if hit else "",
        })
        if len(buffer) >= FLUSH_EVERY:
            store.append_rows(buffer, data_root, ENDPOINT)
            buffer = []
    if buffer:
        store.append_rows(buffer, data_root, ENDPOINT)
    log(f"plan: {summary.status}, matched {summary.matched}, unmatched {summary.unmatched}, "
        f"no plan reference {summary.no_ref}, failed {summary.failed}")
    return summary


def _write_checkpoint(path: Path, recorded: int, waiting: int, summary: Summary) -> None:
    # same shape as a crawl checkpoint, so the command centre shows it as "recorded / recorded + waiting"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "endpoint": "plan_estimates",
        "next_page": recorded + 1,
        "total_pages": recorded + waiting,
        "remaining_live": waiting,
        "updated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "last_run_status": summary.status,
        "last_run_matched": summary.matched,
        "last_run_unmatched": summary.unmatched,
        "last_run_no_ref": summary.no_ref,
        "last_run_failed": summary.failed,
    }, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Read plan estimates for live tenders")
    ap.add_argument("--data-root", default="data")
    ap.add_argument("--n", type=int, default=5000)
    ap.add_argument("--budget-min", type=float, default=40)
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--checkpoint", default="checkpoints/plan_estimates.json")
    a = ap.parse_args(argv)
    root = Path(a.data_root)
    tenders = store.load_all(root, "tenders")
    done = store.known_ids(root, ENDPOINT)
    ids = pick_live(tenders, done, a.n)
    summary = collect(EgpSession(min_interval=a.interval), ids, stored_refs(store.load_all(root, "details")),
                      root, a.budget_min * 60) if ids else Summary()
    done = store.known_ids(root, ENDPOINT)
    waiting = len(pick_live(tenders, done, 10**9))
    _write_checkpoint(Path(a.checkpoint), len(done), waiting, summary)
    return 0 if summary.status != "aborted" else 1


if __name__ == "__main__":
    raise SystemExit(main())
