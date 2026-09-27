"""Fail the build when a nightly run produced something that is wrong but looks fine.

Every incident this project has had is the same shape. Two crawlers raced one checkpoint and each
reported success. A `shell=True` call ran bare `npx`, wrote nothing to D1 for days and exited zero.
A stale model bundle failed its format check, `load()` returned None, and the build quietly wrote an
empty category for ninety-six percent of contracts while every step stayed green. None of these were
hard to fix and none of them were caught by a test, because nothing crashed: the pipeline did the
wrong thing successfully.

So this asserts the things that were true before and must stay true, on the artefacts the run
actually produced. It is deliberately about outcomes rather than code paths -- it does not care how
the categories were written, only that they exist -- which is why it catches causes nobody has
thought of yet.

It runs *after* the crawl's data has been committed, never before. A check that can abort the job
mid-pipeline would throw away hours of crawling to report a cosmetic problem, which is a worse trade
than the problem. By the time this runs the data is safe, so it is free to exit non-zero and make
somebody look.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# A published estimate above this many lakh is not a big tender, it is a parse error. The largest
# award in the archive is about 32,000 lakh, so this leaves an order of magnitude of headroom.
MAX_SANE_ESTIMATE_LAKH = 500_000.0


def _fail(checks: list[tuple[bool, str]], ok: bool, message: str) -> None:
    checks.append((ok, message))


def check_promotions(models_dir: Path, checks: list) -> None:
    """A model the gate rejected must not pass unnoticed just because the run exited zero."""
    path = models_dir / "metrics.json"
    if not path.exists():
        return
    blocked = json.loads(path.read_text(encoding="utf-8")).get("blocked") or {}
    for section, entry in blocked.items():
        figures = ", ".join(
            f"{b['figure']} {b['was']} to {b['now']}" for b in entry.get("breaches", []))
        _fail(checks, False,
              f"{section}: a candidate trained at {entry.get('at')} was rejected and the previous "
              f"model is still serving ({figures}). Investigate before the next run, or widen the "
              f"tolerance deliberately if the loss is real and acceptable.")


def check_categories(data_root: Path, checks: list) -> None:
    """Some tender without a portal tag must carry a model category.

    This is the stale-bundle incident, stated as an outcome. When `classifier.load` rejects a bundle
    whose format has moved on, it returns None and the build writes an empty category for every
    untagged tender without complaining. The share looks healthy because the portal's own tags cover
    most live tenders, so the only sharp signal is that the model contributed nothing at all.
    """
    path = data_root / "clean" / "tenders.parquet"
    if not path.exists():
        return
    import polars as pl
    df = pl.read_parquet(path)
    if "category_source" not in df.columns:
        _fail(checks, False, "tenders.parquet has no category_source column; the build did not tag")
        return
    untagged = df.filter(pl.col("category_source") != "portal").height
    from_model = df.filter(pl.col("category_source") == "model").height
    if untagged and not from_model:
        _fail(checks, False,
              f"{untagged:,} tenders carry no portal tag and the model categorised none of them. "
              "That is what an unusable model bundle looks like: check that the classifier trained "
              "and that models/category.joblib matches the code's BUNDLE_FORMAT.")
    else:
        _fail(checks, True, f"categories: {from_model:,} from the model, {untagged:,} untagged")


def check_predictions(data_root: Path, checks: list) -> None:
    """Every live tender gets a band, the band is ordered, and no estimate is absurd."""
    tpath, ppath = data_root / "clean" / "tenders.parquet", data_root / "clean" / "predictions.parquet"
    if not (tpath.exists() and ppath.exists()):
        return
    import polars as pl
    live = pl.read_parquet(tpath)
    if "status" in live.columns:
        live = live.filter(pl.col("status") == "Live")
    preds = pl.read_parquet(ppath)
    if live.is_empty():
        return
    covered = preds.height / live.height
    if covered < 0.95:
        _fail(checks, False, f"predictions cover {covered:.1%} of {live.height:,} live tenders; "
                             "the apply step did not finish")
    else:
        _fail(checks, True, f"predictions: {preds.height:,} rows for {live.height:,} live tenders")
    disordered = preds.filter((pl.col("q10_lakh") > pl.col("q50_lakh"))
                              | (pl.col("q50_lakh") > pl.col("q90_lakh"))).height
    _fail(checks, disordered == 0, f"{disordered:,} predictions have their band out of order"
          if disordered else "predictions: every band is ordered low to high")
    absurd = preds.filter(pl.col("q50_lakh") > MAX_SANE_ESTIMATE_LAKH)
    if absurd.height:
        worst = absurd.select(pl.col("q50_lakh").max()).item()
        _fail(checks, False,
              f"{absurd.height:,} predictions exceed {MAX_SANE_ESTIMATE_LAKH:,.0f} lakh, the worst "
              f"at {worst:,.0f}. A mis-punctuated tender security reads like this; check the "
              "plausibility guard in bidefy/models/award.py.")
    else:
        _fail(checks, True, "predictions: no estimate is beyond what the archive has ever awarded")


def check_generated_docs(checks: list) -> None:
    """The accuracy page is generated. If regenerating it changes anything, it was edited by hand."""
    page = ROOT / "docs" / "product" / "05-accuracy.md"
    if not page.exists():
        return
    before = page.read_text(encoding="utf-8")
    run = subprocess.run([sys.executable, str(ROOT / "tools" / "write_accuracy_doc.py")],
                         cwd=ROOT, capture_output=True, text=True)
    if run.returncode != 0:
        _fail(checks, False, f"tools/write_accuracy_doc.py failed: {run.stderr.strip()[:200]}")
        return
    if page.read_text(encoding="utf-8") != before:
        _fail(checks, False,
              "docs/product/05-accuracy.md is not what the writer produces from models/metrics.json. "
              "The page promises it cannot drift from the model it describes, so either it was "
              "edited by hand or the writer was changed without regenerating it.")
    else:
        _fail(checks, True, "the accuracy page matches what the writer produces right now")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Assert the invariants a nightly run must not break")
    ap.add_argument("--data-root", default="data")
    ap.add_argument("--models-dir", default="models")
    a = ap.parse_args(argv)
    checks: list[tuple[bool, str]] = []
    check_promotions(Path(a.models_dir), checks)
    check_categories(Path(a.data_root), checks)
    check_predictions(Path(a.data_root), checks)
    check_generated_docs(checks)

    for ok, message in checks:
        print(f"{'ok  ' if ok else 'FAIL'} {message}")
    broken = [m for ok, m in checks if not ok]
    if broken:
        print(f"\n{len(broken)} invariant(s) broken. The data is committed and safe; the run that "
              "produced it is not trustworthy.")
        return 1
    print(f"\n{len(checks)} invariant(s) hold.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
