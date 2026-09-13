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
