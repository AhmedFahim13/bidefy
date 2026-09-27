"""Refuse to promote a model that got worse by more than noise can explain.

The design document has promised this since week one -- "a regression past a stated threshold fails
the job and keeps the previous model" -- and until now nothing enforced it. Every nightly run
overwrote the serving model with whatever it had just fitted, so a bad change would have been
published to the accuracy page and served to readers before anyone looked.

Two decisions make the gate honest rather than decorative.

The threshold is measured, not chosen. `tools/metrics_stability.py` reads how far each published
figure actually moves between runs, and the tolerance is the larger of three typical steps and the
widest spread that figure has shown across the measured window. Three steps alone was tried first
and is too tight: coverage steps about 0.3 points a run, which gives 0.9, while it has genuinely
ranged over 1.5 points in a week, so a good run would have been blocked. Taking the observed spread
as a floor makes the rule sayable in one line -- block only when a figure moves further than it has
ever been seen to move -- and a real regression is several points, well clear of it. Where nothing
has been measured yet, a deliberately generous default applies, because blocking on noise is worse
than missing one bad run.

And a block never fails the training step. That step runs before the crawl's data is committed, and
a job that dies here throws away hours of crawling. So a blocked candidate is recorded, the previous
model keeps serving, the run exits zero, and a separate step after the commit fails the build so a
human is actually told. The accuracy page says a candidate was blocked, because a page that only
describes models that passed would be advertising.
"""
from __future__ import annotations

import json
from datetime import datetime, UTC
from pathlib import Path

TOLERANCE_STEPS = 3
# Generous, and only used before the run-to-run spread of a figure has been measured. Two points of
# accuracy or coverage is far more than any real night moves, so this cannot block on noise.
DEFAULT_TOLERANCE = 0.02
MULTIPLE_TOLERANCE = 0.5        # band widths are multiples, not shares

# (key, which direction is better). Only figures a reader is asked to trust are guarded: a count of
# rows scored moves with the archive and means nothing about quality.
GUARDED: dict[str, tuple[tuple[str, str], ...]] = {
    "award_value_model": (
        ("coverage_80", "up"),
        ("history_coverage_80", "up"),
        ("history_mape", "down"),
        ("history_band_width_median", "down"),
        ("security_coverage_80", "up"),
        ("security_mape", "down"),
    ),
    "category_classifier": (
        ("accuracy_acted", "up"),
        ("deferral_rate", "down"),
        ("macro_f1", "up"),
    ),
}


def _tolerance(section: str, key: str, stability: dict) -> float:
    """How far this figure may fall before the candidate is refused.

    The larger of three typical steps and the widest spread already observed, so the rule is "it
    moved further than it has ever moved" rather than a number somebody picked.
    """
    figure = (stability.get("figures") or {}).get(f"{section}.{key}") or {}
    step, spread = figure.get("typical_step"), figure.get("spread")
    measured = [v for v in (TOLERANCE_STEPS * float(step) if isinstance(step, (int, float)) and step > 0 else None,
                            float(spread) if isinstance(spread, (int, float)) and spread > 0 else None)
                if v is not None]
    if measured:
        return max(measured)
    return MULTIPLE_TOLERANCE if figure.get("kind") == "multiple" else DEFAULT_TOLERANCE


def _read(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def check(section: str, candidate: dict, models_dir: Path) -> list[dict]:
    """Which guarded figures the candidate lost on, by more than the measured noise allows.

    An empty list means promote. There is nothing to compare against on a first run, so a first run
    always promotes: a gate that blocked it would leave the product with no model at all.
    """
    models_dir = Path(models_dir)
    previous = _read(models_dir / "metrics.json").get(section) or {}
    if not previous:
        return []
    stability = _read(models_dir / "stability.json")
    breaches = []
    for key, better in GUARDED.get(section, ()):
        was, now = previous.get(key), candidate.get(key)
        if not isinstance(was, (int, float)) or not isinstance(now, (int, float)):
            continue
        tolerance = _tolerance(section, key, stability)
        lost = (was - now) if better == "up" else (now - was)
        if lost > tolerance:
            breaches.append({"figure": key, "better": better, "was": round(float(was), 4),
                             "now": round(float(now), 4), "lost": round(float(lost), 4),
                             "tolerated": round(tolerance, 4)})
    return breaches


def describe(section: str, breaches: list[dict]) -> str:
    parts = [f"{b['figure']} {b['was']} -> {b['now']} (lost {b['lost']}, tolerated {b['tolerated']})"
             for b in breaches]
    return f"{section} not promoted: " + "; ".join(parts)


def record_blocked(models_dir: Path, section: str, candidate: dict, breaches: list[dict]) -> None:
    """Keep the serving model's figures in place and file the rejected candidate beside them."""
    path = Path(models_dir) / "metrics.json"
    metrics = _read(path)
    metrics.setdefault("blocked", {})[section] = {
        "at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "breaches": breaches,
        "candidate": candidate,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metrics, indent=2) + chr(10), encoding="utf-8")


def clear_blocked(metrics: dict, section: str) -> dict:
    """Drop a stale rejection once this section promotes again."""
    blocked = metrics.get("blocked")
    if isinstance(blocked, dict):
        blocked.pop(section, None)
        if not blocked:
            metrics.pop("blocked", None)
    return metrics
