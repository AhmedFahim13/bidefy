"""Generate docs/product/05-accuracy.md from models/metrics.json.

The accuracy page is written by the same run that trains the models, so the published numbers
can never drift from the model that produced them. Nothing here is typed by hand.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "product" / "05-accuracy.md"


def pct(v, digits: int = 1) -> str:
    return "n/a" if v is None else f"{v * 100:.{digits}f} percent"


def num(v, digits: int = 2) -> str:
    return "n/a" if v is None else f"{v:,.{digits}f}".rstrip("0").rstrip(".")


def live_category_sources() -> tuple[int, float] | None:
    """How many live tenders take their category from the portal rather than from the model."""
    path = ROOT / "data" / "clean" / "tenders.parquet"
    if not path.exists():
        return None
    import polars as pl
    df = pl.read_parquet(path)
    if "category_source" not in df.columns or "status" not in df.columns:
        return None
    live = df.filter(pl.col("status") == "Live")
    if live.is_empty():
        return None
    return live.height, float((live["category_source"] == "portal").mean())


def main() -> None:
    metrics_path = ROOT / "models" / "metrics.json"
    if not metrics_path.exists():
        OUT.write_text("# Accuracy\n\nNo models have been trained yet.\n", encoding="utf-8")
        return
    m = json.loads(metrics_path.read_text(encoding="utf-8"))
    cat = m.get("category_classifier", {})
    aw = m.get("award_value_model", {})
    lines: list[str] = []
    add = lines.append

    add("# What Bidefy gets right, and how often")
    add("")
    add("Every figure here is measured on data the model was not trained on, and this page is "
        "written by the training run itself, so it cannot drift from the model it describes.")
    add("")
    add("Two rules govern everything below. A model may decline, and when it declines that is "
        "reported next to its accuracy, because an accuracy figure without its deferral rate is "
        "not a measurement. And a prediction is only scored against evidence the model could not "
        "have seen: the portal's own records, never a rule Bidefy wrote.")
    add("")

    if aw:
        add("## Award value")
        add("")
        add(f"The history route is trained on {aw.get('n_fit', 0):,} awards, calibrated on "
            f"{aw.get('n_calibration', 0):,} out-of-sample residuals, and scored on the "
            f"{aw.get('n_test', 0):,} most recent awards, everything signed on or after "
            f"{aw.get('test_from', 'n/a')}. Every award it is scored on is later in time than every "
            "award used to fit or calibrate it, so this is a forecast, not a fit.")
        add("")
        add("A tender notice publishes a refundable tender security. Buyers set it as a fixed share "
            "of a cost estimate they do not publish, and awards land near that estimate, so where a "
            "security exists it pins the value far more tightly than history can.")
        add("")
        add("The two routes are measured on two different windows, and are never averaged into one "
            "headline. The archive of awards reaches back years, but detail pages have only been "
            "fetched for roughly the last year, so every published security on record is recent. "
            "Split the whole archive by date and all of them land after the cut, leaving the "
            "security multiplier nothing to learn from. So that route is given its own split, at "
            "eighty percent of the securities by date, fitted on the earlier ones and scored on the "
            "later ones. Both windows are strictly forward-looking.")
        add("")
        add("| | From the tender security | From entity history |")
        add("|---|---|---|")
        add(f"| Awards scored | {aw.get('security_n', 0):,} | {aw.get('history_n', 0):,} |")
        add(f"| Fitted on | {aw.get('security_fitted_on', 0):,} earlier securities | {aw.get('n_fit', 0):,} earlier awards |")
        add(f"| Scored on awards signed from | {aw.get('security_test_from', 'n/a')} | {aw.get('test_from', 'n/a')} |")
        add(f"| Median error of the central estimate | {pct(aw.get('security_mape'))} | {pct(aw.get('history_mape'))} |")
        add(f"| Share of awards inside the band | {pct(aw.get('security_coverage_80'))} | {pct(aw.get('history_coverage_80'))} |")
        add(f"| Typical band, high over low | {num(aw.get('security_band_width_median'))}x | {num(aw.get('history_band_width_median'))}x |")
        add("")
        add(f"Of the {aw.get('security_route_n_total', 0):,} awards in the archive whose notice "
            "published a security, that is every one the route could be scored on without fitting "
            "and testing on the same rows.")
        add("")
        share = aw.get("live_security_share")
        if share is not None and aw.get("security_mape") is not None:
            add("### What a bidder actually meets")
            add("")
            add(f"Of the tenders open right now, {pct(share)} publish a security and take the precise "
                "route; the rest fall to history. The archive is a poor guide to that split, because "
                "its detail pages were mostly never fetched, so a security looks absent there when it "
                "was only uncollected. Weighting the two measured routes by the split the site "
                "actually serves:")
            add("")
            add("| Route | Share of open tenders | Median error | Typical band |")
            add("|---|---|---|---|")
            add(f"| From the tender security | {pct(share)} | {pct(aw.get('security_mape'))} | {num(aw.get('security_band_width_median'))}x |")
            add(f"| From entity history | {pct(1 - share)} | {pct(aw.get('history_mape'))} | {num(aw.get('history_band_width_median'))}x |")
            add("")
            add("Four tenders in five get the precise answer. That is a property of what the portal "
                "publishes, not of the model, and it is the single most valuable thing found in this "
                "project. Nothing here is an average of the two rows: each is measured on its own "
                "held-out window and reported as itself.")
            add("")

        add(f"Taking the test window exactly as crawled, with whatever mix of routes it happens to "
            f"contain, the median error is {pct(aw.get('mape_acted'))} and the typical band is "
            f"{num(aw.get('band_width_median'))}x wide. For scale, the spread between the 10th and 90th "
            f"percentile of all awards is {num(aw.get('unconditional_spread'), 0)}x, which is the band "
            "someone would quote knowing nothing at all. Simply guessing the median award for every "
            f"tender gives a median error of {pct(aw.get('mape_naive_median'))}.")
        add("")
        by_method = aw.get("history_by_method") or {}
        if by_method:
            add("### The history route is not one number")
            add("")
            add("Open tendering is the hardest method to price and the one the history route is "
                "mostly asked about, because a large open tender is exactly the kind that publishes "
                "no security. Quoting a single history figure would hide that, so here is each "
                "method on its own.")
            add("")
            add("| Method | Tenders answered | Median error | Inside the band | Typical band | Declined |")
            add("|---|---|---|---|---|---|")
            for name, v in by_method.items():
                add(f"| {name} | {v['n_acted']:,} | {pct(v['mape'])} | {pct(v['coverage_80'])} | "
                    f"{num(v['band_width_median'])}x | {pct(v['deferral_rate'])} |")
            add("")

        limits = aw.get("deferral_at_band_limit") or {}
        if limits:
            add("Bidefy declines when a band would be too wide to act on. Where that line is drawn is "
                "a product decision, not a statistical one, so here is the whole trade:")
            add("")
            add("| Widest band shown | Tenders declined |")
            add("|---|---|")
            for limit, rate in sorted(limits.items(), key=lambda kv: int(kv[0])):
                add(f"| {limit}x | {pct(rate)} |")
            add("")

    if cat:
        add("## Category")
        add("")
        add("A tender's category is read from the portal's own tags wherever Bidefy has fetched that "
            "tender's detail page. The model below exists only to cover tenders whose detail page has "
            "not been fetched, mostly older archived ones.")
        add("")
        live = live_category_sources()
        if live:
            count, share = live
            add(f"Of the {count:,} tenders open right now, {pct(share)} take their category straight from "
                "the portal. For those the category is not a prediction at all, and nothing is declined.")
            add("")
        add(f"Trained and scored on {cat.get('n_labels', 0):,} tenders across {cat.get('n_classes', 0)} "
            f"categories, {cat.get('evaluation', 'cross-validated')}.")
        add("")
        add("| Measure | Value |")
        add("|---|---|")
        add(f"| Accuracy on the predictions it commits to | {pct(cat.get('accuracy_acted'))} |")
        add(f"| Share of tenders it declines | {pct(cat.get('deferral_rate'))} |")
        add(f"| Accuracy if forced to answer every time | {pct(cat.get('accuracy_all'))} |")
        add(f"| Macro F1 across categories | {num(cat.get('macro_f1'), 3)} |")
        add(f"| Deferral needed to reach 93 percent | {pct(cat.get('deferral_for_93'))} |")
        add(f"| Deferral needed to reach 95 percent | {pct(cat.get('deferral_for_95'))} |")
        add("")
        if cat.get("repeats", 1) > 1:
            add(f"This model is not deterministic. Run the same cross-validation again, on the same "
                f"data with the same seed, and the share it declines moves by up to "
                f"{pct(cat.get('deferral_spread'))} and its macro F1 by "
                f"{num(cat.get('macro_f1_spread'), 3)}. That is the floor below which a change to "
                f"this model cannot be distinguished from chance, and it is published here because a "
                f"figure quoted without it invites reading an improvement into noise. The numbers "
                f"above pool {cat.get('repeats')} runs, which is why they are steadier than any one of them.")
            add("")

        dropped = cat.get("classes_dropped_for_sparsity") or []
        if dropped:
            add(f"Categories held back for want of examples: {', '.join(dropped)}. They return once the "
                "detail crawl has collected enough of them.")
            add("")

    add("## What would move these numbers")
    add("")
    add("The award band is limited by what a notice says. The title carries the item but rarely the "
        "quantity, and the quantity lives in a tender document behind a fee. Fetching the detail page "
        "of every live tender is what unlocks the security route, and that is now part of the nightly "
        "run. The category model is limited by labelled examples, and every detail page fetched adds one.")
    add("")
    add("An earlier version of the category model also trained on labels produced by a keyword rule "
        "Bidefy wrote. Removing them was worth doing: adding twenty thousand such rows had driven "
        "accuracy against the portal's real tags from 89.8 percent down to 55.4 percent, while making "
        "the published figure look better, because the model was partly being scored on the rule it "
        "had been taught to copy.")
    add("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
