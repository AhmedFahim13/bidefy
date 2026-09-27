import { describe, expect, it } from "vitest";
import { USAGE_SQL, usageParams, usageSummary } from "../src/usage";

describe("usageSummary", () => {
  it("separates demand from liveness, so an empty audience is not confused with a dead cron", () => {
    const u = usageSummary([
      { n: 0, first: null },          // subscriptions
      { n: 0 },                       // alerted in 30 days
      { n: 0, first: null, last: null },
      { n: 0 },
      { n: 0, last: null },           // access requests
      { n: 412, last: "2026-09-27T09:00:00Z", seen: 5310 },
      { seen: 918 },
    ]);
    expect(u.has_audience).toBe(false);
    expect(u.subscribers).toBe(0);
    expect(u.alert_runs).toBe(412);
    expect(u.tenders_examined).toBe(5310);
    expect(u.tenders_examined_in_7_days).toBe(918);
    expect(u.last_alert_run_at).toBe("2026-09-27T09:00:00Z");
  });

  it("counts the runs that threw, so a crashloop cannot read as a quiet one", () => {
    const u = usageSummary([
      { n: 0 }, { n: 0 }, { n: 0 }, { n: 0 }, { n: 0 },
      { n: 24, last: "2026-09-27T08:00:00Z", seen: 0, errored: 24 },
      { seen: 0 },
    ]);
    // Twenty-four runs, every one of them a failure, and no candidates seen. Without the errored
    // column this is indistinguishable from a healthy day on which nothing was published.
    expect(u.alert_runs).toBe(24);
    expect(u.alert_runs_that_threw).toBe(24);
    expect(u.tenders_examined).toBe(0);
  });

  it("reports an audience once anyone has subscribed or asked for access", () => {
    const base = [{ n: 0, first: null }, { n: 0 }, { n: 0 }, { n: 0 }, { n: 0, last: null },
                  { n: 1, last: null, seen: 0 }, { seen: 0 }];
    expect(usageSummary(base).has_audience).toBe(false);
    expect(usageSummary([{ n: 2, first: "x" }, ...base.slice(1)]).has_audience).toBe(true);
    expect(usageSummary([...base.slice(0, 4), { n: 1, last: "y" }, ...base.slice(5)]).has_audience).toBe(true);
  });

  it("survives missing rows and string counts rather than serving NaN", () => {
    const u = usageSummary([undefined, undefined, undefined, undefined, undefined, undefined, undefined]);
    expect(u.subscribers).toBe(0);
    expect(u.tenders_examined).toBe(0);
    expect(Number.isNaN(u.alert_runs)).toBe(false);
    expect(usageSummary([{ n: "7" }, ...Array(6).fill({})]).subscribers).toBe(7);
  });

  it("never selects a column that identifies a person", () => {
    for (const sql of USAGE_SQL) {
      expect(sql).not.toMatch(/endpoint|keys_json|contact|ip_hash|\bname\b/i);
      expect(sql.startsWith("SELECT")).toBe(true);
    }
  });

  it("gives a cutoff to exactly the statements that ask for one", () => {
    const params = usageParams(new Date("2026-09-27T00:00:00Z"));
    expect(params.length).toBe(USAGE_SQL.length);
    USAGE_SQL.forEach((sql, i) => expect(params[i].length).toBe((sql.match(/\?/g) ?? []).length));
    expect(params[1][0]).toBe("2026-08-28T00:00:00.000Z");   // 30 days back
    expect(params[3][0]).toBe("2026-09-20T00:00:00.000Z");   // 7 days back
  });
});
