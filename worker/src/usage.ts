/**
 * What the product is actually being used for, counted honestly.
 *
 * Two kinds of number live here and they must not be confused. Subscribers, alerts delivered and
 * access requests are demand: they are zero until someone arrives, and reporting a zero as though
 * it were a measurement of anything but that would be dishonest. Alert runs and the candidates each
 * one saw are liveness: the hourly cron has been examining newly published tenders since launch
 * whether or not anybody is subscribed, so those numbers are real from the first day and say the
 * pipeline works.
 *
 * Nothing here returns a row that identifies a person. Endpoints, keys and contact details stay in
 * their tables; only counts and timestamps leave.
 */

export type UsageRow = Record<string, unknown>;

/** The statements behind /api/v1/usage, in the order usageSummary expects them. */
export const USAGE_SQL: string[] = [
  "SELECT COUNT(*) AS n, MIN(created_at) AS first FROM subscriptions",
  "SELECT COUNT(*) AS n FROM subscriptions WHERE last_sent_at >= ?",
  "SELECT COUNT(*) AS n, MIN(sent_at) AS first, MAX(sent_at) AS last FROM sent",
  "SELECT COUNT(*) AS n FROM sent WHERE sent_at >= ?",
  "SELECT COUNT(*) AS n, MAX(created_at) AS last FROM access_requests",
  "SELECT COUNT(*) AS n, MAX(ran_at) AS last, SUM(candidates) AS seen, SUM(errored) AS errored FROM alert_runs",
  "SELECT SUM(candidates) AS seen FROM alert_runs WHERE ran_at >= ?",
];

/** The parameters for USAGE_SQL: the statements that take one all take the same cutoff. */
export function usageParams(now: Date): (string | number)[][] {
  const ago = (days: number) => new Date(now.getTime() - days * 86_400_000).toISOString();
  return [[], [ago(30)], [], [ago(7)], [], [], [ago(7)]];
}

const int = (v: unknown): number => (typeof v === "number" ? v : Number(v ?? 0)) || 0;
const iso = (v: unknown): string | null => (typeof v === "string" && v ? v : null);

export function usageSummary(rows: (UsageRow | undefined)[]) {
  const [subs, subsActive, sent, sent7, access, runs, runs7] = rows;
  const subscribers = int(subs?.n);
  const delivered = int(sent?.n);
  const requests = int(access?.n);
  return {
    // Demand. Zero until the product is in front of someone.
    subscribers,
    subscribers_alerted_in_30_days: int(subsActive?.n),
    first_subscribed_at: iso(subs?.first),
    alerts_delivered: delivered,
    alerts_delivered_in_7_days: int(sent7?.n),
    first_alert_at: iso(sent?.first),
    last_alert_at: iso(sent?.last),
    access_requests: requests,
    last_access_request_at: iso(access?.last),
    // Liveness. Real from the first hour, with or without an audience.
    alert_runs: int(runs?.n),
    alert_runs_that_threw: int(runs?.errored),
    last_alert_run_at: iso(runs?.last),
    tenders_examined: int(runs?.seen),
    tenders_examined_in_7_days: int(runs7?.seen),
    // Stated rather than left for a reader to infer from three zeros.
    has_audience: subscribers > 0 || requests > 0,
  };
}
