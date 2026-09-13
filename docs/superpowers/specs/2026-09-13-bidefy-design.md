# Bidefy design

Date: 2026-09-13. Status: approved by Fahim Ahmed in session, before implementation.

## 1. What it is

Bidefy is tender intelligence for Bangladesh's public procurement portal (e-GP, eprocure.gov.bd). It indexes every public tender notice and contract award, resolves the messy names of bidders and procuring entities into stable identities, predicts the likely award value of a live tender, flags unusual award patterns, and sends web push alerts to subscribers when a tender matching their filters appears.

Version 1 is a public website installable as a PWA, free to use, with a pricing page for a paid tier that is not yet purchasable. There is no WhatsApp, no Telegram, and no payment in v1.

## 2. Why it exists

Incumbents (BDTender, AllTender) sell daily notice alerts filtered by category, district and organisation for roughly 1,050 taka a month. None of them use the 877,000 public contract awards, so none can say who wins what, at what value, against whom. That layer is empty. Bidefy sells that layer and never competes on alerts.

The build is also the portfolio piece for a product-management application to Advanced AI Lab Limited, Dhaka. Every decision here must survive the question "what did you choose not to build, and why".

## 3. Constraints

- Production cost is zero taka. Every component runs on a free tier.
- No component depends on another person, an API approval, or a client to be built. Selling needs people; building does not.
- The crawler must never disrupt the portal: one request per second, one session, checkpointed, stops after three consecutive failures.
- Only public, login-free pages are read. Derived intelligence is published; raw notices are not mirrored wholesale.
- No Meta products. Web push is the only alert channel.
- Ship in eight weeks, with a public launch at the end of week four.

## 4. Verified facts about the source

Verified 2026-09-13 from Dhaka and from a GitHub Actions runner.

| Fact | Value |
|---|---|
| Tender index endpoint | POST `/TenderDetailsServlet`, params `funName=AllTenders, keyword, pageNo, size, homeWSearch=homeWSearch, approve=false, h=t` |
| Contract index endpoint | POST `/SearchNoaServlet`, params `keyword, pageNo, size` |
| Session | A GET of `/resources/common/StdTenderSearch.jsp?h=t` sets `JSESSIONID`; expires after 30 idle minutes |
| Page size | 200 rows honoured. Tenders: 3,129 pages (~625,800 notices). Contracts: 4,386 pages (~877,200 awards) |
| Detail page | POST `/resources/common/ViewTender.jsp` with `id` and `h=t`. Contains category tags, tender security amount, dates, procuring entity contact. No official cost estimate |
| Latency | Under one second per page from Dhaka; 4 to 35 seconds observed from a US runner |
| Blocking | None observed. No robots.txt rules. Terms forbid disrupting the service, nothing about automated reads |
| Not available | Losing bids, bidder counts, official cost estimates |

The tender security amount is set as a fixed share of the estimate by each procuring entity, so it serves as the cost proxy.

## 5. Architecture

Pipeline in GitHub Actions, product on Cloudflare. Five units.

### 5.1 crawler (Python, stdlib only)

- Establishes a session, pages newest-first at 200 rows per request.
- Writes a checkpoint after every page: endpoint, last page number, last seen ID, timestamp.
- Full backfill runs across several nightly jobs using the checkpoint, because a US runner may need more than the six-hour job cap.
- Daily delta pages from page one until it meets an ID already stored, then stops.
- Detail pages are fetched only for live tenders and for a modelling sample of closed ones, queued and rate-limited the same way.
- Output: Parquet files under `data/raw/`, committed to the repo. Size estimate under 100 MB for the full index.
- Failure: any non-200, a zero-row page, or a session-expired body counts as a failure. Three in a row aborts the run with the checkpoint intact.

### 5.2 normalize (Python, Polars, DuckDB)

- Parses raw rows into four tables: `tenders`, `contracts`, `procuring_entities`, `bidders`.
- Entity resolution for bidders: normalise case, punctuation, "M/S", "M/S.", "Messrs", whitespace and common transliteration variants; block on the first token and district; score remaining pairs with character n-gram TF-IDF cosine; merge above 0.92, send 0.80 to 0.92 to `review/pairs.csv` for a human decision, leave the rest apart.
- Same procedure for procuring entities, which are cleaner.
- Output: `data/clean/` Parquet with stable integer IDs.

### 5.3 models (Python, scikit-learn, LightGBM)

- Category classifier: title and brief description to the portal's own top-level category tags harvested from detail pages. Supervised, no hand labelling. Reports accuracy on a held-out set and a deferral rate below a confidence threshold.
- Award-value model: LightGBM regression on log award value from resolved procuring entity, ministry, method, category, district, month, and security amount. Reports median absolute percentage error against a naive baseline (median award for that entity and category). Produces a prediction interval, not a point.
- Anomaly flags, computed nightly, never called fraud: winner share of awards per procuring entity and category over twelve months; awards outside the predicted interval; entities winning across unrelated categories. Each flag carries the number behind it.
- Every training run writes `models/metrics.json`. A regression past a stated threshold fails the job and keeps the previous model.

