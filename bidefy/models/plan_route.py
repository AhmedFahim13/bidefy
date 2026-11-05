"""Award band from the buyer's own Annual Procurement Plan estimate, switched on by evidence alone.

Every tender page names its plan and package, and the public plan search lists that package's
estimated cost (bidefy/crawler/plan.py reads it while the tender is open). A probe of 120 awarded
tenders put the award at about 0.91 of the estimate on OTM and about all of it on RFQ, but it read
today's plans for past tenders, and a buyer can revise a plan after the award. So this route is
judged only on estimates read before their award was signed: fitted on the earlier half of those
awards and scored on the later half, with the same error measure as the other routes (miss over
the actual award).

It serves nothing until it earns it. The rule was fixed on 2026-11-05, before a single award had
been scored, so no result can be fitted to it after the fact. The route switches on when:

  - at least MIN_TEST_AWARDS awards were scored on the later half,
  - its median error there is below the security route's published median error, the most
    accurate route the product has, and
  - its 80 percent band held between 75 and 85 percent of those awards.

Until then it is measured, published in models/metrics.json and on the command centre, and left
off. When on, it prices every live tender with a matched estimate, overriding the other routes.
"""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import polars as pl

from ..crawler import store

ENDPOINT = "plan_estimates"
COVERAGE = 0.80
LO_Q, HI_Q = (1 - COVERAGE) / 2, 1 - (1 - COVERAGE) / 2
MIN_PAIRS = 20              # below this there is nothing to score
MIN_TEST_AWARDS = 200       # the gate: awards scored on the later half
COVERAGE_RANGE = (0.75, 0.85)
MIN_METHOD_PAIRS = 50       # a method thinner than this borrows the pooled band
ROUTE_FILE = "plan_route.json"


def pairs(plan: pl.DataFrame, contracts: pl.DataFrame) -> pl.DataFrame:
    """Award over plan estimate for every estimate read before its award was signed."""
    if plan.is_empty() or contracts.is_empty():
        return pl.DataFrame(schema={"tender_id": pl.Utf8, "method": pl.Utf8, "ratio": pl.Float64, "signed_on": pl.Utf8})
    p = (plan.filter(pl.col("matched").fill_null(False) & (pl.col("estimate_bdt").fill_null(0) > 0))
         .with_columns(pl.col("tender_id").cast(pl.Utf8),
                       (pl.col("fetched_at").str.slice(0, 4) + "-" + pl.col("fetched_at").str.slice(4, 2)
                        + "-" + pl.col("fetched_at").str.slice(6, 2)).alias("read_on")))
    c = (contracts.filter((pl.col("value_crore").fill_null(0) > 0) & pl.col("signed_on").is_not_null())
         .select(pl.col("tender_id").cast(pl.Utf8), "value_crore", pl.col("signed_on").cast(pl.Utf8))
         .unique("tender_id", keep="last"))
    return (p.join(c, on="tender_id").filter(pl.col("read_on") < pl.col("signed_on"))
            .select("tender_id", pl.col("plan_method").fill_null("").alias("method"),
                    (pl.col("value_crore") * 1e7 / pl.col("estimate_bdt")).alias("ratio"), "signed_on")
            .sort(["signed_on", "tender_id"]))


def _stats(log_r: np.ndarray) -> dict:
    n = len(log_r)
    return {"n": int(n), "centre": float(np.median(log_r)),
            "lo": float(np.quantile(log_r, max(0.0, LO_Q * (n + 1) / n))),
            "hi": float(np.quantile(log_r, min(1.0, HI_Q * (n + 1) / n)))}


def fit(p: pl.DataFrame) -> dict:
    """Each method's typical award over estimate and its 80 percent spread, with a pooled fallback."""
    log_r = np.log(p["ratio"].to_numpy())
    route = {"pooled": _stats(log_r), "by_method": {}}
    for (method,), g in p.group_by("method"):
        if method and g.height >= MIN_METHOD_PAIRS:
            route["by_method"][str(method)] = _stats(np.log(g["ratio"].to_numpy()))
    return route


def _band(route: dict, method: str) -> dict:
    return route["by_method"].get(str(method)) or route["pooled"]


