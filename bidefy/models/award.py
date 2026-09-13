"""Award-value model: a median prediction with a conformal band (10th to 90th residual percentiles).

A LightGBM model predicts the log award value. The band around it comes from the empirical residual
quantiles on a calibration slice held out by date (per category when there is enough data), so the
80 percent coverage claim is honest by construction. Trained on indexed contract awards, evaluated on
the latest 20 percent by signing date. Predictions are written for live tenders, in lakh taka.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
import polars as pl

CAT_COLS = ["pe_id", "ministry", "method", "district", "category"]
NUM_COLS = ["month", "year_offset", "title_len"]
MIN_ROWS = 200
MIN_CAL_PER_CATEGORY = 30
DEFER_RATIO = 12.0
MIN_ENTITY_HISTORY = 3
YEAR0 = 2020
PARAMS = dict(n_estimators=300, learning_rate=0.05, num_leaves=15, min_child_samples=25, subsample=0.9,
              subsample_freq=1, colsample_bytree=0.9, reg_lambda=1.0, verbose=-1)


def _frame(df: pl.DataFrame, date_col: str) -> pd.DataFrame:
    pdf = df.to_pandas()
    for c in CAT_COLS:
        if c not in pdf.columns:
            pdf[c] = ""
        pdf[c] = pdf[c].fillna("").astype(str)
    d = pd.to_datetime(pdf[date_col], errors="coerce") if date_col in pdf.columns else pd.Series(pd.NaT, index=pdf.index)
    pdf["month"] = d.dt.month.fillna(6).astype(int)
    pdf["year_offset"] = (d.dt.year.fillna(YEAR0) - YEAR0).astype(int)
    pdf["title_len"] = pdf["title"].fillna("").astype(str).str.len() if "title" in pdf.columns else 0
    return pdf


def _encode(pdf: pd.DataFrame, levels: dict[str, list[str]] | None = None) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    out = pd.DataFrame(index=pdf.index)
    levels = levels or {}
    for c in CAT_COLS:
        cats = levels.get(c) or sorted(v for v in pdf[c].unique() if v)
        levels[c] = list(cats)
        out[c] = pd.Categorical(pdf[c].where(pdf[c] != "", None), categories=cats)
    for c in NUM_COLS:
        out[c] = pdf[c].astype(float)
    return out, levels


def _baseline(train: pd.DataFrame) -> dict:
    return {
        "pe_cat": train.groupby(["pe_id", "category"])["lakh"].median().to_dict(),
        "cat": train.groupby("category")["lakh"].median().to_dict(),
        "global": float(train["lakh"].median()),
    }


def _baseline_predict(b: dict, pe: str, cat: str) -> float:
    return b["pe_cat"].get((pe, cat), b["cat"].get(cat, b["global"]))


def _load_contracts(data_root: Path) -> pl.DataFrame:
    path = Path(data_root) / "clean" / "contracts.parquet"
    if not path.exists():
        return pl.DataFrame()
    df = pl.read_parquet(path)
    if "category" not in df.columns:
        df = df.with_columns(pl.lit("").alias("category"))
    return df.filter((pl.col("value_crore").fill_null(0) > 0) & pl.col("signed_on").is_not_null() & (pl.col("signed_on") != ""))


def _residual_quantiles(cal: pd.DataFrame, pred_log: np.ndarray) -> dict:
    """10th and 90th percentiles of log residuals, per category with enough rows, plus a global fallback."""
    res = cal["y"].to_numpy() - pred_log
    out = {"global": (float(np.quantile(res, 0.1)), float(np.quantile(res, 0.9))), "by_category": {}}
    cats = cal["category"].to_numpy()
    for c in set(cats):
        mask = cats == c
        if c and mask.sum() >= MIN_CAL_PER_CATEGORY:
            out["by_category"][c] = (float(np.quantile(res[mask], 0.1)), float(np.quantile(res[mask], 0.9)))
    return out


def _band(pred_log: np.ndarray, categories: np.ndarray, rq: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    lo = np.array([rq["by_category"].get(c, rq["global"])[0] for c in categories])
    hi = np.array([rq["by_category"].get(c, rq["global"])[1] for c in categories])
    q50 = np.expm1(pred_log)
    return np.expm1(pred_log + lo), q50, np.expm1(pred_log + hi)


def _fit_with_calibration(pdf: pd.DataFrame, seed: int) -> tuple[lgb.LGBMRegressor, dict, dict[str, list[str]]]:
    """Fit on the first 85 percent by date, calibrate residual quantiles on the last 15 percent."""
    cut = int(len(pdf) * 0.85)
    fit, cal = pdf.iloc[:cut], pdf.iloc[cut:]
    X_fit, levels = _encode(fit)
    model = lgb.LGBMRegressor(objective="regression_l1", random_state=seed, **PARAMS).fit(X_fit, fit["y"])
    X_cal, _ = _encode(cal, levels)
    rq = _residual_quantiles(cal, model.predict(X_cal))
    return model, rq, levels


def train(data_root: Path, models_dir: Path, seed: int = 0) -> dict | None:
    df = _load_contracts(data_root)
    if df.height < MIN_ROWS:
        return None
    pdf = _frame(df.sort("signed_on"), "signed_on")
    pdf["lakh"] = pdf["value_crore"].astype(float) * 100
    pdf["y"] = np.log1p(pdf["lakh"])
    cut = int(len(pdf) * 0.8)
    tr, te = pdf.iloc[:cut].copy(), pdf.iloc[cut:].copy()
    model, rq, levels = _fit_with_calibration(tr, seed)
    X_te, _ = _encode(te, levels)
    history = tr.groupby("pe_id").size().to_dict()
    q10, q50, q90 = _band(model.predict(X_te), te["category"].to_numpy(), rq)
    deferred = _defer_mask(q10, q90, te["pe_id"].map(history).fillna(0).to_numpy(), te["category"].to_numpy())
    acted = ~deferred
    actual = te["lakh"].to_numpy()
    base = _baseline(tr)
    bpred = np.array([_baseline_predict(base, p, c) for p, c in zip(te["pe_id"], te["category"])])
    ape = lambda pred: float(np.median(np.abs(pred[acted] - actual[acted]) / actual[acted])) if acted.any() else 1.0
    metrics = {
        "mape_acted": round(ape(q50), 4),
        "mape_baseline": round(ape(bpred), 4),
        "coverage_80": round(float(((actual >= q10) & (actual <= q90))[acted].mean()), 4) if acted.any() else 0.0,
        "deferral_rate": round(float(deferred.mean()), 4),
        "band_ratio_median": round(float(np.median((q90 / np.maximum(q10, 1e-6))[acted])), 2) if acted.any() else 0.0,
        "n_train": int(len(tr)),
        "n_test": int(len(te)),
        "test_from": str(te["signed_on"].iloc[0]),
        "trained_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model_version": datetime.now(timezone.utc).strftime("award-%Y%m%d"),
    }
    final_model, final_rq, final_levels = _fit_with_calibration(pdf, seed)
    bundle = {"model": final_model, "residuals": final_rq, "levels": final_levels,
              "history": pdf.groupby("pe_id").size().to_dict(), "baseline": _baseline(pdf), "version": metrics["model_version"]}
    models_dir = Path(models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, models_dir / "award.joblib", compress=3)
    mpath = models_dir / "metrics.json"
    existing = json.loads(mpath.read_text(encoding="utf-8")) if mpath.exists() else {}
    existing["award_value_model"] = metrics
    mpath.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    return metrics


def _defer_mask(q10: np.ndarray, q90: np.ndarray, history: np.ndarray, category: np.ndarray) -> np.ndarray:
    ratio = q90 / np.maximum(q10, 1e-6)
    thin = (history < MIN_ENTITY_HISTORY) & (np.array([not c for c in category]))
    return (ratio > DEFER_RATIO) | thin


def load(models_dir: Path) -> dict | None:
    path = Path(models_dir) / "award.joblib"
    return joblib.load(path) if path.exists() else None


def predict(rows: pl.DataFrame, bundle: dict, date_col: str = "published_at") -> pl.DataFrame:
    pdf = _frame(rows, date_col)
    X, _ = _encode(pdf, bundle["levels"])
    q10, q50, q90 = _band(bundle["model"].predict(X), pdf["category"].to_numpy(), bundle["residuals"])
    hist = pdf["pe_id"].map(bundle["history"]).fillna(0).to_numpy()
    deferred = _defer_mask(q10, q90, hist, pdf["category"].to_numpy())
    return pl.DataFrame({
        "tender_id": pdf["tender_id"].astype(str).tolist(),
        "q10_lakh": np.round(q10, 2).tolist(),
        "q50_lakh": np.round(q50, 2).tolist(),
        "q90_lakh": np.round(q90, 2).tolist(),
        "deferred": deferred.tolist(),
        "model_version": [bundle["version"]] * len(pdf),
    })


def apply(data_root: Path, models_dir: Path) -> int:
    bundle = load(models_dir)
    tpath = Path(data_root) / "clean" / "tenders.parquet"
    if not bundle or not tpath.exists():
        return 0
    tenders = pl.read_parquet(tpath)
    if "status" in tenders.columns:
        tenders = tenders.filter(pl.col("status") == "Live")
    if tenders.is_empty():
        return 0
    if "district" not in tenders.columns:
        tenders = tenders.with_columns(pl.lit("").alias("district"))
    if "category" not in tenders.columns:
        tenders = tenders.with_columns(pl.lit("").alias("category"))
    preds = predict(tenders, bundle)
    out = Path(data_root) / "clean" / "predictions.parquet"
    tmp = out.with_suffix(".parquet.tmp")
    preds.write_parquet(tmp, compression="zstd")
    tmp.replace(out)
    return preds.height


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Train or apply the award-value model")
    ap.add_argument("command", choices=["train", "apply"])
    ap.add_argument("--data-root", default="data")
    ap.add_argument("--models-dir", default="models")
    a = ap.parse_args(argv)
    if a.command == "train":
        m = train(Path(a.data_root), Path(a.models_dir))
        if m is None:
            print("award model: not enough awards yet, nothing trained")
            return 0
        print(f"award model: median APE {m['mape_acted']:.3f} vs baseline {m['mape_baseline']:.3f}, "
              f"80% band coverage {m['coverage_80']:.3f}, deferral {m['deferral_rate']:.3f}, train {m['n_train']}, test {m['n_test']}")
        return 0
    n = apply(Path(a.data_root), Path(a.models_dir))
    print(f"award model: predictions for {n} live tenders")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
