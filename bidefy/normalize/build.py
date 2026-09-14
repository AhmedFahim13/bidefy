"""Build data/clean/*.parquet from the raw store and maintain the review CSV."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import polars as pl

from ..crawler import store
from ..models import award, classifier
from ..models.categories import label_from_tags
from ..models import flags as flagmod
from . import resolve as r
from .names import normalize_name

EMPTY = {"tenders": 0, "contracts": 0, "bidders": 0, "procuring_entities": 0, "review_pairs": 0}
MAX_VALUE_CRORE = 500.0    # above this the value cell was keyed in taka, not crore; divide by ten million
TAKA_PER_CRORE = 10_000_000.0


def _pe_id(name: str) -> str:
    n = normalize_name(name)
    return r.entity_id("pe:" + n) if n else ""


def _write(df: pl.DataFrame, root: Path, name: str) -> None:
    out = root / "clean"
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / f"{name}.parquet.tmp"
    df.write_parquet(tmp, compression="zstd")
    tmp.replace(out / f"{name}.parquet")


RECENT_PER_BIDDER = 50
RECENT_PER_PE = 10
TOP_BIDDERS_PER_PE = 10


def _json_rows(df: pl.DataFrame, cols: list[str]) -> str:
    return json.dumps(df.select(cols).to_dicts(), ensure_ascii=False, default=str)


def _recent_awards_by_bidder(awarded: pl.DataFrame) -> pl.DataFrame:
    """bidder_id -> JSON list of the latest awards, newest first."""
    cols = ["tender_id", "title", "procuring_entity", "pe_id", "district", "value_crore", "signed_on"]
    out = []
    for (bid,), grp in awarded.sort("signed_on", descending=True, nulls_last=True).group_by("bidder_id"):
        out.append({"bidder_id": bid, "recent_awards": _json_rows(grp.head(RECENT_PER_BIDDER), cols)})
    return pl.DataFrame(out, schema={"bidder_id": pl.Utf8, "recent_awards": pl.Utf8})


def _pe_aggregates(contracts: pl.DataFrame) -> pl.DataFrame:
    """pe_id -> JSON of the latest awards and of the top bidders by award count."""
    cols = ["tender_id", "title", "awardee", "bidder_id", "value_crore", "signed_on"]
    rows = []
    for (pe,), grp in contracts.filter(pl.col("pe_id") != "").sort("signed_on", descending=True, nulls_last=True).group_by("pe_id"):
        top = (
            grp.filter(pl.col("bidder_id") != "")
            .group_by("bidder_id")
            .agg(pl.col("awardee").mode().first().alias("awardee"), pl.len().alias("n_awards"),
                 pl.col("value_crore").fill_null(0.0).sum().alias("total_value_crore"))
            .sort(["n_awards", "total_value_crore"], descending=[True, True])
            .head(TOP_BIDDERS_PER_PE)
        )
        rows.append({"pe_id": pe, "recent_awards": _json_rows(grp.head(RECENT_PER_PE), cols),
                     "top_bidders": _json_rows(top, ["bidder_id", "awardee", "n_awards", "total_value_crore"])})
    return pl.DataFrame(rows, schema={"pe_id": pl.Utf8, "recent_awards": pl.Utf8, "top_bidders": pl.Utf8})


def _pe_counts(df: pl.DataFrame, count_col: str, zero_col: str) -> pl.DataFrame:
    return (
        df.group_by("pe_id", "procuring_entity", "ministry")
        .agg(pl.len().alias(count_col))
        .with_columns(pl.lit(0).alias(zero_col))
    )


def _briefs(data_root: Path) -> dict[str, str]:
    """The notice's own description, where the detail page has been fetched."""
    details = store.load_all(Path(data_root), "details")
    if details.is_empty() or "brief" not in details.columns:
        return {}
    return {str(t): (b or "") for t, b in details.select("tender_id", "brief").iter_rows()}


