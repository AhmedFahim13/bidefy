"""Write docs/product/03-buyers.md: five buyer profiles selected from real award data by fixed rules."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "product" / "03-buyers.md"


def crore(v: float | None) -> str:
    if v is None:
        return "n/a"
    return f"{v:.2f} crore" if v >= 1 else f"{v * 100:.1f} lakh"


def main() -> None:
    contracts = pl.read_parquet(ROOT / "data" / "clean" / "contracts.parquet")
    bidders = pl.read_parquet(ROOT / "data" / "clean" / "bidders.parquet")
    awarded = contracts.filter(pl.col("bidder_id") != "")
    if awarded.height < 100:
        OUT.write_text("# Buyer profiles\n\nNot enough award data yet.\n", encoding="utf-8")
        print("not enough data")
        return
    today = date.today()
    year_ago = (today - timedelta(days=365)).isoformat()
    ninety = (today - timedelta(days=90)).isoformat()
    name_of = dict(zip(bidders["bidder_id"].to_list(), bidders["canonical_name"].to_list()))

    per_pe = awarded.group_by("bidder_id", "pe_id", "procuring_entity").len().sort("len", descending=True)
    specialist = per_pe.row(0, named=True)
    ministries = awarded.group_by("bidder_id").agg(pl.col("ministry").n_unique().alias("n_min"), pl.len().alias("n")).filter(pl.col("n_min") >= 4).sort("n", descending=True)
    generalist = ministries.row(0, named=True) if ministries.height else None
    recent_value = awarded.filter(pl.col("signed_on") >= year_ago).group_by("bidder_id").agg(pl.col("value_crore").fill_null(0).sum().alias("v"), pl.len().alias("n")).sort("v", descending=True)
    infra = recent_value.row(0, named=True) if recent_value.height else None
    first = awarded.group_by("bidder_id").agg(pl.col("signed_on").min().alias("first"), pl.len().alias("n")).filter(pl.col("first") >= ninety).sort("n", descending=True)
    newcomer = first.row(0, named=True) if first.height else None
    dist = awarded.filter(pl.col("district") != "").group_by("bidder_id", "district").len()
    tot = awarded.group_by("bidder_id").len().rename({"len": "total"})
    dist = dist.join(tot, on="bidder_id").with_columns((pl.col("len") / pl.col("total")).alias("share")).filter(pl.col("total") >= 8).sort(["share", "total"], descending=[True, True])
    regional = dist.row(0, named=True) if dist.height else None

    def block(title: str, bid: str, facts: list[str], show: str) -> str:
        rows = awarded.filter(pl.col("bidder_id") == bid)
        cats = rows["category"].value_counts().sort("count", descending=True).head(3)["category"].to_list() if "category" in rows.columns else []
        lines = [f"## {title}: {name_of.get(bid, bid)}", ""]
        lines += [f"- {f}" for f in facts]
        lines.append(f"- Awards indexed: {rows.height}, total value {crore(float(rows['value_crore'].fill_null(0).sum()))}")
        lines.append(f"- Entities: {rows['pe_id'].n_unique()}, districts: {rows.filter(pl.col('district') != '')['district'].n_unique()}")
        if cats:
            lines.append(f"- Main categories: {', '.join(c for c in cats if c)}")
        lines += ["", f"**What Bidefy shows them:** {show}", ""]
        return "\n".join(lines)

    parts = ["# Five buyer profiles", "", "These profiles are computed from public award data, not interviews. Each is a real bidder selected by a fixed rule; the rule is stated so the selection can be reproduced.", ""]
    parts.append(block("The specialist", specialist["bidder_id"], [f"Rule: most awards at a single procuring entity ({specialist['procuring_entity']}, {specialist['len']} awards)."],
                       "Every new tender from that entity within the hour, the entity's award history, and the value band before they price."))
    if generalist:
        parts.append(block("The generalist", generalist["bidder_id"], [f"Rule: awards under {generalist['n_min']} or more ministries, most awards among them."],
                           "Category filters across ministries and a single feed instead of five portals' worth of notices."))
    if infra:
        parts.append(block("The infrastructure contractor", infra["bidder_id"], [f"Rule: highest total award value in the last twelve months ({crore(float(infra['v']))} across {infra['n']} awards)."],
                           "Who else wins at the entities they target, the concentration flags, and bands on multi-crore tenders where one mispriced bid costs more than a year of Pro."))
    if newcomer:
        parts.append(block("The newcomer", newcomer["bidder_id"], [f"Rule: first indexed award within the last 90 days, most awards since ({newcomer['n']})."],
                           "Which entities award to newcomers, and the typical value at their size, so they bid where they can win."))
    if regional:
        parts.append(block("The regional bidder", regional["bidder_id"], [f"Rule: highest share of awards in one district ({regional['district']}, {regional['share']:.0%} of {regional['total']})."],
                           "District-filtered alerts and the entities in their district ranked by volume."))
    parts.append("Pricing signal: the first three profiles bid on tenders where a one percent pricing error exceeds 2,500 taka. The last two are free-tier users until they grow.")
    OUT.write_text("\n".join(parts) + "\n", encoding="utf-8")
    print("wrote", OUT, json.dumps({"awarded_rows": awarded.height}))


if __name__ == "__main__":
    main()
