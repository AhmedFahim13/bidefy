import csv
from pathlib import Path

from bidefy.normalize import resolve as r


def test_merges_close_variants_and_keeps_distinct_firms():
    counts = {
        "M/S Sawda Traders": 5, "M/S. SAWDA TRADERS": 3, "Sawda Traders": 1,
        "Sawda Trading Corporation": 2, "Hamida Traders": 4,
    }
    res = r.resolve(counts)
    ids = res.entity_of
    assert ids["M/S Sawda Traders"] == ids["M/S. SAWDA TRADERS"] == ids["Sawda Traders"]
    assert ids["Hamida Traders"] != ids["M/S Sawda Traders"]
    assert ids["Sawda Trading Corporation"] != ids["M/S Sawda Traders"]
    sawda = next(e for e in res.entities if e["entity_id"] == ids["M/S Sawda Traders"])
    assert sawda["canonical_name"] == "M/S Sawda Traders"          # most frequent raw spelling
    assert sawda["n_rows"] == 9
    assert sorted(sawda["variants"]) == ["M/S Sawda Traders", "M/S. SAWDA TRADERS", "Sawda Traders"]


def test_borderline_pairs_go_to_review_not_merge():
    counts = {"Rahim Construction": 3, "Rahim Constructions Ltd": 2}
    res = r.resolve(counts, merge_threshold=0.99, review_threshold=0.50)
    assert res.entity_of["Rahim Construction"] != res.entity_of["Rahim Constructions Ltd"]
    assert len(res.review_pairs) == 1
    a, b, score = res.review_pairs[0]
    assert {a, b} == {"Rahim Construction", "Rahim Constructions Ltd"} and 0.5 <= score < 0.99


def _decide(path: Path, decisions: dict[tuple[str, str], str]) -> None:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        key = (row["a"], row["b"]) if row["a"] <= row["b"] else (row["b"], row["a"])
        if key in decisions:
            row["decision"] = decisions[key]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["a", "b", "score", "decision"])
        w.writeheader()
        w.writerows(rows)


def test_review_decisions_override(tmp_path: Path):
    csv_path = tmp_path / "pairs.csv"
    counts = {"Rahim Construction": 3, "Rahim Constructions Ltd": 2, "Karim Traders": 1, "Karim Trader": 1}
    first = r.resolve(counts, merge_threshold=0.99, review_threshold=0.50)
    assert len(first.review_pairs) == 2
    r.write_review(csv_path, first.review_pairs, existing=r.read_review(csv_path))
    assert csv_path.read_text(encoding="utf-8").startswith("a,b,score,decision")
    _decide(csv_path, {("Rahim Construction", "Rahim Constructions Ltd"): "merge", ("Karim Trader", "Karim Traders"): "keep"})
    decisions = r.read_review(csv_path)
    assert len(decisions) == 2
    second = r.resolve(counts, merge_threshold=0.99, review_threshold=0.50, decisions=decisions)
    assert second.entity_of["Rahim Construction"] == second.entity_of["Rahim Constructions Ltd"]
    assert second.entity_of["Karim Traders"] != second.entity_of["Karim Trader"]
    assert second.review_pairs == []                       # decided pairs are not re-queued
    n = r.write_review(csv_path, second.review_pairs, existing=decisions)
    assert n == 2                                          # decided rows are kept in the file


def test_entity_ids_are_stable_across_runs():
    a = r.resolve({"Hamida Traders": 1, "Other Firm": 1})
    b = r.resolve({"Other Firm": 9, "Hamida Traders": 2, "New Firm": 1})
    assert a.entity_of["Hamida Traders"] == b.entity_of["Hamida Traders"]
    assert len(a.entity_of["Hamida Traders"]) == 12


def test_empty_and_blank_names():
    res = r.resolve({"": 3, "   ": 1, "Real Firm": 1})
    assert res.entity_of[""] == "" and res.entity_of["   "] == ""
    assert len(res.entities) == 1
