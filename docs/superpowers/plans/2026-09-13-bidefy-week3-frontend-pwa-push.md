# Bidefy Week 3: Frontend on Vercel, PWA and Push Subscriptions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task inline. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A public Next.js site on Vercel that lists live tenders with filters, shows a tender with similar past awards, shows bidder and procuring-entity profiles, installs as a PWA, and lets a visitor subscribe to web push alerts with up to three filters, stored in D1 through the Worker.

**Architecture:** `web/` is a Next.js App Router project (TypeScript, Tailwind v4) that renders on the server by fetching the Worker API with short revalidation. The Worker gains a subscriptions API, a filters endpoint, a stats endpoint and a VAPID public key endpoint; the VAPID private key is a Worker secret used by the week 4 sender. The service worker lives at the Vercel origin and posts subscriptions to the Worker. No database access from Vercel.

**Tech Stack:** Next.js 15, React 19, TypeScript, Tailwind CSS v4, vitest; Hono on Cloudflare Workers with D1; web-push for key generation; Vercel CLI 55 (logged in as ahmedfahim13); Pillow for icon generation.

Spec: `docs/superpowers/specs/2026-09-13-bidefy-design.md`, section 5.5. Deviation recorded by the owner: the frontend is on Vercel rather than served by the Worker.

**Token economy note:** page component bodies (Tasks 3 and 4) are specified by route, data source, props and acceptance checks rather than reproduced in full here; they are written once during execution. Tests, Worker code and shared libraries are complete in this document.

---

## File structure

```
worker/src/subscriptions.ts        validateSubscription(), newSubscriptionId()
worker/src/index.ts                new routes: filters, stats, vapid key, subscriptions POST and DELETE
worker/test/subscriptions.test.ts
worker/wrangler.jsonc              vars.VAPID_PUBLIC_KEY, vars.VAPID_SUBJECT
worker/.dev.vars                   VAPID_PRIVATE_KEY for local dev (gitignored)
web/package.json, tsconfig.json, next.config.ts, postcss.config.mjs, vitest.config.ts
web/app/globals.css                Tailwind v4 @theme tokens
web/app/layout.tsx                 shell: header, nav, stale banner, footer, PWA meta
web/app/page.tsx                   live tenders with filters and paging
web/app/t/[id]/page.tsx            tender detail with similar awards
web/app/e/[id]/page.tsx            bidder profile
web/app/pe/[id]/page.tsx           procuring entity profile
web/app/alerts/page.tsx            alerts page (server) + AlertsForm client component
web/app/components/*.tsx           TenderCard, Filters, Pagination, StaleBanner, AlertsForm, InstallHint, Sw
web/lib/api.ts                     typed fetchers against the Worker
web/lib/format.ts                  formatDate, formatCrore, isStale, buildQuery
web/lib/push.ts                    urlBase64ToUint8Array, subscribe/unsubscribe helpers
web/lib/__tests__/format.test.ts
web/public/manifest.webmanifest, sw.js, icon-192.png, icon-512.png, icon.svg
tools/make_icons.py                renders the PNG icons
```

Conventions unchanged: LF, no em dashes, commit per task with the trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`, pull before push. Never print the VAPID private key.

---

### Task 1: Worker subscriptions, filters, stats and VAPID key

**Files:**
- Create: `worker/src/subscriptions.ts`, `worker/test/subscriptions.test.ts`
- Modify: `worker/src/index.ts`, `worker/wrangler.jsonc`, `.gitignore`

- [ ] **Step 1: Write the failing tests**

`worker/test/subscriptions.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import { validateSubscription, newSubscriptionId } from "../src/subscriptions";

const good = {
  subscription: { endpoint: "https://push.example/abc", keys: { p256dh: "BPk", auth: "a1" } },
  filters: [{ q: "printer" }, { ministry: "Ministry of Finance" }],
};

