"""One crawl per endpoint. Two of them once ran at once and both reported success."""
import json
from pathlib import Path

import pytest

from bidefy.crawler import lock


def test_a_second_crawl_of_the_same_endpoint_is_refused(tmp_path: Path):
    cp = tmp_path / "tenders.json"
    with lock.held(cp):
        with pytest.raises(lock.CrawlLocked, match="already being crawled"):
            with lock.held(cp):
                pass


def test_a_different_endpoint_is_not_blocked(tmp_path: Path):
    with lock.held(tmp_path / "tenders.json"), lock.held(tmp_path / "contracts.json"):
        pass


def test_the_lock_says_who_holds_it(tmp_path: Path):
    """A lock that says nothing is worse than none: the first question is whether the holder lives."""
    cp = tmp_path / "tenders.json"
    with lock.held(cp) as path:
        held = json.loads(path.read_text(encoding="utf-8"))
    assert held["pid"] > 0 and held["host"] and held["since"].endswith("Z")


def test_the_lock_is_released_even_when_the_crawl_raises(tmp_path: Path):
    """A crawl that dies must not lock its endpoint out until somebody deletes a file."""
    cp = tmp_path / "tenders.json"
    with pytest.raises(ValueError):
        with lock.held(cp):
            raise ValueError("the portal went down")
    with lock.held(cp):
        pass


def test_a_stale_lock_is_taken_over(tmp_path: Path):
    """A killed process leaves its lock behind, and a pipeline that then needs a human every night
    is worse than the race the lock prevents."""
    cp = tmp_path / "tenders.json"
    stale = cp.with_suffix(".lock")
    stale.write_text(json.dumps({"host": "runner", "pid": 4242, "since": "2026-01-01T00:00:00Z"}),
                     encoding="utf-8")
    said: list[str] = []
    with lock.held(cp, log=said.append, stale_seconds=0):
        pass
    assert "taking over a lock" in said[0] and "4242" in said[0]


def test_a_fresh_lock_is_respected_even_if_it_is_unreadable(tmp_path: Path):
    """A truncated lock file still means somebody got there first."""
    cp = tmp_path / "tenders.json"
    cp.parent.mkdir(parents=True, exist_ok=True)
    cp.with_suffix(".lock").write_text("not json", encoding="utf-8")
    with pytest.raises(lock.CrawlLocked):
        with lock.held(cp):
            pass


def test_the_lock_sits_beside_the_checkpoint_not_inside_it(tmp_path: Path):
    cp = tmp_path / "nested" / "tenders.json"
    with lock.held(cp) as path:
        assert path == tmp_path / "nested" / "tenders.lock"
        assert not cp.exists()          # the lock must never be mistaken for resume state
