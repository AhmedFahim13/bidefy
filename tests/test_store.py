import polars as pl

from bidefy.crawler import store


def _rows(*ids):
    return [
        {"tender_id": i, "reference": "r", "status": "Live", "nature": "Goods", "title": f"t{i}",
         "ministry": "m", "organization": "", "procuring_entity": "pe", "procurement_type": "NCT",
         "method": "OTM", "published_at": "2026-09-13T11:00", "closing_at": "2026-09-28T13:00"}
        for i in ids
    ]


def test_append_and_known_ids(tmp_path):
    path = store.append_rows(_rows("1", "2"), tmp_path, "tenders")
    assert path.exists() and path.suffix == ".parquet"
    assert store.known_ids(tmp_path, "tenders") == {"1", "2"}
    assert store.known_ids(tmp_path, "contracts") == set()


def test_append_empty_writes_nothing(tmp_path):
    assert store.append_rows([], tmp_path, "tenders") is None
    assert store.known_ids(tmp_path, "tenders") == set()


def test_load_all_keeps_latest_by_id(tmp_path):
    store.append_rows(_rows("1"), tmp_path, "tenders")
    later = _rows("1")
    later[0]["status"] = "Cancelled"
    store.append_rows(later, tmp_path, "tenders")
    df = store.load_all(tmp_path, "tenders")
    assert isinstance(df, pl.DataFrame)
    assert df.height == 1
    assert df["status"][0] == "Cancelled"
    assert "fetched_at" in df.columns
