import { Hono } from "hono";
import { cors } from "hono/cors";
import { bidderQuery, parseJsonList, parseJsonObject, parseTenderFilters, peQuery, predictionQuery, tenderByIdQuery, tenderListQuery } from "./query";
import { newSubscriptionId, validateSubscription } from "./subscriptions";
import { runAlerts } from "./alerts";
import { hashIp, validateAccessRequest } from "./access";

type Bindings = {
  DB: D1Database;
  VAPID_PUBLIC_KEY: string;
  VAPID_PRIVATE_KEY: string;
  VAPID_SUBJECT: string;
  ADMIN_TOKEN: string;
  SITE_BASE: string;
};
const app = new Hono<{ Bindings: Bindings }>();

app.use("/api/*", cors({ origin: "*", allowMethods: ["GET", "POST", "DELETE", "OPTIONS"] }));

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
  const pe = peQuery(String(tender.pe_id ?? ""));
  const p = predictionQuery(id);
  const [entity, prediction] = await c.env.DB.batch([
    c.env.DB.prepare(pe.sql).bind(...pe.params),
    c.env.DB.prepare(p.sql).bind(...p.params),
  ]);
  const entityRow = (entity.results?.[0] as Record<string, unknown> | undefined) ?? {};
  return c.json({ tender, similar_awards: parseJsonList(entityRow.recent_awards), prediction: prediction.results?.[0] ?? null });
});

app.get("/api/v1/bidders/:id", async (c) => {
  const id = c.req.param("id");
  const b = bidderQuery(id);
  const bidder = await c.env.DB.prepare(b.sql).bind(...b.params).first<Record<string, unknown>>();
  if (!bidder) return c.json({ error: "not found" }, 404);
  const { recent_awards, flags, ...rest } = bidder;
  return c.json({ bidder: rest, awards: parseJsonList(recent_awards), flags: parseJsonObject(flags) });
});

app.get("/api/v1/pe/:id", async (c) => {
  const id = c.req.param("id");
  const p = peQuery(id);
  const pe = await c.env.DB.prepare(p.sql).bind(...p.params).first<Record<string, unknown>>();
  if (!pe) return c.json({ error: "not found" }, 404);
  const { recent_awards, top_bidders, flags, ...rest } = pe;
  return c.json({ procuring_entity: rest, top_bidders: parseJsonList(top_bidders), recent_awards: parseJsonList(recent_awards), flags: parseJsonObject(flags) });
});

app.get("/api/v1/filters", async (c) => {
  const [ministries, districts, statuses, categories] = await c.env.DB.batch([
    c.env.DB.prepare("SELECT ministry AS v, COUNT(*) AS n FROM tenders WHERE ministry != '' GROUP BY ministry ORDER BY n DESC LIMIT 60"),
    c.env.DB.prepare("SELECT district AS v, COUNT(*) AS n FROM contracts WHERE district != '' GROUP BY district ORDER BY n DESC LIMIT 70"),
    c.env.DB.prepare("SELECT status AS v, COUNT(*) AS n FROM tenders WHERE status != '' GROUP BY status ORDER BY n DESC"),
    c.env.DB.prepare("SELECT category AS v, COUNT(*) AS n FROM tenders WHERE category IS NOT NULL AND category != '' GROUP BY category ORDER BY n DESC"),
  ]);
  return c.json({
    ministries: ministries.results ?? [],
    districts: districts.results ?? [],
    statuses: statuses.results ?? [],
    categories: categories.results ?? [],
  });
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
  return c.json({
    live_tenders: one(0).n ?? 0,
    contracts: one(1).n ?? 0,
    bidders: one(2).n ?? 0,
    newest_published: one(3).v ?? null,
    last_fetched: one(4).v ?? null,
  });
});

app.get("/api/v1/push/public-key", (c) => c.json({ key: c.env.VAPID_PUBLIC_KEY ?? "" }));