describe("validateSubscription", () => {
  it("accepts a well formed body and normalises filters", () => {
    const r = validateSubscription(good);
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.value.endpoint).toBe("https://push.example/abc");
      expect(r.value.filters).toEqual([{ q: "printer" }, { ministry: "Ministry of Finance" }]);
    }
  });
  it("rejects non-https endpoints, missing keys, and more than three filters", () => {
    expect(validateSubscription({ ...good, subscription: { ...good.subscription, endpoint: "http://x" } }).ok).toBe(false);
    expect(validateSubscription({ ...good, subscription: { endpoint: "https://x", keys: {} } }).ok).toBe(false);
    expect(validateSubscription({ ...good, filters: [{ q: "a" }, { q: "b" }, { q: "c" }, { q: "d" }] }).ok).toBe(false);
  });
  it("drops unknown filter keys and empty filters, requires at least one", () => {
    const r = validateSubscription({ ...good, filters: [{ q: "  ", bogus: 1 }, { status: "Live", extra: "x" }] });
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.value.filters).toEqual([{ status: "Live" }]);
    expect(validateSubscription({ ...good, filters: [] }).ok).toBe(false);
    expect(validateSubscription({ ...good, filters: [{ q: "" }] }).ok).toBe(false);
  });
  it("truncates long strings", () => {
    const r = validateSubscription({ ...good, filters: [{ q: "x".repeat(500) }] });
    expect(r.ok && r.value.filters[0].q?.length).toBe(120);
  });
});

