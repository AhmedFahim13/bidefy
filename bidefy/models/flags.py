"""Concentration and residual flags for procuring entities and bidders.

Every flag is a number with the count behind it, phrased as a pattern. Nothing here is a verdict.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import polars as pl

MIN_AWARDS_FOR_NOTE = 5
TOP_SHARE_NOTE = 0.5
HHI_NOTE = 0.4
TOP_ENTITY_NOTE = 0.7
OUTSIDE_FACTOR = 3.0
EMPTY_PE = pl.DataFrame({"pe_id": [], "flags": []}, schema={"pe_id": pl.Utf8, "flags": pl.Utf8})
EMPTY_BIDDER = pl.DataFrame({"bidder_id": [], "flags": []}, schema={"bidder_id": pl.Utf8, "flags": pl.Utf8})


def since_default(today: date | None = None) -> str:
    return ((today or date.today()) - timedelta(days=365)).isoformat()


def _window(contracts: pl.DataFrame, since: str) -> pl.DataFrame:
    return contracts.filter((pl.col("bidder_id").fill_null("") != "") & (pl.col("signed_on").fill_null("") >= since))


def entity_flags(contracts: pl.DataFrame, since: str) -> pl.DataFrame:
    """pe_id -> flags JSON: awards_12m, winners, top_bidder, top_share, top3_share, hhi, notes."""
    if contracts.is_empty():
        return EMPTY_PE.clone()
    w = _window(contracts, since)
    rows = []
    for (pe,), grp in w.group_by("pe_id"):
        n = grp.height
        by = (
            grp.group_by("bidder_id")
            .agg(pl.len().alias("k"), pl.col("awardee").mode().first().alias("name"))
            .sort(["k", "bidder_id"], descending=[True, False])
        )
        shares = (by["k"] / n).to_list()
        top_share = shares[0]
        top3 = sum(shares[:3])
        hhi = sum(s * s for s in shares)
        notes = []
        if n >= MIN_AWARDS_FOR_NOTE:
            if top_share >= TOP_SHARE_NOTE:
                notes.append(f"One bidder won {round(top_share * 100)} percent of {n} awards in the last 12 months")
            if hhi >= HHI_NOTE and by.height > 1:
                notes.append(f"Awards concentrated among {by.height} winners (HHI {hhi:.2f})")
        rows.append({"pe_id": pe, "flags": json.dumps({
            "awards_12m": n, "winners": by.height, "top_bidder": by["name"][0], "top_bidder_id": by["bidder_id"][0],
            "top_share": round(top_share, 4), "top3_share": round(min(top3, 1.0), 4), "hhi": round(hhi, 4), "notes": notes,
        }, ensure_ascii=False)})
    return pl.DataFrame(rows, schema={"pe_id": pl.Utf8, "flags": pl.Utf8}) if rows else EMPTY_PE.clone()


def bidder_flags(contracts: pl.DataFrame, bands: pl.DataFrame | None, since: str) -> pl.DataFrame:
    """bidder_id -> flags JSON: awards_12m, entities, top_entity, top_entity_share, above_band, below_band, notes.

    bands: tender_id, q10_lakh, q90_lakh for historical awards. An award is well outside the band when it is
    more than OUTSIDE_FACTOR times above the top edge or below the bottom edge (values are log-scaled).
    """
    if contracts.is_empty():
        return EMPTY_BIDDER.clone()
    w = _window(contracts, since)
    if bands is not None and not bands.is_empty():
        w = w.join(bands.select("tender_id", "q10_lakh", "q90_lakh"), on="tender_id", how="left")
    else:
        w = w.with_columns(pl.lit(None, dtype=pl.Float64).alias("q10_lakh"), pl.lit(None, dtype=pl.Float64).alias("q90_lakh"))
    w = w.with_columns((pl.col("value_crore") * 100).alias("lakh")).with_columns(
        (pl.col("lakh") > pl.col("q90_lakh") * OUTSIDE_FACTOR).fill_null(False).alias("above"),
        (pl.col("lakh") < pl.col("q10_lakh") / OUTSIDE_FACTOR).fill_null(False).alias("below"),
    )
    rows = []
    for (bid,), grp in w.group_by("bidder_id"):
        n = grp.height
        by = grp.group_by("pe_id").agg(pl.len().alias("k")).sort(["k", "pe_id"], descending=[True, False])
        top_share = by["k"][0] / n
        above, below = int(grp["above"].sum()), int(grp["below"].sum())
        notes = []
        if n >= MIN_AWARDS_FOR_NOTE and top_share >= TOP_ENTITY_NOTE:
            notes.append(f"{round(top_share * 100)} percent of its awards come from one entity ({n} awards in 12 months)")
        if above + below > 0:
            plural = "s" if above != 1 else ""
            notes.append(f"{above} award{plural} well above and {below} well below the predicted band")
        rows.append({"bidder_id": bid, "flags": json.dumps({
            "awards_12m": n, "entities": by.height, "top_entity": by["pe_id"][0], "top_entity_share": round(top_share, 4),
            "above_band": above, "below_band": below, "notes": notes,
        }, ensure_ascii=False)})
    return pl.DataFrame(rows, schema={"bidder_id": pl.Utf8, "flags": pl.Utf8}) if rows else EMPTY_BIDDER.clone()
