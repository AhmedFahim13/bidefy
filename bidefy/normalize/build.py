"""Build data/clean/*.parquet from the raw store and maintain the review CSV."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import polars as pl

from ..crawler import store
from . import resolve as r
from .names import normalize_name

EMPTY = {"tenders": 0, "contracts": 0, "bidders": 0, "procuring_entities": 0, "review_pairs": 0}


def _pe_id(name: str) -> str:
    n = normalize_name(name)
    return r.entity_id("pe:" + n) if n else ""


def _write(df: pl.DataFrame, root: Path, name: str) -> None:
    out = root / "clean"
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / f"{name}.parquet.tmp"
    df.write_parquet(tmp, compression="zstd")
    tmp.replace(out / f"{name}.parquet")


def _pe_counts(df: pl.DataFrame, count_col: str, zero_col: str) -> pl.DataFrame:
    return (
        df.group_by("pe_id", "procuring_entity", "ministry")
        .agg(pl.len().alias(count_col))
        .with_columns(pl.lit(0).alias(zero_col))
    )


def build(data_root: Path, review_path: Path) -> dict:
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
            pl.col("awardee").fill_null("").map_elements(lambda a: res.entity_of.get(a, ""), return_dtype=pl.Utf8).alias("bidder_id"),
            pl.col("procuring_entity").fill_null("").map_elements(_pe_id, return_dtype=pl.Utf8).alias("pe_id"),
        )
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
            .sort("n_awards", descending=True)
        )
        _write(bidders, data_root, "bidders")
        n_bidders = bidders.height

    # tenders and procuring entities
    if not tenders.is_empty():
        tenders = tenders.with_columns(
            pl.col("procuring_entity").fill_null("").map_elements(_pe_id, return_dtype=pl.Utf8).alias("pe_id")
        )
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
