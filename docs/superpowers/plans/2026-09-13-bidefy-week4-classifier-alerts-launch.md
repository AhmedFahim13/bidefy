# Bidefy Week 4: Category Classifier, Alert Sender and Launch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task inline. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every tender carries a Bidefy category with a confidence and a deferral rule, learned from the portal's own category tags; subscribers receive web push notifications within an hour of a matching tender appearing; the site, API and command centre reflect v0.1 as publicly launched.

**Architecture:** A detail-page sampler fetches category tags for a few thousand tenders. A taxonomy module maps those tags to fifteen Bidefy categories as weak labels. A TF-IDF plus logistic regression classifier learns title to category, reports accuracy on acted-on predictions with the deferral rate beside it, and writes `models/metrics.json` that the command centre already renders. The clean-tables builder applies the model to every tender. D1 gains category columns and a `sent` table. The Worker cron matches new tenders to subscription filters and sends push through the Web Crypto push library, pruning dead endpoints. The site shows categories and offers them as a filter and as an alert filter.

**Tech Stack:** Python, scikit-learn, joblib, polars; Hono, `@block65/webcrypto-web-push`; Next.js.

Spec: `docs/superpowers/specs/2026-09-13-bidefy-design.md`, sections 5.3, 5.5, 8.

---

## File structure

```
bidefy/crawler/details.py           sample and fetch detail pages, checkpointed, into data/raw/details/
bidefy/models/__init__.py
bidefy/models/categories.py         CATEGORIES, label_from_tags()
bidefy/models/classifier.py         train(), apply(), CLI; writes models/category.joblib and models/metrics.json
bidefy/normalize/build.py           applies the model: category, category_confidence columns
bidefy/export/d1.py                 new columns in TABLES
worker/migrations/0001_category_sent.sql
worker/src/alerts.ts                matchFilters(), runAlerts()
worker/src/index.ts                 category filter, admin run-alerts endpoint, scheduled -> runAlerts
worker/src/query.ts                 category filter
worker/test/alerts.test.ts
web/lib/api.ts, web/app/components/*.tsx, web/app/page.tsx   category display and filters
docs/product/02-system.md
tests/test_details.py, tests/test_categories.py, tests/test_classifier.py
```

---

### Task 1: Detail-page sampler

Fetches detail pages for a random sample of tenders at one request per second, stores category tags and security amounts. Runs locally once for the training sample (about 25 minutes from Dhaka), and nightly for live tenders later.

**Files:**
- Create: `bidefy/crawler/details.py`, `tests/test_details.py`

- [ ] **Step 1: Tests** (`tests/test_details.py`)

```python
from pathlib import Path

import polars as pl

from bidefy.crawler import details, store
from bidefy.crawler.checkpoint import Checkpoint

FIX = Path(__file__).parent / "fixtures"
DETAIL = (FIX / "detail_page.html").read_text(encoding="utf-8")


class FakeSession:
    def __init__(self, fail_ids=()):
        self.calls = []
        self.fail_ids = set(fail_ids)

    def detail(self, tender_id):
        self.calls.append(tender_id)
        if tender_id in self.fail_ids:
            raise RuntimeError("boom")
        return DETAIL.replace("1333472", tender_id)


def test_pick_ids_excludes_done_and_is_deterministic():
    ids = [str(i) for i in range(100)]
    a = details.pick_ids(ids, done={"1", "2"}, n=10, seed=7)
    b = details.pick_ids(ids, done={"1", "2"}, n=10, seed=7)
    assert a == b and len(a) == 10 and not ({"1", "2"} & set(a))


def test_fetch_stores_rows_and_skips_failures(tmp_path):
    s = FakeSession(fail_ids={"5"})
    summary = details.fetch(s, ["3", "5", "7"], tmp_path / "data", time_budget_s=1000)
    assert summary.fetched == 2 and summary.failed == 1
    df = store.load_all(tmp_path / "data", "details")
    assert df.height == 2 and set(df["tender_id"].to_list()) == {"3", "7"}
    assert "categories" in df.columns and df["security_bdt"][0] == 80000
    assert isinstance(df["categories"][0], str) and "Software" in df["categories"][0]


def test_fetch_respects_budget(tmp_path):
    s = FakeSession()
    clock = iter([0, 0, 10, 20, 30, 40])
    summary = details.fetch(s, [str(i) for i in range(10)], tmp_path / "data", time_budget_s=15, now=lambda: next(clock))
    assert summary.fetched < 10 and summary.status == "budget"
```

- [ ] **Step 2: Module** (`bidefy/crawler/details.py`)

