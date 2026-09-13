from pathlib import Path

import polars as pl

from bidefy.crawler import store
from bidefy.normalize import build


def _tender(i, pe="Taxes Zone-Faridpur", status="Live"):
    return {"tender_id": str(i), "reference": f"R{i}", "status": status, "note": "", "nature": "Goods",
            "title": f"Tender {i}", "ministry": "Ministry of Finance", "organization": "NBR",
            "procuring_entity": pe, "procurement_type": "NCT", "method": "OTM",
            "published_at": "2026-09-01T10:00", "closing_at": "2026-09-20T10:00"}


def _contract(i, awardee, pe="Taxes Zone-Faridpur", value=0.5):
    return {"tender_id": str(i), "reference": f"R{i}", "title": f"Contract {i}", "advertised_at": "2026-08-01T10:00",
            "ministry": "Ministry of Finance", "procuring_entity": pe, "method": "OTM", "district": "Faridpur",
            "signed_on": "2026-09-0%d" % (1 + i % 8), "awardee": awardee, "value_crore": value}


def _seed(root: Path):
    store.append_rows([_tender(1), _tender(2, status="Cancelled"), _tender(3, pe="Kushtia PBS")], root, "tenders")
    store.append_rows([_contract(1, "M/S Sawda Traders", value=1.0), _contract(2, "M/S. SAWDA TRADERS"),
                       _contract(3, "Hamida Traders", pe="Kushtia PBS"), _contract(4, "")], root, "contracts")


def test_build_writes_clean_tables_with_stable_ids(tmp_path: Path):
    _seed(tmp_path)
    out = build.build(tmp_path, tmp_path / "review" / "pairs.csv")
    bidders = pl.read_parquet(tmp_path / "clean" / "bidders.parquet")
    contracts = pl.read_parquet(tmp_path / "clean" / "contracts.parquet")
    pes = pl.read_parquet(tmp_path / "clean" / "procuring_entities.parquet")
    tenders = pl.read_parquet(tmp_path / "clean" / "tenders.parquet")
    assert out["bidders"] == 2 and bidders.height == 2
    sawda = bidders.filter(pl.col("canonical_name") == "M/S Sawda Traders").row(0, named=True)
    assert sawda["n_awards"] == 2 and abs(sawda["total_value_crore"] - 1.5) < 1e-9
    assert sawda["first_award"] == "2026-09-02" and sawda["last_award"] == "2026-09-03"
    assert contracts.filter(pl.col("tender_id") == "4")["bidder_id"][0] == ""      # blank awardee
    assert sawda["bidder_id"] in set(contracts["bidder_id"].to_list())
    assert pes.height == 2 and set(pes.columns) >= {"pe_id", "name", "ministry", "n_contracts", "n_tenders"}
    faridpur = pes.filter(pl.col("name") == "Taxes Zone-Faridpur").row(0, named=True)
    assert faridpur["n_contracts"] == 3 and faridpur["n_tenders"] == 2
    assert tenders.height == 3 and "pe_id" in tenders.columns
    assert tenders.filter(pl.col("tender_id") == "1")["pe_id"][0] == faridpur["pe_id"]
    assert (tmp_path / "review" / "pairs.csv").exists()
    import json
    recent = json.loads(sawda["recent_awards"])
    assert len(recent) == 2 and recent[0]["signed_on"] >= recent[1]["signed_on"] and "title" in recent[0]
    top = json.loads(faridpur["top_bidders"])
    assert top[0]["bidder_id"] == sawda["bidder_id"] and top[0]["n_awards"] == 2
    assert len(json.loads(faridpur["recent_awards"])) == 3


def test_build_is_idempotent_and_keeps_ids(tmp_path: Path):
    _seed(tmp_path)
    build.build(tmp_path, tmp_path / "review" / "pairs.csv")
    first = pl.read_parquet(tmp_path / "clean" / "bidders.parquet").sort("bidder_id")
    build.build(tmp_path, tmp_path / "review" / "pairs.csv")
    second = pl.read_parquet(tmp_path / "clean" / "bidders.parquet").sort("bidder_id")
    assert first["bidder_id"].to_list() == second["bidder_id"].to_list()


def test_build_with_no_raw_data(tmp_path: Path):
    out = build.build(tmp_path, tmp_path / "review" / "pairs.csv")
    assert out == {"tenders": 0, "contracts": 0, "bidders": 0, "procuring_entities": 0, "review_pairs": 0}
