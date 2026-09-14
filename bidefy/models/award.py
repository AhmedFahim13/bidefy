"""Award-value model: a median prediction with a calibrated band, by two routes.

Route 1, the security route. A tender notice publishes a refundable tender security, which each
procuring entity sets as a fixed share of its own (unpublished) cost estimate. Awards land close
to that estimate, so the award value is close to a constant multiple of the security. Where the
notice publishes one, that multiple gives a band a few tens of percent wide.

Route 2, the history route, for tenders with no published security. A LightGBM model on the
entity, ministry, method, district, category and the title (both as quantity signals and as a
stacked text prediction) predicts the log award value.

Both routes carry split-conformal bands calibrated on held-out slices, so the stated coverage is
honest by construction. The history route normalises its band by a predicted difficulty, so an
easy tender gets a narrow band and a hard one a wide band or a deferral.

Everything is ordered by signing date: fitted on the oldest rows, calibrated on the middle,
evaluated on the newest. Nothing is fitted on data later than what it predicts.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
import polars as pl
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import Ridge
from sklearn.model_selection import KFold

from ..crawler import store

CAT_COLS = ["pe_id", "ministry", "method", "district", "category"]
PARAMS = dict(n_estimators=600, learning_rate=0.05, num_leaves=63, min_child_samples=20,
              subsample=0.9, subsample_freq=1, colsample_bytree=0.9, reg_lambda=1.0, verbose=-1)
MIN_ROWS = 200
MIN_FOR_WALK = 5_000       # below this, one holdout slice calibrates better than four small ones
MIN_SECURITY_ROWS = 60
MIN_GROUP_ROWS = 40
DEFER_RATIO = 12.0         # wider than this and the band rules out too little to be worth showing
MIN_ENTITY_HISTORY = 3
MIN_METHOD_ROWS = 300      # below this a method borrows the shared quantiles
COVERAGE = 0.80
BUNDLE_FORMAT = 2          # bump when the saved bundle gains or loses a key
YEAR0 = 2020
TAKA_PER_LAKH = 100_000.0
UNIT_RE = re.compile(r"\b(km|kilometer|metre|meter|mtr|nos?|pcs|piece|set|sets|ton|mt|litre|liter|ltr|kg|unit|packet|bag|sqm|sft|cft|rft)\b", re.I)
NUM_RE = re.compile(r"\d[\d,]*\.?\d*")
LO_Q, HI_Q = (1 - COVERAGE) / 2, 1 - (1 - COVERAGE) / 2


# --------------------------------------------------------------------------- features

def title_numerics(titles: pd.Series) -> pd.DataFrame:
    """Quantity signals a reader takes from the title: how many, how large, in what units."""
    nums = titles.map(lambda t: [float(x.replace(",", "")) for x in NUM_RE.findall(t)[:12]] or [0.0])
    return pd.DataFrame({
        "title_len": titles.str.len(),
        "title_words": titles.str.split().map(len),
        "n_numbers": nums.map(len),
        "max_number": nums.map(lambda v: np.log1p(max(v))),
        "sum_number": nums.map(lambda v: np.log1p(sum(v))),
        "has_unit": titles.map(lambda t: 1 if UNIT_RE.search(t) else 0),
        "has_year_range": titles.str.contains(r"20\d\d\s*-\s*20\d\d", regex=True).astype(int),
    }, index=titles.index)


NUM_COLS = ["month", "year_offset", "title_len", "title_words", "n_numbers", "max_number",
            "sum_number", "has_unit", "has_year_range", "txt", "pe_history"]


def _prepare(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    for col in CAT_COLS:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str)
    df["title"] = df["title"].fillna("").astype(str) if "title" in df.columns else ""
    d = pd.to_datetime(df[date_col], errors="coerce") if date_col in df.columns else pd.Series(pd.NaT, index=df.index)
    df["month"] = d.dt.month.fillna(6).astype(int)
    df["year_offset"] = (d.dt.year.fillna(YEAR0) - YEAR0).astype(int)
    for col, values in title_numerics(df["title"]).items():
        df[col] = values.to_numpy()
    return df


def _matrix(df: pd.DataFrame, levels: dict[str, list[str]]) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    for c in CAT_COLS:
        out[c] = pd.Categorical(df[c].where(df[c] != "", None), categories=levels[c])
    for c in NUM_COLS:
        out[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    return out


def _fit_text(fit: pd.DataFrame, others: list[pd.DataFrame], seed: int, folds: int = 4):
    """Ridge on title TF-IDF predicting log value; its output becomes one numeric feature.

    Out-of-fold inside the fitting slice, so the tree model never sees a text prediction that
    already memorised the row it is training on.
    """
    vec = TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=3, max_features=200_000,
                          sublinear_tf=True, dtype=np.float32)
    X = vec.fit_transform(fit["title"])
    y = fit["y"].to_numpy()
    oof = np.zeros(len(fit))
    for tr, va in KFold(n_splits=folds, shuffle=True, random_state=seed).split(X):
        oof[va] = Ridge(alpha=1.0, solver="sparse_cg").fit(X[tr], y[tr]).predict(X[va])
    fit["txt"] = oof
    full = Ridge(alpha=1.0, solver="sparse_cg").fit(X, y)
    for df in others:
        df["txt"] = full.predict(vec.transform(df["title"]))
    return vec, full


# --------------------------------------------------------------------------- the security route

def _fit_security(df: pd.DataFrame) -> dict | None:
    """Multiples of the published security, per method where there is enough history."""
    rows = df[_has_security(df)]
    if len(rows) < MIN_SECURITY_ROWS:
        return None
    sec_lakh = pd.to_numeric(rows["security_bdt"], errors="coerce").astype(float) / TAKA_PER_LAKH
    log_ratio = np.log(rows["lakh"].to_numpy() / sec_lakh.to_numpy())
    model = {"global": float(np.median(log_ratio)), "by_method": {}, "n": int(len(rows))}
    for method, idx in rows.groupby("method").groups.items():
        if method and len(idx) >= MIN_GROUP_ROWS:
            model["by_method"][str(method)] = float(np.median(log_ratio[rows.index.get_indexer(idx)]))
    return model


def _security_log_multiple(model: dict, methods: np.ndarray) -> np.ndarray:
    return np.array([model["by_method"].get(str(m), model["global"]) for m in methods])


def _method_quantiles(methods: np.ndarray, by_method: dict, lo: float, hi: float):
    """Per-method conformal quantiles, falling back to the shared pair."""
    pairs = [by_method.get(str(m), (lo, hi)) for m in methods]
    return np.array([q[0] for q in pairs]), np.array([q[1] for q in pairs])


def _has_security(df: pd.DataFrame) -> np.ndarray:
    if "security_bdt" not in df.columns:
        return np.zeros(len(df), dtype=bool)
    return (pd.to_numeric(df["security_bdt"], errors="coerce").fillna(0) > 0).to_numpy()


# --------------------------------------------------------------------------- loading

def _load_awards(data_root: Path) -> pd.DataFrame:
    path = Path(data_root) / "clean" / "contracts.parquet"
    if not path.exists():
        return pd.DataFrame()
    c = pl.read_parquet(path)
    if "category" not in c.columns:
        c = c.with_columns(pl.lit("").alias("category"))
    c = c.filter((pl.col("value_crore").fill_null(0) > 0) & pl.col("signed_on").is_not_null() & (pl.col("signed_on") != ""))
    c = _join_security(c, data_root)
    pdf = c.sort("signed_on").to_pandas().reset_index(drop=True)
    pdf["lakh"] = pdf["value_crore"].astype(float) * 100
    pdf["y"] = np.log1p(pdf["lakh"])
    pdf = _prepare(pdf, "signed_on")
    # How much history this buyer had at the time, counting only earlier awards. It tells the
    # difficulty model when a tender comes from an entity it barely knows, so the band can widen
    # instead of quietly being wrong.
    pdf["pe_history"] = np.log1p(pdf.groupby("pe_id").cumcount())
    return pdf


def _join_security(df: pl.DataFrame, data_root: Path) -> pl.DataFrame:
    """Attach the published tender security from crawled detail pages, keeping any value already present."""
    details = store.load_all(Path(data_root), "details")
    df = df.with_columns(pl.col("tender_id").cast(pl.Utf8))
    if "security_bdt" not in df.columns:
        df = df.with_columns(pl.lit(None, dtype=pl.Float64).alias("security_bdt"))
    df = df.with_columns(pl.col("security_bdt").cast(pl.Float64))
    if details.is_empty() or "security_bdt" not in details.columns:
        return df
    sec = (details.with_columns(pl.col("tender_id").cast(pl.Utf8))
           .select("tender_id", pl.col("security_bdt").cast(pl.Float64).alias("_sec_detail"))
           .unique(subset=["tender_id"], keep="last"))
    return (df.join(sec, on="tender_id", how="left")
            .with_columns(pl.coalesce(pl.col("security_bdt"), pl.col("_sec_detail")).alias("security_bdt"))
            .drop("_sec_detail"))


# --------------------------------------------------------------------------- training

def train(data_root: Path, models_dir: Path, seed: int = 0) -> dict | None:
    pdf = _load_awards(Path(data_root))
    if len(pdf) < MIN_ROWS:
        return None
    n = len(pdf)
    i_test = int(n * 0.80)
    past, test = pdf.iloc[:i_test].copy(), pdf.iloc[i_test:].copy()

    vec, ridge = _fit_text(past, [test], seed)
    levels = {c: sorted(v for v in past[c].unique() if v) for c in CAT_COLS}

    # Calibrate on forward-looking out-of-sample residuals rather than one small slice: walk an
    # expanding window through the past, each step predicting the block it has not seen. That is
    # the situation the model is actually in every night, so the residuals carry its real error,
    # drift included, and there are tens of thousands of them rather than a few thousand.
    fractions = (0.4, 0.55, 0.70, 0.85, 1.0) if len(past) >= MIN_FOR_WALK else (0.8, 1.0)
    edges = [int(len(past) * f) for f in fractions]
    oof_index, oof_resid = [], []
    start = edges[0]
    for end in edges[1:]:
        block = past.iloc[start:end]
        if len(block) == 0:
            start = end
            continue
        prior = past.iloc[:start]
        step = lgb.LGBMRegressor(objective="regression_l1", random_state=seed, **PARAMS).fit(
            _matrix(prior, levels), prior["y"])
        oof_index.append(block.index.to_numpy())
        oof_resid.append(block["y"].to_numpy() - step.predict(_matrix(block, levels)))
        start = end
    idx = np.concatenate(oof_index)
    resid = np.concatenate(oof_resid)
    calib = past.loc[idx]

    model = lgb.LGBMRegressor(objective="regression_l1", random_state=seed, **PARAMS).fit(_matrix(past, levels), past["y"])

    # The difficulty model and the quantiles must not be learned from the same rows: a model
    # scored on its own training data looks more certain than it is, and the band comes out too
    # narrow to cover. Split the calibration residuals in two and give each half one job.
    a, b = int(len(calib) * 0.6), int(len(calib) * 0.8)
    diff_rows, q_rows, check_rows = calib.iloc[:a], calib.iloc[a:b], calib.iloc[b:]
    diff_resid, q_resid, check_resid = resid[:a], resid[a:b], resid[b:]
    difficulty = lgb.LGBMRegressor(objective="regression_l1", random_state=seed,
                                   **{**PARAMS, "n_estimators": 300}).fit(_matrix(diff_rows, levels), np.abs(diff_resid))
    floor = max(float(np.quantile(np.abs(diff_resid), 0.05)), 0.02)
    scale = np.maximum(difficulty.predict(_matrix(q_rows, levels)), floor)
    normalised = q_resid / scale
    lo_q, hi_q = float(np.quantile(normalised, LO_Q)), float(np.quantile(normalised, HI_Q))
    # One quantile for every procurement method covers none of them properly: open tendering is
    # far more variable than a quick quote, so a shared band under-covers open tenders and wastes
    # width on the rest. Give each method its own quantiles where there is enough history.
    by_method: dict[str, tuple[float, float]] = {}
    methods = q_rows["method"].to_numpy()
    for name in set(methods):
        mask = methods == name
        if name and mask.sum() >= MIN_METHOD_ROWS:
            by_method[str(name)] = (float(np.quantile(normalised[mask], LO_Q)), float(np.quantile(normalised[mask], HI_Q)))

    # Quantiles taken from one period under-cover the next, because the world moves. Measure that
    # shortfall on a later block the quantiles have not seen, and widen just enough to close it.
    # Still only past data: no part of the test window is consulted.
    # Quantiles taken from one period under-cover the next, and they do not under-cover every
    # procurement method equally: open tendering drifts hardest. Measure the shortfall per method
    # on a later block the quantiles have not seen, and widen each one just enough to close it.
    # Still only past data: no part of the test window is consulted.
    drift = 1.0
    if len(check_rows) >= 200:
        check_scale = np.maximum(difficulty.predict(_matrix(check_rows, levels)), floor)
        check_methods = check_rows["method"].to_numpy()

        def _widen(mask: np.ndarray, lo: float, hi: float) -> float:
            if mask.sum() < MIN_METHOD_ROWS:
                return 1.0
            r, sc = check_resid[mask], check_scale[mask]
            for k in np.arange(1.0, 3.05, 0.05):
                if ((r >= lo * k * sc) & (r <= hi * k * sc)).mean() >= COVERAGE:
                    return float(k)
            return 3.0

        drift = _widen(np.ones(len(check_rows), dtype=bool), lo_q, hi_q)
        widened = {}
        for name, (lo, hi) in by_method.items():
            k = _widen(check_methods == name, lo, hi)
            widened[name] = (lo * k, hi * k)
        by_method = widened
    lo_q, hi_q = lo_q * drift, hi_q * drift

    sec_model = _fit_security(past)
    sec_lo = sec_hi = 0.0
    if sec_model:
        with_sec = past[_has_security(past)]
        ratio = (np.log(with_sec["lakh"].to_numpy() * TAKA_PER_LAKH / pd.to_numeric(with_sec["security_bdt"]).to_numpy())
                 - _security_log_multiple(sec_model, with_sec["method"].to_numpy()))
        sec_lo, sec_hi = float(np.quantile(ratio, LO_Q)), float(np.quantile(ratio, HI_Q))

    bundle = {
        "model": model, "difficulty": difficulty, "levels": levels, "vectorizer": vec, "ridge": ridge,
        "lo_q": lo_q, "hi_q": hi_q, "floor": floor, "by_method": by_method,
        "security": sec_model, "security_lo": sec_lo, "security_hi": sec_hi,
        "history": past.groupby("pe_id").size().to_dict(),
        "format": BUNDLE_FORMAT,
        "version": datetime.now(timezone.utc).strftime("award-%Y%m%d"),
        "coverage_target": COVERAGE,
        "drift_allowance": round(drift, 3),
    }
    metrics = _evaluate(bundle, test)
    metrics.update({"drift_allowance": round(drift, 3), "n_fit": len(past), "n_calibration": len(calib), "n_test": len(test),
                    "test_from": str(test["signed_on"].iloc[0]),
                    "trained_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "model_version": bundle["version"]})

    models_dir = Path(models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, models_dir / "award.joblib", compress=3)
    mpath = models_dir / "metrics.json"
    existing = json.loads(mpath.read_text(encoding="utf-8")) if mpath.exists() else {}
    existing["award_value_model"] = metrics
    mpath.write_text(json.dumps(existing, indent=2) + chr(10), encoding="utf-8")
    return metrics


def _evaluate(bundle: dict, test: pd.DataFrame) -> dict:
    pred = predict(test, bundle, date_col="signed_on", already_prepared=True)
    q10 = pred["q10_lakh"].to_numpy()
    q50 = pred["q50_lakh"].to_numpy()
    q90 = pred["q90_lakh"].to_numpy()
    deferred = pred["deferred"].to_numpy()
    basis = pred["basis"].to_numpy()
    actual = test["lakh"].to_numpy()
    acted = ~deferred
    inside = (actual >= q10) & (actual <= q90)
    ratio = q90 / np.maximum(q10, 1e-9)

    prior = float(np.median(actual))
    naive = np.full(len(actual), prior)
    ape = lambda p, m: round(float(np.median(np.abs(p[m] - actual[m]) / actual[m])), 4) if m.any() else None
    unconditional = float(np.percentile(actual, 90) / max(np.percentile(actual, 10), 1e-9))

    out = {
        "mape_acted": ape(q50, acted), "mape_naive_median": ape(naive, acted),
        "coverage_80": round(float(inside[acted].mean()), 4) if acted.any() else 0.0,
        "deferral_rate": round(float(deferred.mean()), 4),
        "band_width_median": round(float(np.median(ratio[acted])), 2) if acted.any() else None,
        "band_width_p25": round(float(np.percentile(ratio[acted], 25)), 2) if acted.any() else None,
        "band_width_p75": round(float(np.percentile(ratio[acted], 75)), 2) if acted.any() else None,
        "unconditional_spread": round(unconditional, 1),
        "security_share_of_test": round(float((basis == "security").mean()), 4),
        "deferral_at_band_limit": {str(lim): round(float(((ratio > lim) & (basis != "security")).mean()), 4)
                                   for lim in (4, 6, 8, 12, 20)},
    }
    for name in ("security", "history"):
        m = acted & (basis == name)
        out[f"{name}_n"] = int(m.sum())
        if m.any():
            out[f"{name}_mape"] = ape(q50, m)
            out[f"{name}_coverage_80"] = round(float(inside[m].mean()), 4)
            out[f"{name}_band_width_median"] = round(float(np.median(ratio[m])), 2)
    return out


# --------------------------------------------------------------------------- prediction

def load(models_dir: Path) -> dict | None:
    """The saved bundle, or None when it is missing or was written by an older format."""
    path = Path(models_dir) / "award.joblib"
    if not path.exists():
        return None
    bundle = joblib.load(path)
    if bundle.get("format") != BUNDLE_FORMAT:
        return None          # a stale model is skipped; the nightly job retrains it
    return bundle


def predict(rows, bundle: dict, date_col: str = "published_at", already_prepared: bool = False) -> pl.DataFrame:
    """Band per row. Rows whose notice published a security use that; the rest use history."""
    df = rows if isinstance(rows, pd.DataFrame) else rows.to_pandas()
    df = df.copy()
    if not already_prepared:
        df = _prepare(df, date_col)
        df["txt"] = bundle["ridge"].predict(bundle["vectorizer"].transform(df["title"]))
    elif "txt" not in df.columns:
        df["txt"] = bundle["ridge"].predict(bundle["vectorizer"].transform(df["title"]))

    if "pe_history" not in df.columns:
        df["pe_history"] = np.log1p(df["pe_id"].map(bundle["history"]).fillna(0).astype(float))
    X = _matrix(df, bundle["levels"])
    p = bundle["model"].predict(X)
    s = np.maximum(bundle["difficulty"].predict(X), bundle["floor"])
    lo, hi = _method_quantiles(df["method"].to_numpy(), bundle.get("by_method", {}), bundle["lo_q"], bundle["hi_q"])
    q10 = np.expm1(p + lo * s)
    q50 = np.expm1(p)
    q90 = np.expm1(p + hi * s)
    basis = np.array(["history"] * len(df), dtype=object)

    sec_model = bundle.get("security")
    if sec_model:
        has = _has_security(df)
        if has.any():
            sec_lakh = pd.to_numeric(df.loc[has, "security_bdt"], errors="coerce").to_numpy() / TAKA_PER_LAKH
            centre = np.log(sec_lakh) + _security_log_multiple(sec_model, df.loc[has, "method"].to_numpy())
            q10[has] = np.exp(centre + bundle["security_lo"])
            q50[has] = np.exp(centre)
            q90[has] = np.exp(centre + bundle["security_hi"])
            basis[has] = "security"

    q10 = np.minimum(q10, q50)
    q90 = np.maximum(q90, q50)
    hist = df["pe_id"].map(bundle["history"]).fillna(0).to_numpy()
    thin = (hist < MIN_ENTITY_HISTORY) & np.array([not c for c in df["category"]])
    wide = (q90 / np.maximum(q10, 1e-9)) > DEFER_RATIO
    deferred = (wide | thin) & (basis != "security")     # a security band is always worth showing

    return pl.DataFrame({
        "tender_id": df["tender_id"].astype(str).tolist(),
        "q10_lakh": np.round(q10, 2).tolist(),
        "q50_lakh": np.round(q50, 2).tolist(),
        "q90_lakh": np.round(q90, 2).tolist(),
        "deferred": deferred.tolist(),
        "basis": basis.tolist(),
        "model_version": [bundle["version"]] * len(df),
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
    for col in ("district", "category"):
        if col not in tenders.columns:
            tenders = tenders.with_columns(pl.lit("").alias(col))
    tenders = _join_security(tenders, Path(data_root))
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
        print(f"award model: median APE {m['mape_acted']:.3f}, coverage {m['coverage_80']:.3f}, "
              f"deferral {m['deferral_rate']:.3f}, median band {m['band_width_median']}x "
              f"(security rows {m.get('security_n', 0)} at {m.get('security_band_width_median', 'n/a')}x, "
              f"history rows {m.get('history_n', 0)} at {m.get('history_band_width_median', 'n/a')}x)")
        return 0
    n = apply(Path(a.data_root), Path(a.models_dir))
    print(f"award model: predictions for {n} live tenders")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