def evaluate(p: pl.DataFrame) -> dict:
    """Fit on the earlier half of the awards by signing date, score on the later half."""
    if p.height < MIN_PAIRS:
        return {"n": p.height, "n_test": 0, "verdict": "too few awards yet"}
    ratios = p["ratio"].to_numpy()
    half = p.height // 2
    route = fit(p.head(half))
    test = p.tail(p.height - half)
    errors, inside, widths = [], 0, []
    for r in test.iter_rows(named=True):
        b = _band(route, r["method"])
        lr = float(np.log(r["ratio"]))
        errors.append(abs(np.exp(b["centre"] - lr) - 1))      # |q50 - actual| / actual
        inside += b["lo"] <= lr <= b["hi"]
        widths.append(np.exp(b["hi"] - b["lo"]))
    return {
        "n": p.height,
        "n_test": test.height,
        "test_from": str(test["signed_on"][0]),
        "median_ratio": round(float(np.median(ratios)), 4),
        "raw_error": round(float(np.median(np.abs(1 / ratios - 1))), 4),
        "mape": round(float(np.median(errors)), 4),
        "coverage_80": round(inside / test.height, 4),
        "band_width": round(float(np.median(widths)), 3),
        "by_method": {str(m): {"n": g.height, "median_ratio": round(float(np.median(g["ratio"].to_numpy())), 4)}
                      for (m,), g in p.group_by("method")},
        "verdict": "measured",
    }


def gate(e: dict, security_mape: float | None) -> tuple[bool, str]:
    """The fixed rule. Returns whether the route may serve, and why or why not."""
    if e.get("n_test", 0) < MIN_TEST_AWARDS:
        return False, f"{e.get('n_test', 0)} of {MIN_TEST_AWARDS} awards scored so far"
    if security_mape is None:
        return False, "no security route figure to beat"
    if not e["mape"] < security_mape:
        return False, f"median error {e['mape']:.1%} does not beat the security route's {security_mape:.1%}"
    lo, hi = COVERAGE_RANGE
    if not lo <= e["coverage_80"] <= hi:
        return False, f"band held {e['coverage_80']:.1%} of awards, outside {lo:.0%} to {hi:.0%}"
    return True, f"beats the security route ({e['mape']:.1%} against {security_mape:.1%}) with an honest band"


def overlay(preds: pl.DataFrame, plan: pl.DataFrame, route: dict | None) -> pl.DataFrame:
    """Reprice live tenders that have a matched plan estimate, when the route is on."""
    if not route or not route.get("active") or preds.is_empty() or plan.is_empty():
        return preds
    est = {r["tender_id"]: (r["estimate_bdt"] / 100_000, r.get("plan_method") or "")
           for r in plan.filter(pl.col("matched").fill_null(False) & (pl.col("estimate_bdt").fill_null(0) > 0))
           .with_columns(pl.col("tender_id").cast(pl.Utf8)).to_dicts()}
    rows = []
    for r in preds.to_dicts():
        hit = est.get(str(r["tender_id"]))
        if hit:
            lakh, method = hit
            b = _band(route, method)
            r = {**r, "q10_lakh": round(lakh * float(np.exp(b["lo"])), 2),
                 "q50_lakh": round(lakh * float(np.exp(b["centre"])), 2),
                 "q90_lakh": round(lakh * float(np.exp(b["hi"])), 2),
                 "deferred": False, "basis": "plan",
                 "model_version": route.get("version", r.get("model_version"))}
        rows.append(r)
    return pl.DataFrame(rows, schema=preds.schema)


def load(models_dir: Path) -> dict | None:
    path = Path(models_dir) / ROUTE_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def train(data_root: Path, models_dir: Path) -> dict:
    """Score the route, apply the gate, and write both the route and its figures."""
    data_root, models_dir = Path(data_root), Path(models_dir)
    p = pairs(store.load_all(data_root, ENDPOINT), store.load_all(data_root, "contracts"))
    e = evaluate(p)
    mpath = models_dir / "metrics.json"
    metrics = json.loads(mpath.read_text(encoding="utf-8")) if mpath.exists() else {}
    security_mape = (metrics.get("award_value_model") or {}).get("security_mape")
    active, reason = gate(e, security_mape)
    stamp = datetime.now(UTC)
    route = {**(fit(p) if p.height >= MIN_PAIRS else {"pooled": None, "by_method": {}}),
             "active": active, "reason": reason, "version": stamp.strftime("plan-%Y%m%d")}
    models_dir.mkdir(parents=True, exist_ok=True)
    (models_dir / ROUTE_FILE).write_text(json.dumps(route, indent=2) + "\n", encoding="utf-8")
    metrics["plan_route"] = {**e, "active": active, "gate": reason, "gate_min_awards": MIN_TEST_AWARDS,
                             "security_mape_to_beat": security_mape,
                             "trained_at": stamp.strftime("%Y-%m-%dT%H:%M:%SZ")}
    mpath.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    return metrics["plan_route"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Score the plan-estimate route and apply its gate")
    ap.add_argument("command", choices=["train"])
    ap.add_argument("--data-root", default="data")
    ap.add_argument("--models-dir", default="models")
    a = ap.parse_args(argv)
    print(json.dumps(train(Path(a.data_root), Path(a.models_dir)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