```python
"""Fetch tender detail pages for a sample of ids; stores category tags and security amounts."""
from __future__ import annotations

import argparse
import json
import random
import time
from dataclasses import dataclass
from pathlib import Path

from . import parse, store
from .session import EgpSession, HttpFailure, SessionExpired

ENDPOINT = "details"
FLUSH_EVERY = 100


@dataclass
class Summary:
    fetched: int = 0
    failed: int = 0
    status: str = "done"


def pick_ids(candidates: list[str], done: set[str], n: int, seed: int = 0) -> list[str]:
    pool = sorted(set(candidates) - set(done))
    rng = random.Random(seed)
    rng.shuffle(pool)
    return pool[:n]


def _row(tender_id: str, d: dict) -> dict:
    return {
        "tender_id": tender_id or d.get("tender_id", ""),
        "categories": json.dumps(d.get("categories", []), ensure_ascii=False),
        "security_bdt": d.get("security_bdt"),
        "document_price_bdt": d.get("document_price_bdt"),
        "brief": d.get("brief", ""),
        "budget_type": d.get("budget_type", ""),
        "source_of_funds": d.get("source_of_funds", ""),
        "procuring_entity_district": d.get("procuring_entity_district", ""),
        "method": d.get("method", ""),
    }


def fetch(session, ids: list[str], data_root: Path, time_budget_s: float, now=time.monotonic, log=print) -> Summary:
    started = now()
    summary = Summary()
    buffer: list[dict] = []
    consecutive = 0
    for tender_id in ids:
        if now() - started > time_budget_s:
            summary.status = "budget"
            break
        try:
            html = session.detail(tender_id)
            d = parse.parse_detail(html)
            if not d.get("procuring_entity"):
                raise RuntimeError("empty detail")
            buffer.append(_row(tender_id, d))
            summary.fetched += 1
            consecutive = 0
        except (HttpFailure, SessionExpired, RuntimeError) as e:
            summary.failed += 1
            consecutive += 1
            log(f"detail {tender_id}: {e}")
            if consecutive >= 3:
                summary.status = "aborted"
                break
        if len(buffer) >= FLUSH_EVERY:
            store.append_rows(buffer, data_root, ENDPOINT)
            buffer = []
    if buffer:
        store.append_rows(buffer, data_root, ENDPOINT)
    log(f"details: {summary.status}, fetched {summary.fetched}, failed {summary.failed}")
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fetch a sample of tender detail pages")
    ap.add_argument("--data-root", default="data")
    ap.add_argument("--n", type=int, default=3000)
    ap.add_argument("--budget-min", type=float, default=30)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--interval", type=float, default=1.0)
    a = ap.parse_args(argv)
    root = Path(a.data_root)
    tenders = store.load_all(root, "tenders")
    if tenders.is_empty():
        print("no tenders yet")
        return 0
    done = store.known_ids(root, ENDPOINT)
    ids = pick_ids(tenders["tender_id"].cast(str).to_list(), done, a.n, a.seed)
    summary = fetch(EgpSession(min_interval=a.interval), ids, root, a.budget_min * 60)
    return 0 if summary.status != "aborted" else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Run tests, then one local sample run**

`uv run pytest tests/test_details.py -q` then `uv run python -m bidefy.crawler.details --n 2500 --budget-min 25` (about 1,500 to 2,500 detail pages at one per second). Commit code and data: `Add detail-page sampler and first training sample`.

---

### Task 2: Category taxonomy and weak labels

**Files:**
- Create: `bidefy/models/__init__.py`, `bidefy/models/categories.py`, `tests/test_categories.py`

- [ ] **Step 1: Tests**

```python
from bidefy.models.categories import CATEGORIES, label_from_tags, label_from_title


def test_categories_are_stable_slugs():
    assert len(CATEGORIES) == 15 and all(c == c.lower() and " " not in c for c in CATEGORIES)


def test_tags_map_to_categories():
    assert label_from_tags(["Computer equipment and supplies", "Software", "Servers"]) == "it_equipment"
    assert label_from_tags(["Construction work for highways, roads", "Road-repair works"]) == "roads_bridges"
    assert label_from_tags(["Pharmaceutical products", "Medical equipments"]) == "medical"
    assert label_from_tags(["Office and computing machinery", "Stationery"]) in ("office_supplies", "it_equipment")


def test_ambiguous_or_unknown_returns_none():
    assert label_from_tags([]) is None
    assert label_from_tags(["Zebra breeding services"]) is None


def test_title_fallback_is_keyword_based():
    assert label_from_title("Construction of RCC bridge over Kaliganga river") == "roads_bridges"
    assert label_from_title("Procurement of furniture for Taxes Zone") == "furniture"
    assert label_from_title("Something entirely unrelated") is None
