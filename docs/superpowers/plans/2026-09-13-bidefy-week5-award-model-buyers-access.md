# Bidefy Week 5: Award-Value Model, Buyer Profiles and Request Access Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task inline. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every live tender shows a predicted award-value band with a stated coverage and a deferral rule, learned from the indexed contract awards; five buyer profiles derived from real award data replace the interviews that could not happen; a request-access form collects real pricing signals into D1.

**Architecture:** A LightGBM quantile model (10th, 50th and 90th percentiles) on log award value, with categorical features for procuring entity, ministry, method, district and title category, and a month feature. Deferral when the band is wider than a ratio or the entity has too little history. A naive baseline (median by entity and category) is reported beside it. Predictions for live tenders go to a `predictions` table in D1 and the Worker returns them with the tender. A script writes `docs/product/03-buyers.md` from the awards table by rules, never by invention. The Worker gains `POST /api/v1/access-requests` with a honeypot and an hourly per-IP cap, and the site gains `/access`.

**Tech Stack:** Python, LightGBM, polars; Hono, D1; Next.js.

Spec: sections 5.3, 5.5, 8 of `docs/superpowers/specs/2026-09-13-bidefy-design.md`. Owner decision: the five-bidder interviews are replaced by data-derived profiles plus a request-access form.

---

## File structure

```
bidefy/models/award.py               features(), train(), predict(), CLI train | apply
tests/test_award.py
worker/migrations/0002_predictions_access.sql
worker/src/access.ts                 validateAccessRequest()
worker/src/index.ts                  predictions on tender, access-requests POST, admin list
worker/src/query.ts                  predictionQuery
worker/test/access.test.ts
web/app/access/page.tsx, web/app/components/AccessForm.tsx
web/app/t/[id]/page.tsx              predicted band card
tools/buyer_profiles.py              writes docs/product/03-buyers.md
bidefy/export/d1.py                  predictions table
.github/workflows/crawl.yml          award model train and apply step
```

Conventions unchanged. Data: the contracts backfill runs locally for an hour at the start of this plan, its checkpoint is pushed, and the queued Actions run resumes from it.

---

### Task 1: Contracts data in, clean tables and D1

- [ ] Run `uv run python -m bidefy.crawler.run --endpoint contracts --mode backfill --budget-min 60` (started at plan time). When it ends: `uv run python -m bidefy.normalize.build`, then `uv run python -m bidefy.export.d1 --max-rows 40000` (D1 budget for today), then `git add data checkpoints review && git commit -m "Contracts backfill, first hour" && git pull --rebase && git push`. Expected: contracts in the hundreds of thousands, bidders in the tens of thousands, review pairs in the low thousands.

---

### Task 2: Award-value model

**Files:** `bidefy/models/award.py`, `tests/test_award.py`, `pyproject.toml` (lightgbm)

- [ ] **Tests** (`tests/test_award.py`): synthetic awards where value depends on entity and category with noise; `train` returns metrics with keys `mape_acted, mape_baseline, coverage_80, deferral_rate, n_train, n_test, trained_at`; coverage between 0.6 and 0.95; `mape_acted` at most `mape_baseline`; `predict` on rows returns q10 <= q50 <= q90 and a `deferred` flag true for an unseen entity with an unknown category; model round-trips through joblib.

- [ ] **Module.** Features: `pe_id, ministry, method, district, category` as pandas categoricals, `month` (1 to 12), `year_offset`, `title_len`. Target `log1p(value_crore * 100)` (lakh). Three LightGBM regressors with `objective="quantile"` at alpha 0.1, 0.5, 0.9, 400 trees, learning rate 0.05, `min_child_samples=20`. Split by `signed_on` (last 20 percent by date is the test set, so the metric is honest about time). Baseline: median lakh by (pe_id, category), falling back to category, then global. Deferral: `q90/q10 > 12` or entity with fewer than 3 awards and category empty. Metrics computed on the non-deferred test rows. `apply(data_root, models_dir)`: predicts for clean tenders with `status == "Live"`, joins category and pe history, writes `data/clean/predictions.parquet` with `tender_id, q10_lakh, q50_lakh, q90_lakh, deferred, model_version`. CLI `train` and `apply`. Metrics merged into `models/metrics.json` under `award_value_model`. Model file gitignored like the classifier.

- [ ] Workflow: add `uv run python -m bidefy.models.award train && uv run python -m bidefy.models.award apply` after the classifier step. Commit: `Award-value quantile model with deferral and baseline`.

---

### Task 3: Predictions in D1, API and the tender page

- [ ] Migration `0002_predictions_access.sql`: `predictions(tender_id PK, q10_lakh REAL, q50_lakh REAL, q90_lakh REAL, deferred INTEGER, model_version TEXT)`, `access_requests(id PK, created_at, name, organisation, role, bids_on, value_band, contact, note, ip_hash)`. Add `predictions` to `TABLES` in `d1.py` (loaded fully each night; a few thousand rows). Worker: `predictionQuery(id)`, `/api/v1/tenders/:id` returns `prediction` (null when none). Site: the "Predicted award band" card shows "q10 to q90 lakh, most likely q50" with the coverage sentence, or the deferral sentence with the reason. Commit: `Predicted award band on tender pages`.

---

### Task 4: Buyer profiles from the awards table

- [ ] `tools/buyer_profiles.py` selects five real entities by rules from `data/clean`: the most frequent winner at a single procuring entity (specialist), a bidder with awards under four or more ministries (generalist), the top bidder by total value in the last year (infrastructure), a bidder whose first award is within the last 90 days (newcomer), and a district-concentrated bidder with the highest share of one district (regional). For each it writes name, counts, values, entities, categories, and what Bidefy would show them, into `docs/product/03-buyers.md` with the sentence "These profiles are computed from public award data, not interviews." Commit: `Five data-derived buyer profiles`.

---

### Task 5: Request access

- [ ] Worker `access.ts`: `validateAccessRequest(body)` requires `name` (2 to 80), `organisation` (2 to 120), `bids_on` (2 to 200), `value_band` in a fixed set, optional `role`, `contact` (email or phone, 5 to 120), `note` (up to 500), and an empty honeypot field `website`. `POST /api/v1/access-requests` hashes the IP with SHA-256, rejects more than 5 per IP per hour, inserts, returns 201. `GET /api/v1/admin/access-requests` behind the admin token lists the latest 200. Tests for the validator. Site `/access`: a short page (what Pro will include, the placeholder price of 2,500 taka a month, "no payment yet") and `AccessForm` client component posting to the Worker, with a success state. Links from the home hero and the alerts page. Commit: `Request-access form and admin listing`. Deploy Worker and site, update `status.yaml`, push.

---

## Self-review against the spec

- 5.3 award model: quantile interval, deferral, baseline comparison, time-based split, metrics file (Task 2).
- 5.5 tender page prediction (Task 3). 8 pricing page stays week 7; the access form is its precursor.
- Buyer profiles replace interviews per the owner's decision and are labelled as such (Task 4).
- Names: `train`, `apply`, `predict`, `predictionQuery`, `validateAccessRequest`.
