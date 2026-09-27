/**
 * The API proxy: every browser call to the data service goes through here.
 *
 * It exists because some Bangladeshi networks block *.workers.dev, so the site origin forwards on
 * the reader's behalf. That makes it the single point every request passes, and it had no tests --
 * the vitest config only collected lib/**, so a test placed here would not even have run.
 *
 * What matters about a proxy is as much what it refuses to pass on as what it passes. A forwarder
 * that copied every header would hand the reader's cookies and Authorization to an upstream that has
 * no business seeing them, and would do it silently.
 */
import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { API_BASE } from "@/lib/api";
import { DELETE, GET, POST } from "./[...path]/route";

const ctx = (...path: string[]) => ({ params: Promise.resolve({ path }) });

function upstream(body: unknown, init: { status?: number; contentType?: string } = {}) {
  return vi.fn(async () =>
    new Response(typeof body === "string" ? body : JSON.stringify(body), {
      status: init.status ?? 200,
      headers: { "content-type": init.contentType ?? "application/json" },
    }));
}

const called = (fetchMock: ReturnType<typeof vi.fn>) => {
  const [url, options] = fetchMock.mock.calls[0] as [URL, RequestInit];
  return { url: url.toString(), options, headers: options.headers as Record<string, string> };
};

beforeEach(() => vi.useRealTimers());
afterEach(() => vi.restoreAllMocks());

describe("the proxy forwards", () => {
  it("the path and the query string, onto the data service", async () => {
    const f = upstream({ items: [] });
    vi.stubGlobal("fetch", f);
    await GET(new NextRequest("https://bidefy.vercel.app/api/v1/tenders?q=road&page=2"),
              ctx("v1", "tenders"));
    expect(called(f).url).toBe(`${API_BASE}/api/v1/tenders?q=road&page=2`);
  });

  it("a nested path without losing a segment", async () => {
    const f = upstream({ bidder: {} });
    vi.stubGlobal("fetch", f);
    await GET(new NextRequest("https://bidefy.vercel.app/api/v1/bidders/abc123"),
              ctx("v1", "bidders", "abc123"));
    expect(called(f).url).toBe(`${API_BASE}/api/v1/bidders/abc123`);
  });

  it("the upstream status and content type, rather than flattening them to 200", async () => {
    vi.stubGlobal("fetch", upstream({ error: "not found" }, { status: 404 }));
    const res = await GET(new NextRequest("https://bidefy.vercel.app/api/v1/tenders/nope"),
                          ctx("v1", "tenders", "nope"));
    expect(res.status).toBe(404);
    expect(res.headers.get("content-type")).toContain("application/json");
    expect(await res.json()).toEqual({ error: "not found" });
  });

  it("a POST body, and sends none on a GET", async () => {
    const post = upstream({ id: "x" }, { status: 201 });
    vi.stubGlobal("fetch", post);
    await POST(new NextRequest("https://bidefy.vercel.app/api/v1/access-requests",
                               { method: "POST", body: JSON.stringify({ name: "A" }),
                                 headers: { "content-type": "application/json" } }),
               ctx("v1", "access-requests"));
    expect(called(post).options.body).toBe(JSON.stringify({ name: "A" }));
    expect(called(post).headers["content-type"]).toBe("application/json");

    const get = upstream({ ok: true });
    vi.stubGlobal("fetch", get);
    await GET(new NextRequest("https://bidefy.vercel.app/api/v1/stats"), ctx("v1", "stats"));
    expect(called(get).options.body).toBeUndefined();
  });

  it("a DELETE through, since unsubscribing uses it", async () => {
    const f = upstream({ deleted: 1 });
    vi.stubGlobal("fetch", f);
    const res = await DELETE(new NextRequest("https://bidefy.vercel.app/api/v1/subscriptions/s1",
                                             { method: "DELETE" }), ctx("v1", "subscriptions", "s1"));
    expect(called(f).options.method).toBe("DELETE");
    expect(res.status).toBe(200);
  });
});

describe("the proxy withholds", () => {
  it("the reader's cookies and Authorization, which the data service must never see", async () => {
    const f = upstream({ ok: true });
    vi.stubGlobal("fetch", f);
    await GET(new NextRequest("https://bidefy.vercel.app/api/v1/stats", {
      headers: { cookie: "session=secret", authorization: "Bearer someone-elses-token",
                 "user-agent": "Mozilla/5.0" },
    }), ctx("v1", "stats"));
    const keys = Object.keys(called(f).headers).map((k) => k.toLowerCase());
    expect(keys).not.toContain("cookie");
    expect(keys).not.toContain("authorization");
    expect(keys).not.toContain("user-agent");
    expect(keys).toContain("accept");
  });

  it("but carries the admin token and the caller's address, which the API does need", async () => {
    const f = upstream({ items: [] });
    vi.stubGlobal("fetch", f);
    await GET(new NextRequest("https://bidefy.vercel.app/api/v1/admin/access-requests", {
      headers: { "x-admin-token": "t0ken", "x-forwarded-for": "203.0.113.9" },
    }), ctx("v1", "admin", "access-requests"));
    expect(called(f).headers["x-admin-token"]).toBe("t0ken");
    expect(called(f).headers["x-forwarded-for"]).toBe("203.0.113.9");
  });
});

describe("when the data service does not answer", () => {
  it("returns 502 with a sentence a reader can act on, not a stack trace", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("ECONNREFUSED"); }));
    const res = await GET(new NextRequest("https://bidefy.vercel.app/api/v1/stats"), ctx("v1", "stats"));
    expect(res.status).toBe(502);
    expect(await res.json()).toEqual({ error: "the data service did not respond" });
  });

  it("gives up rather than hanging, so a page never waits on a dead upstream forever", async () => {
    const aborted = vi.fn((_url: URL, options: RequestInit) =>
      new Promise((_resolve, reject) => {
        (options.signal as AbortSignal).addEventListener("abort", () => reject(new Error("aborted")));
      }));
    vi.stubGlobal("fetch", aborted);
    const res = GET(new NextRequest("https://bidefy.vercel.app/api/v1/stats"), ctx("v1", "stats"));
    // The route awaits its route params before it fetches, so the call has not happened yet.
    await vi.waitFor(() => expect(aborted).toHaveBeenCalled());
    const signal = (aborted.mock.calls[0][1] as RequestInit).signal as AbortSignal;
    expect(signal).toBeInstanceOf(AbortSignal);
    signal.dispatchEvent(new Event("abort"));
    expect((await res).status).toBe(502);
  });
});
