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
        {"tender_id": "9", "reference": "r", "title": "C", "advertised_at": "2026-08-01T10:00", "ministry": "M",
         "procuring_entity": "PE", "pe_id": "p1", "method": "OTM", "district": "Dhaka", "signed_on": "2026-09-01",
         "awardee": "A", "bidder_id": "b1", "value_crore": 0.5, "fetched_at": "20260913T070000000003Z"},
    ]).write_parquet(root / "clean" / "contracts.parquet")
    pl.DataFrame([{"bidder_id": "b1", "canonical_name": "A", "variants": '["A"]', "n_awards": 1,
                   "total_value_crore": 0.5, "first_award": "2026-09-01", "last_award": "2026-09-01"}]).write_parquet(root / "clean" / "bidders.parquet")
    pl.DataFrame([{"pe_id": "p1", "name": "PE", "ministry": "M", "n_contracts": 1, "n_tenders": 3}]).write_parquet(root / "clean" / "procuring_entities.parquet")


def test_plan_selects_window_escapes_and_caps(tmp_path: Path):
    _clean(tmp_path)
    plan = d1.plan_load(tmp_path, d1.Watermark(), max_rows=100, today="2026-09-13")
    sql = "\n".join(plan.statements)
    assert "INSERT OR REPLACE INTO tenders" in sql and "'O''Brien supply'" in sql
    assert "'Old one'" not in sql                                   # outside the 12 month window
    assert "INSERT OR REPLACE INTO contracts" in sql and "INSERT OR REPLACE INTO bidders" in sql
    assert plan.rows == 2 + 1 + 1 + 1
    assert plan.watermark.tenders == "20260913T070000000002Z" and plan.watermark.contracts == "20260913T070000000003Z"


def test_cap_stops_and_watermark_resumes(tmp_path: Path):
    _clean(tmp_path)
    first = d1.plan_load(tmp_path, d1.Watermark(), max_rows=1, today="2026-09-13")
    assert first.rows == 1 and first.watermark.tenders == "20260913T070000000000Z"
    second = d1.plan_load(tmp_path, first.watermark, max_rows=100, today="2026-09-13")
    joined = "\n".join(second.statements)
    assert "'Newer'" in joined and "'O''Brien supply'" not in joined


def test_statements_are_batched(tmp_path: Path):
    (tmp_path / "clean").mkdir()
    rows = [{"tender_id": str(i), "title": f"t{i}", "fetched_at": f"2026091{i % 10}", "published_at": "2026-09-01T00:00",
             "status": "Live"} for i in range(1200)]
    pl.DataFrame(rows).write_parquet(tmp_path / "clean" / "tenders.parquet")
    plan = d1.plan_load(tmp_path, d1.Watermark(), max_rows=5000, today="2026-09-13")
    tender_stmts = [s for s in plan.statements if s.startswith("INSERT OR REPLACE INTO tenders")]
    assert len(tender_stmts) == 6 and plan.rows == 1200


def test_statements_stay_under_the_byte_cap(tmp_path: Path):
    (tmp_path / "clean").mkdir()
    rows = [{"tender_id": str(i), "title": "x" * 3000, "fetched_at": "20260913", "published_at": "2026-09-01T00:00",
             "status": "Live"} for i in range(100)]
    pl.DataFrame(rows).write_parquet(tmp_path / "clean" / "tenders.parquet")
    plan = d1.plan_load(tmp_path, d1.Watermark(), max_rows=5000, today="2026-09-13")
    assert plan.rows == 100
    assert all(len(s.encode("utf-8")) <= d1.MAX_STATEMENT_BYTES for s in plan.statements)
    assert len(plan.statements) >= 4


def test_watermark_roundtrip(tmp_path: Path):
    w = d1.Watermark(tenders="a", contracts="b", loaded_rows_today=5, day="2026-09-13")
    w.save(tmp_path / "w.json")
    assert d1.Watermark.load(tmp_path / "w.json") == w
    assert d1.Watermark.load(tmp_path / "missing.json") == d1.Watermark()


def test_write_sql_files(tmp_path: Path):
    _clean(tmp_path)
    plan = d1.plan_load(tmp_path, d1.Watermark(), max_rows=100, today="2026-09-13")
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
    f1.write_text("x", encoding="utf-8"); f2.write_text("y", encoding="utf-8")
    try:
        d1.execute([f1, f2], "bidefy", remote=True, runner=runner)
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "b.sql" in str(e)
    assert len(calls) == 2 and "--remote" in calls[0]