def _tag_categories(data_root: Path) -> dict[str, str]:
    """The portal's own category tags, mapped to Bidefy categories. Authoritative where present."""
    details = store.load_all(Path(data_root), "details")
    if details.is_empty() or "categories" not in details.columns:
        return {}
    out: dict[str, str] = {}
    for tid, raw in details.select("tender_id", "categories").iter_rows():
        try:
            tags = json.loads(raw or "[]")
        except json.JSONDecodeError:
            continue
        label = label_from_tags(tags)
        if label:
            out[str(tid)] = label
    return out


def _categorise(tenders: pl.DataFrame, models_dir: Path, data_root: Path) -> pl.DataFrame:
    """Category per tender: the portal's own tags where we have the detail page, else the model.

    Reading the answer beats predicting it. The classifier exists to cover tenders whose detail
    page has not been fetched, and it still declines when it is not confident.
    """
    if "title" not in tenders.columns:
        return tenders
    tags = _tag_categories(data_root)
    bundle = classifier.load(models_dir)
    titles = tenders["title"].fill_null("").to_list()
    ids = tenders["tender_id"].cast(pl.Utf8).to_list()
    entities = tenders["procuring_entity"].fill_null("").to_list() if "procuring_entity" in tenders.columns else None
    ministries = tenders["ministry"].fill_null("").to_list() if "ministry" in tenders.columns else None
    brief_of = _briefs(data_root)
    texts = classifier.compose(titles, entities, ministries, [brief_of.get(i, "") for i in ids])
    predicted = classifier.apply(texts, bundle, entities) if bundle else [("", 0.0)] * len(titles)
    categories, confidences, sources = [], [], []
    for tid, (cat, conf) in zip(ids, predicted):
        tagged = tags.get(tid)
        if tagged:
            categories.append(tagged); confidences.append(1.0); sources.append("portal")
        else:
            categories.append(cat); confidences.append(conf); sources.append("model" if cat else "")
    return tenders.with_columns(
        pl.Series("category", categories, dtype=pl.Utf8),
        pl.Series("category_confidence", confidences, dtype=pl.Float64),
        pl.Series("category_source", sources, dtype=pl.Utf8),
    )


