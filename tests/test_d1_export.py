import json
from pathlib import Path

import polars as pl

from bidefy.export import d1

OK = '[{"results": [], "success": true, "meta": {"duration": 1}}]'
NEVER_SLEEP = lambda seconds: None      # noqa: E731 - keeps the retry tests instant


def _tender(tid: str, status: str, published: str, fetched: str, title: str = "t") -> dict:
    return {"tender_id": tid, "reference": "r", "status": status, "note": "", "nature": "Goods", "title": title,
            "ministry": "M", "organization": "", "procuring_entity": "PE", "pe_id": "p1", "procurement_type": "NCT",
            "method": "OTM", "published_at": published, "closing_at": "2026-09-20T10:00", "fetched_at": fetched}


def _clean(root: Path):
    (root / "clean").mkdir(parents=True)
    pl.DataFrame([
        _tender("1", "Live", "2026-09-01T10:00", "20260913T070000000000Z", "O'Brien supply"),
        _tender("2", "Cancelled", "2024-01-01T10:00", "20260913T070000000001Z", "Old one"),
        _tender("3", "Live", "2026-09-02T10:00", "20260913T070000000002Z", "Newer"),
    ]).write_parquet(root / "clean" / "tenders.parquet")
    pl.DataFrame([
        {"bidder_id": "b1", "canonical_name": "A", "variants": '["A"]', "n_awards": 1, "total_value_crore": 0.5,
         "first_award": "2026-09-01", "last_award": "2026-09-01", "recent_awards": "[]"},
        {"bidder_id": "b2", "canonical_name": "B", "variants": '["B"]', "n_awards": 3, "total_value_crore": 2.0,
         "first_award": "2025-01-01", "last_award": "2026-09-12", "recent_awards": "[]"},
    ]).write_parquet(root / "clean" / "bidders.parquet")
    pl.DataFrame([{"pe_id": "p1", "name": "PE", "ministry": "M", "n_contracts": 1, "n_tenders": 3, "recent_awards": "[]", "top_bidders": "[]"}]).write_parquet(root / "clean" / "procuring_entities.parquet")


class R:
    def __init__(self, code: int = 0, stdout: str = OK, stderr: str = ""):
        self.returncode, self.stdout, self.stderr = code, stdout, stderr


def _file(tmp_path: Path, name: str = "a.sql") -> Path:
    f = tmp_path / name
    f.write_text("x", encoding="utf-8")
    return f


def _runner(marker_value: str = "m1", fail_first: int = 0):
    """A fake wrangler: fails the first `fail_first` file loads, then answers normally."""
    calls: list[tuple[list[str], dict]] = []
    left = {"n": fail_first}

    def runner(cmd, **kw):
        calls.append((cmd, kw))
        if "--command" in cmd:
            return R(stdout=json.dumps([{"results": [{"value": marker_value}], "success": True}]))
        if left["n"]:
            left["n"] -= 1
            return R(1, stdout="partial", stderr="spinner text")
        return R()

    return runner, calls


def test_plan_counts_writes_with_index_weights(tmp_path: Path):
    _clean(tmp_path)
    plan = d1.plan_load(tmp_path, d1.Watermark(), max_writes=10_000, today="2026-09-13")
    sql = "\n".join(plan.statements)
    assert "INSERT OR REPLACE INTO tenders" in sql and "'O''Brien supply'" in sql and "'Old one'" not in sql
    assert "INSERT OR REPLACE INTO contracts" not in sql
    assert plan.rows == 2 + 1 + 2                       # live tenders, the buyer, both bidders
    assert plan.writes == 2 * d1.WRITE_WEIGHT["tenders"] + 1 + 2
    assert plan.watermark.writes_today == plan.writes and plan.watermark.day == "2026-09-13"
    assert plan.watermark.live == "20260913T070000000002Z" and plan.watermark.bidders == "2026-09-12"
    assert plan.watermark.tenders == ""                 # nothing archived inside the window


def test_live_tenders_jump_the_archive_backlog(tmp_path: Path):
    (tmp_path / "clean").mkdir()
    rows = [_tender(str(i), "Awarded", "2026-06-01T00:00", f"20260910T0000{i:06d}Z") for i in range(50)]
    rows.append(_tender("live", "Live", "2026-09-14T00:00", "20260915T010000000000Z", "Fresh notice"))
    pl.DataFrame(rows).write_parquet(tmp_path / "clean" / "tenders.parquet")
    plan = d1.plan_load(tmp_path, d1.Watermark(), max_writes=5, today="2026-09-15")   # room for one tender
    assert plan.rows == 1 and "'Fresh notice'" in "\n".join(plan.statements)
    assert plan.watermark.live == "20260915T010000000000Z" and plan.watermark.tenders == ""
    assert plan.skipped["tenders_backlog"] == 50


