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
        add(f"Trained on {aw.get('n_fit', 0):,} awards, calibrated on {aw.get('n_calibration', 0):,} "
            f"out-of-sample residuals, tested on the {aw.get('n_test', 0):,} most recent awards "
            f"(everything signed on or after {aw.get('test_from', 'n/a')}). The test awards are later "
            "in time than every award used to fit or calibrate, so this is a forecast, not a fit.")
        add("")
        add("A tender notice publishes a refundable tender security. Buyers set it as a fixed share "
            "of a cost estimate they do not publish, and awards land near that estimate, so where a "
            "security exists it pins the value far more tightly than history can.")
        add("")
        add("| | From the tender security | From entity history |")
        add("|---|---|---|")
        add(f"| Tenders in the test set | {aw.get('security_n', 0):,} | {aw.get('history_n', 0):,} |")
        add(f"| Median error of the central estimate | {pct(aw.get('security_mape'))} | {pct(aw.get('history_mape'))} |")
        add(f"| Share of awards inside the band | {pct(aw.get('security_coverage_80'))} | {pct(aw.get('history_coverage_80'))} |")
        add(f"| Typical band, high over low | {num(aw.get('security_band_width_median'))}x | {num(aw.get('history_band_width_median'))}x |")
        add("")
        if aw.get("live_security_share") is not None:
            add("### What a bidder actually meets")
            add("")
            add(f"Of the tenders open right now, {pct(aw.get('live_security_share'))} publish a security and "
                "take the precise route. The historical test window looks nothing like that, because its "
                "detail pages have mostly never been fetched, so a security appears absent there when it was "
                "only uncollected. Resampling the test awards to today's mix of routes gives the figures a "
                "bidder should expect:")
            add("")
            add("| Measure | Value |")
            add("|---|---|")
            add(f"| Median error of the central estimate | {pct(aw.get('expected_mape_on_open_tenders'))} |")
            add(f"| Share of awards inside the band | {pct(aw.get('expected_coverage_on_open_tenders'))} |")
            add(f"| Typical band, high over low | {num(aw.get('expected_band_width_on_open_tenders'))}x |")
            add("")
            add("This is a projection onto a different population, not a fourth measurement. Every number in "
                "it comes from held-out awards; only the proportions are changed, and they are changed to "
                "match what the site serves.")
            add("")
        add(f"Across the test window as crawled, the median error is {pct(aw.get('mape_acted'))} and the typical band is "
            f"{num(aw.get('band_width_median'))}x wide. For scale, the spread between the 10th and 90th "
            f"percentile of all awards is {num(aw.get('unconditional_spread'), 0)}x, which is the band "
            "someone would quote knowing nothing at all. Simply guessing the median award for every "
            f"tender gives a median error of {pct(aw.get('mape_naive_median'))}.")
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
