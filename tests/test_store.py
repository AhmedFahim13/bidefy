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


def test_known_ids_tolerates_mixed_int_and_str_ids_across_parts(tmp_path):
    # One part with an integer id column, one with a string id column.
    store.append_rows([{"tender_id": 1, "status": "Live"}], tmp_path, "tenders")
    store.append_rows([{"tender_id": "2", "status": "Live"}], tmp_path, "tenders")
    ids = store.known_ids(tmp_path, "tenders")
    assert ids == {"1", "2"}
    assert all(isinstance(i, str) for i in ids)


def test_known_ids_and_load_all_skip_corrupt_part(tmp_path, capsys):
    store.append_rows(_rows("1", "2"), tmp_path, "tenders")
    bad = tmp_path / "raw" / "tenders" / "part-bad.parquet"
    bad.write_bytes(b"")   # zero-byte, unreadable as parquet
    ids = store.known_ids(tmp_path, "tenders")
    assert ids == {"1", "2"}
    err = capsys.readouterr().err
    assert "part-bad.parquet" in err

    df = store.load_all(tmp_path, "tenders")
    assert df.height == 2
    err = capsys.readouterr().err
    assert "part-bad.parquet" in err


def test_append_rows_two_rapid_calls_produce_distinct_files(tmp_path):
    p1 = store.append_rows(_rows("1"), tmp_path, "tenders")
    p2 = store.append_rows(_rows("2"), tmp_path, "tenders")
    assert p1 != p2
    assert p1.exists() and p2.exists()


def test_compact_merges_parts_keeps_latest_and_removes_old(tmp_path):
    store.append_rows(_rows("1", "2"), tmp_path, "tenders")
    store.append_rows(_rows("3"), tmp_path, "tenders")
    later = _rows("1")
    later[0]["status"] = "Cancelled"
    store.append_rows(later, tmp_path, "tenders")

    parts_before = sorted((tmp_path / "raw" / "tenders").glob("part-*.parquet"))
    assert len(parts_before) == 3

    new_path = store.compact(tmp_path, "tenders")
    assert new_path is not None
    assert new_path.name.endswith("-compact.parquet")

    parts_after = sorted((tmp_path / "raw" / "tenders").glob("part-*.parquet"))
    assert parts_after == [new_path]

    df = store.load_all(tmp_path, "tenders")
    assert df.height == 3
    assert df.filter(pl.col("tender_id") == "1")["status"][0] == "Cancelled"


def test_compact_returns_none_with_fewer_than_two_parts(tmp_path):
    assert store.compact(tmp_path, "tenders") is None
    store.append_rows(_rows("1"), tmp_path, "tenders")
    assert store.compact(tmp_path, "tenders") is None
