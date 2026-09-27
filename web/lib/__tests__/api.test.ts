/**
 * Every page renders from these calls, and every one of them can fail.
 *
 * The contract is that a failure returns null rather than throwing, because the pages are server
 * components: an exception there is a 500 for the reader, while a null becomes "the data service did
 * not respond" beside whatever else the page could still show. That contract had no test.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { api, API_BASE } from "../api";

// Declared parameters so the mock's call tuple is typed and `calls[0][0]` type-checks.
const ok = (body: unknown) =>
  vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
    new Response(JSON.stringify(body), { status: 200 }));

afterEach(() => vi.restoreAllMocks());

describe("api", () => {
  it("asks the expected path and returns the parsed body", async () => {
    const f = ok({ live_tenders: 4167 });
    vi.stubGlobal("fetch", f);
    expect(await api.stats()).toEqual({ live_tenders: 4167 });
    expect(String(f.mock.calls[0][0])).toBe(`${API_BASE}/api/v1/stats`);
  });

  it("returns null on an error status instead of throwing at the reader", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("nope", { status: 500 })));
    expect(await api.stats()).toBeNull();
  });

  it("returns null when the request never completes", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("ECONNREFUSED"); }));
    expect(await api.tenders("status=Live")).toBeNull();
  });

  it("returns null rather than half an object when the body is not JSON", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>gateway</html>", { status: 200 })));
    expect(await api.stats()).toBeNull();
  });

  it("escapes an id so a slash in it cannot reach for another endpoint", async () => {
    const f = ok({ bidder: {} });
    vi.stubGlobal("fetch", f);
    await api.bidder("a/../pe/x");
    expect(String(f.mock.calls[0][0])).toBe(`${API_BASE}/api/v1/bidders/a%2F..%2Fpe%2Fx`);
  });

  it("omits the query string entirely when there is none, rather than a bare question mark", async () => {
    const f = ok({ ministries: [] });
    vi.stubGlobal("fetch", f);
    await api.filters("");
    expect(String(f.mock.calls[0][0])).toBe(`${API_BASE}/api/v1/filters`);
  });
});
