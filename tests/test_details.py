from pathlib import Path

import polars as pl

from bidefy.crawler import details, store
from bidefy.crawler.session import HttpFailure

FIX = Path(__file__).parent / "fixtures"
DETAIL = (FIX / "detail_page.html").read_text(encoding="utf-8")


class FakeSession:
    def __init__(self, fail_ids=(), empty_ids=()):
        self.calls = []
        self.fail_ids = set(fail_ids)
        self.empty_ids = set(empty_ids)

    def detail(self, tender_id):
        self.calls.append(tender_id)
        if tender_id in self.fail_ids:
            raise HttpFailure("boom")
        if tender_id in self.empty_ids:
            return "<html><body>View IFT Notice Details</body></html>"
        return DETAIL.replace("1333472", tender_id)


def _archive_frames():
    tenders = pl.DataFrame({
        "tender_id": ["1", "2", "3", "4", "5"],
        "published_at": ["2015-03-01", "2023-06-01", "2019-01-01", "2024-02-01", None],
    })
    # 3 and 5 were awarded; 9 is an award whose notice is missing from the tender index
    contracts = pl.DataFrame({
        "tender_id": ["3", "5", "9"],
        "advertised_at": ["2019-01-01", "2021-05-05", "2022-01-01"],
    })
    return tenders, contracts


def test_archive_ids_puts_awarded_first_then_newest_first():
    # 5 has no notice date of its own, so its award's advertised date places it
    tenders, contracts = _archive_frames()
    assert details.archive_ids(tenders, contracts, done=set(), n=10) == ["5", "3", "4", "2", "1"]


def test_archive_ids_leaves_out_awards_missing_from_the_tender_index():
    """27 of 30 sampled award-only ids served an empty stub (2026-11-03)."""
    tenders, contracts = _archive_frames()
    assert "9" not in details.archive_ids(tenders, contracts, done=set(), n=10)


def test_archive_ids_skips_fetched_ids_and_caps_at_n():
    tenders, contracts = _archive_frames()
    assert details.archive_ids(tenders, contracts, done={"5", "4"}, n=3) == ["3", "2", "1"]


def test_archive_progress_counts_the_tender_index():
    tenders, contracts = _archive_frames()
    assert details.archive_progress(tenders, contracts, done={"3", "9", "77"}) == {
        "indexed": 5, "fetched": 1, "remaining": 4}


def test_archive_source_fetches_in_archive_order(tmp_path, monkeypatch):
    tenders, contracts = _archive_frames()
    store.append_rows(tenders.to_dicts(), tmp_path, "tenders")
    store.append_rows(contracts.to_dicts(), tmp_path, "contracts")
    session = FakeSession()
    monkeypatch.setattr(details, "EgpSession", lambda min_interval: session)
    ckpt = tmp_path / "checkpoints" / "details_archive.json"
    assert details.main(["--data-root", str(tmp_path), "--source", "archive", "--n", "2",
                         "--checkpoint", str(ckpt)]) == 0
    assert session.calls == ["5", "3"]
    # the command centre renders every checkpoint as "next_page - 1 / total_pages"
    import json
    c = json.loads(ckpt.read_text(encoding="utf-8"))
    assert (c["next_page"] - 1, c["total_pages"], c["remaining"]) == (2, 5, 3)
    assert c["last_run_status"] == "done" and c["updated_at"].endswith("Z")


def test_pick_ids_excludes_done_and_is_deterministic():
    ids = [str(i) for i in range(100)]
    a = details.pick_ids(ids, done={"1", "2"}, n=10, seed=7)
    b = details.pick_ids(ids, done={"1", "2"}, n=10, seed=7)
    assert a == b and len(a) == 10 and not ({"1", "2"} & set(a))


def test_fetch_stores_rows_and_skips_failures(tmp_path):
    s = FakeSession(fail_ids={"5"})
    summary = details.fetch(s, ["3", "5", "7"], tmp_path / "data", time_budget_s=1000, log=lambda m: None)
    assert summary.fetched == 2 and summary.failed == 1
    df = store.load_all(tmp_path / "data", "details")
    assert df.height == 2 and set(df["tender_id"].to_list()) == {"3", "7"}
    assert "categories" in df.columns and df["security_bdt"][0] == 80000
    assert isinstance(df["categories"][0], str) and "Office" in df["categories"][0]


def test_empty_pages_are_recorded_and_do_not_abort(tmp_path):
    """The portal serves a stub for some archived tenders. That is data, not a fault."""
    s = FakeSession(empty_ids={"1", "2", "3", "4"})
    summary = details.fetch(s, ["1", "2", "3", "4", "9"], tmp_path / "data", time_budget_s=1000, log=lambda m: None)
    assert summary.status == "done" and summary.empty == 4 and summary.fetched == 1 and summary.failed == 0
    df = store.load_all(tmp_path / "data", "details")
    assert df.height == 5                      # empty ids are stored so they are not re-fetched nightly
    assert df.filter(pl.col("tender_id") == "9")["security_bdt"][0] == 80000


def test_transport_failures_abort_after_five(tmp_path):
    s = FakeSession(fail_ids={str(i) for i in range(10)})
    summary = details.fetch(s, [str(i) for i in range(10)], tmp_path / "data", time_budget_s=1000, log=lambda m: None)
    assert summary.status == "aborted" and summary.failed == 5


def test_fetch_respects_budget(tmp_path):
    s = FakeSession()
    clock = iter([0, 0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
    summary = details.fetch(s, [str(i) for i in range(10)], tmp_path / "data", time_budget_s=15, now=lambda: next(clock), log=lambda m: None)
    assert summary.fetched < 10 and summary.status == "budget"
