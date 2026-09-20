"""Award-value model: a median prediction with a calibrated band, by two routes.

Route 1, the security route. A tender notice publishes a refundable tender security, which each
procuring entity sets as a fixed share of its own (unpublished) cost estimate. Awards land close
to that estimate, so the award value is close to a multiple of the security, and each buyer tends
to keep to its own multiple, so the multiplier is learned per buyer and pulled back toward the
buyer's procurement method where a buyer has little history. What is left over is the gap between
the buyer's estimate and the winning bid, which competition sets and the portal never publishes,
so it is the floor on how narrow this band can be.

Route 2, the history route, for tenders with no published security. A LightGBM model on the
entity, ministry, method, district, category and the title (both as quantity signals and as a
stacked text prediction) predicts the log award value.

Both routes carry conformal bands calibrated on held-out slices, so the stated coverage is honest
by construction. The history route fits one model to the low edge of the band and one to the high
edge, then pads both by a margin measured on rows neither model has seen. Two edges that can move
independently beat one central estimate stretched by a predicted difficulty, which assumes every
tender's error has the same shape: an easy tender gets a narrow band and a hard one a wide band or
a deferral, and a tender with a firm floor and a long tail above it gets that too. The older
difficulty-scaled route is still here, behind BAND_METHOD, because the comparison is in the docs.

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
MIN_METHOD_ROWS = 300      # below this a group borrows the shared quantiles
CONFORMAL_GROUPS = ("method",)   # what the band is calibrated separately for
COVERAGE = 0.80
BUNDLE_FORMAT = 3          # bump when the saved bundle gains or loses a key
BAND_METHOD = "cqr"  # "normalised": one median model, band scaled by predicted difficulty.
                            # "cqr": two quantile models, conformalised. See _cqr_scores.
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


BASE_NUM_COLS = ["month", "year_offset", "title_len", "title_words", "n_numbers", "max_number",
                 "sum_number", "has_unit", "has_year_range", "txt", "pe_history"]
PRIOR_COLS = ["pe_prior", "pe_method_prior"]
USE_ENTITY_PRIORS = True   # what this buyer has paid before, counting only earlier awards


def _num_cols() -> list[str]:
    return BASE_NUM_COLS + (PRIOR_COLS if USE_ENTITY_PRIORS else [])


def _expanding_prior(pdf: pd.DataFrame, keys: list[str], smooth: float = 5.0) -> np.ndarray:
    """The average log award this buyer had signed before this row, for rows sorted by date.

    A buyer's past is the strongest thing a bidder knows about it, and the tree can only reach it
    through the entity id, which it has to learn level by level from whatever rows it happens to
    see. Handing it the running average directly is the same evidence in a usable shape. Only
    earlier awards count, so no row is ever informed by its own outcome or by a later one.
    """
    y = pdf["y"].to_numpy(dtype=float)
    grand = float(np.mean(y)) if len(y) else 0.0
    g = pdf.groupby(keys, observed=True)["y"]
    earlier_sum = g.cumsum().to_numpy() - y
    earlier_n = g.cumcount().to_numpy()
    return (earlier_sum + smooth * grand) / (earlier_n + smooth)


def _prior_tables(pdf: pd.DataFrame) -> dict:
    """The same averages over all of history, for scoring a tender that has not happened yet."""
    grand = float(pdf["y"].mean())
    return {
        "grand": grand,
        "pe": pdf.groupby("pe_id", observed=True)["y"].mean().to_dict(),
        "pe_method": {f"{a}|{b}": v for (a, b), v in
                      pdf.groupby(["pe_id", "method"], observed=True)["y"].mean().to_dict().items()},
    }


def _apply_priors(df: pd.DataFrame, tables: dict) -> pd.DataFrame:
    grand = tables.get("grand", 0.0)
    pe = df["pe_id"].astype(str).map(tables.get("pe", {}))
    key = df["pe_id"].astype(str) + "|" + df["method"].astype(str)
    pm = key.map(tables.get("pe_method", {}))
    df["pe_prior"] = pe.fillna(grand).to_numpy()
    df["pe_method_prior"] = pm.fillna(pe).fillna(grand).to_numpy()
    return df


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


def _matrix(df: pd.DataFrame, levels: dict[str, list[str]], cols: list[str] | None = None) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    for c in CAT_COLS:
        out[c] = pd.Categorical(df[c].where(df[c] != "", None), categories=levels[c])
    for c in (cols or _num_cols()):
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

ENTITY_SHRINK = 10.0       # a buyer needs this many past securities to be trusted over its method


def _fit_security(df: pd.DataFrame) -> dict | None:
    """Multiples of the published security: per method, and per buyer where a buyer has a habit.

    Buyers set the security as a share of their own cost estimate, and each one tends to pick the
    same share every time, so its past awards say more than its procurement method does. A buyer
    with few securities on record is pulled back toward its method, which is what ENTITY_SHRINK
    does: it is the number of past securities at which a buyer's own habit outweighs its method.
    """
    rows = df[_has_security(df)]
    if len(rows) < MIN_SECURITY_ROWS:
        return None
    sec_lakh = pd.to_numeric(rows["security_bdt"], errors="coerce").astype(float) / TAKA_PER_LAKH
    log_ratio = np.log(rows["lakh"].to_numpy() / sec_lakh.to_numpy())
    model = {"global": float(np.median(log_ratio)), "by_method": {}, "by_entity": {}, "n": int(len(rows))}
    for method, idx in rows.groupby("method").groups.items():
        if method and len(idx) >= MIN_GROUP_ROWS:
            model["by_method"][str(method)] = float(np.median(log_ratio[rows.index.get_indexer(idx)]))
    methods = rows["method"].to_numpy()
    for entity, idx in rows.groupby("pe_id").groups.items():
        if not entity:
            continue
        pos = rows.index.get_indexer(idx)
        own = float(np.median(log_ratio[pos]))
        fallback = model["by_method"].get(str(methods[pos[0]]), model["global"])
        model["by_entity"][str(entity)] = (own * len(pos) + fallback * ENTITY_SHRINK) / (len(pos) + ENTITY_SHRINK)
    return model


def _security_residuals(model: dict, rows: pd.DataFrame) -> np.ndarray:
    """How far each award sat from the multiple its security implied."""
    return (np.log(rows["lakh"].to_numpy() * TAKA_PER_LAKH / pd.to_numeric(rows["security_bdt"]).to_numpy())
            - _security_log_multiple(model, rows["method"].to_numpy(), rows["pe_id"].to_numpy()))


def _security_band(model: dict, rows: pd.DataFrame) -> tuple[float, float]:
    """The band's edges, measured on securities the multiplier was never fitted on.

    Measuring them on the fitting rows makes the band look tighter than it is, and the tighter the
    multiplier the worse the flattery: once each buyer got its own multiple, an in-sample band
    covered 75.5 percent of later awards while promising 80.
    """
    if rows.empty:
        return 0.0, 0.0
    ratio = _security_residuals(model, rows)
    n = len(ratio)
    return (float(np.quantile(ratio, max(0.0, LO_Q * (n + 1) / n))),
            float(np.quantile(ratio, min(1.0, HI_Q * (n + 1) / n))))


def _security_log_multiple(model: dict, methods: np.ndarray, entities: np.ndarray | None = None) -> np.ndarray:
    """The buyer's own habit where it has one, otherwise its method, otherwise the overall median."""
    by_method = model.get("by_method", {})
    by_entity = model.get("by_entity", {})
    if entities is None:
        entities = np.array([""] * len(methods))
    return np.array([by_entity.get(str(e)) if by_entity.get(str(e)) is not None
                     else by_method.get(str(m), model["global"])
                     for m, e in zip(methods, entities)])


