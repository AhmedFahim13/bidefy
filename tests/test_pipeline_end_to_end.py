"""The whole nightly chain, on synthetic data, from raw parts to the published page.

Every other test in this suite checks one link. The two worst bugs this project has had were both
*between* links: the D1 loader ran, exited zero and wrote nothing, and a model bundle whose format
had moved on made the build write an empty category for ninety-six percent of contracts while every
step stayed green. A suite of green unit tests said nothing about either.

So this runs the chain the workflow runs -- build, train the classifier, build again so the
categories land, train the award model, apply it, read the stability history, write the accuracy
page, assert the invariants -- and then checks the artefacts agree with each other. The second test
breaks it exactly the way it broke in production and insists the invariants notice.
"""
import json
import random
from datetime import date, timedelta
from pathlib import Path

import polars as pl
import pytest

from bidefy.crawler import store
from bidefy.models import award, classifier
from bidefy.normalize import build
from tools import check_pipeline, write_accuracy_doc

# Four CPV descriptions the official hierarchy resolves to four different sectors, so the classifier
# has something real to learn and MIN_PER_CLASS is satisfied.
CPV = {
    "construction": "Construction work",
    "medical": "Medical equipments",
    "furniture": "Office furniture",
    "it_equipment": "Computer equipment and supplies",
}
TITLES = {
    "construction": "Construction of road embankment and culvert works package",
    "medical": "Supply of surgical gloves syringes and medical consumables for hospital",
    "furniture": "Supply of office furniture chairs tables and almirah for the office",
    "it_equipment": "Supply of desktop computers printers and network switch equipment",
}


def _seed(root: Path, n: int = 700, offset: int = 0, wrong_codes: bool = False) -> None:
    # Enough awards that the award model has a hundred in its test slice after the eighty percent
    # date cut, which is its own floor for reporting a figure at all.
    """Raw crawl output: notices, awards and the detail pages that carry the portal's own codes."""
    rng = random.Random(7)
    sectors = list(CPV)
    entities = [f"PE {i}" for i in range(6)]
    start = date(2025, 1, 1)
    tenders, contracts, details = [], [], []
    for k in range(n):
        i = k + offset
        sector = sectors[i % len(sectors)]
        # When asked for wrong codes, the detail page claims a sector its title contradicts. That is
        # what a labelling regression looks like from the pipeline's side: the data still arrives,
        # still parses, and teaches the model the wrong thing.
        tagged_as = sectors[(i + 1) % len(sectors)] if wrong_codes else sector
        pe = entities[i % len(entities)]
        value = round(0.2 + rng.random() * 3, 4)
        tenders.append({
            "tender_id": str(i), "reference": f"R{i}", "status": "Live" if i % 5 == 0 else "Closed",
            "note": "", "nature": "Works" if sector == "construction" else "Goods",
            "title": f"{TITLES[sector]} lot {i}", "ministry": f"Ministry {i % 3}",
            "organization": "Org", "procuring_entity": pe, "procurement_type": "NCT",
            "method": "OTM" if i % 2 else "LTM",
            "published_at": (start + timedelta(days=i)).isoformat() + "T10:00",
            "closing_at": (start + timedelta(days=i + 20)).isoformat() + "T10:00",
        })
        contracts.append({
            "tender_id": str(i), "reference": f"R{i}", "title": f"{TITLES[sector]} lot {i}",
            "advertised_at": (start + timedelta(days=i)).isoformat() + "T10:00",
            "ministry": f"Ministry {i % 3}", "procuring_entity": pe,
            "method": "OTM" if i % 2 else "LTM", "district": f"District {i % 4}",
            "signed_on": (start + timedelta(days=i + 40)).isoformat(),
            "awardee": f"M/S Firm {i % 40} Traders", "value_crore": value,
        })
        # Only some notices have had their detail page fetched, which is the real state of the
        # archive and the reason the classifier exists at all. Tagging every one of them would make
        # the category invariant untestable: it fires on the share the model was asked to cover.
        if i % 10 < 7:
            details.append({
                "tender_id": str(i), "categories": json.dumps([CPV[tagged_as]]),
                "brief": f"{TITLES[sector]} for {pe}",
                # A security is a fixed share of the buyer's estimate, which is what the precise
                # route learns. Roughly a third of notices publish one, as on the portal.
                "security_bdt": (value * 100 * 100_000 / 36) if i % 3 == 0 else None,
            })
    store.append_rows(tenders, root, "tenders")
    store.append_rows(contracts, root, "contracts")
    store.append_rows(details, root, "details")


def _run_chain(root: Path, models: Path) -> dict:
    """Exactly the sequence .github/workflows/crawl.yml runs, in the same order."""
    out = {}
    build.build(root, root / "review" / "pairs.csv", models_dir=models)
    out["classifier"] = classifier.train(root, models)
    build.build(root, root / "review" / "pairs.csv", models_dir=models)
    out["award"] = award.train(root, models)
    out["applied"] = award.apply(root, models)
    return out


@pytest.fixture
def chain(tmp_path, monkeypatch):
    root, models = tmp_path / "data", tmp_path / "models"
    _seed(root)
    result = _run_chain(root, models)
    # The page writer reads models/ and writes docs/product/, both relative to its own ROOT.
    (tmp_path / "docs" / "product").mkdir(parents=True)
    monkeypatch.setattr(write_accuracy_doc, "ROOT", tmp_path)
    monkeypatch.setattr(write_accuracy_doc, "OUT", tmp_path / "docs" / "product" / "05-accuracy.md")
    write_accuracy_doc.main()
    return {"root": root, "models": models, "tmp": tmp_path, **result}


