import { buildPushPayload, type PushSubscription, type VapidKeys } from "@block65/webcrypto-web-push";
import type { Filter } from "./subscriptions";
import { categoryMatches } from "./query";

export type TenderLite = {
  tender_id: string;
  title: string;
  ministry: string;
  status: string;
  category?: string | null;
  procuring_entity: string;
  closing_at: string | null;
  fetched_at?: string | null;
};

export type Notification = { title: string; body: string; url: string; tag: string };

export type AlertEnv = {
  DB: D1Database;
  VAPID_PUBLIC_KEY: string;
  VAPID_PRIVATE_KEY: string;
  VAPID_SUBJECT: string;
};

export type RunResult = { candidates: number; subscriptions: number; matched: number; sent: number; failed: number; pruned: number; dry: boolean; watermark: string };

const MAX_CANDIDATES = 500;
const MAX_PER_SUBSCRIPTION = 20;

function rowMatches(t: TenderLite, f: Filter): boolean {
  const keys = Object.entries(f).filter(([, v]) => typeof v === "string" && v.trim() !== "");
  if (!keys.length) return false;
  for (const [k, v] of keys) {
    const want = (v as string).trim();
    if (k === "q" && !(t.title ?? "").toLowerCase().includes(want.toLowerCase())) return false;
    if (k === "ministry" && (t.ministry ?? "") !== want) return false;
    if (k === "status" && (t.status ?? "") !== want) return false;
    if (k === "category" && !categoryMatches(t.category, want)) return false;
    if (k === "district") return false; // tenders carry no district; district filters apply to awards later
  }
  return true;
}

export function matchFilters(t: TenderLite, filters: Filter[]): boolean {
  return filters.some((f) => rowMatches(t, f));
}

