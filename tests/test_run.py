import re
from pathlib import Path

import pytest

from bidefy.crawler import run, store
from bidefy.crawler.checkpoint import Checkpoint
from bidefy.crawler.session import HttpFailure

FIX = Path(__file__).parent / "fixtures"
PAGE = (FIX / "tenders_page.html").read_text(encoding="utf-8")


class FakeSession:
    """Serves the fixture for every page; fails when told to."""

    def __init__(self, fail_times=0, total_pages_override=None):
        self.calls = []
        self.fail_times = fail_times
        self.html = PAGE
        if total_pages_override is not None:
            self.html = re.sub(r'id="totalPages" value="\d+"', f'id="totalPages" value="{total_pages_override}"', PAGE)

    def list_page(self, endpoint, page, size=200):
        self.calls.append(page)
        if self.fail_times > 0:
            self.fail_times -= 1
            raise HttpFailure("boom")
        return self.html


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        self.t += 10.0      # each check advances ten seconds
        return self.t


def _cp(tmp_path, **kw):
    return tmp_path / "checkpoints" / "tenders.json"


def test_backfill_advances_checkpoint_and_stores_rows(tmp_path):
    session = FakeSession(total_pages_override=3)
    summary = run.crawl(session, "tenders", "backfill", tmp_path / "data", _cp(tmp_path), time_budget_s=10_000)
    assert session.calls == [1, 2, 3]
    cp = Checkpoint.load(_cp(tmp_path))
    assert cp.next_page == 4 and cp.total_pages == 3 and cp.backfill_done
    assert summary.pages == 3 and summary.rows == 600 and summary.status == "done"
    assert len(store.known_ids(tmp_path / "data", "tenders")) == 200   # same ids every page, deduped on read


def test_backfill_resumes_from_checkpoint(tmp_path):
    Checkpoint(endpoint="tenders", next_page=2, total_pages=3).save(_cp(tmp_path))
    session = FakeSession(total_pages_override=3)
    run.crawl(session, "tenders", "backfill", tmp_path / "data", _cp(tmp_path), time_budget_s=10_000)
    assert session.calls == [2, 3]


def test_backfill_stops_on_time_budget(tmp_path):
    session = FakeSession(total_pages_override=50)
    summary = run.crawl(session, "tenders", "backfill", tmp_path / "data", _cp(tmp_path), time_budget_s=25, now=FakeClock())
    assert summary.status == "budget"
    assert 1 <= len(session.calls) <= 3
    assert Checkpoint.load(_cp(tmp_path)).next_page == len(session.calls) + 1


def test_three_consecutive_failures_abort_without_moving_checkpoint(tmp_path):
    session = FakeSession(fail_times=3, total_pages_override=5)
    summary = run.crawl(session, "tenders", "backfill", tmp_path / "data", _cp(tmp_path), time_budget_s=10_000)
    assert summary.status == "aborted"
    assert Checkpoint.load(_cp(tmp_path)).next_page == 1


def test_two_failures_then_success_continues(tmp_path):
    session = FakeSession(fail_times=2, total_pages_override=1)
    summary = run.crawl(session, "tenders", "backfill", tmp_path / "data", _cp(tmp_path), time_budget_s=10_000)
    assert summary.status == "done" and summary.pages == 1


def test_delta_stops_when_page_has_no_new_ids(tmp_path):
    session = FakeSession(total_pages_override=3)
    run.crawl(session, "tenders", "backfill", tmp_path / "data", _cp(tmp_path), time_budget_s=10_000)
    session.calls.clear()
    summary = run.crawl(session, "tenders", "delta", tmp_path / "data", _cp(tmp_path), time_budget_s=10_000)
    assert session.calls == [1]
    assert summary.rows == 0 and summary.status == "done"
    cp = Checkpoint.load(_cp(tmp_path))
    assert cp.mode == "delta" and cp.next_page == 4    # backfill position untouched


def test_delta_on_empty_store_stores_first_page(tmp_path):
    session = FakeSession(total_pages_override=1)
    summary = run.crawl(session, "tenders", "delta", tmp_path / "data", _cp(tmp_path), time_budget_s=10_000)
    assert summary.rows == 200
