"""The post-commit invariants. Each one is an incident this project actually had."""
import json
from pathlib import Path

import polars as pl

from tools import check_pipeline


def _tenders(root: Path, sources: list[str]) -> None:
    (root / "clean").mkdir(parents=True, exist_ok=True)
    pl.DataFrame({
        "tender_id": [str(i) for i in range(len(sources))],
        "status": ["Live"] * len(sources),
        "category_source": sources,
    }).write_parquet(root / "clean" / "tenders.parquet")


def _predictions(root: Path, q50: list[float]) -> None:
    n = len(q50)
    pl.DataFrame({
        "tender_id": [str(i) for i in range(n)],
        "q10_lakh": [v / 2 for v in q50],
        "q50_lakh": q50,
        "q90_lakh": [v * 2 for v in q50],
    }).write_parquet(root / "clean" / "predictions.parquet")


def _messages(checks: list) -> str:
    return " | ".join(m for ok, m in checks if not ok)


def test_a_model_that_categorised_nothing_is_caught(tmp_path: Path):
    """The stale-bundle incident: load() returned None and the build wrote empty categories.

    Every step stayed green, and 96 percent of contracts silently lost their category. The share of
    live tenders looked healthy because the portal's own tags cover most of them, so the only sharp
    signal is that the model contributed nothing at all.
    """
    _tenders(tmp_path, ["portal"] * 90 + [""] * 10)
    checks: list = []
    check_pipeline.check_categories(tmp_path, checks)
    assert "categorised none" in _messages(checks)


def test_a_healthy_build_passes_the_category_check(tmp_path: Path):
    _tenders(tmp_path, ["portal"] * 90 + ["model"] * 8 + [""] * 2)
    checks: list = []
    check_pipeline.check_categories(tmp_path, checks)
    assert all(ok for ok, _ in checks)


def test_a_build_with_nothing_left_to_model_passes(tmp_path: Path):
    """When the portal has tagged everything there is nothing for the model to do, and that is fine."""
    _tenders(tmp_path, ["portal"] * 50)
    checks: list = []
    check_pipeline.check_categories(tmp_path, checks)
    assert all(ok for ok, _ in checks)


def test_an_absurd_estimate_is_caught(tmp_path: Path):
    """The mis-punctuated security: one notice implied an award larger than the national budget."""
    _tenders(tmp_path, ["portal"] * 3)
    _predictions(tmp_path, [20.0, 35.0, 2_900_000.0])
    checks: list = []
    check_pipeline.check_predictions(tmp_path, checks)
    assert "exceed" in _messages(checks)


def test_a_half_finished_apply_is_caught(tmp_path: Path):
    """The apply step writing a partial file is the shape of the D1 loader bug: exit zero, do less."""
    _tenders(tmp_path, ["portal"] * 100)
    _predictions(tmp_path, [20.0] * 40)
    checks: list = []
    check_pipeline.check_predictions(tmp_path, checks)
    assert "cover 40.0%" in _messages(checks)


def test_a_band_out_of_order_is_caught(tmp_path: Path):
    _tenders(tmp_path, ["portal"] * 2)
    (tmp_path / "clean").mkdir(parents=True, exist_ok=True)
    pl.DataFrame({"tender_id": ["0", "1"], "q10_lakh": [10.0, 90.0],
                  "q50_lakh": [20.0, 50.0], "q90_lakh": [30.0, 60.0]}).write_parquet(
        tmp_path / "clean" / "predictions.parquet")
    checks: list = []
    check_pipeline.check_predictions(tmp_path, checks)
    assert "out of order" in _messages(checks)


def test_healthy_predictions_pass(tmp_path: Path):
    _tenders(tmp_path, ["portal"] * 100)
    _predictions(tmp_path, [20.0] * 100)
    checks: list = []
    check_pipeline.check_predictions(tmp_path, checks)
    assert all(ok for ok, _ in checks)


def test_a_rejected_model_candidate_fails_the_build(tmp_path: Path):
    """A block exits zero so the crawl still commits. This is what then tells a human."""
    models = tmp_path / "models"
    models.mkdir()
    (models / "metrics.json").write_text(json.dumps({
        "category_classifier": {"accuracy_acted": 0.93},
        "blocked": {"category_classifier": {"at": "2026-09-27T00:00:00Z", "breaches": [
            {"figure": "accuracy_acted", "was": 0.93, "now": 0.88}]}},
    }), encoding="utf-8")
    checks: list = []
    check_pipeline.check_promotions(models, checks)
    assert "still serving" in _messages(checks)
    assert "accuracy_acted 0.93 to 0.88" in _messages(checks)


def test_a_clean_metrics_file_reports_no_rejection(tmp_path: Path):
    models = tmp_path / "models"
    models.mkdir()
    (models / "metrics.json").write_text(json.dumps({"category_classifier": {}}), encoding="utf-8")
    checks: list = []
    check_pipeline.check_promotions(models, checks)
    assert checks == []


def test_missing_artefacts_are_not_treated_as_failures(tmp_path: Path):
    """CI has no crawled data. The checks that need it must stay quiet rather than fail the build."""
    checks: list = []
    check_pipeline.check_categories(tmp_path, checks)
    check_pipeline.check_predictions(tmp_path, checks)
    check_pipeline.check_promotions(tmp_path / "models", checks)
    assert checks == []


def test_the_exit_code_follows_the_invariants(tmp_path: Path, monkeypatch, capsys):
    _tenders(tmp_path, ["portal"] * 90 + [""] * 10)          # the stale-bundle signature
    monkeypatch.setattr(check_pipeline, "check_generated_docs", lambda checks, data_root=None: None)
    assert check_pipeline.main(["--data-root", str(tmp_path), "--models-dir", str(tmp_path)]) == 1
    assert "invariant(s) broken" in capsys.readouterr().out

    _tenders(tmp_path, ["portal"] * 90 + ["model"] * 10)
    assert check_pipeline.main(["--data-root", str(tmp_path), "--models-dir", str(tmp_path)]) == 0


def test_the_page_is_not_compared_without_the_inputs_it_was_written_from(tmp_path: Path, capsys):
    """A check that cannot pass in the place it runs is worse than no check.

    One line of the page counts live tenders out of data/clean/tenders.parquet, which is derived and
    gitignored. On a fresh checkout the writer legitimately produces a different page, so comparing
    would fail every CI run for a reason that is not a defect. Found by the check failing its own
    first run in CI, twenty minutes after it was pushed.
    """
    checks: list = []
    check_pipeline.check_generated_docs(checks, tmp_path)       # no clean tables here
    assert checks and all(ok for ok, _ in checks)
    assert "was not compared" in checks[0][1]


def test_the_page_is_compared_when_the_inputs_are_there(tmp_path: Path, monkeypatch):
    """And with the inputs present it does the real comparison, so the skip cannot become the norm."""
    _tenders(tmp_path, ["portal"] * 3)
    called: list = []
    monkeypatch.setattr(check_pipeline, "ROOT", tmp_path)       # no page here, so it returns early
    check_pipeline.check_generated_docs(called, tmp_path)
    assert called == []                                         # reached the page check, found none
