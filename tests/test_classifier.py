import json
import random
from pathlib import Path

import polars as pl

from bidefy.models import classifier

WORDS = {
    "roads_bridges": ["road", "bridge", "culvert", "carpeting", "embankment", "highway"],
    "medical": ["medicine", "surgical", "hospital", "reagent", "vaccine", "laboratory"],
    "it_equipment": ["computer", "laptop", "printer", "server", "software", "scanner"],
    "furniture": ["furniture", "chair", "table", "almirah", "desk", "sofa"],
    "food_catering": ["rice", "food", "catering", "meal", "ration", "kitchen"],
}
TAGS = {
    "roads_bridges": ["Road-repair works", "Construction work for highways"],
    "medical": ["Pharmaceutical products", "Medical equipments"],
    "it_equipment": ["Computer equipment and supplies", "Software"],
    "furniture": ["Furniture", "Office furniture"],
    "food_catering": ["Food, beverages", "Catering services"],
}


def _synthetic(root: Path, n=300, seed=1):
    rng = random.Random(seed)
    tenders, details = [], []
    for i in range(n):
        cat = list(WORDS)[i % len(WORDS)]
        title = f"Procurement of {rng.choice(WORDS[cat])} and {rng.choice(WORDS[cat])} for zone {rng.randint(1, 60)}"
        tenders.append({"tender_id": str(i), "title": title, "status": "Live", "fetched_at": "20260913T000000000000Z"})
        details.append({"tender_id": str(i), "categories": json.dumps(TAGS[cat]), "fetched_at": "20260913T000000000000Z"})
    (root / "clean").mkdir(parents=True, exist_ok=True)
    pl.DataFrame(tenders).write_parquet(root / "clean" / "tenders.parquet")
    (root / "raw" / "details").mkdir(parents=True, exist_ok=True)
    pl.DataFrame(details).write_parquet(root / "raw" / "details" / "part-1.parquet")


def test_train_writes_model_and_honest_metrics(tmp_path: Path):
    _synthetic(tmp_path)
    m = classifier.train(tmp_path, tmp_path / "models", threshold=0.55, seed=0)
    assert set(m) >= {"accuracy_acted", "deferral_rate", "coverage", "macro_f1", "n_train", "n_test", "threshold", "trained_at", "labels_from_tags", "labels_from_title"}
    assert m["accuracy_acted"] >= 0.9 and 0 <= m["deferral_rate"] <= 0.5
    assert abs(m["coverage"] - (1 - m["deferral_rate"])) < 1e-9
    assert (tmp_path / "models" / "category.joblib").exists()
    metrics = json.loads((tmp_path / "models" / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["category_classifier"]["n_test"] == m["n_test"]


def test_apply_defers_below_threshold(tmp_path: Path):
    _synthetic(tmp_path)
    classifier.train(tmp_path, tmp_path / "models", threshold=0.55, seed=0)
    model = classifier.load(tmp_path / "models")
    out = classifier.apply(["Procurement of laptop and printer for zone 3", "zzzz qqqq"], model)
    assert out[0][0] == "it_equipment" and out[0][1] >= 0.55
    assert out[1][0] == "" and 0 <= out[1][1] < 0.55


def test_train_without_labels_returns_none(tmp_path: Path):
    (tmp_path / "clean").mkdir()
    pl.DataFrame({"tender_id": ["1"], "title": ["x"]}).write_parquet(tmp_path / "clean" / "tenders.parquet")
    assert classifier.train(tmp_path, tmp_path / "models") is None
