import polars as pl

from tools import plan_forward_test as fwd


def _frames(n=40):
    # every award is 0.9 of its estimate, read a day before the signing
    plan = pl.DataFrame({
        "tender_id": [str(i) for i in range(n)] + ["late", "nomatch"],
        "matched": [True] * n + [True, False],
        "estimate_bdt": [1_000_000.0] * n + [1_000_000.0, None],
        "fetched_at": [f"202610{(i % 28) + 1:02d}T000000000000Z" for i in range(n)]
                      + ["20261130T000000000000Z", "20261001T000000000000Z"],
    })
    contracts = pl.DataFrame({
        "tender_id": [str(i) for i in range(n)] + ["late", "nomatch"],
        "value_crore": [0.09] * n + [0.09, 0.09],
        "method": ["OTM"] * n + ["OTM", "OTM"],
        "signed_on": [f"2026-10-{(i % 28) + 2:02d}" for i in range(n)] + ["2026-11-01", "2026-11-01"],
    })
    return plan, contracts


def test_only_estimates_read_before_the_award_count():
    plan, contracts = _frames()
    r = fwd.forward_test(plan, contracts)
    # "late" was read after its award was signed and "nomatch" had no estimate
    assert r["n"] == 40


def test_discount_is_fitted_on_earlier_awards_and_scored_on_later_ones():
    plan, contracts = _frames()
    r = fwd.forward_test(plan, contracts)
    assert r["median_ratio"] == 0.9
    assert r["raw_error"] == 0.1                  # the estimate itself is 10 percent high
    assert r["scaled_error"] == 0.0               # the fitted 0.9 discount removes it
    assert r["band_coverage"] == 1.0 and r["n_test"] == 20


def test_too_few_awards_says_so():
    plan, contracts = _frames(n=4)
    assert fwd.forward_test(plan, contracts)["verdict"] == "too few awards yet"
