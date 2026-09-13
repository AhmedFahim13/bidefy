"""Title to category classifier with a deferral threshold and honest metrics.

Labels come from the portal's own category tags on sampled detail pages (weak labels through
categories.label_from_tags), with a title-keyword fallback. Metrics are reported on the
predictions that clear the threshold, with the deferral rate printed beside them.
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
from sklearn.model_selection import train_test_split
from sklearn.pipeline import FeatureUnion, Pipeline

from ..crawler import store
from .categories import label_from_tags, label_from_title

DEFAULT_THRESHOLD = 0.55
MIN_LABELS = 60
MIN_PER_CLASS = 3


def _labelled(data_root: Path) -> tuple[pl.DataFrame, int, int]:
    """Titles with weak labels. Returns (frame with title and label, n_from_tags, n_from_title)."""
    tenders_path = Path(data_root) / "clean" / "tenders.parquet"
    if not tenders_path.exists():
        return pl.DataFrame(), 0, 0
    tenders = pl.read_parquet(tenders_path).select("tender_id", "title")
    details = store.load_all(Path(data_root), "details")
    rows, from_tags, from_title = [], 0, 0
    tag_map: dict[str, list[str]] = {}
    if not details.is_empty():
        for tid, tags in details.select("tender_id", "categories").iter_rows():
            try:
                tag_map[str(tid)] = json.loads(tags or "[]")
            except json.JSONDecodeError:
                tag_map[str(tid)] = []
    for tid, title in tenders.iter_rows():
        title = title or ""
        if not title.strip():
            continue
        label = label_from_tags(tag_map.get(str(tid), [])) if str(tid) in tag_map else None
        if label:
            from_tags += 1
        else:
            label = label_from_title(title)
            if label:
                from_title += 1
        if label:
            rows.append({"title": title, "label": label})
    return pl.DataFrame(rows), from_tags, from_title


def _pipeline(seed: int) -> Pipeline:
    return Pipeline([
        ("features", FeatureUnion([
            ("word", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=2, max_features=40_000, sublinear_tf=True, dtype=np.float32)),
            ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2, max_features=120_000, sublinear_tf=True, dtype=np.float32)),
        ])),
        ("clf", LogisticRegression(C=4.0, max_iter=2000, class_weight="balanced", random_state=seed)),
    ])


def train(data_root: Path, models_dir: Path, threshold: float = DEFAULT_THRESHOLD, seed: int = 0) -> dict | None:
    df, from_tags, from_title = _labelled(data_root)
    if df.is_empty() or df.height < MIN_LABELS:
        return None
    counts = df.group_by("label").len()
    keep = set(counts.filter(pl.col("len") >= MIN_PER_CLASS)["label"].to_list())
    df = df.filter(pl.col("label").is_in(list(keep)))
    if df.height < MIN_LABELS or len(keep) < 2:
        return None
    X, y = df["title"].to_list(), df["label"].to_list()
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=seed, stratify=y)
    model = _pipeline(seed).fit(X_tr, y_tr)
    proba = model.predict_proba(X_te)
    classes = list(model.classes_)
    conf = proba.max(axis=1)
    pred = np.array([classes[i] for i in proba.argmax(axis=1)])
    acted = conf >= threshold
    y_te_arr = np.array(y_te)
    acc_acted = float((pred[acted] == y_te_arr[acted]).mean()) if acted.any() else 0.0
    metrics = {
        "accuracy_acted": round(acc_acted, 4),
        "deferral_rate": round(float(1 - acted.mean()), 4),
        "coverage": round(float(acted.mean()), 4),
        "macro_f1": round(float(f1_score(y_te_arr, pred, average="macro")), 4),
        "accuracy_all": round(float((pred == y_te_arr).mean()), 4),
        "n_train": len(X_tr),
        "n_test": len(X_te),
        "n_classes": len(classes),
        "threshold": threshold,
        "labels_from_tags": from_tags,
        "labels_from_title": from_title,
        "trained_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    models_dir = Path(models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)
    final = _pipeline(seed).fit(X, y)          # refit on everything for deployment
    joblib.dump({"model": final, "threshold": threshold, "classes": list(final.classes_)}, models_dir / "category.joblib", compress=3)
    metrics_path = models_dir / "metrics.json"
    existing = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else {}
    existing["category_classifier"] = metrics
    metrics_path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    return metrics


def load(models_dir: Path) -> dict | None:
    path = Path(models_dir) / "category.joblib"
    return joblib.load(path) if path.exists() else None


def apply(titles: list[str], bundle: dict) -> list[tuple[str, float]]:
    """(category, confidence) per title; category is '' when confidence is below the threshold."""
    if not titles:
        return []
    proba = bundle["model"].predict_proba([t or "" for t in titles])
    classes = bundle["classes"]
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
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    a = ap.parse_args(argv)
    if a.command == "train":
        m = train(Path(a.data_root), Path(a.models_dir), threshold=a.threshold)
        if m is None:
            print("classifier: not enough labels yet, nothing trained")
            return 0
        print(f"classifier: acted accuracy {m['accuracy_acted']:.3f} at deferral {m['deferral_rate']:.3f}, "
              f"macro F1 {m['macro_f1']:.3f}, train {m['n_train']}, test {m['n_test']}, classes {m['n_classes']}")
        return 0
    bundle = load(Path(a.models_dir))
    if not bundle:
        print("no model")
        return 1
    for title, (cat, p) in zip(
        ["Purchase of Dot Matrix Printer Ribbon", "Construction of RCC bridge", "Supply of medicine for hospital"],
        apply(["Purchase of Dot Matrix Printer Ribbon", "Construction of RCC bridge", "Supply of medicine for hospital"], bundle),
    ):
        print(f"{cat or '(deferred)':28s} {p:.2f}  {title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
