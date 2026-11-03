"""Forward test of the Annual Procurement Plan estimate as a predictor of the award.

Only estimates read before their award was signed count, so a plan revised after the award cannot
flatter the result. The discount each method's awards take off the estimate is fitted on the earlier
half of the awards by signing date and scored on the later half, and the 80 percent band is the
earlier half's 10th to 90th percentile of award over estimate. Run it once a few weeks of awards have
landed (bidefy.crawler.plan started recording on 2026-11-03):

    uv run python tools/plan_forward_test.py
"""
from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bidefy.crawler import plan as plan_mod, store  # noqa: E402

MIN_AWARDS = 20


def _q(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, max(0, round(q * (len(xs) - 1))))]


def forward_test(plan: pl.DataFrame, contracts: pl.DataFrame) -> dict:
    p = (plan.filter(pl.col("matched") & pl.col("estimate_bdt").is_not_null() & (pl.col("estimate_bdt") > 0))
         .with_columns(pl.col("tender_id").cast(pl.Utf8),
                       (pl.col("fetched_at").str.slice(0, 4) + "-" + pl.col("fetched_at").str.slice(4, 2)
                        + "-" + pl.col("fetched_at").str.slice(6, 2)).alias("read_on")))
    c = (contracts.filter(pl.col("value_crore") > 0)
         .select(pl.col("tender_id").cast(pl.Utf8), "value_crore", "method", pl.col("signed_on").cast(pl.Utf8))
         .unique("tender_id"))
    j = (p.join(c, on="tender_id").filter(pl.col("read_on") < pl.col("signed_on"))
         .with_columns((pl.col("value_crore") * 1e7 / pl.col("estimate_bdt")).alias("ratio"))
         .sort("signed_on"))
    out: dict = {"n": j.height}
    if j.height < MIN_AWARDS:
        return {**out, "verdict": "too few awards yet"}
    ratios = j["ratio"].to_list()
    out["median_ratio"] = round(st.median(ratios), 4)
    out["raw_error"] = round(st.median([abs(1 - r) for r in ratios]), 4)
    half = j.height // 2
    fit, test = j.head(half), j.tail(j.height - half)
    disc = {m: st.median(g["ratio"].to_list()) for (m,), g in fit.group_by("method")}
    pooled = st.median(fit["ratio"].to_list())
    lo, hi = _q(fit["ratio"].to_list(), 0.10), _q(fit["ratio"].to_list(), 0.90)
    scaled, inside = [], 0
    for r in test.iter_rows(named=True):
        d = disc.get(r["method"], pooled)
        scaled.append(abs(1 - r["ratio"] / d))
        inside += lo <= r["ratio"] <= hi
    out.update({
        "n_test": test.height,
        "scaled_error": round(st.median(scaled), 4),
        "band_coverage": round(inside / test.height, 4),
        "band_width": round(hi / lo, 3) if lo > 0 else None,
        "by_method": {m: {"n": g.height, "median_ratio": round(st.median(g["ratio"].to_list()), 4)}
                      for (m,), g in j.group_by("method")},
        "verdict": "measured",
    })
    return out


def main() -> None:
    data = ROOT / "data"
    r = forward_test(store.load_all(data, plan_mod.ENDPOINT), store.load_all(data, "contracts"))
    metrics_path = ROOT / "models" / "metrics.json"
    if metrics_path.exists():
        a = json.loads(metrics_path.read_text(encoding="utf-8")).get("award_value_model", {})
        r["today_for_comparison"] = {k: a.get(k) for k in ("security_mape", "security_coverage_80",
                                                           "security_band_width_median", "mape_acted")}
    print(json.dumps(r, indent=2))


if __name__ == "__main__":
    main()
