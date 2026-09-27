"""The writer that produces the published accuracy page.

Coverage said this file was 6 percent tested -- 270 of 288 statements never executed -- and it is the
one that writes the product's central artefact. Two of the seven findings in the last code review
were here, and both would have printed a false claim on the page that exists to prove the numbers
are trustworthy. The least-tested file produced the most dangerous bugs, which is not a coincidence.

So each test below fixes a sentence the page is allowed to say, and the conditions under which it may
say it. They render from synthetic metrics into a temporary tree; nothing here touches the real page.
"""
import json

import pytest

from tools import write_accuracy_doc as w

AWARD = {
    "n_fit": 700_000, "n_calibration": 400_000, "n_test": 170_000, "test_from": "2025-03-24",
    "mape_acted": 0.30, "mape_naive_median": 0.78, "coverage_80": 0.79, "deferral_rate": 0.12,
    "band_width_median": 4.3, "unconditional_spread": 48.0,
    "history_n": 120_000, "history_mape": 0.378, "history_coverage_80": 0.784,
    "history_band_width_median": 5.05,
    "history_coverage_ci95": [0.782, 0.786], "history_mape_ci95": [0.376, 0.380],
    "security_n": 6_000, "security_fitted_on": 15_000, "security_test_from": "2026-06-18",
    "security_mape": 0.077, "security_coverage_80": 0.758, "security_band_width_median": 1.35,
    "security_route_n_total": 26_000, "security_rows_implausible": 85,
    "live_security_share": 0.847, "trained_at": "2026-09-27T00:11:56Z",
    "history_by_value": {
        "coverage_per_tender": 0.784, "coverage_per_taka_estimated": 0.766,
        "coverage_per_taka_awarded": 0.638, "mean_error": 0.74,
        "share_of_escaped_taka_that_escaped_upward": 0.918,
        "strata": [{"estimate_from_lakh": 0.2 + i, "estimate_to_lakh": 4.0 * (i + 1),
                    "awards": 24_000, "mape": 0.38, "coverage_80": 0.79 - i * 0.006,
                    "above_ceiling": 0.15 - i * 0.01, "below_floor": 0.06 + i * 0.02,
                    "band_width_median": 4.9, "award_over_estimate_median": 1.16 - i * 0.05}
                   for i in range(5)]},
    "security_by_value": {
        "coverage_per_tender": 0.758, "coverage_per_taka_estimated": 0.706,
        "coverage_per_taka_awarded": 0.664, "mean_error": 0.11,
        "share_of_escaped_taka_that_escaped_upward": 0.74,
        "strata": [{"estimate_from_lakh": 0.1, "estimate_to_lakh": 5.0, "awards": 1_200,
                    "mape": 0.077, "coverage_80": 0.76, "above_ceiling": 0.11,
                    "below_floor": 0.13, "band_width_median": 1.35,
                    "award_over_estimate_median": 1.0} for _ in range(5)]},
}
CATEGORY = {
    "accuracy_acted": 0.93, "deferral_rate": 0.13, "accuracy_all": 0.868, "macro_f1": 0.715,
    "n_labels": 46_000, "n_classes": 13, "truth_coverage": 0.81, "n_tagged": 47_000,
    "deferral_for_93": 0.13, "deferral_for_95": 0.193, "repeats": 3,
    "deferral_spread": 0.0025, "macro_f1_spread": 0.005,
    "evaluation": "cross-validated against the portal's codes",
    "accuracy_acted_heldout_bar": 0.9215, "deferral_rate_heldout_bar": 0.141,
    "cost_optimal_points": [{"wrong_answer_costs": 1, "deferral": 0.01, "accuracy": 0.87},
                            {"wrong_answer_costs": 2, "deferral": 0.11, "accuracy": 0.92},
                            {"wrong_answer_costs": 3, "deferral": 0.15, "accuracy": 0.935},
                            {"wrong_answer_costs": 5, "deferral": 0.26, "accuracy": 0.955},
                            {"wrong_answer_costs": 10, "deferral": 0.38, "accuracy": 0.975}],
}
STABILITY = {"runs": 14, "from": "2026-09-20T14:37:22Z", "to": "2026-09-27T00:11:56Z", "figures": {
    "award_value_model.coverage_80": {"label": "Award band coverage, whole window", "kind": "pct",
                                     "expected_steady": True, "better": "up", "first": 0.785,
                                     "last": 0.793, "spread": 0.012, "typical_step": 0.0025,
                                     "net_change": 0.008},
    "award_value_model.history_band_width_median": {"label": "Band width, history route",
                                                   "kind": "multiple", "expected_steady": True,
                                                   "better": "down", "first": 5.09, "last": 5.05,
                                                   "spread": 0.16, "typical_step": 0.02,
                                                   "net_change": -0.04},
    "category_classifier.accuracy_acted": {"label": "Category accuracy", "kind": "pct",
                                          "expected_steady": True, "better": "up", "first": 0.93,
                                          "last": 0.93, "spread": 0.0, "typical_step": 0.0,
                                          "net_change": 0.0},
    "category_classifier.deferral_rate": {"label": "Category deferral", "kind": "pct",
                                         "expected_steady": False, "better": "down", "first": 0.156,
                                         "last": 0.13, "spread": 0.026, "typical_step": 0.002,
                                         "net_change": -0.026},
    "category_classifier.macro_f1": {"label": "Category macro F1", "kind": "score",
                                    "expected_steady": False, "better": "up", "first": 0.698,
                                    "last": 0.715, "spread": 0.018, "typical_step": 0.002,
                                    "net_change": 0.017},
}}