def _group_keys(df: pd.DataFrame, predicted: np.ndarray | None = None,
                size_edges: list[float] | None = None) -> np.ndarray:
    """The label a row's band is calibrated under: its method, optionally with its size band.

    Size matters because a small purchase and a large one are not equally predictable, and one
    shared quantile serves neither well. Bucket edges are fixed when the model is trained and
    carried in the bundle, so a row falls in the same bucket whatever else it is predicted beside.
    """
    parts = []
    for col in CONFORMAL_GROUPS:
        if col == "size":
            if predicted is None or not size_edges:
                parts.append(np.zeros(len(df), dtype=int).astype(str))
            else:
                parts.append(np.digitize(predicted, size_edges).astype(str))
        else:
            parts.append(df[col].astype(str).to_numpy())
    return np.array(["|".join(vals) for vals in zip(*parts)])


def _fit_quantile_pair(frame: pd.DataFrame, levels: dict, seed: int):
    """A model for the low edge of the band and one for the high edge.

    Scaling one median prediction by a predicted difficulty assumes every tender's error spreads
    the same shape, only wider or narrower. Real awards are not like that: a tender can have a
    firm floor and a long tail above it. Two quantile models can learn an edge each.
    """
    X, y = _matrix(frame, levels), frame["y"]
    make = lambda a: lgb.LGBMRegressor(objective="quantile", alpha=a, random_state=seed, **PARAMS).fit(X, y)
    return make(LO_Q), make(HI_Q)


