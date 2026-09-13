from pathlib import Path

import pytest

from bidefy.crawler import parse

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def tenders_html() -> str:
    return (FIX / "tenders_page.html").read_text(encoding="utf-8")


def test_parse_tender_rows_count_and_total(tenders_html):
    rows, total_pages = parse.parse_tender_rows(tenders_html)
    assert len(rows) == 200
    assert total_pages > 3000


def test_parse_tender_row_fields(tenders_html):
    rows, _ = parse.parse_tender_rows(tenders_html)
    row = rows[0]
    assert set(row) == {
        "tender_id", "reference", "status", "note", "nature", "title",
        "ministry", "organization", "procuring_entity",
        "procurement_type", "method", "published_at", "closing_at",
    }
    assert row["tender_id"].isdigit()
    assert row["status"] in {"Live", "Cancelled", "Closed", "Awarded", "Withdrawn", "Rejected", "Re-Tendered"} or row["status"]
    assert row["title"]
    assert row["published_at"].count("-") == 2 and "T" in row["published_at"]
    assert row["closing_at"] >= row["published_at"]


def test_corrigendum_rows_have_empty_status_and_a_note(tenders_html):
    rows, _ = parse.parse_tender_rows(tenders_html)
    by_id = {r["tender_id"]: r for r in rows}
    for tid in ("1332878", "1324653"):
        assert by_id[tid]["status"] == ""
        assert "Corrigendum" in by_id[tid]["note"]
    assert sum(1 for r in rows if r["status"] == "Live") == 196


def test_tender_ids_unique(tenders_html):
    rows, _ = parse.parse_tender_rows(tenders_html)
    ids = [r["tender_id"] for r in rows]
    assert len(ids) == len(set(ids))


def test_parse_datetime():
    assert parse.parse_datetime("13-Sep-2026 11:00") == "2026-09-13T11:00"
    assert parse.parse_datetime("  28-Sep-2026 13:00,") == "2026-09-28T13:00"
    assert parse.parse_datetime("garbage") is None


@pytest.fixture(scope="module")
def contracts_html() -> str:
    return (FIX / "contracts_page.html").read_text(encoding="utf-8")


def test_parse_contract_rows_count_and_total(contracts_html):
    rows, total_pages = parse.parse_contract_rows(contracts_html)
    assert len(rows) == 200
    assert total_pages > 4000


def test_parse_contract_row_fields(contracts_html):
    rows, _ = parse.parse_contract_rows(contracts_html)
    row = rows[0]
    assert set(row) == {
        "tender_id", "reference", "title", "advertised_at", "ministry",
        "procuring_entity", "method", "district", "signed_on", "awardee", "value_crore",
    }
    assert row["tender_id"].isdigit()
    assert row["awardee"]
    assert isinstance(row["value_crore"], float)
    assert row["signed_on"] is None or len(row["signed_on"]) == 10
    assert "more" not in row["title"].split()


def test_contract_value_parse():
    assert parse.parse_value_crore("0.137") == 0.137
    assert parse.parse_value_crore("2,433.5") == 2433.5
    assert parse.parse_value_crore("abc") is None


@pytest.fixture(scope="module")
def detail_html() -> str:
    return (FIX / "detail_page.html").read_text(encoding="utf-8")


def test_parse_detail_fields(detail_html):
    d = parse.parse_detail(detail_html)
    assert d["tender_id"].isdigit()
    assert d["procuring_entity"]
    assert d["procuring_entity_district"]
    assert d["method"]
    assert isinstance(d["categories"], list) and d["categories"]
    assert d["security_bdt"] is None or d["security_bdt"] >= 0
    assert d["published_at"] and "T" in d["published_at"]
    assert isinstance(d["document_price_bdt"], (int, type(None)))


def test_parse_detail_empty():
    d = parse.parse_detail("<html><body>Session Expired</body></html>")
    assert d["tender_id"] == ""
    assert d["categories"] == []