def build(data_root: Path, review_path: Path, models_dir: Path = Path("models")) -> dict:
    data_root = Path(data_root)
    tenders = store.load_all(data_root, "tenders")
    contracts = store.load_all(data_root, "contracts")
    if tenders.is_empty() and contracts.is_empty():
        return dict(EMPTY)

    # bidders
    counts: dict[str, int] = {}
    if not contracts.is_empty():
        for name, n in contracts.group_by("awardee").len().iter_rows():
            counts[name or ""] = int(n)
    decisions = r.read_review(review_path)
    res = r.resolve(counts, decisions=decisions)
    n_pairs = r.write_review(review_path, res.review_pairs, decisions)

    n_bidders = 0
    if not contracts.is_empty():
        contracts = contracts.with_columns(
            pl.when(pl.col("value_crore") > MAX_VALUE_CRORE)
            .then(pl.col("value_crore") / TAKA_PER_CRORE)
            .otherwise(pl.col("value_crore"))
            .alias("value_crore")
        )
        contracts = contracts.with_columns(
            pl.col("awardee").fill_null("").map_elements(lambda a: res.entity_of.get(a, ""), return_dtype=pl.Utf8).alias("bidder_id"),
            pl.col("procuring_entity").fill_null("").map_elements(_pe_id, return_dtype=pl.Utf8).alias("pe_id"),
        )
        contracts = _categorise(contracts, Path(models_dir), data_root)
        _write(contracts, data_root, "contracts")
        awarded = contracts.filter(pl.col("bidder_id") != "")
        stats = awarded.group_by("bidder_id").agg(
            pl.len().alias("n_awards"),
            pl.col("value_crore").fill_null(0.0).sum().alias("total_value_crore"),
            pl.col("signed_on").min().alias("first_award"),
            pl.col("signed_on").max().alias("last_award"),
        )
        meta = pl.DataFrame(
            [
                {"bidder_id": e["entity_id"], "canonical_name": e["canonical_name"],
                 "variants": json.dumps(e["variants"], ensure_ascii=False)}
                for e in res.entities
            ],
            schema={"bidder_id": pl.Utf8, "canonical_name": pl.Utf8, "variants": pl.Utf8},
        )
        bidders = (
            meta.join(stats, on="bidder_id", how="left")
            .with_columns(pl.col("n_awards").fill_null(0), pl.col("total_value_crore").fill_null(0.0))
            .join(_recent_awards_by_bidder(awarded), on="bidder_id", how="left")
            .with_columns(pl.col("recent_awards").fill_null("[]"))
            .sort("n_awards", descending=True)
        )
        _write(bidders, data_root, "bidders")
        n_bidders = bidders.height

    # tenders and procuring entities
    if not tenders.is_empty():
        tenders = tenders.with_columns(
            pl.col("procuring_entity").fill_null("").map_elements(_pe_id, return_dtype=pl.Utf8).alias("pe_id")
        )
        tenders = _categorise(tenders, Path(models_dir), data_root)
        _write(tenders, data_root, "tenders")
    frames = []
    if not tenders.is_empty():
        frames.append(_pe_counts(tenders, "n_tenders", "n_contracts"))
    if not contracts.is_empty():
        frames.append(_pe_counts(contracts, "n_contracts", "n_tenders"))
    pes = (
        pl.concat(frames, how="diagonal_relaxed")
        .filter(pl.col("pe_id") != "")
        .group_by("pe_id")
        .agg(
            pl.col("procuring_entity").first().alias("name"),
            pl.col("ministry").first().alias("ministry"),
            pl.col("n_contracts").sum(),
            pl.col("n_tenders").sum(),
        )
        .sort("n_contracts", descending=True)
    )
    if not contracts.is_empty():
        pes = pes.join(_pe_aggregates(contracts), on="pe_id", how="left")
    else:
        pes = pes.with_columns(pl.lit(None, dtype=pl.Utf8).alias("recent_awards"), pl.lit(None, dtype=pl.Utf8).alias("top_bidders"))
    pes = pes.with_columns(pl.col("recent_awards").fill_null("[]"), pl.col("top_bidders").fill_null("[]"))
    # concentration and residual flags over the last twelve months of awards
    since = flagmod.since_default()
    bands = None
    if not contracts.is_empty():
        bundle = award.load(Path(models_dir))
        recent = contracts.filter((pl.col("bidder_id") != "") & (pl.col("signed_on").fill_null("") >= since))
        if bundle is not None and not recent.is_empty():
            bands = award.predict(recent, bundle, date_col="signed_on").select("tender_id", "q10_lakh", "q90_lakh")
        pes = pes.join(flagmod.entity_flags(contracts, since), on="pe_id", how="left")
        bidders_path = data_root / "clean" / "bidders.parquet"
        if bidders_path.exists():
            b = pl.read_parquet(bidders_path)
            if "flags" in b.columns:
                b = b.drop("flags")
            b = b.join(flagmod.bidder_flags(contracts, bands, since), on="bidder_id", how="left").with_columns(pl.col("flags").fill_null("{}"))
            _write(b, data_root, "bidders")
    if "flags" not in pes.columns:
        pes = pes.with_columns(pl.lit("{}").alias("flags"))
    pes = pes.with_columns(pl.col("flags").fill_null("{}"))
    _write(pes, data_root, "procuring_entities")
    return {
        "tenders": tenders.height, "contracts": contracts.height, "bidders": n_bidders,
        "procuring_entities": pes.height, "review_pairs": n_pairs,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build clean tables and the review queue")
    ap.add_argument("--data-root", default="data")
    ap.add_argument("--review", default="review/pairs.csv")
    a = ap.parse_args(argv)
    out = build(Path(a.data_root), Path(a.review))
    print("clean build: " + ", ".join(f"{k}={v}" for k, v in out.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