def _cqr_scores(lo_pred: np.ndarray, hi_pred: np.ndarray, y: np.ndarray) -> np.ndarray:
    """How far outside its own band each row fell; negative when the band had room to spare."""
    return np.maximum(lo_pred - y, y - hi_pred)


def _conformal_pad(scores: np.ndarray) -> float:
    """The margin that must be added to both edges for the stated share of rows to land inside.

    The finite-sample correction matters: with a few hundred rows, taking the plain 80th
    percentile leaves coverage a little short of 80 percent every time.
    """
    n = len(scores)
    if n == 0:
        return 0.0
    level = min(np.ceil((n + 1) * COVERAGE) / n, 1.0)
    return float(np.quantile(scores, level))


def _method_quantiles(keys: np.ndarray, by_group: dict, lo: float, hi: float):
    """Per-group conformal quantiles, falling back to the shared pair."""
    pairs = [by_group.get(str(k), (lo, hi)) for k in keys]
    return np.array([q[0] for q in pairs]), np.array([q[1] for q in pairs])


def _has_security(df: pd.DataFrame) -> np.ndarray:
    if "security_bdt" not in df.columns:
        return np.zeros(len(df), dtype=bool)
    return (pd.to_numeric(df["security_bdt"], errors="coerce").fillna(0) > 0).to_numpy()


# --------------------------------------------------------------------------- loading

def live_security_share(data_root: Path) -> float | None:
    """Share of open tenders whose notice publishes a security, so they take the precise route.

    The historical test window is a poor guide to this: its detail pages have mostly not been
    fetched, so security looks absent there when in truth it was simply never collected.
    """
    path = Path(data_root) / "clean" / "tenders.parquet"
    if not path.exists():
        return None
    t = pl.read_parquet(path)
    if "status" in t.columns:
        t = t.filter(pl.col("status") == "Live")
    if t.is_empty():
        return None
    t = _join_security(t, Path(data_root))
    return float((pl.col("security_bdt").is_not_null().sum() / t.height) if False else
                 t["security_bdt"].is_not_null().mean())


def live_method_mix(data_root: Path) -> dict[str, float]:
    """How open tenders that have no published security split across procurement methods.

    These are the tenders the history route has to price, and they are not the historical mix:
    open tendering dominates them, and open tendering is the hardest method to price. Ignoring
    that made the projected figures flattering.
    """
    path = Path(data_root) / "clean" / "tenders.parquet"
    if not path.exists():
        return {}
    t = pl.read_parquet(path)
    if "status" in t.columns:
        t = t.filter(pl.col("status") == "Live")
    if t.is_empty() or "method" not in t.columns:
        return {}
    t = _join_security(t, Path(data_root)).filter(pl.col("security_bdt").is_null())
    if t.is_empty():
        return {}
    counts = t.group_by("method").len()
    total = int(counts["len"].sum())
    return {str(m): n / total for m, n in counts.iter_rows() if m}


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
    pdf["pe_prior"] = _expanding_prior(pdf, ["pe_id"])
    pdf["pe_method_prior"] = _expanding_prior(pdf, ["pe_id", "method"])
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

