import pytest

from bidefy.crawler.checkpoint import Checkpoint


def test_roundtrip(tmp_path):
    path = tmp_path / "tenders.json"
    cp = Checkpoint(endpoint="tenders", next_page=42, total_pages=3129, newest_id_seen="1332746", mode="backfill")
    cp.save(path)
    loaded = Checkpoint.load(path)
    assert loaded == cp
    assert loaded.updated_at


def test_load_missing_returns_fresh(tmp_path):
    cp = Checkpoint.load(tmp_path / "nope.json", endpoint="contracts")
    assert cp.endpoint == "contracts"
    assert cp.next_page == 1
    assert cp.total_pages == 0
    assert cp.newest_id_seen == ""


def test_backfill_done():
    assert Checkpoint(endpoint="t", next_page=10, total_pages=9).backfill_done
    assert not Checkpoint(endpoint="t", next_page=1, total_pages=0).backfill_done


def test_a_longer_index_does_not_undo_a_finished_backfill():
    """New notices lengthen the index daily. A finished crawl must not look unfinished again."""
    grown = Checkpoint(endpoint="t", next_page=3132, total_pages=3134, backfill_completed=True)
    assert grown.backfill_done
    assert not Checkpoint(endpoint="t", next_page=3132, total_pages=3134).backfill_done


def test_load_ignores_fields_it_does_not_know(tmp_path):
    path = tmp_path / "tenders.json"
    path.write_text('{"endpoint": "tenders", "next_page": 5, "something_new": 1}', encoding="utf-8")
    cp = Checkpoint.load(path, endpoint="tenders")
    assert cp.next_page == 5 and cp.backfill_completed is False


def test_save_leaves_no_tmp_file_behind(tmp_path):
    path = tmp_path / "tenders.json"
    Checkpoint(endpoint="tenders").save(path)
    assert path.exists()
    assert not path.with_suffix(".json.tmp").exists()
    assert list(tmp_path.iterdir()) == [path]


def test_load_with_mismatched_endpoint_raises(tmp_path):
    path = tmp_path / "tenders.json"
    Checkpoint(endpoint="tenders").save(path)
    with pytest.raises(ValueError, match="tenders.*contracts|contracts.*tenders"):
        Checkpoint.load(path, endpoint="contracts")
