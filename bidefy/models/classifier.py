"""Category classifier: title and buyer to one of fifteen Bidefy categories, with a deferral rule.

Labels come only from the portal's own category tags, harvested from detail pages. An earlier
version also trained on labels produced by a title-keyword rule. That was measured to be actively
harmful: adding twenty thousand such rows drove accuracy on portal-tag ground truth from 0.898 to
0.554, because the rule is a biased labeller and it drowns out the real tags. It also flattered
the reported accuracy, because the model was partly scored on the rule it had been taught to copy.

Scoring is cross-validated over every tag-labelled row, so a small gold set still gives a stable
estimate, and the reported accuracy is only ever measured against the portal's tags.

This model is the fallback. Where a tender's detail page has been fetched, its category is read
from the portal directly rather than predicted; see bidefy.normalize.build.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import polars as pl
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import FeatureUnion, Pipeline

from collections import defaultdict

from ..crawler import store
from .categories import label_from_tags

TARGET_ACCURACY = 0.93     # the bar is set to deliver this, rather than picked by hand
FALLBACK_THRESHOLD = 0.60
MIN_LABELS = 60
MIN_PER_CLASS = 5
FOLDS = 5
BUNDLE_FORMAT = 4
BRIEF_DROPOUT = 0.3        # so the model still works for tenders whose detail page is unfetched
ENTITY_PRIOR_WEIGHT = 1.0   # a buyer's own history, combined with the text model as evidence


def compose(titles, entities=None, ministries=None, briefs=None) -> list[str]:
    """One text per tender: what is being bought, who is buying, and the notice's own description.

    The buyer is evidence in itself, since a hospital does not buy bridges. The brief description
    comes from the detail page and is fuller than the title; it is blank for tenders whose detail
    page has not been fetched, which the model is trained to tolerate.
    """
    titles = list(titles)
    n = len(titles)
    entities = list(entities) if entities is not None else [""] * n
    ministries = list(ministries) if ministries is not None else [""] * n
    briefs = list(briefs) if briefs is not None else [""] * n
    return [f"{t or ''} || {e or ''} || {m or ''} || {b or ''}"
            for t, e, m, b in zip(titles, entities, ministries, briefs)]


def _labelled(data_root: Path) -> pl.DataFrame:
    """Every tender whose detail page carries category tags we can map. This is the gold set."""
    details = store.load_all(Path(data_root), "details")
    if details.is_empty() or "categories" not in details.columns:
        return pl.DataFrame()
    briefs: dict[str, str] = {}
    if "brief" in details.columns:
        briefs = {str(t): (b or "") for t, b in details.select("tender_id", "brief").iter_rows()}
    labels: dict[str, str] = {}
    for tid, raw in details.select("tender_id", "categories").iter_rows():
        try:
            tags = json.loads(raw or "[]")
        except json.JSONDecodeError:
            continue
        label = label_from_tags(tags)
        if label:
            labels[str(tid)] = label
    if not labels:
        return pl.DataFrame()
    wanted = ["tender_id", "title", "procuring_entity", "ministry"]
    frames = []
    for name in ("tenders", "contracts"):
        path = Path(data_root) / "clean" / f"{name}.parquet"
        if not path.exists():
            continue
        df = pl.read_parquet(path)
        missing = [pl.lit("").alias(c) for c in wanted if c not in df.columns]
        frames.append(df.with_columns(missing).select(wanted))
    if not frames:
        return pl.DataFrame()
    rows = (pl.concat(frames, how="diagonal_relaxed")
            .with_columns(pl.col("tender_id").cast(pl.Utf8))
            .unique(subset=["tender_id"], keep="first")
            .filter(pl.col("tender_id").is_in(list(labels)))
            .filter(pl.col("title").fill_null("").str.strip_chars() != ""))
    if rows.is_empty():
        return pl.DataFrame()
    return (rows.with_columns(pl.col("tender_id").replace_strict(labels, default=None).alias("label"),
                              pl.col("tender_id").replace_strict(briefs, default="").alias("brief"))
            .drop_nulls("label"))


def _pipeline(seed: int) -> Pipeline:
    return Pipeline([
        ("features", FeatureUnion([
            ("word", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=2, max_features=80_000, sublinear_tf=True, dtype=np.float32)),
            ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2, max_features=200_000, sublinear_tf=True, dtype=np.float32)),
        ])),
        # No class weighting: balancing lifted macro F1 on rare categories but pushed the whole
        # accuracy-versus-deferral frontier the wrong way, costing 25 points of deferral at a
        # 97 percent accuracy target.
        ("clf", LogisticRegression(C=4.0, max_iter=3000, random_state=seed)),
    ])


def _entity_counts(entities: list[str], labels: np.ndarray, classes: list[str], rows) -> dict[str, np.ndarray]:
    """How often each buyer has bought each category, from the given rows only."""
    pos = {c: i for i, c in enumerate(classes)}
    tally: dict[str, np.ndarray] = defaultdict(lambda: np.zeros(len(classes)))
    for i in rows:
        if entities[i]:
            tally[entities[i]][pos[labels[i]]] += 1
    return dict(tally)


def _blend_with_entity(proba: np.ndarray, entities: list[str], counts: dict[str, np.ndarray],
                       weight: float = ENTITY_PRIOR_WEIGHT) -> np.ndarray:
    """Multiply the text model's probabilities by what this buyer usually buys, then renormalise.

    A Roads Division buys roads, and a short tender title often does not say so. Buyers with no
    history are left untouched. The ministry was tried the same way and made things worse: it is
    too broad to say anything a buyer's own record does not say better.
    """
    if not counts or weight <= 0:
        return proba
    out = proba.copy()
    n_classes = proba.shape[1]
    for row, entity in enumerate(entities):
        tally = counts.get(entity)
        if tally is None:
            continue
        prior = (tally + 1.0) / (tally.sum() + n_classes)
        blended = proba[row] * prior ** weight
        total = blended.sum()
        if total > 0:
            out[row] = blended / total
    return out


def _deferral_for_accuracy(conf: np.ndarray, correct: np.ndarray, targets=(0.93, 0.95, 0.97)) -> dict:
    """Smallest deferral that reaches each accuracy, declining the least confident predictions first."""
    order = np.argsort(-conf)
    ordered = correct[order].astype(float)
    running = np.cumsum(ordered) / np.arange(1, len(ordered) + 1)
    out = {}
    for t in targets:
        ok = np.where(running >= t)[0]
        out[f"deferral_for_{int(t * 100)}"] = round(1 - (int(ok.max()) + 1) / len(ordered), 4) if len(ok) else None
    return out


def _threshold_for_accuracy(conf: np.ndarray, correct: np.ndarray, target: float) -> float:
    """The lowest confidence bar that still delivers the target accuracy, so deferral is as small
    as it can be for the accuracy we promise. Returns a fallback when the target is unreachable."""
    order = np.argsort(-conf)
    ordered_conf, ordered_correct = conf[order], correct[order].astype(float)
    running = np.cumsum(ordered_correct) / np.arange(1, len(ordered_correct) + 1)
    ok = np.where(running >= target)[0]
    return float(ordered_conf[int(ok.max())]) if len(ok) else FALLBACK_THRESHOLD


def train(data_root: Path, models_dir: Path, target_accuracy: float = TARGET_ACCURACY, seed: int = 0) -> dict | None:
    df = _labelled(Path(data_root))
    if df.is_empty() or df.height < MIN_LABELS:
        return None
    counts = df.group_by("label").len()
    keep = set(counts.filter(pl.col("len") >= MIN_PER_CLASS)["label"].to_list())
    dropped = sorted(set(counts["label"].to_list()) - keep)
    df = df.filter(pl.col("label").is_in(list(keep)))
    if df.height < MIN_LABELS or len(keep) < 2:
        return None

    rng = np.random.default_rng(seed)
    briefs = df["brief"].fill_null("").to_list() if "brief" in df.columns else [""] * df.height
    # Train on text whose brief is sometimes blanked, so the model tolerates a missing detail page.
    # Score on text with the brief present, because that is how nearly every open tender arrives.
    X_train = compose(df["title"], df["procuring_entity"], df["ministry"],
                      ["" if rng.random() < BRIEF_DROPOUT else b for b in briefs])
    X = compose(df["title"], df["procuring_entity"], df["ministry"], briefs)
    entities = df["procuring_entity"].fill_null("").to_list()
    y = np.array(df["label"].to_list())
    folds = min(FOLDS, int(counts.filter(pl.col("label").is_in(list(keep)))["len"].min()))
    conf_parts, correct_parts, pred_parts, true_parts = [], [], [], []
    for tr, te in StratifiedKFold(n_splits=max(folds, 2), shuffle=True, random_state=seed).split(X, y):
        fold = _pipeline(seed).fit([X_train[i] for i in tr], y[tr])
        classes = list(fold.classes_)
        proba = fold.predict_proba([X[i] for i in te])
        # Priors from the training fold only, so no row is ever helped by its own label.
        proba = _blend_with_entity(proba, [entities[i] for i in te], _entity_counts(entities, y, classes, tr))
        conf_parts.append(proba.max(axis=1))
        pred = np.array([classes[i] for i in proba.argmax(axis=1)])
        pred_parts.append(pred); correct_parts.append(pred == y[te]); true_parts.append(y[te])
    conf = np.concatenate(conf_parts)
    correct = np.concatenate(correct_parts)
    pred = np.concatenate(pred_parts)
    true = np.concatenate(true_parts)
    threshold = _threshold_for_accuracy(conf, correct, target_accuracy)
    acted = conf >= threshold

    metrics = {
        "accuracy_acted": round(float(correct[acted].mean()), 4) if acted.any() else 0.0,
        "deferral_rate": round(float(1 - acted.mean()), 4),
        "coverage": round(float(acted.mean()), 4),
        "accuracy_all": round(float(correct.mean()), 4),
        "macro_f1": round(float(f1_score(true, pred, average="macro")), 4),
        "n_labels": int(df.height),
        "n_classes": len(keep),
        "classes_dropped_for_sparsity": dropped,
        "threshold": round(threshold, 4),
        "target_accuracy": target_accuracy,
        "evaluation": "cross-validated on portal category tags only, entity priors from the training fold",
        "brief_dropout": BRIEF_DROPOUT,
        "scored_with_brief": True,
        "trained_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        **_deferral_for_accuracy(conf, correct),
    }

    final = _pipeline(seed).fit(X_train, y)
    final_classes = list(final.classes_)
    models_dir = Path(models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": final, "threshold": threshold, "classes": final_classes, "format": BUNDLE_FORMAT,
                 "entity_counts": _entity_counts(entities, y, final_classes, range(len(y))),
                 "entity_prior_weight": ENTITY_PRIOR_WEIGHT},
                models_dir / "category.joblib", compress=3)
    mpath = models_dir / "metrics.json"
    existing = json.loads(mpath.read_text(encoding="utf-8")) if mpath.exists() else {}
    existing["category_classifier"] = metrics
    mpath.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    return metrics


def load(models_dir: Path) -> dict | None:
    path = Path(models_dir) / "category.joblib"
    if not path.exists():
        return None
    bundle = joblib.load(path)
    return bundle if bundle.get("format") == BUNDLE_FORMAT else None


def apply(texts: list[str], bundle: dict, entities: list[str] | None = None) -> list[tuple[str, float]]:
    """(category, confidence) per text; category is '' when confidence is below the threshold."""
    if not texts:
        return []
    proba = bundle["model"].predict_proba([t or "" for t in texts])
    classes = bundle["classes"]
    if entities is not None:
        proba = _blend_with_entity(proba, [e or "" for e in entities], bundle.get("entity_counts", {}),
                                   bundle.get("entity_prior_weight", ENTITY_PRIOR_WEIGHT))
    out = []
    for row in proba:
        i = int(row.argmax())
        p = float(row[i])
        out.append((classes[i] if p >= bundle["threshold"] else "", round(p, 4)))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Train or check the category classifier")
    ap.add_argument("command", choices=["train", "check"])
    ap.add_argument("--data-root", default="data")
    ap.add_argument("--models-dir", default="models")
    ap.add_argument("--target-accuracy", type=float, default=TARGET_ACCURACY)
    a = ap.parse_args(argv)
    if a.command == "train":
        m = train(Path(a.data_root), Path(a.models_dir), target_accuracy=a.target_accuracy)
        if m is None:
            print("classifier: not enough portal-tagged labels yet, nothing trained")
            return 0
        print(f"classifier: acted accuracy {m['accuracy_acted']:.3f} at deferral {m['deferral_rate']:.3f} "
              f"(bar {m['threshold']} set for a {m['target_accuracy']:.0%} target), "
              f"macro F1 {m['macro_f1']:.3f}, {m['n_labels']} labels across {m['n_classes']} classes "
              f"(95 percent accuracy needs deferral {m['deferral_for_95']})")
        return 0
    bundle = load(Path(a.models_dir))
    if not bundle:
        print("no model")
        return 1
    samples = ["Purchase of Dot Matrix Printer Ribbon", "Construction of RCC bridge", "Supply of medicine for hospital"]
    for title, (cat, p) in zip(samples, apply(compose(samples), bundle)):
        print(f"{cat or '(declined)':28s} {p:.2f}  {title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
