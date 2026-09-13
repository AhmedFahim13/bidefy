import json
import math
import random
from datetime import date, timedelta
from pathlib import Path

import polars as pl

from bidefy.models import award

CATS = ["roads_bridges", "medical", "it_equipment", "furniture", "food_catering"]
MULT = {"roads_bridges": 8.0, "medical": 2.0, "it_equipment": 1.0, "furniture": 0.4, "food_catering": 0.7}


def _synthetic(root: Path, n=900, seed=3):
    rng = random.Random(seed)
    entities = [f"pe{i}" for i in range(20)]
    base = {e: rng.uniform(5, 200) for e in entities}
    rows = []
    start = date(2024, 1, 1)
    for i in range(n):
        e = rng.choice(entities)
        c = rng.choice(CATS)
        value_lakh = base[e] * MULT[c] * math.exp(rng.gauss(0, 0.25))
        rows.append({
            "tender_id": str(i), "title": f"Supply of {c.replace('_', ' ')} items {i}", "pe_id": e,
            "ministry": f"M{int(e[2:]) % 4}", "method": rng.choice(["OTM", "RFQ", "LTM"]), "district": f"D{int(e[2:]) % 6}",
            "signed_on": (start + timedelta(days=i)).isoformat(), "value_crore": value_lakh / 100, "category": c,
            "procuring_entity": e.upper(), "fetched_at": "20260913T000000000000Z",
        })
    (root / "clean").mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_parquet(root / "clean" / "contracts.parquet")
    live = [{"tender_id": f"L{i}", "title": "Supply of medical items", "status": "Live", "pe_id": "pe1", "ministry": "M1",
             "method": "OTM", "published_at": "2026-09-01T10:00", "category": "medical", "procuring_entity": "PE1"} for i in range(3)]
    live.append({"tender_id": "LX", "title": "Mystery", "status": "Live", "pe_id": "unknown", "ministry": "M9", "method": "OTM",
                 "published_at": "2026-09-01T10:00", "category": "", "procuring_entity": "NEW"})
    pl.DataFrame(live).write_parquet(root / "clean" / "tenders.parquet")


def test_train_reports_honest_metrics(tmp_path: Path):
    _synthetic(tmp_path)
    m = award.train(tmp_path, tmp_path / "models", seed=0)
    assert set(m) >= {"mape_acted", "mape_baseline", "coverage_80", "deferral_rate", "n_train", "n_test", "trained_at", "model_version"}
    assert 0.6 <= m["coverage_80"] <= 0.97
    assert m["mape_acted"] <= m["mape_baseline"] + 0.05
    assert 0 <= m["deferral_rate"] <= 0.5
    metrics = json.loads((tmp_path / "models" / "metrics.json").read_text(encoding="utf-8"))
    assert "award_value_model" in metrics


def test_apply_writes_predictions_with_ordered_quantiles_and_deferral(tmp_path: Path):
    _synthetic(tmp_path)
    award.train(tmp_path, tmp_path / "models", seed=0)
    out = award.apply(tmp_path, tmp_path / "models")
    p = pl.read_parquet(tmp_path / "clean" / "predictions.parquet")
    assert out == p.height == 4
    assert (p["q10_lakh"] <= p["q50_lakh"]).all() and (p["q50_lakh"] <= p["q90_lakh"]).all()
    known = p.filter(pl.col("tender_id") == "L0").row(0, named=True)
    unknown = p.filter(pl.col("tender_id") == "LX").row(0, named=True)
    assert known["deferred"] is False and unknown["deferred"] is True
    assert known["q50_lakh"] > 0 and known["model_version"]


def test_train_without_data_returns_none(tmp_path: Path):
    assert award.train(tmp_path, tmp_path / "models") is None
