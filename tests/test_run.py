import re
from pathlib import Path

from bidefy.crawler import run, store
from bidefy.crawler.checkpoint import Checkpoint
from bidefy.crawler.session import HttpFailure

FIX = Path(__file__).parent / "fixtures"
PAGE = (FIX / "tenders_page.html").read_text(encoding="utf-8")

_TOTAL_RE = re.compile(r'id="totalPages" value="\d+"')
_ID_INPUT_RE = re.compile(r'name="id" value="(\d+)"')


def _with_total(html: str, total: int) -> str:
    return _TOTAL_RE.sub(f'id="totalPages" value="{total}"', html)


def _rewrite_ids(html: str, transform) -> str:
    """Replace every hidden id input's value using transform(old_id) -> new_id.

    parse_tender_rows reads the tender id from this hidden input (embedded in
    the title cell's form), so rewriting it is enough to change the ids a page
    reports, independent of the merely-visible id line in the first column.
    """
    return _ID_INPUT_RE.sub(lambda m: f'name="id" value="{transform(m.group(1))}"', html)


class FakeSession:
    """Serves the fixture for every page; fails when told to."""

    def __init__(self, fail_times=0, total_pages_override=None, pages_map=None, fail_pages=None):
        self.calls = []
        self.fail_times = fail_times
        self.html = PAGE
        if total_pages_override is not None:
            self.html = re.sub(r'id="totalPages" value="\d+"', f'id="totalPages" value="{total_pages_override}"', PAGE)
        self.pages_map = pages_map or {}
        self.fail_pages = fail_pages or set()

    def list_page(self, endpoint, page, size=200):
        self.calls.append(page)
        if page in self.fail_pages:
            raise HttpFailure("boom")
        if self.fail_times > 0:
            self.fail_times -= 1
            raise HttpFailure("boom")
        return self.pages_map.get(page, self.html)


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


def test_delta_keeps_walking_past_a_page_with_some_known_ids(tmp_path):
    # A page mixing known and new ids must not stop the walk; only a page
    # with zero new ids should. Pre-seed one known id, then serve:
    #   page 1: 200 new ids
    #   page 2: 1 known id (the pre-seeded one) + 199 new ids
    #   page 3: the same 200 ids as page 1 (all known by then) -> stop
    seed_id = "9999999"
    store.append_rows([{"tender_id": seed_id}], tmp_path / "data", "tenders")

    first_old_id = _ID_INPUT_RE.search(PAGE).group(1)

    def offset_and_seed(old_id):
        return seed_id if old_id == first_old_id else str(int(old_id) + 5_000_000)

    page1 = _with_total(PAGE, 10)
    page2 = _with_total(_rewrite_ids(PAGE, offset_and_seed), 10)
    page3 = page1

    session = FakeSession(pages_map={1: page1, 2: page2, 3: page3})
    summary = run.crawl(session, "tenders", "delta", tmp_path / "data", _cp(tmp_path), time_budget_s=10_000)

    assert session.calls == [1, 2, 3]
    assert summary.pages == 3
    assert summary.rows == 399
    assert summary.status == "done"


def test_backfill_over_120_pages_flushes_every_50_and_at_the_end(tmp_path):
    session = FakeSession(total_pages_override=120)
    summary = run.crawl(session, "tenders", "backfill", tmp_path / "data", _cp(tmp_path), time_budget_s=1_000_000)
    assert summary.status == "done"
    assert summary.pages == 120
    assert summary.rows == 120 * 200
    parts = sorted((tmp_path / "data" / "raw" / "tenders").glob("part-*.parquet"))
    assert len(parts) == 3   # two flushes of 50 pages, one final flush of 20


def test_backfill_abort_stores_fetched_pages_and_leaves_next_page(tmp_path):
    session = FakeSession(total_pages_override=10, fail_pages={3})
    summary = run.crawl(session, "tenders", "backfill", tmp_path / "data", _cp(tmp_path), time_budget_s=10_000)
    assert summary.status == "aborted"
    assert summary.pages == 2 and summary.rows == 400
    # the 2 successfully-fetched pages made it to disk despite the abort
    assert store.load_all(tmp_path / "data", "tenders").height == 200   # same 200 ids both pages, deduped
    assert Checkpoint.load(_cp(tmp_path)).next_page == 3


def test_backfill_saves_summary_only_via_flush(tmp_path, monkeypatch):
    save_calls = []
    orig_save = Checkpoint.save

    def counting_save(self, path):
        save_calls.append(path)
        return orig_save(self, path)

    monkeypatch.setattr(Checkpoint, "save", counting_save)

    session = FakeSession(total_pages_override=3)
    summary = run.crawl(session, "tenders", "backfill", tmp_path / "data", _cp(tmp_path), time_budget_s=10_000)

    assert summary.status == "done" and summary.pages == 3
    assert len(save_calls) == 1   # one flush (3 pages, well under FLUSH_EVERY_PAGES) -> one save
    cp = Checkpoint.load(_cp(tmp_path))
    assert cp.last_run_status == "done"
    assert cp.last_run_pages == summary.pages
    assert cp.last_run_rows == summary.rows


def test_backfill_handles_shrinking_page_count(tmp_path):
    # The checkpoint (and pages 1-3) still say 5 total pages, but page 4 comes
    # back empty and reports the true total of 3: that must end the run
    # cleanly (not count as a failure) and correct total_pages downward.
    Checkpoint(endpoint="tenders", next_page=1, total_pages=5).save(_cp(tmp_path))
    pages_map = {
        1: _with_total(PAGE, 5),
        2: _with_total(PAGE, 5),
        3: _with_total(PAGE, 5),
        4: '<input type="hidden" id="totalPages" value="3">',
    }
    session = FakeSession(pages_map=pages_map)
    summary = run.crawl(session, "tenders", "backfill", tmp_path / "data", _cp(tmp_path), time_budget_s=10_000)
    assert session.calls == [1, 2, 3, 4]
    assert summary.status == "done"
    assert summary.pages == 3
    assert summary.rows == 3 * 200
    cp = Checkpoint.load(_cp(tmp_path))
    assert cp.total_pages == 3