describe("newSubscriptionId", () => {
  it("is 32 hex chars and unique", () => {
    const a = newSubscriptionId(), b = newSubscriptionId();
    expect(a).toMatch(/^[0-9a-f]{32}$/);
    expect(a).not.toBe(b);
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd C:/Users/hp/Auto/egp-intel/worker && npx vitest run`
Expected: FAIL, cannot resolve `../src/subscriptions`.

- [ ] **Step 3: Write subscriptions.ts**

```ts
export type Filter = { q?: string; ministry?: string; status?: string; district?: string };
export type ValidSubscription = { endpoint: string; keys: { p256dh: string; auth: string }; filters: Filter[] };
export type Result = { ok: true; value: ValidSubscription } | { ok: false; error: string };

const MAX_FILTERS = 3;
const MAX_LEN = 120;
const FILTER_KEYS: (keyof Filter)[] = ["q", "ministry", "status", "district"];

function str(v: unknown): string {
  return typeof v === "string" ? v.trim().slice(0, MAX_LEN) : "";
}

export function validateSubscription(body: unknown): Result {
  const b = (body ?? {}) as Record<string, unknown>;
  const sub = (b.subscription ?? {}) as Record<string, unknown>;
  const endpoint = typeof sub.endpoint === "string" ? sub.endpoint : "";
  if (!endpoint.startsWith("https://") || endpoint.length > 2048) return { ok: false, error: "bad endpoint" };
  const keys = (sub.keys ?? {}) as Record<string, unknown>;
  const p256dh = typeof keys.p256dh === "string" ? keys.p256dh : "";
  const auth = typeof keys.auth === "string" ? keys.auth : "";
  if (!p256dh || !auth) return { ok: false, error: "missing keys" };
  const raw = Array.isArray(b.filters) ? b.filters : [];
  if (raw.length > MAX_FILTERS) return { ok: false, error: `at most ${MAX_FILTERS} filters` };
  const filters: Filter[] = [];
  for (const f of raw) {
    const o = (f ?? {}) as Record<string, unknown>;
    const clean: Filter = {};
    for (const k of FILTER_KEYS) {
      const v = str(o[k]);
      if (v) clean[k] = v;
    }
    if (Object.keys(clean).length) filters.push(clean);
  }
  if (!filters.length) return { ok: false, error: "at least one filter" };
  return { ok: true, value: { endpoint, keys: { p256dh, auth }, filters } };
}

export function newSubscriptionId(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (x) => x.toString(16).padStart(2, "0")).join("");
}
```

- [ ] **Step 4: Add routes to index.ts**

Replace the CORS line with `app.use("/api/*", cors({ origin: "*", allowMethods: ["GET", "POST", "DELETE", "OPTIONS"] }));`, extend `Bindings` with `VAPID_PUBLIC_KEY: string; VAPID_SUBJECT: string;`, import `newSubscriptionId, validateSubscription` from `./subscriptions`, and add before `export default`:
```ts
app.get("/api/v1/filters", async (c) => {
  const [ministries, districts, statuses] = await c.env.DB.batch([
    c.env.DB.prepare("SELECT ministry AS v, COUNT(*) AS n FROM tenders WHERE ministry != '' GROUP BY ministry ORDER BY n DESC LIMIT 60"),
    c.env.DB.prepare("SELECT district AS v, COUNT(*) AS n FROM contracts WHERE district != '' GROUP BY district ORDER BY n DESC LIMIT 70"),
    c.env.DB.prepare("SELECT status AS v, COUNT(*) AS n FROM tenders WHERE status != '' GROUP BY status ORDER BY n DESC"),
  ]);
  return c.json({ ministries: ministries.results ?? [], districts: districts.results ?? [], statuses: statuses.results ?? [] });
});

app.get("/api/v1/stats", async (c) => {
  const r = await c.env.DB.batch([
    c.env.DB.prepare("SELECT COUNT(*) AS n FROM tenders WHERE status = 'Live'"),
    c.env.DB.prepare("SELECT COUNT(*) AS n FROM contracts"),
    c.env.DB.prepare("SELECT COUNT(*) AS n FROM bidders"),
    c.env.DB.prepare("SELECT MAX(published_at) AS v FROM tenders"),
    c.env.DB.prepare("SELECT MAX(fetched_at) AS v FROM tenders"),
  ]);
  const one = (i: number) => (r[i].results?.[0] as Record<string, unknown> | undefined) ?? {};
  return c.json({ live_tenders: one(0).n ?? 0, contracts: one(1).n ?? 0, bidders: one(2).n ?? 0, newest_published: one(3).v ?? null, last_fetched: one(4).v ?? null });
});

app.get("/api/v1/push/public-key", (c) => c.json({ key: c.env.VAPID_PUBLIC_KEY ?? "" }));

app.post("/api/v1/subscriptions", async (c) => {
  let body: unknown;
  try { body = await c.req.json(); } catch { return c.json({ error: "invalid json" }, 400); }
  const v = validateSubscription(body);
  if (!v.ok) return c.json({ error: v.error }, 400);
  const existing = await c.env.DB.prepare("SELECT id FROM subscriptions WHERE endpoint = ?").bind(v.value.endpoint).first<{ id: string }>();
  const id = existing?.id ?? newSubscriptionId();
  await c.env.DB.prepare(
    "INSERT OR REPLACE INTO subscriptions (id, endpoint, keys_json, filters_json, created_at, last_sent_at) VALUES (?, ?, ?, ?, COALESCE((SELECT created_at FROM subscriptions WHERE id = ?), ?), NULL)",
  ).bind(id, v.value.endpoint, JSON.stringify(v.value.keys), JSON.stringify(v.value.filters), id, new Date().toISOString()).run();
  return c.json({ id, filters: v.value.filters }, existing ? 200 : 201);
});

app.delete("/api/v1/subscriptions/:id", async (c) => {
  const { meta } = await c.env.DB.prepare("DELETE FROM subscriptions WHERE id = ?").bind(c.req.param("id")).run();
  return c.json({ deleted: meta.changes ?? 0 });
});
```

- [ ] **Step 5: Generate VAPID keys without printing the private key**

Run from `worker/`:
```bash
npx --yes web-push generate-vapid-keys --json > .vapid.json
python -c "import json;d=json.load(open('.vapid.json'));open('.dev.vars','w').write('VAPID_PRIVATE_KEY='+d['privateKey']+'\n');print('public:',d['publicKey'])"
python -c "import json;print(json.load(open('.vapid.json'))['privateKey'])" | npx wrangler secret put VAPID_PRIVATE_KEY
rm .vapid.json
```
Expected: the public key printed once; wrangler reports the secret created. Add `worker/.dev.vars` and `worker/.vapid.json` to `.gitignore`. Put the public key and `"VAPID_SUBJECT": "mailto:ahmed.fahim.official.bd@gmail.com"` in `wrangler.jsonc` under `"vars"`.

- [ ] **Step 6: Test, type check, deploy, smoke**

Run: `cd worker && npx vitest run && npx tsc -p tsconfig.json && npx wrangler deploy`
Then: `curl -s https://bidefy.iba-jobs.workers.dev/api/v1/stats; curl -s https://bidefy.iba-jobs.workers.dev/api/v1/push/public-key; curl -s -X POST -H "content-type: application/json" -d '{"subscription":{"endpoint":"https://push.example/t","keys":{"p256dh":"x","auth":"y"}},"filters":[{"q":"printer"}]}' https://bidefy.iba-jobs.workers.dev/api/v1/subscriptions`
Expected: 10 vitest tests pass; stats JSON; a non-empty key; a `{"id":"...","filters":[...]}` reply. Then delete the test row with `curl -s -X DELETE .../api/v1/subscriptions/<id>` and expect `{"deleted":1}`.

- [ ] **Step 7: Commit and push**

```bash
git add worker/src worker/test worker/wrangler.jsonc .gitignore
git commit -m "Worker: subscriptions, filters, stats and VAPID key endpoints"
git pull --rebase && git push
```

---

### Task 2: Web app scaffold, shared libraries and tests

**Files:**
- Create: `web/package.json`, `web/tsconfig.json`, `web/next.config.ts`, `web/postcss.config.mjs`, `web/vitest.config.ts`, `web/app/globals.css`, `web/lib/api.ts`, `web/lib/format.ts`, `web/lib/__tests__/format.test.ts`, `web/.gitignore`

- [ ] **Step 1: Scaffold**

Run from the repo root: `npx --yes create-next-app@latest web --ts --tailwind --app --eslint --no-src-dir --import-alias "@/*" --use-npm --yes`
Expected: `web/` created with Next 15 and Tailwind v4. Then `cd web && npm i -D vitest @vitejs/plugin-react`.

- [ ] **Step 2: Write the failing tests**

`web/lib/__tests__/format.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import { buildQuery, formatCrore, formatDate, isStale, daysLeft } from "../format";

describe("format", () => {
  it("formatDate renders ISO minutes as a short Dhaka style date", () => {
    expect(formatDate("2026-09-13T11:00")).toBe("13 Sep 2026, 11:00");
    expect(formatDate("2026-09-13")).toBe("13 Sep 2026");
    expect(formatDate(null)).toBe("");
  });
  it("formatCrore shows taka in crore or lakh", () => {
    expect(formatCrore(2.433)).toBe("2.43 crore");
    expect(formatCrore(0.079)).toBe("7.9 lakh");
    expect(formatCrore(null)).toBe("");
  });
  it("isStale is true past 36 hours", () => {
    const now = new Date("2026-09-14T00:00:00Z");
    expect(isStale("20260913T070000000000Z", now)).toBe(false);
    expect(isStale("20260912T070000000000Z", now)).toBe(true);
    expect(isStale(null, now)).toBe(true);
  });
  it("daysLeft counts whole days until closing", () => {
    expect(daysLeft("2026-09-28T13:00", new Date("2026-09-13T12:00:00Z"))).toBe(15);
    expect(daysLeft(null, new Date())).toBeNull();
  });
  it("buildQuery drops empties and defaults", () => {
    expect(buildQuery({ q: "printer", status: "Live", ministry: "", page: 1 })).toBe("q=printer");
    expect(buildQuery({ q: "", status: "all", page: 3 })).toBe("status=all&page=3");
  });
});
```

- [ ] **Step 3: Write format.ts**

```ts
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/.exec(iso);
  if (!m) return iso;
  const day = `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${m[1]}`;
  return m[4] ? `${day}, ${m[4]}:${m[5]}` : day;
}

export function formatCrore(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "";
  if (v >= 1) return `${v.toFixed(2).replace(/\.?0+$/, "")} crore`;
  return `${(v * 100).toFixed(1).replace(/\.?0+$/, "")} lakh`;
}

export function parseFetchedAt(stamp: string | null | undefined): Date | null {
  const m = /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})/.exec(stamp ?? "");
  if (!m) return null;
  return new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]));
}

export function isStale(lastFetched: string | null | undefined, now: Date = new Date()): boolean {
  const d = parseFetchedAt(lastFetched);
  if (!d) return true;
  return now.getTime() - d.getTime() > 36 * 3600 * 1000;
}

export function daysLeft(closing: string | null | undefined, now: Date = new Date()): number | null {
  if (!closing) return null;
  const d = new Date(closing + (closing.length === 16 ? ":00+06:00" : ""));
  if (Number.isNaN(d.getTime())) return null;
  return Math.floor((d.getTime() - now.getTime()) / 86_400_000);
}

export function buildQuery(p: Record<string, string | number | undefined>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(p)) {
    if (v === undefined || v === "" || (k === "status" && v === "Live") || (k === "page" && Number(v) <= 1)) continue;
    sp.set(k, String(v));
  }
  return sp.toString();
}
```

- [ ] **Step 4: Write api.ts**

```ts
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "https://bidefy.iba-jobs.workers.dev";

export type Tender = {
  tender_id: string; reference: string; status: string; nature: string; title: string; ministry: string;
  organization: string; procuring_entity: string; pe_id: string; method: string; published_at: string | null; closing_at: string | null;
  note?: string; awardee?: string | null; bidder_id?: string | null; value_crore?: number | null; signed_on?: string | null; district?: string | null;
};
export type Award = { tender_id: string; title: string; awardee?: string; bidder_id?: string; value_crore: number | null; signed_on: string | null; procuring_entity?: string; pe_id?: string; district?: string };
export type Bidder = { bidder_id: string; canonical_name: string; variants: string; n_awards: number; total_value_crore: number; first_award: string | null; last_award: string | null };
export type PE = { pe_id: string; name: string; ministry: string; n_contracts: number; n_tenders: number };
export type Stats = { live_tenders: number; contracts: number; bidders: number; newest_published: string | null; last_fetched: string | null };
export type Filters = { ministries: { v: string; n: number }[]; districts: { v: string; n: number }[]; statuses: { v: string; n: number }[] };

async function get<T>(path: string, revalidate = 300): Promise<T | null> {
  try {
    const r = await fetch(`${API_BASE}${path}`, { next: { revalidate } });
    if (!r.ok) return null;
    return (await r.json()) as T;
  } catch {
    return null;
  }
}

export const api = {
  stats: () => get<Stats>("/api/v1/stats", 120),
  filters: () => get<Filters>("/api/v1/filters", 3600),
  tenders: (qs: string) => get<{ page: number; size: number; items: Tender[] }>(`/api/v1/tenders${qs ? "?" + qs : ""}`, 120),
  tender: (id: string) => get<{ tender: Tender; similar_awards: Award[] }>(`/api/v1/tenders/${encodeURIComponent(id)}`),
  bidder: (id: string) => get<{ bidder: Bidder; awards: Award[] }>(`/api/v1/bidders/${encodeURIComponent(id)}`),
  pe: (id: string) => get<{ procuring_entity: PE; top_bidders: { bidder_id: string; awardee: string; n_awards: number; total_value_crore: number }[] }>(`/api/v1/pe/${encodeURIComponent(id)}`),
};
```

- [ ] **Step 5: vitest config, run tests, commit**

`web/vitest.config.ts`:
```ts
import { defineConfig } from "vitest/config";
export default defineConfig({ test: { include: ["lib/**/*.test.ts"], environment: "node" } });
```
Add `"test": "vitest run"` to `web/package.json` scripts. Run: `cd web && npx vitest run` and expect 5 passed. Commit: `git add web && git commit -m "Scaffold web app with API client and format helpers"`.

---

### Task 3: Layout and the four data pages

Design direction: an editorial, data-dense tool, not a marketing page. Serif display for headings, system sans for body, a single indigo accent, generous whitespace, tables that read on a phone. Every page renders on the server from the API with revalidation, so there is no loading spinner on first paint.

**Files:**
- Create: `web/app/layout.tsx`, `web/app/page.tsx`, `web/app/t/[id]/page.tsx`, `web/app/e/[id]/page.tsx`, `web/app/pe/[id]/page.tsx`
- Create: `web/app/components/StaleBanner.tsx`, `Filters.tsx`, `TenderCard.tsx`, `Pagination.tsx`, `Stat.tsx`
- Modify: `web/app/globals.css`

Contract for each piece:

- [ ] **Step 1: `globals.css`** imports Tailwind v4 and defines an `@theme` block with `--color-ink`, `--color-ink-2`, `--color-ink-3` (at least 4.5:1 on the ground), `--color-ground`, `--color-surface`, `--color-rule`, `--color-brand` (indigo), `--color-brand-wash`, `--color-ok`, `--color-warn`, `--font-display` (Newsreader with serif fallback via Google Fonts link in layout), `--font-sans` (system stack). Body uses ground and ink.

- [ ] **Step 2: `layout.tsx`** server component: `<html lang="en">`, metadata with title template `%s | Bidefy`, description, `manifest: "/manifest.webmanifest"`, theme colour, apple touch icon. Header with the wordmark "Bidefy" linking home, nav links Tenders, Alerts, and an external link to the API health. Renders `<StaleBanner/>` (fetches stats; shows a warn strip when `isStale(last_fetched)`), then `<main class="mx-auto max-w-6xl px-4 py-8">{children}</main>`, footer with "Data from eprocure.gov.bd, updated nightly. Zero production cost." Includes the `<Sw/>` client component (Task 4) that registers the service worker.

- [ ] **Step 3: `page.tsx` (home)** reads `searchParams` (`q`, `status`, `ministry`, `page`), calls `api.filters()` and `api.tenders(qs)` in parallel, renders `<Stat/>` tiles (live tenders, contracts, bidders from stats), the `<Filters/>` form (GET form, inputs: keyword, status select from statuses plus "all", ministry select from filters; submit keeps the URL shareable), a list of `<TenderCard/>` (title as link to `/t/[id]`, procuring entity, ministry, method tag, published and closing dates with `daysLeft` badge that turns warn under 3 days), and `<Pagination/>` (previous and next preserving the query, next disabled when fewer than `size` items). Empty state text when no items. Acceptance: `/?q=printer` shows the two EPSON tenders from D1; `/?status=all&page=2` paginates.

- [ ] **Step 4: `t/[id]/page.tsx`** fetches `api.tender(id)`; `notFound()` when null. Shows status pill, title as h1, a definition grid (reference, procuring entity linking to `/pe/[pe_id]`, ministry and organisation, nature, method, procurement type, published, closing with days left, note when present). If the tender has an awardee, a card "Awarded" with awardee linking to `/e/[bidder_id]`, value via `formatCrore`, signed date. A section "Recent awards by this entity" listing `similar_awards` in a table (title, awardee link, value, signed). Metadata title from the tender title. Acceptance: `/t/1329525` renders.

- [ ] **Step 5: `e/[id]/page.tsx`** fetches `api.bidder(id)`; h1 canonical name, variants (parsed from JSON) shown as small chips under "Also appears as", stat tiles n_awards, total value, first and last award, table of awards (title linking to `/t/[id]`, entity linking to `/pe/[pe_id]`, district, value, signed). Empty-data states are text, not blank. Acceptance: renders 404 page for an unknown id and a profile once contracts are loaded.

- [ ] **Step 6: `pe/[id]/page.tsx`** fetches `api.pe(id)`; h1 name, ministry, tiles n_tenders and n_contracts, table "Top bidders" (awardee link, n_awards, total value). Acceptance: `/pe/864ee676c14d` (Kushtia Palli Bidyut Samity) renders with zero bidders for now.

- [ ] **Step 7: Verify locally** with `cd web && npm run dev` and the browser pane: home, `/?q=printer`, `/t/1329525`, `/pe/864ee676c14d`, `/e/none` (404). Then `npm run build` must pass. Commit: `git add web && git commit -m "Web: layout and tender, bidder and entity pages"`.

---

### Task 4: PWA shell and the alerts page

**Files:**
- Create: `tools/make_icons.py`, `web/public/icon.svg`, `web/public/icon-192.png`, `web/public/icon-512.png`, `web/public/manifest.webmanifest`, `web/public/sw.js`, `web/lib/push.ts`, `web/app/components/Sw.tsx`, `web/app/components/AlertsForm.tsx`, `web/app/alerts/page.tsx`
- Modify: `pyproject.toml` (Pillow as a dev dependency)

- [ ] **Step 1: Icons.** `uv add --dev pillow`. `tools/make_icons.py` draws a 512 and a 192 PNG: indigo rounded square, white serif "B" centred, using Pillow's default font scaled (or a bundled TTF if present). Also write `icon.svg` with the same mark. Run it, commit the PNGs.

- [ ] **Step 2: `manifest.webmanifest`**
```json
{ "name": "Bidefy", "short_name": "Bidefy", "description": "Tender intelligence for Bangladesh's e-GP portal",
  "start_url": "/", "scope": "/", "display": "standalone", "background_color": "#f1f3f8", "theme_color": "#2a3a93",
  "icons": [ { "src": "/icon-192.png", "sizes": "192x192", "type": "image/png" }, { "src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable" } ] }
```

- [ ] **Step 3: `sw.js`**
```js
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("push", (e) => {
  let data = {};
  try { data = e.data ? e.data.json() : {}; } catch { data = { title: "Bidefy", body: e.data ? e.data.text() : "" }; }
  const title = data.title || "New tender";
  const options = { body: data.body || "", icon: "/icon-192.png", badge: "/icon-192.png", data: { url: data.url || "/" }, tag: data.tag || undefined };
  e.waitUntil(self.registration.showNotification(title, options));
});
self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || "/";
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
    for (const c of list) { if ("focus" in c) { c.navigate(url); return c.focus(); } }
    return self.clients.openWindow(url);
  }));
});
```

- [ ] **Step 4: `lib/push.ts`**
```ts
export function urlBase64ToUint8Array(base64: string): Uint8Array {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const b64 = (base64 + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(b64);
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}
export type Filter = { q?: string; ministry?: string; status?: string; district?: string };
export async function subscribeToPush(apiBase: string, filters: Filter[]): Promise<{ id: string }> {
  const reg = await navigator.serviceWorker.ready;
  const { key } = await (await fetch(`${apiBase}/api/v1/push/public-key`)).json();
  const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(key) });
  const r = await fetch(`${apiBase}/api/v1/subscriptions`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ subscription: sub.toJSON(), filters }) });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error ?? "subscribe failed");
  const data = await r.json();
  localStorage.setItem("bidefy.sub", JSON.stringify({ id: data.id, filters }));
  return { id: data.id };
}
export async function unsubscribeFromPush(apiBase: string): Promise<void> {
  const saved = localStorage.getItem("bidefy.sub");
  const reg = await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.getSubscription();
  if (sub) await sub.unsubscribe();
  if (saved) { const { id } = JSON.parse(saved); await fetch(`${apiBase}/api/v1/subscriptions/${id}`, { method: "DELETE" }); }
  localStorage.removeItem("bidefy.sub");
}
```

- [ ] **Step 5: `Sw.tsx`** client component: on mount, if `"serviceWorker" in navigator`, `navigator.serviceWorker.register("/sw.js")`. Renders nothing.

- [ ] **Step 6: `AlertsForm.tsx`** client component with props `apiBase`, `ministries: string[]`, `statuses: string[]`. State: up to three filter rows (each a keyword, a ministry select, a status select), permission state, saved subscription from localStorage. Buttons: Add filter (disabled at 3), Enable alerts (requests permission, calls `subscribeToPush`), Stop alerts. Shows the unsupported-browser message on iOS Safari that is not installed (`!("PushManager" in window)`), and an install hint. Errors from the API are rendered in a warn box.

- [ ] **Step 7: `alerts/page.tsx`** server component: fetches `api.filters()`, renders a short explanation (free, up to three filters, alerts arrive when a matching tender is published, hourly checks), then `<AlertsForm/>`.

- [ ] **Step 8: Verify** in the browser pane with `npm run dev`: `/alerts` renders, the manifest loads at `/manifest.webmanifest`, `/sw.js` is served, and the Enable button either subscribes (Chrome) or shows the unsupported message. Then `npm run build`. Commit: `git add web tools pyproject.toml uv.lock && git commit -m "PWA shell, service worker and push alert subscriptions"`.

---

### Task 5: Deploy to Vercel, status and docs

**Files:**
- Modify: `status.yaml`, `README.md`, `docs/product/00-overview.md`

- [ ] **Step 1: Deploy** from `web/`: `npx vercel --prod --yes` (project name bidefy, framework auto-detected). Set the env var once: `npx vercel env add NEXT_PUBLIC_API_BASE production` with value `https://bidefy.iba-jobs.workers.dev` (non-interactive form: `echo https://bidefy.iba-jobs.workers.dev | npx vercel env add NEXT_PUBLIC_API_BASE production`), then redeploy. Record the production URL.

- [ ] **Step 2: Smoke** with curl: `/` returns 200 and contains "Bidefy"; `/manifest.webmanifest` returns JSON; `/sw.js` returns JavaScript; `/t/1329525` returns 200.

- [ ] **Step 3: Status and docs.** In `status.yaml` mark `w3-pages` and `w3-pwa` done and add `{id: w3-vercel, title: "Site live on Vercel", owner: claude, state: done, weight: 1, note: "<url>"}`. Add the site URL to `README.md` and to the top of `docs/product/00-overview.md` as "Live: <url>". Commit: `Deploy site to Vercel; week 3 status` and push.

---

## Self-review against the spec

- 5.5 pages: `/`, `/t/:id`, `/e/:id`, `/pe/:id`, `/alerts` covered; `/pricing` is week 7. Predicted award band is week 5; the tender page shows similar awards now and leaves a slot.
- PWA and push: manifest, service worker, push handler, subscription storage in D1 with at most three filters on the free tier. The hourly sender is week 4.
- Stale banner at 36 hours: `isStale` plus `StaleBanner`.
- Tests: vitest for Worker validation and web formatting; `next build` and `tsc` as gates.
- Names consistent: `validateSubscription`, `newSubscriptionId`, `api`, `formatDate`, `formatCrore`, `isStale`, `daysLeft`, `buildQuery`, `subscribeToPush`, `unsubscribeFromPush`.
