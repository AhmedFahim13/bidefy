# Bidefy Week 6: Concentration Flags, Procurement Primer, Site Proxy and Paging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task inline. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every bidder and procuring entity carries concentration flags with the numbers behind them; the site explains every procurement term it uses and links to a primer the owner can read before an interview; browser calls go through the Vercel site so networks that block workers.dev still work; the tender list gets a page jump and a larger page size.

**Architecture:** `bidefy/models/flags.py` computes, from clean contracts, per entity: top-bidder share, top-three share and a Herfindahl index over the last twelve months plus the count of distinct winners; per bidder: share of awards at its top entity, number of entities, and awards outside the predicted band using the award model's residual bands. Flags are JSON aggregates joined into the existing bidder and entity rows (no schema change beyond a `flags` column via migration 0004). The Worker returns them. Next.js route handlers under `web/app/api/[...path]/route.ts` forward GET, POST and DELETE to the Worker, and the client code targets the site origin. A glossary module drives tooltips and a `/learn` page; `docs/product/04-primer.md` is the long form.

**Tech Stack:** Python, polars; Hono; Next.js route handlers.

---

### Task 1: Recovery and hygiene
- [ ] Re-dispatch the tender backfill (280 minutes) with the fixed workflow. Confirm the bot commit lands.
- [ ] Add `.github/workflows/deploy-worker.yml`: on push to `worker/**`, `npm ci` and `wrangler deploy` with the two Cloudflare secrets, `continue-on-error: false`. If the token lacks Workers edit rights the run fails visibly and the owner extends the token.

### Task 2: Flags
- [ ] `tests/test_flags.py`: synthetic contracts where one entity awards 8 of 10 contracts to one bidder; assert `entity_flags` gives top share 0.8, HHI above 0.6, distinct winners 3; a bidder with all awards at one entity gets `top_entity_share` 1.0; residual flag counts awards where value is outside the band by more than the band itself.
- [ ] `bidefy/models/flags.py`: `entity_flags(contracts, since)` and `bidder_flags(contracts, predictions_for_awards, since)` returning DataFrames with a `flags` JSON column (`{"top_share": 0.8, "top3_share": 1.0, "hhi": 0.66, "winners": 3, "awards_12m": 10, "notes": ["One bidder won 80 percent of 10 awards in the last 12 months"]}`); band residuals computed by applying the award bundle to historical awards. `build.py` joins both. `d1.py` adds `flags` to both tables. Migration `0004_flags.sql` adds the columns.
- [ ] Worker: bidder and entity endpoints return `flags` parsed; site profile pages show a "Patterns" card listing the notes with the numbers, and the sentence "A pattern is not a verdict."

### Task 3: Site proxy and paging
- [ ] `web/app/api/[...path]/route.ts`: forwards to `API_BASE`, preserving method, query, JSON body and the `x-admin-token` header only when present; strips hop headers; 15 second timeout; returns the Worker's status and body. Client code (`push.ts`, `AccessForm.tsx`, `AlertsForm.tsx`) uses `""` as base so calls hit `/api/v1/...` on the site origin.
- [ ] Pagination: a form with a number input to jump to a page, page size selector 25 / 50 / 100 carried in the query string, and the total hint "Page N". `parseTenderFilters` already caps size at 100.

### Task 4: Primer and glossary
- [ ] `web/lib/glossary.ts`: term to one-sentence definition for every abbreviation and field shown (OTM, LTM, RFQ, DPM, NCT, ICT, OSTETM, TSTM, procuring entity, ministry and organisation, reference number, tender security, document price, publishing and closing, corrigendum, re-tender, Being processed, Contract Awarded, crore and lakh, e-GP, BPPA, IFT, NOA).
- [ ] Tooltips: method and type abbreviations on cards and the tender page render with `title` text from the glossary and a dotted underline; the tender page shows a "What these terms mean" link to `/learn#term`.
- [ ] `/learn` page: how a tender goes from notice to award in Bangladesh, what Bidefy adds at each step, the glossary as a definition list with anchors.
- [ ] `docs/product/04-primer.md`: the same in long form for the owner, including how to read a tender notice, how procurement methods differ, what the value bands mean, and the five questions a bidder asks.

### Task 5: Close
- [ ] Build, tests, deploy site, update `status.yaml` (w6 done, plus owner tasks: `wrangler login`, extend the API token to Workers edit if the deploy workflow fails, read the primer), push.
