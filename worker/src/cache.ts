/**
 * Summaries that only change when the nightly load does, kept in meta between loads.
 *
 * D1's free tier allows five million rows read a day for the whole account, and on 2026-11-03 the
 * account ran out by 13:00 UTC: every query failed until midnight, the site's API with them, and
 * 44 percent of hourly alert runs threw. The figures behind /stats, /health and the unfiltered
 * dropdowns count whole tables -- about 120 thousand rows for /stats alone -- yet they can only
 * change when bidefy.export.d1 writes, and every load stamps meta's d1_last_load. So each summary
 * is computed once per load, stored against that stamp, and served from one row until the next.
 */
import type { TenderFilters } from "./query";

const MARKER_SQL = "SELECT value FROM meta WHERE key = 'd1_last_load'";
const CACHEABLE_STATUS = new Set(["Live", "all"]);

/** The cached value, if it was computed against this load; otherwise undefined. */
export function readCache(raw: unknown, marker: string): unknown {
  if (!marker || typeof raw !== "string") return undefined;
  try {
    const v = JSON.parse(raw);
    return v && v.marker === marker ? v.value : undefined;
  } catch {
    return undefined;
  }
}

/** The meta key for a dropdown request nobody has narrowed, or null when it should not be cached.
 * Only the default views are cached, so a crawler trying combinations cannot grow the table. */
export function defaultFiltersKey(f: TenderFilters): string | null {
  if (f.q || f.ministry || f.district || f.category || !CACHEABLE_STATUS.has(f.status)) return null;
  return `summary:filters:${f.status}`;
}

/** compute() once per load: two single-row reads on every later call until the next load. */
export async function cachedSummary<T>(db: D1Database, key: string, compute: () => Promise<T>): Promise<T> {
  const [m, c] = await db.batch([db.prepare(MARKER_SQL), db.prepare("SELECT value FROM meta WHERE key = ?").bind(key)]);
  const marker = String((m.results?.[0] as { value?: unknown } | undefined)?.value ?? "");
  const hit = readCache((c.results?.[0] as { value?: unknown } | undefined)?.value, marker);
  if (hit !== undefined) return hit as T;
  const value = await compute();
  if (marker) {
    try {
      await db.prepare("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)")
        .bind(key, JSON.stringify({ marker, value })).run();
    } catch {
      // a failed write only means the next call computes again
    }
  }
  return value;
}
