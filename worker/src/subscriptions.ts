export type Filter = { q?: string; ministry?: string; status?: string; district?: string; category?: string };
export type ValidSubscription = { endpoint: string; keys: { p256dh: string; auth: string }; filters: Filter[] };
export type Result = { ok: true; value: ValidSubscription } | { ok: false; error: string };

const MAX_FILTERS = 3;
const MAX_LEN = 120;
const FILTER_KEYS: (keyof Filter)[] = ["q", "ministry", "status", "district", "category"];

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
