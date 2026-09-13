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
        "tender_id", "reference", "status", "nature", "title",
        "ministry", "organization", "procuring_entity",
        "procurement_type", "method", "published_at", "closing_at",
    }
    assert row["tender_id"].isdigit()
    assert row["status"] in {"Live", "Cancelled", "Closed", "Awarded", "Withdrawn", "Rejected", "Re-Tendered"} or row["status"]
    assert row["title"]
    assert row["published_at"].count("-") == 2 and "T" in row["published_at"]
    assert row["closing_at"] >= row["published_at"]


def test_tender_ids_unique(tenders_html):
    rows, _ = parse.parse_tender_rows(tenders_html)
    ids = [r["tender_id"] for r in rows]
    assert len(ids) == len(set(ids))


def test_parse_datetime():
    assert parse.parse_datetime("13-Sep-2026 11:00") == "2026-09-13T11:00"
    assert parse.parse_datetime("  28-Sep-2026 13:00,") == "2026-09-28T13:00"
    assert parse.parse_datetime("garbage") is None
