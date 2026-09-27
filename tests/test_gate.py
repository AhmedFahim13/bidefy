"""The promotion gate. The design document promised it in week one; these are its terms."""
import json
from pathlib import Path

from bidefy.models import gate

PREVIOUS = {
    "award_value_model": {"coverage_80": 0.79, "history_coverage_80": 0.78, "history_mape": 0.378,
                          "history_band_width_median": 5.05, "security_coverage_80": 0.76,
                          "security_mape": 0.077},
    "category_classifier": {"accuracy_acted": 0.93, "deferral_rate": 0.13, "macro_f1": 0.71},
}
# A week of measured movement. The tolerance is the larger of three typical steps and the widest
# spread seen, so coverage tolerates 0.012 here: three 0.003 steps is 0.009, the spread is 0.012.
STABILITY = {"figures": {
    "award_value_model.coverage_80": {"typical_step": 0.003, "spread": 0.012, "kind": "pct"},
    "award_value_model.history_mape": {"typical_step": 0.001, "spread": 0.008, "kind": "pct"},
    "award_value_model.history_band_width_median": {"typical_step": 0.02, "spread": 0.16, "kind": "multiple"},
    "category_classifier.deferral_rate": {"typical_step": 0.002, "spread": 0.026, "kind": "pct"},
}}


def _models(tmp_path: Path, previous=PREVIOUS, stability=STABILITY) -> Path:
    d = tmp_path / "models"
    d.mkdir(parents=True, exist_ok=True)
    if previous is not None:
        (d / "metrics.json").write_text(json.dumps(previous), encoding="utf-8")
    if stability is not None:
        (d / "stability.json").write_text(json.dumps(stability), encoding="utf-8")
    return d


def test_a_first_run_always_promotes(tmp_path: Path):
    """A gate that blocked the first run would leave the product with no model at all."""
    d = _models(tmp_path, previous=None)
    assert gate.check("award_value_model", {"coverage_80": 0.1}, d) == []


def test_movement_inside_the_measured_noise_promotes(tmp_path: Path):
    d = _models(tmp_path)
    # Coverage down 0.6 points, well inside anything measured.
    assert gate.check("award_value_model", {**PREVIOUS["award_value_model"], "coverage_80": 0.784}, d) == []


def test_a_loss_larger_than_the_noise_blocks(tmp_path: Path):
    d = _models(tmp_path)
    breaches = gate.check("award_value_model", {**PREVIOUS["award_value_model"], "coverage_80": 0.77}, d)
    assert [b["figure"] for b in breaches] == ["coverage_80"]
    assert breaches[0]["was"] == 0.79 and breaches[0]["now"] == 0.77
    assert breaches[0]["tolerated"] == 0.012           # the widest spread seen, not a chosen number


def test_the_tolerance_is_the_wider_of_the_two_measures(tmp_path: Path):
    """Three typical steps alone is tighter than a figure's real week-to-week range, and blocking a
    good run costs a day of the model not improving for nothing."""
    d = _models(tmp_path)
    # 1.1 points down: past three steps (0.9) but inside the 1.2-point spread, so it promotes.
    assert gate.check("award_value_model", {**PREVIOUS["award_value_model"], "coverage_80": 0.779}, d) == []
    # 1.4 points down: past both.
    assert gate.check("award_value_model", {**PREVIOUS["award_value_model"], "coverage_80": 0.776}, d)


def test_direction_is_per_figure(tmp_path: Path):
    """Coverage falling is a loss; error falling is a win. Getting this backwards blocks progress."""
    d = _models(tmp_path)
    better = {**PREVIOUS["award_value_model"], "history_mape": 0.30}     # a big improvement
    assert gate.check("award_value_model", better, d) == []
    worse = {**PREVIOUS["award_value_model"], "history_mape": 0.40}
    assert [b["figure"] for b in gate.check("award_value_model", worse, d)] == ["history_mape"]


def test_a_band_that_widens_a_lot_blocks_but_a_little_does_not(tmp_path: Path):
    d = _models(tmp_path)
    fine = {**PREVIOUS["award_value_model"], "history_band_width_median": 5.15}
    assert gate.check("award_value_model", fine, d) == []
    bad = {**PREVIOUS["award_value_model"], "history_band_width_median": 5.40}
    assert [b["figure"] for b in gate.check("award_value_model", bad, d)] == ["history_band_width_median"]


def test_an_unmeasured_figure_gets_a_generous_default(tmp_path: Path):
    """Before its spread has been measured, a figure must not be blocked on noise."""
    d = _models(tmp_path, stability={"figures": {}})
    near = {**PREVIOUS["award_value_model"], "security_coverage_80": 0.745}   # 1.5 points down
    assert gate.check("award_value_model", near, d) == []
    far = {**PREVIOUS["award_value_model"], "security_coverage_80": 0.70}     # 6 points down
    assert [b["figure"] for b in gate.check("award_value_model", far, d)] == ["security_coverage_80"]


def test_a_missing_figure_is_not_a_regression(tmp_path: Path):
    """A key absent from one side means the metric changed shape, not that the model got worse."""
    d = _models(tmp_path)
    assert gate.check("award_value_model", {"coverage_80": None}, d) == []
    assert gate.check("award_value_model", {}, d) == []


def test_several_losses_are_all_reported(tmp_path: Path):
    d = _models(tmp_path)
    breaches = gate.check("category_classifier",
                          {"accuracy_acted": 0.88, "deferral_rate": 0.25, "macro_f1": 0.60}, d)
    assert {b["figure"] for b in breaches} == {"accuracy_acted", "deferral_rate", "macro_f1"}
    assert "accuracy_acted 0.93 -> 0.88" in gate.describe("category_classifier", breaches)


def test_a_block_is_filed_without_touching_the_serving_figures(tmp_path: Path):
    """The accuracy page reads metrics.json, so it must keep describing the model still serving."""
    d = _models(tmp_path)
    candidate = {"accuracy_acted": 0.88, "deferral_rate": 0.13, "macro_f1": 0.71}
    breaches = gate.check("category_classifier", candidate, d)
    gate.record_blocked(d, "category_classifier", candidate, breaches)
    written = json.loads((d / "metrics.json").read_text(encoding="utf-8"))
    assert written["category_classifier"]["accuracy_acted"] == 0.93       # untouched
    assert written["blocked"]["category_classifier"]["candidate"] == candidate
    assert written["blocked"]["category_classifier"]["breaches"] == breaches


def test_a_later_promotion_clears_the_rejection(tmp_path: Path):
    metrics = {"blocked": {"category_classifier": {"at": "x"}, "award_value_model": {"at": "y"}}}
    once = gate.clear_blocked(metrics, "category_classifier")
    assert set(once["blocked"]) == {"award_value_model"}
    twice = gate.clear_blocked(once, "award_value_model")
    assert "blocked" not in twice