function shortDate(iso: string | null): string {
  if (!iso) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${Number(m[3])} ${months[Number(m[2]) - 1]}`;
}

export function notificationFor(t: TenderLite, siteBase: string): Notification {
  const title = (t.title || "New tender").slice(0, 80);
  const closes = t.closing_at ? ` · closes ${shortDate(t.closing_at)}` : "";
  return {
    title,
    body: `${t.procuring_entity || t.ministry || "e-GP"}${closes}`,
    url: `${siteBase.replace(/\/$/, "")}/t/${t.tender_id}`,
    tag: `tender-${t.tender_id}`,
  };
}

type SubRow = { id: string; endpoint: string; keys_json: string; filters_json: string };

async function sendOne(sub: SubRow, n: Notification, vapid: VapidKeys): Promise<number> {
  const subscription: PushSubscription = { endpoint: sub.endpoint, expirationTime: null, keys: JSON.parse(sub.keys_json) };
  const payload = await buildPushPayload({ data: n, options: { ttl: 6 * 3600, urgency: "normal" } }, subscription, vapid);
  const res = await fetch(sub.endpoint, payload);
  return res.status;
}

export async function runAlerts(env: AlertEnv, opts: { dry: boolean; siteBase: string }): Promise<RunResult> {
  // Every real run is recorded, including the ones that found nothing and the ones that threw.
  // With no subscribers the matcher still examines the tenders published since the last watermark,
  // so this is the only honest usage number the product has before it has an audience, and the only
  // evidence the hourly cron is alive. That claim only holds if a failing run leaves a row too:
  // otherwise an hourly crashloop writes nothing and looks exactly like a cron that never fired.
  // A dry run is a diagnostic and is not recorded.
  let result: RunResult | null = null;
  let error: string | null = null;
  try {
    result = await matchAndSend(env, opts);
    return result;
  } catch (e) {
    error = alertErrorText(e);
    throw e;
  } finally {
    if (!opts.dry) await record(env, result, error);
  }
}

/** What a failed run threw, short enough to publish: its kind and message, long numbers masked. */
export function alertErrorText(e: unknown): string {
  const text = e instanceof Error ? `${e.name}: ${e.message}` : e === undefined ? "unknown" : String(e);
  return text.replace(/\d{6,}/g, "#").slice(0, 200);
}

async function record(env: AlertEnv, r: RunResult | null, error: string | null): Promise<void> {
  const at = new Date().toISOString();
  try {
    await env.DB.prepare(
      "INSERT OR REPLACE INTO alert_runs (ran_at, candidates, subscriptions, matched, sent, failed, pruned, errored) " +
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
    )
      .bind(at, r?.candidates ?? 0, r?.subscriptions ?? 0, r?.matched ?? 0,
            r?.sent ?? 0, r?.failed ?? 0, r?.pruned ?? 0, r ? 0 : 1)
      .run();
    // The count of failed runs says that the cron breaks, not why; the last error says why, and
    // /api/v1/usage shows it, so a crashloop can be read without access to the Cloudflare logs.
    if (error) {
      await env.DB.prepare("INSERT OR REPLACE INTO meta (key, value) VALUES ('last_alert_error', ?)")
        .bind(JSON.stringify({ at, error }))
        .run();
    }
  } catch {
    // Bookkeeping must never cost an alert. The run happened whether or not it was written down.
  }
}

async function matchAndSend(env: AlertEnv, opts: { dry: boolean; siteBase: string }): Promise<RunResult> {
  const wm = await env.DB.prepare("SELECT value FROM meta WHERE key = 'alerts_watermark'").first<{ value: string }>();
  const watermark = wm?.value ?? "";
  if (!watermark && !opts.dry) {
    // First ever run: never treat the whole backlog as new. Start alerting from now on.
    const newest = await env.DB.prepare("SELECT MAX(fetched_at) AS v FROM tenders").first<{ v: string | null }>();
    if (newest?.v) {
      await env.DB.prepare("INSERT OR REPLACE INTO meta (key, value) VALUES ('alerts_watermark', ?)").bind(newest.v).run();
    }
    return { candidates: 0, subscriptions: 0, matched: 0, sent: 0, failed: 0, pruned: 0, dry: false, watermark: newest?.v ?? "" };
  }
  // New tenders only reach D1 with a load, so an hour with no new load has nothing to examine.
  // Reading every live tender to learn that cost 15.7k rows an hour against D1's daily read cap.
  const marks = await env.DB.prepare("SELECT key, value FROM meta WHERE key IN ('d1_last_load', 'alerts_matched_load')")
    .all<{ key: string; value: string }>();
  const mark = (k: string) => marks.results?.find((r) => r.key === k)?.value;
  const load = mark("d1_last_load") ?? "";
  if (!opts.dry && loadAlreadyMatched(load, mark("alerts_matched_load"))) {
    return { candidates: 0, subscriptions: 0, matched: 0, sent: 0, failed: 0, pruned: 0, dry: false, watermark };
  }
  const { results: tenders } = await env.DB.prepare(
    "SELECT tender_id, title, ministry, status, category, procuring_entity, closing_at, fetched_at FROM tenders " +
      "WHERE fetched_at > ? AND status = 'Live' ORDER BY fetched_at ASC LIMIT ?",
  )
    .bind(watermark, MAX_CANDIDATES)
    .all<TenderLite>();
  const { results: subs } = await env.DB.prepare("SELECT id, endpoint, keys_json, filters_json FROM subscriptions").all<SubRow>();
  const result: RunResult = { candidates: tenders?.length ?? 0, subscriptions: subs?.length ?? 0, matched: 0, sent: 0, failed: 0, pruned: 0, dry: opts.dry, watermark };
  if (!tenders?.length || !subs?.length) {
    if (tenders?.length && !opts.dry) await advance(env, tenders);
    if (!opts.dry) await markMatched(env, load, tenders?.length ?? 0);
    return result;
  }
  const vapid: VapidKeys = { subject: env.VAPID_SUBJECT, publicKey: env.VAPID_PUBLIC_KEY, privateKey: env.VAPID_PRIVATE_KEY };
  const sentRows = await env.DB.prepare("SELECT subscription_id, tender_id FROM sent WHERE tender_id IN (" + tenders.map(() => "?").join(",") + ")")
    .bind(...tenders.map((t) => t.tender_id))
    .all<{ subscription_id: string; tender_id: string }>();
  const already = new Set((sentRows.results ?? []).map((r) => `${r.subscription_id}:${r.tender_id}`));
  const now = new Date().toISOString();

  for (const sub of subs) {
    let filters: Filter[] = [];
    try { filters = JSON.parse(sub.filters_json); } catch { continue; }
    let count = 0;
    let dead = false;
    for (const t of tenders) {
      if (dead || count >= MAX_PER_SUBSCRIPTION) break;
      if (already.has(`${sub.id}:${t.tender_id}`) || !matchFilters(t, filters)) continue;
      result.matched += 1;
      if (opts.dry) continue;
      try {
        const status = await sendOne(sub, notificationFor(t, opts.siteBase), vapid);
        if (status === 404 || status === 410) {
          dead = true;
          await env.DB.prepare("DELETE FROM subscriptions WHERE id = ?").bind(sub.id).run();
          result.pruned += 1;
          break;
        }
        if (status >= 200 && status < 300) {
          result.sent += 1;
          count += 1;
          await env.DB.batch([
            env.DB.prepare("INSERT OR IGNORE INTO sent (subscription_id, tender_id, sent_at) VALUES (?, ?, ?)").bind(sub.id, t.tender_id, now),
            env.DB.prepare("UPDATE subscriptions SET last_sent_at = ? WHERE id = ?").bind(now, sub.id),
          ]);
        } else {
          result.failed += 1;
        }
      } catch {
        result.failed += 1;
      }
    }
  }
  if (!opts.dry) {
    await advance(env, tenders);
    await markMatched(env, load, tenders.length);
  }
  return result;
}

/** True when this load's tenders were already all examined by an earlier run. */
export function loadAlreadyMatched(load: string, matched: string | undefined): boolean {
  return !!load && load === matched;
}

async function markMatched(env: AlertEnv, load: string, examined: number): Promise<void> {
  // a full batch may have more behind it, so only a short one closes the load
  if (!load || examined >= MAX_CANDIDATES) return;
  await env.DB.prepare("INSERT OR REPLACE INTO meta (key, value) VALUES ('alerts_matched_load', ?)").bind(load).run();
}

async function advance(env: AlertEnv, tenders: TenderLite[]): Promise<void> {
  const newest = tenders[tenders.length - 1]?.fetched_at;
  if (!newest) return;
  await env.DB.prepare("INSERT OR REPLACE INTO meta (key, value) VALUES ('alerts_watermark', ?)").bind(newest).run();
  await env.DB.prepare("INSERT OR REPLACE INTO meta (key, value) VALUES ('last_cron', ?)").bind(new Date().toISOString()).run();
}