```

- [ ] **Step 2: Module.** Fifteen categories: `roads_bridges, buildings_civil, water_sanitation, electrical_power, it_equipment, office_supplies, furniture, medical, vehicles_transport, food_catering, textiles_uniforms, printing_media, security_cleaning_services, consultancy, agriculture_environment`. Each has a list of lowercase keyword stems matched against the joined tag text; `label_from_tags` scores categories by matched keyword count, returns the top one when it has at least two hits or is the only category with a hit, else None. `label_from_title` uses a shorter keyword list per category and needs one hit with no tie. Commit: `Add category taxonomy and weak labels`.

---

### Task 3: Classifier, metrics, apply in build, nightly retrain

**Files:**
- Create: `bidefy/models/classifier.py`, `tests/test_classifier.py`
- Modify: `bidefy/normalize/build.py`, `bidefy/export/d1.py`, `.github/workflows/crawl.yml`, `pyproject.toml` (joblib)

- [ ] **Step 1: Tests** cover: training on a synthetic labelled frame of 300 titles across 5 categories reaches accuracy above 0.9 on the acted-on subset, writes metrics with keys `accuracy_acted, deferral_rate, coverage, macro_f1, n_train, n_test, threshold, trained_at`; `apply` returns `("other", 0.0)` style deferral (`category = ""`) below threshold; model round-trips through joblib.

- [ ] **Step 2: Module.** `train(data_root, models_dir, threshold=0.55, seed=0)`: builds labels from `data/raw/details` via `label_from_tags` (falls back to `label_from_title` when tags give None, and records the label source), joins titles from clean tenders, stratified 80/20 split, pipeline `FeatureUnion(word 1-2 gram TF-IDF, char_wb 3-5 gram TF-IDF) -> LogisticRegression(C=4, max_iter=2000, class_weight="balanced")`, calibrates nothing beyond the softmax probabilities but reports metrics only on predictions with probability at or above the threshold, plus the deferral rate. Saves `models/category.joblib` and `models/metrics.json` as `{"category_classifier": {...}}`. `apply(titles, model) -> list[tuple[str, float]]` returns `("", p)` when deferred. CLI `train` and `apply --check`.

- [ ] **Step 3: Integrate.** In `build.py`, after writing tenders, if `models/category.joblib` exists, add `category` and `category_confidence` columns and rewrite `clean/tenders.parquet`. In `d1.py` add both columns to `TABLES["tenders"]`. In the workflow add `uv run python -m bidefy.models.classifier train` after "Build clean tables" and then re-run build so the new model applies, and `git add models`. Commit: `Category classifier with deferral, applied nightly`.

---

### Task 4: D1 migration, category in the API

**Files:**
- Create: `worker/migrations/0001_category_sent.sql`
- Modify: `worker/src/query.ts`, `worker/src/index.ts`, `worker/test/query.test.ts`, `worker/package.json`

- [ ] **Step 1: Migration**

```sql
ALTER TABLE tenders ADD COLUMN category TEXT;
ALTER TABLE tenders ADD COLUMN category_confidence REAL;
CREATE INDEX IF NOT EXISTS idx_tenders_category ON tenders(category);
CREATE TABLE IF NOT EXISTS sent (
  subscription_id TEXT NOT NULL, tender_id TEXT NOT NULL, sent_at TEXT NOT NULL,
  PRIMARY KEY (subscription_id, tender_id)
);
```
Apply with `npx wrangler d1 execute bidefy --remote --file migrations/0001_category_sent.sql --yes` (ALTER fails if re-run; that is fine, it runs once). Add script `migrate:remote`.

- [ ] **Step 2: Query and routes.** `TenderFilters` gains `category`; `parseTenderFilters` reads it; `tenderListQuery` adds `category = ?`; the list SELECT and `/api/v1/filters` return categories with counts (`SELECT category AS v, COUNT(*) AS n FROM tenders WHERE category != '' AND category IS NOT NULL GROUP BY category ORDER BY n DESC`). Tests: filter present in SQL and params; omitted when empty. Load the new columns: `uv run python -m bidefy.export.d1 --max-rows 45000` after resetting the tenders watermark to "" in `checkpoints/d1_load.json` so every recent tender is rewritten with its category. Commit: `Category in D1 and the API`.

---

### Task 5: Alert matcher and push sender

**Files:**
- Create: `worker/src/alerts.ts`, `worker/test/alerts.test.ts`
- Modify: `worker/src/index.ts`, `worker/src/subscriptions.ts` (category filter key), `worker/wrangler.jsonc` (ADMIN_TOKEN as a secret, not a var)

- [ ] **Step 1: Tests** (`worker/test/alerts.test.ts`)

```ts
import { describe, expect, it } from "vitest";
import { matchFilters, notificationFor } from "../src/alerts";

