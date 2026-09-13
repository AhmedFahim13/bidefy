import { describe, expect, it } from "vitest";
import { newSubscriptionId, validateSubscription } from "../src/subscriptions";

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
    const a = newSubscriptionId();
    const b = newSubscriptionId();
    expect(a).toMatch(/^[0-9a-f]{32}$/);
    expect(a).not.toBe(b);
  });
});
