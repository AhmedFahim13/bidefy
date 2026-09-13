from pathlib import Path

from bidefy.crawler import details, store

FIX = Path(__file__).parent / "fixtures"
DETAIL = (FIX / "detail_page.html").read_text(encoding="utf-8")


class FakeSession:
    def __init__(self, fail_ids=()):
        self.calls = []
        self.fail_ids = set(fail_ids)

    def detail(self, tender_id):
        self.calls.append(tender_id)
        if tender_id in self.fail_ids:
            raise RuntimeError("boom")
        return DETAIL.replace("1333472", tender_id)


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


def test_fetch_respects_budget(tmp_path):
    s = FakeSession()
    clock = iter([0, 0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
    summary = details.fetch(s, [str(i) for i in range(10)], tmp_path / "data", time_budget_s=15, now=lambda: next(clock), log=lambda m: None)
    assert summary.fetched < 10 and summary.status == "budget"