def _calibrate_cqr(past: pd.DataFrame, levels: dict, calib: pd.DataFrame,
                   oof_lo: np.ndarray, oof_hi: np.ndarray, a: int, b: int, seed: int) -> dict:
    """Pad the two quantile models' band until it covers, per method, then check it against drift.

    The rows are split exactly as the difficulty route splits them, so the two band methods are
    calibrated on the same evidence and the comparison between them is about the method alone.
    """
    q_rows, check_rows = calib.iloc[a:b], calib.iloc[b:]
    q_y, check_y = q_rows["y"].to_numpy(), check_rows["y"].to_numpy()
    q_score = _cqr_scores(oof_lo[a:b], oof_hi[a:b], q_y)
    pad = _conformal_pad(q_score)

    keys = _group_keys(q_rows)
    by_method = {str(k): _conformal_pad(q_score[keys == k]) for k in set(keys)
                 if k and (keys == k).sum() >= MIN_METHOD_ROWS}

    # Quantiles fitted on one period under-cover the next. Measure the shortfall on a later block
    # these pads have not seen and widen each one just enough. Still only past data.
    drift = 0.0
    if len(check_rows) >= 200:
        check_score = _cqr_scores(oof_lo[b:], oof_hi[b:], check_y)
        check_keys = _group_keys(check_rows)

        def _extra(mask: np.ndarray, base: float) -> float:
            if mask.sum() < MIN_METHOD_ROWS:
                return 0.0
            sc = check_score[mask]
            for step in np.arange(0.0, 2.02, 0.02):
                if (sc <= base + step).mean() >= COVERAGE:
                    return float(step)
            return 2.0

        drift = _extra(np.ones(len(check_rows), dtype=bool), pad)
        by_method = {k: v + _extra(check_keys == k, v) for k, v in by_method.items()}
    pad += drift

    lo_model, hi_model = _fit_quantile_pair(past, levels, seed)
    return {"lo_model": lo_model, "hi_model": hi_model, "pad": pad, "by_method": by_method,
            "drift_pad": round(drift, 3)}


def _evaluate_security_route(pdf: pd.DataFrame) -> dict:
    """Score the security route on its own timeline, fitted on earlier securities only.

    The archive reaches back to 2019 but detail pages have only been fetched for the last year, so
    every published security we hold is recent. Split the whole archive at eighty percent and every
    one of them lands on the test side, leaving the multiplier nothing to learn from and the route
    silently switched off. That is a fact about what has been crawled, not about the method.

    So the route gets its own split, at eighty percent of the securities by date: fitted on the
    earlier ones, scored on the later ones. It is a smaller and more recent window than the history
    route's, which is why it is reported separately and never folded into a single headline.
    """
    rows = pdf[_has_security(pdf)].sort_values("signed_on")
    out = {"security_route_n_total": int(len(rows))}
    if len(rows) < 2 * MIN_SECURITY_ROWS:
        return out
    signed = rows["signed_on"].astype(str)
    fit_cut = str(rows["signed_on"].iloc[int(len(rows) * 0.60)])
    cut = str(rows["signed_on"].iloc[int(len(rows) * 0.80)])
    earlier = rows[signed < fit_cut]
    calib = rows[(signed >= fit_cut) & (signed < cut)]
    later = rows[signed >= cut]
    model = _fit_security(earlier)
    if model is None or len(later) < 30 or len(calib) < 30:
        return out
    lo, hi = _security_band(model, calib)
    sec_lakh = pd.to_numeric(later["security_bdt"], errors="coerce").to_numpy() / TAKA_PER_LAKH
    centre = np.log(sec_lakh) + _security_log_multiple(model, later["method"].to_numpy(), later["pe_id"].to_numpy())
    q50, q10, q90 = np.exp(centre), np.exp(centre + lo), np.exp(centre + hi)
    actual = later["lakh"].to_numpy()
    ok = np.isfinite(q50) & (actual > 0)
    inside = (actual >= q10) & (actual <= q90)
    out.update({
        "security_n": int(ok.sum()),
        "security_fitted_on": int(len(earlier)),
        "security_calibrated_on": int(len(calib)),
        "security_test_from": cut,
        "security_mape": round(float(np.median(np.abs(q50[ok] - actual[ok]) / actual[ok])), 4),
        "security_coverage_80": round(float(inside[ok].mean()), 4),
        "security_band_width_median": round(float(np.median(q90[ok] / np.maximum(q10[ok], 1e-9))), 2),
    })
    # A band ages. The share buyers ask for drifts, and the spread of awards around it has widened
    # month by month, so a band set in June covers June better than September. The model retrains
    # every night, so the band a live tender meets is at most a day or two old. Coverage is
    # therefore reported against how stale the band was, and the freshest bucket is the one the
    # product actually runs at. The whole-window figure above is the stale end of the same table.
    age = (pd.to_datetime(later["signed_on"], errors="coerce")
           - pd.to_datetime(calib["signed_on"], errors="coerce").max()).dt.days.to_numpy()
    decay = {}
    for lo_d, hi_d, label in ((0, 7, "within a week"), (7, 21, "one to three weeks"),
                              (21, 45, "three to six weeks"), (45, 10_000, "over six weeks")):
        m = ok & (age >= lo_d) & (age < hi_d)
        if m.sum() >= 50:
            decay[label] = {"awards": int(m.sum()), "coverage_80": round(float(inside[m].mean()), 4)}
    if decay:
        out["security_coverage_by_band_age"] = decay
        fresh = decay.get("within a week")
        if fresh:
            out["security_coverage_fresh_band"] = fresh["coverage_80"]
            out["security_n_fresh_band"] = fresh["awards"]
    return out


