import { Hono } from "hono";
import { cors } from "hono/cors";
import {
  bidderAwardsQuery, bidderQuery, parseTenderFilters, peQuery, peTopBiddersQuery,
  similarAwardsQuery, tenderByIdQuery, tenderListQuery,
} from "./query";

type Bindings = { DB: D1Database };
const app = new Hono<{ Bindings: Bindings }>();

app.use("/api/*", cors({ origin: "*", allowMethods: ["GET", "OPTIONS"] }));

app.get("/", (c) => c.json({ name: "Bidefy API", docs: "/api/v1/health" }));

app.get("/api/v1/health", async (c) => {
  const counts = await c.env.DB.batch([
    c.env.DB.prepare("SELECT COUNT(*) AS n FROM tenders"),
    c.env.DB.prepare("SELECT COUNT(*) AS n FROM contracts"),
    c.env.DB.prepare("SELECT COUNT(*) AS n FROM bidders"),
    c.env.DB.prepare("SELECT MAX(published_at) AS newest FROM tenders"),
  ]);
  const row = (i: number) => (counts[i].results?.[0] as Record<string, unknown> | undefined) ?? {};
  return c.json({
    ok: true,
    tenders: row(0).n ?? 0,
    contracts: row(1).n ?? 0,
    bidders: row(2).n ?? 0,
    newest_tender: row(3).newest ?? null,
  });
});

app.get("/api/v1/tenders", async (c) => {
  const f = parseTenderFilters(new URL(c.req.url).searchParams);
  const q = tenderListQuery(f);
  const { results } = await c.env.DB.prepare(q.sql).bind(...q.params).all();
  return c.json({ page: f.page, size: f.size, items: results ?? [] });
});

app.get("/api/v1/tenders/:id", async (c) => {
  const id = c.req.param("id");
  const q = tenderByIdQuery(id);
  const tender = await c.env.DB.prepare(q.sql).bind(...q.params).first<Record<string, unknown>>();
  if (!tender) return c.json({ error: "not found" }, 404);
  const s = similarAwardsQuery(String(tender.pe_id ?? ""));
  const { results } = await c.env.DB.prepare(s.sql).bind(...s.params).all();
  return c.json({ tender, similar_awards: results ?? [] });
});

app.get("/api/v1/bidders/:id", async (c) => {
  const id = c.req.param("id");
  const b = bidderQuery(id);
  const bidder = await c.env.DB.prepare(b.sql).bind(...b.params).first();
  if (!bidder) return c.json({ error: "not found" }, 404);
  const a = bidderAwardsQuery(id);
  const { results } = await c.env.DB.prepare(a.sql).bind(...a.params).all();
  return c.json({ bidder, awards: results ?? [] });
});

app.get("/api/v1/pe/:id", async (c) => {
  const id = c.req.param("id");
  const p = peQuery(id);
  const pe = await c.env.DB.prepare(p.sql).bind(...p.params).first();
  if (!pe) return c.json({ error: "not found" }, 404);
  const t = peTopBiddersQuery(id);
  const { results } = await c.env.DB.prepare(t.sql).bind(...t.params).all();
  return c.json({ procuring_entity: pe, top_bidders: results ?? [] });
});

export default {
  fetch: app.fetch,
  async scheduled(_event: ScheduledEvent, env: Bindings, _ctx: ExecutionContext) {
    // Week 4 wires the alert matcher here. For now record the tick so the cron is observable.
    await env.DB.prepare("INSERT OR REPLACE INTO meta (key, value) VALUES ('last_cron', ?)")
      .bind(new Date().toISOString())
      .run();
  },
};
