import { describe, expect, it } from "vitest";
import { defaultFiltersKey, readCache } from "../src/cache";
import { parseTenderFilters } from "../src/query";

describe("readCache", () => {
  it("serves a summary only while the load that produced it is still the latest", () => {
    const raw = JSON.stringify({ marker: "load-7", value: { live_tenders: 15742 } });
    expect(readCache(raw, "load-7")).toEqual({ live_tenders: 15742 });
    expect(readCache(raw, "load-8")).toBeUndefined();     // a newer load: recompute
  });

  it("never caches against a missing marker, which would freeze the figures for good", () => {
    expect(readCache(JSON.stringify({ marker: "", value: 1 }), "")).toBeUndefined();
    expect(readCache(undefined, "load-7")).toBeUndefined();
    expect(readCache("not json", "load-7")).toBeUndefined();
  });
});

describe("defaultFiltersKey", () => {
  it("caches only the views nobody has narrowed, so bots cannot fill the table with keys", () => {
    const f = (qs: string) => parseTenderFilters(new URLSearchParams(qs));
    expect(defaultFiltersKey(f(""))).toBe("summary:filters:Live");
    expect(defaultFiltersKey(f("status=all"))).toBe("summary:filters:all");
    expect(defaultFiltersKey(f("q=road"))).toBeNull();
    expect(defaultFiltersKey(f("ministry=Health"))).toBeNull();
    expect(defaultFiltersKey(f("status=whatever"))).toBeNull();
  });
});