def test_award_bands_and_buyers_load_before_the_backlog(tmp_path: Path):
    (tmp_path / "clean").mkdir()
    pl.DataFrame([_tender(str(i), "Awarded", "2026-06-01T00:00", f"20260910T0000{i:06d}Z") for i in range(10)]).write_parquet(tmp_path / "clean" / "tenders.parquet")
    pl.DataFrame([{"tender_id": "9", "q10_lakh": 1.0, "q50_lakh": 2.0, "q90_lakh": 3.0, "deferred": False, "basis": "security", "model_version": "v"}]).write_parquet(tmp_path / "clean" / "predictions.parquet")
    pl.DataFrame([{"pe_id": "p1", "name": "PE", "ministry": "M"}]).write_parquet(tmp_path / "clean" / "procuring_entities.parquet")
    plan = d1.plan_load(tmp_path, d1.Watermark(), max_writes=2, today="2026-09-15")
    sql = "\n".join(plan.statements)
    assert "INTO predictions" in sql and "INTO procuring_entities" in sql and "INTO tenders" not in sql


def test_budget_survives_across_runs_in_a_day(tmp_path: Path):
    _clean(tmp_path)
    first = d1.plan_load(tmp_path, d1.Watermark(), max_writes=6, today="2026-09-13")      # one live tender (5 writes) and the buyer (1)
    assert first.rows == 2 and first.skipped["tenders_live"] == 1 and first.writes == 6
    second = d1.plan_load(tmp_path, first.watermark, max_writes=6, today="2026-09-13")   # budget spent: nothing loads
    assert second.rows == 0 and second.statements == []
    assert second.watermark.live == first.watermark.live
    next_day = d1.plan_load(tmp_path, first.watermark, max_writes=6, today="2026-09-14")
    assert "'Newer'" in "\n".join(next_day.statements)


def test_bidders_first_load_resumes_by_id_then_goes_incremental(tmp_path: Path):
    (tmp_path / "clean").mkdir()
    pl.DataFrame([{"bidder_id": f"b{i}", "canonical_name": f"B{i}", "last_award": f"2026-09-0{i}"} for i in range(1, 6)]).write_parquet(tmp_path / "clean" / "bidders.parquet")
    first = d1.plan_load(tmp_path, d1.Watermark(), max_writes=2, today="2026-09-13")
    assert first.rows == 2 and first.watermark.bidders_after == "b2" and first.watermark.bidders == ""
    second = d1.plan_load(tmp_path, first.watermark, max_writes=10, today="2026-09-14")
    sql = "\n".join(second.statements)
    assert "'b3'" in sql and "'b5'" in sql and "'b1'" not in sql      # resumes, never restarts from the top
    assert second.watermark.bidders == "2026-09-05" and second.watermark.bidders_after == ""
    third = d1.plan_load(tmp_path, second.watermark, max_writes=10, today="2026-09-15")
    sql = "\n".join(third.statements)
    assert "'b5'" in sql and "'b1'" not in sql                          # only awards within the lookback


def test_bidders_load_incrementally_by_last_award(tmp_path: Path):
    _clean(tmp_path)
    wm = d1.Watermark(bidders="2026-09-10", tenders="zzz", live="zzz")
    plan = d1.plan_load(tmp_path, wm, max_writes=10_000, today="2026-09-13")
    sql = "\n".join(plan.statements)
    assert "'b2'" in sql and "'b1'" not in sql          # only the bidder with a recent award is rewritten


def test_statements_stay_under_the_byte_cap(tmp_path: Path):
    (tmp_path / "clean").mkdir()
    rows = [{"tender_id": str(i), "title": "x" * 3000, "fetched_at": "20260913", "published_at": "2026-09-01T00:00",
             "status": "Live"} for i in range(100)]
    pl.DataFrame(rows).write_parquet(tmp_path / "clean" / "tenders.parquet")
    plan = d1.plan_load(tmp_path, d1.Watermark(), max_writes=50_000, today="2026-09-13")
    assert plan.rows == 100
    assert all(len(s.encode("utf-8")) <= d1.MAX_STATEMENT_BYTES for s in plan.statements)
    assert len(plan.statements) >= 4


