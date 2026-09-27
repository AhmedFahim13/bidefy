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
# Real CPV descriptions, as the portal lists them: labels are read through the official code list.
TAGS = {
    "roads_bridges": ["Construction work for highways, roads", "Surface work for roads"],
    "medical": ["Pharmaceutical products", "Medical equipments"],
    "it_equipment": ["Computer equipment and supplies", "Software"],
    "furniture": ["Furniture", "Office furniture"],
    "food_catering": ["Food, beverages, tobacco and related products", "Catering services"],
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
    m = classifier.train(tmp_path, tmp_path / "models", target_accuracy=0.90, seed=0)
    assert set(m) >= {"accuracy_acted", "deferral_rate", "coverage", "macro_f1", "n_labels", "n_classes",
                      "threshold", "target_accuracy", "trained_at", "evaluation", "deferral_for_95"}
    assert m["accuracy_acted"] >= m["target_accuracy"]      # the bar is set to deliver the target
    assert 0 <= m["deferral_rate"] <= 0.6
    assert abs(m["coverage"] - (1 - m["deferral_rate"])) < 1e-9
    assert (tmp_path / "models" / "category.joblib").exists()
    metrics = json.loads((tmp_path / "models" / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["category_classifier"]["n_labels"] == m["n_labels"]


def test_labels_come_only_from_portal_tags(tmp_path: Path):
    """A title-keyword rule must never supply training labels: it taught the model to copy itself."""
    _synthetic(tmp_path, n=300)
    m = classifier.train(tmp_path, tmp_path / "models", seed=0)
    detail_rows = pl.read_parquet(tmp_path / "raw" / "details" / "part-1.parquet").height
    assert m["n_labels"] <= detail_rows        # never more labels than tagged detail pages


def test_apply_defers_below_threshold(tmp_path: Path):
    _synthetic(tmp_path)
    classifier.train(tmp_path, tmp_path / "models", target_accuracy=0.90, seed=0)
    model = classifier.load(tmp_path / "models")
    out = classifier.apply(classifier.compose(["Procurement of laptop and printer for zone 3", "zzzz qqqq"]), model)
    assert out[0][0] == "it_equipment" and out[0][1] >= model["threshold"]
    assert out[1][0] == "" and 0 <= out[1][1] < model["threshold"]


def test_train_without_labels_returns_none(tmp_path: Path):
    (tmp_path / "clean").mkdir()
    pl.DataFrame({"tender_id": ["1"], "title": ["x"]}).write_parquet(tmp_path / "clean" / "tenders.parquet")
    assert classifier.train(tmp_path, tmp_path / "models") is None


def test_cost_curve_walks_from_answering_everything_to_declining_a_third():
    """The sweet spot depends on how much worse a wrong label is than no label, so it is swept.

    A model whose confidence carries real signal should answer everything when a wrong answer costs
    no more than a silence, and decline more and more as a wrong answer gets dearer. The table is
    published as context; it must never move the operating point.
    """
    import numpy as np
    rng = np.random.default_rng(0)
    n = 20_000
    conf = rng.uniform(0.4, 1.0, n)
    correct = rng.random(n) < conf          # confidence that means something
    points = classifier._cost_optimal_points(conf, correct)
    assert [p["wrong_answer_costs"] for p in points] == [1, 2, 3, 5, 10]
    deferrals = [p["deferral"] for p in points]
    accuracies = [p["accuracy"] for p in points]
    assert deferrals == sorted(deferrals)               # dearer mistakes, more silence
    assert accuracies == sorted(accuracies)             # and higher accuracy on what is left
    assert deferrals[0] < 0.05                          # at parity, answer nearly everything


def test_cost_curve_never_defers_when_confidence_says_nothing():
    """With confidence that carries no signal there is nothing to select on, so silence buys nothing."""
    import numpy as np
    rng = np.random.default_rng(1)
    n = 20_000
    conf = rng.uniform(0, 1, n)
    correct = rng.random(n) < 0.9           # accuracy independent of confidence
    for p in classifier._cost_optimal_points(conf, correct, ratios=(1, 2)):
        assert p["deferral"] < 0.02


def test_threshold_optimism_is_measured_on_tenders_the_bar_did_not_see():
    """Choosing the bar on the rows it is scored on flatters the figure. This measures by how much."""
    import numpy as np
    rng = np.random.default_rng(2)
    n_tenders = 4_000
    rows = np.tile(np.arange(n_tenders), 3)             # three repeats, as the real pool has
    conf = rng.uniform(0.4, 1.0, len(rows))
    correct = rng.random(len(rows)) < conf
    out = classifier._threshold_optimism(conf, correct, rows, 0.93, seed=0)
    assert set(out) == {"accuracy_acted_heldout_bar", "deferral_rate_heldout_bar"}
    # The bar was chosen to deliver 0.93 elsewhere, so the held-out accuracy lands near it rather
    # than exactly on it. A wild miss would mean the split had leaked or the bar was degenerate.
    assert 0.88 <= out["accuracy_acted_heldout_bar"] <= 0.97
    # Deferral runs high here only because this synthetic confidence is far weaker than the real
    # model's: correctness equals confidence, so a 93 percent bar has to cut deep. What is being
    # checked is that a bar chosen elsewhere still lands near its target, not the level it lands at.
    assert 0.0 <= out["deferral_rate_heldout_bar"] <= 0.9


def test_threshold_optimism_declines_to_answer_when_there_is_too_little_data():
    import numpy as np
    rows = np.arange(50)
    assert classifier._threshold_optimism(np.linspace(0.5, 1, 50), np.ones(50, bool), rows, 0.93) == {}


def test_an_unreachable_target_is_not_reported_as_a_measurement():
    """_threshold_for_accuracy answers an unreachable target with a 0.60 fallback rather than a
    refusal. Publishing that as a held-out pair would state a bar chosen for one purpose as though
    it had been chosen for another, and inflate the very optimism gap the paragraph exists to
    quantify."""
    import numpy as np
    rng = np.random.default_rng(0)
    n_tenders = 2_000
    rows = np.tile(np.arange(n_tenders), 3)
    # Reachability hinges on the most confident prediction, because a prefix of one row scores
    # either 0 or 100 percent. So the case that triggers the fallback is a model whose top-confidence
    # answer is wrong and which never recovers: here it is wrong at the top and right half the time
    # after, so no bar delivers 93 percent.
    conf = np.linspace(1.0, 0.5, len(rows))
    correct = rng.random(len(rows)) < 0.5
    correct[0] = False
    assert classifier._reaches(conf, correct, 0.93) is False
    assert classifier._threshold_optimism(conf, correct, rows, 0.93, seed=0) == {}
    # Reachable when the confident rows really are the right ones.
    conf2 = np.linspace(0.5, 1.0, len(rows))
    correct2 = conf2 > 0.55
    assert classifier._reaches(conf2, correct2, 0.93) is True
