from tools import build_site

STATUS = {
    "project": "Bidefy",
    "tagline": "t",
    "launch_target": "2026-10-11",
    "phases": [
        {"id": "w1", "name": "Week 1", "tasks": [
            {"id": "a", "title": "Done thing", "owner": "claude", "state": "done", "weight": 3},
            {"id": "b", "title": "Doing thing", "owner": "claude", "state": "doing", "weight": 1},
            {"id": "c", "title": "Your thing", "owner": "fahim", "state": "todo", "weight": 1, "note": "n"},
        ]},
        {"id": "w2", "name": "Week 2", "tasks": [
            {"id": "d", "title": "Later thing", "owner": "claude", "state": "todo", "weight": 5},
        ]},
    ],
}


def test_compute_progress():
    p = build_site.compute_progress(STATUS)
    assert p["percent"] == 30            # 3 of 10 weight
    assert p["done_count"] == 1 and p["total_count"] == 4
    assert [t["id"] for t in p["next_steps"]] == ["b", "c", "d"]
    assert [t["id"] for t in p["fahim_tasks"]] == ["c"]
    assert [t["title"] for t in p["done"]] == ["Done thing"]
    assert p["phases"][0]["percent"] == 60


def test_render_dashboard_contains_key_numbers():
    p = build_site.compute_progress(STATUS)
    html = build_site.render_dashboard(STATUS, p, crawl={"tenders": {"next_page": 5, "total_pages": 10, "updated_at": "2026-09-13T00:00:00Z", "last_run_status": "budget"}}, metrics=None)
    assert "30%" in html and "Your thing" in html and "Later thing" in html
    assert "tenders" in html and "5" in html
    assert "<title>Bidefy" in html


def test_render_doc_builds_toc():
    html = build_site.render_doc(STATUS, [("Overview", "<p>Hello</p>"), ("Market", "<p>World</p>")])
    assert "Overview" in html and "Market" in html and "<p>Hello</p>" in html
    assert 'href="#s1"' in html