def test_watermark_roundtrip_ignores_unknown_fields(tmp_path: Path):
    w = d1.Watermark(tenders="a", bidders="2026-09-01", writes_today=5, day="2026-09-13", live="b", bidders_after="c")
    w.save(tmp_path / "w.json")
    assert d1.Watermark.load(tmp_path / "w.json") == w
    (tmp_path / "old.json").write_text('{"tenders": "a", "contracts": "", "loaded_rows_today": 3, "day": "x", "extra": 1}', encoding="utf-8")
    old = d1.Watermark.load(tmp_path / "old.json")
    assert old.tenders == "a" and old.live == "" and old.bidders_after == ""
    assert d1.Watermark.load(tmp_path / "missing.json") == d1.Watermark()


def test_write_sql_files(tmp_path: Path):
    _clean(tmp_path)
    plan = d1.plan_load(tmp_path, d1.Watermark(), max_writes=10_000, today="2026-09-13")
    files = d1.write_sql(plan, tmp_path / "build", statements_per_file=2)
    assert len(files) == -(-len(plan.statements) // 2)
    assert files[0].read_text(encoding="utf-8").count("INSERT OR REPLACE") == 2


def test_add_marker_counts_one_write(tmp_path: Path):
    _clean(tmp_path)
    plan = d1.plan_load(tmp_path, d1.Watermark(), max_writes=10_000, today="2026-09-13")
    before = plan.writes
    d1.add_marker(plan, "2026-09-13-abc")
    assert plan.statements[-1] == "INSERT OR REPLACE INTO meta (key, value) VALUES ('d1_last_load', '2026-09-13-abc');"
    assert plan.writes == before + 1 and plan.watermark.writes_today == before + 1


def test_execute_never_hands_a_list_to_the_shell(tmp_path: Path):
    runner, calls = _runner()
    d1.execute([_file(tmp_path)], "bidefy", remote=True, marker="m1", runner=runner, sleep=NEVER_SLEEP)
    assert len(calls) == 2
    for cmd, kw in calls:
        assert not kw.get("shell")
        assert cmd[1:4] == ["wrangler", "d1", "execute"] and "--json" in cmd and "--remote" in cmd


def test_execute_retries_a_batch_that_failed_mid_upload(tmp_path: Path):
    """D1 rolls a failed import back, and every statement is idempotent, so a retry is safe."""
    runner, calls = _runner(fail_first=1)
    d1.execute([_file(tmp_path)], "bidefy", remote=True, marker="m1", runner=runner, sleep=NEVER_SLEEP)
    assert len(calls) == 3          # the batch twice, then the marker read-back


def test_execute_gives_up_after_the_retry_limit_and_says_why(tmp_path: Path):
    calls = []

    def runner(cmd, **kw):
        calls.append(cmd)
        return R(1, stdout="partial output", stderr="spinner text")

    try:
        d1.execute([_file(tmp_path)], "bidefy", remote=True, runner=runner, sleep=NEVER_SLEEP)
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        msg = str(e)
        assert "a.sql failed after 3 attempts" in msg
        assert "exit 1" in msg and "spinner text" in msg and "partial output" in msg
    assert len(calls) == d1.RETRIES


def test_execute_rejects_a_clean_exit_that_printed_nothing(tmp_path: Path):
    """The production failure: bare npx ran, exited 0, and not one statement executed."""
    try:
        d1.execute([_file(tmp_path)], "bidefy", remote=True, marker="m1",
                   runner=lambda cmd, **kw: R(stdout=""), sleep=NEVER_SLEEP)
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "a.sql failed after 3 attempts" in str(e) and "no JSON result" in str(e)


def test_execute_rejects_a_load_whose_marker_is_missing(tmp_path: Path):
    def runner(cmd, **kw):
        if "--command" in cmd:
            return R(stdout='[{"results": [], "success": true}]')
        return R()

    try:
        d1.execute([_file(tmp_path)], "bidefy", remote=True, marker="m1", runner=runner, sleep=NEVER_SLEEP)
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "marker" in str(e)


def test_execute_reports_which_file_failed(tmp_path: Path):
    calls = []

    def runner(cmd, **kw):
        calls.append(cmd)
        return R(0 if any("a.sql" in str(c) for c in cmd) else 1, stderr="boom")

    f1, f2 = _file(tmp_path, "a.sql"), _file(tmp_path, "b.sql")
    try:
        d1.execute([f1, f2], "bidefy", remote=True, runner=runner, sleep=NEVER_SLEEP)
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "b.sql" in str(e)
    assert len(calls) == 1 + d1.RETRIES and "--remote" in calls[0]