def train(data_root: Path, models_dir: Path, seed: int = 0) -> dict | None:
    pdf = _load_awards(Path(data_root))
    if len(pdf) < MIN_ROWS:
        return None
    n = len(pdf)
    # Split on a date, not on a row number: awards signed on the same day must not straddle the
    # boundary, or a few of the rows being forecast would share a day with rows used to fit.
    cut_date = str(pdf["signed_on"].iloc[int(n * 0.80)])
    is_test = pdf["signed_on"].astype(str) >= cut_date
    past, test = pdf[~is_test].copy(), pdf[is_test].copy()
    if len(test) < 100 or len(past) < MIN_ROWS:
        return None

    vec, ridge = _fit_text(past, [test], seed)
    levels = {c: sorted(v for v in past[c].unique() if v) for c in CAT_COLS}

    # Calibrate on forward-looking out-of-sample residuals rather than one small slice: walk an
    # expanding window through the past, each step predicting the block it has not seen. That is
    # the situation the model is actually in every night, so the residuals carry its real error,
    # drift included, and there are tens of thousands of them rather than a few thousand.
    fractions = (0.4, 0.55, 0.70, 0.85, 1.0) if len(past) >= MIN_FOR_WALK else (0.8, 1.0)
    edges = [int(len(past) * f) for f in fractions]
    oof_index, oof_resid, oof_lo, oof_hi = [], [], [], []
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
        if BAND_METHOD == "cqr":
            lo_m, hi_m = _fit_quantile_pair(prior, levels, seed)
            oof_lo.append(lo_m.predict(_matrix(block, levels)))
            oof_hi.append(hi_m.predict(_matrix(block, levels)))
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
    q_pred = model.predict(_matrix(q_rows, levels))
    size_edges = [float(v) for v in np.quantile(q_pred, [0.2, 0.4, 0.6, 0.8])] if "size" in CONFORMAL_GROUPS else []
    methods = _group_keys(q_rows, q_pred, size_edges)
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
        check_methods = _group_keys(check_rows, model.predict(_matrix(check_rows, levels)), size_edges)

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

    cqr: dict = {}
    if BAND_METHOD == "cqr":
        cqr = _calibrate_cqr(past, levels, calib, np.concatenate(oof_lo), np.concatenate(oof_hi), a, b, seed)

    # For serving, the multiplier learns from every security in the archive, which is what the
    # nightly retrain would do. The figures published for this route come from the separate,
    # earlier-only fit in _evaluate_security_route, never from this one.
    with_sec = (past if _has_security(past).sum() >= MIN_SECURITY_ROWS else pdf)
    with_sec = with_sec[_has_security(with_sec)].sort_values("signed_on")
    sec_model = _fit_security(with_sec)
    sec_lo = sec_hi = 0.0
    if sec_model and len(with_sec) >= 2 * MIN_SECURITY_ROWS:
        signed = with_sec["signed_on"].astype(str)
        fit_cut = str(with_sec["signed_on"].iloc[int(len(with_sec) * 0.80)])
        weaker = _fit_security(with_sec[signed < fit_cut])
        if weaker:
            # The band is measured against a multiplier that saw only the earlier securities, then
            # served with one that saw them all. The served model is the better of the two, so the
            # band errs wide rather than narrow. It is calibrated on the most recent securities
            # because the spread widens over time and tonight's tenders resemble them most.
            sec_lo, sec_hi = _security_band(weaker, with_sec[signed >= fit_cut])
    elif sec_model:
        sec_lo, sec_hi = _security_band(sec_model, with_sec)     # too few to hold any back

    bundle = {
        "model": model, "difficulty": difficulty, "levels": levels, "vectorizer": vec, "ridge": ridge,
        "lo_q": lo_q, "hi_q": hi_q, "floor": floor, "by_method": by_method, "size_edges": size_edges,
        "security": sec_model, "security_lo": sec_lo, "security_hi": sec_hi,
        "band_method": BAND_METHOD, "cqr": cqr,
        "num_cols": _num_cols(), "priors": _prior_tables(past) if USE_ENTITY_PRIORS else {},
        "history": past.groupby("pe_id").size().to_dict(),
        "format": BUNDLE_FORMAT,
        "version": datetime.now(timezone.utc).strftime("award-%Y%m%d"),
        "coverage_target": COVERAGE,
        "drift_allowance": cqr.get("drift_pad", round(drift, 3)),
    }
    metrics = _evaluate(bundle, test, live_security_share(Path(data_root)), live_method_mix(Path(data_root)))
    sec_metrics = _evaluate_security_route(pdf)
    sec_metrics["live_security_share"] = live_security_share(Path(data_root))
    metrics = {k: v for k, v in metrics.items()
               if not (k.startswith("security_") and sec_metrics.get("security_n"))}
    metrics.update(sec_metrics)
    metrics.update({"drift_allowance": cqr.get("drift_pad", round(drift, 3)), "n_fit": len(past), "n_calibration": len(calib), "n_test": len(test),
                    "test_from": str(test["signed_on"].iloc[0]),
                    "train_last_signed": str(past["signed_on"].iloc[-1]),
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


def _evaluate(bundle: dict, test: pd.DataFrame, live_share: float | None = None,
              method_mix: dict[str, float] | None = None) -> dict:
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
    rng_ci = np.random.default_rng(7)

    def ci(values: np.ndarray, stat, draws: int = 400) -> list[float]:
        """Bootstrap a 95 percent interval, so a figure from few rows cannot pass as a firm one."""
        if len(values) < 30:
            return []
        picks = rng_ci.integers(0, len(values), size=(draws, len(values)))
        spread = np.array([stat(values[p]) for p in picks])
        return [round(float(np.percentile(spread, 2.5)), 4), round(float(np.percentile(spread, 97.5)), 4)]

    for name in ("security", "history"):
        m = acted & (basis == name)
        out[f"{name}_n"] = int(m.sum())
        out[f"{name}_n_including_declined"] = int((basis == name).sum())
        if m.any():
            out[f"{name}_mape"] = ape(q50, m)
            out[f"{name}_coverage_80"] = round(float(inside[m].mean()), 4)
            out[f"{name}_band_width_median"] = round(float(np.median(ratio[m])), 2)
            errs = (np.abs(q50[m] - actual[m]) / actual[m])
            out[f"{name}_mape_ci95"] = ci(errs, lambda v: float(np.median(v)))
            out[f"{name}_coverage_ci95"] = ci(inside[m].astype(float), lambda v: float(v.mean()))

    # The history route is not one thing. Open tendering is far harder to price than a quotation,
    # and open tendering is nearly all of what the route is actually asked to price on the live
    # site, so a single history figure hides the number that matters.
    if "method" in test.columns:
        methods = test["method"].astype(str).to_numpy()
        by_method = {}
        for name in pd.unique(methods):
            seen = (basis == "history") & (methods == name)
            m = acted & seen
            if seen.sum() < 200 or m.sum() < 100:
                continue
            by_method[str(name)] = {
                "n_acted": int(m.sum()),
                "mape": ape(q50, m),
                "coverage_80": round(float(inside[m].mean()), 4),
                "band_width_median": round(float(np.median(ratio[m])), 2),
                "deferral_rate": round(float((deferred & seen).sum() / seen.sum()), 4),
            }
        out["history_by_method"] = dict(sorted(by_method.items(), key=lambda kv: -kv[1]["n_acted"]))

    # What a user actually meets. The test window's security coverage reflects how much of it has
    # been crawled, not how many notices publish a security, so resample the test rows to the mix
    # of routes seen on open tenders today and measure that.
    sec_rows = np.where(acted & (basis == "security"))[0]
    hist_rows = np.where(acted & (basis == "history"))[0]
    if live_share is not None and len(sec_rows) >= 30 and len(hist_rows) >= 30:
        rng = np.random.default_rng(0)
        n_draw = min(len(hist_rows) * 2, 20_000)
        # Draw the history rows to match the methods that open tenders without a security actually
        # use, not the methods the archive happens to hold.
        if method_mix:
            methods = test["method"].astype(str).to_numpy()
            pools = {m: hist_rows[methods[hist_rows] == m] for m in method_mix}
            usable = {m: w for m, w in method_mix.items() if len(pools.get(m, [])) >= 30}
            if usable:
                total = sum(usable.values())
                names = list(usable)
                drawn = rng.choice(len(names), n_draw, p=[usable[m] / total for m in names])
                hist_draw = np.array([rng.choice(pools[names[i]]) for i in drawn])
                out["projection_method_mix"] = {m: round(w / total, 4) for m, w in usable.items()}
            else:
                hist_draw = rng.choice(hist_rows, n_draw)
        else:
            hist_draw = rng.choice(hist_rows, n_draw)
        pick = np.where(rng.random(n_draw) < live_share, rng.choice(sec_rows, n_draw), hist_draw)
        out["live_security_share"] = round(float(live_share), 4)
        out["expected_mape_on_open_tenders"] = round(float(np.median(np.abs(q50[pick] - actual[pick]) / actual[pick])), 4)
        out["expected_coverage_on_open_tenders"] = round(float(inside[pick].mean()), 4)
        out["expected_band_width_on_open_tenders"] = round(float(np.median(ratio[pick])), 2)
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
    if bundle.get("priors") and "pe_prior" not in df.columns:
        df = _apply_priors(df, bundle["priors"])
    X = _matrix(df, bundle["levels"], bundle.get("num_cols"))
    p = bundle["model"].predict(X)
    cqr = bundle.get("cqr") or {}
    if bundle.get("band_method") == "cqr" and cqr:
        keys = _group_keys(df)
        pad = np.array([cqr["by_method"].get(str(k), cqr["pad"]) for k in keys])
        low = cqr["lo_model"].predict(X) - pad
        high = cqr["hi_model"].predict(X) + pad
    else:
        s_scale = np.maximum(bundle["difficulty"].predict(X), bundle["floor"])
        lo, hi = _method_quantiles(_group_keys(df, p, bundle.get("size_edges")), bundle.get("by_method", {}),
                                   bundle["lo_q"], bundle["hi_q"])
        low, high = p + lo * s_scale, p + hi * s_scale
    q10 = np.expm1(low)
    q50 = np.expm1(p)
    q90 = np.expm1(high)
    basis = np.array(["history"] * len(df), dtype=object)

    sec_model = bundle.get("security")
    if sec_model:
        has = _has_security(df)
        if has.any():
            sec_lakh = pd.to_numeric(df.loc[has, "security_bdt"], errors="coerce").to_numpy() / TAKA_PER_LAKH
            centre = np.log(sec_lakh) + _security_log_multiple(sec_model, df.loc[has, "method"].to_numpy(), df.loc[has, "pe_id"].to_numpy())
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