app.post("/api/v1/subscriptions", async (c) => {
  let body: unknown;
  try {
    body = await c.req.json();
  } catch {
    return c.json({ error: "invalid json" }, 400);
  }
  const v = validateSubscription(body);
  if (!v.ok) return c.json({ error: v.error }, 400);
  const existing = await c.env.DB.prepare("SELECT id FROM subscriptions WHERE endpoint = ?")
    .bind(v.value.endpoint)
    .first<{ id: string }>();
  const id = existing?.id ?? newSubscriptionId();
  await c.env.DB.prepare(
    "INSERT OR REPLACE INTO subscriptions (id, endpoint, keys_json, filters_json, created_at, last_sent_at) " +
      "VALUES (?, ?, ?, ?, COALESCE((SELECT created_at FROM subscriptions WHERE id = ?), ?), NULL)",
  )
    .bind(id, v.value.endpoint, JSON.stringify(v.value.keys), JSON.stringify(v.value.filters), id, new Date().toISOString())
    .run();
  return c.json({ id, filters: v.value.filters }, existing ? 200 : 201);
});

app.delete("/api/v1/subscriptions/:id", async (c) => {
  const { meta } = await c.env.DB.prepare("DELETE FROM subscriptions WHERE id = ?").bind(c.req.param("id")).run();
  return c.json({ deleted: meta.changes ?? 0 });
});

app.post("/api/v1/access-requests", async (c) => {
  let body: unknown;
  try {
    body = await c.req.json();
  } catch {
    return c.json({ error: "invalid json" }, 400);
  }
  const v = validateAccessRequest(body);
  if (!v.ok) return c.json({ error: v.error }, 400);
  const ip = c.req.header("cf-connecting-ip") ?? c.req.header("x-forwarded-for") ?? "unknown";
  const ipHash = await hashIp(ip);
  const hourAgo = new Date(Date.now() - 3600_000).toISOString();
  const recent = await c.env.DB.prepare("SELECT COUNT(*) AS n FROM access_requests WHERE ip_hash = ? AND created_at > ?")
    .bind(ipHash, hourAgo)
    .first<{ n: number }>();
  if ((recent?.n ?? 0) >= 5) return c.json({ error: "too many requests from this network, try later" }, 429);
  const id = newSubscriptionId();
  await c.env.DB.prepare(
    "INSERT INTO access_requests (id, created_at, name, organisation, role, bids_on, value_band, contact, note, ip_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
  )
    .bind(id, new Date().toISOString(), v.value.name, v.value.organisation, v.value.role, v.value.bids_on, v.value.value_band, v.value.contact, v.value.note, ipHash)
    .run();
  return c.json({ id }, 201);
});

app.get("/api/v1/admin/access-requests", async (c) => {
  const token = c.req.header("x-admin-token") ?? "";
  if (!c.env.ADMIN_TOKEN || token !== c.env.ADMIN_TOKEN) return c.json({ error: "forbidden" }, 403);
  const { results } = await c.env.DB.prepare(
    "SELECT id, created_at, name, organisation, role, bids_on, value_band, contact, note FROM access_requests ORDER BY created_at DESC LIMIT 200",
  ).all();
  return c.json({ items: results ?? [] });
});

app.post("/api/v1/admin/run-alerts", async (c) => {
  const token = c.req.header("x-admin-token") ?? "";
  if (!c.env.ADMIN_TOKEN || token !== c.env.ADMIN_TOKEN) return c.json({ error: "forbidden" }, 403);
  const dry = new URL(c.req.url).searchParams.get("dry") === "1";
  const result = await runAlerts(c.env, { dry, siteBase: c.env.SITE_BASE });
  return c.json(result);
});

export default {
  fetch: app.fetch,
  async scheduled(_event: ScheduledEvent, env: Bindings, ctx: ExecutionContext) {
    ctx.waitUntil(runAlerts(env, { dry: false, siteBase: env.SITE_BASE }));
  },
};
