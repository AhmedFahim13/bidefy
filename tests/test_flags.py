import json

import polars as pl

from bidefy.models import flags


def _contracts():
    rows = []
    # entity p1: 10 awards in the window, 8 to bidder A, 1 each to B and C
    for i in range(8):
        rows.append({"tender_id": f"a{i}", "pe_id": "p1", "bidder_id": "A", "awardee": "A Ltd", "signed_on": "2026-06-01", "value_crore": 1.0})
    rows.append({"tender_id": "b1", "pe_id": "p1", "bidder_id": "B", "awardee": "B Ltd", "signed_on": "2026-06-02", "value_crore": 1.0})
    rows.append({"tender_id": "c1", "pe_id": "p1", "bidder_id": "C", "awardee": "C Ltd", "signed_on": "2026-06-03", "value_crore": 1.0})
    # entity p2: an old award outside the window, and A also wins there recently once
    rows.append({"tender_id": "old", "pe_id": "p2", "bidder_id": "B", "awardee": "B Ltd", "signed_on": "2024-01-01", "value_crore": 1.0})
    rows.append({"tender_id": "p2a", "pe_id": "p2", "bidder_id": "A", "awardee": "A Ltd", "signed_on": "2026-07-01", "value_crore": 1.0})
    return pl.DataFrame(rows)


def test_entity_flags_measure_concentration():
    ef = flags.entity_flags(_contracts(), since="2025-09-14")
    p1 = json.loads(ef.filter(pl.col("pe_id") == "p1")["flags"][0])
    assert p1["awards_12m"] == 10 and p1["winners"] == 3
    assert abs(p1["top_share"] - 0.8) < 1e-9 and abs(p1["top3_share"] - 1.0) < 1e-9
    assert p1["hhi"] > 0.6 and p1["top_bidder"] == "A Ltd"
    assert any("80 percent" in n for n in p1["notes"])
    p2 = json.loads(ef.filter(pl.col("pe_id") == "p2")["flags"][0])
    assert p2["awards_12m"] == 1 and p2["notes"] == []


def test_bidder_flags_measure_entity_dependence_and_band_residuals():
    c = _contracts()
    bands = pl.DataFrame({"tender_id": ["a0", "a1", "b1"], "q10_lakh": [50.0, 50.0, 500.0], "q90_lakh": [200.0, 200.0, 2000.0]})
    bf = flags.bidder_flags(c, bands, since="2025-09-14")
    a = json.loads(bf.filter(pl.col("bidder_id") == "A")["flags"][0])
    assert a["awards_12m"] == 9 and a["entities"] == 2 and abs(a["top_entity_share"] - 8 / 9) < 1e-3
    assert a["above_band"] == 0 and a["below_band"] == 0
    b = json.loads(bf.filter(pl.col("bidder_id") == "B")["flags"][0])
    assert b["below_band"] == 1
    assert any("percent of its awards" in n for n in a["notes"])


def test_flags_on_empty_frames():
    empty = pl.DataFrame({"tender_id": [], "pe_id": [], "bidder_id": [], "awardee": [], "signed_on": [], "value_crore": []})
    assert flags.entity_flags(empty, since="2025-09-14").height == 0
    assert flags.bidder_flags(empty, None, since="2025-09-14").height == 0