### 5.4 export and load

- D1 free tier permits 100,000 row writes a day. This is the binding constraint.
- D1 holds: live and recently closed tenders (about 12 months), the last 12 months of contract awards loaded across three nights, resolved bidders and procuring entities, per-tender predictions, and push subscriptions.
- Deep history stays in Parquet. Aggregates (entity win histories, category price bands, monthly volumes) are precomputed in Actions and shipped to the Worker as static JSON assets.
- Load runs as the last step of the nightly pipeline through `wrangler d1 execute` in batches, idempotent by ID.

### 5.5 worker (TypeScript, Hono, Cloudflare Workers, D1)

Pages:
- `/` live tenders with filters for category, district, ministry, value band, closing date.
- `/t/:id` one tender: details, predicted award band with the interval, similar past awards, likely bidders from history.
- `/e/:id` bidder profile: awards, entities, categories, districts, share flags.
- `/pe/:id` procuring entity profile: volume, repeat winners, concentration.
- `/alerts` subscribe with up to three filters on the free tier; stores the push subscription.
- `/pricing` free, pro, enterprise. Pro shows a request-access form.
- `/api/v1/tenders`, `/api/v1/entities/:id` read-only JSON, rate-limited per IP.

Cron, hourly: match tenders loaded since the last run against subscriptions, send web push with VAPID, prune any subscription that returns 410.

PWA: manifest, service worker, push handler, installable on Android; iOS requires add to home screen.

Stale banner: if the newest tender is older than 36 hours, every page shows it.

## 6. Command centre

Source of truth is `status.yaml` at the repo root: phases, tasks, owner (`claude` or `fahim`), state (`todo`, `doing`, `done`), weight, and an optional note. A build script renders two static pages to GitHub Pages on every push:

- `index.html`: percent complete by weight, tasks done, next three steps, tasks owned by Fahim that are not done, last crawl timestamp, current model metrics.
- `doc.html`: the product document in the structure of the Auto document: thesis, market, competition, what defends, system, models, accuracy budget, guardrails, threats, pricing, unit economics, go to market, roadmap, tasks before launch, verdict, sources.

The build reads `status.yaml`, `models/metrics.json`, the crawl checkpoint, and `docs/product/*.md`.

## 7. Testing

- Parsers: pytest against saved HTML fixtures for both list endpoints and the detail page.
- Entity resolution: a labelled set of 200 pairs; precision reported and asserted above 0.95 on merges.
- Models: metrics file on every run; job fails on regression.
- Worker: vitest with the Miniflare environment for route responses and the subscription matcher.
- CI: lint and tests on every push. Nightly pipeline is a separate workflow.

## 8. Pricing, version 1

| Tier | Price | Includes |
|---|---|---|
| Free | 0 | Live tenders, search, three alert filters |
| Pro | 2,500 taka a month, placeholder | Award predictions, bidder and entity profiles, unlimited alerts, CSV export, API key |
| Enterprise | On request | Data licence, custom feeds |

No payment is built. Pro is a request-access form. Taking money requires a bKash merchant account, which is Fahim's task and not in v1.

## 9. Eight-week sequence

| Week | Lands |
|---|---|
| 1 | Crawler with checkpointing, full tender index, fixtures, tests, status.yaml, dashboard build |
| 2 | Contracts index, entity resolution, D1 schema, Worker skeleton |
| 3 | Site pages, PWA, push subscriptions |
| 4 | Category classifier, alert cron. Public launch v0.1 |
| 5 | Award-value model with metrics and interval |
| 6 | Anomaly flags, bidder and entity profiles |
| 7 | Product document, pricing page, polish, dashboard complete |
| 8 | Usage numbers, demo video, outreach |

## 10. Tasks only Fahim can do

1. Create a Cloudflare account and run `wrangler login` once.
2. Decide on a domain (about 1,200 taka a year) or stay on workers.dev.
3. Read the e-GP terms and disclaimer pages once.
4. Review `review/pairs.csv` when the resolver asks.
5. Talk to five people who bid on tenders about the Pro price.
6. Record a two-minute demo video.
7. Write the launch post.
8. Message the four Advanced AI Lab product managers with the site and dashboard links.
9. Later: bKash merchant account for the Pro tier.

## 11. Out of scope for v1

WhatsApp or Telegram alerts. Payments. Losing-bid data, which the portal does not publish. Bid document parsing. A mobile app store listing. Any claim of fraud; flags describe patterns with numbers only.

## 12. Open risks

- A US runner may be slow or become blocked. Mitigation: checkpointed multi-night backfill; fallback is running the crawler from Fahim's laptop with the same code.
- The security-to-estimate ratio may vary by entity. Mitigation: learn it per entity and report the interval, not a point.
- Entity resolution errors could attach awards to the wrong firm. Mitigation: conservative thresholds, a review queue, and profiles that show the raw names merged.
- Name collision with "Bidify", an auction app. Different market; monitor.