const t = { tender_id: "1", title: "Purchase of Dot Matrix Printer Ribbon", ministry: "Ministry of Energy", status: "Live", category: "it_equipment", procuring_entity: "Kushtia PBS", closing_at: "2026-09-28T13:00" };

describe("matchFilters", () => {
  it("matches keyword case-insensitively, ministry and category exactly", () => {
    expect(matchFilters(t, [{ q: "printer" }])).toBe(true);
    expect(matchFilters(t, [{ q: "PRINTER", ministry: "Ministry of Energy" }])).toBe(true);
    expect(matchFilters(t, [{ q: "printer", ministry: "Ministry of Finance" }])).toBe(false);
    expect(matchFilters(t, [{ category: "it_equipment" }])).toBe(true);
    expect(matchFilters(t, [{ category: "medical" }, { q: "ribbon" }])).toBe(true);   // any filter row matches
    expect(matchFilters(t, [{ status: "Cancelled" }])).toBe(false);
  });
  it("an empty filter row never matches everything", () => {
    expect(matchFilters(t, [{}])).toBe(false);
  });
});

describe("notificationFor", () => {
  it("builds a compact payload with the tender url", () => {
    const n = notificationFor(t, "https://bidefy.vercel.app");
    expect(n.title.length).toBeLessThanOrEqual(80);
    expect(n.body).toContain("Kushtia PBS");
    expect(n.url).toBe("https://bidefy.vercel.app/t/1");
    expect(n.tag).toBe("tender-1");
  });
});
```

- [ ] **Step 2: Module.** `matchFilters(tender, filters)`: true when any filter row has at least one key and every key in that row matches (q substring of title, case-insensitive; ministry, status, category equality). `notificationFor(tender, siteBase)` returns `{ title, body, url, tag }`. `runAlerts(env, { dry, siteBase })`: reads `meta.alerts_watermark` (fetched_at); selects tenders with `fetched_at > watermark AND status = 'Live'` ordered by fetched_at limit 500; loads all subscriptions; for each pair that matches and has no `sent` row, sends push through `buildPushPayload` from `@block65/webcrypto-web-push` with the VAPID keys, records `sent`, updates `last_sent_at`; on 404 or 410 deletes the subscription; caps sends per subscription per run at 20; advances the watermark to the newest fetched_at processed; returns `{ candidates, matched, sent, pruned, dry }`. In dry mode nothing is sent or recorded. Install: `npm i @block65/webcrypto-web-push`.

- [ ] **Step 3: Routes.** `scheduled` calls `runAlerts(env, { dry: false, siteBase: env.SITE_BASE })`. Add `POST /api/v1/admin/run-alerts?dry=1` guarded by header `x-admin-token` equal to `env.ADMIN_TOKEN` (secret set with `wrangler secret put ADMIN_TOKEN` from a locally generated random string saved to `.dev.vars`). Add `SITE_BASE: "https://bidefy.vercel.app"` to vars. Extend `validateSubscription` FILTER_KEYS with `category`. Deploy, then call the dry-run endpoint and record the counts. Commit: `Hourly alert matcher and web push sender`.

---

### Task 6: Category on the site, launch

**Files:**
- Modify: `web/lib/api.ts`, `web/app/components/TenderCard.tsx`, `Filters.tsx`, `AlertsForm.tsx`, `web/app/page.tsx`, `web/app/alerts/page.tsx`, `web/app/t/[id]/page.tsx`
- Create: `docs/product/02-system.md`
- Modify: `status.yaml`, `README.md`

- [ ] **Step 1: Site.** Category chip on cards and the tender page (human label from a `CATEGORY_LABELS` map in `web/lib/categories.ts`), category select in Filters and AlertsForm (options from `/api/v1/filters`), `category` passed through `buildQuery`. Build, deploy with `npx vercel --prod --yes`.

- [ ] **Step 2: Docs and status.** `docs/product/02-system.md`: the pipeline in one page (crawl, compact, resolve, classify, load, serve, alert), the accuracy table copied from `models/metrics.json`, the deferral principle, the daily write budget. `status.yaml`: w4 tasks done except the launch post, add `w4-detail-sample` done. README: "Status: v0.1 public" line. Tag `v0.1.0` on main. Commit: `Launch v0.1: categories on the site, system doc`, push.

---

## Self-review against the spec

- 5.3 models: classifier with metrics and deferral (Task 3). Award model and anomaly flags are weeks 5 and 6.
- 5.5 cron: hourly matcher and sender with 410 pruning (Task 5).
- 8 pricing page is week 7; launch is v0.1 with the free tier only.
- Names consistent: `pick_ids`, `fetch`, `label_from_tags`, `label_from_title`, `train`, `apply`, `matchFilters`, `notificationFor`, `runAlerts`.
