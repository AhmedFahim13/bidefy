from pathlib import Path

import polars as pl

from bidefy.export import d1


def _clean(root: Path):
    (root / "clean").mkdir(parents=True)
    pl.DataFrame([
        {"tender_id": "1", "reference": "r", "status": "Live", "note": "", "nature": "Goods", "title": "O'Brien supply",
         "ministry": "M", "organization": "", "procuring_entity": "PE", "pe_id": "p1", "procurement_type": "NCT",
         "method": "OTM", "published_at": "2026-09-01T10:00", "closing_at": "2026-09-20T10:00", "fetched_at": "20260913T070000000000Z"},
        {"tender_id": "2", "reference": "r", "status": "Cancelled", "note": "", "nature": "Goods", "title": "Old one",
         "ministry": "M", "organization": "", "procuring_entity": "PE", "pe_id": "p1", "procurement_type": "NCT",
         "method": "OTM", "published_at": "2024-01-01T10:00", "closing_at": "2024-01-20T10:00", "fetched_at": "20260913T070000000001Z"},
        {"tender_id": "3", "reference": "r", "status": "Live", "note": "", "nature": "Goods", "title": "Newer",
         "ministry": "M", "organization": "", "procuring_entity": "PE", "pe_id": "p1", "procurement_type": "NCT",
         "method": "OTM", "published_at": "2026-09-02T10:00", "closing_at": "2026-09-21T10:00", "fetched_at": "20260913T070000000002Z"},
    ]).write_parquet(root / "clean" / "tenders.parquet")
    pl.DataFrame([
        {"bidder_id": "b1", "canonical_name": "A", "variants": '["A"]', "n_awards": 1, "total_value_crore": 0.5,
         "first_award": "2026-09-01", "last_award": "2026-09-01", "recent_awards": "[]"},
        {"bidder_id": "b2", "canonical_name": "B", "variants": '["B"]', "n_awards": 3, "total_value_crore": 2.0,
         "first_award": "2025-01-01", "last_award": "2026-09-12", "recent_awards": "[]"},
    ]).write_parquet(root / "clean" / "bidders.parquet")
    pl.DataFrame([{"pe_id": "p1", "name": "PE", "ministry": "M", "n_contracts": 1, "n_tenders": 3, "recent_awards": "[]", "top_bidders": "[]"}]).write_parquet(root / "clean" / "procuring_entities.parquet")


def test_plan_counts_writes_with_index_weights(tmp_path: Path):
    _clean(tmp_path)
    plan = d1.plan_load(tmp_path, d1.Watermark(), max_writes=10_000, today="2026-09-13")
    sql = "\n".join(plan.statements)
    assert "INSERT OR REPLACE INTO tenders" in sql and "'O''Brien supply'" in sql and "'Old one'" not in sql
    assert "INSERT OR REPLACE INTO contracts" not in sql
    assert plan.rows == 2 + 2 + 1
    assert plan.writes == 2 * d1.WRITE_WEIGHT["tenders"] + 2 + 1
    assert plan.watermark.writes_today == plan.writes and plan.watermark.day == "2026-09-13"
    assert plan.watermark.tenders == "20260913T070000000002Z" and plan.watermark.bidders == "2026-09-12"


def test_budget_survives_across_runs_in_a_day(tmp_path: Path):
    _clean(tmp_path)
    first = d1.plan_load(tmp_path, d1.Watermark(), max_writes=6, today="2026-09-13")      # one tender (5 writes) plus one bidder (1)
    assert first.rows == 2 and first.skipped["tenders"] == 1 and first.writes == 6
    second = d1.plan_load(tmp_path, first.watermark, max_writes=6, today="2026-09-13")   # budget spent: nothing loads
    assert second.rows == 0 and second.statements == []
    assert second.watermark.tenders == first.watermark.tenders
    next_day = d1.plan_load(tmp_path, first.watermark, max_writes=6, today="2026-09-14")
    assert "'Newer'" in "\n".join(next_day.statements)


def test_bidders_load_incrementally_by_last_award(tmp_path: Path):
    _clean(tmp_path)
    wm = d1.Watermark(bidders="2026-09-10", tenders="zzz")
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
    w = d1.Watermark(tenders="a", bidders="2026-09-01", writes_today=5, day="2026-09-13")
    w.save(tmp_path / "w.json")
    assert d1.Watermark.load(tmp_path / "w.json") == w
    (tmp_path / "old.json").write_text('{"tenders": "a", "contracts": "", "loaded_rows_today": 3, "day": "x", "extra": 1}', encoding="utf-8")
    assert d1.Watermark.load(tmp_path / "old.json").tenders == "a"
    assert d1.Watermark.load(tmp_path / "missing.json") == d1.Watermark()


def test_write_sql_files(tmp_path: Path):
    _clean(tmp_path)
    plan = d1.plan_load(tmp_path, d1.Watermark(), max_writes=10_000, today="2026-09-13")
    files = d1.write_sql(plan, tmp_path / "build", statements_per_file=2)
    assert len(files) == -(-len(plan.statements) // 2)
    assert files[0].read_text(encoding="utf-8").count("INSERT OR REPLACE") == 2


def test_execute_raises_on_wrangler_failure(tmp_path: Path):
    calls = []

    class R:
        def __init__(self, code):
            self.returncode, self.stderr, self.stdout = code, "boom", ""

    def runner(cmd, **kw):
        calls.append(cmd)
        return R(0 if len(calls) == 1 else 1)

    f1, f2 = tmp_path / "a.sql", tmp_path / "b.sql"
    f1.write_text("x", encoding="utf-8")
    f2.write_text("y", encoding="utf-8")
    try:
        d1.execute([f1, f2], "bidefy", remote=True, runner=runner)
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "b.sql" in str(e)
    assert len(calls) == 2 and "--remote" in calls[0]