@pytest.fixture
def render(tmp_path, monkeypatch):
    """Render the page from whatever metrics a test asks for, and hand back the text."""
    (tmp_path / "models").mkdir()
    (tmp_path / "docs" / "product").mkdir(parents=True)
    monkeypatch.setattr(w, "ROOT", tmp_path)
    monkeypatch.setattr(w, "OUT", tmp_path / "docs" / "product" / "05-accuracy.md")

    def go(metrics: dict, stability: dict | None = STABILITY) -> str:
        (tmp_path / "models" / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
        if stability is not None:
            (tmp_path / "models" / "stability.json").write_text(json.dumps(stability), encoding="utf-8")
        w.main()
        return w.OUT.read_text(encoding="utf-8")
    return go


def test_an_untrained_project_says_so_rather_than_printing_zeros(tmp_path, monkeypatch):
    monkeypatch.setattr(w, "ROOT", tmp_path)
    out = tmp_path / "docs" / "product" / "05-accuracy.md"
    out.parent.mkdir(parents=True)
    monkeypatch.setattr(w, "OUT", out)
    w.main()
    assert "No models have been trained yet" in out.read_text(encoding="utf-8")


def test_the_two_routes_are_never_averaged_into_one_headline(render):
    page = render({"award_value_model": AWARD, "category_classifier": CATEGORY})
    assert "| Median error of the central estimate | 7.7 percent | 37.8 percent |" in page
    assert "each is measured on its own" in page


def test_coverage_is_published_three_ways_with_the_reason_they_differ(render):
    page = render({"award_value_model": AWARD, "category_classifier": CATEGORY})
    assert "| | Per tender | Per taka estimated | Per taka awarded |" in page
    assert "| From entity history | 78.4 percent | 76.6 percent | 63.8 percent |" in page
    assert "91.8 percent of the taka that fell outside a band fell above its ceiling" in page


def test_the_size_bands_say_they_are_cut_on_the_estimate(render):
    """Cutting them on the award selects the rows the model guessed low on. The page must say so."""
    page = render({"award_value_model": AWARD, "category_classifier": CATEGORY})
    assert "Bands are cut on the model's own estimate" in page
    assert "by the arithmetic of selection" in page
    assert "| Bidefy's estimate | Tenders | Median error |" in page


def test_the_sampling_interval_is_named_as_the_narrowest_of_several(render):
    page = render({"award_value_model": AWARD, "category_classifier": CATEGORY})
    assert "coverage between 78.2 percent and 78.6 percent" in page
    assert "narrowest of the several ways these numbers move" in page


def test_the_optimism_paragraph_states_the_direction_of_each_gap(render):
    """Published accuracy above held-out is optimistic; published deferral below it is too."""
    page = render({"award_value_model": AWARD, "category_classifier": CATEGORY})
    assert "delivers 92.2 percent accuracy at 14.1 percent deferral" in page
    assert "the published accuracy is 0.9 percent optimistic" in page
    assert "the published deferral 1.1 percent optimistic" in page


def test_a_conservative_gap_is_not_called_optimistic(render):
    """If the held-out figures come out better, the wording has to flip rather than lie."""
    cat = {**CATEGORY, "accuracy_acted_heldout_bar": 0.94, "deferral_rate_heldout_bar": 0.12}
    page = render({"award_value_model": AWARD, "category_classifier": cat})
    assert "the published accuracy is 1.0 percent conservative" in page
    assert "the published deferral 1.0 percent conservative" in page


def test_the_cost_curve_names_the_range_the_operating_point_holds_over(render):
    page = render({"award_value_model": AWARD, "category_classifier": CATEGORY})
    assert "| A wrong answer costs this many silences |" in page
    assert "| 3x | 15.0 percent | 93.5 percent |" in page
    # Deferral is 13 percent, so rows at 11 and 15 percent are within five points of it.
    assert "for a ratio of 2 to 3" in page
    assert "Nothing here moved the operating point" in page


def test_a_cost_curve_that_supports_no_row_says_that_plainly(render):
    """Flattering silence would be the easy option here, so the absence is stated instead."""
    cat = {**CATEGORY, "deferral_rate": 0.60}
    page = render({"award_value_model": AWARD, "category_classifier": cat})
    assert "No row of this table matches the operating point" in page


def test_a_rejected_candidate_is_announced_above_every_figure(render):
    page = render({"award_value_model": AWARD, "category_classifier": CATEGORY,
                   "blocked": {"category_classifier": {"at": "2026-09-28T00:11:03Z", "breaches": [
                       {"figure": "accuracy_acted", "was": 0.93, "now": 0.9012,
                        "lost": 0.0288, "tolerated": 0.02}]}}})
    assert page.index("A candidate was rejected") < page.index("## Award value")
    assert "| accuracy_acted | 0.93 | 0.9012 | 0.0288 | 0.02 |" in page
    assert "figures of the model still serving" in page


def test_a_clean_run_does_not_mention_rejection(render):
    page = render({"award_value_model": AWARD, "category_classifier": CATEGORY})
    assert "candidate was rejected" not in page


def test_each_tracked_figure_is_formatted_as_the_kind_of_number_it_is(render):
    """A band width is a multiple and an F1 a score. Printing either as a percent prints nonsense."""
    page = render({"award_value_model": AWARD, "category_classifier": CATEGORY})
    assert "| Band width, history route | 5.09x | 5.05x | 0.02x | 0.16x |" in page
    assert "| Category macro F1 | 0.698 | 0.715 | 0.002 | 0.018 |" in page
    assert "| Award band coverage, whole window | 78.5 percent | 79.3 percent |" in page


def test_the_noise_floor_is_quoted_from_comparable_figures_only(render):
    """The widest spread among percentages is 1.2 points; the 0.16 band width is not "16 percent"."""
    page = render({"award_value_model": AWARD, "category_classifier": CATEGORY})
    assert "by up to 1.2 percent across the week" in page


def test_movement_the_wrong_way_is_not_called_an_improvement(render):
    """The finding that mattered most: abs() would have announced a regression as the week's win."""
    figs = json.loads(json.dumps(STABILITY))
    figs["figures"]["category_classifier.deferral_rate"].update(
        first=0.13, last=0.156, net_change=0.026)
    page = render({"award_value_model": AWARD, "category_classifier": CATEGORY}, figs)
    assert "moved the wrong way by more than noise explains" in page
    assert "only reports the figures going the right way is advertising" in page
    deferral_line = next(l for l in page.splitlines() if l.startswith("- Category deferral"))
    assert "13.0 percent to 15.6 percent" in deferral_line


def test_a_flat_accuracy_is_explained_as_a_dial_not_a_triumph(render):
    page = render({"award_value_model": AWARD, "category_classifier": CATEGORY})
    assert "Category accuracy sits flat at zero" in page
    assert "is a dial and not a result" in page


def test_only_category_accuracy_gets_the_confidence_bar_explanation(render):
    """The other finding: keying off "spread == 0" would attribute any flat figure to the bar."""
    figs = json.loads(json.dumps(STABILITY))
    figs["figures"]["category_classifier.accuracy_acted"]["spread"] = 0.004      # no longer flat
    figs["figures"]["award_value_model.coverage_80"]["spread"] = 0.0             # this one is
    page = render({"award_value_model": AWARD, "category_classifier": CATEGORY}, figs)
    assert "confidence bar is set to deliver" not in page.split("## How much these numbers move")[1]


def test_no_stability_file_drops_the_section_rather_than_guessing(render):
    page = render({"award_value_model": AWARD, "category_classifier": CATEGORY}, stability={})
    assert "How much these numbers move" not in page
    assert "## Award value" in page          # the rest of the page still renders


def test_the_unusable_securities_are_accounted_for(render):
    page = render({"award_value_model": AWARD, "category_classifier": CATEGORY})
    assert "A further 85 published a figure that cannot be true" in page
