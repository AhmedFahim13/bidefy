import { describe, expect, it } from "vitest";
import { bidderQuery, parseJsonList, parseTenderFilters, peQuery, tenderByIdQuery, tenderListQuery } from "../src/query";

describe("parseJsonList", () => {
  it("returns arrays for valid JSON lists and empty arrays otherwise", () => {
    expect(parseJsonList('[{"a":1}]')).toEqual([{ a: 1 }]);
    expect(parseJsonList("{}")).toEqual([]);
    expect(parseJsonList("not json")).toEqual([]);
    expect(parseJsonList(null)).toEqual([]);
  });
});

describe("parseTenderFilters", () => {
  it("defaults and clamps", () => {
    const f = parseTenderFilters(new URLSearchParams(""));
    expect(f).toEqual({ q: "", status: "Live", ministry: "", district: "", category: "", page: 1, size: 25 });
    const g = parseTenderFilters(new URLSearchParams("status=all&page=0&size=999&q=%20printer%20"));
    expect(g.status).toBe("all");
    expect(g.page).toBe(1);
    expect(g.size).toBe(100);
    expect(g.q).toBe("printer");
  });
});

describe("tenderListQuery", () => {
  it("builds a parameterised query with filters and paging", () => {
    const { sql, params } = tenderListQuery({ q: "printer", status: "Live", ministry: "Ministry of Finance", district: "", category: "", page: 3, size: 25 });
    expect(sql).toContain("FROM tenders");
    expect(sql).toContain("status = ?");
    expect(sql).toContain("title LIKE ?");
    expect(sql).toContain("ministry = ?");
    expect(sql).toContain("ORDER BY published_at DESC");
    expect(sql).toContain("LIMIT ? OFFSET ?");
    expect(params).toEqual(["Live", "%printer%", "Ministry of Finance", 25, 50]);
  });
  it("omits the status clause for all", () => {
    const { sql, params } = tenderListQuery({ q: "", status: "all", ministry: "", district: "", category: "", page: 1, size: 10 });
    expect(sql).not.toContain("status = ?");
    expect(sql).not.toContain("category = ?");
    expect(params).toEqual([10, 0]);
  });
  it("filters by category when given", () => {
    const { sql, params } = tenderListQuery({ q: "", status: "Live", ministry: "", district: "", category: "medical", page: 1, size: 10 });
    expect(sql).toContain("category = ?");
    expect(params).toEqual(["Live", "medical", 10, 0]);
    expect(parseTenderFilters(new URLSearchParams("category=medical")).category).toBe("medical");
  });
});

describe("detail queries", () => {
  it("tender by id joins the contract", () => {
    const q = tenderByIdQuery("123");
    expect(q.sql).toContain("LEFT JOIN contracts");
    expect(q.params).toEqual(["123"]);
  });
  it("bidder and pe queries take one id", () => {
    expect(bidderQuery("b1").params).toEqual(["b1"]);
    expect(peQuery("p1").params).toEqual(["p1"]);
  });
});