def test_the_chain_produces_artefacts_that_agree_with_each_other(chain):
    root, models = chain["root"], chain["models"]
    assert chain["classifier"] is not None and chain["award"] is not None
    assert chain["classifier"]["promoted"] is True and chain["award"]["promoted"] is True

    # The page is written from metrics.json, so the two must state the same thing.
    metrics = json.loads((models / "metrics.json").read_text(encoding="utf-8"))
    page = (chain["tmp"] / "docs" / "product" / "05-accuracy.md").read_text(encoding="utf-8")
    assert f"{metrics['category_classifier']['n_labels']:,} tenders" in page
    assert set(metrics) >= {"award_value_model", "category_classifier"}
    assert "blocked" not in metrics

    # Every live tender got a band, and the bands are ordered.
    tenders = pl.read_parquet(root / "clean" / "tenders.parquet").filter(pl.col("status") == "Live")
    preds = pl.read_parquet(root / "clean" / "predictions.parquet")
    assert chain["applied"] == preds.height == tenders.height
    assert (preds["q10_lakh"] <= preds["q50_lakh"]).all()
    assert (preds["q50_lakh"] <= preds["q90_lakh"]).all()
    assert set(preds["basis"].to_list()) <= {"history", "security"}

    # The security route must actually have been taken, or the chain silently lost the detail pages.
    assert "security" in set(preds["basis"].to_list())


def test_the_invariants_pass_on_a_healthy_run(chain):
    # The category invariant only speaks about tenders the portal did not tag, so a run where the
    # model was never asked anything would pass it vacuously. Check the fixture leaves it work.
    tenders = pl.read_parquet(chain["root"] / "clean" / "tenders.parquet")
    assert tenders.filter(pl.col("category_source") == "model").height > 0
    checks: list = []
    check_pipeline.check_categories(chain["root"], checks)
    check_pipeline.check_predictions(chain["root"], checks)
    check_pipeline.check_promotions(chain["models"], checks)
    assert checks and all(ok for ok, _ in checks), [m for ok, m in checks if not ok]


def test_a_bundle_the_code_can_no_longer_read_is_caught(tmp_path):
    """The incident, reproduced: a stale format makes load() return None and the build writes no
    categories. Every step exits zero. This is the assertion that would have caught it."""
    root, models = tmp_path / "data", tmp_path / "models"
    _seed(root)
    build.build(root, root / "review" / "pairs.csv", models_dir=models)
    assert classifier.train(root, models) is not None

    bundle_path = models / "category.joblib"
    import joblib
    bundle = joblib.load(bundle_path)
    bundle["format"] = classifier.BUNDLE_FORMAT - 1          # what a version bump leaves behind
    joblib.dump(bundle, bundle_path, compress=3)
    assert classifier.load(models) is None                   # silently unusable

    build.build(root, root / "review" / "pairs.csv", models_dir=models)
    checks: list = []
    check_pipeline.check_categories(root, checks)
    assert any(not ok and "categorised none" in m for ok, m in checks)


def test_the_page_is_reproducible_from_the_metrics_alone(chain):
    """The page's central promise: it cannot drift from the model it describes."""
    page_path = chain["tmp"] / "docs" / "product" / "05-accuracy.md"
    first = page_path.read_text(encoding="utf-8")
    write_accuracy_doc.main()
    assert page_path.read_text(encoding="utf-8") == first


def test_a_worse_model_is_refused_and_the_old_one_keeps_serving(tmp_path):
    """The gate, through the real training path rather than a stub.

    Unit tests fix its arithmetic. This one proves the thing that matters: that a genuinely worse
    candidate does not reach the bundle on disk, that the figures on the accuracy page go on
    describing the model a reader meets, and that somebody is told.
    """
    root, models = tmp_path / "data", tmp_path / "models"
    _seed(root)
    build.build(root, root / "review" / "pairs.csv", models_dir=models)
    first = classifier.train(root, models)
    assert first["promoted"] is True
    serving = (models / "category.joblib").read_bytes()
    was = json.loads((models / "metrics.json").read_text(encoding="utf-8"))["category_classifier"]

    # A second batch arrives whose codes contradict their titles.
    _seed(root, n=700, offset=700, wrong_codes=True)
    build.build(root, root / "review" / "pairs.csv", models_dir=models)
    second = classifier.train(root, models)

    assert second["promoted"] is False
    assert second["breaches"], "a model this much worse must name what it lost"
    assert second["accuracy_acted"] < was["accuracy_acted"]

    # Nothing about what is served changed.
    assert (models / "category.joblib").read_bytes() == serving
    metrics = json.loads((models / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["category_classifier"] == was
    assert metrics["blocked"]["category_classifier"]["candidate"]["accuracy_acted"] == second["accuracy_acted"]

    # And the build is failed afterwards, so the rejection cannot pass unnoticed.
    checks: list = []
    check_pipeline.check_promotions(models, checks)
    assert any(not ok and "still serving" in m for ok, m in checks)


def test_a_promotion_after_a_rejection_clears_it(tmp_path):
    """A stale rejection would fail every later build and train people to ignore the check."""
    root, models = tmp_path / "data", tmp_path / "models"
    _seed(root)
    build.build(root, root / "review" / "pairs.csv", models_dir=models)
    classifier.train(root, models)
    metrics_path = models / "metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    metrics["blocked"] = {"category_classifier": {"at": "2026-09-01T00:00:00Z", "breaches": []}}
    metrics_path.write_text(json.dumps(metrics), encoding="utf-8")

    assert classifier.train(root, models)["promoted"] is True
    assert "blocked" not in json.loads(metrics_path.read_text(encoding="utf-8"))
    checks: list = []
    check_pipeline.check_promotions(models, checks)
    assert checks == []
