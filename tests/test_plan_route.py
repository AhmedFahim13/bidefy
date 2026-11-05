import math

import polars as pl

from bidefy.models import plan_route as pr


def _forward(n=300, ratio=0.9, method="OTM", start=1):
    """n awards, each signed the day after its estimate was read, at award = ratio x estimate."""
    plan = pl.DataFrame({
        "tender_id": [str(i) for i in range(start, start + n)],
        "matched": [True] * n,
        "estimate_bdt": [1_000_000.0] * n,
        "plan_method": [method] * n,
        "fetched_at": [f"2026{11 + (i // 28) % 2:02d}{(i % 28) + 1:02d}T000000000000Z" for i in range(n)],
    })
    contracts = pl.DataFrame({
        "tender_id": [str(i) for i in range(start, start + n)],
        "value_crore": [ratio * 0.1] * n,
        "signed_on": [f"2026-{11 + (i // 28) % 2:02d}-{(i % 28) + 1:02d}" for i in range(n)],
    })
    # read the day before signing: shift the signing one day later
    contracts = contracts.with_columns(
        (pl.col("signed_on").str.to_date() + pl.duration(days=1)).dt.strftime("%Y-%m-%d").alias("signed_on"))
    return plan, contracts


def test_pairs_keep_only_estimates_read_before_the_award_was_signed():
    plan, contracts = _forward(n=3)
    late = pl.DataFrame({"tender_id": ["L"], "matched": [True], "estimate_bdt": [1e6], "plan_method": ["OTM"],
                         "fetched_at": ["20261130T000000000000Z"]})
    unmatched = pl.DataFrame({"tender_id": ["U"], "matched": [False], "estimate_bdt": [None],
                              "plan_method": [""], "fetched_at": ["20261101T000000000000Z"]})
    awards = pl.DataFrame({"tender_id": ["L", "U"], "value_crore": [0.09, 0.09], "signed_on": ["2026-11-02"] * 2})
    p = pr.pairs(pl.concat([plan, late, unmatched], how="diagonal_relaxed"),
                 pl.concat([contracts, awards], how="diagonal_relaxed"))
    assert sorted(p["tender_id"].to_list()) == ["1", "2", "3"]
    assert all(abs(r - 0.9) < 1e-9 for r in p["ratio"].to_list())


def test_fit_learns_each_methods_discount_and_falls_back_to_the_pool():
    a, ca = _forward(n=120, ratio=0.9, method="OTM")
    b, cb = _forward(n=120, ratio=1.0, method="RFQ", start=1000)
    thin, ct = _forward(n=5, ratio=0.5, method="DPM", start=5000)
    route = pr.fit(pr.pairs(pl.concat([a, b, thin]), pl.concat([ca, cb, ct])))
    assert abs(math.exp(route["by_method"]["OTM"]["centre"]) - 0.9) < 1e-9
    assert abs(math.exp(route["by_method"]["RFQ"]["centre"]) - 1.0) < 1e-9
    assert "DPM" not in route["by_method"]          # five awards borrow the pooled figures


def test_evaluate_fits_the_earlier_awards_and_scores_the_later_ones():
    plan, contracts = _forward(n=400, ratio=0.9)
    e = pr.evaluate(pr.pairs(plan, contracts))
    assert e["n_test"] == 200
    assert e["raw_error"] == round(1 / 0.9 - 1, 4)  # the estimate alone misses by its 11 percent
    assert e["mape"] == 0.0 and e["coverage_80"] == 1.0


def test_gate_needs_enough_awards_a_better_error_and_an_honest_band():
    ok = {"n_test": 250, "mape": 0.04, "coverage_80": 0.80}
    assert pr.gate(ok, security_mape=0.067)[0] is True
    assert pr.gate({**ok, "n_test": 150}, security_mape=0.067)[0] is False
    assert pr.gate({**ok, "mape": 0.07}, security_mape=0.067)[0] is False
    assert pr.gate({**ok, "coverage_80": 0.70}, security_mape=0.067)[0] is False
    assert pr.gate({**ok, "coverage_80": 0.95}, security_mape=0.067)[0] is False
    assert pr.gate(ok, security_mape=None)[0] is False   # nothing to beat is not a pass


def _preds():
    return pl.DataFrame({"tender_id": ["7", "8"], "q10_lakh": [1.0, 1.0], "q50_lakh": [2.0, 2.0],
                         "q90_lakh": [3.0, 3.0], "deferred": [True, False], "basis": ["history", "security"],
                         "model_version": ["award-x", "award-x"]})


def test_an_active_route_prices_tenders_with_a_matched_estimate_and_leaves_the_rest():
    route = {"active": True, "pooled": {"centre": math.log(0.9), "lo": math.log(0.8), "hi": math.log(1.0)},
             "by_method": {}, "version": "plan-20261205"}
    plan = pl.DataFrame({"tender_id": ["7"], "matched": [True], "estimate_bdt": [5_000_000.0], "plan_method": ["OTM"]})
    out = {r["tender_id"]: r for r in pr.overlay(_preds(), plan, route).to_dicts()}
    assert out["7"]["basis"] == "plan" and out["7"]["deferred"] is False
    assert (out["7"]["q10_lakh"], out["7"]["q50_lakh"], out["7"]["q90_lakh"]) == (40.0, 45.0, 50.0)
    assert out["8"] == _preds().to_dicts()[1]


def test_an_inactive_route_changes_nothing():
    route = {"active": False, "pooled": {"centre": 0.0, "lo": 0.0, "hi": 0.0}, "by_method": {}}
    plan = pl.DataFrame({"tender_id": ["7"], "matched": [True], "estimate_bdt": [5e6], "plan_method": ["OTM"]})
    assert pr.overlay(_preds(), plan, route).equals(_preds())
