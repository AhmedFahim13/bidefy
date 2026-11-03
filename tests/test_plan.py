import json
from pathlib import Path

import polars as pl

from bidefy.crawler import plan, store
from bidefy.crawler.session import HttpFailure

FIX = Path(__file__).parent / "fixtures"
SEARCH = (FIX / "plan_search.html").read_text(encoding="utf-8")
DETAIL = (FIX / "detail_page.html").read_text(encoding="utf-8")


def test_parse_plan_rows_reads_package_estimate_and_method():
    rows = plan.parse_plan_rows(SEARCH)
    assert [r["package_no"] for r in rows] == [
        "ee/gopal/25-26/APP-NR-50", "ee/gopal/25-26/APP-NR-51", "ee/pwd/gopal/25-26/EM-NR-40"]
    first = rows[0]
    assert (first["app_id"], first["estimate_bdt"], first["plan_method"], first["nature"]) == (
        "214270", 1039417.0, "OTM", "Works")
    assert first["pkg_id"] == "1205863"


def test_match_package_needs_the_same_package_number():
    rows = plan.parse_plan_rows(SEARCH)
    assert plan.match_package(rows, "ee/pwd/gopal/25-26/EM-NR-40")["estimate_bdt"] == 501000.0
    # spacing and case differences are the portal's, not a different package
    assert plan.match_package(rows, " EE/PWD/gopal/25-26/em-nr-40 ")["estimate_bdt"] == 501000.0
    # a near miss is a different package: the search matches by substring
    assert plan.match_package(rows, "ee/pwd/gopal/25-26/EM-NR-4") is None


def test_pick_live_is_newest_first_and_skips_recorded():
    tenders = pl.DataFrame({
        "tender_id": ["1", "2", "3", "4"],
        "status": ["Live", "Contract Awarded", "Live", "Live"],
        "published_at": ["2026-10-01", "2026-10-30", "2026-11-02", "2026-10-20"],
    })
    assert plan.pick_live(tenders, done={"4"}, n=10) == ["3", "1"]


class FakeSession:
    def __init__(self, fail=()):
        self.calls = []
        self.fail = set(fail)

    def detail(self, tender_id):
        self.calls.append(("detail", tender_id))
        if tender_id in self.fail:
            raise HttpFailure("boom")
        return DETAIL

    def plan_search(self, app_id, package_no):
        self.calls.append(("plan", app_id, package_no))
        return SEARCH


def test_collect_uses_stored_references_and_reads_the_rest(tmp_path):
    s = FakeSession()
    refs = {"7": ("214270", "ee/pwd/gopal/25-26/EM-NR-40")}
    summary = plan.collect(s, ["7", "8"], refs, tmp_path, time_budget_s=60)
    # 7 had its plan reference on file, so only 8 needed its tender page
    assert s.calls == [("plan", "214270", "ee/pwd/gopal/25-26/EM-NR-40"), ("detail", "8"),
                       ("plan", "232366", "TZFaridpur/OfficeEqp/2026-2027")]
    rows = {r["tender_id"]: r for r in store.load_all(tmp_path, plan.ENDPOINT).to_dicts()}
    assert rows["7"]["estimate_bdt"] == 501000.0 and rows["7"]["matched"] is True
    # 8's package is not in that plan page: recorded as unmatched, not guessed
    assert rows["8"]["estimate_bdt"] is None and rows["8"]["matched"] is False
    assert (summary.matched, summary.unmatched) == (1, 1)


def test_collect_aborts_after_five_transport_failures(tmp_path):
    ids = [str(i) for i in range(10)]
    summary = plan.collect(FakeSession(fail=ids), ids, {}, tmp_path, time_budget_s=60)
    assert summary.status == "aborted" and summary.failed == 5


def test_main_writes_a_checkpoint_for_the_command_centre(tmp_path, monkeypatch):
    store.append_rows([{"tender_id": "3", "status": "Live", "published_at": "2026-11-02"},
                       {"tender_id": "5", "status": "Live", "published_at": "2026-11-01"}],
                      tmp_path, "tenders")
    monkeypatch.setattr(plan, "EgpSession", lambda min_interval: FakeSession())
    ckpt = tmp_path / "checkpoints" / "plan_estimates.json"
    assert plan.main(["--data-root", str(tmp_path), "--n", "1", "--checkpoint", str(ckpt)]) == 0
    c = json.loads(ckpt.read_text(encoding="utf-8"))
    # one recorded, one live tender still waiting
    assert (c["next_page"] - 1, c["total_pages"], c["remaining_live"]) == (1, 2, 1)
    assert c["last_run_status"] == "done"
