"""Measure how much the published figures move between nightly runs, from the repository's own history.

The category model publishes a noise floor and says that a figure quoted without one invites reading
an improvement into noise. The award model published none, and when two runs on identical fit data
moved its coverage by nearly a point it became clear that it needed one.

Rather than retrain the award model many times to estimate its spread -- which would cost an hour
and would only capture its own seed, not the classifier refit upstream that feeds it a category
feature -- this reads the real thing. Every nightly run rewrites models/metrics.json, so its git
history is a record of what each run published. The night-to-night step in a figure is therefore
measured rather than modelled, and it includes every source at once: the seed, the upstream refit,
and the archive growing.

That last source matters for how the numbers are read. A figure that should hold still, like
coverage against an 80 percent target, moves mostly by noise. One that is meant to improve, like the
category model's deferral as labels accumulate, moves mostly by data. The output carries the
direction of travel so the two can be told apart, and the accuracy page says so in words.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRACKED = Path("models/metrics.json")
OUT = ROOT / "models" / "stability.json"
RUNS = 14          # about a week of runs, two a day
MIN_RUNS = 5       # below this the spread says more about the clone than about the models

# (section, key, label, steady, kind, better). "steady" marks a figure meant to hold still, so that
# movement in it reads as noise while movement in the others reads as the archive growing. "kind"
# travels with the figure because a band width is a multiple and an F1 is a score: formatting either
# as a percentage would print nonsense. "better" travels with it because the page describes movement
# in words, and without a direction a regression gets announced as an improvement. The page is
# generated, so nothing downstream can catch either mistake.
FIGURES = [
    ("award_value_model", "coverage_80", "Award band coverage, whole window", True, "pct", "up"),
    ("award_value_model", "history_coverage_80", "Coverage, history route", True, "pct", "up"),
    ("award_value_model", "history_mape", "Median error, history route", True, "pct", "down"),
    ("award_value_model", "history_band_width_median", "Band width, history route", True, "multiple", "down"),
    ("award_value_model", "security_coverage_80", "Coverage, security route", True, "pct", "up"),
    ("award_value_model", "security_mape", "Median error, security route", True, "pct", "down"),
    # Award deferral is not meant to hold still either: the detail crawl keeps finding securities,
    # and a tender with a security is never declined, so this should fall as the archive fills.
    ("award_value_model", "deferral_rate", "Award deferral", False, "pct", "down"),
    ("category_classifier", "accuracy_acted", "Category accuracy", True, "pct", "up"),
    ("category_classifier", "deferral_rate", "Category deferral", False, "pct", "down"),
    ("category_classifier", "macro_f1", "Category macro F1", False, "score", "up"),
]


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def _history(limit: int) -> list[dict]:
    """Each distinct training run that reached the repository, oldest first."""
    shas = _git("log", f"-{limit * 3}", "--format=%H", "--", str(TRACKED)).split()
    runs: list[dict] = []
    seen: set[str] = set()
    for sha in shas:
        try:
            blob = json.loads(_git("show", f"{sha}:{TRACKED.as_posix()}"))
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            continue
        stamp = str((blob.get("award_value_model") or {}).get("trained_at")
                    or (blob.get("category_classifier") or {}).get("trained_at") or sha)
        if stamp in seen:
            continue            # a commit that carried the file without retraining
        seen.add(stamp)
        runs.append({"trained_at": stamp, "metrics": blob})
        if len(runs) >= limit:
            break
    return list(reversed(runs))


def main() -> None:
    try:
        _write()
    except Exception as exc:
        # This runs inside the nightly training step, and "Commit data" is the step after it. A
        # non-zero exit here would skip that step and throw away hours of crawling for the sake of
        # a table of noise figures, so every failure is swallowed and the section is simply omitted.
        OUT.write_text(json.dumps({"runs": 0, "error": str(exc)[:200], "figures": {}}, indent=2)
                       + chr(10), encoding="utf-8")
        print(f"metrics stability: skipped ({type(exc).__name__}: {exc})")


def _write() -> None:
    runs = _history(RUNS)
    shallow = _git("rev-parse", "--is-shallow-repository").strip() == "true"
    out: dict = {"runs": len(runs), "shallow_clone": shallow, "figures": {}}
    if len(runs) < MIN_RUNS:
        # Publishing a spread measured over two runs would understate the floor, and understating
        # the floor is how a change gets read as a result. Say nothing instead.
        OUT.write_text(json.dumps(out, indent=2) + chr(10), encoding="utf-8")
        print(f"wrote {OUT}: only {len(runs)} runs in history"
              + (" (shallow clone)" if shallow else "") + ", no spread published")
        return
    if len(runs) >= 2:
        out["from"] = runs[0]["trained_at"]
        out["to"] = runs[-1]["trained_at"]
    for section, key, label, steady, kind, better in FIGURES:
        series = [r["metrics"].get(section, {}).get(key) for r in runs]
        series = [float(v) for v in series if isinstance(v, (int, float))]
        if len(series) < 3:
            continue
        # Ragged on purpose: n values give n-1 steps, so this is the one zip here that must
        # not be strict.
        steps = [abs(b - a) for a, b in zip(series, series[1:], strict=False)]
        out["figures"][f"{section}.{key}"] = {
            "label": label,
            "expected_steady": steady,
            "kind": kind,
            "better": better,
            "runs": len(series),
            "first": round(series[0], 4),
            "last": round(series[-1], 4),
            "min": round(min(series), 4),
            "max": round(max(series), 4),
            "spread": round(max(series) - min(series), 4),
            "typical_step": round(sorted(steps)[len(steps) // 2], 4),
            "largest_step": round(max(steps), 4),
            "net_change": round(series[-1] - series[0], 4),
        }
    OUT.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} from {len(runs)} training runs")


if __name__ == "__main__":
    main()
